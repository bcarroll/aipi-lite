# AIPI-Lite MicroPython Application

This directory is the MicroPython application tree copied to the AIPI-Lite
ESP32-S3 image by the repository installer.

## Layout

| Path | Purpose |
| --- | --- |
| `boot.py` | Safe startup defaults. It emits serial status and does not construct GPIO pins or change GPIO10 board-power control. |
| `main.py` | Application entrypoint. It prints bring-up status, renders the boot screen when available, connects the local push-to-talk flow, and polls GPIO42. |
| `pins.py` | Central pin constants from `SPEC.md`, grouped by display, audio, status LED, button, and power. |
| `status_led.py` | WS2812/NeoPixel status LED driver for GPIO46 with named firmware states. |
| `button.py` | Active-low GPIO42 side button reader with debounce and press/release events. |
| `io_probe.py` | Explicit GPIO-only probe that cycles status LED states and prints button events. |
| `display.py` | ST7735 display wrapper, PWM backlight control, text layout, and named status screen renderer. |
| `display_probe.py` | Explicit LCD probe that cycles boot, Wi-Fi, ready, recording, processing, speaking, and error screens. |
| `aipi_lite_config.py` | Compatibility shim for the imported ST7735 baseline. |
| `es8311.py` | ES8311 I2C register driver and GPIO9 speaker amplifier gate helper. |
| `audio_probe.py` | Opt-in serial codec probe that scans I2C, initializes the ES8311, and briefly pulses the muted speaker gate. |
| `audio_capture.py` | Bounded 16 kHz 16-bit mono I2S microphone capture and WAV packaging helpers. |
| `capture_probe.py` | Opt-in serial microphone probe that initializes ES8311 input, captures a short PCM buffer, and reports level metrics. |
| `audio_playback.py` | Bounded 16 kHz 16-bit mono I2S speaker playback, WAV parsing, and test-tone generation helpers. |
| `playback_probe.py` | Opt-in serial speaker probe that initializes ES8311 output, plays a generated test tone, and reports write metrics. |
| `assistant_state.py` | Assistant state names and shared LED/display/serial state output mapping. |
| `push_to_talk.py` | Local-only push-to-talk controller that coordinates button events, capture, local service exchange, response display, and playback. |
| `reliability.py` | Bounded retry policy, reconnect helper, serial diagnostics, GPIO21 charge observation, and GPIO10 board-power guard. |
| `service_contract.py` | Local assistant service endpoint constants, URL helpers, status names, and contract version. |
| `service_client.py` | Local-only client for `/health`, `/session`, `/audio`, `/response/{session_id}`, and response WAV downloads. |
| `version.py` | MVP firmware name, version, target model, local-only profile, and service contract metadata. |
| `wifi_config.py` | Loader for ignored local Wi-Fi and local-service configuration. |
| `local_endpoint.py` | Local-only endpoint parser and validator for configured service URLs. |
| `wifi_probe.py` | Explicit Wi-Fi/local-service probe that validates endpoint policy, connects Wi-Fi, calls `/health`, and reports status. |
| `lib/st7735/` | Imported ST7735 display driver and font files. |
| `lib/drivers/` | Tracked external MicroPython display driver bundle staged by `tools/setup_micropython_tools.sh`. |
| `lib/AIPI-LITE-MICROPYTHON-LIBRARIES.md` | Manifest for tracked external MicroPython library source and upstream license location. |

## Firmware Image Selection

Use the root installer to resolve and flash the latest stable official
MicroPython `ESP32_GENERIC_S3` image:

```bash
./install.sh --port /dev/cu.usbmodem31101
```

Pass an explicit image when hardware testing requires a known version:

```bash
./install.sh --port /dev/cu.usbmodem31101 \
  --firmware-url https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20260406-v1.28.0.bin
```

The installer stores downloaded firmware and MicroPython tooling under ignored
`tools/.local/` paths. Do not commit firmware downloads, stock flash backups,
credentials, tokens, or local serial configuration.

## Copy and Run Workflow

The default installer uploads this full `src/` tree after flashing
MicroPython. To upload a changed application tree without changing the
firmware image, use the installer flow once prerequisites are installed, or run
the equivalent `mpremote` copy sequence from the root documentation.

On boot, expected serial output includes:

```text
boot: AIPI-Lite safe startup
boot: collecting garbage before application start
boot: GPIO10 board power left unchanged
main: AIPI-Lite MicroPython application starting
main: serial bring-up active
main: GPIO10 board power left unchanged
main: safe boot leaves board_power_control on GPIO10 untouched
main: speaker amplifier disabled
main: display boot status rendered
main: status LED initialized
main: connecting local push-to-talk service
assistant: state connecting: local service
assistant: state ready
main: push-to-talk ready
main: polling right function button
```

Normal boot stays in the button polling loop after the ready line. If optional
display or LED initialization is unavailable, `main.py` prints the matching
`skipped: <ErrorName>` line and continues with serial output. If local Wi-Fi,
configuration, or service startup fails, `main.py` prints
`main: push-to-talk startup failed: <ErrorName>` and renders an `error` status
when display or LED output is available.

