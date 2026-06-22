# AIPI-Lite Firmware Implementation Roadmap

Target device: XORIGIN AI PI-Lite / AIPI Lite, model `XY006PL01`

This document breaks the local-only replacement firmware into high-level tasks
that should be implemented as separate Git branches. Each branch lists the
expected subordinate work as commit-sized units.

The roadmap assumes the firmware direction in [FIRMWARE_PLAN.md](FIRMWARE_PLAN.md)
and the hardware pinout in [SPEC.md](SPEC.md). Start each branch from `main`,
keep each branch focused, and merge only after its acceptance criteria pass.

## Branch Strategy

- Use `feat/<number>-<topic>` for implementation work.
- Use `docs/<topic>` for documentation-only updates.
- Use `spike/<topic>` for disposable hardware experiments that should not be
  merged as production firmware.
- Use `fallback/<topic>` only if the MicroPython path fails a documented
  fallback criterion.
- Keep commits small enough that each one explains one usable increment.
- For generated Python code, include tests in the same branch.
- Do not add production dependencies without explicit approval.

## Merge Order Checklist

Legend: ✅ Complete, 🟡 Pending, ❌ Failed. Each icon is paired with text so
the checklist does not rely on color alone.

1. ✅ Complete - `feat/01-backup-recovery`
2. ✅ Complete - `feat/02-micropython-skeleton`
3. 🟡 Pending hardware validation - `feat/03-gpio-status-input`
4. 🟡 Pending implementation completion - `feat/04-display-bringup`
5. 🟡 Pending implementation - `feat/05-local-wifi-policy`
6. 🟡 Pending hardware validation - `feat/06-es8311-codec-control`
7. 🟡 Pending implementation - `feat/07-audio-capture`
8. 🟡 Pending implementation - `feat/08-audio-playback`
9. 🟡 Pending implementation - `feat/09-local-service-contract`
10. 🟡 Pending implementation - `feat/10-push-to-talk-flow`
11. 🟡 Pending implementation - `feat/11-reliability-power-errors`
12. 🟡 Pending implementation - `feat/12-mvp-release`

Optional on-device inference branches:

13. 🟡 Pending feasibility check - `spike/13-on-device-inference-feasibility`
14. 🟡 Pending feasibility result - `feat/14-on-device-inference`

Conditional runtime fallback branch:

- 🟡 Pending fallback criterion - `fallback/esp-idf-audio-runtime`

## Current Implementation Status

The repository now includes an earlier implementation from
`https://github.com/bcarroll/aipi-lite` at remote commit `b06b569`. That imported
code should be treated as the current source baseline for implementation work.
Legacy checked-in firmware binaries are intentionally excluded from the current
workflow; firmware images should be downloaded or generated into ignored
tooling directories.

