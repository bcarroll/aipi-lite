"""AIPI-Lite MicroPython skeleton entrypoint.

The first firmware milestone keeps startup deliberately small: print a
serial-visible bring-up sequence, leave risky power-control pins untouched, and
exercise the existing display baseline when the ST7735 driver is available.
"""

import time

from pins import BOARD_POWER_CONTROL
from pins import DO_NOT_TOUCH_DURING_BOOT

STARTUP_LINES = (
    "main: AIPI-Lite MicroPython skeleton starting",
    "main: serial bring-up active",
    "main: GPIO{} board power left unchanged".format(BOARD_POWER_CONTROL),
)


def sleep_ms(milliseconds):
    """Sleep for the requested milliseconds on MicroPython or CPython."""
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(milliseconds)
        return
    time.sleep(milliseconds / 1000)


def load_sysfont():
    """Load the bundled MicroPython ST7735 font only when the display is used."""
    from lib.st7735.sysfont import sysfont

    return sysfont


def tftprinttest(display, font=None):
    """Display sample strings with the provided font on the TFT display."""
    if font is None:
        font = load_sysfont()

    from aipi_lite_config import BLACK, WHITE

    display.fill(BLACK)
    display.text((10, 30), "AIPI-LITE", WHITE, font, 2, nowrap=True)
    display.text((30, 60), "Micropython", WHITE, font, 1, nowrap=True)
    sleep_ms(1500)


def run_display_demo():
    """Initialize the existing display baseline and draw the startup message."""
    from aipi_lite_config import tft

    tftprinttest(tft)


def disable_speaker_amplifier():
    """Drive the speaker amplifier gate off during normal application startup."""
    from es8311 import SpeakerAmplifierGate

    SpeakerAmplifierGate().disable()


def main(print_func=print):
    """Run the safe serial-visible MicroPython skeleton startup sequence."""
    for line in STARTUP_LINES:
        print_func(line)

    for signal_name, pin_number in DO_NOT_TOUCH_DURING_BOOT.items():
        print_func("main: safe boot leaves {} on GPIO{} untouched".format(signal_name, pin_number))

    try:
        disable_speaker_amplifier()
        print_func("main: speaker amplifier disabled")
    except Exception as exc:
        print_func("main: speaker amplifier default skipped: {}".format(type(exc).__name__))

    try:
        run_display_demo()
        print_func("main: display baseline rendered")
    except Exception as exc:
        print_func("main: display baseline skipped: {}".format(type(exc).__name__))

    sleep_ms(100)
    print_func("main: skeleton ready")


if __name__ == "__main__":
    main()
