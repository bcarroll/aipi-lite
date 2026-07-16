"""Tests for the documented AIPI-Lite pin map."""

from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SRC_LIB_ROOT = SRC_ROOT / "lib"


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    for source_root in (SRC_ROOT, SRC_LIB_ROOT):
        source_path = str(source_root)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)


class PinMapTests(unittest.TestCase):
    """Validate the skeleton pin constants against the firmware plan."""

    @classmethod
    def setUpClass(cls):
        """Import the pin map once because it has no hardware side effects."""
        ensure_src_path()
        import pins

        cls.pins = pins

    def test_required_pin_groups_exist(self):
        """pins.py should define every group required by feat/02."""
        self.assertEqual(
            set(self.pins.required_group_names()),
            {"display", "audio", "status_led", "button", "power"},
        )

    def test_pin_groups_match_documented_hardware_map(self):
        """Pin constants should match the current SPEC.md hardware table."""
        self.assertEqual(
            self.pins.DISPLAY_PINS,
            {
                "backlight": 3,
                "dc": 7,
                "cs": 15,
                "sclk": 16,
                "mosi": 17,
                "reset": 18,
            },
        )
        self.assertEqual(
            self.pins.AUDIO_PINS,
            {
                "i2c_scl": 4,
                "i2c_sda": 5,
                "i2s_mclk": 6,
                "i2s_dout": 11,
                "i2s_lrclk": 12,
                "i2s_din": 13,
                "i2s_bclk": 14,
                "speaker_enable": 9,
            },
        )
        self.assertEqual(self.pins.STATUS_LED_PINS, {"ws2812_data": 46})
        self.assertEqual(self.pins.BUTTON_PINS, {"right_function": 42})
        self.assertEqual(self.pins.POWER_PINS, {"board_power_control": 10, "charge_pulse": 21})

    def test_grouped_pins_do_not_reuse_gpio_assignments(self):
        """Declared signals should not duplicate GPIO assignments in the skeleton."""
        pin_numbers = self.pins.grouped_pin_numbers()

        self.assertEqual(len(pin_numbers), len(set(pin_numbers)))

    def test_board_power_control_is_marked_do_not_touch_during_boot(self):
        """GPIO10 should remain declarative until later hardware verification."""
        self.assertEqual(self.pins.BOARD_POWER_CONTROL, 10)
        self.assertEqual(self.pins.DO_NOT_TOUCH_DURING_BOOT, {"board_power_control": 10})


if __name__ == "__main__":
    unittest.main()
