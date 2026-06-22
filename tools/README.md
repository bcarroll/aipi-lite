# AIPI-Lite Tooling

This directory contains host-side tooling for preparing an AIPI-Lite device over
USB-C. Downloaded tools, virtual environments, and firmware binaries are stored
under the repo-local `.tools/` directory, which is ignored by Git.

## Bootstrap Flashing Tools

Run:

```bash
tools/setup_micropython_tools.sh
```

The script creates `.tools/micropython-venv/`, installs `esptool` and
`mpremote`, downloads the default ESP32-S3 MicroPython firmware image, and prints
the commands needed to erase flash, write MicroPython firmware, and upload the
future `firmware/micropython/` application tree.

Use an explicit serial port when multiple USB serial devices are attached:

```bash
tools/setup_micropython_tools.sh --port /dev/cu.usbmodem31101
```

Override the firmware image URL if the target needs a different MicroPython
build:

```bash
tools/setup_micropython_tools.sh \
  --firmware-url https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20260406-v1.28.0.bin
```

The script does not flash the device automatically. Review the printed commands
and confirm the stock firmware backup exists before erasing or writing flash.
