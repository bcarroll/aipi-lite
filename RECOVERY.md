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

## Application Recovery

For ordinary application recovery on a device that already runs MicroPython, use
the Windows installer to re-upload the current `src/` application tree:

```cmd
install.cmd --port COM3 --yes
```

This does not use bootloader mode, back up firmware, erase flash, or write a
MicroPython image. It only reinstalls the application source.

## MicroPython Firmware Flashing

The Windows installer can flash MicroPython firmware. Use explicit flashing when
the connected device needs MicroPython installed or replaced:

```cmd
install.cmd --port COM3 --flash-micropython --yes
```

Flashing selects and writes the Octal-SPIRAM build
`ESP32_GENERIC_S3-SPIRAM_OCT`. This build is required because the AIPI-Lite has
8 MB of Octal PSRAM (see [SPEC.md](SPEC.md)). The plain `ESP32_GENERIC_S3` build
leaves the ESP-IDF Wi-Fi driver without internal DRAM, so Wi-Fi init fails
instantly with `Wifi Out of Memory`. Writing the SPIRAM_OCT build is the fix for
that failure.

Flash-related flags:

- `--flash-micropython` performs the flash before the application upload.
- `--firmware-url URL` overrides the firmware image; the default is the latest
  SPIRAM_OCT build.
- `--baud RATE` sets the flash baud rate (default `460800`).
- `--skip-erase` skips the pre-flash chip erase.

After writing firmware, the installer hard-resets the device into MicroPython,
waits for it to reboot and its USB serial port to re-enumerate, then resets once
more over `mpremote` before uploading the application in the same run.

The operator must place the device in ESP32-S3 bootloader mode and connect it
over USB-C before flashing, because those are physical actions.

## Stock Firmware Backup (manual only)

Stock-firmware backup is not automated by the repository scripts. When a fresh
stock recovery image is required before replacing firmware, perform the backup
manually and out-of-band with `esptool` after staging tools:

```bash
tools/setup_micropython_tools.sh --skip-firmware --skip-libraries
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/ttyUSB0 \
  flash-id
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/ttyUSB0 \
  read-flash 0 0x1000000 tools/.local/backups/aipi-lite-stock.bin
```

This is a manual recovery procedure, not a supported repository command. Adjust
the `--port` value for the host that performs the backup.

By default, keep backups under an ignored local path such as:

```text
tools/.local/backups/
```

A complete stock image for this device is `0x1000000` / `16777216` bytes. Treat
a partial transfer, for example `1048576/16777216` bytes, as incomplete and read
it again rather than relying on it. If `read-flash` stalls on a specific USB
setup, use a smaller chunk size with esptool's `--flash-size`/read options, a
direct known-good USB-C cable, and a different host USB port before retrying.

Expected backup indicators:

- `esptool` detects an ESP32-S3.
- `flash-id` reports a flash chip without connection errors.
- `read-flash` reaches 100 percent and writes a complete
  16 MB / `16777216` byte `.bin` file.
- The backup file remains under ignored `tools/.local/` or another location
  outside source control.

## Stock Firmware Restore (manual only)

Stock-firmware restore is not automated by the repository scripts either.
Restore a previously saved stock image manually with `esptool`:

```bash
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/ttyUSB0 \
  erase_flash
tools/.local/micropython-venv/bin/python -m esptool \
  --chip esp32s3 \
  --port /dev/ttyUSB0 \
  --baud 460800 \
  write_flash 0 tools/.local/backups/aipi-lite-stock.bin
```

This is a manual recovery procedure, not a supported repository command.

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

- If a manual stock backup is used, confirm the stock firmware backup exists and
  is non-empty before relying on it for recovery.
- If a backup exists, confirm it is not staged in Git: `git status --short`.
- If the normal upload-only install path is used, confirm MicroPython is already
  flashed and running on the device.
- If MicroPython firmware is flashed without a manual stock backup, confirm the
  operator accepts that stock firmware recovery may be unavailable.
- Confirm the device is on stable USB power.
- If using the battery module, confirm it has enough charge or remove it during
  bench flashing.
- For backup, flash, or restore operations, confirm the device is in ESP32-S3
  bootloader mode.
- Confirm [SPEC.md](SPEC.md) still matches the physical unit and no hardware
  modifications have changed the relevant pins.
- Confirm replacement firmware configuration does not contain public cloud
  endpoints, cloud tokens, vendor credentials, Wi-Fi credentials, or secrets.
- Confirm `.conf`, downloaded firmware, local virtual environments, and backup
  images remain ignored local artifacts.

## Current Automation Coverage

The Windows installer (`install.cmd`, backed by `tools/windows_installer.py`)
covers these operations:

- Reads and writes installer answers from ignored `.conf`.
- Uploads application source to a MicroPython runtime by default without backing
  up, erasing, or flashing firmware.
- Flashes the `ESP32_GENERIC_S3-SPIRAM_OCT` MicroPython build with
  `--flash-micropython`, honoring `--firmware-url`, `--baud`, and `--skip-erase`.
- Stages missing local tools only after approval.
- Keeps generated tools, downloads, and backups under ignored `tools/.local/`
  unless explicitly configured otherwise.

Automated stock-firmware backup and restore are not provided by the repository
scripts. Those recovery operations must be performed manually and out-of-band as
described above.
