# AIPI-Lite Local Firmware Plan

Target device: XORIGIN AI PI-Lite / AIPI Lite, model `XY006PL01`

Goal: replace the stock firmware with local-only firmware that uses the attached
display, status LED, button, microphone, and speaker to communicate with the
user. The device must communicate only with on-device code or services on the
local network unless an operator explicitly adds and approves another endpoint.

## Direction

Use a hardware-first firmware bring-up. MicroPython is the first candidate
runtime because it can exercise ESP32-S3 Wi-Fi, I2C, SPI, GPIO, PWM, NeoPixel,
and I2S without a full native firmware build loop. The decision point is not
language preference; the decision point is whether the runtime can reliably
initialize the ES8311 audio codec and stream microphone and speaker audio with
acceptable latency.

If MicroPython cannot provide stable audio I/O on this board, fall back to an
ESP-IDF firmware in C/C++. CircuitPython is not the preferred fallback because
the AIPI-Lite's primary risk is bidirectional ES8311 audio plus I2S streaming,
not display/UI support.

On-device LLM inference is welcomed if it can fit within the target device's
memory, flash, compute, thermal, power, and responsiveness limits. It should not
block the first firmware milestone, because display, audio, controls, Wi-Fi,
and local-only policy must be proven first. Treat on-device inference as an
optional local-only capability that can reduce or replace calls to a LAN service
after the core I/O path is stable.

## Non-Goals

- Do not contact AIPI, X-ORIGIN, MQTT, WebSocket, OTA, analytics, or cloud AI
  endpoints from replacement firmware.
- Do not require on-device LLM inference for the first working MVP.
- Do not make wake-word detection part of the first firmware milestone.
- Do not preserve stock cloud account provisioning.
- Do not add production dependencies without explicit approval.

## Target User Experience

The initial usable firmware should behave as a push-to-talk local assistant
terminal:

1. Device boots and shows local firmware status on the LCD.
2. Device connects to configured local Wi-Fi.
3. Device verifies that the configured local service is reachable.
4. Status LED shows offline, connecting, ready, recording, processing, speaking,
   and error states.
5. User presses the side function button to record.
6. Device streams or uploads captured PCM audio to a local LAN service, unless a
   later on-device mode can handle the full exchange locally.
7. Local service performs speech-to-text, assistant logic, and text-to-speech
   for the MVP.
8. A future on-device inference mode may perform some or all assistant logic
   locally if it remains responsive and does not require cloud services.
9. Device receives or produces response text and audio.
10. Device displays short status/response text and plays response audio.

## On-Device Inference Position

On-device inference is a desirable enhancement, not a core bring-up dependency.
It may take one of these forms:

- Small local intent classification or command routing.
- Tiny local text model for constrained responses.
- Local wake-word or speech activity logic after the audio path is stable.
- A native ESP-IDF inference path if MicroPython cannot host the required
  runtime efficiently.

Any on-device inference work must preserve these constraints:

- No cloud endpoints, telemetry, model fetches, or remote activation are allowed
  by default.
- Models and runtime artifacts must be versioned and traceable.
- The display, button, LED, microphone capture, speaker playback, and network
  recovery behavior must remain responsive.
- The firmware must fail back to the local LAN service or a clear offline state
  if on-device inference is unavailable.
- Memory, flash, CPU, latency, power, and thermal observations must be recorded
  before the feature is promoted beyond an experiment.

## Hardware Map

Use [SPEC.md](SPEC.md) as the authoritative local hardware inventory. Current
custom-firmware pin assignments are:

| Function | Pins |
| --- | --- |
| LCD backlight | GPIO3 |
| ES8311 I2C control | GPIO4 SCL, GPIO5 SDA |
| ES8311 I2S audio | GPIO6 MCLK, GPIO11 DOUT, GPIO12 LRCLK/WS, GPIO13 DIN, GPIO14 BCLK |
| LCD SPI | GPIO15 CS, GPIO16 SCLK, GPIO17 MOSI, GPIO7 D/C, GPIO18 RESET |
| Speaker enable | GPIO9 |
| Board power control | GPIO10, verify before relying on it |
| Charge pulse input | GPIO21 |
| Right function button | GPIO42, active-low |
| Status LED | GPIO46, WS2812/NeoPixel-style GRB |

## Local Network Protocol

