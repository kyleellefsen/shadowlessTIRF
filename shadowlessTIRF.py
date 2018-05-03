# -*- coding: utf-8 -*-
"""
Created on Fri Jun 20 19:06:55 2014
@author: Kyle Ellefsen

This program controls the mirrors attached to the galvos.   The position of one mirror is controlled by a sine wave, the other mirror is controlled by a cosine wave.  
When a laser is reflected off both mirrors, it spins in a circle.  This can be used to position the laser for shadowless TIRF microscopy.  

Make sure that the National Instruments DAC PCI-6733 is "Dev2" with the National Instruments Measurement and Automation tool.  
To view pins, look at http://www.ni.com/pdf/manuals/371232b.pdf figure 4. 
- Pin 57 (ao2) is the sine wave.  
- Pin 25 (ao3) is the cosine wave.  
- Pin 60 (ao4) is the ttl pulse which is which is triggered at the beginning of every period and should be plugged into Pin 1 (top right) of the Cascade Photometrics Model 128 camera. 
- Pin 69 (analog ground) should be plugged into Pin 3 of the Camera (top, third pin from right). 

The blue laser is pin 28 (ao5). Ground is pin 29.
The green laser is pin 30 (ao6).  Ground is pin 31.

To Use:
Run this program with python.  
Open MetaMorph.  In MetaMorph:
    Acquire->Acquire
        Trigger Mode: External (STROBED)
        Live Trigger Mode: External (STROBED)
    Acquire->Stream Acquisition->Camera Parameters
        Aquisition Mode: Acquire images from each extrnal trigger
        Make sure, if you check 'Display preview image during acquisition', that you aren't updating too often, or you will miss frames.

    
LASER CONTROL:
WIRES:
green  - ground
blue   - blue laser (488nm)
yellow - green laser
TTL control info:
Green laser is active low
Blue laser is active high
Blue laser requires "Digital:Power" mode in 'Coherent Connection' software to be operated via ttl pulse.
"""
import os, sys, time
from os.path import expanduser
os.chdir(os.path.split(os.path.realpath(__file__))[0])
from PyDAQmx import *
from PyDAQmx.DAQmxCallBack import *
import numpy as np
from qtpy.QtWidgets import *
from qtpy.QtGui import *
from qtpy.QtCore import *
from qtpy.QtCore import Signal, Slot
import pickle


class Settings:
    ''' This class saves all the settings as you adjust them.  This way, when you close the program and reopen it, all your settings will automatically load as they were just after the last adjustement'''
    def __init__(self):
        self.i=0
        self.config_file=os.path.join(expanduser("~"),'.ShadowlessTIRF','config.p')
        try:
            self.d=pickle.load(open(self.config_file, "rb" ))
        except IOError:
            a=dict()
            a['frequency']=200 #Hz
            a['radius']=.93 #in volts.  Max amplitude is 10 volts
            a['ellipticity']=.49
            a['phase']=-.001
            a['x_shift']=.04
            a['y_shift']=-.028
            a['alternate12']=False # When this is true, settings 1 and 2 are alternated every cycle.
            a['alternate123']=False # When this is true, settings 1,2 and 3 are cycled through.
            a['blue_laser']=False
            a['green_laser']=False
            a['green_laser_power']=5 #in volts
            a['blue_laser_power']=5 #in volts
            self.d=[a,a.copy(),a.copy(),a.copy()]
    def __getitem__(self, item):
        return self.d[self.i][item]
    def __setitem__(self,key,item):
        self.d[self.i][key]=item
    def save(self):
        '''save to a config file.'''
        if not os.path.exists(os.path.dirname(self.config_file)):
            os.makedirs(os.path.dirname(self.config_file))
        pickle.dump(self.d, open(self.config_file, "wb" ))
    def keys(self):
        return self.d[self.i].keys()
        

        
