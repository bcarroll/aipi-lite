"""Tests for the local-only push-to-talk assistant flow."""

import importlib
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SRC_LIB_ROOT = SRC_ROOT / "lib"

MODULES_TO_CLEAR = (
    "assistant_state",
    "audio_capture",
    "audio_playback",
    "button",
    "local_endpoint",
    "pins",
    "push_to_talk",
    "reliability",
    "service_client",
    "service_contract",
    "wifi_config",
)


class FakeStatusLed:
    """Record status LED state transitions."""

    def __init__(self):
        """Create an empty transition recorder."""
        self.states = []

    def set_state(self, state):
        """Record the requested LED state."""
        self.states.append(state)


class FakeStatusDisplay:
    """Record display status renders."""

    def __init__(self):
        """Create an empty render recorder."""
        self.screens = []

    def render_status(self, status, detail=None):
        """Record the requested display status and detail."""
        self.screens.append((status, detail))


class FakePlaybackMetrics:
    """Minimal playback metrics returned by test playback."""

    underrun_count = 2


class FakeServiceClient:
    """Test double for the local service client."""

    def __init__(self, fail_health=False):
        """Create a fake service client."""
        self.fail_health = fail_health
        self.calls = []

    def health(self):
        """Record a health check and optionally fail it."""
        self.calls.append(("health",))
        if self.fail_health:
            raise RuntimeError("health failed")
        return {"status": "ok"}

    def start_session(self):
        """Return a deterministic session identifier."""
        self.calls.append(("start_session",))
        return "session-0001"

    def upload_audio(self, session_id, audio_bytes):
        """Record uploaded audio."""
        self.calls.append(("upload_audio", session_id, audio_bytes))
        return {"status": "processing"}

    def get_response(self, session_id):
        """Return a complete deterministic response."""
        self.calls.append(("get_response", session_id))
        return {
            "status": "complete",
            "display_text": "Mock response",
            "audio_url": "/audio/mock-response.wav",
        }

    def download_audio(self, audio_url):
        """Return deterministic response audio bytes."""
        self.calls.append(("download_audio", audio_url))
        return b"RIFF-wav"

    def response_ready(self, response_payload):
        """Return True when the fake payload is complete."""
        return response_payload.get("status") == "complete"


class FakeReconnectManager:
    """Record reconnect attempts from the controller."""

    def __init__(self):
        """Create an empty reconnect recorder."""
        self.calls = 0

    def ensure_connected(self):
        """Record one reconnect attempt."""
        self.calls += 1
        return "wlan"