## GPIO Status/Input Probe

After the application tree is uploaded, run the GPIO-only probe explicitly when
you want to validate the status LED and side function button:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import io_probe; io_probe.run_probe(cycles=2)"
```

The probe cycles these named LED states over the GPIO46 WS2812/NeoPixel status
LED: `offline`, `connecting`, `ready`, `recording`, `processing`, `speaking`,
and `error`. It then watches the active-low GPIO42 right function button and
prints debounced `pressed` and `released` events to serial.

This probe intentionally avoids Wi-Fi, display initialization, audio setup, and
GPIO10 board-power control.

## Display Probe

After the application tree is uploaded, run the display probe explicitly when
you want to validate the LCD, backlight, orientation, color order, and status
screen readability:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import display_probe; display_probe.run_probe(cycles=2)"
```

The probe cycles through `boot`, `wifi`, `ready`, `recording`, `processing`,
`speaking`, and `error` screens and prints each transition to serial. The
renderer uses the ST7735-compatible driver, SPI bus 1 at 20 MHz, rotation `1`,
RGB color order enabled, and GPIO3 PWM backlight control. These assumptions are
not yet physically validated on this exact unit.

## ES8311 Codec Probe

The current codec-control milestone adds ES8311 setup over the documented I2C
bus on GPIO4/GPIO5. The firmware expects the codec to appear at 7-bit I2C
address `0x18`; `0x19` is also accepted as the alternate ES8311 address.

Run the probe from a MicroPython REPL only when the device is ready for hardware
bring-up:

```python
import audio_probe
audio_probe.run_probe()
```

The probe prints the I2C scan result, initializes the codec for 16 kHz 16-bit
I2S with MCLK on GPIO6, keeps the DAC muted, briefly enables the GPIO9 speaker
amplifier gate, and disables it again before returning.

## Microphone Capture Probe

The capture milestone adds bounded I2S microphone capture on the ES8311 audio
path using GPIO6 MCLK, GPIO13 DIN, GPIO12 LRCLK/WS, and GPIO14 BCLK. The
default capture format is 16 kHz, 16-bit, mono PCM with WAV packaging helpers.

Run the probe explicitly when the device is ready to validate microphone input:

```python
import capture_probe
capture_probe.run_probe()
```

The probe initializes the ES8311 input path, keeps GPIO9 speaker enable
disabled, captures a short bounded PCM sample, and prints byte count, sample
count, peak level, and clipping count to serial. It does not write captured
audio to flash by default; use `audio_capture.wav_bytes()` from a REPL or later
service upload code when an off-device WAV artifact is needed.

## Speaker Playback Probe

The playback milestone adds bounded I2S speaker output on the ES8311 audio path
using GPIO6 MCLK, GPIO11 DOUT, GPIO12 LRCLK/WS, and GPIO14 BCLK. The supported
format is 16 kHz, 16-bit, mono PCM, either as raw PCM bytes or as a RIFF/WAVE
file with matching format fields.

Run the probe explicitly when the device is ready to validate speaker output:

```python
import playback_probe
playback_probe.run_probe()
```

The probe initializes the ES8311 output path, generates a short low-volume test
tone, unmutes the DAC only for playback, enables GPIO9 only while I2S samples
are being written, then mutes the DAC and disables GPIO9 before returning. It
prints byte count, sample count, write calls, and underrun count to serial.

## Local Service Client

`service_client.py` implements the local assistant service contract used by the
push-to-talk flow. It rejects public service endpoints through
`local_endpoint.py` before issuing any HTTP request.

The client methods map to the current contract:

- `health()` calls `GET /health`.
- `start_session()` calls `POST /session`.
- `upload_audio(session_id, audio_bytes)` calls `POST /audio`.
- `get_response(session_id)` calls `GET /response/{session_id}`.
- `download_audio(audio_url)` downloads a local response WAV URL.

See [../service/README.md](../service/README.md) for the host-side mock service,
payloads, and error responses.

## Push-To-Talk MVP Flow

`assistant_state.py` defines the shared assistant states: `booting`,
`connecting`, `ready`, `recording`, `uploading`, `processing`, `speaking`, and
`error`. `StatusOutputs` maps each state to the existing LED and display status
names so serial, LED, and display updates come from one state source.

`push_to_talk.py` coordinates one local assistant exchange:

1. Validate local service reachability with `GET /health`.
2. Move to `recording` on a debounced GPIO42 press.
3. On release, capture a bounded 16 kHz, 16-bit, mono WAV payload.
4. Start a local service session and upload the audio.
5. Retrieve response text and a local WAV response URL.
6. Play the response while GPIO9 is enabled only for playback.
7. Return to `ready` or enter visible `error` state on failure.

