"""Tests for backup and recovery documentation."""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
RECOVERY_DOC = REPO_ROOT / "RECOVERY.md"
README = REPO_ROOT / "README.md"
FIRMWARE_IMPL = REPO_ROOT / "FIRMWARE_IMPL.md"


class RecoveryDocumentationTests(unittest.TestCase):
    """Validate that feat/01 recovery procedures stay documented."""

    @classmethod
    def setUpClass(cls):
        """Load recovery-related documentation once for static assertions."""
        cls.recovery_text = RECOVERY_DOC.read_text(encoding="utf-8")
        cls.readme_text = README.read_text(encoding="utf-8")
        cls.impl_text = FIRMWARE_IMPL.read_text(encoding="utf-8")

    def test_documents_stock_backup_procedure(self):
        """Recovery docs should explain bootloader access and stock backup."""
        self.assertIn("Bootloader Mode", self.recovery_text)
        self.assertIn("Stock Firmware Backup", self.recovery_text)
        self.assertIn("read_flash 0 0x1000000", self.recovery_text)
        self.assertIn("tools/.local/backups/", self.recovery_text)
        self.assertIn("--backup-chunk-size", self.recovery_text)
        self.assertIn("1048576/16777216", self.recovery_text)
        self.assertIn("0x00100000", self.recovery_text)
        self.assertIn("4 KiB", self.recovery_text)
        self.assertIn("exactly matches `AIPI_FLASH_SIZE`", self.recovery_text)

    def test_documents_stock_restore_procedure(self):
        """Recovery docs should explain restore commands and expected signals."""
        self.assertIn("Stock Firmware Restore", self.recovery_text)
        self.assertIn("--restore-backup", self.recovery_text)
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

    def test_roadmap_and_readme_reference_recovery(self):
        """Top-level docs should point users to recovery procedures."""
        self.assertIn("[RECOVERY.md](RECOVERY.md)", self.readme_text)
        self.assertIn("exact-size backup", self.readme_text)
        self.assertIn("`feat/01-backup-recovery` | Implemented", self.impl_text)
        self.assertIn("smaller-chunk retries", self.impl_text)


if __name__ == "__main__":
    unittest.main()
