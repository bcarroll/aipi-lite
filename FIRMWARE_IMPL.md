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

## Merge Order

1. `feat/01-backup-recovery`
2. `feat/02-micropython-skeleton`
3. `feat/03-gpio-status-input`
4. `feat/04-display-bringup`
5. `feat/05-local-wifi-policy`
6. `feat/06-es8311-codec-control`
7. `feat/07-audio-capture`
8. `feat/08-audio-playback`
9. `feat/09-local-service-contract`
10. `feat/10-push-to-talk-flow`
11. `feat/11-reliability-power-errors`
12. `feat/12-mvp-release`

Conditional fallback branch:

- `fallback/esp-idf-audio-runtime`

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
  - Add `firmware/micropython/boot.py`.
  - Add `firmware/micropython/main.py`.
  - Add `firmware/micropython/README.md`.
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
- Keep all generated Python methods documented with docstrings.
- Add host-side tests for Python logic whenever code is generated.
- Update `SPEC.md` when hardware behavior is verified or corrected.
- Update `FIRMWARE_PLAN.md` when scope or fallback criteria change.
- Track hardware validation results in branch documentation before merge.
- Keep U.S. Federal security, privacy, accessibility, procurement, and
  supply-chain considerations visible in documentation and release notes.
