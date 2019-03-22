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
from adafruit_circuitplayground.express import cpx
import time
import os
import storage
import digitalio
import board


# pylint: disable=bad-whitespace
# states
_STATE_WAITING              = 0
_STATE_RUNNING              = 2
_STATE_RUNNING_FAST         = 4
_STATE_RUNNING_FAST2        = 5
_STATE_ENDING               = 8
_STATE_ENDED                = 9

# pin labels for relays
_RELAY_ON                   = 0
_RELAY_OFF                  = 1

# neopixel values for representing states
_PIX_WAITING                = (  0,   0, 80)
_PIX_RUNNING                = (  0,  80,  0)
_PIX_RUNNING_FAST           = (  8,  80,  0)
_PIX_RUNNING_FAST2          = ( 25,  80,  0)
_PIX_ENDING                 = ( 80,  80,  0)
_PIX_ENDED                  = (255,   0,  0)
_PIX_OFF                    = (  0,   0,  0)

# INA3221 resistor value
_SHUNT_VALUE                = 0.1

_FILE_COUNTER               = "/testcount.txt"
_FILE_LOG                   = "/battery%03d.csv"
_LOG_HEADER                 = "File: %s\nTime;Voltage (V);Current (A);C (Ah)\n"
_LOG_FORMAT                 = "%7.1f;%6.3f;%6.3f;%6.3f\n"

_SAMPLE_PERIOD_DEFAULT      = 10.0
_SAMPLE_PERIOD_FAST         = 2.0
_SAMPLE_PERIOD_FAST2        = 0.5
_SAMPLE_PERIOD_ENDING       = 0.5
_ENDING_DURATION            = 120

_VOLTAGE_FAST               = 3.5
_VOLTAGE_FAST2              = 3.25
_VOLTAGE_END                = 2.9
# pylint: enable=bad-whitespace


