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
        validation_text = (REPO_ROOT / "validate.cmd").read_text(encoding="utf-8")

        self.assertIn('py -3 "%HELPER%" install %*', install_text)
        self.assertIn('python "%HELPER%" install %*', install_text)
        self.assertIn('py -3 "%HELPER%" developer %*', developer_text)
        self.assertIn('python "%HELPER%" developer %*', developer_text)
        self.assertIn('py -3 "%HELPER%" validate %*', validation_text)
        self.assertIn('python "%HELPER%" validate %*', validation_text)

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

    def test_inference_capture_forces_no_reset_and_creates_redacted_issue(self):
        """Windows inference capture should publish redacted evidence after a no-reset upload."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_dir = Path(temporary_directory) / "capture"
            args = installer.create_parser().parse_args(
                [
                    "developer",
                    "--capture-dir",
                    str(capture_dir),
                    "--inference-probe",
                    "--gh",
                    "owner/repo",
                    "--device-label",
                    "bench-COM7",
                    "--inference-check",
                    "display=pass",
                    "--inference-check",
                    "status-led=pass",
                    "--inference-check",
                    "button=pass",
                    "--inference-check",
                    "offline=pass",
                    "--",
                    "--port",
                    "COM7",
                    "--yes",
                ]
            )
            sink = self.make_sink()
            received_request = None

            def simulated_install(request, install_sink):
                """Record the safe upload request and return a successful install status."""
                nonlocal received_request
                received_request = request
                install_sink.write("installer COM7 token=local-value")
                return 0

            def simulated_probe(command, probe_sink):
                """Emit representative offline probe output through the normal stream helper."""
                self.assertEqual(command[1:4], ["connect", "COM7", "exec"])
                probe_sink.write("inference_probe: elapsed_ms=751 iterations=123 checksum=456")
                probe_sink.write(
                    "inference_probe: heap_before=200000 heap_after=180000 flash_free=1048576"
                )
                probe_sink.write("inference_probe: button_polls=15 button_events=pressed,released")
                probe_sink.write("inference_probe: prompt_response=offline fixture ready")
                probe_sink.write(
                    "inference_probe: decision=candidate_supported reason=token=probe-token"
                )
                return 0

            gh_result = subprocess.CompletedProcess(
                args=["gh"],
                returncode=0,
                stdout="https://github.com/owner/repo/issues/101\n",
            )
            with (
                mock.patch.object(installer, "run_install_request", side_effect=simulated_install),
                mock.patch.object(installer, "ensure_mpremote", return_value=Path("C:/mpremote.exe")),
                mock.patch.object(installer, "run_streaming", side_effect=simulated_probe),
                mock.patch.object(installer.shutil, "which", return_value="C:/gh.exe"),
                mock.patch.object(installer.subprocess, "run", return_value=gh_result) as run,
            ):
                self.assertEqual(installer.run_developer_capture(args, sink), 0)

            self.assertIsNotNone(received_request)
            self.assertTrue(received_request.no_reset)
            issue_body = (capture_dir / "github-issue-body.md").read_text(encoding="utf-8")
            metadata = (capture_dir / "run-metadata.txt").read_text(encoding="utf-8")
            self.assertIn("Decision: `candidate_supported`", issue_body)
            self.assertIn("GPIO46 status LED updated during load: `pass`", issue_body)
            self.assertIn("<redacted-serial-port>", issue_body)
            self.assertNotIn("COM7", issue_body)
            self.assertNotIn("local-value", issue_body)
            self.assertNotIn("probe-token", issue_body)
            self.assertIn("workflow=windows-inference-validation", metadata)
            self.assertIn("inference_probe_status=0", metadata)
            self.assertIn("inference_decision=candidate_supported", metadata)
            self.assertEqual(
                (capture_dir / "github-created-issue.txt").read_text(encoding="utf-8"),
                "https://github.com/owner/repo/issues/101\n",
            )
            self.assertIn("issue", run.call_args.args[0])
            self.assertIn("create", run.call_args.args[0])
            self.assertIn("owner/repo", run.call_args.args[0])

    def test_inference_capture_requires_a_valid_probe_decision(self):
        """A successful Windows probe command without a decision should fail validation."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_dir = Path(temporary_directory) / "capture"
            args = installer.create_parser().parse_args(
                [
                    "developer",
                    "--capture-dir",
                    str(capture_dir),
                    "--inference-probe",
                    "--",
                    "--port",
                    "COM7",
                    "--yes",
                ]
            )
            sink = self.make_sink()

            def incomplete_probe(_command, probe_sink):
                """Emit probe output that lacks a required decision line."""
                probe_sink.write("inference_probe: elapsed_ms=751 iterations=123 checksum=456")
                return 0

            with (
                mock.patch.object(installer, "run_install_request", return_value=0),
                mock.patch.object(installer, "ensure_mpremote", return_value=Path("C:/mpremote.exe")),
                mock.patch.object(installer, "run_streaming", side_effect=incomplete_probe),
            ):
                self.assertEqual(installer.run_developer_capture(args, sink), 1)

            metadata = (capture_dir / "run-metadata.txt").read_text(encoding="utf-8")
            issue_body = (capture_dir / "github-issue-body.md").read_text(encoding="utf-8")
            self.assertIn("inference_probe_status=1", metadata)
            self.assertIn("inference_decision=not-reported", metadata)
            self.assertIn("Decision: `not-reported`", issue_body)

    def test_inference_capture_keeps_report_local_when_gh_is_unavailable(self):
        """An unavailable GitHub CLI should not turn a valid Windows probe into failure."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_dir = Path(temporary_directory) / "capture"
            args = installer.create_parser().parse_args(
                [
                    "developer",
                    "--capture-dir",
                    str(capture_dir),
                    "--inference-probe",
                    "--gh",
                    "owner/repo",
                    "--",
                    "--port",
                    "COM7",
                    "--yes",
                ]
            )
            sink = self.make_sink()

            def successful_probe(_command, probe_sink):
                """Emit a valid deferred decision for the offline probe."""
                probe_sink.write(
                    "inference_probe: decision=defer_inference reason=heap metric unavailable"
                )
                return 0

            with (
                mock.patch.object(installer, "run_install_request", return_value=0),
                mock.patch.object(installer, "ensure_mpremote", return_value=Path("C:/mpremote.exe")),
                mock.patch.object(installer, "run_streaming", side_effect=successful_probe),
                mock.patch.object(installer.shutil, "which", return_value=None),
            ):
                self.assertEqual(installer.run_developer_capture(args, sink), 0)

            self.assertTrue((capture_dir / "github-issue-body.md").is_file())
            self.assertFalse((capture_dir / "github-created-issue.txt").exists())
            self.assertIn("gh CLI not available", sink.transcript)

    def test_inference_capture_rejects_duplicate_operator_checks_before_upload(self):
        """Duplicate Windows inference checks should stop before device activity."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_dir = Path(temporary_directory) / "capture"
            args = installer.create_parser().parse_args(
                [
                    "developer",
                    "--capture-dir",
                    str(capture_dir),
                    "--inference-probe",
                    "--inference-check",
                    "display=pass",
                    "--inference-check",
                    "display=fail",
                    "--",
                    "--port",
                    "COM7",
                ]
            )
            sink = self.make_sink()
            with mock.patch.object(installer, "run_install_request") as run_install_request:
                self.assertEqual(installer.run_developer_capture(args, sink), 1)

            run_install_request.assert_not_called()
            self.assertIn("duplicate inference check: display", sink.transcript)

    def test_invalid_inference_capture_does_not_publish_an_issue(self):
        """Invalid inference arguments should not create an issue without a device upload."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_dir = Path(temporary_directory) / "capture"
            args = installer.create_parser().parse_args(
                [
                    "developer",
                    "--capture-dir",
                    str(capture_dir),
                    "--inference-probe",
                    "--gh",
                    "owner/repo",
                    "--",
                    "--yes",
                ]
            )
            sink = self.make_sink()
            with (
                mock.patch.object(installer, "run_install_request") as run_install_request,
                mock.patch.object(installer, "create_github_issue") as create_github_issue,
            ):
                self.assertEqual(installer.run_developer_capture(args, sink), 1)

            run_install_request.assert_not_called()
            create_github_issue.assert_not_called()
            self.assertTrue((capture_dir / "github-issue-body.md").is_file())

    def test_redaction_removes_common_sensitive_values(self):
        """Shareable artifacts should not retain common secret or hardware identifiers."""
        redacted = installer.redact_text(
            "password=hunter2 ssid=lab COM8 01:23:45:67:89:ab C:\\bench\\serial.log"
        )
        self.assertEqual(
            redacted,
            "password=<redacted> ssid=<redacted> <redacted-serial-port> "
            "<redacted-mac> <redacted-local-path>",
        )

    def test_device_validation_requires_a_com_port(self):
        """The physical validation command should not run without one COM port."""
        with mock.patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                installer.create_parser().parse_args(["validate", "--yes"])

    def test_device_validation_uploads_without_reset_and_creates_issue(self):
        """Validation should upload once, run every probe, and publish redacted evidence."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_dir = Path(temporary_directory) / "capture"
            args = installer.create_parser().parse_args(
                [
                    "validate",
                    "--capture-dir",
                    str(capture_dir),
                    "--device-label",
                    "bench-COM7",
                    "--port",
                    "COM7",
                    "--yes",
                ]
            )
            sink = self.make_sink()
            received_request = None

            def simulated_install(request, install_sink):
                """Record the upload request without using a physical device."""
                nonlocal received_request
                received_request = request
                install_sink.write("upload COM7 token=upload-secret C:\\bench\\upload.log")
                return 0

            def simulated_probe(command, probe_sink):
                """Write stable serial output for each configured validation probe."""
                probe = next(
                    item for item in installer.DEVICE_VALIDATION_PROBES if item.command == command[-1]
                )
                probe_sink.write(
                    f"{probe.serial_prefix} complete COM7 token=probe-secret C:\\bench\\serial.log"
                )
                return 0

            responses = iter(["pass"] * len(installer.DEVICE_VALIDATION_OBSERVATIONS))
            gh_result = subprocess.CompletedProcess(
                args=["gh"],
                returncode=0,
                stdout="https://github.com/owner/repo/issues/202\n",
            )
            with (
                mock.patch.object(installer, "run_install_request", side_effect=simulated_install),
                mock.patch.object(installer, "ensure_mpremote", return_value=Path("C:/mpremote.exe")),
                mock.patch.object(installer, "run_streaming", side_effect=simulated_probe) as run_streaming,
                mock.patch.object(installer, "resolve_device_validation_repository", return_value="owner/repo"),
                mock.patch.object(installer.shutil, "which", return_value="C:/gh.exe"),
                mock.patch.object(installer.subprocess, "run", return_value=gh_result) as run,
            ):
                self.assertEqual(
                    installer.run_device_validation(args, sink, input_func=lambda _prompt: next(responses)),
                    0,
                )

            self.assertIsNotNone(received_request)
            self.assertTrue(received_request.no_reset)
            self.assertEqual(
                [call.args[0][-1] for call in run_streaming.call_args_list],
                [probe.command for probe in installer.DEVICE_VALIDATION_PROBES],
            )
            issue_body = (capture_dir / "github-issue-body.md").read_text(encoding="utf-8")
            metadata = (capture_dir / "run-metadata.txt").read_text(encoding="utf-8")
            self.assertIn("Aggregate validation status: `0`", issue_body)
            self.assertIn("GPIO42 button press and release were observed: `pass`", issue_body)
            self.assertIn("inference_probe: complete", issue_body)
            self.assertNotIn("COM7", issue_body)
            self.assertNotIn("probe-secret", issue_body)
            self.assertNotIn("C:\\bench", issue_body)
            self.assertIn("workflow=windows-device-validation", metadata)
            self.assertIn("observation_speaker=pass", metadata)
            self.assertEqual(
                (capture_dir / "github-created-issue.txt").read_text(encoding="utf-8"),
                "https://github.com/owner/repo/issues/202\n",
            )
            self.assertIn("issue", run.call_args.args[0])
            self.assertIn("create", run.call_args.args[0])
            self.assertIn("owner/repo", run.call_args.args[0])

    def test_device_validation_continues_after_a_probe_failure(self):
        """One probe failure should not prevent later independent probes from running."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            args = installer.create_parser().parse_args(
                [
                    "validate",
                    "--capture-dir",
                    str(Path(temporary_directory) / "capture"),
                    "--port",
                    "COM7",
                    "--yes",
                ]
            )
            sink = self.make_sink()
            responses = iter(["pass"] * len(installer.DEVICE_VALIDATION_OBSERVATIONS))
            with (
                mock.patch.object(installer, "run_install_request", return_value=0),
                mock.patch.object(installer, "ensure_mpremote", return_value=Path("C:/mpremote.exe")),
                mock.patch.object(
                    installer,
                    "run_streaming",
                    side_effect=[0, 4, 0, 0, 0, 0],
                ) as run_streaming,
                mock.patch.object(installer, "resolve_device_validation_repository", return_value="owner/repo"),
                mock.patch.object(installer, "create_github_issue") as create_github_issue,
            ):
                self.assertEqual(
                    installer.run_device_validation(args, sink, input_func=lambda _prompt: next(responses)),
                    1,
                )

            self.assertEqual(run_streaming.call_count, len(installer.DEVICE_VALIDATION_PROBES))
            create_github_issue.assert_called_once()
            self.assertIn("inference probe exit status: 0", sink.transcript)

    def test_device_validation_records_unobserved_checks_and_keeps_report_local(self):
        """Unavailable operator input should be non-passing while retaining a report locally."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            capture_dir = Path(temporary_directory) / "capture"
            args = installer.create_parser().parse_args(
                [
                    "validate",
                    "--capture-dir",
                    str(capture_dir),
                    "--port",
                    "COM7",
                    "--yes",
                ]
            )
            sink = self.make_sink()
            with (
                mock.patch.object(installer, "run_install_request", return_value=0),
                mock.patch.object(installer, "ensure_mpremote", return_value=Path("C:/mpremote.exe")),
                mock.patch.object(installer, "run_streaming", return_value=0),
                mock.patch.object(installer, "resolve_device_validation_repository", return_value="owner/repo"),
                mock.patch.object(installer.shutil, "which", return_value=None),
            ):
                self.assertEqual(
                    installer.run_device_validation(
                        args,
                        sink,
                        input_func=lambda _prompt: (_ for _ in ()).throw(EOFError()),
                    ),
                    1,
                )

            issue_body = (capture_dir / "github-issue-body.md").read_text(encoding="utf-8")
            self.assertIn("Aggregate validation status: `1`", issue_body)
            self.assertIn("Low-volume speaker playback was audible: `not-observed`", issue_body)
            self.assertFalse((capture_dir / "github-created-issue.txt").exists())
            self.assertIn("gh CLI not available", sink.transcript)


if __name__ == "__main__":
    unittest.main()
