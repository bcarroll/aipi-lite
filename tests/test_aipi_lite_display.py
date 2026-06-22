"""Tests for the implemented MicroPython display baseline."""

import importlib
from pathlib import Path
import sys
import types
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

MODULES_TO_CLEAR = (
    "aipi_lite_config",
    "es8311",
    "main",
    "pins",
    "machine",
    "time",
    "lib",
    "lib.st7735",
    "lib.st7735.sysfont",
)


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


class FakePWM:
    """Record PWM construction for backlight setup."""

    created = []

    def __init__(self, pin):
        """Create a fake PWM channel bound to a fake pin."""
        self.pin = pin
        FakePWM.created.append(self)


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


class FakeTime(types.ModuleType):
    """Minimal replacement for MicroPython's time module."""

    def __init__(self):
        """Create a fake time module that records millisecond sleeps."""
        super().__init__("time")
        self.sleep_ms_calls = []

    def sleep_ms(self, milliseconds):
        """Record a MicroPython sleep_ms call."""
        self.sleep_ms_calls.append(milliseconds)


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
    sysfont.sysfont = {"Width": 5, "Height": 8, "Start": 0, "End": 255, "Data": bytearray()}
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
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


class AipiLiteDisplayConfigTests(unittest.TestCase):
    """Validate the implemented display pin map and demo behavior."""

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

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

    def test_main_draws_expected_boot_demo_text(self):
        """main.py should render the current AIPI-LITE MicroPython demo text."""
        clear_imported_modules()
        ensure_src_path()
        fake_time = install_micropython_stubs()

        main = importlib.import_module("main")
        messages = []
        main.main(print_func=messages.append)
        tft = FakeTFT.created[0]

        self.assertEqual(
            tft.calls[-3:],
            [
                ("fill", 0),
                ("text", (10, 30), "AIPI-LITE", 65535, main.load_sysfont(), 2, True),
                ("text", (30, 60), "Micropython", 65535, main.load_sysfont(), 1, True),
            ],
        )
        self.assertIn("main: speaker amplifier disabled", messages)
        speaker_pin = next(pin for pin in FakePin.created if pin.pin_id == 9)
        self.assertEqual(speaker_pin.values, [0, 0])
        self.assertEqual(messages[-2:], ["main: display baseline rendered", "main: skeleton ready"])
        self.assertEqual(fake_time.sleep_ms_calls, [1500, 100])


if __name__ == "__main__":
    unittest.main()
