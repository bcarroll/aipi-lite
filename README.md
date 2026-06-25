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

Run without `--port` to let `mpremote` auto-detect the attached MicroPython
device:

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

After copying `src/`, the installer attempts to reset the device.
Set `AIPI_RESET_AFTER_UPLOAD=no` in `.conf` or pass `--no-reset` to skip that
step.

Backup, restore, expected output, and safety details are documented in
[RECOVERY.md](RECOVERY.md).

See [tools/README.md](tools/README.md) for lower-level setup tooling.

## MicroPython Application

The MicroPython source under `src/` now provides the normal local-only
push-to-talk application and opt-in hardware/service probes:

- `src/boot.py`
- `src/main.py`
- `src/pins.py`
- `src/status_led.py`
- `src/button.py`
- `src/io_probe.py`
- `src/display.py`
- `src/display_probe.py`
- `src/aipi_lite_config.py`
- `src/es8311.py`
- `src/audio_probe.py`
- `src/audio_capture.py`
- `src/capture_probe.py`
- `src/audio_playback.py`
- `src/playback_probe.py`
- `src/assistant_state.py`
- `src/push_to_talk.py`
- `src/reliability.py`
- `src/service_contract.py`
- `src/service_client.py`
- `src/version.py`
- `src/wifi_config.py`
- `src/local_endpoint.py`
- `src/wifi_probe.py`
- `src/lib/st7735/`
- `src/lib/drivers/`

`boot.py` emits serial-visible safe startup status without constructing GPIO
pins or touching GPIO10 board-power control. `main.py` prints the bring-up
sequence, drives GPIO9 speaker enable low, renders the boot screen, initializes
available LED/display outputs, connects Wi-Fi and the local service through the
push-to-talk controller, and then polls GPIO42 for press/release events. If
startup fails, `main.py` prints the failure type and renders a visible error
state when display or LED output is available. `pins.py` centralizes the
documented pin map for later hardware probe branches. `aipi_lite_config.py`
remains as a compatibility shim for the imported display baseline. `es8311.py`
provides codec I2C control and the speaker amplifier gate; `audio_probe.py` is
the opt-in ES8311 hardware probe. `audio_capture.py` and `capture_probe.py`
add bounded 16 kHz 16-bit mono microphone capture and WAV packaging helpers for
the ES8311/I2S path. `audio_playback.py` and `playback_probe.py` add bounded
16 kHz 16-bit mono PCM/WAV speaker playback and a generated low-volume tone
probe. `service_contract.py` and `service_client.py` define the local assistant
service API and client. `assistant_state.py`, `push_to_talk.py`, and
`reliability.py` add the local-only assistant state machine, push-to-talk
exchange flow, bounded retries, diagnostics, and conservative power
observations. `version.py` records MVP metadata. `wifi_probe.py` connects only
to configured local Wi-Fi and calls only a local `/health` endpoint after
endpoint policy validation passes. External MicroPython display driver source is
tracked under `src/lib/drivers/` so a normal application upload includes it.

The GPIO status/input probe remains opt-in so normal boot stays recoverable. To
cycle the GPIO46 WS2812/NeoPixel status LED states and print debounced GPIO42
right-function-button events after uploading `src/`, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import io_probe; io_probe.run_probe(cycles=2)"
```

The probe does not start Wi-Fi, initialize audio, initialize the display, or
touch GPIO10 board-power control.

The display probe is also opt-in. To cycle the 128 x 128 LCD through boot,
Wi-Fi, ready, recording, processing, speaking, and error screens, run:

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
machine, retries bounded local service calls, and returns to a visible error
state on capture, network, service, or playback failures. The full MVP install,
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
endpoints are rejected by default and are not contacted.

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
