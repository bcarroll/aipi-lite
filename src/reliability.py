"""Reliability helpers for local-only AIPI-Lite assistant sessions."""

import gc
import time

from pins import BOARD_POWER_CONTROL
from pins import CHARGE_PULSE


class RetryError(Exception):
    """Raised when a bounded retry operation exhausts all attempts."""

    def __init__(self, attempts, last_error):
        """Create a retry failure with the last underlying exception."""
        super().__init__("operation failed after {} attempts: {}".format(attempts, last_error))
        self.attempts = attempts
        self.last_error = last_error


class BoardPowerSafetyError(RuntimeError):
    """Raised when code attempts unapproved GPIO10 board-power control."""


def sleep_ms(milliseconds):
    """Sleep for a bounded retry delay on MicroPython or CPython."""
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(milliseconds)
        return
    time.sleep(milliseconds / 1000)


def ticks_ms():
    """Return monotonic milliseconds on MicroPython or CPython."""
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


class RetryPolicy:
    """Describe bounded retry attempts and backoff delays."""

    def __init__(self, max_attempts=3, initial_delay_ms=200, max_delay_ms=1000, multiplier=2):
        """Create a retry policy with positive bounded values."""
        self.max_attempts = _positive_int(max_attempts, "max_attempts")
        self.initial_delay_ms = _positive_int(initial_delay_ms, "initial_delay_ms")
        self.max_delay_ms = _positive_int(max_delay_ms, "max_delay_ms")
        self.multiplier = _positive_int(multiplier, "multiplier")

    def delay_for_retry(self, retry_index):
        """Return the delay before a retry after a failed attempt."""
        retry_index = _positive_int(retry_index, "retry_index")
        delay = self.initial_delay_ms * (self.multiplier ** (retry_index - 1))
        return min(delay, self.max_delay_ms)


def _positive_int(value, field_name):
    """Return value as a positive integer or raise ValueError."""
    try:
        integer = int(value)
    except (TypeError, ValueError):
        raise ValueError("{} must be an integer".format(field_name))
    if integer <= 0:
        raise ValueError("{} must be greater than zero".format(field_name))
    return integer


def call_with_retries(
    operation,
    policy=None,
    retry_exceptions=(Exception,),
    sleep_ms_func=sleep_ms,
    on_retry=None,
):
    """Run an operation with bounded retries and return its result."""
    if policy is None:
        policy = RetryPolicy()

    attempt = 1
    while True:
        try:
            return operation()
        except retry_exceptions as exc:
            if attempt >= policy.max_attempts:
                raise RetryError(attempt, exc)
            delay = policy.delay_for_retry(attempt)
            if on_retry is not None:
                on_retry(attempt, delay, exc)
            sleep_ms_func(delay)
            attempt += 1


class RuntimeEvent:
    """Hold one serial-visible diagnostic event."""

    def __init__(self, timestamp_ms, category, message, fields=None):
        """Create a diagnostic event with optional formatted fields."""
        self.timestamp_ms = timestamp_ms
        self.category = str(category)
        self.message = str(message)
        self.fields = dict(fields or {})

    def format(self):
        """Return a stable serial-friendly event line."""
        line = "diag t={} {} {}".format(self.timestamp_ms, self.category, self.message)
        if not self.fields:
            return line
        field_parts = []
        for key in sorted(self.fields):
            field_parts.append("{}={}".format(key, self.fields[key]))
        return "{} {}".format(line, " ".join(field_parts))


class DiagnosticsLog:
    """Keep bounded runtime diagnostics and mirror them to serial."""

    def __init__(self, print_func=print, max_events=50, ticks_ms_func=ticks_ms):
        """Create a bounded diagnostics log."""
        self.print_func = print_func
        self.max_events = _positive_int(max_events, "max_events")
        self.ticks_ms_func = ticks_ms_func
        self.events = []

    def record(self, category, message, fields=None):
        """Record and print one diagnostic event."""
        event = RuntimeEvent(self.ticks_ms_func(), category, message, fields=fields)
        self.events.append(event)
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events :]
        self.print_func(event.format())
        return event

    def record_state_transition(self, previous, current, detail=None):
        """Record an assistant state transition."""
        fields = {"from": previous, "to": current}
        if detail:
            fields["detail"] = detail
        return self.record("state", "transition", fields)

    def record_failure(self, category, error):
        """Record a named failure without exposing secrets."""
        return self.record(category, "failure", {"type": type(error).__name__})

    def record_metric(self, name, value):
        """Record a single numeric or text runtime metric."""
        return self.record("metric", name, {"value": value})

    def record_heap(self):
        """Record free heap bytes when the runtime exposes that metric."""
        if hasattr(gc, "mem_free"):
            return self.record_metric("heap_free", gc.mem_free())
        return self.record_metric("heap_free", "unavailable")

    def formatted_events(self):
        """Return all retained events as formatted serial lines."""
        return tuple(event.format() for event in self.events)


class ReconnectManager:
    """Ensure a WLAN connection is available before local service calls."""

    def __init__(self, config, connect_func, wlan=None, diagnostics=None):
        """Create a reconnect manager around the configured Wi-Fi connector."""
        self.config = config
        self.connect_func = connect_func
        self.wlan = wlan
        self.diagnostics = diagnostics

    def is_connected(self):
        """Return True when the current WLAN reports a connection."""
        return self.wlan is not None and hasattr(self.wlan, "isconnected") and self.wlan.isconnected()

    def ensure_connected(self):
        """Reconnect Wi-Fi when needed and return the active WLAN."""
        if self.is_connected():
            return self.wlan
        if self.diagnostics is not None:
            self.diagnostics.record("network", "reconnect")
        self.wlan = self.connect_func(self.config, wlan=self.wlan)
        return self.wlan


class ChargePulseReader:
    """Read GPIO21 as a conservative charge pulse observation."""

    def __init__(self, pin_number=CHARGE_PULSE, pin_factory=None):
        """Create a charge pulse reader without deriving battery percentage."""
        if pin_factory is None:
            from machine import Pin

            pin_factory = Pin
        self.pin_number = pin_number
        try:
            self.pin = pin_factory(pin_number, pin_factory.IN)
        except AttributeError:
            self.pin = pin_factory(pin_number)

    def read(self):
        """Return ``charge_pulse_high`` or ``charge_pulse_low``."""
        value = self.pin.value() if hasattr(self.pin, "value") else self.pin()
        if value:
            return "charge_pulse_high"
        return "charge_pulse_low"


class BoardPowerGuard:
    """Keep GPIO10 board-power control behind an explicit safety flag."""

    def __init__(self, allow_control=False, pin_number=BOARD_POWER_CONTROL):
        """Create a guard for the unverified board-power pin."""
        self.allow_control = bool(allow_control)
        self.pin_number = pin_number

    def assert_can_drive(self):
        """Raise unless board-power control has been explicitly enabled."""
        if not self.allow_control:
            raise BoardPowerSafetyError(
                "GPIO{} board-power control is not approved".format(self.pin_number)
            )
        return True
