"""AIPI-Lite ST7735 display wrapper and status screen renderer."""

from pins import DISPLAY_BACKLIGHT
from pins import DISPLAY_CS
from pins import DISPLAY_DC
from pins import DISPLAY_MOSI
from pins import DISPLAY_RESET
from pins import DISPLAY_SCLK

SCREEN_SIZE = (128, 128)
SPI_BUS_ID = 1
SPI_BAUDRATE = 20000000
DISPLAY_ROTATION = 1
DISPLAY_RGB = True

BLACK = 0
RED = 31
GREEN = 2016
BLUE = 63488
CYAN = 65504
YELLOW = 2047
MAGENTA = 63519
WHITE = 65535

LEFT_MARGIN = 6
TITLE_Y = 12
BODY_Y = 44
BODY_LINE_HEIGHT = 14
FONT_WIDTH = 5
FONT_HEIGHT = 8
TITLE_SCALE = 2
BODY_SCALE = 1
MAX_BODY_LINES = 5
STATUS_DOT_POSITION = (118, 8)
STATUS_DOT_RADIUS = 4
CONNECTIVITY_TITLE_Y = 6
CONNECTIVITY_ROW_Y = (36, 62)
CONNECTIVITY_COMPONENT_ICON_X = 12
CONNECTIVITY_LABEL_X = 25
CONNECTIVITY_BADGE_X = 78
CONNECTIVITY_STATUS_X = 85
CONNECTIVITY_ACTION_Y = (91, 108)

STATUS_ORDER = (
    "boot",
    "wifi",
    "offline",
    "limited",
    "ready",
    "recording",
    "processing",
    "speaking",
    "error",
)

STATUS_SCREENS = {
    "boot": {
        "title": "AIPI-LITE",
        "lines": ("Booting", "Local firmware"),
        "foreground": WHITE,
        "background": BLACK,
    },
    "wifi": {
        "title": "WI-FI",
        "lines": ("Connecting", "Local network"),
        "foreground": CYAN,
        "background": BLACK,
    },
    "offline": {
        "title": "OFFLINE",
        "lines": ("Press button", "to reconnect"),
        "foreground": WHITE,
        "background": BLACK,
        "status_dot": RED,
    },
    "limited": {
        "title": "LIMITED",
        "lines": ("PTT unavailable", "Tap to retry"),
        "foreground": WHITE,
        "background": BLACK,
        "status_dot": RED,
    },
    "ready": {
        "title": "ONLINE",
        "lines": ("Press button", "to record"),
        "foreground": GREEN,
        "background": BLACK,
        "status_dot": GREEN,
    },
    "recording": {
        "title": "REC",
        "lines": ("Recording", "Release to stop"),
        "foreground": RED,
        "background": BLACK,
    },
    "processing": {
        "title": "WORKING",
        "lines": ("Processing", "local request"),
        "foreground": YELLOW,
        "background": BLACK,
    },
    "speaking": {
        "title": "SPEAKING",
        "lines": ("Playing", "response audio"),
        "foreground": BLUE,
        "background": BLACK,
    },
    "error": {
        "title": "ERROR",
        "lines": ("Check serial", "for details"),
        "foreground": MAGENTA,
        "background": BLACK,
    },
}


class DisplayHardware:
    """Hold initialized ST7735 display hardware objects."""

    def __init__(self, backlight, chip_select, data_command, reset, spi, tft):
        """Create a display hardware bundle from initialized components."""
        self.backlight = backlight
        self.chip_select = chip_select
        self.data_command = data_command
        self.reset = reset
        self.spi = spi
        self.tft = tft


def available_statuses():
    """Return the supported display status names in probe order."""
    return STATUS_ORDER


def load_sysfont():
    """Load the bundled MicroPython ST7735 font only when rendering text."""
    from lib.st7735.sysfont import sysfont

    return sysfont


