"""Assistant state and shared UI status handling for AIPI-Lite."""

STATE_BOOTING = "booting"
STATE_CONNECTING = "connecting"
STATE_OFFLINE = "offline"
STATE_READY = "ready"
STATE_RECORDING = "recording"
STATE_UPLOADING = "uploading"
STATE_PROCESSING = "processing"
STATE_SPEAKING = "speaking"
STATE_ERROR = "error"

ASSISTANT_STATES = (
    STATE_BOOTING,
    STATE_CONNECTING,
    STATE_OFFLINE,
    STATE_READY,
    STATE_RECORDING,
    STATE_UPLOADING,
    STATE_PROCESSING,
    STATE_SPEAKING,
    STATE_ERROR,
)

STATE_UI = {
    STATE_BOOTING: ("offline", "boot"),
    STATE_CONNECTING: ("connecting", "wifi"),
    STATE_OFFLINE: ("offline", "offline"),
    STATE_READY: ("ready", "ready"),
    STATE_RECORDING: ("recording", "recording"),
    STATE_UPLOADING: ("processing", "processing"),
    STATE_PROCESSING: ("processing", "processing"),
    STATE_SPEAKING: ("speaking", "speaking"),
    STATE_ERROR: ("error", "error"),
}


class AssistantStateError(ValueError):
    """Raised when an assistant state transition is invalid."""


def validate_state(state):
    """Return a supported assistant state name or raise."""
    if state not in ASSISTANT_STATES:
        raise AssistantStateError("unknown assistant state: {}".format(state))
    return state


def ui_state_for(state):
    """Return ``(led_state, display_status)`` for an assistant state."""
    return STATE_UI[validate_state(state)]


class StatusOutputs:
    """Update serial, status LED, and display from assistant states."""

    def __init__(self, status_led=None, status_display=None, print_func=print):
        """Create an output multiplexer with optional UI devices."""
        self.status_led = status_led
        self.status_display = status_display
        self.print_func = print_func
        self.events = []

    def update(self, state, detail=None, display_detail=None):
        """Render a state update, with an optional display-only detail override."""
        led_state, display_status = ui_state_for(state)
        self.events.append((state, detail))

        if self.status_led is not None:
            self.status_led.set_state(led_state)
        if self.status_display is not None:
            if display_detail is None:
                display_detail = detail
            self.status_display.render_status(display_status, detail=display_detail)

        message = "assistant: state {}".format(state)
        if detail:
            message = "{}: {}".format(message, detail)
        self.print_func(message)


class AssistantStateMachine:
    """Track assistant state transitions and notify shared UI outputs."""

    def __init__(self, initial_state=STATE_BOOTING, outputs=None, diagnostics=None):
        """Create a state machine with an initial state."""
        self.outputs = outputs
        self.diagnostics = diagnostics
        self.state = validate_state(initial_state)
        self.history = []
        self.transition(self.state)

    def transition(self, state, detail=None, display_detail=None):
        """Move to a supported state and update observers with optional LCD detail."""
        state = validate_state(state)
        previous = self.state
        self.state = state
        self.history.append((state, detail))

        if self.diagnostics is not None:
            self.diagnostics.record_state_transition(previous, state, detail=detail)
        if self.outputs is not None:
            self.outputs.update(state, detail=detail, display_detail=display_detail)
        return state

    def is_ready(self):
        """Return True when the assistant can accept a push-to-talk press."""
        return self.state == STATE_READY

    def is_offline(self):
        """Return True when a button press should retry the local connection."""
        return self.state == STATE_OFFLINE

    def is_recording(self):
        """Return True when a push-to-talk recording is active."""
        return self.state == STATE_RECORDING

    def reset_to_ready(self, detail=None):
        """Recover from a terminal or startup state back to ready."""
        return self.transition(STATE_READY, detail=detail)
