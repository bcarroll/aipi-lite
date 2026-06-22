"""Tests for the root install.sh firmware installer."""

from pathlib import Path
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
        parser_index = self.script_text.index("while [[ $# -gt 0 ]]")

        self.assertIn('git -C "${worktree_root}" pull --ff-only', self.script_text)
        self.assertIn('exec env AIPI_INSTALL_SELF_UPDATED=1 "${SCRIPT_DIR}/install.sh" "$@"', self.script_text)
        self.assertIn("--skip-self-update", self.script_text)
        self.assertIn("AIPI_SKIP_SELF_UPDATE", self.script_text)
        self.assertIn("git pull failed; installer stopped before device operations", self.script_text)
        self.assertLess(self_update_index, parser_index)

    def test_answers_are_persisted_in_conf(self):
        """The installer should read and write task answers from .conf."""
        gitignore_text = GITIGNORE.read_text(encoding="utf-8")

        self.assertIn('CONF_FILE="${AIPI_INSTALL_CONF:-${SCRIPT_DIR}/.conf}"', self.script_text)
        self.assertIn("config_get()", self.script_text)
        self.assertIn("config_set()", self.script_text)
        self.assertIn("confirm_from_config()", self.script_text)
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

    def test_backs_up_stock_firmware_before_flashing(self):
        """The installer should read the stock flash before erase/write operations."""
        main_text = self.script_text[self.script_text.index("main()") :]
        backup_index = main_text.index('backup_stock_firmware "${esptool_py}"')
        erase_index = main_text.index("erase_flash")
        write_index = main_text.index("write_flash 0")

        self.assertIn('BACKUP_DIR="${TOOLS_ROOT}/backups"', self.script_text)
        self.assertIn("AIPI_STOCK_BACKUP_PATH", self.script_text)
        self.assertIn('read_flash "${offset_arg}" "${read_size_arg}" "${chunk_path}"', self.script_text)
        self.assertIn('mv "${tmp_path}" "${BACKUP_PATH}"', self.script_text)
        self.assertLess(backup_index, erase_index)
        self.assertLess(backup_index, write_index)

    def test_backup_uses_chunked_reads_and_rejects_partial_files(self):
        """The stock backup should be chunked and exact-size validated."""
        self.assertIn('BACKUP_CHUNK_SIZE="${AIPI_BACKUP_CHUNK_SIZE:-}"', self.script_text)
        self.assertIn("--backup-chunk-size SIZE", self.script_text)
        self.assertIn("--backup-min-chunk-size SIZE", self.script_text)
        self.assertIn('BACKUP_CHUNK_SIZE="${BACKUP_CHUNK_SIZE:-0x80000}"', self.script_text)
        self.assertIn('BACKUP_MIN_CHUNK_SIZE="${BACKUP_MIN_CHUNK_SIZE:-0x1000}"', self.script_text)
        self.assertIn("positive_size_to_bytes()", self.script_text)
        self.assertIn("file_size_bytes()", self.script_text)
        self.assertIn("backup_file_is_complete()", self.script_text)
        self.assertIn("--before no_reset --after no_reset", self.script_text)
        self.assertIn("Retrying failed chunks down to", self.script_text)
        self.assertIn("retrying down to", self.script_text)
        self.assertIn("read-protected", self.script_text)
        self.assertIn("Existing stock firmware backup is incomplete", self.script_text)
        self.assertIn("backup chunk size mismatch", self.script_text)
        self.assertNotIn('read_flash 0 "${FLASH_SIZE}" "${BACKUP_PATH}"', self.script_text)

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
