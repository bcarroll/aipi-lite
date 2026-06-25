"""Tests for setup_micropython_tools.sh static configuration."""

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = REPO_ROOT / "tools" / "setup_micropython_tools.sh"
SRC_LIB = REPO_ROOT / "src" / "lib"


class SetupMicropythonToolsTests(unittest.TestCase):
    """Validate declared external tooling and library downloads."""

    @classmethod
    def setUpClass(cls):
        """Load the setup script once for static assertions."""
        cls.script_text = SETUP_SCRIPT.read_text(encoding="utf-8")

    def test_host_downloads_and_libraries_use_separate_roots(self):
        """The setup script should keep host artifacts local and libraries in src/lib."""
        self.assertIn('TOOLS_ROOT="${SCRIPT_DIR}/.local"', self.script_text)
        self.assertIn('DOWNLOAD_DIR="${TOOLS_ROOT}/downloads/firmware"', self.script_text)
        self.assertIn('APP_DIR="${REPO_ROOT}/src"', self.script_text)
        self.assertIn('LIB_ROOT="${APP_DIR}/lib"', self.script_text)
        self.assertIn("MicroPython library source is staged under src/lib", self.script_text)
        self.assertNotIn('TOOLS_ROOT}/micropython-libs', self.script_text)

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

    def test_downloads_have_python_fallback(self):
        """The setup script should download with Python if curl and wget are unavailable."""
        self.assertIn("from urllib.request import urlopen", self.script_text)
        self.assertIn("output_path.write_bytes(response.read())", self.script_text)

    def test_legacy_checked_in_binary_flow_is_not_used(self):
        """The setup script should avoid the removed checked-in firmware image flow."""
        self.assertNotIn("bootloader.bin", self.script_text)
        self.assertNotIn("partition-table.bin", self.script_text)
        self.assertNotIn("micropython.bin", self.script_text)
        self.assertIn("write_flash 0 ${firmware_path}", self.script_text)

    def test_required_display_libraries_are_declared(self):
        """The setup script should stage the TFT display driver bundle and license."""
        expected_destinations = {
            "drivers/boolpalette.py",
            "drivers/st7735r/package.json",
            "drivers/st7735r/st7735r.py",
            "drivers/st7735r/st7735r_4bit.py",
            "drivers/st7735r/st7735r144.py",
            "drivers/st7735r/st7735r144_4bit.py",
            "metadata/micropython-nano-gui-LICENSE",
        }
        actual_destinations = set(
            re.findall(r'"([^"|]+\.(?:py|json)|metadata/[^"|]+)\|https://', self.script_text)
        )

        self.assertTrue(expected_destinations.issubset(actual_destinations))
        self.assertIn("github.com/peterhinch/micropython-nano-gui", self.script_text)
        self.assertIn("The application upload includes MicroPython libraries", self.script_text)
        self.assertNotIn("Upload MicroPython libraries:", self.script_text)

    def test_required_display_libraries_are_tracked_under_src_lib(self):
        """The external display library bundle should live in src/lib."""
        expected_paths = {
            SRC_LIB / "drivers" / "boolpalette.py",
            SRC_LIB / "drivers" / "st7735r" / "package.json",
            SRC_LIB / "drivers" / "st7735r" / "st7735r.py",
            SRC_LIB / "drivers" / "st7735r" / "st7735r_4bit.py",
            SRC_LIB / "drivers" / "st7735r" / "st7735r144.py",
            SRC_LIB / "drivers" / "st7735r" / "st7735r144_4bit.py",
            SRC_LIB / "metadata" / "micropython-nano-gui-LICENSE",
            SRC_LIB / "AIPI-LITE-MICROPYTHON-LIBRARIES.md",
        }

        for path in sorted(expected_paths):
            self.assertTrue(path.is_file(), f"{path} should be tracked under src/lib")


if __name__ == "__main__":
    unittest.main()
