"""AIPI-Lite MicroPython application entrypoint."""

import time

from pins import BOARD_POWER_CONTROL
from pins import DO_NOT_TOUCH_DURING_BOOT

STARTUP_LINES = (
    "main: AIPI-Lite MicroPython application starting",
    "main: serial bring-up active",
    "main: GPIO{} board power left unchanged".format(BOARD_POWER_CONTROL),
)


def sleep_ms(milliseconds):
    """Sleep for the requested milliseconds on MicroPython or CPython."""
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(milliseconds)
        return
    time.sleep(milliseconds / 1000)


def create_status_display():
    """Create the shared status display for normal application output."""
    from display import create_status_display

    return create_status_display()


def render_boot_screen(status_display=None, status_display_factory=create_status_display):
    """Initialize the display and render the local firmware boot status."""
    if status_display is None:
        status_display = status_display_factory()
    status_display.render_status("boot")
    return status_display


def create_status_led():
    """Create the shared status LED for normal application output."""
    from status_led import StatusLed

    return StatusLed()


def create_debounced_button():
    """Create the GPIO42 side button used by the push-to-talk loop."""
    from button import DebouncedButton

    return DebouncedButton()


def disable_speaker_amplifier():
    """Drive the speaker amplifier gate off during normal application startup."""
    from es8311 import SpeakerAmplifierGate

    SpeakerAmplifierGate().disable()


def create_push_to_talk_controller(status_led=None, status_display=None, print_func=print):
    """Create the local-only push-to-talk controller for normal boot."""
    from push_to_talk import create_controller
    from reliability import DiagnosticsLog
    from wifi_probe import connect_wifi

    def connect_wifi_with_trace(config, wlan=None):
        """Connect Wi-Fi while routing always-on trace output to serial."""
        return connect_wifi(config, wlan=wlan, print_func=print_func)

    diagnostics = DiagnosticsLog(print_func=print_func)
    return create_controller(
        status_led=status_led,
        status_display=status_display,
        print_func=print_func,
        diagnostics=diagnostics,
        connect_wifi_func=connect_wifi_with_trace,
    )


def render_error_state(status_led=None, status_display=None, detail="startup"):
    """Render a visible startup error without assuming all outputs exist."""
    if status_led is not None:
        try:
            status_led.set_state("error")
        except Exception:
            pass
    if status_display is not None:
        try:
            status_display.render_status("error", detail=detail)
        except Exception:
            pass


def run_push_to_talk_app(
    status_led=None,
    status_display=None,
    print_func=print,
    button_factory=create_debounced_button,
    controller_factory=create_push_to_talk_controller,
    poll_button_loop_func=None,
    idle_polls=None,
):
    """Connect local services and poll the GPIO42 push-to-talk button."""
    if poll_button_loop_func is None:
        from push_to_talk import poll_button_loop

        poll_button_loop_func = poll_button_loop

    print_func("main: connecting local push-to-talk service")
    controller = controller_factory(
        status_led=status_led,
        status_display=status_display,
        print_func=print_func,
    )
    connection_state = controller.connect()
    button = button_factory()
    if connection_state == "ready":
        print_func("main: push-to-talk ready")
    else:
        print_func("main: push-to-talk offline; tap to retry or hold 2s to bypass")
    print_func("main: polling right function button")
    return poll_button_loop_func(controller, button, idle_polls=idle_polls)


def main(
    print_func=print,
    run_push_to_talk=True,
    idle_polls=None,
    status_display_factory=create_status_display,
    status_led_factory=create_status_led,
    button_factory=create_debounced_button,
    controller_factory=create_push_to_talk_controller,
    poll_button_loop_func=None,
    disable_speaker_func=disable_speaker_amplifier,
    sleep_ms_func=sleep_ms,
):
    """Run safe startup, then enter the local push-to-talk application."""
    status_display = None
    status_led = None

    for line in STARTUP_LINES:
        print_func(line)

    for signal_name, pin_number in DO_NOT_TOUCH_DURING_BOOT.items():
        print_func("main: safe boot leaves {} on GPIO{} untouched".format(signal_name, pin_number))

    try:
        disable_speaker_func()
        print_func("main: speaker amplifier disabled")
    except Exception as exc:
        print_func("main: speaker amplifier default skipped: {}".format(type(exc).__name__))

    try:
        status_display = render_boot_screen(status_display_factory=status_display_factory)
        print_func("main: display boot status rendered")
    except Exception as exc:
        print_func("main: display boot status skipped: {}".format(type(exc).__name__))

    try:
        status_led = status_led_factory()
        print_func("main: status LED initialized")
    except Exception as exc:
        print_func("main: status LED skipped: {}".format(type(exc).__name__))

    if not run_push_to_talk:
        sleep_ms_func(100)
        print_func("main: boot-only startup complete")
        return "boot"

    try:
        state = run_push_to_talk_app(
            status_led=status_led,
            status_display=status_display,
            print_func=print_func,
            button_factory=button_factory,
            controller_factory=controller_factory,
            poll_button_loop_func=poll_button_loop_func,
            idle_polls=idle_polls,
        )
        print_func("main: push-to-talk loop stopped: {}".format(state))
        return state
    except Exception as exc:
        detail = type(exc).__name__
        print_func("main: push-to-talk startup failed: {}".format(detail))
        render_error_state(status_led=status_led, status_display=status_display, detail=detail)
        return "error"


if __name__ == "__main__":
    main()
