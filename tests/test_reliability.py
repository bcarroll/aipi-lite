"""Tests for AIPI-Lite retry, diagnostics, and power observation helpers."""

import importlib
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

MODULES_TO_CLEAR = ("pins", "reliability")


class FakeInputPin:
    """Test double for an input pin."""

    def __init__(self, value=0):
        """Create a pin with a fixed value."""
        self._value = value

    def value(self):
        """Return the configured value."""
        return self._value


class FakePinFactory:
    """Record charge pulse pin construction."""

    IN = "IN"

    def __init__(self, pin):
        """Create a factory that returns the supplied pin."""
        self.pin = pin
        self.calls = []

    def __call__(self, pin_number, mode=None):
        """Return the fake pin and record constructor arguments."""
        self.calls.append((pin_number, mode))
        return self.pin


class FakeWLAN:
    """Test double for a WLAN connection."""

    def __init__(self, connected=False):
        """Create a fake WLAN with initial connection state."""
        self.connected = connected

    def isconnected(self):
        """Return the fake connection state."""
        return self.connected


def clear_imported_modules():
    """Remove imported firmware modules after each test."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


class ReliabilityTests(unittest.TestCase):
    """Validate reliability helpers without hardware."""

    def setUp(self):
        """Import a fresh reliability module."""
        clear_imported_modules()
        ensure_src_path()
        self.reliability = importlib.import_module("reliability")

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def test_retry_policy_bounds_attempts_and_backoff(self):
        """call_with_retries should bound attempts and report retry delays."""
        attempts = []
        sleeps = []
        retries = []
        policy = self.reliability.RetryPolicy(max_attempts=3, initial_delay_ms=10, max_delay_ms=15)

        def flaky():
            """Fail twice, then succeed."""
            attempts.append("attempt")
            if len(attempts) < 3:
                raise RuntimeError("temporary")
            return "ok"

        result = self.reliability.call_with_retries(
            flaky,
            policy=policy,
            sleep_ms_func=sleeps.append,
            on_retry=lambda attempt, delay, error: retries.append((attempt, delay, type(error).__name__)),
        )

        self.assertEqual(result, "ok")
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleeps, [10, 15])
        self.assertEqual(retries, [(1, 10, "RuntimeError"), (2, 15, "RuntimeError")])

    def test_retry_exhaustion_raises_retry_error(self):
        """Retry exhaustion should raise RetryError with the last error."""
        policy = self.reliability.RetryPolicy(max_attempts=2, initial_delay_ms=1)

        with self.assertRaises(self.reliability.RetryError) as raised:
            self.reliability.call_with_retries(
                lambda: (_ for _ in ()).throw(ValueError("nope")),
                policy=policy,
                sleep_ms_func=lambda milliseconds: None,
            )

        self.assertEqual(raised.exception.attempts, 2)
        self.assertIsInstance(raised.exception.last_error, ValueError)

    def test_diagnostics_format_state_metrics_and_failures(self):
        """DiagnosticsLog should keep bounded serial-friendly events."""
        messages = []
        log = self.reliability.DiagnosticsLog(print_func=messages.append, max_events=2, ticks_ms_func=lambda: 7)

        log.record_state_transition("ready", "recording", detail="button")
        log.record_metric("playback_underruns", 1)
        log.record_failure("service", RuntimeError("hidden detail"))

        self.assertEqual(len(log.events), 2)
        self.assertEqual(messages[0], "diag t=7 state transition detail=button from=ready to=recording")
        self.assertEqual(log.formatted_events()[-1], "diag t=7 service failure type=RuntimeError")

    def test_reconnect_manager_reuses_or_reconnects_wlan(self):
        """ReconnectManager should skip connected WLANs and reconnect dropped ones."""
        connected = FakeWLAN(connected=True)
        calls = []
        manager = self.reliability.ReconnectManager("config", lambda config, wlan=None: calls.append((config, wlan)), wlan=connected)

        self.assertIs(manager.ensure_connected(), connected)
        self.assertEqual(calls, [])

        dropped = FakeWLAN(connected=False)
        replacement = FakeWLAN(connected=True)
        manager = self.reliability.ReconnectManager(
            "config",
            lambda config, wlan=None: calls.append((config, wlan)) or replacement,
            wlan=dropped,
        )

        self.assertIs(manager.ensure_connected(), replacement)
        self.assertEqual(calls, [("config", dropped)])

    def test_charge_pulse_reader_reports_observation_only(self):
        """ChargePulseReader should read GPIO21 without deriving battery percentage."""
        pin = FakeInputPin(value=1)
        factory = FakePinFactory(pin)

        reader = self.reliability.ChargePulseReader(pin_factory=factory)

        self.assertEqual(factory.calls, [(21, "IN")])
        self.assertEqual(reader.read(), "charge_pulse_high")

    def test_board_power_guard_requires_explicit_control(self):
        """GPIO10 board-power control should remain blocked by default."""
        guard = self.reliability.BoardPowerGuard()

        with self.assertRaises(self.reliability.BoardPowerSafetyError):
            guard.assert_can_drive()

        self.assertTrue(self.reliability.BoardPowerGuard(allow_control=True).assert_can_drive())


if __name__ == "__main__":
    unittest.main()
