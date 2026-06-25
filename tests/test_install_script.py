"""Tests for the root install.sh firmware installer."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SCRIPT = REPO_ROOT / "install.sh"
GITIGNORE = REPO_ROOT / ".gitignore"


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
        """Missing prerequisite downloads should require config-backed approval."""
        self.assertIn("collect_missing_prerequisites", self.script_text)
        self.assertIn("Download missing components and continue", self.script_text)
        self.assertIn('confirm_from_config "AIPI_DOWNLOAD_PREREQUISITES"', self.script_text)
        self.assertIn("bash \"${SETUP_SCRIPT}\"", self.script_text)
        self.assertIn("-y|--yes", self.script_text)

    def test_self_updates_from_git_before_installer_actions(self):
        """The installer should pull the latest script before parsing normal actions."""
        self_update_index = self.script_text.index('self_update_from_git "$@"')
        parser_index = self.script_text.index("while [[ $# -gt 0 ]]", self_update_index)

        self.assertIn('git -C "${worktree_root}" pull --ff-only', self.script_text)
        self.assertIn("self_update_pull_with_retry()", self.script_text)
        self.assertIn("for attempt in 1 2", self.script_text)
        self.assertIn("retrying once before installer stops", self.script_text)
        self.assertIn("sleep 2", self.script_text)
        self.assertIn('exec env AIPI_INSTALL_SELF_UPDATED=1 "${SCRIPT_DIR}/install.sh" "$@"', self.script_text)
        self.assertIn("--skip-self-update", self.script_text)
        self.assertIn("AIPI_SKIP_SELF_UPDATE", self.script_text)
        self.assertIn("git pull failed after retry; installer stopped before device operations", self.script_text)
        self.assertIn("--skip-self-update only for an intentional offline or pinned-revision run", self.script_text)
        self.assertLess(self_update_index, parser_index)

    def test_debug_mode_writes_sanitized_issue_artifact(self):
        """Debug mode should write an ignored, sanitized issue-ready artifact."""
        gitignore_text = GITIGNORE.read_text(encoding="utf-8")
        debug_index = self.script_text.index("start_debug_logging")
        self_update_index = self.script_text.index('self_update_from_git "$@"')

        self.assertIn("--debug", self.script_text)
        self.assertIn("--debug-file FILE", self.script_text)
        self.assertIn("AIPI_INSTALL_DEBUG", self.script_text)
        self.assertIn("AIPI_INSTALL_DEBUG_FILE", self.script_text)
        self.assertIn('TOOLS_ROOT="${TOOLS_DIR}/.local"', self.script_text)
        self.assertIn('debug/install-debug-%s.txt', self.script_text)
        self.assertIn("redact_stream()", self.script_text)
        self.assertIn("mkfifo", self.script_text)
        self.assertIn("redacted-mac", self.script_text)
        self.assertIn("Sanitized run context", self.script_text)
        self.assertIn("status --short --branch", self.script_text)
        self.assertIn("Installer debug file:", self.script_text)
        self.assertIn("tools/.local/", gitignore_text)
        self.assertLess(debug_index, self_update_index)

    def test_trace_mode_writes_device_and_install_status_artifact(self):
        """Trace mode should add detailed sanitized install and target diagnostics."""
        self.assertIn("--trace", self.script_text)
        self.assertIn("--trace-file FILE", self.script_text)
        self.assertIn("AIPI_INSTALL_TRACE", self.script_text)
        self.assertIn("AIPI_INSTALL_TRACE_FILE", self.script_text)
        self.assertIn("debug/install-trace-%s.txt", self.script_text)
        self.assertIn("trace_event()", self.script_text)
        self.assertIn("trace_file_metadata()", self.script_text)
        self.assertIn("trace_source_inventory()", self.script_text)
        self.assertIn("trace_device_probe()", self.script_text)
        self.assertIn("trace_micropython_probe()", self.script_text)
        self.assertIn("run_with_trace()", self.script_text)
        self.assertIn("chip-id", self.script_text)
        self.assertIn("flash-id", self.script_text)
        self.assertIn("read-mac", self.script_text)
        self.assertIn("micropython_firmware", self.script_text)
        self.assertIn("install_write_flash", self.script_text)
        self.assertIn("upload_application", self.script_text)
        self.assertIn("sha256_file()", self.script_text)

    def test_trace_mode_creates_ignored_artifact_for_cleanup_run(self):
        """A trace cleanup run should create debug and trace artifacts only under tools/.local."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            tmp_install = repo_root / "install.sh"
            shutil.copy2(INSTALL_SCRIPT, tmp_install)
            tmp_install.chmod(0o755)

            result = subprocess.run(
                [str(tmp_install), "--trace", "--clean-tools"],
                cwd=repo_root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Installer debug file:", result.stdout)
            self.assertIn("Installer trace file:", result.stdout)

            trace_files = list((repo_root / "tools" / ".local" / "debug").glob("install-trace-*.txt"))
            self.assertEqual(len(trace_files), 1)
            trace_text = trace_files[0].read_text(encoding="utf-8")
            self.assertIn("AIPI-Lite installer trace log", trace_text)
            self.assertIn("event=installer_start", trace_text)
            self.assertIn("name=clean_tools", trace_text)
            self.assertEqual(trace_files[0].stat().st_mode & 0o777, 0o600)

    def test_noninteractive_prompts_default_safely(self):
        """Closed stdin should not leave installer prompts hidden and waiting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            tmp_install = repo_root / "install.sh"
            setup_script = repo_root / "tools" / "setup_micropython_tools.sh"
            shutil.copy2(INSTALL_SCRIPT, tmp_install)
            tmp_install.chmod(0o755)
            setup_script.parent.mkdir(parents=True)
            setup_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            setup_script.chmod(0o755)

            result = subprocess.run(
                [
                    str(tmp_install),
                    "--skip-self-update",
                    "--firmware-url",
                    "https://example.invalid/ESP32_GENERIC_S3-test.bin",
                    "--skip-backup",
                ],
                cwd=repo_root,
                stdin=subprocess.DEVNULL,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            combined_output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 1)
            self.assertIn("Serial port, or blank for auto-detect [auto]", combined_output)
            self.assertIn("Serial port prompt skipped because prompt input is not available", combined_output)
            self.assertIn("Download missing components and continue [no]", combined_output)
            self.assertIn("defaulting to no because prompt input is not available", combined_output)
            self.assertIn("aborted: prerequisites are missing", combined_output)
            self.assertIn(
                "AIPI_SERIAL_PORT=auto",
                (repo_root / ".conf").read_text(encoding="utf-8"),
            )

    def test_clean_tools_removes_downloaded_prerequisites_only(self):
        """The cleanup option should preserve backups and diagnostic artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            tmp_install = repo_root / "install.sh"
            shutil.copy2(INSTALL_SCRIPT, tmp_install)
            tmp_install.chmod(0o755)

            tools_root = repo_root / "tools" / ".local"
            prerequisite_paths = [
                tools_root / "micropython-venv",
                tools_root / "downloads" / "firmware",
                tools_root / "micropython-libs",
            ]
            preserved_paths = [
                tools_root / "backups",
                tools_root / "debug",
                tools_root / "dev-install",
            ]
            for path in prerequisite_paths + preserved_paths:
                path.mkdir(parents=True)
                (path / "marker.txt").write_text("keep scope visible", encoding="utf-8")

            result = subprocess.run(
                [str(tmp_install), "--clean-tools"],
                cwd=repo_root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Cleaning downloaded prerequisite artifacts", result.stdout)
            self.assertIn("Prerequisite cleanup complete.", result.stdout)
            for path in prerequisite_paths:
                self.assertFalse(path.exists(), f"{path} should have been removed")
            for path in preserved_paths:
                self.assertTrue((path / "marker.txt").exists(), f"{path} should be preserved")

    def test_answers_are_persisted_in_conf(self):
        """The installer should read and write task answers from .conf."""
        gitignore_text = GITIGNORE.read_text(encoding="utf-8")

        self.assertIn('CONF_FILE="${AIPI_INSTALL_CONF:-${SCRIPT_DIR}/.conf}"', self.script_text)
        self.assertIn("config_get()", self.script_text)
        self.assertIn("config_set()", self.script_text)
        self.assertIn("confirm_from_config()", self.script_text)
        self.assertIn("read_prompt_answer()", self.script_text)
        self.assertNotIn("read -r -p", self.script_text)
        self.assertIn("AIPI_SERIAL_PORT", self.script_text)
        self.assertIn("AIPI_BOOTLOADER_CONFIRMED", self.script_text)
        self.assertIn("AIPI_CONFIRM_FLASH", self.script_text)
        self.assertIn("AIPI_CONFIRM_RESTORE", self.script_text)
        self.assertIn("AIPI_BACKUP_CHUNK_SIZE", self.script_text)
        self.assertIn("AIPI_BACKUP_MIN_CHUNK_SIZE", self.script_text)
        self.assertIn(".conf", gitignore_text)

    def test_flashes_firmware_at_offset_zero(self):
        """The installer should use the ESP32-S3 MicroPython offset-zero flow."""
        self.assertIn("--chip esp32s3", self.script_text)
        self.assertIn("erase_flash", self.script_text)
        self.assertIn("write_flash 0 \"${firmware_path}\"", self.script_text)
        self.assertNotIn("bootloader.bin", self.script_text)
        self.assertNotIn("partition-table.bin", self.script_text)

    def test_restore_mode_uses_saved_backup_without_firmware_download(self):
        """Restore mode should write a stock backup without resolving MicroPython."""
        main_text = self.script_text[self.script_text.index("main()") :]
        restore_index = main_text.index('if [[ "${RESTORE_MODE}" -eq 1 ]]')
        resolve_index = main_text.index('firmware_url="$(resolve_firmware_url)"')

        self.assertIn("--restore", self.script_text)
        self.assertIn("--restore-backup FILE", self.script_text)
        self.assertIn("AIPI_RESTORE_BACKUP_PATH", self.script_text)
        self.assertIn("AIPI_CONFIRM_RESTORE", self.script_text)
        self.assertIn('write_flash 0 "${RESTORE_BACKUP_PATH}"', self.script_text)
        self.assertLess(restore_index, resolve_index)

    def test_auto_detected_esptool_port_is_reused(self):
        """Auto-detected esptool ports should be locked before backup retries."""
        main_text = self.script_text[self.script_text.index("main()") :]
        lock_index = main_text.index('lock_esptool_auto_port "${esptool_py}"')
        probe_index = main_text.index('trace_device_probe "${esptool_py}"')
        backup_index = main_text.index('backup_stock_firmware "${esptool_py}"')

        self.assertIn("extract_esptool_connected_port()", self.script_text)
        self.assertIn("lock_esptool_auto_port()", self.script_text)
        self.assertIn("Connected[[:space:]]to", self.script_text)
        self.assertIn('config_set "AIPI_SERIAL_PORT" "${PORT}"', self.script_text)
        self.assertIn('port_args=(--port "${PORT}")', self.script_text)
        self.assertIn("Detected ESP32-S3 serial port:", self.script_text)
        self.assertIn("auto-detect probe failed", self.script_text)
        self.assertIn("phase=auto_port_detect", self.script_text)
        self.assertLess(lock_index, probe_index)
        self.assertLess(lock_index, backup_index)

    def test_esptool_port_parser_handles_v5_connected_output(self):
        """The port parser should capture the successful esptool v5 port line."""
        start = self.script_text.index("extract_esptool_connected_port()")
        end = self.script_text.index("\n\nlock_esptool_auto_port()", start)
        function_text = self.script_text[start:end]
        sample_output = "\n".join(
            [
                "Serial port /dev/ttyS99:",
                "/dev/ttyS99 failed to connect",
                "Serial port /dev/ttyS7:",
                "Connecting....",
                "Connected to ESP32-S3 on /dev/ttyS7:",
                "Chip type: ESP32-S3",
            ]
        )

        result = subprocess.run(
            [
                "bash",
                "-c",
                f"{function_text}\nextract_esptool_connected_port \"$1\"",
                "test-shell",
                sample_output,
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/dev/ttyS7")

    def test_stock_backup_opt_in_runs_before_flashing(self):
        """The optional stock backup should still run before erase/write operations."""
        main_text = self.script_text[self.script_text.index("main()") :]
        opt_in_index = main_text.index("if should_backup_stock_firmware; then")
        backup_index = main_text.index('backup_stock_firmware "${esptool_py}"')
        erase_index = main_text.index("erase_flash")
        write_index = main_text.index("write_flash 0")

        self.assertIn('BACKUP_DIR="${TOOLS_ROOT}/backups"', self.script_text)
        self.assertIn("AIPI_STOCK_BACKUP_PATH", self.script_text)
        self.assertIn('BACKUP_STOCK_FIRMWARE="${AIPI_BACKUP_STOCK_FIRMWARE:-0}"', self.script_text)
        self.assertIn("--backup-stock", self.script_text)
        self.assertIn("AIPI_BACKUP_STOCK_FIRMWARE", self.script_text)
        self.assertIn("should_backup_stock_firmware()", self.script_text)
        self.assertIn('read-flash "${offset_arg}" "${read_size_arg}" "${chunk_path}"', self.script_text)
        self.assertIn('mv "${tmp_path}" "${BACKUP_PATH}"', self.script_text)
        self.assertLess(opt_in_index, backup_index)
        self.assertLess(backup_index, erase_index)
        self.assertLess(backup_index, write_index)

    def test_backup_uses_chunked_reads_and_rejects_partial_files(self):
        """The stock backup should be chunked and exact-size validated."""
        self.assertIn('BACKUP_CHUNK_SIZE="${AIPI_BACKUP_CHUNK_SIZE:-}"', self.script_text)
        self.assertIn("--backup-chunk-size SIZE", self.script_text)
        self.assertIn("--backup-min-chunk-size SIZE", self.script_text)
        self.assertIn("--clean-tools", self.script_text)
        self.assertIn("--clean-prereqs", self.script_text)
        self.assertIn('BACKUP_CHUNK_SIZE="${BACKUP_CHUNK_SIZE:-0x80000}"', self.script_text)
        self.assertIn('BACKUP_MIN_CHUNK_SIZE="${BACKUP_MIN_CHUNK_SIZE:-0x1000}"', self.script_text)
        self.assertIn("positive_size_to_bytes()", self.script_text)
        self.assertIn("file_size_bytes()", self.script_text)
        self.assertIn("backup_file_is_complete()", self.script_text)
        self.assertIn("--before no-reset --after no-reset", self.script_text)
        self.assertIn("Retrying failed chunks down to", self.script_text)
        self.assertIn("retrying down to", self.script_text)
        self.assertIn("read-protected", self.script_text)
        self.assertIn("report_stock_backup_blocked()", self.script_text)
        self.assertIn('trace_event "stock_backup_blocked"', self.script_text)
        self.assertIn("hardware validation status: blocked", self.script_text)
        self.assertIn("On WSL, detach and reattach the USB device", self.script_text)
        self.assertIn("Rerun without --backup-stock only when stock recovery is not required", self.script_text)
        self.assertIn("--backup-chunk-size 0x40000 --backup-min-chunk-size 0x1000", self.script_text)
        self.assertIn("Existing stock firmware backup is incomplete", self.script_text)
        self.assertIn("backup chunk size mismatch", self.script_text)
        self.assertNotIn('read-flash 0 "${FLASH_SIZE}" "${BACKUP_PATH}"', self.script_text)

    def test_stock_backup_skips_by_default_with_opt_in_backup(self):
        """Normal installs should skip backup while keeping opt-in recovery backup."""
        self.assertIn('BACKUP_STOCK_FIRMWARE="${AIPI_BACKUP_STOCK_FIRMWARE:-0}"', self.script_text)
        self.assertIn('SKIP_STOCK_BACKUP="${AIPI_SKIP_STOCK_BACKUP:-0}"', self.script_text)
        self.assertIn("--backup-stock", self.script_text)
        self.assertIn("--skip-backup", self.script_text)
        self.assertIn("AIPI_BACKUP_STOCK_FIRMWARE", self.script_text)
        self.assertIn("AIPI_SKIP_STOCK_BACKUP", self.script_text)
        self.assertIn("Stock firmware backup skipped by default for application install", self.script_text)
        self.assertIn("Use --backup-stock when a fresh stock recovery image is required", self.script_text)
        self.assertIn("should_backup_stock_firmware", self.script_text)
        self.assertIn('if should_backup_stock_firmware; then', self.script_text)
        self.assertIn("stock firmware backup skipped by operator request", self.script_text)
        self.assertIn("stock firmware recovery may be unavailable", self.script_text)
        self.assertIn('skip_stock_firmware_backup "operator_requested"', self.script_text)
        self.assertIn('trace_event "stock_backup" "status=skipped" "reason=${reason}"', self.script_text)
        self.assertIn('trace_event "phase" "name=stock_backup" "status=skipped" "reason=default_application_install"', self.script_text)
        self.assertIn('stock_backup_summary="skipped by default"', self.script_text)
        self.assertIn('stock_backup_summary="skipped by operator request"', self.script_text)
        self.assertIn('Stock backup: ${stock_backup_summary}', self.script_text)
        self.assertNotIn('config_set "AIPI_BACKUP_STOCK_FIRMWARE"', self.script_text)
        self.assertNotIn('config_set "AIPI_SKIP_STOCK_BACKUP"', self.script_text)

    def test_uploads_current_application_baseline(self):
        """The installer should copy the current app source when no app dir exists."""
        self.assertIn('${SCRIPT_DIR}/src', self.script_text)
        self.assertIn("upload_tree", self.script_text)
        self.assertNotIn('${SCRIPT_DIR}/main.py', self.script_text)
        self.assertNotIn('${SCRIPT_DIR}/aipi_lite_config.py', self.script_text)
        self.assertNotIn('${SCRIPT_DIR}/lib', self.script_text)
        self.assertIn("lib/drivers", self.script_text)

    def test_resets_device_after_upload(self):
        """The installer should reset the device after copying source by default."""
        main_text = self.script_text[self.script_text.index("main()") :]
        upload_index = main_text.index('upload_application "${mpremote_bin}"')
        reset_index = main_text.index('reset_device "${mpremote_bin}"')

        self.assertIn("AIPI_RESET_AFTER_UPLOAD", self.script_text)
        self.assertIn('"${mpremote_bin}" connect "${connect_target}" reset', self.script_text)
        self.assertLess(upload_index, reset_index)


if __name__ == "__main__":
    unittest.main()
