# AIPI-Lite Tooling

This directory contains host-side tooling for preparing an AIPI-Lite device over
USB-C. Downloaded tools, virtual environments, and firmware binaries are stored
under `tools/.local/`, which is ignored by Git. External MicroPython library
source that must be uploaded to the device is tracked under `src/lib/`.

## Bootstrap Flashing Tools

The preferred full install path is the repository root installer:

```bash
./install.sh --port /dev/cu.usbmodem31101
```

It assumes ESP32_GENERIC_S3 MicroPython is already flashed on the connected
device, prompts before downloading missing local prerequisites, stores answers
in the ignored root `.conf` file, copies application source with `mpremote`, and
resets the device when possible. Normal installs do not run `git pull`, back up
stock firmware, erase flash, or write a MicroPython firmware image. Use
`--self-update` only when an intentional `git pull --ff-only` and restart is
wanted.
Before explicit flash-sensitive operations, it verifies the ESP32-S3 ROM
bootloader responds to `esptool chip-id` without auto-reset. Add
`--flash-micropython --backup-stock` or set `AIPI_FLASH_MICROPYTHON=1` and
`AIPI_BACKUP_STOCK_FIRMWARE=1` when a fresh stock recovery image is required
before flashing.
Installer prompts are printed explicitly so they remain visible through
`dev_install.sh` captures. In noninteractive runs, optional prompts use safe
defaults, confirmations default to `no`, and the installer exits instead of
waiting silently.
Existing `--skip-backup` and `AIPI_SKIP_STOCK_BACKUP=1` remain accepted for
explicit application-first install runs.

Use the development wrapper when an install run should produce a shareable
transcript for GitHub issue review or hardware validation analysis:

```bash
./dev_install.sh \
  --gh \
  --gh-title "AIPI-Lite bench-a install capture" \
  --device-label bench-a \
  --hardware-note "captured serial-visible install behavior" \
  -- --port /dev/cu.usbmodem31101
```

`dev_install.sh` stores generated artifacts under
`tools/.local/dev-install/`, which is ignored by Git. Each run includes the raw
visible installer transcript, a redacted transcript, run metadata, and a
GitHub-ready Markdown issue body. `--gh OWNER/REPO` creates a new issue through
an already-authenticated `gh` CLI; bare `--gh` uses `AIPI_GITHUB_REPO` or the
local `origin` remote when possible. `--issue OWNER/REPO#123` comments on an
existing issue instead. Installer help captures and known stock-backup-blocked
captures are kept local instead of creating automatic issues; use `--issue`
after bench triage when one should be attached to a chosen tracker. If GitHub
tooling is missing or unauthenticated, the local issue body remains available
for manual review.

### On-Device Inference Feasibility Capture

Use the opt-in inference mode to upload the current application tree, run the
offline `inference_probe`, and create one redacted GitHub issue with the bench
evidence. It requires an explicit serial port and rejects flash, restore,
backup, cleanup, help, and self-update operations so the run stays
application-first.

```bash
./dev_install.sh \
  --inference-probe \
  --gh \
  --device-label bench-a \
  --inference-check display=pass \
  --inference-check status-led=pass \
  --inference-check button=pass \
  --inference-check offline=pass \
  -- --port /dev/cu.usbmodem31101
```

The check names are `display`, `status-led`, `button`, and `offline`; each
value is `pass`, `fail`, or `not-observed`. The wrapper does not infer physical
observations that were not supplied. It captures the stable probe serial lines,
feasibility decision, and operator checks in the redacted issue body while
keeping raw output, the local artifact path, and serial-device path local.
`--prepare-only` skips the GitHub create step. A missing or unauthenticated
`gh` CLI also leaves the redacted body local without masking the actual
installer or probe exit status. Set `AIPI_DEV_MPREMOTE` only when an alternate
local `mpremote` command is required, such as host-side test fixtures.

For deeper hardware feedback, pass installer tracing through the wrapper:

```bash
./dev_install.sh --trace -- --port /dev/cu.usbmodem31101
```

Trace mode enables installer debug logging and writes a separate redacted trace
file under `tools/.local/debug/`. The trace records phase transitions,
firmware metadata and checksum for explicit flash runs, prerequisite state,
best-effort esptool target identity for explicit flash/restore runs,
MicroPython/mpremote probes, upload inventory, command exit statuses, and reset
status. It does not commit firmware dumps or local secrets.

To force a clean prerequisite setup without deleting operational artifacts, run:

```bash
./install.sh --clean-tools
```

The cleanup removes `tools/.local/micropython-venv/`,
`tools/.local/downloads/firmware/`, and other ignored prerequisite artifacts.
It preserves tracked MicroPython libraries in `src/lib/`, stock backups in
`tools/.local/backups/`, debug logs in `tools/.local/debug/`, and developer
install captures in `tools/.local/dev-install/`. Use
`./dev_install.sh --clean-tools` when the cleanup transcript should be captured
for issue review.

Use the setup script directly when you only want to stage tools, firmware, and
libraries without flashing:

Run:

```bash
tools/setup_micropython_tools.sh
```

The script creates `tools/.local/micropython-venv/`, installs `esptool` and
`mpremote`, downloads the default ESP32-S3 MicroPython firmware image, stages
the MicroPython libraries under `src/lib/`, and prints the commands needed to
erase flash, write MicroPython firmware, and upload the `src/` application tree.

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
before erasing or writing flash. If stock recovery is required, create and
verify a stock firmware backup before flashing.

## Staged MicroPython Libraries

The current setup script stages the ST7735R display driver bundle from
`micropython-nano-gui` in tracked source:

```text
src/lib/drivers/
```

That bundle is uploaded as part of the normal `src/` application tree and covers
the AIPI-Lite TFT LCD driver dependency. The first firmware bring-up expects
other device capabilities to come from MicroPython built-ins:
`machine`, `network`, `socket`, `framebuf`, `neopixel`, and `machine.I2S`.

The downloaded display driver source is MIT licensed; the script also downloads
the upstream license into `src/lib/metadata/`.