| Branch / component | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| `feat/01-backup-recovery` | Implemented | `install.sh` prompts for bootloader readiness, stores answers in `.conf`, backs up stock flash to ignored tooling storage, restores saved stock backups, and `RECOVERY.md` documents backup, restore, expected recovery output, and the flashing safety checklist. | Validate the restore flow on physical hardware and record exact stock serial logs. |
| `feat/02-micropython-skeleton` | Implemented | `src/boot.py`, `src/main.py`, `src/pins.py`, `src/README.md`, and host tests provide safe startup defaults, grouped pin constants, serial-visible bring-up status, and hardware-free regression coverage. | Validate the serial output and display baseline on physical hardware. |
| `feat/04-display-bringup` | Partial | `src/lib/st7735/`, `src/aipi_lite_config.py`, and `src/main.py` initialize the ST7735 TFT and display text. | Convert demo into reusable display probe/status renderer and document orientation/color assumptions. |
| LCD pin constants | Implemented | `src/pins.py` includes display, button, status LED, ES8311 audio, speaker enable, charge input, and board power constants from `SPEC.md`. | Verify unconfirmed GPIO10 power behavior before any branch attempts to drive it. |
| `feat/03-gpio-status-input` | Implemented, hardware validation pending | `src/status_led.py`, `src/button.py`, `src/io_probe.py`, and `tests/test_gpio_status_input.py` add GPIO46 status states, GPIO42 active-low debounce events, a GPIO-only serial probe, and host regression coverage. | Validate LED colors and button press/release serial output on physical hardware. |
| `feat/05-local-wifi-policy` | Not started | No imported Wi-Fi or local endpoint code. | Implement local config, endpoint validation, and `/health` client. |
| `feat/06-es8311-codec-control` | Implemented, hardware validation pending | `src/es8311.py`, `src/audio_probe.py`, `src/main.py`, and `tests/test_es8311_codec.py` add ES8311 I2C detection, register setup, GPIO9 speaker gate defaults, and host-side regression coverage. | Run `audio_probe.run_probe()` on physical hardware and record the observed scan and audio behavior. |
| `feat/07-audio-capture` | Not started | No imported I2S microphone capture code. | Implement bounded PCM capture and WAV/PCM packaging. |
| `feat/08-audio-playback` | Not started | No imported I2S speaker playback code. | Implement playback and speaker enable timing. |
| `feat/09-local-service-contract` | Not started | No imported LAN service contract or mock service. | Define API, mock service, client, and tests. |
| `feat/10-push-to-talk-flow` | Not started | No imported assistant state machine. | Integrate button, audio, local service, display, and speaker. |
| `feat/11-reliability-power-errors` | Not started | No imported reconnect, retry, power, or diagnostics logic. | Add recovery behavior and hardware troubleshooting docs. |
| `feat/12-mvp-release` | Not started | No imported release checklist. | Package repeatable MVP validation and version metadata. |
| `spike/13-on-device-inference-feasibility` | Not started | No imported on-device inference experiment. | Measure feasibility after core I/O is reliable. |
| `feat/14-on-device-inference` | Not started | No imported inference runtime integration. | Add only after feasibility is proven. |

## Task Branches

### `feat/01-backup-recovery`

Purpose: make the device recoverable before any replacement firmware is flashed.

Expected commits:

- `docs: add stock firmware backup procedure`
  - Document entering bootloader mode.
  - Document `esptool` commands for chip identification and flash backup.
  - Document where backup artifacts should be stored outside source control.

- `docs: add firmware restore procedure`
  - Document restore commands and verification steps.
  - Document expected serial output after restoring stock firmware.

- `docs: add flashing safety checklist`
  - Require battery/power state checks.
  - Require confirmation that `SPEC.md` pinout has not changed.
  - Require no public/cloud endpoints in replacement firmware configuration.

Acceptance criteria:

- A user can back up the stock firmware before flashing replacement firmware.
- A user can restore stock firmware from the documented backup.
- No binary firmware dumps or secrets are committed.

### `feat/02-micropython-skeleton`

Purpose: create the first runnable firmware tree with safe defaults.

Expected commits:

- `firmware: add MicroPython project skeleton`
  - Add or update `src/boot.py`.
  - Add or update `src/main.py`.
  - Add `src/README.md`.
  - Keep startup safe: no GPIO10 power-control changes.

- `firmware: add AIPI-Lite pin constants`
  - Add `pins.py` with constants from `SPEC.md`.
  - Group pins by display, audio, status LED, button, and power.
  - Include docstrings on generated Python methods.

- `tests: add pin map validation tests`
  - Add host-side tests for duplicate pin assignments where duplicates are not
    expected.
  - Check required pin groups exist.
  - Keep tests runnable without hardware.

- `docs: add MicroPython flash and run instructions`
  - Document firmware image selection.
  - Document copy/upload workflow.
  - Document serial log capture.

Acceptance criteria:

- Firmware tree can be copied to a MicroPython ESP32-S3 image.
- Host tests pass.
- Boot sequence produces serial-visible status without touching risky pins.

### `feat/03-gpio-status-input`

