"""
`batterytester`
============================================================
Li-Ion Battery Tester by barbudor
------------------------------------------------------------
Allows to test capacity of Li-Ion batteries in //
Based on
- AdafruitCircuit Playground Express running CPy 4.0.0beta
- INA3221 for voltage/current measurement
   driver: https://github.com/barbudor/Adafruit_CircuitPython_INA219
- 4 relays board (Chinese, such as SainSmart)
"""

import time
import os
import storage
from micropython import const
import digitalio
import board
import neopixel

from barbudor_ina3221_lite import INA3221


class Tester:
    """battery tester state-machine"""

    # pylint: disable=bad-whitespace
    # states
    _STATE_WAITING            = const(0)
    _STATE_RUNNING            = const(2)
    _STATE_RUNNING_FAST       = const(4)
    _STATE_ENDING             = const(8)
    _STATE_ENDED              = const(9)

    # CPX pin labels for relays
    _RELAY_ON                 = const(0)
    _RELAY_OFF                = const(1)

    # CPX neopixel index
    _PIX_WAITING = (0, 0, 85)
    _PIX_RUNNING = (0, 85, 0)
    _PIX_RUNNING_FAST = (10, 85, 0)
    _PIX_ENDING = (85, 85, 0)
    _PIX_ENDED = (255, 0, 0)
    _PIX_OFF = (0, 0, 0)

    # INA3221 resistor value
    _SHUNT_VALUE              = 0.1

    _FILE_COUNTER             = "/tester.count"
    _FILE_LOG                 = "/battery%03d.csv"
    _LOG_HEADER               = "File: %s\nTime; Voltage (V); Current (A)\n"
    _LOG_FORMAT               = "%9.2f; %6.3f; %6.3f\n"

    _SAMPLE_PERIOD_DEFAULT    = 10.0
    _SAMPLE_PERIOD_FAST       = 1.0
    _SAMPLE_PERIOD_ENDING     = 0.5
    _ENDING_DURATION          = const(60)

    _END_VOLTAGE              = 3.0
    # pylint: enable=bad-whitespace

    def _setpix(self, color):
        cpx_pixels[self.pixel] = color

    def _getpix(self):
        return cpx_pixels[self.pixel]

    def _read_file_counter(self):
        counter = 0
        try:
            with open(Tester._FILE_COUNTER, "r") as file:
                line = file.readline()
                line = line.strip()
                counter = int(line)
                print("%9.2f:[%d]: read counter %d" % (time.monotonic(), self.channel, counter))
        except:
            print("%9.2f:[%d]: read counter default %d" % (time.monotonic(), self.channel, counter))
            #pass
        return counter

    def _write_file_counter(self, counter):
        print("%9.2f:[%d]: write counter %d" % (time.monotonic(), self.channel, counter))
        try:
            with open(Tester._FILE_COUNTER, "w") as file:
                file.write("%d\n" % counter)
        except:
            pass

    def _read_v_and_i_sim(self):
        voltage = 4.200
        current = 0.000
        if self.relay.value == Tester._RELAY_ON:
            if self.previous_voltage < 3.4:
                voltage = 4.000-(self.sample_count/(10.0+self.channel))
                current = 1.123-(self.sample_count/(40.0+self.channel))
            else:
                voltage = 4.000-(self.sample_count/(20.0+self.channel))
                current = 1.123-(self.sample_count/(40.0+self.channel))
        self.sample_count += 1
        print("%9.2f:[%d]: %5.3fV %5.3fA" % (time.monotonic(), self.channel, voltage, current))
        return (voltage, current)

    def _read_v_and_i(self):
        #return self._read_v_and_i_sim()
        voltage = self.sensor.bus_voltage(self.channel)
        current = self.sensor.current(self.channel)
        return (voltage, current)


    def _write_log(self, timestamp, voltage, current):
        with open(self.logfilename, "a") as file:
            file.write(Tester._LOG_FORMAT % (timestamp, voltage, current))

    def __init__(self, sensor, channel, pin, neopixel):
        self.relay = digitalio.DigitalInOut(pin)
        self.relay.switch_to_output(value=Tester._RELAY_OFF)
        self.sensor = sensor
        self.channel = channel
        self.pixel = neopixel
        self.sample_count = 0
        self.sample_period = 0
        self.ending = 0
        self.state = Tester._STATE_WAITING
        self._setpix(Tester._PIX_WAITING)

    def __del__(self):
        self.deinit()

    def deinit(self):
        self.state = Tester._STATE_WAITING
        self._setpix(Tester._PIX_WAITING)
        self.relay.value = Tester._RELAY_OFF

    def start(self):
        # initialise state machine
        self.sample_count = 0
        self.sample_period = Tester._SAMPLE_PERIOD_DEFAULT
        self.ending = Tester._ENDING_DURATION
        self.state = Tester._STATE_RUNNING
        pixel = Tester._PIX_RUNNING
        self._setpix(tuple(3*x for x in pixel))
        # create log file
        filecount = self._read_file_counter()
        self.logfilename = Tester._FILE_LOG % filecount
        with open(self.logfilename, "w") as file:
            file.write(Tester._LOG_HEADER % self.logfilename)
        self._write_file_counter(filecount+1)
        print("%9.2f:[%d]: starting '%s'" % (time.monotonic(), self.channel, self.logfilename))
        # initial sample performed with relay off (battery not loaded)
        self.start_time = time.monotonic()
        (voltage, current) = self._read_v_and_i()
        self._write_log(0, voltage, current)
        # switch on the load relay
        self.relay.value = Tester._RELAY_ON
        # initialise some values
        self.previous_voltage = voltage
        self.previous_delta_v = 5.0
        # 1st sample after switching on the load is done just 1 sec after
        self.next_time = self.start_time + 1.0
        # restore pixel
        self._setpix(pixel)

    def run(self):
        if self.state < Tester._STATE_ENDED:
            now = time.monotonic()
            if now >= self.next_time:
                print("%9.2f:[%d]: sample" % (time.monotonic(), self.channel))
                # save current pixel then increase light
                pixel = self._getpix()
                self._setpix(tuple(3*x for x in pixel))
                (voltage, current) = self._read_v_and_i()
                self._write_log(now - self.start_time, voltage, current)

        delta_v = self.previous_voltage - voltage
        print("%9.2f:[%d]: dV=%f pdV=%f" % \
            (time.monotonic(), self.channel, delta_v, self.previous_delta_v))
        if self.state < Tester._STATE_RUNNING_FAST:
            if delta_v >= (1.5 * self.previous_delta_v):
                print("%9.2f:[%d]: ->run_fast" % (time.monotonic(), self.channel))
                self.state = Tester._STATE_RUNNING_FAST
                pixel = Tester._PIX_RUNNING_FAST
                self.sample_period = Tester._SAMPLE_PERIOD_FAST
            self.previous_delta_v = delta_v
            self.previous_voltage = voltage

        if self.state < Tester._STATE_ENDING:
            if voltage <= Tester._END_VOLTAGE:
                print("%9.2f:[%d]: ->ending" % (time.monotonic(), self.channel))
                self.relay.value = Tester._RELAY_OFF
                self.state = Tester._STATE_ENDING
                pixel = Tester._PIX_ENDING
                self.sample_period = Tester._SAMPLE_PERIOD_ENDING

        if self.state == Tester._STATE_ENDING:
            self.ending -= 1
            if self.ending == 0:
                print("%9.2f:[%d]: ended" % (time.monotonic(), self.channel))
                self.state = Tester._STATE_ENDED
                pixel = Tester._PIX_ENDED

        # restore pixel or update to new
        self._setpix(pixel)
        self.next_time += self.sample_period


################################################################################

cpx_pixels = NeoPixel(board.NEOPIXEL,10)
cpx_pixels.brightness = 0.1

# create measure chip
i2c_bus = board.I2C()
ina = INA3221(i2c_bus)

# create testers
#testers = (Tester(ina, 1, board.A1, 6), Tester(ina, 2, board.A2, 7), Tester(ina, 3, board.A3, 8))
testers = [Tester(ina, 1, board.A1, 6)]

def RunTest():
    # check if FS is writable
    try:
        with open("/test.test", "w") as f:
            f.write("tested\n")
        os.remove("/test.test")
    except:
        try:
            storage.remount("/", False)
        except:
            cpx_pixels[0] = (255, 0, 0,)
            while True:
                pass

    # wait press A to start
    while not cpx.button_a:
        cpx.red_led = not cpx.red_led
        time.sleep(0.200)
        cpx.red_led = False

    # start state-machines
    for t in testers:
        t.start()

    # test loop, press B to exit
    while not cpx.button_b:
        for t in testers:
            t.run()

    # clean-up
    for t in testers:
        t.deinit()

################################################################################

#RunTest()
