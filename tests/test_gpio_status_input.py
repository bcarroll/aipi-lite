"""Tests for AIPI-Lite GPIO status LED and side button probes."""

from pathlib import Path
import importlib
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

MODULES_TO_CLEAR = ("button", "io_probe", "pins", "status_led", "machine", "neopixel")


def clear_imported_modules():
    """Remove firmware modules imported by these GPIO tests."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


class FakeInputPin:
    """Test double for a MicroPython active-low input pin."""

    def __init__(self, value=1):
        """Create a fake pin with an initial high or low value."""
        self._value = value

    def value(self):
        """Return the current fake pin value."""
        return self._value

    def set_value(self, value):
        """Set the current fake pin value."""
        self._value = value


class FakePinFactory:
    """Record MicroPython Pin construction for button tests."""

    IN = "IN"
    PULL_UP = "PULL_UP"

    def __init__(self, pin):
        """Create a factory that returns the supplied fake pin."""
        self.pin = pin
        self.calls = []

    def __call__(self, pin_number, mode=None, pull=None):
        """Return the fake pin and record constructor arguments."""
        self.calls.append((pin_number, mode, pull))
        return self.pin


class FakeOutputPin:
    """Test double for a MicroPython output-capable pin."""

    def __init__(self, pin_number):
        """Record the GPIO number bound to the fake output pin."""
        self.pin_number = pin_number


class FakeNeoPixel:
    """Record NeoPixel writes without attached hardware."""

    def __init__(self, pin, count):
        """Create a fake NeoPixel strip bound to the supplied pin."""
        self.pin = pin
        self.count = count
        self.values = {}
        self.write_count = 0

    def __setitem__(self, index, value):
        """Record a pixel color assignment."""
        self.values[index] = value

    def write(self):
        """Record that pending pixel colors were flushed."""
        self.write_count += 1


class FakeStatusLed:
    """Record status LED state transitions for the IO probe test."""

    def __init__(self):
        """Create a fake status LED recorder."""
        self.states = []
        self.off_called = False

    def set_state(self, state):
        """Record a requested state transition."""
        self.states.append(state)

    def off(self):
        """Record probe shutdown."""
        self.off_called = True


class FakeButton:
    """Yield a fixed sequence of debounced button events."""

    def __init__(self, events):
        """Create a fake button with events returned one per update."""
        self.events = list(events)

    def update(self):
        """Return the next fake event or None."""
        if self.events:
            return self.events.pop(0)
        return None


class GpioStatusInputTests(unittest.TestCase):
    """Validate GPIO status/input logic without attached hardware."""

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def test_status_led_state_colors_match_probe_contract(self):
        """Status LED states should have deterministic low-brightness colors."""
        clear_imported_modules()
        ensure_src_path()
        status_led = importlib.import_module("status_led")

        self.assertEqual(
            status_led.available_states(),
            (
                "offline",
                "connecting",
                "ready",
                "recording",
                "processing",
                "speaking",
                "error",
            ),
        )
        self.assertEqual(status_led.color_for_state("offline"), (0, 0, 0))
        self.assertEqual(status_led.color_for_state("connecting"), (0, 0, 24))
        self.assertEqual(status_led.color_for_state("ready"), (0, 24, 0))
        self.assertEqual(status_led.color_for_state("recording"), (24, 0, 0))
        self.assertEqual(status_led.color_for_state("processing"), (24, 12, 0))
        self.assertEqual(status_led.color_for_state("speaking"), (0, 18, 18))
        self.assertEqual(status_led.color_for_state("error"), (24, 0, 24))
        with self.assertRaises(ValueError):
            status_led.color_for_state("unknown")

    def test_status_led_uses_documented_ws2812_gpio(self):
        """StatusLed should drive the GPIO46 NeoPixel with mapped colors."""
        clear_imported_modules()
        ensure_src_path()
        status_led = importlib.import_module("status_led")

        led = status_led.StatusLed(
            pin_factory=FakeOutputPin,
            neopixel_factory=FakeNeoPixel,
        )
        led.set_state("ready")

        self.assertEqual(led.pin_number, 46)
        self.assertEqual(led.pin.pin_number, 46)
        self.assertEqual(led.pixel.count, 1)
        self.assertEqual(led.pixel.values[0], (0, 24, 0))
        self.assertEqual(led.pixel.write_count, 1)
        self.assertEqual(led.state, "ready")

    def test_debounced_button_reports_active_low_press_and_release(self):
        """DebouncedButton should emit events only after stable transitions."""
        clear_imported_modules()
        ensure_src_path()
        button = importlib.import_module("button")
        input_pin = FakeInputPin(value=1)
        pin_factory = FakePinFactory(input_pin)
        debounced = button.DebouncedButton(
            debounce_ms=50,
            pin_factory=pin_factory,
            ticks_ms_func=lambda: 0,
        )

        self.assertEqual(pin_factory.calls, [(42, "IN", "PULL_UP")])
        self.assertFalse(debounced.is_pressed())

        input_pin.set_value(0)
        self.assertIsNone(debounced.update(now_ms=10))
        self.assertIsNone(debounced.update(now_ms=59))
        self.assertEqual(debounced.update(now_ms=60), button.BUTTON_PRESSED)
        self.assertTrue(debounced.is_pressed())

        input_pin.set_value(1)
        self.assertIsNone(debounced.update(now_ms=70))
        self.assertIsNone(debounced.update(now_ms=119))
        self.assertEqual(debounced.update(now_ms=120), button.BUTTON_RELEASED)
        self.assertFalse(debounced.is_pressed())

    def test_io_probe_cycles_led_states_and_prints_button_events(self):
        """The IO probe should cycle states, print events, and switch off."""
        clear_imported_modules()
        ensure_src_path()
        io_probe = importlib.import_module("io_probe")
        fake_led = FakeStatusLed()
        fake_button = FakeButton([None, "pressed", None, "released"])
        messages = []
        sleeps = []

        io_probe.run_probe(
            cycles=1,
            poll_iterations=4,
            poll_delay_ms=5,
            led_delay_ms=7,
            print_func=messages.append,
            status_led=fake_led,
            button=fake_button,
            sleep_ms_func=sleeps.append,
        )

        self.assertEqual(fake_led.states, list(io_probe.available_states()))
        self.assertTrue(fake_led.off_called)
        self.assertIn("io_probe: led ready", messages)
        self.assertIn("io_probe: button pressed", messages)
        self.assertIn("io_probe: button released", messages)
        self.assertEqual(messages[-1], "io_probe: complete")
        self.assertEqual(sleeps[: len(fake_led.states)], [7] * len(fake_led.states))
        self.assertEqual(sleeps[len(fake_led.states) :], [5, 5, 5, 5])

    def test_io_probe_avoids_other_hardware_subsystems(self):
        """The GPIO probe should not initialize display, Wi-Fi, audio, or GPIO10."""
        probe_text = (SRC_ROOT / "io_probe.py").read_text(encoding="utf-8")

        self.assertNotIn("aipi_lite_config", probe_text)
        self.assertNotIn("network", probe_text)
        self.assertNotIn("WLAN", probe_text)
        self.assertNotIn("AUDIO_", probe_text)
        self.assertNotIn("BOARD_POWER_CONTROL", probe_text)


if __name__ == "__main__":
    unittest.main()