Purpose: validate the simplest user I/O: status LED and side button.

Expected commits:

- `firmware: add status LED driver`
  - Drive GPIO46 as a WS2812/NeoPixel-style GRB LED.
  - Add named states: `offline`, `connecting`, `ready`, `recording`,
    `processing`, `speaking`, and `error`.

- `firmware: add side button input`
  - Read GPIO42 as active-low.
  - Add debounce logic.
  - Expose press and release events.

- `firmware: add IO probe mode`
  - Cycle LED states.
  - Print button transitions to serial.
  - Avoid Wi-Fi, display, audio, and GPIO10 during this probe.

- `tests: add status and button logic tests`
  - Test state-to-color mapping.
  - Test debounce behavior with simulated input.

Acceptance criteria:

- LED state colors display correctly on hardware.
- Button press/release events are visible over serial.
- Host tests pass.

### `feat/04-display-bringup`

Purpose: initialize the LCD and render user-visible status.

Expected commits:

- `firmware: add ST7735 display driver wrapper`
  - Use GPIO15 CS, GPIO16 SCLK, GPIO17 MOSI, GPIO7 D/C, and GPIO18 RESET.
  - Use GPIO3 for backlight.
  - Keep hardware-specific initialization isolated.

- `firmware: add status screen renderer`
  - Render boot, Wi-Fi, ready, recording, processing, speaking, and error
    screens.
  - Keep text short enough for the 128 x 128 LCD.

- `firmware: add display probe mode`
  - Cycle through status screens.
  - Print display state transitions over serial.

- `tests: add display layout tests`
  - Test text truncation and line wrapping.
  - Test status-to-screen mapping without hardware.

- `docs: document display assumptions`
  - Record LCD controller assumptions.
  - Record orientation and color order found during hardware testing.

Acceptance criteria:

- LCD initializes reliably after reset.
- Backlight control works.
- Status screens are legible on the target device.
- Host tests pass.

### `feat/05-local-wifi-policy`

Purpose: connect to Wi-Fi and enforce local-only network behavior.

Expected commits:

- `firmware: add Wi-Fi configuration loader`
  - Load SSID, password, and local service URL from ignored local config.
  - Do not commit credentials.

- `firmware: add local endpoint validator`
  - Accept RFC1918 IPv4 addresses, `.local` mDNS names, and explicitly
    operator-approved local DNS names.
  - Reject public internet hostnames by default.

- `firmware: add health check client`
  - Call only configured local `/health`.
  - Report status through serial, LED, and display.

- `tests: add endpoint policy tests`
  - Test accepted local endpoints.
  - Test rejected public endpoints.
  - Test malformed endpoint handling.

- `docs: document local network configuration`
  - Explain config file format.
  - Explain local-only policy and override requirements.

Acceptance criteria:

- Device connects to Wi-Fi using local config.
- Firmware refuses public service endpoints by default.
- Health check state is visible on serial, LED, and display.
- Host tests pass.

### `feat/06-es8311-codec-control`

Purpose: initialize the ES8311 audio codec over I2C.

Expected commits:

- `firmware: add ES8311 register driver`
  - Scan I2C on GPIO4/GPIO5.
  - Detect expected codec address.
  - Provide named initialization sequences for input, output, and shutdown.

- `firmware: add speaker amplifier gate`
  - Control GPIO9 as speaker enable.
  - Default speaker output to disabled during boot and microphone capture.

- `firmware: add codec probe mode`
  - Print I2C scan results.
  - Initialize codec.
  - Toggle speaker enable safely.

- `tests: add codec register sequence tests`
  - Verify expected register writes for each mode.
  - Verify speaker enable defaults to safe/off state.

- `docs: document ES8311 findings`
  - Record detected I2C address.
  - Record working register settings.
  - Record unresolved codec behavior.

Acceptance criteria:

- Codec is detected over I2C.
- Initialization succeeds repeatedly after reset.
- Speaker amplifier remains off unless explicitly enabled.
- Host tests pass.