class GalvoDriver(QWidget):
    ''' This class sends creates the signal which will control the two galvos and the lasers, and sends it to the DAQ.'''
    finished_acquire_sig=Signal()
    def __init__(self,settings):
        QWidget.__init__(self)
        self.settings=settings
        self.sample_rate=1000000 # Maximum for the NI PCI-6733 is 1MHz.
        self.sampsPerPeriod=1 #dummy variable
        self.calculate()
        self.read = int32()
        self.createTask()
        self.hide()
    def createTask(self):
        self.analog_output = Task()
        self.analog_output.CreateAOVoltageChan("Dev1/ao0","",-10.0,10.0,DAQmx_Val_Volts,None) # sine wave
        self.analog_output.CreateAOVoltageChan("Dev1/ao1","",-10.0,10.0,DAQmx_Val_Volts,None) # cosine wave
        # self.analog_output.CreateAOVoltageChan("Dev1/ao4","",-10.0,10.0,DAQmx_Val_Volts,None) #On the NI PCI-6733, ao4 is pin 60 and ground is 59
        # self.analog_output.CreateAOVoltageChan("Dev1/ao5","",-10.0,10.0,DAQmx_Val_Volts,None) #On the NI PCI-6733, ao5 is pin 28 and ground is 29. This is blue laser
        # self.analog_output.CreateAOVoltageChan("Dev1/ao6","",-10.0,10.0,DAQmx_Val_Volts,None) #On the NI PCI-6733, ao6 is pin 30 and ground is 31. This is green laser


                        #  CfgSampClkTiming(source, rate, activeEdge, sampleMode, sampsPerChan)
        self.analog_output.CfgSampClkTiming("",self.sample_rate,DAQmx_Val_Rising,DAQmx_Val_ContSamps,self.sampsPerPeriod)
                        #  WriteAnalogF64(numSampsPerChan, autoStart, timeout, dataLayout, writeArray, sampsPerChanWritten, reserved)
        self.analog_output.WriteAnalogF64(self.sampsPerPeriod,0,-1,DAQmx_Val_GroupByChannel,self.data,byref(self.read),None) 
        self.analog_output.StartTask()
        self.stopped=False
        self.acquiring=False
        
        
        
        
    def getSinCosTTL(self,frequency,radius,ellipticity,phase,x_shift,y_shift,blue_laser,green_laser,blue_laser_power,green_laser_power,period=.005):
        ''' The period argument is only used when the value of the frequency is 0'''
        if frequency==0:
            t=np.arange(0,period,1/self.sample_rate)
            sinwave=radius*np.sin(np.zeros(len(t)))+x_shift/1000
            coswave=(ellipticity*radius*np.cos(np.zeros(len(t))+phase*(2*np.pi/360)))+(y_shift/1000)
        else:
            period=1/frequency
            t=np.arange(0,period,1/self.sample_rate )
            sinwave=radius*np.sin(frequency*(t*(2*np.pi)))+x_shift/1000
            coswave=(ellipticity*radius*np.cos(frequency*t*2*np.pi+phase*(2*np.pi/360)))+(y_shift/1000)
            camera_ttl=np.zeros(len(t))
            camera_ttl[0]=5
        camera_ttl=np.zeros(len(t))
        camera_ttl[0]=5
        return sinwave, coswave
    def calculate(self):
        s=self.settings
        if s['alternate12'] is False and s['alternate123'] is False:
            sinwave, coswave = self.getSinCosTTL(s['frequency'],s['radius'],s['ellipticity'],s['phase'],s['x_shift'],s['y_shift'],s['blue_laser'],s['green_laser'],s['blue_laser_power'],s['green_laser_power'])
            self.data=np.concatenate((sinwave,coswave))
            self.sampsPerPeriod=len(sinwave)
        elif s['alternate12']:
            f1=s.d[1]['frequency']
            f2=s.d[2]['frequency']
            if f1==0 and f2==0:
                period1=.005; period2=.005; #Alternate every 5ms if there is the frequency for both setting #1 and setting #2 is 0
            elif f1==0:
                period1=1/f2; period2=period1 #Give adopt the period of setting #2 if the frequency for setting #1 is 0
            elif f2==0:
                period1=1/f1; period2=period1
            else:
                period1=1/f1; period2=1/f2
            sinwave1, coswave1 = self.getSinCosTTL(f1,s.d[1]['radius'],s.d[1]['ellipticity'],s.d[1]['phase'],s.d[1]['x_shift'],s.d[1]['y_shift'],s.d[1]['blue_laser'],s.d[1]['green_laser'],s.d[1]['blue_laser_power'],s.d[1]['green_laser_power'],period1)
            sinwave2, coswave2 = self.getSinCosTTL(f2,s.d[2]['radius'],s.d[2]['ellipticity'],s.d[2]['phase'],s.d[2]['x_shift'],s.d[2]['y_shift'],s.d[2]['blue_laser'],s.d[2]['green_laser'],s.d[2]['blue_laser_power'],s.d[2]['green_laser_power'],period2)
            self.data=np.concatenate((sinwave1,sinwave2,coswave1,coswave2))
            self.sampsPerPeriod=len(sinwave1)+len(sinwave2)
        elif s['alternate123']:
            f1=s.d[1]['frequency']
            f2=s.d[2]['frequency']
            f3=s.d[3]['frequency']
            if f1==0 and f2==0 and f3==0:
                period1=.005; period2=.005; period3=.005;
            elif f1==0 and f2==0:
                period3=1/f3; period2=period3; period1=period3;
            elif f1==0 and f3==0:
                period2=1/f2; period1=period2; period3=period2
            elif f2==0 and f3==0:
                period1=1/f1; period2=period1; period3=period1
            elif f1==0:
                period2=1/f2; period3=1/f3; period1=period2
            elif f2==0:
                period1=1/f1; period2=period1; period3=1/f3
            elif f3==0:
                period1=1/f1; period2=1/f2; period3=period1
            else:
                period1=1/f1; period2=1/f2; period3=1/f3
            sinwave1, coswave1=self.getSinCosTTL(f1,s.d[1]['radius'],s.d[1]['ellipticity'],s.d[1]['phase'],s.d[1]['x_shift'],s.d[1]['y_shift'],s.d[1]['blue_laser'],s.d[1]['green_laser'],s.d[1]['blue_laser_power'],s.d[1]['green_laser_power'],period1)
            sinwave2, coswave2=self.getSinCosTTL(f2,s.d[2]['radius'],s.d[2]['ellipticity'],s.d[2]['phase'],s.d[2]['x_shift'],s.d[2]['y_shift'],s.d[2]['blue_laser'],s.d[2]['green_laser'],s.d[2]['blue_laser_power'],s.d[2]['green_laser_power'],period2)
            sinwave3, coswave3=self.getSinCosTTL(f3,s.d[3]['radius'],s.d[3]['ellipticity'],s.d[3]['phase'],s.d[3]['x_shift'],s.d[3]['y_shift'],s.d[3]['blue_laser'],s.d[3]['green_laser'],s.d[3]['blue_laser_power'],s.d[3]['green_laser_power'],period3)
            self.data = np.concatenate((sinwave1, sinwave2, sinwave3, coswave1, coswave2, coswave3))
            self.sampsPerPeriod = len(sinwave1)+len(sinwave2)+len(sinwave3)
    def startstop(self):
        if self.stopped:
            self.analog_output.StartTask()
            self.stopped=False
            self.refresh()
        else:
            self.settings.d[0]['frequency']=0
            self.settings.d[0]['radius']=.6
            self.settings.d[0]['alternate']=False
            self.refresh()
            self.analog_output.StopTask()
            self.stopped=True
    def refresh(self):
        if self.stopped is False:
            self.calculate()
            self.analog_output.StopTask()
            self.analog_output.CfgSampClkTiming("",self.sample_rate,DAQmx_Val_Rising,DAQmx_Val_ContSamps,self.sampsPerPeriod)
            self.analog_output.WriteAnalogF64(self.sampsPerPeriod,0,-1,DAQmx_Val_GroupByChannel,self.data,byref(self.read),None) 
            self.analog_output.StartTask()
    def acquire(self):
        print('Acquiring')
        self.acquiring=True
        self.counter=0
        self.tic=time.time()
        radius=self.settings.d[0]['radius']; alternate12=self.settings.d[0]['alternate12']; alternate123=self.settings.d[0]['alternate123']
        self.settings['radius']=.6
        self.settings['alternate12']=False
        self.settings['alternate123']=False
        self.calculate()
        self.settings['radius']=radius; self.settings['alternate12']=alternate12; self.settings['alternate123']=alternate123
        if self.stopped is False:
            self.analog_output.StopTask()
        self.EveryNCallback = DAQmxEveryNSamplesEventCallbackPtr(self.EveryNCallback_py)
        self.nSamples=int(self.sampsPerPeriod)
        DAQmxRegisterEveryNSamplesEvent(self.analog_output.taskHandle,DAQmx_Val_Transferred_From_Buffer,self.nSamples,0,self.EveryNCallback,None)
        self.analog_output.CfgSampClkTiming("",self.sample_rate,DAQmx_Val_Rising,DAQmx_Val_ContSamps,self.sampsPerPeriod)
        self.analog_output.WriteAnalogF64(self.sampsPerPeriod,0,-1,DAQmx_Val_GroupByChannel,self.data,byref(self.read),None)         
        self.analog_output.StartTask()
        self.stopped=False
        
    def EveryNCallback_py(self,taskHandle, status, callbackData,sure):
        self.counter+=1
        if self.counter==100:
            self.calculate()
            self.analog_output.StopTask()
            self.analog_output.CfgSampClkTiming("",self.sample_rate,DAQmx_Val_Rising,DAQmx_Val_ContSamps,self.sampsPerPeriod)
            self.analog_output.WriteAnalogF64(self.sampsPerPeriod,0,-1,DAQmx_Val_GroupByChannel,self.data,byref(self.read),None)         
            self.analog_output.StartTask()
            print('Opened "shutter" because counter reached {}'.format(self.counter))
        if self.counter==200:
            self.stopAcquiring()
            print('Stopped Acquiring because counter reached {}'.format(self.counter))
        #print(time.time()-self.tic)
        return 0 # The function should return an integer
    def stopAcquiring(self):
        self.settings.d[0]['frequency']=0
        self.settings.d[0]['radius']=.6
        self.settings.d[0]['alternate12']=False
        self.settings.d[0]['alternate123']=False
        self.calculate()
        self.createTask()
        self.startstop()
        self.acquiring=False
        self.finished_acquire_sig.emit()
        #maingui.acquireButton.setStyleSheet("background-color: green");
            
        
        

