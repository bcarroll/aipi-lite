"""MicroPython display wiring for the AIPI-Lite TFT baseline."""

from machine import SPI, Pin, PWM
from lib.st7735 import TFT
from pins import DISPLAY_BACKLIGHT
from pins import DISPLAY_CS
from pins import DISPLAY_DC
from pins import DISPLAY_MOSI
from pins import DISPLAY_RESET
from pins import DISPLAY_SCLK

BLACK = 0
RED = 31
GREEN = 2016
BLUE = 63488
WHITE = 65535

spi_baudrate = 20000000


def create_display():
    """Initialize the ST7735-compatible TFT with documented display pins."""
    backlight = PWM(Pin(DISPLAY_BACKLIGHT))
    chip_select = Pin(DISPLAY_CS, Pin.OUT)
    data_command = Pin(DISPLAY_DC, Pin.OUT)
    reset = Pin(DISPLAY_RESET, Pin.OUT)
    spi_bus = SPI(
        1,
        spi_baudrate,
        polarity=0,
        phase=0,
        sck=Pin(DISPLAY_SCLK),
        mosi=Pin(DISPLAY_MOSI),
        miso=None,
    )
    display = TFT(spi_bus, data_command, reset, chip_select, (128, 128))
    display.initr()
    display.rotation(1)
    display.rgb(True)
    return backlight, chip_select, data_command, reset, spi_bus, display


bl, cs, dc, rst, spi, tft = create_display()
