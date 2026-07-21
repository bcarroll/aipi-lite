"""Debounced active-low side button input for the AIPI-Lite."""

import time

from pins import RIGHT_FUNCTION_BUTTON

BUTTON_PRESSED = "pressed"
BUTTON_RELEASED = "released"
BUTTON_LONG_PRESSED = "long_pressed"
DEFAULT_LONG_PRESS_MS = 2000


def ticks_ms():
    """Return a monotonic millisecond count on MicroPython or CPython."""
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


def ticks_diff(newer, older):
    """Return the signed millisecond difference between two tick values."""
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(newer, older)
    return newer - older


class DebouncedButton:
    """Read and debounce the active-low right function button."""

    def __init__(
        self,
        pin_number=RIGHT_FUNCTION_BUTTON,
        debounce_ms=50,
        long_press_ms=DEFAULT_LONG_PRESS_MS,
        pin_factory=None,
        ticks_ms_func=None,
    ):
        """Create a debounced button reader for the supplied GPIO pin."""
        if pin_factory is None:
            from machine import Pin

            pin_factory = Pin

        self.pin_number = pin_number
        self.debounce_ms = debounce_ms
        self.long_press_ms = int(long_press_ms)
        if self.long_press_ms <= 0:
            raise ValueError("long_press_ms must be greater than zero")
        self.ticks_ms_func = ticks_ms_func or ticks_ms

        try:
            self.pin = pin_factory(pin_number, pin_factory.IN, pin_factory.PULL_UP)
        except AttributeError:
            self.pin = pin_factory(pin_number)

        now = self._now()
        raw_pressed = self._read_raw_pressed()
        self._last_raw_pressed = raw_pressed
        self._last_raw_change_ms = now
        self._stable_pressed = raw_pressed
        self._press_started_ms = now if raw_pressed else None
        self._long_press_emitted = False

    def _now(self):
        """Return the current debounce clock value in milliseconds."""
        return self.ticks_ms_func()

    def _pin_value(self):
        """Read the underlying MicroPython pin value."""
        if hasattr(self.pin, "value"):
            return self.pin.value()
        return self.pin()

    def _read_raw_pressed(self):
        """Return True when the active-low input is currently pressed."""
        return self._pin_value() == 0

    def is_pressed(self):
        """Return the current debounced pressed state."""
        return self._stable_pressed

    def update(self, now_ms=None):
        """Poll the button and return a press/release event when debounced."""
        now = self._now() if now_ms is None else now_ms
        raw_pressed = self._read_raw_pressed()

        if raw_pressed != self._last_raw_pressed:
            self._last_raw_pressed = raw_pressed
            self._last_raw_change_ms = now
            return None

        if (
            raw_pressed != self._stable_pressed
            and ticks_diff(now, self._last_raw_change_ms) >= self.debounce_ms
        ):
            self._stable_pressed = raw_pressed
            if raw_pressed:
                self._press_started_ms = now
                self._long_press_emitted = False
                return BUTTON_PRESSED
            self._press_started_ms = None
            self._long_press_emitted = False
            return BUTTON_RELEASED

        if (
            self._stable_pressed
            and not self._long_press_emitted
            and self._press_started_ms is not None
            and ticks_diff(now, self._press_started_ms) >= self.long_press_ms
        ):
            self._long_press_emitted = True
            return BUTTON_LONG_PRESSED

        return None
