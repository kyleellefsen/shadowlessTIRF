"""
National instruments test file

"""

from PyDAQmx import *
from PyDAQmx.DAQmxCallBack import *
import numpy as np
from ctypes import byref

def generate_signal():
    period = 1
    ao_rate = 250000 # Maximum analog output rate for the NI USB-6211 is 250 kHz.
    t = np.arange(0, period, 1/ao_rate)
    frequency = 100
    sinewave =  np.sin(frequency*(t*(2*np.pi)))
    writeArray = np.concatenate((sinewave, sinewave))
    return writeArray



def setup_task(writeArray, read):
    ao_rate = 250000 # Maximum analog output rate for the NI USB-6211 is 250 kHz.
    sampsPerPeriod = 1 #dummy variable
    ao = Task()
    ao.CreateAOVoltageChan("Dev1/ao0", '', -10.0, 10.0, DAQmx_Val_Volts, None)
    ao.CreateAOVoltageChan("Dev1/ao1", '', -10.0, 10.0, DAQmx_Val_Volts, None)
    ao.CfgSampClkTiming('', ao_rate, DAQmx_Val_Rising, DAQmx_Val_ContSamps, sampsPerPeriod)   # CfgSampClkTiming(source, rate, activeEdge, sampleMode, sampsPerChan)
 #  WriteAnalogF64(numSampsPerChan, autoStart, timeout, dataLayout, writeArray, sampsPerChanWritten, reserved)
    ao.WriteAnalogF64(sampsPerPeriod, 0, -1, DAQmx_Val_GroupByChannel, writeArray, byref(read), None) 
    ao.StartTask()
    return ao


read = int32()
writeArray = generate_signal()
ao = setup_task(read, read)