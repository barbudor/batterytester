"""
`batterytester`
============================================================
Li-Ion Battery Tester by barbudor
------------------------------------------------------------
Allows to test capacity of Li-Ion batteries in //
Based on
- AdafruitCircuit Playground Express running CPy 4.0.0beta
- INA3221 for voltage/current measurement
   driver: https://github.com/barbudor/CircuitPython_INA3221
- 4 relays board (Chinese, such as SainSmart)
"""

# biggest lib to be imported 1st to reduce memory fragmentation
from barbudor_ina3221_lite import INA3221
import batterytester
import time
import os
import sys
import storage
import board
from neopixel import NeoPixel
import digitalio

# neopixels
pixels = NeoPixel(board.NEOPIXEL, 10)
pixels.brightness = 0.1

# check if FS is writable
try:
    with open("/test.test", "w") as f:
        f.write("tested\n")
    os.remove("/test.test")
except:
    try:
        storage.remount("/", False)
    except:
        pixels[0] = (80, 0, 0,)
        while True:
            pass

button_a = digitalio.DigitalInOut(board.BUTTON_A)
button_a.switch_to_input(digitalio.Pull.DOWN)
button_b = digitalio.DigitalInOut(board.BUTTON_B)
button_b.switch_to_input(digitalio.Pull.DOWN)

# create measure chip
i2c_bus = board.I2C()
ina = INA3221(i2c_bus)

_RELAYPIN_CHAN = (board.A1, board.A2, board.A3)
_NEOPIX_CHAN = (6, 7, 8)

def test(number_of_batteries=1):

    testers = []
    for slot in range(0, number_of_batteries):
        print("Name of battery in slot #%d: " % (slot+1), end='')
        battery_name = sys.stdin.readline().strip()
        print(battery_name)
        relay = digitalio.DigitalInOut(_RELAYPIN_CHAN[slot])
        relay.switch_to_output(value=True)
        testers.append(batterytester.Tester(battery_name, ina, slot+1, relay, \
            pixels, _NEOPIX_CHAN[slot]))

    # wait press A to start
    print("Press button 'A' to start the test")
    while not button_a.value:
        pixels[0] = (0, 80, 0)
        time.sleep(0.200)
        pixels[0] = (0, 0, 0)
    print("Press button 'B' to end the test at anytime")

    # start state-machines (create files and enable measurment)
    for t in testers:
        t.start()

    # test loop, press B to exit
    while not button_b.value:
        for t in testers:
            t.run()

    # clean-up
    for t in testers:
        t.deinit()

################################################################################
