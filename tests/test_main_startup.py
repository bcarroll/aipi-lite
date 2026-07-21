"""Tests for normal MicroPython application startup wiring."""

import importlib
from pathlib import Path
import sys
import types
import unittest
from unittest import mock


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

    def __init__(self, fail_connect=False, connect_result="ready"):
        """Create a controller that can optionally fail during connect."""
        self.fail_connect = fail_connect
        self.connect_result = connect_result
        self.connect_calls = 0

    def connect(self):
        """Record service connection attempts."""
        self.connect_calls += 1
        if self.fail_connect:
            raise RuntimeError("local service unavailable")
        return self.connect_result


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

    def test_main_enters_button_poll_loop_when_connection_is_offline(self):
        """Offline startup should remain usable for a later reconnect press."""
        display = FakeStatusDisplay()
        led = FakeStatusLed()
        button = FakeButton()
        controller = FakeController(connect_result="offline")
        poll_calls = []
        messages = []

        result = self.main.main(
            print_func=messages.append,
            idle_polls=1,
            status_display_factory=lambda: display,
            status_led_factory=lambda: led,
            button_factory=lambda: button,
            controller_factory=lambda **kwargs: controller,
            poll_button_loop_func=lambda *args, **kwargs: poll_calls.append(args) or "offline",
            disable_speaker_func=lambda: None,
        )

        self.assertEqual(result, "offline")
        self.assertEqual(controller.connect_calls, 1)
        self.assertEqual(poll_calls, [(controller, button)])
        self.assertIn("main: push-to-talk offline; press button to reconnect", messages)
        self.assertIn("main: polling right function button", messages)

    def test_controller_factory_routes_wifi_trace_to_normal_boot_serial(self):
        """Normal controller wiring should use the active serial print function for Wi-Fi trace."""
        captured = {}
        messages = []
        connect_calls = []
        diagnostics = object()

        push_to_talk_module = types.ModuleType("push_to_talk")

        def create_controller(**kwargs):
            """Capture normal controller dependencies."""
            captured.update(kwargs)
            return "controller"

        push_to_talk_module.create_controller = create_controller
        reliability_module = types.ModuleType("reliability")
        reliability_module.DiagnosticsLog = lambda print_func: diagnostics
        wifi_probe_module = types.ModuleType("wifi_probe")

        def connect_wifi(config, wlan=None, print_func=print):
            """Record connector arguments and emit one representative trace line."""
            connect_calls.append((config, wlan))
            print_func("wifi_trace phase=start timeout_ms=15000")
            return "connected-wlan"

        wifi_probe_module.connect_wifi = connect_wifi

        with mock.patch.dict(
            sys.modules,
            {
                "push_to_talk": push_to_talk_module,
                "reliability": reliability_module,
                "wifi_probe": wifi_probe_module,
            },
        ):
            controller = self.main.create_push_to_talk_controller(print_func=messages.append)

        result = captured["connect_wifi_func"]("config", wlan="existing-wlan")

        self.assertEqual(controller, "controller")
        self.assertIs(captured["diagnostics"], diagnostics)
        self.assertEqual(result, "connected-wlan")
        self.assertEqual(connect_calls, [("config", "existing-wlan")])
        self.assertEqual(messages, ["wifi_trace phase=start timeout_ms=15000"])


if __name__ == "__main__":
    unittest.main()
