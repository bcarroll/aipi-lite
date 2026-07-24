"""Tests for the Windows-native AIPI-Lite installation entry points."""

from __future__ import annotations

import contextlib
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

    def test_config_update_is_atomic_and_preserves_unrelated_lines(self):
        """Updating the saved port should preserve all unrelated installer answers."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"
            conf_file.write_text(
                "# local installer answers\n"
                "AIPI_SERIAL_PORT=COM3\n"
                "AIPI_RESET_AFTER_UPLOAD=no\n"
                "\n"
                "AIPI_SERIAL_PORT=COM4\n",
                encoding="utf-8",
            )

            installer.write_config_value(conf_file, "AIPI_SERIAL_PORT", "COM7")

            self.assertEqual(
                conf_file.read_text(encoding="utf-8"),
                "# local installer answers\n"
                "AIPI_SERIAL_PORT=COM7\n"
                "AIPI_RESET_AFTER_UPLOAD=no\n"
                "\n"
                "AIPI_SERIAL_PORT=COM7\n",
            )
            self.assertEqual(
                installer.read_config_value(conf_file, "AIPI_SERIAL_PORT"),
                "COM7",
            )
            self.assertEqual(list(conf_file.parent.glob(".conf.tmp.*")), [])

    def test_config_write_failure_preserves_original_file(self):
        """A failed atomic replacement should leave the existing config unchanged."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"
            original = "AIPI_SERIAL_PORT=COM3\nAIPI_RESET_AFTER_UPLOAD=yes\n"
            conf_file.write_text(original, encoding="utf-8")

            with mock.patch.object(installer.os, "replace", side_effect=OSError("simulated")):
                with self.assertRaises(OSError):
                    installer.write_config_value(conf_file, "AIPI_SERIAL_PORT", "COM7")

            self.assertEqual(conf_file.read_text(encoding="utf-8"), original)
            self.assertEqual(list(conf_file.parent.glob(".conf.tmp.*")), [])

    def test_config_update_preserves_windows_line_endings(self):
        """Updating a Windows-created config should retain CRLF line endings."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"
            conf_file.write_bytes(
                b"AIPI_SERIAL_PORT=COM3\r\nAIPI_RESET_AFTER_UPLOAD=yes\r\n"
            )

            installer.write_config_value(conf_file, "AIPI_SERIAL_PORT", "COM7")

            self.assertEqual(
                conf_file.read_bytes(),
                b"AIPI_SERIAL_PORT=COM7\r\nAIPI_RESET_AFTER_UPLOAD=yes\r\n",
            )

    def test_direct_install_port_precedence_prefers_explicit_then_saved(self):
        """An explicit port should override config, while omission should reuse config."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"
            conf_file.write_text("AIPI_SERIAL_PORT=COM7\n", encoding="utf-8")

            explicit = installer.resolve_direct_install_port(
                "com9",
                conf_file=conf_file,
                detected_ports=["COM7", "COM9"],
            )
            saved = installer.resolve_direct_install_port(
                None,
                conf_file=conf_file,
                detected_ports=["COM7", "COM9"],
            )

            self.assertEqual(
                (explicit.port, explicit.source, explicit.persist),
                ("COM9", "explicit", True),
            )
            self.assertEqual(
                (saved.port, saved.source, saved.persist),
                ("COM7", "saved", False),
            )

    def test_direct_install_auto_selects_one_port_for_missing_empty_or_auto_config(self):
        """One detected COM port should satisfy every no-saved-port first-run form."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"
            for configured_value in (None, "", "auto"):
                with self.subTest(configured_value=configured_value):
                    conf_file.unlink(missing_ok=True)
                    if configured_value is not None:
                        conf_file.write_text(
                            "AIPI_SERIAL_PORT={}\n".format(configured_value),
                            encoding="utf-8",
                        )

                    selection = installer.resolve_direct_install_port(
                        None,
                        conf_file=conf_file,
                        detected_ports=["COM12"],
                    )

                    self.assertEqual(
                        (selection.port, selection.source, selection.persist),
                        ("COM12", "detected", True),
                    )

    def test_direct_install_requires_explicit_port_for_zero_or_multiple_ports(self):
        """Ambiguous first-run discovery should stop without changing config."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"

            with self.assertRaisesRegex(installer.InstallerError, "connect the AIPI-Lite"):
                installer.resolve_direct_install_port(
                    None,
                    conf_file=conf_file,
                    detected_ports=[],
                )
            with self.assertRaisesRegex(installer.InstallerError, "COM7, COM9"):
                installer.resolve_direct_install_port(
                    None,
                    conf_file=conf_file,
                    detected_ports=["COM7", "COM9"],
                )

            self.assertFalse(conf_file.exists())

    def test_direct_install_rejects_invalid_or_stale_saved_port(self):
        """Saved-port errors should require explicit correction instead of switching devices."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"
            conf_file.write_text("AIPI_SERIAL_PORT=not-a-port\n", encoding="utf-8")

            with self.assertRaisesRegex(installer.InstallerError, "AIPI_SERIAL_PORT"):
                installer.resolve_direct_install_port(
                    None,
                    conf_file=conf_file,
                    detected_ports=["COM9"],
                )

            conf_file.write_text("AIPI_SERIAL_PORT=COM7\n", encoding="utf-8")
            with self.assertRaisesRegex(installer.InstallerError, "saved port COM7"):
                installer.resolve_direct_install_port(
                    None,
                    conf_file=conf_file,
                    detected_ports=["COM9"],
                )

            self.assertEqual(
                conf_file.read_text(encoding="utf-8"),
                "AIPI_SERIAL_PORT=COM7\n",
            )

    def test_direct_install_persists_explicit_port_before_failed_upload(self):
        """A validated explicit selection should survive a later upload failure."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"
            conf_file.write_text("AIPI_RESET_AFTER_UPLOAD=yes\n", encoding="utf-8")
            args = installer.create_parser().parse_args(
                ["install", "--port", "com9", "--yes"]
            )
            sink = self.make_sink()

            with (
                mock.patch.object(installer, "CONF_FILE", conf_file),
                mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM9"]),
                mock.patch.object(installer, "run_install_request", return_value=7) as run_install,
            ):
                self.assertEqual(installer.run_install_command(args, sink), 7)

            request = run_install.call_args.args[0]
            self.assertEqual(request.port, "COM9")
            saved_config = conf_file.read_text(encoding="utf-8")
            self.assertIn("AIPI_RESET_AFTER_UPLOAD=yes", saved_config)
            self.assertIn("AIPI_SERIAL_PORT=COM9", saved_config)

    def test_direct_install_persists_one_auto_detected_port(self):
        """A first direct install should save its sole detected COM port."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"
            args = installer.create_parser().parse_args(["install", "--yes"])
            sink = self.make_sink()

            with (
                mock.patch.object(installer, "CONF_FILE", conf_file),
                mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM12"]),
                mock.patch.object(installer, "run_install_request", return_value=0) as run_install,
            ):
                self.assertEqual(installer.run_install_command(args, sink), 0)

            self.assertEqual(run_install.call_args.args[0].port, "COM12")
            self.assertEqual(
                conf_file.read_text(encoding="utf-8"),
                "AIPI_SERIAL_PORT=COM12\n",
            )
            self.assertIn("saved to .conf", sink.transcript)

    def test_direct_install_stops_before_upload_when_config_write_fails(self):
        """A persistence failure should stop before prerequisites or device changes."""
        args = installer.create_parser().parse_args(
            ["install", "--port", "COM7", "--yes"]
        )
        sink = self.make_sink()

        with (
            mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM7"]),
            mock.patch.object(installer, "write_config_value", side_effect=OSError("simulated")),
            mock.patch.object(installer, "run_install_request") as run_install,
        ):
            self.assertEqual(installer.run_install_command(args, sink), 1)

        run_install.assert_not_called()
        self.assertIn("error: simulated", sink.transcript)

    def test_direct_install_list_ports_does_not_modify_config(self):
        """The Windows port diagnostic should remain read-only."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            conf_file = Path(temporary_directory) / ".conf"
            original = "AIPI_SERIAL_PORT=COM7\n"
            conf_file.write_text(original, encoding="utf-8")
            args = installer.create_parser().parse_args(["install", "--list-ports"])
            sink = self.make_sink()

            with (
                mock.patch.object(installer, "CONF_FILE", conf_file),
                mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM9"]),
            ):
                self.assertEqual(installer.run_install_command(args, sink), 0)

            self.assertEqual(conf_file.read_text(encoding="utf-8"), original)

    def test_developer_install_request_still_requires_an_explicit_port(self):
        """Direct-install persistence should not relax developer capture targeting."""
        with self.assertRaisesRegex(installer.InstallerError, "--port COMx is required"):
            installer.install_request_from_args(["--yes"])

    def test_upload_runs_copy_then_reset(self):
        """A successful install should copy, remove legacy root modules, and reset."""
        executable = Path("C:/local/mpremote.exe")
        request = installer.InstallRequest(port="COM7", no_reset=False, assume_yes=True)
        sink = self.make_sink()

        def successful_command(command, output_sink):
            """Complete each command and emit the cleanup confirmation marker."""
            if "exec" in command:
                output_sink.write(installer.CLEANUP_COMPLETE_MARKER)
            return 0

        with (
            mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM7"]),
            mock.patch.object(installer, "ensure_mpremote", return_value=executable),
            mock.patch.object(installer, "run_streaming", side_effect=successful_command) as run_streaming,
        ):
            self.assertEqual(installer.run_install_request(request, sink), 0)

        self.assertEqual(run_streaming.call_count, 2)
        upload_command = run_streaming.call_args_list[0].args[0]
        self.assertEqual(upload_command[:6], [str(executable), "connect", "COM7", "fs", "cp", "-r"])
        self.assertEqual(upload_command[-1], ":/")
        uploaded_names = {Path(path).name for path in upload_command[6:-1]}
        self.assertTrue({"boot.py", "main.py", "lib"}.issubset(uploaded_names))
        self.assertNotIn("src", uploaded_names)

        cleanup_command = run_streaming.call_args_list[1].args[0]
        self.assertEqual(cleanup_command[:4], [str(executable), "connect", "COM7", "exec"])
        self.assertEqual(cleanup_command[-1], "reset")
        self.assertIn("Cleaning legacy and misplaced application files", sink.transcript)
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

    def test_preflight_reset_upload_failure_stops_before_cleanup(self):
        """A failed validation preflight upload should not run cleanup or device probes."""
        executable = Path("C:/local/mpremote.exe")
        request = installer.InstallRequest(
            port="COM7",
            no_reset=True,
            assume_yes=True,
            preflight_reset=True,
        )
        sink = self.make_sink()
        with (
            mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM7"]),
            mock.patch.object(installer, "ensure_mpremote", return_value=executable),
            mock.patch.object(installer, "run_streaming", return_value=9) as run_streaming,
        ):
            self.assertEqual(installer.run_install_request(request, sink), 9)

        self.assertEqual(run_streaming.call_count, 1)
        upload_command = run_streaming.call_args.args[0]
        self.assertEqual(
            upload_command[:9],
            [
                str(executable),
                "connect",
                "COM7",
                "reset",
                "sleep",
                installer.VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS,
                "fs",
                "cp",
                "-r",
            ],
        )
        self.assertIn("Hard-resetting COM7", sink.transcript)
        self.assertIn("Application upload failed with status 9.", sink.transcript)
        self.assertNotIn("Cleaning legacy and misplaced application files", sink.transcript)
        self.assertEqual(upload_command[-1], ":/")

    def test_legacy_module_cleanup_failure_does_not_reset_device(self):
        """A failed legacy cleanup should stop before resetting into shadowed modules."""
        executable = Path("C:/local/mpremote.exe")
        request = installer.InstallRequest(port="COM7", no_reset=False, assume_yes=True)
        sink = self.make_sink()
        with (
            mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM7"]),
            mock.patch.object(installer, "ensure_mpremote", return_value=executable),
            mock.patch.object(installer, "run_streaming", side_effect=[0, 7]) as run_streaming,
        ):
            self.assertEqual(installer.run_install_request(request, sink), 7)

        self.assertEqual(run_streaming.call_count, 2)
        self.assertIn("cleanup failed with status 7", sink.transcript)

    def test_legacy_cleanup_targets_only_modules_moved_under_lib(self):
        """The cleanup command should preserve boot, main, and local Wi-Fi config."""
        manifest = ("boot.py", "main.py", "lib/pins.py")
        command = installer.application_cleanup_command(
            Path("mpremote.exe"),
            "COM7",
            manifest,
            reset=False,
        )
        cleanup_code = command[-1]

        compile(cleanup_code, "<legacy-root-cleanup>", "exec")
        self.assertIn("push_to_talk.py", cleanup_code)
        self.assertIn("wifi_probe.py", cleanup_code)
        self.assertNotIn("boot.py", installer.LEGACY_ROOT_MODULES)
        self.assertNotIn("main.py", installer.LEGACY_ROOT_MODULES)
        self.assertNotIn("local_wifi_config.py", installer.LEGACY_ROOT_MODULES)

    def test_staging_filters_host_caches_and_exposes_root_children(self):
        """Windows staging should exclude caches and upload source children, not `src`."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = Path(temporary_directory)
            source_root = temporary_root / "src"
            destination = temporary_root / "staged" / "application"
            (source_root / "lib" / "__pycache__").mkdir(parents=True)
            (source_root / "boot.py").write_text("print('boot')\n", encoding="utf-8")
            (source_root / "main.py").write_text("print('main')\n", encoding="utf-8")
            (source_root / "local_wifi_config.py").write_text(
                "WIFI_SSID = 'local'\n",
                encoding="utf-8",
            )
            (source_root / "lib" / "pins.py").write_text("PIN = 1\n", encoding="utf-8")
            (source_root / "lib" / "__pycache__" / "pins.pyc").write_bytes(b"cache")

            with mock.patch.object(installer, "SRC_DIR", source_root):
                sources, manifest = installer.stage_application_source(destination)

            self.assertEqual(
                {path.name for path in sources},
                {"boot.py", "main.py", "lib", "local_wifi_config.py"},
            )
            self.assertEqual(
                manifest,
                ("boot.py", "lib/pins.py", "local_wifi_config.py", "main.py"),
            )
            self.assertFalse((destination / "lib" / "__pycache__").exists())

    def test_reset_failure_after_cleanup_warns_and_returns_success(self):
        """A reset-only failure should require a power cycle without failing install."""
        executable = Path("C:/local/mpremote.exe")
        request = installer.InstallRequest(port="COM7", no_reset=False, assume_yes=True)
        sink = self.make_sink()

        def reset_failure(command, output_sink):
            """Succeed at upload, then confirm cleanup before reset failure."""
            if "exec" in command:
                output_sink.write(installer.CLEANUP_COMPLETE_MARKER)
                return 7
            return 0

        with (
            mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM7"]),
            mock.patch.object(installer, "ensure_mpremote", return_value=executable),
            mock.patch.object(installer, "run_streaming", side_effect=reset_failure),
        ):
            self.assertEqual(installer.run_install_request(request, sink), 0)

        self.assertIn("automatic reset could not be confirmed", sink.transcript)
        self.assertIn("unplugging and reconnecting USB-C", sink.transcript)

    def test_no_reset_runs_cleanup_without_reset_command(self):
        """A no-reset upload should still clean misplaced and legacy files."""
        executable = Path("C:/local/mpremote.exe")
        request = installer.InstallRequest(port="COM7", no_reset=True, assume_yes=True)
        sink = self.make_sink()

        def successful_command(command, output_sink):
            """Complete upload and cleanup while emitting the cleanup marker."""
            if "exec" in command:
                output_sink.write(installer.CLEANUP_COMPLETE_MARKER)
            return 0

        with (
            mock.patch.object(installer, "list_windows_serial_ports", return_value=["COM7"]),
            mock.patch.object(installer, "ensure_mpremote", return_value=executable),
            mock.patch.object(installer, "run_streaming", side_effect=successful_command) as run_streaming,
        ):
            self.assertEqual(installer.run_install_request(request, sink), 0)

        cleanup_command = run_streaming.call_args_list[1].args[0]
        self.assertNotEqual(cleanup_command[-1], "reset")
        self.assertIn("reset skipped by --no-reset", sink.transcript)

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

    def test_upload_failure_diagnostics_are_redacted_and_bounded(self):
        """Upload issue diagnostics should keep only bounded, redacted signal lines."""
        transcript_lines = [
            "Hard-resetting COM8 and waiting 1.0 seconds before validation upload...",
            "Uploading application source to COM8...",
            "cp C:\\Users\\Brett\\AppData\\Local\\Temp\\application\\README.md :",
            "Traceback (most recent call last):",
            "mpremote: cp: destination does not exist",
            "mpremote.transport.TransportError: token=upload-secret COM8 C:\\bench\\serial.log",
            "error: password=hunter2",
            "mpremote: cp: destination does not exist",
        ]
        transcript_lines.extend(f"mpremote: failure-{index}" for index in range(20))

        diagnostics = installer.device_validation_upload_failure_lines(
            "\n".join(transcript_lines)
        )

        self.assertEqual(len(diagnostics), installer.MAX_UPLOAD_FAILURE_DIAGNOSTIC_LINES)
        self.assertEqual(
            diagnostics[:5],
            [
                "Hard-resetting <redacted-serial-port> and waiting 1.0 seconds before validation upload...",
                "Uploading application source to <redacted-serial-port>...",
                "mpremote: cp: destination does not exist",
                "mpremote.transport.TransportError: token=<redacted> "
                "<redacted-serial-port> <redacted-local-path>",
                "error: password=<redacted>",
            ],
        )
        self.assertNotIn("cp C:\\Users", "\n".join(diagnostics))
        self.assertNotIn("Traceback", "\n".join(diagnostics))
        self.assertEqual(diagnostics.count("mpremote: cp: destination does not exist"), 1)

    def test_upload_failure_issue_includes_diagnostics_but_success_does_not(self):
        """Only nonzero upload reports should contain redacted failure diagnostics."""
        failure_sink = self.make_sink()
        failure_sink.write("Hard-resetting COM8 and waiting 1.0 seconds before validation upload...")
        failure_sink.write("mpremote: cp: destination does not exist")
        failure_sink.write("Application upload failed with status 1.")
        success_sink = self.make_sink()
        success_sink.write("display_probe: complete")
        empty_failure_sink = self.make_sink()
        empty_failure_sink.write("unrelated host output")

        with tempfile.TemporaryDirectory() as temporary_directory:
            failure_issue = Path(temporary_directory) / "failure.md"
            success_issue = Path(temporary_directory) / "success.md"
            empty_failure_issue = Path(temporary_directory) / "empty-failure.md"
            kwargs = {
                "device_label": "bench-COM8",
                "batch_status": None,
                "probe_statuses": (),
                "observations": {},
                "validation_status": 1,
            }
            installer.write_device_validation_issue_body(
                failure_issue,
                sink=failure_sink,
                upload_status=1,
                **kwargs,
            )
            installer.write_device_validation_issue_body(
                success_issue,
                sink=success_sink,
                upload_status=0,
                **kwargs,
            )
            installer.write_device_validation_issue_body(
                empty_failure_issue,
                sink=empty_failure_sink,
                upload_status=1,
                **kwargs,
            )

            failure_body = failure_issue.read_text(encoding="utf-8")
            success_body = success_issue.read_text(encoding="utf-8")
            empty_failure_body = empty_failure_issue.read_text(encoding="utf-8")

        self.assertIn("## Redacted Upload Failure Diagnostics", failure_body)
        self.assertIn("mpremote: cp: destination does not exist", failure_body)
        self.assertNotIn("COM8", failure_body)
        self.assertLess(
            failure_body.index("## Redacted Upload Failure Diagnostics"),
            failure_body.index("## Redacted Device Serial"),
        )
        self.assertNotIn("## Redacted Upload Failure Diagnostics", success_body)
        self.assertIn("No high-signal upload diagnostics were captured.", empty_failure_body)

    def test_device_validation_requires_a_com_port(self):
        """The physical validation command should not run without one COM port."""
        with mock.patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                installer.create_parser().parse_args(["validate", "--yes"])

    def test_device_validation_batch_uses_one_raw_repl_connection(self):
        """The complete probe sequence should be generated for one mpremote session."""
        request = installer.InstallRequest(port="COM7", no_reset=True, assume_yes=True)
        command = installer.device_validation_batch_command(
            Path("C:/mpremote.exe"),
            request,
            installer.DEVICE_VALIDATION_PROBES,
        )

        self.assertEqual(command[:4], ["C:/mpremote.exe", "connect", "COM7", "exec"])
        batch_code = command[-1]
        compile(batch_code, "<device-validation-batch>", "exec")
        self.assertIn("except Exception:", batch_code)
        positions = [batch_code.index(f"exec({probe.command!r})") for probe in installer.DEVICE_VALIDATION_PROBES]
        self.assertEqual(positions, sorted(positions))
        self.assertNotIn("reset", command)

    def test_device_validation_batch_continues_after_a_device_exception(self):
        """A caught probe exception should report failure and still execute later probes."""
        probes = (
            installer.DeviceValidationProbe("first", "print('first ran')", "first:"),
            installer.DeviceValidationProbe("broken", "raise ValueError('expected')", "broken:"),
            installer.DeviceValidationProbe("last", "print('last ran')", "last:"),
        )
        output = io.StringIO()

        with contextlib.redirect_stdout(output):
            exec(installer.device_validation_batch_code(probes), {})

        statuses = dict(installer.parse_device_validation_probe_statuses(output.getvalue(), probes))
        self.assertEqual(statuses, {"first": 0, "broken": 1, "last": 0})
        self.assertIn("last ran", output.getvalue())

    def test_device_validation_probe_status_parser_rejects_missing_and_malformed_markers(self):
        """Only one valid status marker should allow an individual probe to pass."""
        transcript = "\n".join(
            [
                "device_validation_result: name=display status=0",
                "device_validation_result: name=io status=1",
                "device_validation_result: name=codec status=2",
                "device_validation_result: name=capture status=0",
                "device_validation_result: name=capture status=0",
                "device_validation_result: name=inference status=0",
            ]
        )

        statuses = dict(
            installer.parse_device_validation_probe_statuses(
                transcript,
                installer.DEVICE_VALIDATION_PROBES,
            )
        )

        self.assertEqual(statuses["display"], 0)
        self.assertEqual(statuses["io"], 1)
        self.assertEqual(statuses["codec"], 1)
        self.assertEqual(statuses["capture"], 1)
        self.assertEqual(statuses["playback"], 1)
        self.assertEqual(statuses["wifi"], 1)
        self.assertEqual(statuses["inference"], 0)

    def test_device_validation_sweep_includes_the_local_wifi_probe(self):
        """The sweep should run the local Wi-Fi/health probe before inference."""
        names = [probe.name for probe in installer.DEVICE_VALIDATION_PROBES]
        self.assertIn("wifi", names)
        self.assertLess(names.index("playback"), names.index("wifi"))
        self.assertLess(names.index("wifi"), names.index("inference"))

        wifi_probe = next(
            probe for probe in installer.DEVICE_VALIDATION_PROBES if probe.name == "wifi"
        )
        self.assertEqual(wifi_probe.serial_prefix, "wifi_probe:")
        self.assertEqual(wifi_probe.observations, ())
        self.assertIn("wifi_probe.run_probe() == 'ok'", wifi_probe.command)

        batch_code = installer.device_validation_batch_code(installer.DEVICE_VALIDATION_PROBES)
        compile(batch_code, "<device-validation-batch>", "exec")
        self.assertIn(f"exec({wifi_probe.command!r})", batch_code)

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

            def simulated_batch(command, probe_sink):
                """Write complete successful output from the one validation session."""
                batch_code = command[-1]
                for probe in installer.DEVICE_VALIDATION_PROBES:
                    self.assertIn(f"exec({probe.command!r})", batch_code)
                    probe_sink.write(
                        f"{probe.serial_prefix} complete COM7 token=probe-secret C:\\bench\\serial.log"
                    )
                    probe_sink.write(
                        f"device_validation_result: name={probe.name} status=0"
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
                mock.patch.object(installer, "run_streaming", side_effect=simulated_batch) as run_streaming,
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
            self.assertTrue(received_request.preflight_reset)
            self.assertEqual(run_streaming.call_count, 1)
            batch_command = run_streaming.call_args.args[0]
            self.assertEqual(batch_command[:4], ["C:/mpremote.exe", "connect", "COM7", "exec"])
            issue_body = (capture_dir / "github-issue-body.md").read_text(encoding="utf-8")
            metadata = (capture_dir / "run-metadata.txt").read_text(encoding="utf-8")
            self.assertIn("Aggregate validation status: `0`", issue_body)
            self.assertIn("Device validation batch status: `0`", issue_body)
            self.assertIn("GPIO42 button press and release were observed: `pass`", issue_body)
            self.assertIn("- wifi: `0`", issue_body)
            self.assertIn("wifi_probe: complete", issue_body)
            self.assertIn("probe_wifi_status=0", metadata)
            self.assertIn("inference_probe: complete", issue_body)
            self.assertNotIn("## Redacted Upload Failure Diagnostics", issue_body)
            self.assertNotIn("COM7", issue_body)
            self.assertNotIn("probe-secret", issue_body)
            self.assertNotIn("C:\\bench", issue_body)
            self.assertIn("workflow=windows-device-validation", metadata)
            self.assertIn("validation_batch_status=0", metadata)
            self.assertIn("observation_speaker=pass", metadata)
            self.assertEqual(
                (capture_dir / "github-created-issue.txt").read_text(encoding="utf-8"),
                "https://github.com/owner/repo/issues/202\n",
            )
            self.assertIn("issue", run.call_args.args[0])
            self.assertIn("create", run.call_args.args[0])
            self.assertIn("owner/repo", run.call_args.args[0])

    def test_device_validation_continues_after_a_probe_failure(self):
        """One reported probe failure should retain later probe results from the batch."""
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

            def failed_io_batch(command, probe_sink):
                """Report an IO failure while preserving all later probe markers."""
                for probe in installer.DEVICE_VALIDATION_PROBES:
                    status = 1 if probe.name == "io" else 0
                    probe_sink.write(
                        f"device_validation_result: name={probe.name} status={status}"
                    )
                return 0

            with (
                mock.patch.object(installer, "run_install_request", return_value=0),
                mock.patch.object(installer, "ensure_mpremote", return_value=Path("C:/mpremote.exe")),
                mock.patch.object(installer, "run_streaming", side_effect=failed_io_batch) as run_streaming,
                mock.patch.object(installer, "resolve_device_validation_repository", return_value="owner/repo"),
                mock.patch.object(installer, "create_github_issue") as create_github_issue,
            ):
                self.assertEqual(
                    installer.run_device_validation(args, sink, input_func=lambda _prompt: next(responses)),
                    1,
                )

            self.assertEqual(run_streaming.call_count, 1)
            create_github_issue.assert_called_once()
            self.assertIn("inference probe exit status: 0", sink.transcript)

    def test_device_validation_fails_when_batch_transport_fails(self):
        """A nonzero mpremote exit must fail the run even when markers were emitted."""
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
            responses = iter(["pass"] * len(installer.DEVICE_VALIDATION_OBSERVATIONS))

            def transport_failure(command, probe_sink):
                """Emit successful device markers before the host transport disconnects."""
                for probe in installer.DEVICE_VALIDATION_PROBES:
                    probe_sink.write(f"device_validation_result: name={probe.name} status=0")
                return 7

            with (
                mock.patch.object(installer, "run_install_request", return_value=0),
                mock.patch.object(installer, "ensure_mpremote", return_value=Path("C:/mpremote.exe")),
                mock.patch.object(installer, "run_streaming", side_effect=transport_failure),
                mock.patch.object(installer, "resolve_device_validation_repository", return_value="owner/repo"),
                mock.patch.object(installer, "create_github_issue"),
            ):
                self.assertEqual(
                    installer.run_device_validation(args, sink, input_func=lambda _prompt: next(responses)),
                    1,
                )

            issue_body = (capture_dir / "github-issue-body.md").read_text(encoding="utf-8")
            metadata = (capture_dir / "run-metadata.txt").read_text(encoding="utf-8")
            self.assertIn("Device validation batch status: `7`", issue_body)
            self.assertIn("validation_batch_status=7", metadata)

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
