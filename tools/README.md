# AIPI-Lite Tooling

This directory contains host-side tooling for preparing an AIPI-Lite device over
USB-C. Downloaded tools, virtual environments, firmware binaries, and staged
MicroPython libraries are stored under `tools/.local/`, which is ignored by Git.

## Bootstrap Flashing Tools

The preferred full install path is the repository root installer:

```bash
./install.sh --port /dev/cu.usbmodem31101
```

It resolves the latest stable ESP32-S3 MicroPython firmware, prompts before
downloading missing local prerequisites, stores answers in the ignored root
`.conf` file, backs up stock firmware, flashes the connected device, copies
application source with `mpremote`, and resets the device when possible.

Use the setup script directly when you only want to stage tools, firmware, and
libraries without flashing:

Run:

```bash
tools/setup_micropython_tools.sh
```

The script creates `tools/.local/micropython-venv/`, installs `esptool` and
`mpremote`, downloads the default ESP32-S3 MicroPython firmware image, stages the
MicroPython libraries needed by the AIPI-Lite firmware, and prints the commands
needed to erase flash, write MicroPython firmware, upload libraries to `/lib`,
and upload the `src/` application tree.

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

## Staged MicroPython Libraries

The current setup script downloads the ST7735R display driver bundle from
`micropython-nano-gui` into:

```text
tools/.local/micropython-libs/lib/drivers/
```

That bundle covers the AIPI-Lite TFT LCD driver dependency. The first firmware
bring-up expects other device capabilities to come from MicroPython built-ins:
`machine`, `network`, `socket`, `framebuf`, `neopixel`, and `machine.I2S`.

The downloaded display driver source is MIT licensed; the script also downloads
the upstream license into `tools/.local/micropython-libs/metadata/`.
