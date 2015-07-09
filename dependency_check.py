import urllib2
import os
from os.path import basename
import pip
from sys import platform as _platform
import time

if _platform != "win32":
    print("This software has only been tested on Windows 7.  In order to run it on a different operating system, you'll need to manually install the dependencies.")

def download_file(download_url):
    req = urllib2.Request(download_url,headers={'User-Agent':"Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/43.0.2357.132 Safari/537.36"})
    response = urllib2.urlopen(req)
    file = open(basename(download_url), 'wb')
    the_page=response.read()
    file.write(the_page)
    file.close()
try:
    import PyQt4
except ImportError:
    print('Downloading and installing PyQt4')
    download_url='http://www.lfd.uci.edu/~gohlke/pythonlibs/3i673h27/PyQt4-4.11.4-cp27-none-win_amd64.whl'
    download_file(download_url)
    pip.main(['install', basename(download_url)])
    os.remove(basename(download_url))
    
try:
    import numpy
except ImportError:
    print('Downloading and installing numpy')
    download_url='http://www.lfd.uci.edu/~gohlke/pythonlibs/3i673h27/numpy-1.9.2+mkl-cp27-none-win_amd64.whl'
    download_file(download_url)
    pip.main(['install', basename(download_url)])
    os.remove(basename(download_url))
    
try:
    import PyDAQmx
except ImportError:
    print('Downloading and installing PyDAQmx')
    pip.main(['install', 'PyDAQmx'])
except NotImplementedError:
    print('\n\nMake sure you have installed the niDAXmx library before running shadowlessTIRF.  Your niDAXmx library could not be found.\n\n')
    time.sleep(3)