##############################################################################
####   GRAPHICAL USER INTERFACE ##############################################
##############################################################################
class SliderLabel(QWidget):
    '''SliderLabel is a widget containing a QSlider and a QSpinBox (or QDoubleSpinBox if decimals are required)
    The QSlider and SpinBox are connected so that a change in one causes the other to change. 
    '''
    changeSignal=Signal(int)
    def __init__(self,decimals=0): #decimals specifies the resolution of the slider.  0 means only integers,  1 means the tens place, etc.
        QWidget.__init__(self)
        self.slider=QSlider(Qt.Horizontal)
        self.decimals=decimals
        if self.decimals<=0:
            self.label=QSpinBox()
        else:
            self.label=QDoubleSpinBox()
            self.label.setDecimals(self.decimals)
        self.layout=QHBoxLayout()
        self.layout.addWidget(self.slider)
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)
        self.slider.valueChanged.connect(lambda val: self.updateLabel(val/10**self.decimals))
        self.label.valueChanged.connect(self.updateSlider)
        self.valueChanged=self.label.valueChanged
    @Slot(int, float)
    def updateSlider(self,value):
        self.slider.setValue(int(value*10**self.decimals))
    def updateLabel(self,value):
        self.label.setValue(value)
    def value(self):
        return self.label.value()
    def setRange(self,minn,maxx):
        self.slider.setRange(minn*10**self.decimals,maxx*10**self.decimals)
        self.label.setRange(minn,maxx)
    def setMinimum(self,minn):
        self.slider.setMinimum(minn*10**self.decimals)
        self.label.setMinimum(minn)
    def setMaximum(self,maxx):
        self.slider.setMaximum(maxx*10**self.decimals)
        self.label.setMaximum(maxx)
    def setValue(self,value):
        self.slider.setValue(value*10**self.decimals)
        self.label.setValue(value)
