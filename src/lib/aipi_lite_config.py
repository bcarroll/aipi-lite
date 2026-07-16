"""Compatibility shim for the AIPI-Lite display baseline."""

from display import BLACK
from display import BLUE
from display import GREEN
from display import RED
from display import WHITE
from display import SPI_BAUDRATE
from display import create_display_hardware

spi_baudrate = SPI_BAUDRATE


def create_display():
    """Initialize the ST7735-compatible TFT with documented display pins."""
    hardware = create_display_hardware()
    return (
        hardware.backlight,
        hardware.chip_select,
        hardware.data_command,
        hardware.reset,
        hardware.spi,
        hardware.tft,
    )


bl, cs, dc, rst, spi, tft = create_display()