class Tester:
    """battery tester state-machine"""

    def _setpix(self, color):
        cpx.pixels[self.pixel] = color

    def _getpix(self):
        return cpx.pixels[self.pixel]

    def _read_file_counter(self):
        counter = 0
        try:
            with open(_FILE_COUNTER, "r") as file:
                line = file.readline()
                line = line.strip()
                counter = int(line)
                #print("%9.2f:[%d]: read counter %d" % (time.monotonic(), self.channel, counter))
        except Exception as ex:
            #print("Exception ", ex.args)
            #print("%9.2f:[%d]: read counter default %d" % \
            #    (time.monotonic(), self.channel, counter))
            pass
        return counter

    def _write_file_counter(self, counter):
        #print("%9.2f:[%d]: write counter %d" % (time.monotonic(), self.channel, counter))
        try:
            with open(_FILE_COUNTER, "w") as file:
                file.write("%d\n" % counter)
        except:
            pass

    #def _read_v_and_i_sim(self):
    #    voltage = 4.200
    #    current = 0.000
    #    if self.relay.value == _RELAY_ON:
    #        if self.previous_voltage < 3.4:
    #            voltage = 4.000-(self.sample_count/(10.0+self.channel))
    #            current = 1.123-(self.sample_count/(40.0+self.channel))
    #        else:
    #            voltage = 4.000-(self.sample_count/(20.0+self.channel))
    #            current = 1.123-(self.sample_count/(40.0+self.channel))
    #    self.sample_count += 1
    #    print("%9.2f:[%d]: %5.3fV %5.3fA" % (time.monotonic(), self.channel, voltage, current))
    #    return (voltage, current)

    def _read_v_and_i(self):
        voltage = self.sensor.bus_voltage(self.channel)
        current = self.sensor.current(self.channel)
        return (voltage, current)

    def _create_log(self):
        filecount = self._read_file_counter()
        self.logfilename = _FILE_LOG % filecount
        with open(self.logfilename, "w") as file:
            file.write(_LOG_HEADER % self.logfilename)
        self._write_file_counter(filecount+1)

    def _write_log(self, timestamp, voltage, current, capacity):
        with open(self.logfilename, "a") as file:
            file.write(_LOG_FORMAT % (timestamp, voltage, current, capacity))

    def __init__(self, sensor, channel, pin, neopixel):
        self.relay = digitalio.DigitalInOut(pin)
        self.relay.switch_to_output(value=_RELAY_OFF)
        self.sensor = sensor
        self.channel = channel
        self.pixel = neopixel
        self.sample_count = 0
        self.sample_period = 0
        self.ending = 0
        self.previous_voltage = 4.2

        self.state = _STATE_WAITING
        self._setpix(_PIX_WAITING)

    def __del__(self):
        self.deinit()

    def deinit(self):
        self.state = _STATE_WAITING
        self._setpix(_PIX_WAITING)
        self.relay.value = _RELAY_OFF

    def start(self):
        # initialise state machine
        self.sample_period = _SAMPLE_PERIOD_DEFAULT
        self.ending = _ENDING_DURATION
        self.state = _STATE_RUNNING
        pixel = _PIX_RUNNING
        self._setpix(tuple(3*x for x in pixel))
        # start V & I measurement
        self.sensor.enable_channel(self.channel)
        # create log file
        self._create_log()
        print("%9.2f:[%d]: writing to '%s'" % (0.0, self.channel, self.logfilename))
        # initial sample performed with relay off (battery not loaded)
        self.start_time = time.monotonic()
        (voltage, current) = self._read_v_and_i()
        print("%9.2f:[%d]: sample %5.3fV, %5.3fA" % (0.0, self.channel, voltage, current))
        # initialise values
        self.sum_c = 0.0
        self.previous_voltage = voltage
        self.previous_current = current
        self.last_time = self.start_time - self.sample_period + 1.0
        # write 1st log entry
        self._write_log(0, voltage, current, self.sum_c)
        # switch on the load relay
        self.relay.value = _RELAY_ON
        # restore pixel
        self._setpix(pixel)

    def run(self):
        if self.state < _STATE_ENDED:
            now = time.monotonic()
            if now - self.last_time >= self.sample_period:
                # save current pixel then increase light
                pixel = self._getpix()
                self._setpix(tuple(3*x for x in pixel))
                (voltage, current) = self._read_v_and_i()
                print("%9.2f:[%d]: sample %5.3fV, %5.3fA" % \
                    (now-self.start_time, self.channel, voltage, current))
                delta_i = self.previous_current - current
                delta_t = now - self.last_time
                delta_c = delta_t * (self.previous_current + current) / (2.0 * 3600.0)
                self.last_time += self.sample_period

                if self.state < _STATE_RUNNING_FAST:
                    if voltage < _VOLTAGE_FAST:
                        print("%9.2f:[%d]: ->run_fast" % (now-self.start_time, self.channel))
                        self.state = _STATE_RUNNING_FAST
                        pixel = _PIX_RUNNING_FAST
                        self.sample_period = _SAMPLE_PERIOD_FAST

                if self.state < _STATE_RUNNING_FAST2:
                    if voltage < _VOLTAGE_FAST2:
                        print("%9.2f:[%d]: ->run_fast2" % (now-self.start_time, self.channel))
                        self.state = _STATE_RUNNING_FAST2
                        pixel = _PIX_RUNNING_FAST2
                        self.sample_period = _SAMPLE_PERIOD_FAST2

                if self.state < _STATE_ENDING:
                    self.sum_c += delta_c
                    if voltage <= _VOLTAGE_END:
                        print("%9.2f:[%d]: ->ending" % (now-self.start_time, self.channel))
                        self.relay.value = _RELAY_OFF
                        self.state = _STATE_ENDING
                        pixel = _PIX_ENDING
                        self.sample_period = _SAMPLE_PERIOD_ENDING

                if self.state == _STATE_ENDING:
                    self.ending -= 1
                    if self.ending == 0:
                        print("%9.2f:[%d]: ended" % (now-self.start_time, self.channel))
                        self.state = _STATE_ENDED
                        pixel = _PIX_ENDED

                self._write_log(now - self.start_time, voltage, current, self.sum_c)

                self.previous_voltage = voltage
                self.previous_current = current
                # restore pixel or update to new
                self._setpix(pixel)
            #if now >= self.next_time:
        #if self.state < _STATE_ENDED:
    #def run()


################################################################################

# check if FS is writable
try:
    with open("/test.test", "w") as f:
        f.write("tested\n")
    os.remove("/test.test")
except:
    try:
        storage.remount("/", False)
    except:
        cpx.pixels[0] = (255, 0, 0,)
        while True:
            pass


cpx.pixels.brightness = 0.1

# create measure chip
i2c_bus = board.I2C()
ina = INA3221(i2c_bus)

# create testers
#testers = (Tester(ina, 1, board.A1, 6), Tester(ina, 2, board.A2, 7), Tester(ina, 3, board.A3, 8))
testers = [Tester(ina, 1, board.A1, 6)]

def RunTest():

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
