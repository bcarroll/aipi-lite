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

    def _make_upload_fixture(self, repo_root):
        """Create a temporary installer tree with fake upload prerequisites."""
        tmp_install = repo_root / "install.sh"
        setup_script = repo_root / "tools" / "setup_micropython_tools.sh"
        app_dir = repo_root / "src"
        mpremote = repo_root / "tools" / ".local" / "micropython-venv" / "bin" / "mpremote"
        app_lib_dir = app_dir / "lib" / "drivers"

        shutil.copy2(INSTALL_SCRIPT, tmp_install)
        tmp_install.chmod(0o755)
        setup_script.parent.mkdir(parents=True)
        setup_script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
        setup_script.chmod(0o755)
        app_lib_dir.mkdir(parents=True)
        (app_dir / "main.py").write_text("print('hello')\n", encoding="utf-8")
        mpremote.parent.mkdir(parents=True)
        mpremote.write_text(
            "#!/usr/bin/env bash\n"
            "printf '%s\\n' \"$*\" >> \"${AIPI_FAKE_MPREMOTE_LOG:-mpremote.log}\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        mpremote.chmod(0o755)
        return tmp_install, app_dir

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

    def test_self_update_is_explicitly_opt_in(self):
        """The installer should not pull from Git unless self-update is requested."""
        self_update_index = self.script_text.index('self_update_from_git "$@"')
        parser_index = self.script_text.index("while [[ $# -gt 0 ]]", self_update_index)

        self.assertIn('git -C "${worktree_root}" pull --ff-only', self.script_text)
        self.assertIn("self_update_pull_with_retry()", self.script_text)
        self.assertIn("for attempt in 1 2", self.script_text)
        self.assertIn("retrying once before installer stops", self.script_text)
        self.assertIn("sleep 2", self.script_text)
        self.assertIn('exec env AIPI_INSTALL_SELF_UPDATED=1 "${SCRIPT_DIR}/install.sh" "$@"', self.script_text)
        self.assertIn('SELF_UPDATE="${AIPI_INSTALL_SELF_UPDATE:-0}"', self.script_text)
        self.assertIn("--self-update", self.script_text)
        self.assertIn("--skip-self-update", self.script_text)
        self.assertIn("AIPI_INSTALL_SELF_UPDATE", self.script_text)
        self.assertIn("AIPI_SKIP_SELF_UPDATE", self.script_text)
        self.assertIn("git pull failed after retry; installer stopped before device operations", self.script_text)
        self.assertIn('if ! is_truthy_value "${SELF_UPDATE}"; then', self.script_text)
        self.assertIn("self-update is skipped by default", self.script_text)
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
            self.assertIn("aborted: upload prerequisites are missing", combined_output)
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
            ]
            preserved_paths = [
                tools_root / "backups",
                tools_root / "debug",
                tools_root / "dev-install",
            ]
            tracked_lib_path = repo_root / "src" / "lib"
            for path in prerequisite_paths + preserved_paths:
                path.mkdir(parents=True)
                (path / "marker.txt").write_text("keep scope visible", encoding="utf-8")
            tracked_lib_path.mkdir(parents=True)
            (tracked_lib_path / "marker.py").write_text("keep = True\n", encoding="utf-8")

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
            self.assertTrue((tracked_lib_path / "marker.py").exists(), "src/lib should be preserved")

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
        self.assertIn("AIPI_CONFIRM_UPLOAD", self.script_text)
        self.assertIn("AIPI_BOOTLOADER_CONFIRMED", self.script_text)
        self.assertIn("AIPI_CONFIRM_FLASH", self.script_text)
        self.assertIn("AIPI_CONFIRM_RESTORE", self.script_text)
        self.assertIn("AIPI_BACKUP_CHUNK_SIZE", self.script_text)
        self.assertIn("AIPI_BACKUP_MIN_CHUNK_SIZE", self.script_text)
        self.assertIn("AIPI_WIFI_SSID", self.script_text)
        self.assertIn("AIPI_WIFI_PASSWORD", self.script_text)
        self.assertIn("AIPI_LOCAL_SERVICE_URL", self.script_text)
        self.assertIn(".conf", gitignore_text)
        self.assertIn("**/local_wifi_config.py", gitignore_text)

    def test_installer_can_prepare_ignored_local_wifi_config(self):
        """The installer should offer to create local_wifi_config.py before upload."""
        upload_application_text = self.script_text[
            self.script_text.index("upload_application()") : self.script_text.index("\n\nreset_device()", self.script_text.index("upload_application()"))
        ]

        self.assertIn('LOCAL_WIFI_CONFIG_FILENAME="local_wifi_config.py"', self.script_text)
        self.assertIn("prepare_local_wifi_config()", self.script_text)
        self.assertIn("write_local_wifi_config()", self.script_text)
        self.assertIn("read_secret_prompt_answer()", self.script_text)
        self.assertIn("AIPI_CREATE_LOCAL_WIFI_CONFIG", self.script_text)
        self.assertIn("AIPI_RECREATE_LOCAL_WIFI_CONFIG", self.script_text)
        self.assertIn("AIPI_APPROVED_LOCAL_HOSTS", self.script_text)
        self.assertIn("WIFI_PASSWORD = {!r}", self.script_text)
        self.assertIn("redacted-local-wifi-config", self.script_text)
        self.assertIn('prepare_local_wifi_config "${app_root}"', upload_application_text)
        self.assertIn('trace_source_inventory "application" "${app_root}"', upload_application_text)

    def test_missing_local_wifi_config_can_be_created_before_upload(self):
        """Configured values should generate local_wifi_config.py before upload."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            tmp_install, app_dir = self._make_upload_fixture(repo_root)
            (repo_root / ".conf").write_text(
                "\n".join(
                    [
                        "AIPI_SERIAL_PORT=auto",
                        "AIPI_CONFIRM_UPLOAD=yes",
                        "AIPI_CREATE_LOCAL_WIFI_CONFIG=yes",
                        "AIPI_WIFI_SSID=LabNet",
                        "AIPI_WIFI_PASSWORD=secret pass",
                        "AIPI_LOCAL_SERVICE_URL=http://192.168.1.10:8080",
                        "AIPI_APPROVED_LOCAL_HOSTS=assistant.lan, lab.local",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [str(tmp_install), "--no-reset"],
                cwd=repo_root,
                stdin=subprocess.DEVNULL,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            config_path = app_dir / "local_wifi_config.py"
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(config_path.exists())
            self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
            config_text = config_path.read_text(encoding="utf-8")
            self.assertIn("WIFI_SSID = 'LabNet'", config_text)
            self.assertIn("WIFI_PASSWORD = 'secret pass'", config_text)
            self.assertIn("LOCAL_SERVICE_URL = 'http://192.168.1.10:8080'", config_text)
            self.assertIn("APPROVED_LOCAL_HOSTS = ('assistant.lan', 'lab.local')", config_text)
            self.assertIn("local_wifi_config.py", (repo_root / "mpremote.log").read_text(encoding="utf-8"))

    def test_existing_local_wifi_config_is_preserved_by_default(self):
        """Existing Wi-Fi config should not be overwritten without confirmation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            tmp_install, app_dir = self._make_upload_fixture(repo_root)
            config_path = app_dir / "local_wifi_config.py"
            original_text = "WIFI_SSID = 'ExistingNet'\n"
            config_path.write_text(original_text, encoding="utf-8")
            (repo_root / ".conf").write_text(
                "AIPI_SERIAL_PORT=auto\n"
                "AIPI_CONFIRM_UPLOAD=yes\n"
                "AIPI_RECREATE_LOCAL_WIFI_CONFIG=no\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [str(tmp_install), "--no-reset"],
                cwd=repo_root,
                stdin=subprocess.DEVNULL,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(config_path.read_text(encoding="utf-8"), original_text)
            self.assertIn("Keeping existing local Wi-Fi config", result.stdout)

    def test_missing_local_wifi_config_skips_creation_noninteractively(self):
        """Closed stdin should not silently create a credentials file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            tmp_install, app_dir = self._make_upload_fixture(repo_root)
            (repo_root / ".conf").write_text(
                "AIPI_SERIAL_PORT=auto\n"
                "AIPI_CONFIRM_UPLOAD=yes\n",
                encoding="utf-8",
            )

            result = subprocess.run(
                [str(tmp_install), "--no-reset"],
                cwd=repo_root,
                stdin=subprocess.DEVNULL,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            combined_output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((app_dir / "local_wifi_config.py").exists())
            self.assertIn("Create local Wi-Fi config", combined_output)
            self.assertIn("defaulting to no because prompt input is not available", combined_output)
            self.assertIn("Local Wi-Fi config not created", combined_output)

    def test_flash_micropython_mode_uses_offset_zero(self):
        """Explicit flashing should use the ESP32-S3 MicroPython offset-zero flow."""
        main_text = self.script_text[self.script_text.index("main()") :]
        flash_branch_index = main_text.index("if ! should_flash_micropython; then")
        resolve_index = main_text.index('firmware_url="$(resolve_firmware_url)"')

        self.assertIn('FLASH_MICROPYTHON="${AIPI_FLASH_MICROPYTHON:-0}"', self.script_text)
        self.assertIn("--flash-micropython", self.script_text)
        self.assertIn("AIPI_FLASH_MICROPYTHON", self.script_text)
        self.assertIn("should_flash_micropython()", self.script_text)
        self.assertIn("--chip esp32s3", self.script_text)
        self.assertIn("erase_flash", self.script_text)
        self.assertIn("write_flash 0 \"${firmware_path}\"", self.script_text)
        self.assertNotIn("bootloader.bin", self.script_text)
        self.assertNotIn("partition-table.bin", self.script_text)
        self.assertLess(flash_branch_index, resolve_index)

    def test_default_mode_uploads_without_firmware_flash(self):
        """Normal installs should assume MicroPython exists and only upload source."""
        main_text = self.script_text[self.script_text.index("main()") :]
        upload_prereq_index = main_text.index("ensure_upload_prerequisites")
        firmware_resolve_index = main_text.index('firmware_url="$(resolve_firmware_url)"')
        upload_assets_index = main_text.index('upload_runtime_assets "${mpremote_bin}"')

        self.assertIn("collect_missing_upload_prerequisites()", self.script_text)
        self.assertIn("Missing upload prerequisite components", self.script_text)
        self.assertIn("tracked MicroPython libraries in ${app_root}/lib", self.script_text)
        self.assertIn("setup_args=(--skip-firmware)", self.script_text)
        self.assertNotIn("staged MicroPython libraries", self.script_text)
        self.assertNotIn("upload_libraries", self.script_text)
        self.assertNotIn("micropython-libs", self.script_text)
        self.assertIn("AIPI_CONFIRM_UPLOAD", self.script_text)
        self.assertIn("MicroPython firmware: assumed present on device (ESP32_GENERIC_S3)", self.script_text)
        self.assertIn("Upload application source to existing MicroPython device", self.script_text)
        self.assertIn("Application upload complete.", self.script_text)
        self.assertLess(upload_prereq_index, firmware_resolve_index)
        self.assertLess(upload_assets_index, firmware_resolve_index)

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
        """Auto-detected esptool ports should be locked before flash-mode backup retries."""
        main_text = self.script_text[self.script_text.index("main()") :]
        lock_index = main_text.index('lock_esptool_auto_port "${esptool_py}"')
        bootloader_index = main_text.index('require_bootloader_mode "${esptool_py}"')
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
        self.assertLess(lock_index, bootloader_index)
        self.assertLess(lock_index, probe_index)
        self.assertLess(lock_index, backup_index)

    def test_bootloader_check_blocks_flash_sensitive_operations(self):
        """Install and restore should require ROM bootloader sync before flash operations."""
        main_text = self.script_text[self.script_text.index("main()") :]
        first_check_index = main_text.index('require_bootloader_mode "${esptool_py}"')
        restore_index = main_text.index('restore_stock_firmware "${esptool_py}"')
        second_check_index = main_text.index('require_bootloader_mode "${esptool_py}"', first_check_index + 1)
        backup_index = main_text.index('backup_stock_firmware "${esptool_py}"')
        erase_index = main_text.index("install_erase_flash")
        write_index = main_text.index("install_write_flash")

        self.assertIn("require_bootloader_mode()", self.script_text)
        self.assertIn("Checking ESP32-S3 bootloader connection", self.script_text)
        self.assertIn("phase=bootloader_check", self.script_text)
        self.assertIn("--before no-reset --after no-reset chip-id", self.script_text)
        self.assertIn("installer stopped before stock backup, erase, write, or restore operations", self.script_text)
        self.assertIn("put the AIPI-Lite in bootloader mode", self.script_text)
        self.assertLess(first_check_index, restore_index)
        self.assertLess(second_check_index, backup_index)
        self.assertLess(second_check_index, erase_index)
        self.assertLess(second_check_index, write_index)

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
        self.assertIn("error: --backup-stock requires --flash-micropython.", self.script_text)
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
        self.assertIn("Rerun with --flash-micropython but without --backup-stock", self.script_text)
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
        self.assertIn('app_root="${SCRIPT_DIR}/src"', self.script_text)

    def test_resets_device_after_upload(self):
        """The installer should reset the device after copying source by default."""
        upload_runtime_text = self.script_text[
            self.script_text.index("upload_runtime_assets()") : self.script_text.index("\n\nmain()", self.script_text.index("upload_runtime_assets()"))
        ]
        upload_index = upload_runtime_text.index('upload_application "${mpremote_bin}"')
        reset_index = upload_runtime_text.index('reset_device "${mpremote_bin}"')

        self.assertIn("AIPI_RESET_AFTER_UPLOAD", self.script_text)
        self.assertIn('"${mpremote_bin}" connect "${connect_target}" reset', self.script_text)
        self.assertLess(upload_index, reset_index)


if __name__ == "__main__":
    unittest.main()
