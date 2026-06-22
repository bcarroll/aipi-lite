"""GPIO status LED and side button probe for the AIPI-Lite."""

import time

from button import DebouncedButton
from status_led import StatusLed
from status_led import available_states


def sleep_ms(milliseconds):
    """Sleep for the requested number of milliseconds."""
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(milliseconds)
        return
    time.sleep(milliseconds / 1000)


def run_probe(
    cycles=1,
    poll_iterations=120,
    poll_delay_ms=50,
    led_delay_ms=200,
    print_func=print,
    status_led=None,
    button=None,
    sleep_ms_func=sleep_ms,
):
    """Cycle LED states and print debounced button transitions to serial."""
    if status_led is None:
        status_led = StatusLed()
    if button is None:
        button = DebouncedButton()

    print_func("io_probe: starting GPIO status/input probe")

    for _ in range(cycles):
        for state in available_states():
            status_led.set_state(state)
            print_func("io_probe: led {}".format(state))
            sleep_ms_func(led_delay_ms)

    print_func("io_probe: watching right function button")
    for _ in range(poll_iterations):
        event = button.update()
        if event is not None:
            print_func("io_probe: button {}".format(event))
        sleep_ms_func(poll_delay_ms)

    status_led.off()
    print_func("io_probe: complete")


if __name__ == "__main__":
    run_probe()
