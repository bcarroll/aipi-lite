# aipi-lite

Local-only replacement firmware work for the XORIGIN AI PI-Lite / AIPI Lite.

## Current MicroPython Workflow

The repository installer is Windows-only. Run it from a Windows 10 or later
Command Prompt with Python 3 installed (the `py` launcher, or `python` on
`PATH`). Connect the AIPI-Lite over USB-C, then upload the current application
baseline:

```cmd
install.cmd --port COM3 --yes
```

Let the installer select a single detected port, or identify the target
explicitly:

```cmd
install.cmd --list-ports
install.cmd --port COM3 --yes
install.cmd --yes
```

Direct `install.cmd` runs store the validated port as `AIPI_SERIAL_PORT=COMx`
in the ignored root `.conf`. An explicit `--port` takes precedence and replaces
the saved value. When `--port` is omitted, the installer reuses the saved port;
if none is saved and exactly one COM port is detected, it selects and saves that
port automatically. Zero or multiple detected ports require one explicit
`install.cmd --port COMx` run. When the saved port is no longer present, the
installer prompts you to accept a detected port (press Enter for the sole
detected port) or type another, then saves your choice; it never silently
switches devices. In a non-interactive session (for example a `dev_install.cmd`
capture) it still fails closed and asks for an explicit `--port`. A saved value
with an invalid format also requires an explicit port. `install.cmd
--list-ports` remains read-only.

See [DEVELOPER.md](DEVELOPER.md) for the concise connected-device test and
GitHub reporting workflow.

