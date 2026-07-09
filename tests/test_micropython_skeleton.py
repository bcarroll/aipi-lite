"""Tests for safe MicroPython skeleton boot behavior."""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import importlib
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SRC_LIB_ROOT = SRC_ROOT / "lib"

MODULES_TO_CLEAR = ("boot", "pins")


def clear_imported_modules():
    """Remove skeleton modules so import-time boot behavior can be tested."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    for source_root in (SRC_ROOT, SRC_LIB_ROOT):
        source_path = str(source_root)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)


class MicropythonSkeletonTests(unittest.TestCase):
    """Validate boot.py safety expectations without attached hardware."""

    def tearDown(self):
        """Clean imported skeleton modules after each test."""
        clear_imported_modules()

    def test_boot_prints_safe_startup_without_machine_module(self):
        """boot.py should emit serial status without importing hardware drivers."""
        clear_imported_modules()
        ensure_src_path()
        output = StringIO()

        with redirect_stdout(output):
            boot = importlib.import_module("boot")

        self.assertIn("boot: AIPI-Lite safe startup", output.getvalue())
        self.assertIn("boot: GPIO10 board power left unchanged", output.getvalue())
        self.assertNotIn("machine", sys.modules)
        self.assertEqual(
            boot.BOOT_LINES,
            (
                "boot: AIPI-Lite safe startup",
                "boot: collecting garbage before application start",
                "boot: GPIO10 board power left unchanged",
            ),
        )

    def test_boot_source_does_not_construct_pins(self):
        """Safe boot should not instantiate MicroPython Pin objects."""
        boot_text = (SRC_ROOT / "boot.py").read_text(encoding="utf-8")

        self.assertNotIn("Pin(", boot_text)
        self.assertIn("safe_boot_startup()", boot_text)

    def test_application_root_contains_only_startup_python_files(self):
        """Only MicroPython startup files should live at the device root."""
        root_python_files = {
            path.name
            for path in SRC_ROOT.glob("*.py")
            if path.name != "local_wifi_config.py"
        }

        self.assertEqual(root_python_files, {"boot.py", "main.py"})
        self.assertTrue((SRC_LIB_ROOT / "pins.py").exists())
        self.assertTrue((SRC_LIB_ROOT / "push_to_talk.py").exists())


if __name__ == "__main__":
    unittest.main()