Start with a simple HTTP protocol before adding streaming complexity:

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/health` | `GET` | Device checks local service availability. |
| `/session` | `POST` | Device starts a push-to-talk exchange and receives a session ID. |
| `/audio` | `POST` | Device uploads a bounded PCM/WAV recording for the session. |
| `/response/{session_id}` | `GET` | Device polls for response status, display text, and audio URL. |
| `/audio/{response_id}.wav` | `GET` | Device downloads local TTS audio for playback. |

HTTP is easier to debug during bring-up. Move to WebSocket only after the audio
path is stable and lower latency is required.

All endpoints must be configured as local addresses, such as RFC1918 IPv4
addresses, `.local` mDNS names, or a local DNS name controlled by the operator.
The firmware should reject public internet hostnames by default.

If on-device inference is enabled later, the local protocol remains useful as a
fallback and for capabilities that do not fit on the device.

## Runtime Probe Sequence

Build the replacement firmware in small hardware validation steps:

1. Flash backup and recovery
   - Back up the stock firmware before overwriting flash.
   - Stop before erase/write and record `stock_backup_blocked` trace data if
     the stock backup cannot be read after minimum-size retries.
   - Confirm bootloader access through USB serial/JTAG.
   - Record the exact MicroPython or fallback firmware image used.

2. Basic boot
   - Boot replacement runtime.
   - Confirm REPL or serial log access.
   - Confirm PSRAM and flash capacity.

3. GPIO and LED
   - Drive GPIO46 status LED.
   - Read GPIO42 side button.
   - Avoid GPIO10 power-control changes until verified.

4. Display
   - Initialize the ST7735-compatible LCD over SPI.
   - Turn on GPIO3 backlight.
   - Render boot, Wi-Fi, ready, recording, processing, speaking, and error
     states.

5. Wi-Fi and local service
   - Join configured Wi-Fi.
   - Call only the configured local `/health` endpoint.
   - Fail closed if the configured endpoint is non-local.

6. ES8311 control
   - Scan I2C on GPIO4/GPIO5.
   - Confirm ES8311 address.
   - Initialize codec registers for microphone input and speaker output.
   - Gate speaker amplifier with GPIO9.

7. Audio input
   - Capture a short mono PCM sample from I2S.
   - Upload sample to the local service.
   - Verify sample format, level, clipping, and background noise.

8. Audio output
   - Download or generate a local WAV/PCM test clip.
   - Play it through ES8311/I2S and speaker.
   - Verify speaker enable timing and volume.

9. Push-to-talk flow
   - Button press starts capture.
   - Button release stops capture.
   - Device sends audio, shows processing state, receives response, displays
     text, and plays audio.

10. Reliability pass
    - Test repeated sessions.
    - Test Wi-Fi reconnect.
    - Test local service unavailable.
    - Test low battery / battery-only behavior if the battery module is present.

11. Optional on-device inference feasibility
    - Measure available memory, flash, CPU headroom, latency, and power impact.
    - Test only local model/runtime artifacts.
    - Confirm that user I/O and audio streaming remain responsive.
    - Keep LAN-service fallback available.

## Fallback Criteria

Move from MicroPython to ESP-IDF if any of these block the MVP:

- ES8311 cannot be initialized from Python with stable settings.
- I2S input or output is unavailable for the ESP32-S3 build used.
- Audio capture drops samples or cannot sustain the selected sample rate.
- Audio playback underruns during network activity.
- Available heap is too small for buffered audio plus display/network state.
- Local-only network policy cannot be enforced cleanly.

On-device inference failure is not, by itself, a reason to abandon the
MicroPython MVP if the local-service assistant flow works. Move to ESP-IDF for
on-device inference only if native runtime control is required and the benefit
is worth the added firmware complexity.

## Security and Federal Use Considerations

- Default to local-only communications and reject public endpoints unless the
  operator explicitly changes policy.
- Do not embed cloud tokens, vendor credentials, Wi-Fi credentials, or service
  secrets in source control.
- Prefer WPA2 or stronger Wi-Fi and operator-controlled LAN services.
- Log endpoint names and connection attempts locally for auditability.
- Keep firmware source, build artifacts, and third-party dependency versions
  traceable.
- Keep model files, prompts, and inference runtime versions traceable if
  on-device inference is added.
- Before any U.S. Federal deployment, verify applicable security, privacy,
  accessibility, supply-chain, and procurement requirements for the complete
  system, including the local service and device hardware.

## Developer Install Capture

Add a host-only `dev_install.sh` wrapper for the development team. The wrapper
should run the normal `install.sh` flow with the installer arguments supplied on
the command line, preserve the interactive prompts and exit status an operator
would see, and capture the visible stdout/stderr transcript for later review.

The captured transcript is intended to be added to a GitHub issue for ChatGPT
inspection, but it must be treated as an external sharing step rather than
firmware behavior. The wrapper should save redacted issue-ready output under an
ignored local path, support creating a new issue for an explicit or inferred
GitHub repository, support commenting on an explicit existing issue target, and
avoid committing logs, credentials, device identifiers, Wi-Fi settings, tokens,
firmware dumps, or other local-only artifacts. If GitHub upload tooling is not
available or authenticated, the wrapper should leave a local issue body artifact
that a developer can inspect and submit manually.

The same capture path is also the preferred host-side collection mechanism for
future hardware validation runs. Developers can add non-secret device labels and
hardware notes to the issue body while preserving the installer transcript,
metadata, and redacted local artifacts for later analysis.

## Documentation to Maintain

- `SPEC.md`: hardware facts, pinout, verified source links, and electrical
  caveats.
- `FIRMWARE_PLAN.md`: firmware architecture, milestones, protocol, and fallback
  criteria.
- `RECOVERY.md`: stock firmware backup, restore, expected recovery output, and
  flashing safety checklist.
- Future `src/README.md`: MicroPython application layout, configuration,
  upload, and recovery notes.
- Future `service/README.md`: local service API, deployment, and security
  controls.

## First Implementation Milestone

Create a minimal MicroPython hardware probe under `src/` with:

- `boot.py` for safe startup defaults.
- `main.py` for a serial-visible bring-up sequence.
- `pins.py` with constants from `SPEC.md`.
- `display_probe.py` for LCD/backlight.
- `io_probe.py` for button and WS2812 LED.
- `wifi_probe.py` for local `/health` check.
- `audio_probe.py` for ES8311/I2C/I2S experiments.

The first success condition is not a full assistant. The first success condition
is proven control of display, LED, button, Wi-Fi, ES8311, microphone capture,
and speaker playback on the target device.

## Imported Code Baseline

Existing code from `https://github.com/bcarroll/aipi-lite` has been merged as
the current project target. That code provides an early MicroPython LCD bring-up
baseline:

