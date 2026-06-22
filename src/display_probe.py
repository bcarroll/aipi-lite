"""Display status-screen probe for AIPI-Lite hardware bring-up."""

import time

from display import available_statuses
from display import create_status_display


def sleep_ms(milliseconds):
    """Sleep for the requested milliseconds on MicroPython or CPython."""
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(milliseconds)
        return
    time.sleep(milliseconds / 1000)


def run_probe(
    cycles=1,
    delay_ms=700,
    print_func=print,
    status_display=None,
    sleep_ms_func=sleep_ms,
):
    """Cycle display status screens and print transitions to serial."""
    if status_display is None:
        status_display = create_status_display()

    print_func("display_probe: starting display probe")
    for _ in range(cycles):
        for status in available_statuses():
            status_display.render_status(status)
            print_func("display_probe: screen {}".format(status))
            sleep_ms_func(delay_ms)

    print_func("display_probe: complete")


if __name__ == "__main__":
    run_probe()
