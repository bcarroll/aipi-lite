# AIPI-Lite Backup and Recovery

Target device: XORIGIN AI PI-Lite / AIPI Lite, model `XY006PL01`

Use this procedure before replacing stock firmware. Firmware backup files may
contain vendor provisioning data, local configuration, or device identifiers.
Keep them out of Git and store them as local operational artifacts.

## Bootloader Mode

The AIPI-Lite must be in ESP32-S3 bootloader mode for backup, install, or
restore operations.

1. Remove the four back screws from the AIPI-Lite.
2. Hold the BOOT button under the display.
3. Plug the device into USB-C while holding BOOT.
4. Confirm the screen remains black.
5. Use `--port` if more than one USB serial device is attached.

## Stock Firmware Backup

The preferred path is the installer. It prompts for bootloader confirmation,
stores answers in ignored `.conf`, then backs up the full 16 MB flash in
smaller chunks before it erases or writes replacement firmware:

```bash
./install.sh --port /dev/cu.usbmodem31101
```

By default, backups are written under:

```text
tools/.local/backups/
```

Use a specific backup destination when needed:

```bash
./install.sh \
  --port /dev/cu.usbmodem31101 \
  --backup-path /path/outside/git/aipi-lite-stock.bin
```

The installer accepts an existing stock backup only when it exactly matches `AIPI_FLASH_SIZE`.
That defaults to `0x1000000` / `16777216` bytes. A failed partial transfer, for
example `1048576/16777216` bytes, is treated as incomplete and replaced on the
next run instead of being reused.

The default backup chunk size is `0x80000`. If USB transfer reliability is poor,
use a smaller chunk size:

```bash
./install.sh \
  --port /dev/cu.usbmodem31101 \
  --backup-chunk-size 0x40000
```

Manual backup is also possible after staging tools:

```bash
tools/setup_micropython_tools.sh --skip-firmware --skip-libraries
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/cu.usbmodem31101 \
  flash_id
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/cu.usbmodem31101 \
  read_flash 0 0x1000000 tools/.local/backups/aipi-lite-stock.bin
```

Expected backup indicators:

- `esptool` detects an ESP32-S3.
- `flash_id` reports a flash chip without connection errors.
- `read_flash` reaches 100 percent for every chunk and writes a complete
  16 MB / `16777216` byte `.bin` file.
- The backup file remains under ignored `tools/.local/` or another location
  outside source control.

## Stock Firmware Restore

Restore the saved stock firmware image with:

```bash
./install.sh \
  --port /dev/cu.usbmodem31101 \
  --restore-backup tools/.local/backups/aipi-lite-stock.bin
```

If `.conf` already contains `AIPI_STOCK_BACKUP_PATH` or
`AIPI_RESTORE_BACKUP_PATH`, restore that saved path with:

```bash
./install.sh --port /dev/cu.usbmodem31101 --restore
```

Manual restore is:

```bash
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/cu.usbmodem31101 \
  erase_flash
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/cu.usbmodem31101 \
  --baud 460800 \
  write_flash 0 tools/.local/backups/aipi-lite-stock.bin
```

Expected restore indicators:

- `esptool` prints write progress and verifies the written data hash.
- On reset, the device should no longer present the MicroPython banner or `>>>`
  REPL as its normal boot behavior.
- The device display should return to the stock firmware behavior that was
  present before replacement firmware testing.
- Exact vendor serial log lines are not yet verified for this unit; record them
  in this document after a successful hardware restore.

## Flashing Safety Checklist

Before any erase, write, or restore operation:

- Confirm the stock firmware backup exists and is non-empty.
- Confirm the backup is not staged in Git: `git status --short`.
- Confirm the device is on stable USB power.
- If using the battery module, confirm it has enough charge or remove it during
  bench flashing.
- Confirm the device is in ESP32-S3 bootloader mode.
- Confirm [SPEC.md](SPEC.md) still matches the physical unit and no hardware
  modifications have changed the relevant pins.
- Confirm replacement firmware configuration does not contain public cloud
  endpoints, cloud tokens, vendor credentials, Wi-Fi credentials, or secrets.
- Confirm `.conf`, downloaded firmware, local virtual environments, and backup
  images remain ignored local artifacts.

## Current Automation Coverage

`install.sh` now performs these `feat/01-backup-recovery` tasks:

- Reads and writes installer answers from ignored `.conf`.
- Prompts for bootloader readiness.
- Stages missing local tools only after approval.
- Backs up full 16 MB stock flash in chunks before installing MicroPython.
- Rejects partial stock backups whose byte count does not match the configured
  flash size.
- Restores a saved stock firmware backup with `--restore` or
  `--restore-backup`.
- Keeps generated tools, downloads, and backups under ignored `tools/.local/`
  unless explicitly configured otherwise.
