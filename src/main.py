"""AIPI-Lite MicroPython application entrypoint."""

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


def render_boot_screen():
    """Initialize the display and render the local firmware boot status."""
    from display import create_status_display

    status_display = create_status_display()
    status_display.render_status("boot")


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
        render_boot_screen()
        print_func("main: display boot status rendered")
    except Exception as exc:
        print_func("main: display boot status skipped: {}".format(type(exc).__name__))

    sleep_ms(100)
    print_func("main: skeleton ready")


if __name__ == "__main__":
    main()
