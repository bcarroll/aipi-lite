"""Push-to-talk assistant flow for the local-only AIPI-Lite MVP."""

from assistant_state import AssistantStateMachine
from assistant_state import ConnectivityStatus
from assistant_state import STATE_CONNECTING
from assistant_state import STATE_ERROR
from assistant_state import STATE_LIMITED
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
from button import BUTTON_LONG_PRESSED
from button import BUTTON_PRESSED
from button import BUTTON_RELEASED
from local_endpoint import EndpointPolicyError
from reliability import RetryPolicy
from reliability import ReconnectManager
from reliability import call_with_retries
from reliability import sleep_ms
from service_client import LocalServiceClient
from wifi_config import WiFiConfigError
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
        configuration_error=None,
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
        self.configuration_error = configuration_error
        self.connectivity = ConnectivityStatus()
        self.state_machine.connectivity = self.connectivity
        self._blocked_press_active = False
        self._blocked_hold_consumed = False
        self.last_result = None

    def connect(self):
        """Attempt Wi-Fi and local-service startup in dependency order."""
        self.connectivity = ConnectivityStatus()
        self.state_machine.transition(
            STATE_CONNECTING,
            detail="Wi-Fi",
            connectivity=self.connectivity,
        )
        try:
            self._ensure_network()
            self.connectivity = self.connectivity.with_wifi(True)
        except Exception as exc:
            return self._go_connectivity_blocked(STATE_OFFLINE, "wifi_connect", exc)

        self.state_machine.transition(
            STATE_CONNECTING,
            detail="local service",
            connectivity=self.connectivity,
        )
        try:
            self._retry(lambda: self.service_client.health(), "service_health")
            self.connectivity = self.connectivity.with_service(True)
            self.state_machine.transition(STATE_READY, connectivity=self.connectivity)
            return STATE_READY
        except Exception as exc:
            return self._handle_service_failure(STATE_OFFLINE, exc)

    def handle_button_event(self, event):
        """Handle one debounced button event and return the current state."""
        if event == BUTTON_PRESSED and self.state_machine.is_connectivity_blocked():
            self._blocked_press_active = True
            self._blocked_hold_consumed = False
            return self.state_machine.state
        if event == BUTTON_LONG_PRESSED and self.state_machine.is_connectivity_blocked():
            if self._blocked_press_active:
                self._blocked_hold_consumed = True
                if self.state_machine.is_offline():
                    return self.state_machine.transition(
                        STATE_LIMITED,
                        detail="offline bypassed",
                        connectivity=self.connectivity,
                    )
            return self.state_machine.state
        if event == BUTTON_RELEASED and self.state_machine.is_connectivity_blocked():
            if not self._blocked_press_active:
                return self.state_machine.state
            self._blocked_press_active = False
            if self._blocked_hold_consumed:
                self._blocked_hold_consumed = False
                return self.state_machine.state
            return self.retry_first_offline_component()
        if event == BUTTON_PRESSED and self.state_machine.is_ready():
            return self.state_machine.transition(STATE_RECORDING)
        if event == BUTTON_RELEASED and self.state_machine.is_recording():
            self.last_result = self.run_exchange()
            return self.state_machine.state
        return self.state_machine.state

    def retry_first_offline_component(self):
        """Retry exactly the first offline dependency and return the resulting state."""
        blocked_state = STATE_LIMITED if self.state_machine.is_limited() else STATE_OFFLINE
        component = self.connectivity.first_offline_component()
        if component is None:
            return self.state_machine.transition(STATE_READY, connectivity=self.connectivity)

        if component == "wifi":
            self.state_machine.transition(
                STATE_CONNECTING,
                detail="Wi-Fi",
                connectivity=self.connectivity,
            )
            try:
                self._ensure_network()
                self.connectivity = self.connectivity.with_wifi(True)
            except Exception as exc:
                return self._go_connectivity_blocked(blocked_state, "wifi_connect", exc)
            return self.state_machine.transition(
                blocked_state,
                detail="local service pending",
                connectivity=self.connectivity,
            )

        self.state_machine.transition(
            STATE_CONNECTING,
            detail="local service",
            connectivity=self.connectivity,
        )
        try:
            self._retry(lambda: self.service_client.health(), "service_health")
            self.connectivity = self.connectivity.with_service(True)
        except Exception as exc:
            return self._handle_service_failure(blocked_state, exc)
        return self.state_machine.transition(STATE_READY, connectivity=self.connectivity)

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
        if self.configuration_error is not None:
            raise self.configuration_error
        if self.reconnect_manager is not None:
            self.reconnect_manager.ensure_connected()

    def _network_is_connected(self):
        """Return the reconnect manager's best-effort current WLAN state."""
        if self.reconnect_manager is None or not hasattr(self.reconnect_manager, "is_connected"):
            return self.connectivity.wifi_online
        try:
            return bool(self.reconnect_manager.is_connected())
        except Exception:
            return False

    def _fail(self, category, error):
        """Record and display a recoverable assistant failure."""
        if self.diagnostics is not None:
            self.diagnostics.record_failure(category, error)
        self.state_machine.transition(STATE_ERROR, detail=type(error).__name__)

    def _handle_service_failure(self, blocked_state, error):
        """Classify a failed service attempt using the current WLAN state."""
        if not self._network_is_connected():
            self.connectivity = self.connectivity.with_wifi(False)
            return self._go_connectivity_blocked(blocked_state, "wifi_connect", error)
        self.connectivity = self.connectivity.with_service(False)
        return self._go_connectivity_blocked(blocked_state, "service_health", error)

    def _go_connectivity_blocked(self, blocked_state, category, error):
        """Record a component failure and render OFFLINE or LIMITED status."""
        if self.diagnostics is not None:
            self.diagnostics.record_failure(category, error)
        return self.state_machine.transition(
            blocked_state,
            detail="Wi-Fi" if category == "wifi_connect" else "local service",
            connectivity=self.connectivity,
        )


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
    configuration_error = None
    if config is None:
        try:
            config = config_loader()
        except WiFiConfigError as exc:
            configuration_error = exc
    if service_client is None and configuration_error is None:
        try:
            service_client = LocalServiceClient(
                config.local_service_url,
                approved_hosts=config.approved_hosts,
            )
        except EndpointPolicyError as exc:
            configuration_error = exc

    outputs = StatusOutputs(status_led=status_led, status_display=status_display, print_func=print_func)
    state_machine = AssistantStateMachine(outputs=outputs, diagnostics=diagnostics)
    if reconnect_manager is None and connect_wifi_func is not None and configuration_error is None:
        reconnect_manager = ReconnectManager(config, connect_wifi_func, wlan=wlan, diagnostics=diagnostics)
    return PushToTalkController(
        service_client,
        state_machine=state_machine,
        reconnect_manager=reconnect_manager,
        diagnostics=diagnostics,
        configuration_error=configuration_error,
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
