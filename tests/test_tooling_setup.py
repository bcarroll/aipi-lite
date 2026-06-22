"""Tests for setup_micropython_tools.sh static configuration."""

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = REPO_ROOT / "tools" / "setup_micropython_tools.sh"


class SetupMicropythonToolsTests(unittest.TestCase):
    """Validate declared external tooling and library downloads."""

    @classmethod
    def setUpClass(cls):
        """Load the setup script once for static assertions."""
        cls.script_text = SETUP_SCRIPT.read_text(encoding="utf-8")

    def test_downloads_are_staged_under_tools_directory(self):
        """The setup script should use tools/.local as its generated artifact root."""
        self.assertIn('TOOLS_ROOT="${SCRIPT_DIR}/.local"', self.script_text)
        self.assertIn('DOWNLOAD_DIR="${TOOLS_ROOT}/downloads/firmware"', self.script_text)
        self.assertIn('LIB_ROOT="${TOOLS_ROOT}/micropython-libs"', self.script_text)
        self.assertIn("Downloaded files are placed under tools/.local/", self.script_text)

    def test_required_host_tools_are_installed(self):
        """The setup script should install esptool and mpremote into the local venv."""
        self.assertIn('python3 -m venv "${VENV_DIR}"', self.script_text)
        self.assertIn('pip install --upgrade esptool mpremote', self.script_text)
        self.assertIn("-m esptool", self.script_text)
        self.assertIn("/bin/mpremote", self.script_text)

    def test_micropython_firmware_download_is_declared(self):
        """The setup script should download the ESP32-S3 MicroPython firmware image."""
        self.assertIn("ESP32_GENERIC_S3-20260406-v1.28.0.bin", self.script_text)
        self.assertIn("https://micropython.org/resources/firmware/", self.script_text)

    def test_required_display_libraries_are_declared(self):
        """The setup script should stage the TFT display driver bundle and license."""
        expected_destinations = {
            "lib/drivers/boolpalette.py",
            "lib/drivers/st7735r/package.json",
            "lib/drivers/st7735r/st7735r.py",
            "lib/drivers/st7735r/st7735r_4bit.py",
            "lib/drivers/st7735r/st7735r144.py",
            "lib/drivers/st7735r/st7735r144_4bit.py",
            "metadata/micropython-nano-gui-LICENSE",
        }
        actual_destinations = set(
            re.findall(r'"([^"|]+\.(?:py|json)|metadata/[^"|]+)\|https://', self.script_text)
        )

        self.assertTrue(expected_destinations.issubset(actual_destinations))
        self.assertIn("github.com/peterhinch/micropython-nano-gui", self.script_text)
        self.assertIn("Upload MicroPython libraries:", self.script_text)


if __name__ == "__main__":
    unittest.main()
