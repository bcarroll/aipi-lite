# aipi-lite

Local-only replacement firmware work for the XORIGIN AI PI-Lite / AIPI Lite.

## Current MicroPython Workflow

Use the repository installer to resolve the latest stable ESP32-S3 MicroPython
firmware, flash it, and upload the current application baseline:

```bash
./install.sh --port /dev/cu.usbmodem31101
```

If local prerequisites are missing, the installer prompts before downloading or
installing components under ignored `tools/.local/`, then continues with the
flash and upload workflow after approval.

Installer answers are stored in a root `.conf` file, which is ignored by Git.
The script reads that file on later runs for values such as serial port,
download approval, bootloader confirmation, flash approval, backup path, and
reset preference.

Run without `--port` to let `esptool` and `mpremote` auto-detect the attached
device:

```bash
./install.sh
```

Use a specific MicroPython firmware build when the latest standard
ESP32_GENERIC_S3 image is not the right target:

```bash
./install.sh --port /dev/cu.usbmodem31101 \
  --firmware-url https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20260406-v1.28.0.bin
```

Before erasing or writing flash, the installer now requires bootloader
confirmation and backs up the 16 MB stock flash image to `tools/.local/backups/`
unless `.conf` points at an existing backup.

The user still needs to put the AIPI-Lite into ESP32-S3 bootloader mode and
connect the device over USB-C because those are physical actions.

Bootloader access currently requires removing the four back screws, pressing the
button under the display while plugging the device into USB-C, and confirming
that the screen remains black.

After flashing and copying `src/`, the installer attempts to reset the device.
Set `AIPI_RESET_AFTER_UPLOAD=no` in `.conf` or pass `--no-reset` to skip that
step.

Backup, restore, expected output, and safety details are documented in
[RECOVERY.md](RECOVERY.md).

See [tools/README.md](tools/README.md) for lower-level setup tooling.

## MicroPython Application Skeleton

The MicroPython source under `src/` now provides the first safe application
skeleton:

- `src/boot.py`
- `src/main.py`
- `src/pins.py`
- `src/aipi_lite_config.py`
- `src/lib/st7735/`

`boot.py` emits serial-visible safe startup status without constructing GPIO
pins or touching GPIO10 board-power control. `main.py` prints the bring-up
sequence and retains the imported TFT display demo as a best-effort baseline.
`pins.py` centralizes the documented pin map for later hardware probe branches.

See [src/README.md](src/README.md) for firmware image selection, upload, serial
log, and safety notes for the MicroPython application tree.

## Host-side tests

Run the host-side regression tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

These tests use local stubs for MicroPython-only modules so they can validate the
implemented display baseline and setup tooling without an attached AIPI-Lite
device.
