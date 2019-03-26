
Introduction
============

Battery-tester for up to 3 batteries (typically Li-* batteries). The circuite uses a INA3221 triple current
sensor to measure batteries voltage and current drawn during a discharge cycle. Measrumentss are logged into
the file system as CSV files which can then be imported in Excel in order to draw graph or perform additional
calculations.

Note :
I faced some memory problems with CircuitPlayground Express so I had to remove dependencies to 
adafruit_circuitplayground.express and use standard libs to acces neopixels and buttons.
Code has also been splitted in 2:
- batterrytester.py implements the state machine for the test. On systems with limited memory (SAMD21), 
  it must be precompiled to batterytester.mpy. Same applies to barbudor_ina3221 -> mpy
- runtest.py is the main script 

Running :
From REPL, execute
>>> import batterytester
>>> import runtest
>>> runtest.test()

Dependencies
=============
This script depends on:

* Adafruit CircuitPython `<https://github.com/adafruit/circuitpython>`
* Adafruit Bus Device `<https://github.com/adafruit/AdafruitCircuitPythonBusDevice>`
* Barbudor's CircuitPython_INA3221 driver `<https://github.com/barbudor/CircuitPython_INA3221>`

Contributing
============

This is a simple test I've done for my own usage which is not worth contribution.
But feel free to fork, copy and adapt for your own usage.
