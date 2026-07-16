"""Tests for normal MicroPython application startup wiring."""

import importlib
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SRC_LIB_ROOT = SRC_ROOT / "lib"

MODULES_TO_CLEAR = ("main", "pins")


class FakeStatusDisplay:
    """Record status screens rendered by main startup."""

    def __init__(self):
        """Create an empty render recorder."""
        self.screens = []

    def render_status(self, status, detail=None):
        """Record a rendered status and optional detail."""
        self.screens.append((status, detail))


class FakeStatusLed:
    """Record status LED states requested by main startup."""

    def __init__(self):
        """Create an empty state recorder."""
        self.states = []

    def set_state(self, state):
        """Record the requested LED state."""
        self.states.append(state)


class FakeButton:
    """Stand in for the debounced GPIO42 button."""


class FakeController:
    """Record push-to-talk controller startup calls."""

    def __init__(self, fail_connect=False):
        """Create a controller that can optionally fail during connect."""
        self.fail_connect = fail_connect
        self.connect_calls = 0

    def connect(self):
        """Record service connection attempts."""
        self.connect_calls += 1
        if self.fail_connect:
            raise RuntimeError("local service unavailable")
        return "ready"


def clear_imported_modules():
    """Remove main startup modules imported by these tests."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    for source_root in (SRC_ROOT, SRC_LIB_ROOT):
        source_path = str(source_root)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)


class MainStartupTests(unittest.TestCase):
    """Validate that normal boot starts the push-to-talk application."""

    def setUp(self):
        """Import a fresh main module for each test."""
        clear_imported_modules()
        ensure_src_path()
        self.main = importlib.import_module("main")

    def tearDown(self):
        """Clean imported startup modules after each test."""
        clear_imported_modules()

    def test_main_connects_service_and_enters_button_poll_loop(self):
        """Normal boot should leave the boot screen and poll the side button."""
        display = FakeStatusDisplay()
        led = FakeStatusLed()
        button = FakeButton()
        controller = FakeController()
        poll_calls = []
        messages = []

        def poll_button_loop(controller_arg, button_arg, idle_polls=None):
            """Record the poll-loop wiring and return the ready state."""
            poll_calls.append((controller_arg, button_arg, idle_polls))
            return "ready"

        result = self.main.main(
            print_func=messages.append,
            idle_polls=1,
            status_display_factory=lambda: display,
            status_led_factory=lambda: led,
            button_factory=lambda: button,
            controller_factory=lambda **kwargs: controller,
            poll_button_loop_func=poll_button_loop,
            disable_speaker_func=lambda: None,
        )

        self.assertEqual(result, "ready")
        self.assertEqual(display.screens, [("boot", None)])
        self.assertEqual(controller.connect_calls, 1)
        self.assertEqual(poll_calls, [(controller, button, 1)])
        self.assertIn("main: connecting local push-to-talk service", messages)
        self.assertIn("main: push-to-talk ready", messages)
        self.assertIn("main: polling right function button", messages)

    def test_main_renders_visible_error_when_push_to_talk_startup_fails(self):
        """Startup failures should show an error instead of staying on boot."""
        display = FakeStatusDisplay()
        led = FakeStatusLed()
        controller = FakeController(fail_connect=True)
        poll_calls = []
        messages = []

        result = self.main.main(
            print_func=messages.append,
            idle_polls=1,
            status_display_factory=lambda: display,
            status_led_factory=lambda: led,
            button_factory=FakeButton,
            controller_factory=lambda **kwargs: controller,
            poll_button_loop_func=lambda *args, **kwargs: poll_calls.append(args),
            disable_speaker_func=lambda: None,
        )

        self.assertEqual(result, "error")
        self.assertEqual(controller.connect_calls, 1)
        self.assertEqual(poll_calls, [])
        self.assertEqual(display.screens[-1], ("error", "RuntimeError"))
        self.assertEqual(led.states[-1], "error")
        self.assertIn("main: push-to-talk startup failed: RuntimeError", messages)


if __name__ == "__main__":
    unittest.main()