| Plan component | Imported status | Evidence |
| --- | --- | --- |
| Flashing support | Implemented for backup/recovery milestone | `install.sh`, `RECOVERY.md`, `tools/setup_micropython_tools.sh`, `tools/README.md`, and `README.md` document and automate upload-only application installs by default, explicit installer self-update, sanitized debug artifacts, exact-size adaptive stock backup, structured `stock_backup_blocked` trace diagnostics, prerequisite cleanup, opt-in MicroPython flashing, source upload including tracked `src/lib` libraries, and stock restore using ignored local artifacts. |
| MicroPython source skeleton | Partially implemented | `src/main.py` renders a boot status screen through the reusable display wrapper. |
| Pin mapping | Partially implemented | `src/display.py` uses GPIO3 backlight, GPIO15 CS, GPIO7 D/C, GPIO18 reset, GPIO16 SCLK, and GPIO17 MOSI, matching the LCD pins in `SPEC.md`. |
| Display bring-up | Implemented, hardware validation pending | `src/display.py` wraps ST7735 setup, PWM backlight control, text layout, and named status screens; `src/display_probe.py` cycles boot, Wi-Fi, ready, recording, processing, speaking, and error screens. |
| GPIO status LED and side button | Implemented, hardware validation pending | `src/status_led.py`, `src/button.py`, `src/io_probe.py`, and `tests/test_gpio_status_input.py` add GPIO46 status states, GPIO42 active-low debounce events, and an opt-in GPIO-only serial probe. |
| Wi-Fi and local-only service policy | Implemented, hardware validation pending | `src/wifi_config.py`, `src/local_endpoint.py`, and `src/wifi_probe.py` load ignored local Wi-Fi config, reject public service endpoints by default, call only local `/health`, and report health state through serial plus available LED/display modules. |
| ES8311 audio control and I2S audio | Codec control, microphone capture, and speaker playback implemented; hardware validation pending | `src/es8311.py` and `src/audio_probe.py` configure the ES8311 over I2C at expected address `0x18`, keep the DAC muted, and default GPIO9 speaker enable off. `src/audio_capture.py` and `src/capture_probe.py` add bounded 16 kHz 16-bit mono capture, WAV packaging, and serial level metrics. `src/audio_playback.py` and `src/playback_probe.py` add bounded 16 kHz 16-bit mono PCM/WAV speaker playback, generated tone output, GPIO9 gate timing, and write/underrun metrics. |
| Local service contract | Implemented | `src/service_contract.py`, `src/service_client.py`, `service/mock_service.py`, `service/README.md`, and `tests/test_local_service_contract.py` define `/health`, `/session`, `/audio`, `/response/{session_id}`, and `/audio/{response_id}.wav` with a local-only firmware client and deterministic mock service. |
| Push-to-talk assistant flow | Implemented, hardware validation pending | `src/assistant_state.py`, `src/push_to_talk.py`, `src/reliability.py`, and `tests/test_push_to_talk_flow.py` add a local-only state machine, GPIO42 press/release handling, bounded capture handoff, local service exchange, response text/audio handling, playback, bounded retries, diagnostics, and recoverable error states. |
| MVP release packaging | Implemented, hardware validation pending | `src/version.py`, `MVP.md`, `README.md`, `src/README.md`, and `tests/test_mvp_release.py` add local-only version metadata, install/configuration guidance, validation checklist, no-cloud network verification, and a validation report template. |
| On-device inference | Not implemented | No local model runtime, model metadata, or inference routing has been imported. |

The imported baseline should be treated as hardware evidence for the display
branch and as a starting point for refactoring into the planned firmware layout.
Legacy checked-in firmware binaries from the earlier import are not part of the
current workflow; generated or downloaded firmware images belong under ignored
tooling directories such as `tools/.local/`.

## References

- Hardware specification: [SPEC.md](SPEC.md)
- MicroPython ESP32 quick reference: https://docs.micropython.org/en/latest/esp32/quickref.html
- MicroPython I2S API: https://docs.micropython.org/en/latest/library/machine.I2S.html
- CircuitPython audio bus reference: https://docs.circuitpython.org/en/latest/shared-bindings/audiobusio/index.html
- CircuitPython Wi-Fi reference: https://docs.circuitpython.org/en/latest/shared-bindings/wifi/index.html