class FrequencySlider(SliderLabel):
    '''This is a modified SliderLabel class that prevents the user from setting a value between 0 and 1.  This controls the frequency of the sin wave.  Otherwise, the period could be too long, and you can only update any values at phase=0.
    '''
    def __init__(self,demicals=0):
        SliderLabel.__init__(self,demicals)
    def updateSlider(self,value):
        if value>0 and value<1:
            value=0
        self.slider.setValue(int(value*10**self.decimals))
    def updateLabel(self,value):
        if value>0 and value<1:
            value=0
        self.label.setValue(value)
class CheckBox(QCheckBox):
    ''' I overwrote the QCheckBox class so that every graphical element has the method 'setValue'
    '''
    def __init__(self,parent=None):
        QCheckBox.__init__(self,parent)
    def setValue(self,value):
        self.setChecked(value)

class MainGui(QWidget):
    ''' This class creates and controls the GUI '''
    changeSignal=Signal()
    def __init__(self):
        QWidget.__init__(self)
        self.setWindowTitle('Shadowless TIRF Galvo Driver')
        
        formlayout=QFormLayout()
        self.settings=Settings()
        self.galvoDriver=GalvoDriver(self.settings)
        frequency=FrequencySlider(3); frequency.setRange(0,500)
        radius=SliderLabel(3); radius.setRange(0,.6)
        ellipticity=SliderLabel(3); ellipticity.setRange(0,2.5)
        phase=SliderLabel(3); phase.setRange(-90,90)
        x_shift=SliderLabel(3); x_shift.setRange(-1000,1000)
        y_shift=SliderLabel(3); y_shift.setRange(-1000,1000)
        blue_laser_power=SliderLabel(3); blue_laser_power.setRange(-.08,5)
        green_laser_power=SliderLabel(3); green_laser_power.setRange(-.08,5)
        self.items=[]
        self.items.append({'name':'frequency','string':'Frequency (Hz)','object':frequency})
        self.items.append({'name':'radius','string':'Radius','object':radius})
        self.items.append({'name':'ellipticity','string':'Ellipticity','object':ellipticity})
        self.items.append({'name':'phase','string':'Phase','object':phase})
        self.items.append({'name':'x_shift','string':'x-shift','object':x_shift})
        self.items.append({'name':'y_shift','string':'y-shift','object':y_shift})
        self.items.append({'name':'blue_laser','string':'Blue Laser On','object':CheckBox()})
        self.items.append({'name':'green_laser','string':'Green Laser On','object':CheckBox()})
        self.items.append({'name':'blue_laser_power','string':'Blue Laser Power','object':blue_laser_power})
        self.items.append({'name':'green_laser_power','string':'Green Laser Power','object':green_laser_power})
        alternate12=CheckBox(); alternate123=CheckBox();
        self.items.append({'name':'alternate12','string':'Alternate between Setting 1 and Setting 2 every cycle','object':alternate12})
        self.items.append({'name':'alternate123','string':'Alternate between Setting 1, 2, and 3 every cycle','object':alternate123})
        for item in self.items:
            formlayout.addRow(item['string'],item['object'])
            item['object'].setValue(self.settings[item['name']])
            
        
        
        
        self.save1=QPushButton('Save'); self.save1.setStyleSheet("background-color: red"); self.save1.clicked.connect(lambda: self.memstore(1))
        self.save2=QPushButton('Save'); self.save2.setStyleSheet("background-color: red"); self.save2.clicked.connect(lambda: self.memstore(2))
        self.save3=QPushButton('Save'); self.save3.setStyleSheet("background-color: red"); self.save3.clicked.connect(lambda: self.memstore(3))
        self.recall1=QPushButton('Recall'); self.recall1.setStyleSheet("background-color: green"); self.recall1.clicked.connect(lambda: self.memrecall(1))
        self.recall2=QPushButton('Recall'); self.recall2.setStyleSheet("background-color: green"); self.recall2.clicked.connect(lambda: self.memrecall(2))
        self.recall3=QPushButton('Recall'); self.recall3.setStyleSheet("background-color: green"); self.recall3.clicked.connect(lambda: self.memrecall(3))
        
        memlayout=QGridLayout()
        memlayout.setHorizontalSpacing(70)
        memlayout.addWidget(QLabel('Setting #1'),0,0); memlayout.addWidget(self.save1,1,0); memlayout.addWidget(self.recall1,2,0)
        memlayout.addWidget(QLabel('Setting #2'),0,1); memlayout.addWidget(self.save2,1,1); memlayout.addWidget(self.recall2,2,1)
        memlayout.addWidget(QLabel('Setting #3'),0,2); memlayout.addWidget(self.save3,1,2); memlayout.addWidget(self.recall3,2,2)
        membox=QGroupBox("Settings")
        membox.setLayout(memlayout)
        
        self.stopButton=QPushButton('Stop'); self.stopButton.setStyleSheet("background-color: red"); self.stopButton.clicked.connect(self.startstop)
        self.acquireButton=QPushButton('Acquire'); self.acquireButton.setStyleSheet("background-color: green"); self.acquireButton.clicked.connect(self.acquire)
        self.acquireButton.hide() 
        self.galvoDriver.finished_acquire_sig.connect(self.finished_acquire)
        stopacquirebox=QGridLayout()
        stopacquirebox.addWidget(self.stopButton,0,0)
        stopacquirebox.addWidget(self.acquireButton,0,1)
        
        self.layout=QVBoxLayout()
        self.layout.addLayout(formlayout)
        self.layout.addWidget(membox)
        self.layout.addSpacing(100)
        self.layout.addLayout(stopacquirebox)
        self.setLayout(self.layout)
        self.connectToChangeSignal()
        self.changeSignal.connect(self.updateValues)
        self.setGeometry(QRect(488, 390, 704, 376))
        self.show()
    def connectToChangeSignal(self):
        for item in self.items:
            methods=[method for method in dir(item['object']) if callable(getattr(item['object'], method))]
            if 'valueChanged' in methods:
                item['object'].valueChanged.connect(self.changeSignal)
            elif 'stateChanged' in methods:
                item['object'].stateChanged.connect(self.changeSignal)
            elif 'currentIndexChanged' in methods:
                item['object'].currentIndexChanged.connect(self.changeSignal)
    def updateValues(self):
        for item in self.items:
            methods=[method for method in dir(item['object']) if callable(getattr(item['object'], method))]
            if 'value' in methods:
                item['value']=item['object'].value()
            elif 'currentText' in methods:
                item['value']=item['object'].currentText()
            elif 'isChecked' in methods:
                item['value']=item['object'].isChecked()
            self.settings[item['name']]=item['value']
        self.galvoDriver.refresh()
    def memrecall(self,i):
        '''i is the setting number we are recalling'''
        self.changeSignal.disconnect(self.updateValues)
        s=self.settings
        s.d[0]=s.d[i].copy()
        for item in self.items:
            item['object'].setValue(s.d[0][item['name']])
        self.changeSignal.connect(self.updateValues)
        self.galvoDriver.refresh()
    def memstore(self,i):
        '''i is the setting number we are storing.  settings.d[0] is always the current setting.'''
        self.settings.d[i]=self.settings.d[0].copy()
        self.settings.save()
    def acquire(self):
        if self.galvoDriver.acquiring is False: #if we haven't started acquiring
            self.updateValues()
            self.acquireButton.setText('Stop Acquiring')
            self.acquireButton.setStyleSheet("background-color: red");
            self.galvoDriver.acquire()
            self.stopButton.hide()
        else:
            self.acquireButton.setText('Acquire')
            self.acquireButton.setStyleSheet("background-color: green");
            self.galvoDriver.stopAcquiring()
            self.stopButton.show()
    def finished_acquire(self):
        self.acquireButton.setText('Acquire')
        self.acquireButton.setStyleSheet("background-color: green");
        self.stopButton.show()
    def startstop(self):
        if self.galvoDriver.stopped is False: #if we are free running
            self.galvoDriver.startstop()
            self.stopButton.setText('Free Run')
            self.stopButton.setStyleSheet("background-color: green");
            self.acquireButton.show()
        else:
            self.updateValues()
            self.galvoDriver.startstop()
            self.stopButton.setText('Stop Free Run')
            self.stopButton.setStyleSheet("background-color: red");
            self.acquireButton.hide()


    
if __name__ == '__main__':
    app = QApplication(sys.argv)
    maingui=MainGui()
    sys.exit(app.exec_())
    