def max_chars_for_width(scale=BODY_SCALE, screen_width=SCREEN_SIZE[0], margin=LEFT_MARGIN):
    """Return the number of font characters that fit within the display width."""
    char_width = FONT_WIDTH * scale + 1
    usable_width = screen_width - margin * 2
    return max(1, usable_width // char_width)


def truncate_text(text, max_chars):
    """Return text constrained to max_chars using an ASCII continuation marker."""
    text = str(text)
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return text[: max_chars - 3] + "..."


def wrap_text(text, max_chars, max_lines):
    """Wrap text into bounded display lines with deterministic truncation."""
    words = str(text).split()
    if not words:
        return ()

    lines = []
    current = ""
    for word in words:
        while len(word) > max_chars:
            chunk = word[:max_chars]
            word = word[max_chars:]
            if current:
                lines.append(current)
                current = ""
            lines.append(chunk)
            if len(lines) >= max_lines:
                return tuple(lines[: max_lines - 1] + [truncate_text(lines[max_lines - 1], max_chars)])

        candidate = word if not current else current + " " + word
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            lines.append(current)
        current = word
        if len(lines) >= max_lines:
            lines[-1] = truncate_text(lines[-1], max_chars)
            return tuple(lines)

    if current:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = truncate_text(lines[-1], max_chars)
    return tuple(lines)


def screen_definition(status):
    """Return the display definition for a supported status name."""
    try:
        return STATUS_SCREENS[status]
    except KeyError:
        raise ValueError("unknown display status: {}".format(status))


def layout_status_lines(status, detail=None, max_lines=MAX_BODY_LINES):
    """Return wrapped body lines for a named status screen and optional detail."""
    definition = screen_definition(status)
    max_chars = max_chars_for_width(BODY_SCALE)
    lines = []
    for line in definition["lines"]:
        lines.extend(wrap_text(line, max_chars, max_lines))
    if detail:
        lines.extend(wrap_text(detail, max_chars, max_lines))

    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = truncate_text(lines[-1], max_chars)
    return tuple(lines)


def _set_backlight_level(backlight, level):
    """Set the backlight level on PWM or pin-like test doubles."""
    level = max(0, min(65535, int(level)))
    if hasattr(backlight, "duty_u16"):
        backlight.duty_u16(level)
        return
    if hasattr(backlight, "duty"):
        backlight.duty(int(level * 1023 / 65535))
        return
    pin = getattr(backlight, "pin", None)
    if pin is not None:
        if hasattr(pin, "value"):
            pin.value(1 if level else 0)
        else:
            pin(1 if level else 0)


def create_display_hardware(
    pin_factory=None,
    pwm_factory=None,
    spi_factory=None,
    tft_factory=None,
):
    """Initialize and return the ST7735 display hardware bundle."""
    if pin_factory is None or pwm_factory is None or spi_factory is None:
        from machine import PWM
        from machine import SPI
        from machine import Pin

        if pin_factory is None:
            pin_factory = Pin
        if pwm_factory is None:
            pwm_factory = PWM
        if spi_factory is None:
            spi_factory = SPI

    if tft_factory is None:
        from lib.st7735 import TFT

        tft_factory = TFT

    backlight = pwm_factory(pin_factory(DISPLAY_BACKLIGHT))
    chip_select = pin_factory(DISPLAY_CS, pin_factory.OUT)
    data_command = pin_factory(DISPLAY_DC, pin_factory.OUT)
    reset = pin_factory(DISPLAY_RESET, pin_factory.OUT)
    spi = spi_factory(
        SPI_BUS_ID,
        SPI_BAUDRATE,
        polarity=0,
        phase=0,
        sck=pin_factory(DISPLAY_SCLK),
        mosi=pin_factory(DISPLAY_MOSI),
        miso=None,
    )
    tft = tft_factory(spi, data_command, reset, chip_select, SCREEN_SIZE)
    tft.initr()
    tft.rotation(DISPLAY_ROTATION)
    tft.rgb(DISPLAY_RGB)
    return DisplayHardware(backlight, chip_select, data_command, reset, spi, tft)


class StatusDisplay:
    """Render AIPI-Lite named status screens on an initialized ST7735 display."""

    def __init__(self, hardware, font=None):
        """Create a renderer around initialized display hardware."""
        self.hardware = hardware
        self.tft = hardware.tft
        self.backlight = hardware.backlight
        self.font = font or load_sysfont()

    def backlight_on(self, level=65535):
        """Turn on the display backlight."""
        _set_backlight_level(self.backlight, level)

    def backlight_off(self):
        """Turn off the display backlight."""
        _set_backlight_level(self.backlight, 0)

    def clear(self, color=BLACK):
        """Clear the display to a single RGB565 color."""
        self.tft.fill(color)

    def _draw_wifi_icon(self, y, color):
        """Draw a compact Wi-Fi signal graphic using bounded line primitives."""
        x = CONNECTIVITY_COMPONENT_ICON_X
        self.tft.line((x - 6, y), (x, y - 5), color)
        self.tft.line((x, y - 5), (x + 6, y), color)
        self.tft.line((x - 3, y + 3), (x, y), color)
        self.tft.line((x, y), (x + 3, y + 3), color)
        self.tft.fillcircle((x, y + 6), 1, color)

    def _draw_service_icon(self, y, color):
        """Draw a compact two-tier local-service graphic."""
        x = CONNECTIVITY_COMPONENT_ICON_X - 6
        self.tft.rect((x, y - 5), (12, 5), color)
        self.tft.rect((x, y + 2), (12, 5), color)
        self.tft.fillcircle((x + 2, y - 3), 1, color)
        self.tft.fillcircle((x + 2, y + 4), 1, color)

    def _draw_status_badge(self, y, online):
        """Draw a green check or red cross status badge."""
        color = GREEN if online else RED
        center = (CONNECTIVITY_BADGE_X, y)
        self.tft.fillcircle(center, 5, color)
        if online:
            self.tft.line((center[0] - 3, center[1]), (center[0] - 1, center[1] + 2), WHITE)
            self.tft.line((center[0] - 1, center[1] + 2), (center[0] + 3, center[1] - 2), WHITE)
            return
        self.tft.line((center[0] - 2, center[1] - 2), (center[0] + 2, center[1] + 2), WHITE)
        self.tft.line((center[0] + 2, center[1] - 2), (center[0] - 2, center[1] + 2), WHITE)

    def _draw_connectivity_row(self, component, online, y):
        """Draw one fixed connectivity row and return its explicit text status."""
        if component == "WI-FI":
            self._draw_wifi_icon(y, CYAN)
        else:
            self._draw_service_icon(y, CYAN)
        status = "ONLINE" if online else "OFFLINE"
        status_color = GREEN if online else RED
        self.tft.text(
            (CONNECTIVITY_LABEL_X, y - 4),
            component,
            WHITE,
            self.font,
            BODY_SCALE,
            nowrap=True,
        )
        self._draw_status_badge(y, online)
        self.tft.text(
            (CONNECTIVITY_STATUS_X, y - 4),
            status,
            status_color,
            self.font,
            BODY_SCALE,
            nowrap=True,
        )
        self.tft.line((LEFT_MARGIN, y + 12), (SCREEN_SIZE[0] - LEFT_MARGIN, y + 12), WHITE)
        return component, status

    def render_connectivity(self, connectivity, limited=False):
        """Render fixed Wi-Fi/service rows with accessible retry and bypass guidance."""
        title = "LIMITED" if limited else "OFFLINE"
        retry_component = connectivity.first_offline_component()
        retry_label = "Wi-Fi" if retry_component == "wifi" else "service"
        if limited:
            actions = ("PTT unavailable", "Tap: Retry {}".format(retry_label))
        else:
            actions = ("Tap: Retry {}".format(retry_label), "Hold 2s: Bypass")

        self.backlight_on()
        self.clear(BLACK)
        self.tft.text(
            (LEFT_MARGIN, CONNECTIVITY_TITLE_Y),
            title,
            WHITE,
            self.font,
            TITLE_SCALE,
            nowrap=True,
        )
        rows = (
            self._draw_connectivity_row("WI-FI", connectivity.wifi_online, CONNECTIVITY_ROW_Y[0]),
            self._draw_connectivity_row(
                "SERVICE",
                connectivity.service_online,
                CONNECTIVITY_ROW_Y[1],
            ),
        )
        for y, action in zip(CONNECTIVITY_ACTION_Y, actions):
            self.tft.text(
                (LEFT_MARGIN, y),
                action,
                YELLOW if action.startswith("Tap:") or action.startswith("Hold") else WHITE,
                self.font,
                BODY_SCALE,
                nowrap=True,
            )
        return title, rows, actions

    def render_status(self, status, detail=None):
        """Render a named status screen with optional detail text."""
        definition = screen_definition(status)
        background = definition["background"]
        foreground = definition["foreground"]
        title = truncate_text(definition["title"], max_chars_for_width(TITLE_SCALE))
        lines = layout_status_lines(status, detail)

        self.backlight_on()
        self.clear(background)
        self.tft.text((LEFT_MARGIN, TITLE_Y), title, foreground, self.font, TITLE_SCALE, nowrap=True)
        status_dot = definition.get("status_dot")
        if status_dot is not None:
            self.tft.fillcircle(STATUS_DOT_POSITION, STATUS_DOT_RADIUS, status_dot)
        for index, line in enumerate(lines):
            y = BODY_Y + index * BODY_LINE_HEIGHT
            self.tft.text((LEFT_MARGIN, y), line, foreground, self.font, BODY_SCALE, nowrap=True)
        return title, lines


def create_status_display(font=None):
    """Initialize display hardware and return a status renderer."""
    return StatusDisplay(create_display_hardware(), font=font)
