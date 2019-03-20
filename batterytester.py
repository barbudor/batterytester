#--------------------------------------------------------
#    Li-Ion Battery Tester by barbudor
#-----------------------------------------------------------
# Allows to test capacity of Li-Ion batteries in gang
# Based on
#   - AdafruitCircuit Playground Express running CPy 4.0.0b3
#   - INA3221 for voltage/current measurement
#   - 4 relays board (Chinese, such as SainSmart)
#--------------------------------------------------------

import digitalio
from board import *
from adafruit_circuitplayground.express import cpx
import storage
import time
import os

class Tester:

  # states
  STATE_WAITING = 0
  STATE_RUNNING = 2
  STATE_RUNNING_FAST = 4
  STATE_ENDING = 8
  STATE_ENDED = 9

  # CPX pin labels for relays
  RELAY_ON = False
  RELAY_OFF = True
  
  # CPX neopixel index
  PIX_WAITING = (0,0,85)
  PIX_RUNNING = (0,85,0)
  PIX_RUNNING_FAST = (10,85,0)
  PIX_ENDING = (85,85,0)
  PIX_ENDED = (255,0,0)
  PIX_OFF = (0,0,0)
  
  # INA3221 resistor value
  SHUNT_VALUE = 0.1
  
  FILE_COUNTER = "/tester.count"
  FILE_LOG = "/battery%03d.csv"
  LOG_HEADER = "File: %s\nTime; Voltage (V); Current (A)\n"
  LOG_FORMAT = "%9.2f; %6.3f; %6.3f\n"

  SAMPLE_PERIOD_DEFAULT = 10.0
  SAMPLE_PERIOD_FAST = 1.0
  SAMPLE_PERIOD_ENDING = 0.5
  ENDING_DURATION = 60
  
  END_VOLTAGE = 3.0
  
  
  def setpix(self,color):
    cpx.pixels[self.pixel] = color
    
  def getpix(self):
    return cpx.pixels[self.pixel]
    
  def readFileCounter(self):
    counter = 0
    try:
      with open( Tester.FILE_COUNTER, "r" ) as file:
        line = file.readline()
        line = line.strip()
        counter = int(line)
      print("%9.2f:[%d]: read counter %d" % (time.monotonic(), self.channel, counter) )
    except:
      print("%9.2f:[%d]: read counter default %d" % (time.monotonic(), self.channel, counter) )
      pass
    return counter
    
    
  def writeFileCounter(self,counter):
    print("%9.2f:[%d]: write counter %d" % (time.monotonic(), self.channel, counter) )
    try:
      with open( Tester.FILE_COUNTER, "w" ) as file:
        file.write( "%d\n" % counter )
    except:
      pass
      
      
  def readVA_sim(self):
    voltage = 4.200
    current = 0.000
    if self.relay.value == Tester.RELAY_ON:
      if self.previousVoltage < 3.4:
        voltage = 4.000-(self.sampleCount/(10.0+self.channel))
        current = 1.123-(self.sampleCount/(40.0+self.channel))
      else:
        voltage = 4.000-(self.sampleCount/(20.0+self.channel))
        current = 1.123-(self.sampleCount/(40.0+self.channel))
    self.sampleCount += 1
    print("%9.2f:[%d]: %5.3fV %5.3fA" % (time.monotonic(), self.channel, voltage, current) )
    return ( voltage, current )

  def readVA(self):
    return self.readVA_sim()
    
    
  def writeLog(self,timestamp,voltage,current):
    with open( self.logfilename, "a" ) as file:
      file.write( Tester.LOG_FORMAT % ( timestamp, voltage, current ) )

    
  def __init__(self, channel, pin, neopixel):
    self.relay = digitalio.DigitalInOut(pin)
    self.relay.switch_to_output(value=Tester.RELAY_OFF)
    self.channel = channel
    self.pixel = neopixel
    self.state = Tester.STATE_WAITING
    self.setpix(Tester.PIX_WAITING)

    
  def __del__(self):
    self.deinit()

    
  def deinit(self):
    self.state = Tester.STATE_WAITING
    self.setpix(Tester.PIX_WAITING)
    self.relay.value = Tester.RELAY_OFF
    
  def start(self):
    self.state = Tester.STATE_RUNNING
    pixel = Tester.PIX_RUNNING
    self.setpix(tuple(3*x for x in pixel))

    filecount = self.readFileCounter()
    self.logfilename = Tester.FILE_LOG % filecount
    with open( self.logfilename, "w" ) as file:
      file.write( Tester.LOG_HEADER % self.logfilename )
    self.writeFileCounter(filecount+1)
    self.sampleCount = 0
    self.samplePeriod = Tester.SAMPLE_PERIOD_DEFAULT
    self.ending = Tester.ENDING_DURATION
    
    print("%9.2f:[%d]: starting '%s'" % (time.monotonic(), self.channel, self.logfilename) )
    
    # initial sample performed with relay off (battery not loaded)
    self.startTime = time.monotonic()
    (voltage,current) = self.readVA()
    self.writeLog( 0, voltage, current )

    # switch on the load relay
    self.relay.value = Tester.RELAY_ON
    
    self.previousVoltage = voltage
    self.previousDeltaV = 5.0
    # 1st sample after switching on the load is done just 1 sec after
    self.nextTime = self.startTime + 1.0

    self.setpix(pixel)


  def run(self):
    if self.state < Tester.STATE_ENDED:
      now = time.monotonic()
      if now >= self.nextTime:
        print("%9.2f:[%d]: sample" % (time.monotonic(), self.channel) )
        pixel = self.getpix()
        self.setpix(tuple(3*x for x in pixel))
        (voltage,current) = self.readVA()
        self.writeLog( now - self.startTime, voltage, current )

        deltaV = self.previousVoltage - voltage
        print("%9.2f:[%d]: dV=%f pdV=%f" % (time.monotonic(), self.channel, deltaV, self.previousDeltaV) )
        if self.state < Tester.STATE_RUNNING_FAST:
          if deltaV >= (1.5 * self.previousDeltaV):
            print("%9.2f:[%d]: ->run_fast" % (time.monotonic(), self.channel) )
            self.state = Tester.STATE_RUNNING_FAST
            pixel = Tester.PIX_RUNNING_FAST
            self.samplePeriod = Tester.SAMPLE_PERIOD_FAST
          self.previousDeltaV = deltaV
          self.previousVoltage = voltage
        
        if self.state < Tester.STATE_ENDING:
          if voltage <= Tester.END_VOLTAGE:
            print("%9.2f:[%d]: ->ending" % (time.monotonic(), self.channel) )
            self.relay.value = Tester.RELAY_OFF
            self.state = Tester.STATE_ENDING
            pixel = Tester.PIX_ENDING
            self.samplePeriod = Tester.SAMPLE_PERIOD_ENDING
        
        if self.state == Tester.STATE_ENDING:
          self.ending -= 1
          if self.ending == 0:
            print("%9.2f:[%d]: ended" % (time.monotonic(), self.channel) )
            self.state = Tester.STATE_ENDED
            pixel = Tester.PIX_ENDED
            
        self.setpix(pixel)
        self.nextTime += self.samplePeriod


################################################################################

cpx.pixels.brightness = 0.1

# create testers
testers = (Tester(0, A1, 6), Tester(1, A2, 7), Tester(2, A3, 8))
#testers = [Tester(0, A1, 6)]


def RunTest():
  
  # check if FS is writable
  try:
    with open( "/test.test", "w") as f:
      f.write("tested\n")
    os.remove( "/test.test" )
  except:
    try:
      storage.remount("/", False)
    except:
      cpx.pixels[0] = (255,0,0,)
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


