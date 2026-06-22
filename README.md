# aipi-lite

Local-only replacement firmware work for the XORIGIN AI PI-Lite / AIPI Lite.

## Current MicroPython Workflow

Use the repository tooling to download host tools, the selected MicroPython
firmware image, and staged MicroPython libraries:

```bash
tools/setup_micropython_tools.sh
```

The script creates ignored artifacts under `tools/.local/`, installs `esptool`
and `mpremote`, downloads the default ESP32-S3 MicroPython firmware image, and
prints the commands for erasing flash, writing firmware, opening a REPL, and
uploading libraries or application source.

Use an explicit USB serial port when needed:

```bash
tools/setup_micropython_tools.sh --port /dev/cu.usbmodem31101
```

Use a specific MicroPython firmware build when the default image is not the
right target:

```bash
tools/setup_micropython_tools.sh \
  --firmware-url https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20260406-v1.28.0.bin
```

The setup script does not flash automatically. Before erasing or writing flash:

- Back up the stock firmware.
- Put the AIPI-Lite into ESP32-S3 bootloader mode.
- Connect the device over USB-C.

Bootloader access currently requires removing the four back screws, pressing the
button under the display while plugging the device into USB-C, and confirming
that the screen remains black.

See [tools/README.md](tools/README.md) for the full tooling workflow.

## Imported Display Baseline

The imported MicroPython source currently provides an early TFT display demo:

- `main.py`
- `aipi_lite_config.py`
- `lib/st7735/`

This baseline is retained as hardware evidence and will be moved or wrapped into
the planned `firmware/micropython/` application layout.

## Host-side tests

Run the host-side regression tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

These tests use local stubs for MicroPython-only modules so they can validate the
implemented display baseline and setup tooling without an attached AIPI-Lite
device.
