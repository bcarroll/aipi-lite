"""Tests for the AIPI-Lite MicroPython display bring-up."""

import importlib
from pathlib import Path
import sys
import types
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SRC_LIB_ROOT = SRC_ROOT / "lib"

MODULES_TO_CLEAR = (
    "aipi_lite_config",
    "display",
    "display_probe",
    "es8311",
    "main",
    "pins",
    "machine",
    "time",
    "lib",
    "lib.st7735",
    "lib.st7735.sysfont",
)

FAKE_FONT = {"Width": 5, "Height": 8, "Start": 0, "End": 255, "Data": bytearray()}


class FakePin:
    """Record MicroPython Pin construction and output state changes."""

    OUT = "OUT"
    PULL_DOWN = "PULL_DOWN"
    created = []

    def __init__(self, pin_id, mode=None, pull=None):
        """Create a fake pin and preserve the supplied MicroPython arguments."""
        self.pin_id = pin_id.pin_id if isinstance(pin_id, FakePin) else pin_id
        self.mode = mode
        self.pull = pull
        self.values = []
        FakePin.created.append(self)

    def __call__(self, value=None):
        """Read or set the fake pin value."""
        if value is None:
            return self.values[-1] if self.values else 0
        self.values.append(value)

    def value(self, value=None):
        """Read or set the fake pin through MicroPython's value API."""
        return self.__call__(value)


class FakePWM:
    """Record PWM construction and duty changes for backlight setup."""

    created = []

    def __init__(self, pin):
        """Create a fake PWM channel bound to a fake pin."""
        self.pin = pin
        self.duty_u16_values = []
        self.duty_values = []
        FakePWM.created.append(self)

    def duty_u16(self, value):
        """Record a 16-bit PWM duty change."""
        self.duty_u16_values.append(value)

    def duty(self, value):
        """Record a 10-bit PWM duty change."""
        self.duty_values.append(value)


class FakeSPI:
    """Record MicroPython SPI construction for the display bus."""

    created = []

    def __init__(self, bus_id, baudrate, polarity, phase, sck, mosi, miso):
        """Create a fake SPI bus with the supplied display bus arguments."""
        self.bus_id = bus_id
        self.baudrate = baudrate
        self.polarity = polarity
        self.phase = phase
        self.sck = sck
        self.mosi = mosi
        self.miso = miso
        FakeSPI.created.append(self)


class FakeTFT:
    """Record TFT construction, initialization, and drawing calls."""

    created = []

    def __init__(self, spi, dc, rst, cs, screen_size):
        """Create a fake TFT object with the display wiring arguments."""
        self.spi = spi
        self.dc = dc
        self.rst = rst
        self.cs = cs
        self.screen_size = screen_size
        self.calls = []
        FakeTFT.created.append(self)

    def initr(self):
        """Record ST7735 red-tab initialization."""
        self.calls.append(("initr",))

    def rotation(self, rotation):
        """Record display rotation setup."""
        self.calls.append(("rotation", rotation))

    def rgb(self, enabled):
        """Record display RGB/BGR mode setup."""
        self.calls.append(("rgb", enabled))

    def fill(self, color):
        """Record display fill calls."""
        self.calls.append(("fill", color))

    def text(self, position, text, color, font, size, nowrap=False):
        """Record display text rendering calls."""
        self.calls.append(("text", position, text, color, font, size, nowrap))

    def fillcircle(self, position, radius, color):
        """Record circular status-indicator drawing calls."""
        self.calls.append(("fillcircle", position, radius, color))


class FakeTime(types.ModuleType):
    """Minimal replacement for MicroPython's time module."""

    def __init__(self):
        """Create a fake time module that records millisecond sleeps."""
        super().__init__("time")
        self.sleep_ms_calls = []

    def sleep_ms(self, milliseconds):
        """Record a MicroPython sleep_ms call."""
        self.sleep_ms_calls.append(milliseconds)


class FakeStatusDisplay:
    """Record display probe status render calls."""

    def __init__(self):
        """Create a fake display renderer."""
        self.statuses = []

    def render_status(self, status, detail=None):
        """Record one rendered status screen."""
        self.statuses.append((status, detail))


