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
# states, sample period, neopixels colors
# WAITING - From Testesr instance creation until start
_STATE_WAITING              = 0
_PIX_WAITING                = (  0,   0, 80)
# STARTING - Start with 1st sample with relay still off and move to RUN
_STATE_STARTING             = 1
# RUNNING - Mesure every _SAMPLE_PERIOD_DEFAULT
_STATE_RUNNING              = 2
_SAMPLE_PERIOD_DEFAULT      = 10.0
_PIX_RUNNING                = (  0,  80,  0)
# RUNNING_FAST - Accelerate mesure rate as soon as voltage drops below _VOLTAGE_FAST
_STATE_RUNNING_FAST         = 4
_VOLTAGE_FAST               = 3.5
_SAMPLE_PERIOD_FAST         = 2.0
_PIX_RUNNING_FAST           = (  8,  80,  0)
# RUNNING_FAST2 - Accelerate further when voltage dropx below _VOLTAGE_FAST2
_STATE_RUNNING_FAST2        = 5
_VOLTAGE_FAST2              = 3.25
_SAMPLE_PERIOD_FAST2        = 0.5
_PIX_RUNNING_FAST2          = ( 25,  80,  0)
# ENDING - As voltage drops below _VOLTAGE_END, relay is off and we keep measuring for _ENDING_DURATION_SAMPLES
_STATE_ENDING               = 8
_VOLTAGE_END                = 2.9
_SAMPLE_PERIOD_ENDING       = 0.5
_ENDING_DURATION            = 120
_PIX_ENDING                 = ( 80,  80,  0)
# END of all measurements if done _CYCLE_COUNT complete cycles
_CYCLE_COUNT                = 4
_STATE_ENDED                = 9
_PIX_ENDED                  = (255,   0,  0)

_PIX_OFF                    = (  0,   0,  0)

# pin labels for relays
_RELAY_ON                   = 0
_RELAY_OFF                  = 1

# INA3221 resistor value
_SHUNT_VALUE                = 0.1

# file names and log format
_FILE_COUNTER               = "/testcount.txt"
_FILE_LOG                   = "/battery%03d.csv"
_LOG_HEADER                 = "File: %s\nTime;Voltage (V);Current (A);C (Ah)\n"
#_LOG_FORMAT                 = "%7.1f;%6.3f;%6.3f;%6.3f\n"
_LOG_FORMAT                 = "%f;%f;%f;%f\n"
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
        return (self.sensor.bus_voltage(self.channel), self.sensor.current(self.channel))

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
        self.sample_count = 0
        self.sample_period = 0
        self.cycle_count = _CYCLE_COUNT
        self.state = _STATE_STARTING
        self.sum_c = 0.0
        # start V & I measurement
        self.sensor.enable_channel(self.channel)
        # create log file
        self._create_log()
        print("%9.2f:[%d]: writing to '%s'" % (0.0, self.channel, self.logfilename))

    def run(self):
        if self.state == _STATE_STARTING:
            self.state = _STATE_RUNNING
            pixel = _PIX_RUNNING
            self.sample_period = _SAMPLE_PERIOD_DEFAULT
            self._setpix(tuple(3*x for x in pixel))
            # initial sample performed with relay off (battery not loaded)
            self.start_time = time.monotonic()
            (voltage, current) = self._read_v_and_i()
            print("%9.2f:[%d]: sample %5.3fV, %5.3fA" % (0.0, self.channel, voltage, current))
            # write 1st log entry
            self._write_log(0, voltage, current, self.sum_c)
            # initialise values
            self.previous_voltage = voltage
            self.previous_current = current
            self.last_time = self.start_time - self.sample_period + 1.0
            # switch on the load relay
            self.relay.value = _RELAY_ON
            # next state is running
        elif self.state < _STATE_ENDED:
            now = time.monotonic()
            delta_t = now - self.last_time
            if delta_t >= self.sample_period:
                # save current pixel then increase light
                pixel = self._getpix()
                self._setpix(tuple(3*x for x in pixel))
                (voltage, current) = self._read_v_and_i()
                print("%9.2f:[%d]: sample %5.3fV, %5.3fA" % \
                    (now-self.start_time, self.channel, voltage, current))
                delta_i = self.previous_current - current
                delta_c = delta_t * (self.previous_current + current) / (2.0 * 3600.0)
                self.last_time += self.sample_period

                if self.state < _STATE_RUNNING_FAST:
                    if voltage < _VOLTAGE_FAST:
                        print("%9.2f:[%d]: ->run_fast" % (now-self.start_time, self.channel))
                        self.state = _STATE_RUNNING_FAST
                        pixel = _PIX_RUNNING_FAST
                        self.sample_period = _SAMPLE_PERIOD_FAST
                # endif self.state < _STATE_RUNNING_FAST:

                if self.state < _STATE_RUNNING_FAST2:
                    if voltage < _VOLTAGE_FAST2:
                        print("%9.2f:[%d]: ->run_fast2" % (now-self.start_time, self.channel))
                        self.state = _STATE_RUNNING_FAST2
                        pixel = _PIX_RUNNING_FAST2
                        self.sample_period = _SAMPLE_PERIOD_FAST2
                # endif self.state < _STATE_RUNNING_FAST2:

                if self.state < _STATE_ENDING:
                    self.sum_c += delta_c
                    if voltage <= _VOLTAGE_END:
                        print("%9.2f:[%d]: ->ending cycle %d" % \
                            (now-self.start_time, self.channel, _CYCLE_COUNT-self.cycle_count+1))
                        self.relay.value = _RELAY_OFF
                        self.state = _STATE_ENDING
                        self.ending = _ENDING_DURATION
                        pixel = _PIX_ENDING
                        self.sample_period = _SAMPLE_PERIOD_ENDING
                # endif self.state < _STATE_ENDING:

                if self.state == _STATE_ENDING:
                    self.ending -= 1
                    if self.ending == 0:
                        self.cycle_count -= 1
                        if self.cycle_count <= 0:
                            print("%9.2f:[%d]: ended" % (now-self.start_time, self.channel))
                            self.state = _STATE_ENDED
                            pixel = _PIX_ENDED
                            self.sensor.enable_channel(self.channel, False)
                        else:
                            print("%9.2f:[%d]: cycle %d" % \
                                   (now-self.start_time, self.channel, _CYCLE_COUNT-self.cycle_count))
                            self.relay.value = _RELAY_ON
                            self.state = _STATE_RUNNING_FAST
                            pixel = _PIX_RUNNING_FAST
                            self.sample_period = _SAMPLE_PERIOD_FAST
                # endif self.state == _STATE_ENDING:

                # write to file
                self._write_log(now - self.start_time, voltage, current, self.sum_c)
                # keep for next
                self.previous_voltage = voltage
                self.previous_current = current
                # restore pixel or update to new
                self._setpix(pixel)
            # endif now >= self.next_time:
        # endif self.state < _STATE_ENDED:
    #enddef run()


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