Implementation notes:

- The expected ES8311 I2C address is `0x18` in 7-bit notation; `0x19` is
  accepted as the alternate CE-state address.
- The initial register sequence configures 16 kHz, 16-bit I2S with MCLK on
  GPIO6, analog microphone input, muted DAC output, and GPIO9 speaker-enable
  held low by default.
- The shutdown sequence mutes the DAC and powers down the ADC/DAC path. Physical
  validation still needs to confirm microphone gain, playback volume, output
  noise, and repeated reset behavior on the target device.

### `feat/07-audio-capture`

Purpose: capture microphone audio from the ES8311/I2S path.

Expected commits:

- `firmware: add I2S microphone capture`
  - Use GPIO6 MCLK, GPIO13 DIN, GPIO12 LRCLK/WS, and GPIO14 BCLK.
  - Start with bounded mono PCM capture.
  - Record sample rate, bit depth, and channel format.

- `firmware: add WAV/PCM sample writer`
  - Package captured audio for upload or local serial extraction.
  - Keep memory use bounded.

- `firmware: add capture probe mode`
  - Capture a short sample on button press.
  - Report level and clipping metrics.

- `tests: add WAV header and buffer tests`
  - Verify WAV header fields.
  - Verify buffer-size limits.
  - Verify capture state transitions.

- `docs: document capture quality`
  - Record tested sample rates.
  - Record noise, gain, clipping, and any dropped-sample symptoms.

Acceptance criteria:

- Device captures a short microphone sample.
- Captured sample can be inspected off-device.
- Capture does not exhaust heap.
- Host tests pass.

### `feat/08-audio-playback`

Purpose: play local audio through the ES8311 speaker path.

Expected commits:

- `firmware: add I2S speaker playback`
  - Use GPIO6 MCLK, GPIO11 DOUT, GPIO12 LRCLK/WS, and GPIO14 BCLK.
  - Enable GPIO9 only while playback is active.
  - Start with WAV/PCM playback at a fixed tested format.

- `firmware: add playback probe mode`
  - Play a generated test tone or local fixture.
  - Report underruns and playback completion.

- `tests: add playback format tests`
  - Verify WAV parsing for supported format.
  - Verify unsupported formats fail clearly.
  - Verify speaker enable timing logic.

- `docs: document playback limits`
  - Record supported formats.
  - Record volume and underrun findings.

Acceptance criteria:

- Device plays a known local audio clip through the speaker.
- Speaker enable is not left on after playback.
- Playback remains stable while display/status updates run.
- Host tests pass.

### `feat/09-local-service-contract`

Purpose: define and test the LAN service API before full assistant integration.

Expected commits:

- `docs: add local service API contract`
  - Document `/health`, `/session`, `/audio`, `/response/{session_id}`, and
    `/audio/{response_id}.wav`.
  - Document request and response payloads.
  - Document error responses.

- `service: add local mock service`
  - Add a development-only local service that accepts uploads and returns a
    known response.
  - Keep it local-only and dependency-light.

- `firmware: add service client`
  - Start session.
  - Upload bounded audio.
  - Poll response.
  - Download response audio.

- `tests: add service contract tests`
  - Test endpoint payloads.
  - Test local-only URL validation remains enforced.
  - Test error handling.

- `docs: add local service runbook`
  - Explain how to run the mock service.
  - Explain network assumptions and logs.

Acceptance criteria:

- Firmware can talk to the mock local service without cloud access.
- Mock service returns deterministic text/audio for firmware testing.
- Contract tests pass.

### `feat/10-push-to-talk-flow`

Purpose: integrate device I/O, local service calls, and audio into one usable
assistant loop.

Expected commits:

- `firmware: add assistant state machine`
  - Model `booting`, `connecting`, `ready`, `recording`, `uploading`,
    `processing`, `speaking`, and `error`.
  - Drive LED and display from the same state source.

