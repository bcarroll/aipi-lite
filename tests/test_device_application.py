"""Tests for shared AIPI-Lite device application deployment helpers."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))
import device_application as application  # noqa: E402


class FakeDeviceOS:
    """Provide the filesystem subset used by generated MicroPython cleanup code."""

    def __init__(self, files):
        """Create a fake filesystem containing the supplied device file paths."""
        self.files = set(files)
        self.directories = set()
        for file_path in self.files:
            if not file_path.startswith("/"):
                continue
            parent = file_path.rsplit("/", 1)[0]
            while parent:
                self.directories.add(parent)
                parent = parent.rsplit("/", 1)[0]

    def listdir(self, path):
        """Return direct child names for one fake directory."""
        if path not in self.directories:
            raise OSError(path)
        prefix = path.rstrip("/") + "/"
        children = set()
        for candidate in self.files | self.directories:
            if candidate.startswith(prefix):
                remainder = candidate[len(prefix) :]
                if remainder:
                    children.add(remainder.split("/", 1)[0])
        return sorted(children)

    def stat(self, path):
        """Return a MicroPython-compatible mode tuple for a fake path."""
        if path in self.directories:
            return (0x4000,)
        if path in self.files:
            return (0,)
        raise OSError(path)

    def remove(self, path):
        """Remove one fake file or raise when it does not exist."""
        if path not in self.files:
            raise OSError(path)
        self.files.remove(path)

    def rmdir(self, path):
        """Remove an empty fake directory."""
        prefix = path.rstrip("/") + "/"
        if path not in self.directories:
            raise OSError(path)
        if any(candidate.startswith(prefix) for candidate in self.files | self.directories):
            raise OSError(path)
        self.directories.remove(path)


class DeviceApplicationTests(unittest.TestCase):
    """Validate shared application manifests and guarded device cleanup code."""

    def execute_cleanup(self, manifest, fake_os):
        """Execute generated cleanup code against a fake device filesystem."""
        cleanup_code = application.application_cleanup_code(manifest)
        compile(cleanup_code, "<device-application-cleanup>", "exec")
        output = io.StringIO()
        namespace = {"os": fake_os}
        with redirect_stdout(output):
            exec(cleanup_code.replace("import os\n", "", 1), namespace)
        return output.getvalue()

    def test_manifest_excludes_host_cache_artifacts(self):
        """Application manifests should retain source while dropping host caches."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_root = Path(temporary_directory)
            (source_root / "lib" / "__pycache__").mkdir(parents=True)
            (source_root / "main.py").write_text("print('main')\n", encoding="utf-8")
            (source_root / "lib" / "pins.py").write_text("PIN = 1\n", encoding="utf-8")
            (source_root / "lib" / "module.pyc").write_bytes(b"cache")
            (source_root / "lib" / "__pycache__" / "pins.pyc").write_bytes(b"cache")
            (source_root / ".DS_Store").write_bytes(b"metadata")

            self.assertEqual(
                application.application_manifest(source_root),
                ("lib/pins.py", "main.py"),
            )

    def test_recognized_misplaced_tree_and_legacy_modules_are_removed(self):
        """Known `/src` output and legacy root modules should be removed together."""
        manifest = ("boot.py", "main.py", "lib/pins.py")
        fake_os = FakeDeviceOS(
            {
                "/src/boot.py",
                "/src/main.py",
                "/src/lib/pins.py",
                "/src/lib/__pycache__/pins.cpython-314.pyc",
                "pins.py",
                "wifi_probe.py",
            }
        )

        output = self.execute_cleanup(manifest, fake_os)

        self.assertNotIn("/src", fake_os.directories)
        self.assertNotIn("pins.py", fake_os.files)
        self.assertNotIn("wifi_probe.py", fake_os.files)
        self.assertIn("removed misplaced application tree: /src", output)
        self.assertIn(application.CLEANUP_COMPLETE_MARKER, output)

    def test_unknown_misplaced_tree_content_is_preserved(self):
        """An unknown file should preserve the complete `/src` tree."""
        manifest = ("boot.py", "main.py", "lib/pins.py")
        original_files = {
            "/src/boot.py",
            "/src/main.py",
            "/src/lib/pins.py",
            "/src/operator-notes.txt",
        }
        fake_os = FakeDeviceOS(original_files)

        output = self.execute_cleanup(manifest, fake_os)

        self.assertEqual(fake_os.files, original_files)
        self.assertIn("/src", fake_os.directories)
        self.assertIn("preserved /src because it contains unknown device files", output)
        self.assertIn(application.CLEANUP_COMPLETE_MARKER, output)

    def test_cleanup_cli_prints_compilable_code(self):
        """The Unix-facing CLI should emit cleanup code from a valid source tree."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            source_root = Path(temporary_directory)
            (source_root / "lib").mkdir()
            (source_root / "boot.py").write_text("print('boot')\n", encoding="utf-8")
            (source_root / "main.py").write_text("print('main')\n", encoding="utf-8")
            (source_root / "lib" / "pins.py").write_text("PIN = 1\n", encoding="utf-8")
            output = io.StringIO()

            with redirect_stdout(output):
                self.assertEqual(application.main(["--source", str(source_root)]), 0)

            compile(output.getvalue(), "<cleanup-cli>", "exec")
            self.assertIn(application.CLEANUP_COMPLETE_MARKER, output.getvalue())


if __name__ == "__main__":
    unittest.main()
