# AIPI-Lite Local Firmware Plan

Target device: XORIGIN AI PI-Lite / AIPI Lite, model `XY006PL01`

Goal: replace the stock firmware with local-only firmware that uses the attached
display, status LED, button, microphone, and speaker to communicate with the
user. The device must communicate only with services on the local network unless
an operator explicitly adds and approves another endpoint.

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

## Non-Goals

- Do not contact AIPI, X-ORIGIN, MQTT, WebSocket, OTA, analytics, or cloud AI
  endpoints from replacement firmware.
- Do not implement on-device LLM inference.
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
6. Device streams or uploads captured PCM audio to a local LAN service.
7. Local service performs speech-to-text, assistant logic, and text-to-speech.
8. Device receives response text and audio from the local service.
9. Device displays short status/response text and plays response audio.

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

## Runtime Probe Sequence

Build the replacement firmware in small hardware validation steps:

1. Flash backup and recovery
   - Back up the stock firmware before overwriting flash.
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

## Fallback Criteria

Move from MicroPython to ESP-IDF if any of these block the MVP:

- ES8311 cannot be initialized from Python with stable settings.
- I2S input or output is unavailable for the ESP32-S3 build used.
- Audio capture drops samples or cannot sustain the selected sample rate.
- Audio playback underruns during network activity.
- Available heap is too small for buffered audio plus display/network state.
- Local-only network policy cannot be enforced cleanly.

## Security and Federal Use Considerations

- Default to local-only communications and reject public endpoints unless the
  operator explicitly changes policy.
- Do not embed cloud tokens, vendor credentials, Wi-Fi credentials, or service
  secrets in source control.
- Prefer WPA2 or stronger Wi-Fi and operator-controlled LAN services.
- Log endpoint names and connection attempts locally for auditability.
- Keep firmware source, build artifacts, and third-party dependency versions
  traceable.
- Before any U.S. Federal deployment, verify applicable security, privacy,
  accessibility, supply-chain, and procurement requirements for the complete
  system, including the local service and device hardware.

## Documentation to Maintain

- `SPEC.md`: hardware facts, pinout, verified source links, and electrical
  caveats.
- `FIRMWARE_PLAN.md`: firmware architecture, milestones, protocol, and fallback
  criteria.
- Future `firmware/README.md`: flashing, backup, configuration, and recovery
  instructions.
- Future `service/README.md`: local service API, deployment, and security
  controls.

## First Implementation Milestone

Create a minimal MicroPython hardware probe under `firmware/micropython/` with:

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

## References

- Hardware specification: [SPEC.md](SPEC.md)
- MicroPython ESP32 quick reference: https://docs.micropython.org/en/latest/esp32/quickref.html
- MicroPython I2S API: https://docs.micropython.org/en/latest/library/machine.I2S.html
- CircuitPython audio bus reference: https://docs.circuitpython.org/en/latest/shared-bindings/audiobusio/index.html
- CircuitPython Wi-Fi reference: https://docs.circuitpython.org/en/latest/shared-bindings/wifi/index.html
