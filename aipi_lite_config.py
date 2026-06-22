from machine import SPI, Pin, PWM

from lib.st7735 import TFT

BLACK = 0
RED = 31
GREEN = 2016
BLUE = 63488
WHITE = 65535

bl = PWM(Pin(3))
cs = Pin(15,Pin.OUT)
dc = Pin(7,Pin.OUT)
rst = Pin(18,Pin.OUT)
spi_baudrate = 20000000

spi=SPI(1, spi_baudrate, polarity=0, phase=0, sck=Pin(16), mosi=Pin(17), miso=None)
tft = TFT(spi, dc, rst, cs, (128, 128))
tft.initr()
tft.rotation(1)
tft.rgb(True)