During normal boot, `main.py` creates this controller, connects Wi-Fi through
the existing local connector, validates local service health, and then polls the
GPIO42 button continuously. The controller is dependency-injectable for host
tests and hardware validation. It does not add public endpoints, cloud calls,
telemetry, OTA behavior, or model downloads. Long-press behavior remains
reserved until GPIO10 board-power behavior is physically validated.

## Reliability and Diagnostics

`reliability.py` adds conservative runtime helpers for the MVP:

- `RetryPolicy` and `call_with_retries()` bound local service retries and
  backoff.
- `DiagnosticsLog` keeps serial-visible state transitions, retry events, heap
  observations when available, playback underruns, and failure types.
- `ReconnectManager` centralizes Wi-Fi reconnect attempts around the existing
  local Wi-Fi connector.
- `ChargePulseReader` reads GPIO21 only as `charge_pulse_high` or
  `charge_pulse_low`; it does not infer battery percentage.
- `BoardPowerGuard` keeps GPIO10 board-power control blocked unless a future
  hardware-validated safety flag explicitly allows it.

## Wi-Fi and Local Service Probe

Create an ignored `src/local_wifi_config.py` file before uploading `src/` to the
device, or let `install.sh` prompt to create it during upload:

```python
WIFI_SSID = "your-local-ssid"
WIFI_PASSWORD = "your-wpa2-password"
LOCAL_SERVICE_URL = "http://192.168.1.10:8080"
APPROVED_LOCAL_HOSTS = ("assistant.lan",)
```

`APPROVED_LOCAL_HOSTS` is optional and should contain only operator-controlled
local DNS names. Do not commit this file. It is ignored by Git because it may
contain Wi-Fi credentials or local infrastructure names. For noninteractive
installer runs, set `AIPI_CREATE_LOCAL_WIFI_CONFIG=yes`, `AIPI_WIFI_SSID`,
`AIPI_WIFI_PASSWORD`, `AIPI_LOCAL_SERVICE_URL`, and optional
`AIPI_APPROVED_LOCAL_HOSTS` in the ignored root `.conf` file or environment.

Run the probe explicitly when the device is ready to validate local Wi-Fi and
local service reachability:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import local_wifi_config as c; print(dir(c))"
mpremote connect /dev/cu.usbmodem31101 exec "import wifi_probe; wifi_probe.run_probe()"
```

The first command verifies the deployed config module exposes the expected
setting names, including `WIFI_SSID`, without printing credential values. If
`wifi_probe` reports a missing setting, re-run that command to confirm the file
on the device matches the local `src/local_wifi_config.py` that was uploaded.

The probe validates `LOCAL_SERVICE_URL` before connecting or making an HTTP
request. It accepts RFC1918 IPv4 addresses, loopback/link-local IPv4 for bench
testing, `.local` mDNS names, and explicitly approved local hostnames. It
rejects public IPv4 addresses, public DNS names, embedded credentials, query
strings, fragments, and unsupported schemes by default.

When policy validation passes, the probe connects with MicroPython
`network.WLAN`, calls only the derived local `/health` URL, prints serial
status, and updates the status LED and display when those modules initialize.

## Safety Notes

- `boot.py` must remain safe to run before hardware probes. It should not
  instantiate `machine.Pin`, start Wi-Fi, configure audio, or toggle GPIO10.
- Normal `main.py` startup drives GPIO9 speaker enable low. Playback helpers
  must explicitly unmute the DAC for output and mute it again before returning.
- `pins.py` is declarative only. Later branches should import constants from it
  instead of repeating numeric GPIO assignments.
- `io_probe.py` is opt-in. Keep normal boot behavior safe and serial-visible so
  a failed LED or button experiment cannot block recovery access.
- `display_probe.py` is opt-in. It initializes only the LCD and backlight and
  should remain independent of Wi-Fi, audio, and GPIO10 board-power control.
- `wifi_probe.py` is opt-in. It validates endpoint policy before network
  connection attempts and should remain local-only by default.
- `service_client.py` validates endpoint policy before every configured service
  base URL is used. It should remain local-only by default and must not add
  cloud, telemetry, analytics, OTA, or vendor service calls.
- `push_to_talk.py` should remain local-only and keep long-press behavior
  reserved until board-power behavior is validated.
- `reliability.py` may observe GPIO21 but must not claim battery percentage.
  GPIO10 board-power control must remain behind an explicit guard.
- `capture_probe.py` is opt-in. It initializes the ES8311 input and I2S
  microphone path, keeps speaker output disabled, and should remain bounded so
  a capture test cannot exhaust heap.
- `playback_probe.py` is opt-in. It initializes the ES8311 output and I2S
  speaker path, keeps the test tone bounded and low volume, and must leave the
  DAC muted plus GPIO9 speaker enable disabled before returning.
- Local Wi-Fi credentials, service URLs, and operator overrides belong in
  ignored local configuration files, not in source control.
- Replacement firmware must remain local-only by default. Do not add cloud,
  telemetry, analytics, OTA, or vendor endpoints without an explicit design and
  approval step.

## Host Tests

Run the host-side regression tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The tests use local stubs for MicroPython-only modules and do not require
attached hardware.
