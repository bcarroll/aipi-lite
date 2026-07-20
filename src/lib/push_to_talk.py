"""Push-to-talk assistant flow for the local-only AIPI-Lite MVP."""

from assistant_state import AssistantStateMachine
from assistant_state import STATE_CONNECTING
from assistant_state import STATE_ERROR
from assistant_state import STATE_OFFLINE
from assistant_state import STATE_PROCESSING
from assistant_state import STATE_READY
from assistant_state import STATE_RECORDING
from assistant_state import STATE_SPEAKING
from assistant_state import STATE_UPLOADING
from assistant_state import StatusOutputs
from audio_capture import AudioCaptureConfig
from audio_capture import capture_pcm
from audio_capture import wav_bytes
from audio_playback import play_wav
from button import BUTTON_PRESSED
from button import BUTTON_RELEASED
from reliability import RetryPolicy
from reliability import ReconnectManager
from reliability import call_with_retries
from reliability import sleep_ms
from service_client import LocalServiceClient
from wifi_config import load_config


class PushToTalkError(Exception):
    """Raised when a push-to-talk exchange cannot complete."""


class AssistantExchangeResult:
    """Hold the visible result of one assistant exchange."""

    def __init__(self, session_id, display_text="", audio_played=False, playback_metrics=None):
        """Create an immutable exchange result."""
        self.session_id = session_id
        self.display_text = display_text
        self.audio_played = audio_played
        self.playback_metrics = playback_metrics


def capture_wav(config=None):
    """Capture bounded microphone PCM and return a WAV payload."""
    if config is None:
        config = AudioCaptureConfig()
    return wav_bytes(capture_pcm(config=config), config=config)


