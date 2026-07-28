"""Tests for backup and recovery documentation."""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
RECOVERY_DOC = REPO_ROOT / "RECOVERY.md"
README = REPO_ROOT / "README.md"
FIRMWARE_IMPL = REPO_ROOT / "FIRMWARE_IMPL.md"


class RecoveryDocumentationTests(unittest.TestCase):
    """Validate the Windows-only, flash-capable recovery procedures stay documented."""

    @classmethod
    def setUpClass(cls):
        """Load recovery-related documentation once for static assertions."""
        cls.recovery_text = RECOVERY_DOC.read_text(encoding="utf-8")
        cls.readme_text = README.read_text(encoding="utf-8")
        cls.impl_text = FIRMWARE_IMPL.read_text(encoding="utf-8")

    def test_documents_windows_firmware_flashing(self):
        """Recovery docs should explain Windows SPIRAM_OCT firmware flashing."""
        self.assertIn("Bootloader Mode", self.recovery_text)
        self.assertIn("MicroPython Firmware Flashing", self.recovery_text)
        self.assertIn("install.cmd --port COM3 --flash-micropython --yes", self.recovery_text)
        self.assertIn("ESP32_GENERIC_S3-SPIRAM_OCT", self.recovery_text)
        self.assertIn("8 MB of Octal PSRAM", self.recovery_text)
        self.assertIn("Wifi Out of Memory", self.recovery_text)
        self.assertIn("--firmware-url", self.recovery_text)
        self.assertIn("--skip-erase", self.recovery_text)

    def test_documents_manual_stock_backup_procedure(self):
        """Recovery docs should explain the manual, out-of-band stock backup."""
        self.assertIn("Stock Firmware Backup (manual only)", self.recovery_text)
        self.assertIn("not automated by the repository scripts", self.recovery_text)
        self.assertIn("read-flash 0 0x1000000", self.recovery_text)
        self.assertIn("tools/.local/backups/", self.recovery_text)
        self.assertIn("16777216", self.recovery_text)
        self.assertIn("1048576/16777216", self.recovery_text)
        self.assertIn("Expected backup indicators", self.recovery_text)

    def test_documents_manual_stock_restore_procedure(self):
        """Recovery docs should explain manual restore commands and expected signals."""
        self.assertIn("Stock Firmware Restore (manual only)", self.recovery_text)
        self.assertIn("erase_flash", self.recovery_text)
        self.assertIn("write_flash 0", self.recovery_text)
        self.assertIn("Expected restore indicators", self.recovery_text)
        self.assertIn("MicroPython banner", self.recovery_text)

    def test_documents_flashing_safety_checklist(self):
        """Recovery docs should include the required flashing safety checklist."""
        self.assertIn("Flashing Safety Checklist", self.recovery_text)
        self.assertIn("stable USB power", self.recovery_text)
        self.assertIn("SPEC.md", self.recovery_text)
        self.assertIn("public cloud", self.recovery_text)
        self.assertIn("not staged in Git", self.recovery_text)
        self.assertIn("stock firmware recovery may be unavailable", self.recovery_text)
        self.assertIn("upload-only install path", self.recovery_text)

    def test_roadmap_and_readme_reference_recovery(self):
        """Top-level docs should point users to Windows recovery procedures."""
        self.assertIn("[RECOVERY.md](RECOVERY.md)", self.readme_text)
        self.assertIn("install.cmd --port COM3 --flash-micropython --yes", self.readme_text)
        self.assertIn("ESP32_GENERIC_S3-SPIRAM_OCT", self.readme_text)
        self.assertIn("Wifi Out of Memory", self.readme_text)
        self.assertIn("`feat/01-backup-recovery` | Retired Unix workflow", self.impl_text)
        self.assertIn("install.cmd --flash-micropython", self.impl_text)


if __name__ == "__main__":
    unittest.main()