def clear_imported_modules():
    """Remove imported firmware modules after each test."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    for source_root in (SRC_ROOT, SRC_LIB_ROOT):
        source_path = str(source_root)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)


class PushToTalkFlowTests(unittest.TestCase):
    """Validate assistant state and push-to-talk flow without hardware."""

    def setUp(self):
        """Import fresh modules for each test."""
        clear_imported_modules()
        ensure_src_path()
        self.assistant_state = importlib.import_module("assistant_state")
        self.push_to_talk = importlib.import_module("push_to_talk")
        self.reliability = importlib.import_module("reliability")
        self.button = importlib.import_module("button")

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def make_controller(
        self,
        service_client=None,
        capture_func=None,
        playback_func=None,
        sleeps=None,
        reconnect_manager=None,
    ):
        """Create a controller with fake UI and diagnostics."""
        led = FakeStatusLed()
        display = FakeStatusDisplay()
        messages = []
        diagnostics = self.reliability.DiagnosticsLog(print_func=messages.append, ticks_ms_func=lambda: 123)
        outputs = self.assistant_state.StatusOutputs(led, display, print_func=messages.append)
        state_machine = self.assistant_state.AssistantStateMachine(outputs=outputs, diagnostics=diagnostics)
        controller = self.push_to_talk.PushToTalkController(
            service_client or FakeServiceClient(),
            state_machine=state_machine,
            capture_func=capture_func or (lambda: b"captured-wav"),
            playback_func=playback_func or (lambda audio: FakePlaybackMetrics()),
            retry_policy=self.reliability.RetryPolicy(max_attempts=2, initial_delay_ms=5),
            reconnect_manager=reconnect_manager,
            sleep_ms_func=(sleeps.append if sleeps is not None else (lambda milliseconds: None)),
            diagnostics=diagnostics,
        )
        return controller, led, display, messages

    def test_state_outputs_drive_led_display_and_serial(self):
        """Assistant states should update LED, display, and serial from one source."""
        led = FakeStatusLed()
        display = FakeStatusDisplay()
        messages = []
        outputs = self.assistant_state.StatusOutputs(led, display, print_func=messages.append)

        outputs.update("recording", detail="release to stop")

        self.assertEqual(led.states, ["recording"])
        self.assertEqual(display.screens, [("recording", "release to stop")])
        self.assertEqual(messages, ["assistant: state recording: release to stop"])
        with self.assertRaises(self.assistant_state.AssistantStateError):
            outputs.update("unknown")

    def test_normal_push_to_talk_exchange_reaches_ready(self):
        """A press/release should capture, upload, download, play, and recover to ready."""
        service = FakeServiceClient()
        playback_calls = []
        controller, led, display, messages = self.make_controller(
            service_client=service,
            playback_func=lambda audio: playback_calls.append(audio) or FakePlaybackMetrics(),
        )

        controller.connect()
        controller.handle_button_event(self.button.BUTTON_PRESSED)
        final_state = controller.handle_button_event(self.button.BUTTON_RELEASED)

        self.assertEqual(final_state, "ready")
        self.assertEqual(controller.last_result.session_id, "session-0001")
        self.assertEqual(controller.last_result.display_text, "Mock response")
        self.assertTrue(controller.last_result.audio_played)
        self.assertEqual(playback_calls, [b"RIFF-wav"])
        self.assertEqual(
            service.calls,
            [
                ("health",),
                ("start_session",),
                ("upload_audio", "session-0001", b"captured-wav"),
                ("get_response", "session-0001"),
                ("download_audio", "/audio/mock-response.wav"),
            ],
        )
        self.assertIn("recording", led.states)
        self.assertIn("speaking", led.states)
        self.assertEqual(display.screens[-1], ("ready", None))
        self.assertIn("assistant: state speaking: Mock response", messages)

    def test_service_failure_enters_visible_error_and_can_recover(self):
        """Service failures should be retried, reported, and recoverable."""
        sleeps = []
        controller, _, display, _ = self.make_controller(
            service_client=FakeServiceClient(fail_health=True),
            sleeps=sleeps,
        )

        with self.assertRaises(self.reliability.RetryError):
            controller.connect()

        self.assertEqual(controller.state_machine.state, "error")
        self.assertEqual(sleeps, [5])
        self.assertEqual(display.screens[-1], ("error", "RetryError"))
        controller.recover()
        self.assertEqual(controller.state_machine.state, "ready")

    def test_retry_invokes_reconnect_before_rechecking_service(self):
        """Service retry should give Wi-Fi reconnect handling a chance to recover."""
        class TransientHealthService(FakeServiceClient):
            """Fail the first health check and then recover."""

            def health(self):
                """Fail once, then return OK."""
                self.calls.append(("health",))
                if len(self.calls) == 1:
                    raise RuntimeError("temporary")
                return {"status": "ok"}

        reconnect = FakeReconnectManager()
        sleeps = []
        controller, _, _, _ = self.make_controller(
            service_client=TransientHealthService(),
            sleeps=sleeps,
            reconnect_manager=reconnect,
        )

        controller.connect()

        self.assertEqual(controller.state_machine.state, "ready")
        self.assertEqual(reconnect.calls, 2)
        self.assertEqual(sleeps, [5])

    def test_create_controller_reconnects_wifi_before_service_health(self):
        """The default controller factory should connect Wi-Fi before health checks."""
        wifi_config = importlib.import_module("wifi_config")
        config = wifi_config.WiFiConfig(
            "LabNet",
            "secret-password",
            "http://192.168.1.10:8080",
        )
        service = FakeServiceClient()
        led = FakeStatusLed()
        display = FakeStatusDisplay()
        messages = []
        connect_calls = []

        class ConnectedWLAN:
            """Fake WLAN that reports an active connection."""

            def isconnected(self):
                """Return connected after the first connect call."""
                return True

        def connect_wifi(config_arg, wlan=None):
            """Record the Wi-Fi reconnect request."""
            connect_calls.append((config_arg, wlan))
            return ConnectedWLAN()

        controller = self.push_to_talk.create_controller(
            config=config,
            service_client=service,
            status_led=led,
            status_display=display,
            print_func=messages.append,
            connect_wifi_func=connect_wifi,
        )

        state = controller.connect()

        self.assertEqual(state, "ready")
        self.assertEqual(connect_calls, [(config, None)])
        self.assertEqual(service.calls, [("health",)])
        self.assertEqual(display.screens[-1], ("ready", None))
        self.assertIn("assistant: state connecting: local service", messages)

    def test_capture_failure_enters_error_state(self):
        """Capture errors should stop the exchange and show an error state."""
        controller, _, display, _ = self.make_controller(
            capture_func=lambda: (_ for _ in ()).throw(RuntimeError("capture failed")),
        )
        controller.state_machine.reset_to_ready()
        controller.handle_button_event(self.button.BUTTON_PRESSED)

        with self.assertRaises(RuntimeError):
            controller.handle_button_event(self.button.BUTTON_RELEASED)

        self.assertEqual(controller.state_machine.state, "error")
        self.assertEqual(display.screens[-1], ("error", "RuntimeError"))

    def test_playback_failure_enters_error_state(self):
        """Playback errors should leave a visible recoverable error."""
        controller, _, display, _ = self.make_controller(
            playback_func=lambda audio: (_ for _ in ()).throw(RuntimeError("playback failed")),
        )
        controller.state_machine.reset_to_ready()
        controller.handle_button_event(self.button.BUTTON_PRESSED)

        with self.assertRaises(RuntimeError):
            controller.handle_button_event(self.button.BUTTON_RELEASED)

        self.assertEqual(controller.state_machine.state, "error")
        self.assertEqual(display.screens[-1], ("error", "RuntimeError"))

    def test_poll_button_loop_dispatches_events(self):
        """The poll loop should dispatch debounced button events and then exit."""
        pressed = self.button.BUTTON_PRESSED
        released = self.button.BUTTON_RELEASED

        class FakeButton:
            """Return a press, release, then idle events."""

            def __init__(self):
                """Create a fake event source."""
                self.events = [pressed, released, None, None]

            def update(self):
                """Return the next event."""
                if self.events:
                    return self.events.pop(0)
                return None

        controller, _, _, _ = self.make_controller()
        controller.state_machine.reset_to_ready()
        sleeps = []

        state = self.push_to_talk.poll_button_loop(
            controller,
            FakeButton(),
            idle_polls=2,
            sleep_ms_func=sleeps.append,
        )

        self.assertEqual(state, "ready")
        self.assertEqual(sleeps, [25, 25, 25, 25])


if __name__ == "__main__":
    unittest.main()