The first normal run creates an ignored local virtual environment under
`tools\.local\micropython-venv` and installs `mpremote`. `--yes` explicitly
approves that prerequisite setup; omit it to receive an interactive prompt.
The upload stages a cache-free copy of `src\` and copies its children to the
root-stat-safe `mpremote` device-root destination `:/.`, producing `/boot.py`,
`/main.py`, and `/lib` rather than `/src`. It removes the known legacy root-level
application modules that were moved under `/lib`.
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
Port persistence (saving to `.conf`) is intentionally limited to direct
`install.cmd` runs. Developer inference captures still require an explicit COM
port to identify the device whose evidence is being collected. `validate.cmd`
accepts an explicit `--port`, but when it is omitted it reuses the port saved by
`install.cmd` in `.conf` (or a sole detected port), without changing the saved
value.
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
preserved. The inference capture never flashes firmware; firmware flashing is a
separate explicit `install.cmd --flash-micropython` operation described below.
Automated stock-firmware backup and restore are not provided by the repository
scripts and remain manual recovery steps.

If local prerequisites are missing, the installer prompts before downloading or
installing components under ignored `tools/.local/`, then continues with the
upload workflow after approval. The default setup path installs `mpremote`,
ensures external MicroPython library source exists under `src/lib/`, and skips
downloading a MicroPython firmware image.
Prompts are written explicitly so they remain visible through `dev_install.cmd`
captures. If stdin is not interactive, the installer uses safe defaults for
optional prompts, treats confirmations as `no`, and exits instead of waiting
silently.

Installer answers are stored in a root `.conf` file, which is ignored by Git.
The installer reads that file on later runs for values such as serial port,
download approval, upload approval, bootloader confirmation for explicit flash
runs, flash approval, reset preference, and optional local Wi-Fi config
generation values.

Run `install.cmd --list-ports` to probe available COM ports before an upload.
The diagnostic uses the repo-local `mpremote` when it is installed, reports
responsive MicroPython ports, and falls back to raw serial candidates when no
MicroPython device responds.

Run without `--port` to have the installer reuse the saved port or, if none is
saved, select a single detected COM port automatically.

### Firmware flashing

The Windows installer can flash MicroPython firmware. Use explicit flashing only
when the connected device needs MicroPython installed or replaced:

```cmd
install.cmd --port COM3 --flash-micropython --yes
```

Flashing selects and writes the Octal-SPIRAM build
`ESP32_GENERIC_S3-SPIRAM_OCT`. This build is required because the AIPI-Lite has
8 MB of Octal PSRAM (see [SPEC.md](SPEC.md)). The plain `ESP32_GENERIC_S3` build
that was previously flashed leaves the ESP-IDF Wi-Fi driver without internal
DRAM, so Wi-Fi init fails instantly with `Wifi Out of Memory`. Writing the
SPIRAM_OCT build is the fix for that failure.

Flash-related flags on `install.cmd`:

- `--flash-micropython` performs the flash before the application upload.
- `--firmware-url URL` overrides the firmware image; the default is the latest
  SPIRAM_OCT build.
- `--baud RATE` sets the flash baud rate (default `460800`).
- `--skip-erase` skips the pre-flash chip erase.

Pin an explicit SPIRAM_OCT build when the latest image is not the right target:

```cmd
install.cmd --port COM3 --flash-micropython --firmware-url https://micropython.org/resources/firmware/ESP32_GENERIC_S3-SPIRAM_OCT-20260406-v1.28.0.bin --yes
```

The operator still needs to connect the device over USB-C and put the AIPI-Lite
into ESP32-S3 bootloader mode for firmware flashing, because those are physical
actions. Bootloader access currently requires removing the four back screws,
pressing the button under the display while plugging the device into USB-C, and
confirming that the screen remains black.

Stock-firmware backup and restore are not automated by the repository scripts.
They are manual, out-of-band recovery steps only; see [RECOVERY.md](RECOVERY.md)
for the manual procedure and the flashing safety checklist.

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
push-to-talk controller, and then polls GPIO42 for press, release, and
once-per-hold long-press events. When Wi-Fi or the local service is unavailable,
startup enters an explicit `OFFLINE` state and keeps polling GPIO42. The LCD
uses fixed `Wi-Fi` and `SERVICE` rows with status icons and explicit
`ONLINE`/`OFFLINE` text, so color is not the only status indicator. It does not
display the configured SSID, Wi-Fi password, or local service URL.

A short press retries exactly the first offline dependency: Wi-Fi before the
local service. If Wi-Fi reconnects, the service remains visibly offline until a
later short press retries it. Holding GPIO42 for two seconds bypasses the
`OFFLINE` screen without reconnecting and enters `LIMITED`; push-to-talk remains
unavailable there, while a short press can continue the same staged recovery.
When both components are online, the controller enters `ONLINE` automatically
and the next press/release pair records. Other startup failures still print the
failure type and render a visible
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
Wi-Fi, offline, limited, online, recording, processing, speaking, and error
screens, run:

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
report, use the Windows developer wrapper's inference mode. It requires one
explicit COM port, uploads the current `src/` application tree without flashing
firmware, disables generated Wi-Fi configuration, avoids a device reset into
normal startup, then runs the offline probe. Record the physical checks from the
operator's observation; omitted checks remain `not-observed`.

```cmd
dev_install.cmd --inference-probe --gh bcarroll/aipi-lite --device-label bench-a --inference-check display=pass --inference-check status-led=pass --inference-check button=pass --inference-check offline=pass -- --port COM3 --yes
```

`--gh OWNER/REPO` creates one new issue for the run; bare `--gh` uses the
configured repository or `origin`. The issue body contains redacted probe
evidence and never includes the raw transcript or serial-device path. If `gh`
is unavailable or unauthenticated, the wrapper keeps the redacted body under
ignored `tools/.local/dev-install/` for later review without changing the
installer or probe status.

### Windows Physical Device Validation

Use `validate.cmd` on a Windows bench host to hard-reset the device, wait one
second, upload the current application, run the self-contained device probes,
collect operator observations, and create a new redacted GitHub issue for that
run:

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

The validation command performs only that pre-upload hard reset; after upload,
it does not reset the device into normal startup, flash or erase firmware,
configure Wi-Fi, call a local service, run push-to-talk, or drive GPIO10. Raw
and redacted transcripts, metadata, and the GitHub-ready body are retained
under ignored `tools\.local\device-validation\`. When upload fails, the GitHub
body includes up to 12 redacted high-signal upload diagnostics; complete
evidence remains local. It resolves the issue repository from `AIPI_GITHUB_REPO`
when valid, otherwise from `origin`. If `gh` cannot create the issue, the local
report remains available and the console reports the publishing failure
separately from the validation result.

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
or limited status when initial or button-triggered reconnection fails. Its
component-aware screen and serial output distinguish Wi-Fi from local-service
failures, and its staged retry never attempts more than one offline component
per short press. Active capture, network, service, or playback failures still
return to a visible error state.
The full MVP install,
configuration, validation checklist, and report template are in
[MVP.md](MVP.md).

The Wi-Fi/local-service probe requires an ignored `local_wifi_config.py` file on
the device. During application upload, `install.cmd` checks the selected app
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

Every normal boot, reconnect attempt, and explicit probe now emits bounded
`wifi_trace` lines to serial. Status changes print immediately; an unchanged
status prints at most once per second until the existing 15-second timeout.
For example:

```text
wifi_trace phase=start timeout_ms=15000
wifi_trace phase=interface active=1
wifi_trace phase=connect_requested credentials_present=1
wifi_trace phase=status elapsed_ms=0 connected=0 status=connecting status_code=1
wifi_trace phase=timeout elapsed_ms=15000 connected=0 status=connecting status_code=1
```

The mapped status names are `idle`, `connecting`, `wrong_password`,
`no_ap_found`, `connect_fail`, and `got_ip`. Unknown numeric driver states stay
visible as `unknown`; runtimes without `WLAN.status()` report `unavailable`.
ESP32 MicroPython may continue reporting `connecting` while its Wi-Fi driver
retries, so the final status is the runtime's observation rather than a guessed
cause. A successful connection line includes the local IP, netmask, gateway,
and DNS values returned by `ifconfig()`.

Trace lines never include the SSID, password, service URL, approved hostnames,
MAC/BSSID, nearby access-point names, or arbitrary exception text. Exceptions
include only their type and a numeric error code when the runtime provides one.
The trace is serial-only; it is not stored, uploaded, or sent as telemetry.

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
