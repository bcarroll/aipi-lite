# AIPI-Lite Backup and Recovery

Target device: XORIGIN AI PI-Lite / AIPI Lite, model `XY006PL01`

Use this procedure when preserving a stock recovery image matters before
replacing firmware. Firmware backup files may contain vendor provisioning data,
local configuration, or device identifiers. Keep them out of Git and store them
as local operational artifacts.

## Bootloader Mode

The AIPI-Lite must be in ESP32-S3 bootloader mode for stock backup, explicit
firmware flash, or restore operations. The default application upload path
assumes MicroPython is already running and does not use bootloader mode.

1. Remove the four back screws from the AIPI-Lite.
2. Hold the BOOT button under the display.
3. Plug the device into USB-C while holding BOOT.
4. Confirm the screen remains black.
5. Use `--port` if more than one USB serial device is attached.

## Stock Firmware Backup

Normal application installs skip the stock backup and assume the device already
runs compatible ESP32_GENERIC_S3 MicroPython firmware. When a fresh stock
recovery image is required before replacing firmware, use the installer's
explicit flash path with opt-in backup. It prompts for bootloader confirmation,
verifies the ROM bootloader answers `esptool chip-id` without auto-reset, stores
answers in ignored `.conf`, then backs up the full 16 MB flash in smaller chunks
before it erases or writes replacement firmware:

```bash
./install.sh --port /dev/cu.usbmodem31101 --flash-micropython --backup-stock
```

By default, backups are written under:

```text
tools/.local/backups/
```

Use a specific backup destination when needed:

```bash
./install.sh \
  --port /dev/cu.usbmodem31101 \
  --flash-micropython \
  --backup-stock \
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
  --flash-micropython \
  --backup-stock \
  --backup-chunk-size 0x40000
```

During installer backups, failed chunks are retried at smaller sizes down to
`0x1000` / 4 KiB, and the installer avoids resetting the chip between backup
chunks. If a failure repeats at `0x00100000` after those smaller retries, treat
it as an address-specific failure at the stock app region or as evidence that
the USB transport is still unstable. With `--trace`, the installer records
`event=stock_backup_blocked` with the failing offset, final retry chunk size,
selected serial port, backup path, and flash size.

When `hardware validation status: blocked` appears during a
`--flash-micropython --backup-stock` run, re-enter ESP32-S3 bootloader mode, use
a direct known-data USB-C cable, try a different host USB port, and rerun with
the reported `--port` plus
`--backup-chunk-size 0x40000 --backup-min-chunk-size 0x1000`. On WSL, detach and
reattach the USB device to WSL, then verify the `/dev/ttyS*` port before
retrying. Rerun with `--flash-micropython` but without `--backup-stock` only
when stock recovery is not required.

Existing `--skip-backup` and `AIPI_SKIP_STOCK_BACKUP=1` remain accepted for
explicit application-first flash runs. They are not stored in `.conf`, and the
installer still requires the normal erase/write confirmation.

Manual backup is also possible after staging tools:

```bash
tools/setup_micropython_tools.sh --skip-firmware --skip-libraries
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/cu.usbmodem31101 \
  flash-id
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/cu.usbmodem31101 \
  read-flash 0 0x1000000 tools/.local/backups/aipi-lite-stock.bin
```

Expected backup indicators:

- `esptool` detects an ESP32-S3.
- `flash-id` reports a flash chip without connection errors.
- `read-flash` reaches 100 percent for every chunk and writes a complete
  16 MB / `16777216` byte `.bin` file.
- A repeated failure at the same chunk offset is reported with the offset and
  the minimum retry size that was attempted.
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

- If `--backup-stock` is used, confirm the stock firmware backup exists and is
  non-empty before relying on it for recovery.
- If a backup exists, confirm it is not staged in Git: `git status --short`.
- If the normal upload-only install path is used, confirm ESP32_GENERIC_S3
  MicroPython is already flashed and running on the device.
- If explicit firmware flashing is used without `--backup-stock`, confirm the
  operator accepts that stock firmware recovery may be unavailable.
- Confirm the device is on stable USB power.
- If using the battery module, confirm it has enough charge or remove it during
  bench flashing.
- For backup, flash, or restore operations, confirm the device is in ESP32-S3
  bootloader mode; the installer also verifies this with `esptool chip-id`
  before backup, erase, write, or restore commands.
- Confirm [SPEC.md](SPEC.md) still matches the physical unit and no hardware
  modifications have changed the relevant pins.
- Confirm replacement firmware configuration does not contain public cloud
  endpoints, cloud tokens, vendor credentials, Wi-Fi credentials, or secrets.
- Confirm `.conf`, downloaded firmware, local virtual environments, and backup
  images remain ignored local artifacts.

## Current Automation Coverage

`install.sh` now performs these `feat/01-backup-recovery` tasks:

- Reads and writes installer answers from ignored `.conf`.
- Uploads application source by default to an existing ESP32_GENERIC_S3
  MicroPython runtime without backing up, erasing, or flashing firmware.
- Skips Git self-update by default; `--self-update` is available for intentional
  pull-and-restart runs.
- Prompts for bootloader readiness during explicit flash and restore flows.
- Verifies the ESP32-S3 ROM bootloader responds before backup, erase, write, or
  restore operations.
- Stages missing local tools only after approval.
- Skips stock backup by default for application-first MicroPython uploads.
- Backs up full 16 MB stock flash in chunks before installing MicroPython when
  `--flash-micropython --backup-stock` or `AIPI_FLASH_MICROPYTHON=1`
  with `AIPI_BACKUP_STOCK_FIRMWARE=1` is supplied.
- Rejects partial stock backups whose byte count does not match the configured
  flash size.
- Retries failed backup chunks at smaller sizes without resetting the chip
  between chunk reads.
- Keeps existing non-persistent `--skip-backup` /
  `AIPI_SKIP_STOCK_BACKUP=1` compatibility for explicit application-first runs.
- Restores a saved stock firmware backup with `--restore` or
  `--restore-backup`.
- Keeps generated tools, downloads, and backups under ignored `tools/.local/`
  unless explicitly configured otherwise.
