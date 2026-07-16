"""Tests for the Windows-native AIPI-Lite installation entry points."""

from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS_DIR))
import windows_installer as installer  # noqa: E402


class WindowsInstallerTests(unittest.TestCase):
    """Validate application-first Windows upload and capture behavior."""

    def make_sink(self):
        """Create an isolated output sink for a host-side test."""
        return installer.OutputSink(io.StringIO(), io.StringIO())

    def test_cmd_entry_points_delegate_to_the_python_helper(self):
        """The native CMD files should locate Python and select the expected command."""
        install_text = (REPO_ROOT / "install.cmd").read_text(encoding="utf-8")
        developer_text = (REPO_ROOT / "dev_install.cmd").read_text(encoding="utf-8")

        self.assertIn('py -3 "%HELPER%" install %*', install_text)
        self.assertIn('python "%HELPER%" install %*', install_text)
        self.assertIn('py -3 "%HELPER%" developer %*', developer_text)
        self.assertIn('python "%HELPER%" developer %*', developer_text)

    def test_normalizes_valid_com_port_and_rejects_non_windows_port(self):
        """Only Windows COM port names should enter the upload workflow."""
        self.assertEqual(installer.normalize_com_port(" com17 "), "COM17")
        with self.assertRaisesRegex(installer.InstallerError, "COM port"):
            installer.normalize_com_port("/dev/ttyUSB0")

    def test_lists_ports_from_windows_serial_registry(self):
        """Port discovery should use the Windows registry without a new dependency."""
        result = subprocess.CompletedProcess(
            args=["reg"],
            returncode=0,
            stdout="  \\Device\\Serial0    REG_SZ    COM7\\n  \\Device\\Serial1    REG_SZ    com12\\n",
        )
        with (
            mock.patch.object(installer.os, "name", "nt"),
            mock.patch.object(installer.subprocess, "run", return_value=result),
        ):
            self.assertEqual(installer.list_windows_serial_ports(), ["COM12", "COM7"])

    def test_upload_runs_copy_then_reset(self):
        """A successful application-first install should copy src and reset once."""
        executable = Path("C:/local/mpremote.exe")
        request = installer.InstallRequest(port="COM7", no_reset=False, assume_yes=True)
        sink = self.make_sink()
        with (
            mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM7"]),
            mock.patch.object(installer, "ensure_mpremote", return_value=executable),
            mock.patch.object(installer, "run_streaming", side_effect=[0, 0]) as run_streaming,
        ):
            self.assertEqual(installer.run_install_request(request, sink), 0)

        self.assertEqual(
            run_streaming.call_args_list,
            [
                mock.call(
                    [
                        str(executable),
                        "connect",
                        "COM7",
                        "fs",
                        "cp",
                        "-r",
                        f"{installer.SRC_DIR}{installer.os.sep}",
                        ":",
                    ],
                    sink,
                ),
                mock.call([str(executable), "connect", "COM7", "reset"], sink),
            ],
        )
        self.assertIn("Application upload complete.", sink.transcript)

    def test_upload_failure_does_not_reset_device(self):
        """A failed copy should preserve the device state by skipping reset."""
        request = installer.InstallRequest(port="COM7", no_reset=False, assume_yes=True)
        sink = self.make_sink()
        with (
            mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM7"]),
            mock.patch.object(installer, "ensure_mpremote", return_value=Path("mpremote.exe")),
            mock.patch.object(installer, "run_streaming", return_value=9) as run_streaming,
        ):
            self.assertEqual(installer.run_install_request(request, sink), 9)

        self.assertEqual(run_streaming.call_count, 1)
        self.assertIn("Application upload failed with status 9.", sink.transcript)

    def test_unknown_requested_port_stops_before_tool_setup(self):
        """An unavailable COM port should not create tools or touch the device."""
        request = installer.InstallRequest(port="COM9", no_reset=False, assume_yes=True)
        sink = self.make_sink()
        with (
            mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM7"]),
            mock.patch.object(installer, "ensure_mpremote") as ensure_mpremote,
        ):
            with self.assertRaisesRegex(installer.InstallerError, "COM9"):
                installer.run_install_request(request, sink)
        ensure_mpremote.assert_not_called()

    def test_developer_capture_stores_raw_and_redacted_artifacts(self):
        """The developer workflow should preserve local raw output and redact shareable output."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_dir = Path(temporary_directory) / "capture"
            args = installer.create_parser().parse_args(
                [
                    "developer",
                    "--capture-dir",
                    str(capture_dir),
                    "--device-label",
                    "bench-token=private",
                    "--hardware-note",
                    "serial LED observed on COM7",
                    "--",
                    "--port",
                    "COM7",
                    "--yes",
                ]
            )
            sink = self.make_sink()

            def simulated_install(request, install_sink):
                """Write representative sensitive output and return an install failure."""
                self.assertEqual(request.port, "COM7")
                install_sink.write("device COM7 token=local-value aa:bb:cc:dd:ee:ff")
                return 7

            with mock.patch.object(installer, "run_install_request", side_effect=simulated_install):
                self.assertEqual(installer.run_developer_capture(args, sink), 7)

            raw = (capture_dir / "install-transcript-raw.txt").read_text(encoding="utf-8")
            redacted = (capture_dir / "install-transcript-redacted.txt").read_text(
                encoding="utf-8"
            )
            metadata = (capture_dir / "run-metadata.txt").read_text(encoding="utf-8")
            self.assertIn("token=local-value", raw)
            self.assertIn("COM7", raw)
            self.assertNotIn("local-value", redacted)
            self.assertNotIn("COM7", redacted)
            self.assertIn("token=<redacted>", redacted)
            self.assertIn("<redacted-serial-port>", redacted)
            self.assertIn("<redacted-mac>", redacted)
            self.assertIn("installer_exit_status=7", metadata)
            self.assertNotIn("private", metadata)
            self.assertNotIn("COM7", metadata)

    def test_prepare_only_creates_artifacts_without_an_install(self):
        """Preparation-only capture should remain local and avoid device interaction."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_dir = Path(temporary_directory) / "capture"
            args = installer.create_parser().parse_args(
                ["developer", "--capture-dir", str(capture_dir), "--prepare-only"]
            )
            sink = self.make_sink()
            with mock.patch.object(installer, "run_install_request") as run_install_request:
                self.assertEqual(installer.run_developer_capture(args, sink), 0)

            run_install_request.assert_not_called()
            self.assertTrue((capture_dir / "install-transcript-raw.txt").is_file())
            self.assertTrue((capture_dir / "install-transcript-redacted.txt").is_file())
            metadata = (capture_dir / "run-metadata.txt").read_text(encoding="utf-8")
            self.assertIn("prepared_only=yes", metadata)
            self.assertIn("installer_exit_status=not-run", metadata)

    def test_redaction_removes_common_sensitive_values(self):
        """Shareable artifacts should not retain common secret or hardware identifiers."""
        redacted = installer.redact_text(
            "password=hunter2 ssid=lab COM8 01:23:45:67:89:ab"
        )
        self.assertEqual(
            redacted,
            "password=<redacted> ssid=<redacted> <redacted-serial-port> <redacted-mac>",
        )


if __name__ == "__main__":
    unittest.main()
