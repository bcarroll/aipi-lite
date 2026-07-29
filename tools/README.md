# AIPI-Lite Tooling

This directory contains host-side tooling for preparing an AIPI-Lite device over
USB-C. Downloaded tools, virtual environments, and firmware binaries are stored
under `tools/.local/`, which is ignored by Git. External MicroPython library
source that must be uploaded to the device is tracked under `src/lib/`.

The Windows `install.cmd` flow stages a cache-free source tree and copies its
children to the root-stat-safe `mpremote` device-root destination `:/.`, so
startup files land at `/boot.py` and `/main.py` and application modules land
under `/lib`. The install uses guarded cleanup that removes known legacy root
modules and removes a misplaced `/src` tree only when it matches the AIPI-Lite
application manifest. Unknown `/src` content is preserved with a warning.
Cleanup preserves root `boot.py`, `main.py`, and the ignored operator
`local_wifi_config.py`.

Normal uploads connect once before copying. A validation or post-flash upload
that requests a preflight hard reset waits five seconds and reconnects to the
same validated COM port before the copy, ensuring `mpremote` enters raw REPL
through a fresh transport.

Direct Windows uploads persist a validated COM port in the ignored root `.conf`:

```cmd
install.cmd --port COM7 --yes
install.cmd --yes
```

An explicit port has priority and seeds `AIPI_SERIAL_PORT`. Later direct runs
reuse it without `--port`. With no saved value, exactly one detected COM port is
selected and saved automatically; zero or multiple ports require an explicit
selection. Invalid or disconnected saved ports also require an explicit
correction, preventing a silent switch to another device. `--list-ports` does
not modify `.conf`. Saving a resolved port to `.conf` applies only to
`install.cmd`. `dev_install.cmd --inference-probe` still requires an explicit
port. `validate.cmd` reuses the saved `.conf` port (or a sole detected port)
when `--port` is omitted, without persisting a new value.

## Bootstrap Flashing Tools

The full install path is the Windows installer:

```cmd
install.cmd --port COM3 --yes
```

It assumes MicroPython is already flashed on the connected device, prompts
before downloading missing local prerequisites, stores answers in the ignored
root `.conf` file, copies application files to the device root with `mpremote`,
performs the guarded cleanup, and resets the device in that cleanup connection.
A reset failure after confirmed cleanup returns success with a manual
power-cycle warning.

`tools/windows_installer.py` backs the Windows CMD entry points and now also
performs MicroPython firmware flashing with `--flash-micropython`. Flashing
writes the Octal-SPIRAM build `ESP32_GENERIC_S3-SPIRAM_OCT`, which the AIPI-Lite
requires because it has 8 MB of Octal PSRAM; the plain `ESP32_GENERIC_S3` build
leaves the Wi-Fi driver without internal DRAM and fails with `Wifi Out of
Memory`. The `--firmware-url`, `--baud`, and `--skip-erase` flags tune the flash
step:

```cmd
install.cmd --port COM3 --flash-micropython --yes
```

The post-flash upload uses the same hard reset, five-second wait, and same-port
reconnect before copying the application.

Installer prompts are printed explicitly so they remain visible through
`dev_install.cmd` captures. In noninteractive runs, optional prompts use safe
defaults, confirmations default to `no`, and the installer exits instead of
waiting silently. Automated stock-firmware backup and restore are not provided
by the repository scripts; those recovery operations are manual and documented
in RECOVERY.md.

Use the development wrapper when an install run should produce a shareable
transcript for GitHub issue review or hardware validation analysis:

```cmd
dev_install.cmd --gh bcarroll/aipi-lite --gh-title "AIPI-Lite bench-a install capture" --device-label bench-a --hardware-note "captured serial-visible install behavior" -- --port COM3 --yes
```

`dev_install.cmd` stores generated artifacts under `tools\.local\dev-install\`,
which is ignored by Git. Each run includes the raw visible installer transcript,
a redacted transcript, run metadata, and a GitHub-ready Markdown issue body.
`--gh OWNER/REPO` creates a new issue through an already-authenticated `gh` CLI;
bare `--gh` uses `AIPI_GITHUB_REPO` or the local `origin` remote when possible.
`--issue OWNER/REPO#123` comments on an existing issue instead. If GitHub
tooling is missing or unauthenticated, the local issue body remains available
for manual review.

### On-Device Inference Feasibility Capture

Use the opt-in inference mode to upload the current application tree, run the
offline `inference_probe`, and create one redacted GitHub issue with the bench
evidence. It requires an explicit COM port and rejects flash, cleanup, and help
operations so the run stays application-first. It disables generated Wi-Fi
configuration and appends `--no-reset` before running the probe so the normal
Wi-Fi application flow is not started during the capture. Install Python 3 and
the GitHub CLI, authenticate `gh`, then run this from the repository root:

```cmd
gh auth login
dev_install.cmd --inference-probe --gh bcarroll/aipi-lite --device-label bench-a --inference-check display=pass --inference-check status-led=pass --inference-check button=pass --inference-check offline=pass -- --port COM3 --yes
```

The check names are `display`, `status-led`, `button`, and `offline`; each value
is `pass`, `fail`, or `not-observed`. The wrapper does not infer physical
observations that were not supplied. It forces a no-reset application upload,
runs only the offline probe, and writes raw/redacted artifacts plus
`github-issue-body.md` under ignored `tools\.local\dev-install\`. It captures the
stable probe serial lines, feasibility decision, and operator checks in the
redacted issue body while keeping raw output, the local artifact path, and COM
port local. It creates a new issue only with `--gh`; `--prepare-only` skips the
GitHub create step. A missing or unauthenticated `gh` CLI leaves the redacted
body local without masking the actual installer or probe exit status. The issue
body excludes COM ports, secrets, MAC addresses, and local paths.

### Windows Physical Device Validation

Use the dedicated Windows validation command to run the self-contained physical
probes and create one redacted GitHub issue for each run:

```cmd
gh auth login
validate.cmd --port COM8 --yes --device-label bench-a
```

The command hard-resets the device, waits five seconds, reconnects to the same
validated COM port, uploads `src/`, then runs the display, GPIO status/button,
codec, capture, playback, local Wi-Fi/health, and offline inference probes
through one raw-REPL probe session. It emits a per-probe result, continues after
a device-side probe failure so the report contains all available evidence, and
avoids reconnecting between probes. It does not reset into normal startup after
the upload. After the sequence, answer the prompts with `pass`, `fail`, or
`not-observed` for each physical observation. Only an all-pass run exits
successfully.

The `wifi` probe connects to the operator-configured local network and calls the
local `/health` endpoint, so a passing run requires an uploaded
`src/local_wifi_config.py` and a reachable local mock service
(`python3 -m service.mock_service ...`). Without both, the `wifi` probe fails and
the aggregate status is non-zero.

Each parsed run writes raw/redacted transcripts, metadata, and a GitHub-ready
body under ignored `tools\.local\device-validation\`. The target repository is
`AIPI_GITHUB_REPO` when it is valid; otherwise it is derived from `origin`.
For an application upload failure, that body contains at most 12 redacted
high-signal diagnostics; the complete transcript remains local. Missing or
unauthenticated `gh` leaves the body local and reports the publishing failure
without changing the measured validation result. The workflow includes the local
Wi-Fi/health check but excludes full push-to-talk validation and does not flash
firmware, erase flash, or drive GPIO10.

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
