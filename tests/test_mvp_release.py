"""Tests for MVP release metadata and documentation."""

import importlib
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SRC_LIB_ROOT = SRC_ROOT / "lib"

MODULES_TO_CLEAR = ("service_contract", "version")


def clear_imported_modules():
    """Remove imported firmware modules after each test."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    for source_root in (SRC_ROOT, SRC_LIB_ROOT):
        source_path = str(source_root)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)


class MvpReleaseTests(unittest.TestCase):
    """Validate local-only MVP versioning and release docs."""

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def test_firmware_metadata_is_traceable_and_local_only(self):
        """Version metadata should identify the target and service contract."""
        clear_imported_modules()
        ensure_src_path()
        version = importlib.import_module("version")
        service_contract = importlib.import_module("service_contract")

        metadata = version.firmware_metadata(runtime_version="v1.test")

        self.assertEqual(metadata["firmware_name"], "aipi-lite")
        self.assertEqual(metadata["firmware_version"], version.FIRMWARE_VERSION)
        self.assertEqual(metadata["firmware_profile"], "local-only-mvp")
        self.assertEqual(metadata["target_model"], "XY006PL01")
        self.assertTrue(metadata["local_only"])
        self.assertEqual(metadata["service_contract"], service_contract.CONTRACT_VERSION)
        self.assertIn("local-only-mvp", version.firmware_banner())

    def test_mvp_documentation_contains_required_checklists(self):
        """MVP docs should include install, config, validation, and no-cloud checks."""
        mvp_text = (REPO_ROOT / "MVP.md").read_text(encoding="utf-8")

        for expected in (
            "Stock Backup Option",
            "MVP Install Guide",
            "MVP Configuration Guide",
            "MVP Validation Checklist",
            "Validation Report Template",
            "No-cloud network verification",
            "ESP32_GENERIC_S3 MicroPython",
            "GPIO10 board-power control",
            "Installer capture issue/link",
            "Installer bootloader verification passes",
            "but without",
        ):
            self.assertIn(expected, mvp_text)


if __name__ == "__main__":
    unittest.main()
