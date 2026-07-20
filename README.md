# aipi-lite

Local-only replacement firmware work for the XORIGIN AI PI-Lite / AIPI Lite.

## Current MicroPython Workflow

Use the repository installer to upload the current application baseline to an
AIPI-Lite that already has ESP32_GENERIC_S3 MicroPython flashed:

```bash
./install.sh --port /dev/cu.usbmodem31101
```

The installer does not run `git pull` by default. Use `--self-update` or
`AIPI_INSTALL_SELF_UPDATE=1` only when you intentionally want it to run
`git pull --ff-only` and restart itself before installer actions.

For issue reporting or future troubleshooting context, add `--debug` to keep a
sanitized installer transcript and environment summary under
`tools/.local/debug/`:

```bash
./install.sh --debug --port /dev/cu.usbmodem31101
```

The debug file path is printed during the run. Use `--debug-file FILE` when a
specific GitHub issue artifact path is needed. The generated file redacts common
secrets, credentials, SSIDs, tokens, and MAC-like identifiers before writing the
transcript.

Use `--trace` when a hardware or firmware install run needs deeper feedback for
improvement. Trace mode enables `--debug` and writes a separate redacted trace
artifact under `tools/.local/debug/` with installer phase transitions,
prerequisite status, MicroPython/mpremote runtime probes, source upload
inventory, command exit statuses, and reset status. Explicit firmware flashing
runs also include firmware path/size/checksum metadata and best-effort esptool
target identity probes:

```bash
./install.sh --trace --port /dev/cu.usbmodem31101
```

Use `--trace-file FILE` when a specific local trace path is needed. Trace files
remain ignored local artifacts and must be reviewed before sharing; the
installer redacts common secrets, credentials, SSIDs, tokens, and MAC-like
identifiers but does not commit or copy firmware dumps.

Use `--clean-tools` when you need to remove downloaded prerequisite artifacts
before a fresh setup run:

```bash
./install.sh --clean-tools
```

This removes the local MicroPython virtual environment, downloaded firmware
cache, and other ignored prerequisite artifacts under `tools/.local/`. It
preserves tracked MicroPython libraries in `src/lib/`, stock firmware backups,
installer debug logs, and developer install captures. `--clean-prereqs` is
accepted as an alias.

For development-team install captures and future hardware validation runs, use
`dev_install.sh`. It runs the same `install.sh` path, passes installer arguments
through unchanged, shows installer output interactively, and stores raw,
redacted, metadata, and GitHub issue-body artifacts under ignored
`tools/.local/dev-install/`:

```bash
./dev_install.sh \
  --device-label bench-a \
  --hardware-note "display probe readable after install" \
  -- --port /dev/cu.usbmodem31101
```

Add `--issue OWNER/REPO#NUMBER` or a GitHub issue URL to post the redacted issue
body as a comment when the `gh` CLI is already installed and authenticated. Use
`--gh OWNER/REPO` to create a new GitHub issue from the same redacted body, or
use bare `--gh` to read the repository from `AIPI_GITHUB_REPO` or the local
`origin` remote. Add `--gh-title TITLE` when a specific issue title is useful.
Installer help captures and known stock-backup-blocked install captures stay
local instead of creating automatic issues; use `--issue OWNER/REPO#NUMBER`
after bench triage to append one to a chosen tracking issue.
If GitHub tooling is missing, unauthenticated, or `--prepare-only` is supplied,
the script leaves the issue body locally for inspection or manual submission.
The wrapper returns the installer exit status so capture or posting problems do
not mask install failures. The same cleanup option can be captured by running
`./dev_install.sh --clean-tools`. For deeper hardware feedback, run the wrapper
with `--trace -- ...` so the visible transcript records the local trace artifact
path while the installer writes detailed trace data under `tools/.local/debug/`.
See [DEVELOPER.md](DEVELOPER.md) for the concise connected-device test and
GitHub reporting workflow.

### Windows CMD workflow

Windows 10 or later operators can use native Command Prompt entry points for
the same application-first upload path. Install Python 3 for Windows with the
`py` launcher (or make `python` available on `PATH`), connect the already
MicroPython-flashed AIPI-Lite by USB-C, then identify its `COM` port:

```cmd
install.cmd --list-ports
install.cmd --port COM3 --yes
```