- `firmware: add push-to-talk controller`
  - Button press starts capture.
  - Button release stops capture.
  - Long-press behavior remains reserved until power-button behavior is better
    understood.

- `firmware: integrate local service exchange`
  - Start session.
  - Send captured audio.
  - Retrieve text/audio response.
  - Play response.

- `tests: add state machine tests`
  - Test normal flow.
  - Test service unavailable.
  - Test capture failure.
  - Test playback failure.

- `docs: add MVP user workflow`
  - Explain expected device behavior.
  - Explain visible error states.

Acceptance criteria:

- One push-to-talk exchange works end to end with the local mock service.
- No cloud endpoints are contacted.
- Error states are visible and recoverable.
- Host tests pass.

### `feat/11-reliability-power-errors`

Purpose: harden the MVP for repeated local use.

Expected commits:

- `firmware: add Wi-Fi reconnect handling`
  - Recover from dropped Wi-Fi.
  - Return to ready state after service becomes reachable.

- `firmware: add local service retry policy`
  - Bound retries and backoff.
  - Keep user-visible status updated.

- `firmware: add low-power observations`
  - Read GPIO21 charge pulse input if useful.
  - Avoid claiming battery percentage unless verified.
  - Keep GPIO10 usage behind an explicit safety flag.

- `firmware: add runtime diagnostics`
  - Log heap, state transitions, audio buffer underruns, and network failures.
  - Keep logs serial-visible.

- `tests: add reliability logic tests`
  - Test retry bounds.
  - Test reconnect state transitions.
  - Test diagnostics formatting.

- `docs: add troubleshooting guide`
  - Document serial logs.
  - Document common display/LED states.
  - Document recovery steps.

Acceptance criteria:

- Device survives repeated assistant sessions.
- Wi-Fi and local service failures are recoverable.
- Power-management behavior is documented conservatively.
- Host tests pass.

### `feat/12-mvp-release`

Purpose: package the first local-only MVP for repeatable installation and use.

Expected commits:

- `docs: add MVP flashing guide`
  - Include backup prerequisite.
  - Include firmware copy/install steps.
  - Include verification checklist.

- `docs: add MVP configuration guide`
  - Document Wi-Fi and local service config.
  - Document local-only endpoint rules.

- `docs: add MVP validation report template`
  - Include hardware revision/model.
  - Include firmware image version.
  - Include tested I/O devices and pass/fail status.

- `release: add MVP version metadata`
  - Add firmware version file or constant.
  - Record dependency/runtime versions.

- `tests: add MVP regression checklist`
  - Include host tests.
  - Include required hardware manual checks.
  - Include no-cloud network verification.

Acceptance criteria:

- Another operator can install and validate the MVP from documentation.
- Version and runtime details are traceable.
- No secrets or binary firmware dumps are committed.
- Host tests and hardware checklist pass.

### `spike/13-on-device-inference-feasibility`

Purpose: determine whether useful on-device inference can run locally on the
AIPI-Lite without breaking the proven user I/O and audio path.

Expected commits:

- `docs: define on-device inference scope`
  - Define candidate use cases: intent routing, constrained local responses,
    wake-word assistance, or partial assistant logic.
  - Define latency, memory, flash, power, and responsiveness success criteria.
  - Define how the device falls back to the LAN service.

- `docs: inventory candidate runtimes and models`
  - Record candidate runtime options for MicroPython and ESP-IDF.
  - Record model artifact size, license, source, and expected memory needs.
  - Do not commit model binaries unless explicitly approved.

- `firmware: add inference resource probe`
  - Measure heap, flash, CPU timing, and UI responsiveness during simulated
    inference load.
  - Keep microphone, speaker, button, display, and LED checks active.

- `firmware: add local prompt-response experiment`
  - Use a tiny local fixture or mock model interface.
  - Keep all inference inputs and outputs on-device.
  - Avoid cloud model downloads or activation calls.

