# aipi-lite

Local-only replacement firmware work for the XORIGIN AI PI-Lite / AIPI Lite.

## Current MicroPython Workflow

Use the repository installer to resolve the latest stable ESP32-S3 MicroPython
firmware, flash it, and upload the current application baseline:

```bash
./install.sh --port /dev/cu.usbmodem31101
```

Before any installer actions, `install.sh` runs `git pull --ff-only` from the
repository root and restarts itself once so the active script is current. Use
`--skip-self-update` or `AIPI_SKIP_SELF_UPDATE=1` only for intentional offline
or pinned-revision runs.

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
firmware path/size/checksum metadata, prerequisite status, best-effort esptool
target identity probes, MicroPython/mpremote runtime probes after flashing,
source upload inventory, command exit statuses, and reset status:

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
cache, and staged MicroPython libraries under `tools/.local/`. It preserves
stock firmware backups, installer debug logs, and developer install captures.
`--clean-prereqs` is accepted as an alias.

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
body as a comment when the `gh` CLI is already installed and authenticated. If
GitHub tooling is missing, unauthenticated, or `--prepare-only` is supplied, the
script leaves the issue body locally for inspection or manual submission. The
wrapper returns the installer exit status so capture or posting problems do not
mask install failures. The same cleanup option can be captured with
`./dev_install.sh --clean-tools`. For deeper hardware feedback, run
`./dev_install.sh --trace -- ...` so the visible transcript records the local
trace artifact path while the installer writes detailed trace data under
`tools/.local/debug/`. See [DEVELOPER.md](DEVELOPER.md) for the concise
connected-device test and GitHub reporting workflow.

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
unless `.conf` points at an existing exact-size backup. The backup read is
chunked by default so a failed transfer cannot be mistaken for a complete stock
image on the next run. If a backup stalls on a specific USB setup, reduce the
chunk size with `--backup-chunk-size 0x40000` or set
`AIPI_BACKUP_CHUNK_SIZE=0x40000` in `.conf`. The installer also retries failed
backup chunks down to 4 KiB without resetting the chip between chunks; a repeat
failure at the same offset should be treated as an address-specific read
failure or an unstable USB path.

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

The MicroPython source under `src/` now provides the safe application skeleton
and opt-in hardware/service probes:

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

`boot.py` emits serial-visible safe startup status without constructing GPIO
pins or touching GPIO10 board-power control. `main.py` prints the bring-up
sequence, drives GPIO9 speaker enable low, and renders a best-effort boot
status screen through the reusable display wrapper. `pins.py` centralizes the
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
endpoint policy validation passes.

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

The Wi-Fi/local-service probe requires an ignored `src/local_wifi_config.py`
file on the device. After uploading `src/`, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import wifi_probe; wifi_probe.run_probe()"
```

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
