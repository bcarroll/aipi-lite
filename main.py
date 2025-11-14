"""Simple TFT display demo.

This module initializes the SPI-connected ST7735 TFT display and runs a
small text rendering demonstration.
"""

import time
from aipi_lite_config import tft
from aipi_lite_config import BLACK, RED, GREEN, BLUE, WHITE
from lib.st7735.sysfont import sysfont

#from machine import SPI, Pin, PWM

#from lib.st7735 import TFT, sysfont




def tftprinttest(font=sysfont):
    """Display sample strings with the provided font on the TFT display."""
    tft.fill(BLACK)
    v = 30
    tft.text((10, v), "AIPI-LITE", WHITE, font, 2, nowrap=True)
    tft.text((30, 60), "Micropython", WHITE, font, 1, nowrap=True)
    #v += font["Height"]
    #tft.text((0, v), "Hello World!", TFT.YELLOW, font, 2, nowrap=True)
    #v += font["Height"] * 2
    #tft.text((0, v), "Hello World!", TFT.GREEN, font, 3, nowrap=True)
    #v += font["Height"] * 3
    #tft.text((0, v), str(1234.5), TFT.BLUE, font, 4, nowrap=True)
    time.sleep_ms(1500)


def test_main():
    """Run the TFT print test sequence."""
    tftprinttest()
    time.sleep_ms(100)



test_main()