class PushToTalkController:
    """Coordinate button events, audio capture, local service, UI, and playback."""

    def __init__(
        self,
        service_client,
        state_machine=None,
        capture_func=None,
        playback_func=None,
        retry_policy=None,
        reconnect_manager=None,
        sleep_ms_func=sleep_ms,
        diagnostics=None,
    ):
        """Create a push-to-talk controller from injectable dependencies."""
        self.service_client = service_client
        self.diagnostics = diagnostics
        self.state_machine = state_machine or AssistantStateMachine(diagnostics=diagnostics)
        self.capture_func = capture_func or capture_wav
        self.playback_func = playback_func or play_wav
        self.retry_policy = retry_policy or RetryPolicy()
        self.reconnect_manager = reconnect_manager
        self.sleep_ms_func = sleep_ms_func
        self.last_result = None

    def connect(self):
        """Validate local service reachability and return ready or offline."""
        try:
            self.state_machine.transition(STATE_CONNECTING, detail="local service")
            self._ensure_network()
            self._retry(lambda: self.service_client.health(), "service_health")
            self.state_machine.transition(STATE_READY)
            return STATE_READY
        except Exception as exc:
            return self._go_offline("connect", exc)

    def handle_button_event(self, event):
        """Handle one debounced button event and return the current state."""
        if event == BUTTON_PRESSED and self.state_machine.is_offline():
            return self.connect()
        if event == BUTTON_PRESSED and self.state_machine.is_ready():
            return self.state_machine.transition(STATE_RECORDING)
        if event == BUTTON_RELEASED and self.state_machine.is_recording():
            self.last_result = self.run_exchange()
            return self.state_machine.state
        return self.state_machine.state

    def run_exchange(self):
        """Run one complete local assistant exchange after button release."""
        try:
            audio_payload = self.capture_func()
            result = self.exchange_audio(audio_payload)
            self.state_machine.transition(STATE_READY)
            self.last_result = result
            return result
        except Exception as exc:
            self._fail("exchange", exc)
            raise

    def exchange_audio(self, audio_payload):
        """Upload audio, retrieve response text/audio, and play the response."""
        if not audio_payload:
            raise PushToTalkError("captured audio payload is empty")

        self.state_machine.transition(STATE_UPLOADING)
        session_id = self._retry(lambda: self.service_client.start_session(), "start_session")
        self._retry(lambda: self.service_client.upload_audio(session_id, audio_payload), "upload_audio")

        self.state_machine.transition(STATE_PROCESSING)
        response_payload = self._retry(lambda: self.service_client.get_response(session_id), "get_response")
        display_text = response_payload.get("display_text", "")

        playback_metrics = None
        audio_played = False
        audio_url = response_payload.get("audio_url")
        if self.service_client.response_ready(response_payload) and audio_url:
            audio_bytes = self._retry(lambda: self.service_client.download_audio(audio_url), "download_audio")
            self.state_machine.transition(STATE_SPEAKING, detail=display_text)
            playback_metrics = self.playback_func(audio_bytes)
            audio_played = True
            if self.diagnostics is not None and playback_metrics is not None:
                self.diagnostics.record_metric("playback_underruns", playback_metrics.underrun_count)

        return AssistantExchangeResult(
            session_id=session_id,
            display_text=display_text,
            audio_played=audio_played,
            playback_metrics=playback_metrics,
        )

    def recover(self, detail="recovered"):
        """Return the assistant to ready after a visible error state."""
        return self.state_machine.reset_to_ready(detail=detail)

    def _retry(self, operation, name):
        """Run a named local operation through the retry policy."""
        def on_retry(attempt, delay_ms, error):
            if self.diagnostics is not None:
                self.diagnostics.record(
                    "retry",
                    name,
                    {"attempt": attempt, "delay_ms": delay_ms, "type": type(error).__name__},
                )
            self._ensure_network()

        return call_with_retries(
            operation,
            policy=self.retry_policy,
            sleep_ms_func=self.sleep_ms_func,
            on_retry=on_retry,
        )

    def _ensure_network(self):
        """Reconnect Wi-Fi when a reconnect manager is available."""
        if self.reconnect_manager is not None:
            self.reconnect_manager.ensure_connected()

    def _fail(self, category, error):
        """Record and display a recoverable assistant failure."""
        if self.diagnostics is not None:
            self.diagnostics.record_failure(category, error)
        self.state_machine.transition(STATE_ERROR, detail=type(error).__name__)

    def _go_offline(self, category, error):
        """Record a connection failure and await an explicit reconnect press."""
        if self.diagnostics is not None:
            self.diagnostics.record_failure(category, error)
        return self.state_machine.transition(STATE_OFFLINE)


def create_controller(
    config=None,
    config_loader=load_config,
    service_client=None,
    status_led=None,
    status_display=None,
    print_func=print,
    diagnostics=None,
    reconnect_manager=None,
    connect_wifi_func=None,
    wlan=None,
):
    """Create a controller from local Wi-Fi config and optional UI devices."""
    if config is None:
        config = config_loader()
    if service_client is None:
        service_client = LocalServiceClient(config.local_service_url, approved_hosts=config.approved_hosts)

    outputs = StatusOutputs(status_led=status_led, status_display=status_display, print_func=print_func)
    state_machine = AssistantStateMachine(outputs=outputs, diagnostics=diagnostics)
    if reconnect_manager is None and connect_wifi_func is not None:
        reconnect_manager = ReconnectManager(config, connect_wifi_func, wlan=wlan, diagnostics=diagnostics)
    return PushToTalkController(
        service_client,
        state_machine=state_machine,
        reconnect_manager=reconnect_manager,
        diagnostics=diagnostics,
    )


def poll_button_loop(
    controller,
    button,
    poll_delay_ms=25,
    idle_polls=None,
    sleep_ms_func=sleep_ms,
):
    """Poll a debounced button and dispatch push-to-talk events."""
    polls = 0
    while idle_polls is None or polls < idle_polls:
        event = button.update()
        if event is not None:
            controller.handle_button_event(event)
            polls = 0
        else:
            polls += 1
        sleep_ms_func(poll_delay_ms)
    return controller.state_machine.state
