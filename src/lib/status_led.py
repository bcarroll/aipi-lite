"""Status LED driver for the AIPI-Lite WS2812/NeoPixel indicator."""

from pins import STATUS_LED_WS2812_DATA

STATUS_LED_STATES = (
    "offline",
    "connecting",
    "ready",
    "recording",
    "processing",
    "speaking",
    "error",
)

STATUS_LED_COLORS = {
    "offline": (0, 0, 0),
    "connecting": (0, 0, 24),
    "ready": (0, 24, 0),
    "recording": (24, 0, 0),
    "processing": (24, 12, 0),
    "speaking": (0, 18, 18),
    "error": (24, 0, 24),
}


def color_for_state(state):
    """Return the user-visible RGB color tuple for a named LED state."""
    try:
        return STATUS_LED_COLORS[state]
    except KeyError:
        raise ValueError("unknown status LED state: {}".format(state))


def available_states():
    """Return the supported status LED state names in display order."""
    return STATUS_LED_STATES


class StatusLed:
    """Drive the single AIPI-Lite WS2812 status LED through NeoPixel."""

    def __init__(self, pin_number=STATUS_LED_WS2812_DATA, pin_factory=None, neopixel_factory=None):
        """Create a status LED driver for the configured WS2812 data pin."""
        if pin_factory is None or neopixel_factory is None:
            from machine import Pin
            from neopixel import NeoPixel

            if pin_factory is None:
                pin_factory = Pin
            if neopixel_factory is None:
                neopixel_factory = NeoPixel

        self.pin_number = pin_number
        self.pin = pin_factory(pin_number)
        self.pixel = neopixel_factory(self.pin, 1)
        self.state = None

    def set_color(self, color):
        """Write a user-visible RGB color tuple to the NeoPixel driver."""
        self.pixel[0] = color
        self.pixel.write()

    def set_state(self, state):
        """Set the LED to a named status state and record the current state."""
        color = color_for_state(state)
        self.set_color(color)
        self.state = state

    def off(self):
        """Turn the status LED off and mark the state as offline."""
        self.set_state("offline")