- `tests: add inference policy tests`
  - Verify public endpoints remain blocked.
  - Verify fallback state is selected when inference is unavailable.
  - Verify model metadata validation rejects unknown artifacts.

- `docs: record feasibility decision`
  - Summarize measured resource use.
  - Decide whether to continue in MicroPython, move inference to ESP-IDF, or
    defer on-device inference.

Acceptance criteria:

- On-device inference feasibility is documented with measurements.
- No cloud endpoint is required for the experiment.
- Core I/O remains responsive during the probe or the limitation is documented.
- A clear continue/defer/fallback decision is recorded.

### `feat/14-on-device-inference`

Purpose: add a supported on-device inference mode only if the feasibility branch
proves it is practical.

Expected commits:

- `firmware: add inference runtime adapter`
  - Isolate runtime-specific calls behind a small interface.
  - Keep the assistant state machine independent from the inference backend.
  - Preserve LAN service fallback.

- `firmware: add model metadata loader`
  - Load model identity, version, source, license, and checksum metadata.
  - Reject missing or unapproved model metadata.
  - Keep large model artifacts out of source control unless explicitly approved.

- `firmware: add local inference mode`
  - Route eligible prompts or intents to the on-device model.
  - Return unsupported requests to LAN service fallback or a clear offline
    response.
  - Keep display, LED, and serial diagnostics updated.

- `firmware: add inference failure handling`
  - Recover from model load failure.
  - Recover from timeout or memory pressure.
  - Disable inference mode if it compromises audio or controls.

- `tests: add inference routing tests`
  - Test on-device route selection.
  - Test fallback to LAN service.
  - Test disabled or missing model behavior.

- `docs: add on-device inference operation guide`
  - Explain model installation and provenance checks.
  - Explain when inference runs locally versus LAN fallback.
  - Document measured limits and known failure modes.

Acceptance criteria:

- At least one useful assistant behavior runs entirely on-device.
- The device remains local-only by default.
- Display, LED, button, microphone, and speaker behavior remain responsive.
- LAN service fallback remains available.
- Model/runtime provenance is documented.
- Host tests and hardware checks pass.

## Conditional Fallback Branch

### `fallback/esp-idf-audio-runtime`

Purpose: replace the MicroPython runtime only if a documented fallback criterion
blocks the MVP.

Expected commits:

- `docs: record MicroPython fallback decision`
  - Identify the failed criterion.
  - Include logs, reproduction steps, and tested runtime version.

- `firmware: add ESP-IDF project skeleton`
  - Add minimal ESP32-S3 project layout.
  - Add pin constants matching `SPEC.md`.
  - Preserve local-only endpoint policy.

- `firmware: port GPIO display and LED probes`
  - Recreate already validated user I/O.
  - Keep behavior consistent with the MicroPython branch.

- `firmware: port ES8311 audio path`
  - Use ESP-IDF I2C and I2S drivers.
  - Prove stable microphone capture and speaker playback.

- `tests: add ESP-IDF validation path`
  - Add build instructions.
  - Add any available unit tests.
  - Add hardware checklist.

Acceptance criteria:

- Fallback reason is documented with evidence.
- ESP-IDF firmware reaches or exceeds the last successful MicroPython milestone.
- Local-only communication policy remains intact.

## Cross-Branch Requirements

- Keep replacement firmware local-only by default.
- Do not commit Wi-Fi credentials, service secrets, firmware dumps, or device
  serial-specific tokens.
- Do not commit model binaries or inference runtime artifacts without explicit
  approval.
- Keep on-device inference optional until feasibility measurements show it is
  stable on the target device.
- Keep all generated Python methods documented with docstrings.
- Add host-side tests for Python logic whenever code is generated.
- Update `SPEC.md` when hardware behavior is verified or corrected.
- Update `FIRMWARE_PLAN.md` when scope or fallback criteria change.
- Track hardware validation results in branch documentation before merge.
- Keep U.S. Federal security, privacy, accessibility, procurement, and
  supply-chain considerations visible in documentation and release notes.
