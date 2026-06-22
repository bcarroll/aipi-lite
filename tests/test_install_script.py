"""Tests for the root install.sh firmware installer."""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "install.sh"


class InstallScriptTests(unittest.TestCase):
    """Validate the installer workflow without requiring attached hardware."""

    @classmethod
    def setUpClass(cls):
        """Load the installer script once for static assertions."""
        cls.script_text = INSTALL_SCRIPT.read_text(encoding="utf-8")

    def test_resolves_latest_official_micropython_firmware(self):
        """The installer should resolve the latest stable ESP32-S3 firmware URL."""
        self.assertIn("MICROPYTHON_BOARD_URL=", self.script_text)
        self.assertIn("https://micropython.org/download/ESP32_GENERIC_S3/", self.script_text)
        self.assertIn("extract_latest_standard_firmware_url", self.script_text)
        self.assertIn("ESP32_GENERIC_S3-", self.script_text)
        self.assertIn("/resources/firmware/", self.script_text)

    def test_prompts_before_downloading_missing_components(self):
        """Missing prerequisite downloads should require explicit approval."""
        self.assertIn("collect_missing_prerequisites", self.script_text)
        self.assertIn("Download missing components and continue", self.script_text)
        self.assertIn("bash \"${SETUP_SCRIPT}\"", self.script_text)
        self.assertIn("-y|--yes", self.script_text)

    def test_flashes_firmware_at_offset_zero(self):
        """The installer should use the ESP32-S3 MicroPython offset-zero flow."""
        self.assertIn("--chip esp32s3", self.script_text)
        self.assertIn("erase_flash", self.script_text)
        self.assertIn("write_flash 0 \"${firmware_path}\"", self.script_text)
        self.assertNotIn("bootloader.bin", self.script_text)
        self.assertNotIn("partition-table.bin", self.script_text)

    def test_uploads_current_application_baseline(self):
        """The installer should copy the current app source when no app dir exists."""
        self.assertIn('${SCRIPT_DIR}/src', self.script_text)
        self.assertIn("upload_tree", self.script_text)
        self.assertNotIn('${SCRIPT_DIR}/main.py', self.script_text)
        self.assertNotIn('${SCRIPT_DIR}/aipi_lite_config.py', self.script_text)
        self.assertNotIn('${SCRIPT_DIR}/lib', self.script_text)
        self.assertIn("lib/drivers", self.script_text)


if __name__ == "__main__":
    unittest.main()