The first normal run creates an ignored local virtual environment under
`tools\.local\micropython-venv` and installs `mpremote`. `--yes` explicitly
approves that prerequisite setup; omit it to receive an interactive prompt.
The upload stages a cache-free copy of `src\` and copies its children to device
root, producing `/boot.py`, `/main.py`, and `/lib` rather than `/src`. It removes
the known legacy root-level application modules that were moved under `/lib`.
When an earlier Windows install created `/src`, the installer removes it only
when its files match the AIPI-Lite application manifest; unknown `/src` content
is preserved with a warning. This cleanup prevents old root modules from
shadowing current `/lib` firmware and preserves root `boot.py`, `main.py`, and
ignored `local_wifi_config.py`.

Cleanup and reset share one `mpremote` connection. If cleanup succeeds but
`mpremote` cannot confirm reset, installation still succeeds and prints a
warning to unplug and reconnect USB-C before use. Add `--no-reset` to leave the
device without a startup reset after the copy and cleanup.

For local developer captures, use `dev_install.cmd` with its installer options
after `--`:

```cmd
dev_install.cmd --device-label bench-a --hardware-note "display readable" -- --port COM3 --yes
```

It displays installer output and writes raw and redacted transcripts plus
non-secret metadata under ignored `tools\.local\dev-install\`. Use
`--prepare-only` to create those local artifacts without uploading to a device.
For an offline inference feasibility run that independently publishes its
redacted report, use the Windows developer wrapper with a locally authenticated
GitHub CLI:

```cmd
gh auth login
dev_install.cmd --inference-probe --gh bcarroll/aipi-lite --device-label bench-a --inference-check display=pass --inference-check status-led=pass --inference-check button=pass --inference-check offline=pass -- --port COM3 --yes
```

Inference mode forces a no-reset application upload, runs the explicit offline
probe, and creates one new GitHub issue only when `--gh` is supplied. It does
not configure Wi-Fi, call an endpoint, load a model, play speaker audio, back
up firmware, or flash firmware. The published body excludes raw transcripts,
COM ports, secrets, MAC addresses, and local paths. If `gh` is unavailable or
cannot create the issue, the redacted `github-issue-body.md` remains under
ignored `tools\.local\dev-install\` and the installer/probe result is
preserved. Windows still does not support firmware flashing, backup, restore,
or trace artifacts; use the Unix scripts for those workflows.

If local prerequisites are missing, the installer prompts before downloading or
installing components under ignored `tools/.local/`, then continues with the
upload workflow after approval. The default setup path installs `mpremote`,
ensures external MicroPython library source exists under `src/lib/`, and skips
downloading a MicroPython firmware image.
Prompts are written explicitly so they remain visible through `dev_install.sh`
captures. If stdin is not interactive, the installer uses safe defaults for
optional prompts, treats confirmations as `no`, and exits instead of waiting
silently.

Installer answers are stored in a root `.conf` file, which is ignored by Git.
The script reads that file on later runs for values such as serial port,
download approval, upload approval, bootloader confirmation for explicit flash
or restore runs, flash approval, backup path, reset preference, and optional
local Wi-Fi config generation values.
Run `./install.sh --list-env` to print the supported environment override names
without expanding the main help screen.

Run `./install.sh --list-ports` to probe available serial ports before an
upload. The diagnostic uses the repo-local `mpremote` when it is installed,
reports responsive MicroPython ports, and falls back to raw serial candidates
when no MicroPython device responds. On WSL, Windows names such as `COM8`
usually need the Linux device path, such as `/dev/ttyS8` when that mapping is
available, or a USB serial attachment that appears as `/dev/ttyACM*` or
`/dev/ttyUSB*`.

Run without `--port` to have the installer run the same discovery routine before
falling back to `mpremote` auto-detect. If exactly one responsive MicroPython
device is found, the installer stores and uses that port for the upload:

```bash
./install.sh
```

Use explicit firmware flashing only when the connected device needs
ESP32_GENERIC_S3 MicroPython installed or replaced:

```bash
./install.sh --port /dev/cu.usbmodem31101 --flash-micropython
```

Use a specific MicroPython firmware build when the latest standard
ESP32_GENERIC_S3 image is not the right target:

```bash
./install.sh --port /dev/cu.usbmodem31101 \
  --flash-micropython \
  --firmware-url https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20260406-v1.28.0.bin