def install_micropython_stubs():
    """Install fake MicroPython modules required by the current firmware code."""
    FakePin.created.clear()
    FakePWM.created.clear()
    FakeSPI.created.clear()
    FakeTFT.created.clear()

    machine = types.ModuleType("machine")
    machine.Pin = FakePin
    machine.PWM = FakePWM
    machine.SPI = FakeSPI

    st7735 = types.ModuleType("lib.st7735")
    st7735.__path__ = []
    st7735.TFT = FakeTFT

    sysfont = types.ModuleType("lib.st7735.sysfont")
    sysfont.sysfont = FAKE_FONT
    st7735.sysfont = sysfont

    fake_time = FakeTime()

    sys.modules["machine"] = machine
    sys.modules["lib.st7735"] = st7735
    sys.modules["lib.st7735.sysfont"] = sysfont
    sys.modules["time"] = fake_time
    return fake_time


def clear_imported_modules():
    """Remove modules whose imports have MicroPython-only side effects."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    for source_root in (SRC_ROOT, SRC_LIB_ROOT):
        source_path = str(source_root)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)


class AipiLiteDisplayConfigTests(unittest.TestCase):
    """Validate display hardware setup, layout, and probe behavior."""

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def import_display(self):
        """Import the display module with the source tree on sys.path."""
        ensure_src_path()
        return importlib.import_module("display")

    def test_display_config_uses_documented_lcd_pins(self):
        """aipi_lite_config should initialize the TFT with the known LCD pins."""
        clear_imported_modules()
        ensure_src_path()
        install_micropython_stubs()

        config = importlib.import_module("aipi_lite_config")

        self.assertEqual(config.spi_baudrate, 20_000_000)
        self.assertEqual(config.bl.pin.pin_id, 3)
        self.assertEqual(config.cs.pin_id, 15)
        self.assertEqual(config.dc.pin_id, 7)
        self.assertEqual(config.rst.pin_id, 18)

        self.assertEqual(len(FakeSPI.created), 1)
        spi = FakeSPI.created[0]
        self.assertEqual(spi.bus_id, 1)
        self.assertEqual(spi.sck.pin_id, 16)
        self.assertEqual(spi.mosi.pin_id, 17)
        self.assertIsNone(spi.miso)
        self.assertEqual(spi.polarity, 0)
        self.assertEqual(spi.phase, 0)

        self.assertEqual(len(FakeTFT.created), 1)
        tft = FakeTFT.created[0]
        self.assertIs(tft.spi, spi)
        self.assertEqual(tft.dc.pin_id, 7)
        self.assertEqual(tft.rst.pin_id, 18)
        self.assertEqual(tft.cs.pin_id, 15)
        self.assertEqual(tft.screen_size, (128, 128))
        self.assertEqual(tft.calls[:3], [("initr",), ("rotation", 1), ("rgb", True)])

    def test_status_definitions_cover_required_roadmap_states(self):
        """The renderer should support every display status from feat/04."""
        display = self.import_display()

        self.assertEqual(
            display.available_statuses(),
            ("boot", "wifi", "offline", "ready", "recording", "processing", "speaking", "error"),
        )
        for status in display.available_statuses():
            definition = display.screen_definition(status)
            self.assertIn("title", definition)
            self.assertIn("lines", definition)
            self.assertIn("foreground", definition)
            self.assertIn("background", definition)

    def test_wrap_text_keeps_lines_within_display_bounds(self):
        """Long status details should wrap and truncate inside the screen width."""
        display = self.import_display()

        lines = display.wrap_text(
            "supercalifragilistic local firmware display status details",
            max_chars=12,
            max_lines=3,
        )

        self.assertLessEqual(len(lines), 3)
        self.assertTrue(all(len(line) <= 12 for line in lines))
        self.assertEqual(lines[0], "supercalifra")

    def test_layout_status_lines_includes_detail_without_overflow(self):
        """Status layout should include bounded detail text."""
        display = self.import_display()

        lines = display.layout_status_lines(
            "error",
            detail="local service unavailable after repeated health check failures",
        )

        self.assertLessEqual(len(lines), display.MAX_BODY_LINES)
        max_chars = display.max_chars_for_width(display.BODY_SCALE)
        self.assertTrue(all(len(line) <= max_chars for line in lines))
        self.assertIn("Check serial", lines)

    def test_status_display_renders_ready_screen_and_controls_backlight(self):
        """StatusDisplay should clear, draw text, and turn on the backlight."""
        clear_imported_modules()
        install_micropython_stubs()
        display = self.import_display()
        hardware = display.create_display_hardware(
            pin_factory=FakePin,
            pwm_factory=FakePWM,
            spi_factory=FakeSPI,
            tft_factory=FakeTFT,
        )
        renderer = display.StatusDisplay(hardware, font=FAKE_FONT)

        title, lines = renderer.render_status("ready", detail="LAN service reachable")

        self.assertEqual(title, "ONLINE")
        self.assertIn("Press button", lines)
        self.assertIn("LAN service", lines)
        self.assertEqual(FakePWM.created[-1].duty_u16_values, [65535])

        tft = FakeTFT.created[-1]
        self.assertEqual(tft.calls[:3], [("initr",), ("rotation", 1), ("rgb", True)])
        self.assertEqual(tft.calls[3], ("fill", 0))
        self.assertEqual(
            tft.calls[4],
            ("text", (6, 12), "ONLINE", display.GREEN, FAKE_FONT, 2, True),
        )
        self.assertIn(
            ("fillcircle", display.STATUS_DOT_POSITION, display.STATUS_DOT_RADIUS, display.GREEN),
            tft.calls,
        )
        body_calls = [call for call in tft.calls if call[0] == "text" and call[1][1] >= 44]
        self.assertTrue(all(call[1][0] == 6 for call in body_calls))

        offline_title, offline_lines = renderer.render_status("offline")
        self.assertEqual(offline_title, "OFFLINE")
        self.assertIn("to reconnect", offline_lines)
        self.assertIn(
            ("fillcircle", display.STATUS_DOT_POSITION, display.STATUS_DOT_RADIUS, display.RED),
            tft.calls,
        )

        renderer.backlight_off()
        self.assertEqual(FakePWM.created[-1].duty_u16_values[-1], 0)

    def test_display_probe_cycles_status_screens_and_logs_transitions(self):
        """The display probe should cycle all status screens in order."""
        clear_imported_modules()
        ensure_src_path()
        probe = importlib.import_module("display_probe")
        display = self.import_display()
        fake_display = FakeStatusDisplay()
        messages = []
        sleeps = []

        probe.run_probe(
            cycles=1,
            delay_ms=5,
            print_func=messages.append,
            status_display=fake_display,
            sleep_ms_func=sleeps.append,
        )

        self.assertEqual(
            fake_display.statuses,
            [(status, None) for status in display.available_statuses()],
        )
        self.assertEqual(sleeps, [5] * len(display.available_statuses()))
        self.assertEqual(messages[0], "display_probe: starting display probe")
        self.assertEqual(messages[-1], "display_probe: complete")
        self.assertIn("display_probe: screen ready", messages)

    def test_main_renders_boot_status_screen(self):
        """main.py should render the reusable boot status screen."""
        clear_imported_modules()
        ensure_src_path()
        fake_time = install_micropython_stubs()

        main = importlib.import_module("main")
        messages = []
        result = main.main(
            print_func=messages.append,
            run_push_to_talk=False,
            status_led_factory=lambda: object(),
        )
        tft = FakeTFT.created[0]

        self.assertIn(("fill", 0), tft.calls)
        self.assertIn(("text", (6, 12), "AIPI-LITE", 65535, FAKE_FONT, 2, True), tft.calls)
        self.assertIn(("text", (6, 44), "Booting", 65535, FAKE_FONT, 1, True), tft.calls)
        self.assertEqual(FakePWM.created[0].duty_u16_values, [65535])
        self.assertIn("main: speaker amplifier disabled", messages)
        speaker_pin = next(pin for pin in FakePin.created if pin.pin_id == 9)
        self.assertEqual(speaker_pin.values, [0, 0])
        self.assertEqual(result, "boot")
        self.assertIn("main: display boot status rendered", messages)
        self.assertEqual(messages[-1], "main: boot-only startup complete")
        self.assertEqual(fake_time.sleep_ms_calls, [100])


if __name__ == "__main__":
    unittest.main()
