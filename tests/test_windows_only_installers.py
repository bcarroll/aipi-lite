"""Regression tests for the supported Windows-only installer surface."""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class WindowsOnlyInstallerTests(unittest.TestCase):
    """Protect the Windows-only installer entry-point policy."""

    def test_retired_unix_installers_are_absent(self):
        """Unix installer entry points should stay retired."""
        for name in ("install.sh", "dev_install.sh"):
            with self.subTest(name=name):
                self.assertFalse((REPO_ROOT / name).exists())

    def test_supported_windows_entrypoints_are_present(self):
        """Windows install, capture, and validation entry points should remain."""
        for name in ("install.cmd", "dev_install.cmd", "validate.cmd"):
            with self.subTest(name=name):
                self.assertTrue((REPO_ROOT / name).is_file())


if __name__ == "__main__":
    unittest.main()