```

In `--flash-micropython` and restore modes, `esptool` auto-detection can record
a successful ESP32-S3 bootloader port in `.conf` and reuse it for backup
retries, erase, and flash commands so later steps do not rescan every host
serial device.

Before backing up, erasing, writing, or restoring firmware, the installer
requires bootloader confirmation and verifies the ROM bootloader answers
`esptool chip-id` without auto-reset. If that check fails, the installer prints
the bootloader steps and stops before stock backup, erase, write, or restore
operations. Normal installs skip stock backup and firmware flashing so an
already-prepared MicroPython device can receive only the application source.
Recovery-focused runs can add `--flash-micropython --backup-stock` or set
`AIPI_FLASH_MICROPYTHON=1` and `AIPI_BACKUP_STOCK_FIRMWARE=1` to read the
16 MB stock flash image to `tools/.local/backups/` before explicit firmware
flashing. Existing `--skip-backup` and `AIPI_SKIP_STOCK_BACKUP=1` remain
accepted for explicit application-first flash runs.

When `--flash-micropython --backup-stock` is used, the backup read is chunked by
default so a failed transfer cannot be mistaken for a complete stock image on
the next run. If a backup stalls on a specific USB setup, reduce the chunk size
with `--backup-chunk-size 0x40000` or set `AIPI_BACKUP_CHUNK_SIZE=0x40000` in
`.conf`. The installer also retries failed backup chunks down to 4 KiB without
resetting the chip between chunks; a repeat failure at the same offset should be
treated as an address-specific read failure or an unstable USB path. In
`--trace` mode the installer records this as `event=stock_backup_blocked`,
including the failing offset, final retry chunk size, selected port, backup
path, and flash size. Rerun with `--flash-micropython` but without
`--backup-stock` only when stock recovery is not required.

The user still needs to put the AIPI-Lite into ESP32-S3 bootloader mode for
explicit firmware flash or restore operations, and connect the device over
USB-C because those are physical actions.

Bootloader access currently requires removing the four back screws, pressing the
button under the display while plugging the device into USB-C, and confirming
that the screen remains black.

The Unix installer maps each file under `src/` directly to device root, filters
host cache artifacts, and uses the same guarded `/src` and legacy-module
cleanup as the Windows installer. Cleanup and reset share one `mpremote`
connection. If cleanup succeeds but reset cannot be confirmed, installation
succeeds with a manual power-cycle warning. Set `AIPI_RESET_AFTER_UPLOAD=no` in
`.conf` or pass `--no-reset` to skip reset while retaining cleanup.

Backup, restore, expected output, and safety details are documented in
[RECOVERY.md](RECOVERY.md).

See [tools/README.md](tools/README.md) for lower-level setup tooling.

## MicroPython Application

The MicroPython source under `src/` now provides the normal local-only
push-to-talk application and opt-in hardware/service probes:

- `src/boot.py`
- `src/main.py`
- ignored `src/local_wifi_config.py` when local Wi-Fi/service settings are
  configured
- application component modules under `src/lib/*.py`
- `src/lib/inference_probe.py`
- `src/lib/st7735/`
- `src/lib/drivers/`

`boot.py` emits serial-visible safe startup status without constructing GPIO
pins or touching GPIO10 board-power control. `main.py` prints the bring-up
sequence, drives GPIO9 speaker enable low, renders the boot screen, initializes
available LED/display outputs, connects Wi-Fi and the local service through the
push-to-talk controller, and then polls GPIO42 for press/release events. When a
local Wi-Fi configuration is present but its network or service is unavailable,
it completes
startup in an explicit offline state and still polls GPIO42. The LCD shows an
`OFFLINE` label with a red status dot; pressing the button retries the local
connection without recording, and a second press can start recording after a
successful reconnect. `ONLINE` uses the same explicit text plus a green status
dot. Other startup failures still print the failure type and render a visible
error state when display or LED output is available. The remaining application
modules now live under `src/lib/`, which is uploaded to device `/lib` so
MicroPython can import them by bare module name. `pins.py` centralizes the
documented pin map for later hardware probe branches. `aipi_lite_config.py`
remains as a compatibility shim for the imported display baseline. `es8311.py`
provides codec I2C control and the speaker amplifier gate; `audio_probe.py` is
the opt-in ES8311 hardware probe. `audio_capture.py` and `capture_probe.py` add
bounded 16 kHz 16-bit mono microphone capture and WAV packaging helpers for the
ES8311/I2S path. The codec derives its internal clock from standard MicroPython
BCLK rather than an application-driven MCLK pin. `audio_playback.py` and
`playback_probe.py` add bounded 16 kHz 16-bit mono PCM/WAV speaker playback and
a generated low-volume tone probe.
`service_contract.py` and `service_client.py` define the local assistant service
API and client. `assistant_state.py`, `push_to_talk.py`, and `reliability.py`
add the local-only assistant state machine, push-to-talk exchange flow, bounded
retries, diagnostics, and conservative power observations. `version.py` records
MVP metadata. `wifi_probe.py` connects only to configured local Wi-Fi and calls
only a local `/health` endpoint after endpoint policy validation passes.
`inference_probe.py` runs an opt-in offline-first on-device inference
feasibility probe without Wi-Fi, cloud calls, model downloads, or speaker
output. External MicroPython display driver source is tracked under
`src/lib/drivers/` so a normal application upload includes it.

The GPIO status/input probe remains opt-in so normal boot stays recoverable. To
cycle the GPIO46 WS2812/NeoPixel status LED states and print debounced GPIO42
right-function-button events after uploading `src/`, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import io_probe; io_probe.run_probe(cycles=2)"
```

The probe does not start Wi-Fi, initialize audio, initialize the display, or
touch GPIO10 board-power control.

The display probe is also opt-in. To cycle the 128 x 128 LCD through boot,
Wi-Fi, offline, online, recording, processing, speaking, and error screens,
run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import display_probe; display_probe.run_probe(cycles=2)"
```

The display probe initializes only the ST7735-compatible LCD and GPIO3
backlight. It does not start Wi-Fi, audio, or GPIO10 board-power control.

The ES8311 codec probe remains opt-in as well. After uploading `src/`, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import audio_probe; audio_probe.run_probe()"
```

It scans the GPIO4/GPIO5 I2C bus for expected codec address `0x18`, writes the
16 kHz 16-bit initialization registers, keeps the DAC muted, briefly pulses the
GPIO9 speaker amplifier gate, and disables the gate before returning.

The microphone capture probe is opt-in. To initialize ES8311 input, capture a
short bounded PCM sample, and print level/clipping metrics, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import capture_probe; capture_probe.run_probe()"
```

The capture probe keeps GPIO9 speaker enable disabled and does not write audio
to flash by default.

The speaker playback probe is opt-in. To initialize ES8311 output, play a
generated low-volume test tone, and print write/underrun metrics, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import playback_probe; playback_probe.run_probe()"
```

The playback helper currently supports bounded 16 kHz, 16-bit, mono PCM and
WAV input. The probe unmutes the DAC only for playback, enables GPIO9 only
while I2S samples are being written, then mutes the DAC and disables GPIO9
before returning.

The on-device inference feasibility probe is opt-in and offline-first. It
measures heap, flash, timing, button responsiveness, and optional LED/display
updates under a simulated local inference load. It does not require Wi-Fi, a
local service, public network access, model downloads, activation calls, or a
connected speaker:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import inference_probe; inference_probe.run_probe()"
```

For a repeatable application-first bench run with a redacted, GitHub-ready
report, use the developer wrapper's inference mode. It requires one explicit
serial port, uploads the current `src/` application tree without flashing or
backing up firmware, disables generated Wi-Fi configuration, avoids a device
reset into normal startup, then runs the offline probe. Record the physical
checks from the operator's observation; omitted checks remain `not-observed`.

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

`--gh OWNER/REPO` creates one new issue for the run; bare `--gh` uses the
configured repository or `origin`. The issue body contains redacted probe
evidence and never includes the raw transcript or serial-device path. If `gh`
is unavailable or unauthenticated, the wrapper keeps the redacted body under
ignored `tools/.local/dev-install/` for later review without changing the
installer or probe status.

### Windows Physical Device Validation

Use `validate.cmd` on a Windows bench host to upload the current application
without a reset, run the self-contained device probes, collect operator
observations, and create a new redacted GitHub issue for that run:

```cmd
gh auth login
validate.cmd --port COM8 --yes --device-label bench-a
```

The command runs display, GPIO status/button, ES8311 codec, microphone capture,
low-volume speaker playback, and offline inference probes in one raw-REPL
session. It reports each probe result, continues to later probes after a
device-side probe failure, and avoids reconnecting between probes. After the
sequence, it prompts for `pass`, `fail`, or `not-observed` for display, status
LED, button, microphone, speaker, and inference UI behavior. Any failed or
unobserved check makes the validation result non-passing; the GitHub report
records that evidence rather than inferring a successful physical result.

The validation command does not reset the device into normal startup, flash or
erase firmware, configure Wi-Fi, call a local service, run push-to-talk, or
drive GPIO10. Raw and redacted transcripts, metadata, and the GitHub-ready body
are retained under ignored `tools\.local\device-validation\`. It resolves the
issue repository from `AIPI_GITHUB_REPO` when valid, otherwise from `origin`.
If `gh` cannot create the issue, the local report remains available and the
console reports the publishing failure separately from the validation result.

See [INFERENCE_FEASIBILITY.md](INFERENCE_FEASIBILITY.md) for the scope,
candidate runtime inventory, decision states, and validation report template.

The local service client is used by the push-to-talk MVP flow. It validates
that the configured service URL is local-only before calling
`/health`, `/session`, `/audio`, `/response/{session_id}`, or response WAV URLs.
For development, run the stdlib-only mock service on the host:

```bash
python3 -m service.mock_service --host 127.0.0.1 --port 8080
```

Use a LAN address instead of `127.0.0.1` only when testing from the device on an
operator-controlled local network. See [service/README.md](service/README.md)
for request and response payloads.

The push-to-talk controller is available for MVP validation after local Wi-Fi,
audio capture, playback, LED, button, and display probes are ready. It keeps the
same local-only endpoint policy, drives UI state from one assistant state
machine, retries bounded local service calls, and remains available in offline
status when initial or button-triggered reconnection fails. Active capture,
network, service, or playback failures still return to a visible error state.
The full MVP install,
configuration, validation checklist, and report template are in
[MVP.md](MVP.md).

The Wi-Fi/local-service probe requires an ignored `local_wifi_config.py` file on
the device. During application upload, `install.sh` checks the selected app
directory for `local_wifi_config.py`. If it is missing, the installer prompts to
create `src/local_wifi_config.py`; if it already exists, the installer prompts
before re-creating it. The generated or hand-written file should look like:

```python
WIFI_SSID = "your-local-ssid"
WIFI_PASSWORD = "your-wpa2-password"
LOCAL_SERVICE_URL = "http://192.168.1.10:8080"
APPROVED_LOCAL_HOSTS = ("assistant.lan",)
```

`APPROVED_LOCAL_HOSTS` is optional; use an empty tuple when no extra local DNS
names need approval. Do not commit this file because it contains local Wi-Fi
credentials and network details. For noninteractive runs, keep the default skip
behavior or provide explicit values in `.conf` or the environment:

```bash
AIPI_CREATE_LOCAL_WIFI_CONFIG=yes
AIPI_WIFI_SSID=your-local-ssid
AIPI_WIFI_PASSWORD=your-wpa2-password
AIPI_LOCAL_SERVICE_URL=http://192.168.1.10:8080
AIPI_APPROVED_LOCAL_HOSTS=assistant.lan
```

After uploading `src/`, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import local_wifi_config as c; print(dir(c))"
mpremote connect /dev/cu.usbmodem31101 exec "import wifi_probe; wifi_probe.run_probe()"
```

The first command verifies the deployed config module exposes the expected
setting names, including `WIFI_SSID`, without printing credential values. If
`wifi_probe` reports a missing setting, re-run that command to confirm the file
on the device matches the local `src/local_wifi_config.py` that was uploaded.

The probe validates the configured endpoint before connecting to Wi-Fi. It
accepts RFC1918 IPv4 addresses, loopback/link-local IPv4 for bench testing,
`.local` names, and explicitly approved local hostnames. Public internet
endpoints are rejected by default and are not contacted. A Wi-Fi connection
timeout remains a failed probe result, but it renders the normal `OFFLINE`
screen instead of presenting `WiFiProbeError` as a fatal device error.

See [src/README.md](src/README.md) for firmware image selection, upload, serial
log, and safety notes for the MicroPython application tree.

## Host-side tests

Run the host-side regression tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

These tests use local stubs for MicroPython-only modules so they can validate
display layout, GPIO logic, and setup tooling without an attached AIPI-Lite
device.
