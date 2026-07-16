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
- Use `tooling/<topic>` for host-only developer utilities that do not change
  firmware runtime behavior.
- Use `spike/<topic>` for disposable hardware experiments that should not be
  merged as production firmware.
- Use `fallback/<topic>` only if the MicroPython path fails a documented
  fallback criterion.
- Keep commits small enough that each one explains one usable increment.
- For generated Python code, include tests in the same branch.
- Do not add production dependencies without explicit approval.

## Merge Order Checklist

Legend: implementation status uses ✅ Complete, 🟡 Pending, or ❌ Failed.
Validation status uses ✅ Validated or 🟡 Not Validated. Each icon is paired
with text so the checklist does not rely on color alone.

1. ✅ Complete | 🟡 Not Validated - `feat/01-backup-recovery`
2. ✅ Complete | 🟡 Not Validated - `feat/02-micropython-skeleton`
3. ✅ Complete | ✅ Validated - `feat/03-gpio-status-input`
4. ✅ Complete | ✅ Validated - `feat/04-display-bringup`
5. ✅ Complete | 🟡 Not Validated - `feat/05-local-wifi-policy`
6. ✅ Complete | 🟡 Not Validated - `feat/06-es8311-codec-control`
7. ✅ Complete | 🟡 Not Validated - `feat/07-audio-capture`
8. ✅ Complete | 🟡 Not Validated - `feat/08-audio-playback`
9. ✅ Complete | ✅ Validated - `feat/09-local-service-contract`
10. ✅ Complete | 🟡 Not Validated - `feat/10-push-to-talk-flow`
11. ✅ Complete | 🟡 Not Validated - `feat/11-reliability-power-errors`
12. ✅ Complete | 🟡 Not Validated - `feat/12-mvp-release`

Support tooling branch:

- ✅ Complete | ✅ Validated - `tooling/dev-install-capture`

Optional on-device inference branches:

13. ✅ Complete | 🟡 Not Validated - `spike/13-on-device-inference-feasibility`
14. 🟡 Pending | 🟡 Not Validated - `feat/14-on-device-inference`

Conditional runtime fallback branch:

- 🟡 Pending | 🟡 Not Validated - `fallback/esp-idf-audio-runtime`

## Current Implementation Status

The repository now includes an earlier implementation from
`https://github.com/bcarroll/aipi-lite` at remote commit `b06b569`. That imported
code should be treated as the current source baseline for implementation work.
Legacy checked-in firmware binaries are intentionally excluded from the current
workflow; firmware images should be downloaded or generated into ignored
tooling directories.

| Branch / component | Status | Evidence | Remaining work |
| --- | --- | --- | --- |
| `feat/01-backup-recovery` | Implemented | `install.sh` skips Git self-update by default, exposes explicit `--self-update`, can write sanitized debug artifacts for GitHub issues, can list and probe serial ports with `--list-ports`, can discover and use one responsive MicroPython port when upload runs omit `--port`, can clean downloaded prerequisite artifacts while preserving backups/debug/captures, uploads application source by default to an already-flashed ESP32_GENERIC_S3 MicroPython device, stores answers in `.conf`, prompts for bootloader readiness only during explicit flash/restore flows, locks a successful esptool auto-detected port for later backup/flash commands, verifies the ESP32-S3 ROM bootloader responds to `esptool chip-id` without auto-reset before backup, erase, write, or restore operations, skips stock backup, erase, and MicroPython flashing by default for application-first uploads, can opt in to MicroPython flashing with `--flash-micropython` / `AIPI_FLASH_MICROPYTHON=1`, can opt in to stock flash backup with `--flash-micropython --backup-stock` / `AIPI_FLASH_MICROPYTHON=1` plus `AIPI_BACKUP_STOCK_FIRMWARE=1`, keeps exact-size validation, no-reset chunked reads, smaller-chunk retries, compatibility with `--skip-backup` / `AIPI_SKIP_STOCK_BACKUP=1`, and a structured `stock_backup_blocked` trace event when an opt-in backup cannot read flash, restores saved stock backups, and `RECOVERY.md` documents backup, restore, expected recovery output, blocked-backup handling, and the flashing safety checklist. | Validate the restore flow on physical hardware and record exact stock serial logs. |
| `tooling/dev-install-capture` | Implemented | `dev_install.sh`, `install.sh --trace`, `tests/test_dev_install_capture.py`, `tests/test_install_script.py`, `README.md`, and `tools/README.md` add host-only installer capture plus deeper trace diagnostics. Captures include raw/redacted transcripts, run metadata, hardware validation notes, GitHub-ready issue bodies, automatic issue creation, installer phase transitions, firmware metadata, best-effort target probes, upload inventory, and command status under ignored local storage. | Use it during physical hardware validation runs and refine collected metadata if real bench analysis needs more fields. |
| `feat/02-micropython-skeleton` | Implemented | `src/boot.py`, `src/main.py`, `src/lib/pins.py`, `src/README.md`, and host tests provide safe startup defaults, grouped pin constants, serial-visible bring-up status, protected GPIO10 behavior, and hardware-free regression coverage. The copied application root now keeps only startup files plus ignored operator config, with reusable application modules under `src/lib/`. `main.py` now continues from safe startup into the local push-to-talk application instead of stopping at a skeleton-ready screen. | Validate the normal boot serial output and push-to-talk readiness on physical hardware. |
| `feat/04-display-bringup` | Implemented, hardware validated | `src/lib/display.py`, `src/lib/display_probe.py`, `src/lib/aipi_lite_config.py`, `src/main.py`, tracked external display drivers under `src/lib/drivers/`, and `tests/test_aipi_lite_display.py` add an ST7735 wrapper, PWM backlight control, named status screens, an opt-in display probe, and host-side layout coverage. Operator hardware validation on 2026-06-25 reported that `display_probe.run_probe(cycles=2)` passed. | Capture a photo or full display probe serial transcript during a future bench run if exact orientation, color, and readability evidence is needed. |
| LCD pin constants | Implemented | `src/lib/pins.py` includes display, button, status LED, ES8311 audio, speaker enable, charge input, and board power constants from `SPEC.md`. | Verify unconfirmed GPIO10 power behavior before any branch attempts to drive it. |
| `feat/03-gpio-status-input` | Implemented, hardware validated | `src/lib/status_led.py`, `src/lib/button.py`, `src/lib/io_probe.py`, and `tests/test_gpio_status_input.py` add GPIO46 status states, GPIO42 active-low debounce events, a GPIO-only serial probe, and host regression coverage. Operator hardware validation on 2026-06-25 observed the GPIO46 LED blink several colors, recorded the GPIO42 button press correctly, and reported no errors. | Capture a full `io_probe` serial transcript during a future bench run if exact output evidence is needed. |
| `feat/05-local-wifi-policy` | Implemented, hardware validation pending | `src/lib/wifi_config.py`, `src/lib/local_endpoint.py`, `src/lib/wifi_probe.py`, `.gitignore`, `install.sh`, and `tests/test_wifi_policy.py` add ignored local config loading, installer-assisted `local_wifi_config.py` creation, local-only endpoint validation, a Wi-Fi `/health` probe, and host-side policy coverage. | Run `wifi_probe.run_probe()` on physical hardware with a local service and record connection, endpoint, LED, and display behavior. |
| `feat/06-es8311-codec-control` | Implemented, hardware validation pending | `src/lib/es8311.py`, `src/lib/audio_probe.py`, `src/main.py`, and `tests/test_es8311_codec.py` add ES8311 I2C detection, register setup, GPIO9 speaker gate defaults, and host-side regression coverage. | Run `audio_probe.run_probe()` on physical hardware and record the observed scan and audio behavior. |
| `feat/07-audio-capture` | Implemented, hardware validation pending | `src/lib/audio_capture.py`, `src/lib/capture_probe.py`, and `tests/test_audio_capture.py` add bounded 16 kHz 16-bit mono I2S capture, WAV packaging, capture metrics, an opt-in capture probe, BCLK-derived ES8311 clocking, and host-side coverage. | Run `capture_probe.run_probe()` on physical hardware and record gain, clipping, noise floor, dropped-sample behavior, and BCLK-derived codec behavior. |
| `feat/08-audio-playback` | Implemented, hardware validation pending | `src/lib/audio_playback.py`, `src/lib/playback_probe.py`, and `tests/test_audio_playback.py` add bounded 16 kHz 16-bit mono PCM/WAV playback, generated low-volume test tone output, I2S TX setup on GPIO11/GPIO12/GPIO14, BCLK-derived ES8311 clocking, GPIO9 speaker enable timing, DAC mute/unmute safety, and host-side coverage for format rejection and write metrics. | Run `playback_probe.run_probe()` on physical hardware and record volume, output noise, underruns, and BCLK-derived codec behavior. |
| `feat/09-local-service-contract` | Implemented | `src/lib/service_contract.py`, `src/lib/service_client.py`, `service/mock_service.py`, `service/README.md`, and `tests/test_local_service_contract.py` define the local-only API, stdlib mock service, firmware client, request/response payloads, error handling, and host-side contract coverage. | Use the client during `feat/10-push-to-talk-flow` integration and validate it against the mock service from device hardware. |
| `feat/10-push-to-talk-flow` | Implemented, hardware validation pending | `src/main.py`, `src/lib/assistant_state.py`, `src/lib/push_to_talk.py`, `tests/test_main_startup.py`, and `tests/test_push_to_talk_flow.py` add the assistant state machine, normal-boot push-to-talk startup, shared LED/display/serial state output, button press/release handling, bounded capture handoff, local service exchange, response playback, recoverable error states, and host-side flow coverage. | Run one complete exchange on physical hardware against the mock service and record capture, upload, response text, playback, and visible state behavior. |
| `feat/11-reliability-power-errors` | Implemented, hardware validation pending | `src/lib/reliability.py`, `src/lib/push_to_talk.py`, `MVP.md`, and `tests/test_reliability.py` add bounded retry/backoff, retry diagnostics, reconnect helper, runtime diagnostics formatting, GPIO21 charge-pulse observation, and GPIO10 board-power guarding. | Validate repeated sessions, Wi-Fi/service recovery, serial diagnostics, GPIO21 observations, and that GPIO10 remains unchanged on hardware. |
| `feat/12-mvp-release` | Implemented, hardware validation pending | `src/lib/version.py`, `MVP.md`, `README.md`, `src/README.md`, and `tests/test_mvp_release.py` add local-only MVP version metadata, install/configuration guidance, validation checklist, report template, and no-cloud verification expectations. | Complete the MVP validation report from a physical hardware run and record tested MicroPython/runtime versions. |
| `spike/13-on-device-inference-feasibility` | Implemented, hardware validation pending | `src/lib/inference_probe.py`, `INFERENCE_FEASIBILITY.md`, `README.md`, `src/README.md`, `dev_install.sh`, `dev_install.cmd`, `tools/windows_installer.py`, and host tests add an offline-first simulated inference resource probe, deterministic local prompt fixture, model metadata validation, no-network policy checks, a feasibility report template, and redacted GitHub-ready bench capture on Unix or Windows. | Run the appropriate `dev_install` inference capture on physical hardware and record heap, flash, timing, button, LED, display, and decision behavior. Speaker output is not required for this validation path. |
| `feat/14-on-device-inference` | Not started | No imported inference runtime integration. | Add only after feasibility is proven. |

## Hardware Validation Notes

- 2026-06-25: Operator reported successful application deployment to the
  AIPI-Lite with the display showing `AIPI-LITE`, `Booting`, and
  `Local firmware`. A following GPIO probe run made the GPIO46 status LED blink
  several colors, recorded the GPIO42 button press correctly, and reported no
  errors. The full serial transcript was not available.
- 2026-06-25: Operator reported that the explicit display probe
  `display_probe.run_probe(cycles=2)` passed on physical hardware. No full
  display probe serial transcript or photo evidence was captured.
- 2026-07-08: The current test AIPI-Lite has its speaker disconnected. The
  on-device inference feasibility probe is therefore scoped to heap, flash,
  timing, button, LED, display, offline prompt fixture, metadata, and no-network
  behavior. Speaker playback remains validated separately through the audio
  playback branch when hardware is connected for that purpose.
- 2026-06-24: GitHub issue #11 captured a `dev_install.sh --trace` run on
  commit `8afdc028f0edd44d57d4ed176837a6e5db6ad855` that stopped safely during
  the then-default stock firmware backup. `esptool` connected to an ESP32-S3 on
  `/dev/ttyS7`, then `read-flash` repeatedly failed at offset `0x100000` after
  retrying down to the `0x1000` minimum chunk size. The installer did not erase
  or write flash because no complete stock backup was available. Current
  application-first installs skip backup by default; use
  `--flash-micropython --backup-stock` only for recovery-focused runs that
  should still stop on this read failure.
- 2026-06-24: GitHub issue #12 repeated the same blocked backup signature on
  commit `fc5fa6a788d8b029b08ee1942c282e53f854cfca`. `dev_install.sh --gh`
  now keeps this known stock-backup-blocked capture local instead of creating
  another automatic issue; use `--issue OWNER/REPO#NUMBER` to attach a later
  capture to a chosen tracking issue after bench triage.

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

### `tooling/dev-install-capture`

Purpose: give developers a repeatable way to run the normal installer, capture
exactly what an operator could see, and attach the sanitized transcript to a
GitHub issue for ChatGPT inspection.

Expected commits:

- `tooling: add developer install wrapper`
  - Add `dev_install.sh` as a host-only wrapper around `install.sh`.
  - Pass installer CLI arguments through to `install.sh` without changing the
    normal install, backup, restore, prompt, or exit-code behavior.
  - Capture combined stdout/stderr while still showing output interactively.

- `tooling: add issue-ready transcript handling`
  - Store captured logs and issue bodies only under ignored local tooling paths.
  - Redact common secrets, tokens, Wi-Fi values, and local-only identifiers
    before preparing any GitHub issue content.
  - Require an explicit issue target before posting, and leave a local issue
    body artifact when GitHub upload tooling is unavailable or unauthenticated.

- `tests: add developer installer wrapper checks`
  - Verify pass-through argument handling with a stub installer.
  - Verify transcript capture preserves visible installer output.
  - Verify redaction runs before any issue body is posted or written.

- `docs: document developer issue capture`
  - Explain how developers run `dev_install.sh` with installer arguments.
  - Explain where local logs are stored and why they remain ignored.
  - Explain GitHub issue posting prerequisites and manual fallback behavior.

Acceptance criteria:

- `dev_install.sh` runs the same installer path a normal operator would run.
- The script preserves prompts, visible output, and the installer exit status.
- A redacted transcript is added to, or prepared for, an explicit GitHub issue.
- A redacted transcript can create a new GitHub issue for an explicit or
  inferred repository, or comment on an explicit existing issue.
- Missing GitHub tooling does not lose the local transcript or mask installer
  failures.
- No credentials, device tokens, firmware dumps, or local-only artifacts are
  committed.

Implementation notes:

- `dev_install.sh` writes each run to `tools/.local/dev-install/` by default,
  including `install-transcript-raw.txt`, `install-transcript-redacted.txt`,
  `run-metadata.txt`, and `github-issue-body.md`.
- Developer options are parsed before a `--` separator; all remaining arguments
  are passed to `install.sh` unchanged.
- `--device-label` and repeatable `--hardware-note` entries add non-secret
  validation context for later device analysis.
- `--issue OWNER/REPO#NUMBER` or a GitHub issue URL posts the redacted issue
  body through an already-installed and authenticated `gh` CLI. Without `gh`, or
  with `--prepare-only`, the issue body remains local for manual review.
- `--gh OWNER/REPO` creates a new GitHub issue from the redacted issue body
  through the same authenticated `gh` CLI, and bare `--gh` uses
  `AIPI_GITHUB_REPO` or the local `origin` remote when possible.
  `--gh-title TITLE` overrides the generated install-capture title. `--gh` and
  `--issue` are mutually exclusive so one capture run cannot create and comment
  on issues at the same time.
- The wrapper exits with the installer status even if GitHub posting fails, so
  capture/reporting problems do not hide installer failures.
- `install.sh --trace` enables `--debug` and writes a separate redacted trace
  artifact under `tools/.local/debug/` with installer phase transitions,
  firmware path/size/checksum metadata, prerequisite status, best-effort
  esptool target identity probes, MicroPython/mpremote probes,
  source upload inventory, command exit statuses, and reset status.
- `dev_install.sh --trace` passes tracing through to the installer while keeping
  the visible transcript and GitHub issue body behavior unchanged.

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

Implementation notes:

- Display setup uses the existing ST7735-compatible driver, SPI bus 1 at
  20 MHz, GPIO15 CS, GPIO16 SCLK, GPIO17 MOSI, GPIO7 D/C, GPIO18 reset, and
  GPIO3 PWM backlight.
- The renderer uses rotation `1`, RGB color order enabled, a 128 x 128 screen,
  bounded ASCII truncation, and status screens for boot, Wi-Fi, ready,
  recording, processing, speaking, and error.
- `aipi_lite_config.py` remains as a compatibility shim for the imported display
  baseline. New code should use `display.py`.
- Operator hardware validation on 2026-06-25 reported the explicit display
  probe passed with the current rotation, color constants, text size, and
  backlight behavior. Capture photo evidence during a later bench run if exact
  visual records are needed.

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

Implementation notes:

- Operator configuration belongs in ignored `src/local_wifi_config.py` with
  `WIFI_SSID`, `WIFI_PASSWORD`, `LOCAL_SERVICE_URL`, and optional
  `APPROVED_LOCAL_HOSTS`.
- Endpoint validation accepts RFC1918 IPv4, loopback/link-local IPv4 for bench
  testing, `.local` mDNS names, and explicitly approved local hostnames. Public
  IPv4 addresses, public hostnames, embedded credentials, query strings, and
  unsupported schemes fail closed before Wi-Fi or HTTP calls.
- `wifi_probe.py` uses MicroPython station mode, validates the endpoint before
  connecting, calls only the derived local `/health` URL, and reports state
  through serial plus available LED/display modules.
- Physical validation still needs to confirm MicroPython `network.WLAN`,
  `urequests`, local mDNS behavior, and status UI behavior on the target device.

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
- The initial register sequence configures 16 kHz, 16-bit I2S with the ES8311
  deriving its internal clock from GPIO14 BCLK, analog microphone input, muted
  DAC output, and GPIO9 speaker-enable held low by default. The physical GPIO6
  MCLK connection remains undriven by standard MicroPython I2S.
- The shutdown sequence mutes the DAC and powers down the ADC/DAC path. Physical
  validation still needs to confirm microphone gain, playback volume, output
  noise, and repeated reset behavior on the target device.

### `feat/07-audio-capture`

Purpose: capture microphone audio from the ES8311/I2S path.

Expected commits:

- `firmware: add I2S microphone capture`
  - Use GPIO13 DIN, GPIO12 LRCLK/WS, and GPIO14 BCLK; derive the codec clock
    from BCLK.
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

Implementation notes:

- `audio_capture.py` configures I2S RX for 16 kHz, 16-bit, mono PCM using
  GPIO13 DIN, GPIO12 LRCLK/WS, and GPIO14 BCLK; the ES8311 derives its clock
  from BCLK.
- Capture requests are bounded by `MAX_CAPTURE_BYTES` before allocation, and
  `capture_pcm()` deinitializes owned I2S objects after reading.
- WAV packaging is available through `wav_bytes()` for REPL extraction or later
  local-service upload work; `capture_probe.py` keeps the speaker amplifier gate
  disabled and reports byte count, sample count, peak level, and clipping count.
- Physical validation still needs to record microphone gain, noise, clipping,
  dropped-sample observations, and BCLK-derived codec behavior on the target
  firmware image.

### `feat/08-audio-playback`

Purpose: play local audio through the ES8311 speaker path.

Expected commits:

- `firmware: add I2S speaker playback`
  - Use GPIO11 DOUT, GPIO12 LRCLK/WS, and GPIO14 BCLK; derive the codec clock
    from BCLK.
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

Implementation notes:

- `audio_playback.py` supports bounded 16 kHz, 16-bit, mono PCM and RIFF/WAVE
  payloads with matching format fields. Unsupported sample rates, channel
  counts, bit depths, non-PCM formats, oversized payloads, and unaligned PCM
  fail before I2S writes.
- I2S TX uses GPIO11 DOUT, GPIO12 LRCLK/WS, and GPIO14 BCLK with bounded write
  chunks; the ES8311 derives its clock from BCLK. Partial frame writes are
  rejected; partial aligned writes are retried and counted as underruns for
  serial diagnostics.
- `playback_probe.py` initializes the ES8311 output path, generates a short
  low-volume test tone, unmutes the DAC only during playback, enables GPIO9
  only while I2S samples are being written, and always disables GPIO9 plus
  mutes the DAC before returning.
- Physical validation still needs to confirm audible output, safe volume,
  output noise, underrun behavior, and BCLK-derived codec behavior on the
  target firmware image.

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

Implementation notes:

- `service_contract.py` defines contract version
  `aipi-lite-local-service-v1`, endpoint paths, status names, content types, and
  path-safe URL helpers.
- `service_client.py` validates the configured base URL with
  `local_endpoint.validate_local_endpoint()` before requests and supports
  `/health`, `/session`, `/audio`, `/response/{session_id}`, and local response
  WAV downloads. All HTTP responses are closed after processing.
- `service/mock_service.py` is a development-only Python standard-library HTTP
  service. It accepts sessions and audio uploads, returns deterministic response
  text, and serves a deterministic 16 kHz, 16-bit, mono WAV response.
- `service/README.md` documents request payloads, response payloads, headers,
  error responses, and the local runbook. The mock service has no production
  authentication or hardening and must stay on an operator-controlled local
  network.

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

Implementation notes:

- `assistant_state.py` defines the shared assistant state names and maps each
  state to existing LED/display status names. `StatusOutputs` updates serial,
  GPIO46 LED, and LCD from the same state transition source.
- `push_to_talk.py` adds `PushToTalkController`, which validates local service
  health, moves to `recording` on debounced button press, captures bounded WAV
  audio on release, starts a local service session, uploads audio, retrieves
  response text/audio, plays response WAV audio, and returns to `ready`.
- Capture, service, and playback dependencies are injectable so host tests can
  cover normal flow, service failure, capture failure, playback failure, and
  button polling without attached hardware.
- Long-press behavior remains reserved until GPIO10 board-power behavior is
  physically validated.

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

Implementation notes:

- `reliability.py` adds `RetryPolicy` and `call_with_retries()` for bounded
  attempts and backoff. The push-to-talk controller uses this policy for local
  service health, session, upload, response, and audio download operations.
- `DiagnosticsLog` emits serial-friendly state transitions, retry events,
  failure types, heap observations when available, and runtime metrics such as
  playback underruns.
- `ReconnectManager` centralizes Wi-Fi reconnect attempts around the existing
  local Wi-Fi connector without changing endpoint policy.
- `ChargePulseReader` reads GPIO21 only as a charge-pulse observation and does
  not infer battery percentage. `BoardPowerGuard` keeps GPIO10 blocked unless a
  future hardware-validated safety flag explicitly allows control.

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

Implementation notes:

- `version.py` records firmware name, local-only MVP version, target model,
  local-only profile, and service contract metadata for serial/reporting use.
- `MVP.md` packages the stock-backup prerequisite, flashing workflow, ignored
  local Wi-Fi/service configuration, MVP validation checklist, no-cloud network
  verification, and a validation report template.
- README files now reference the assistant flow, reliability helpers, MVP
  metadata, and validation guide.

### `spike/13-on-device-inference-feasibility`

Purpose: determine whether useful on-device inference can run locally on the
AIPI-Lite without requiring networking and without breaking the proven user I/O
path.

Expected commits:

- `docs: define on-device inference scope`
  - Define candidate use cases: intent routing, constrained local responses,
    wake-word assistance, or partial assistant logic.
  - Define latency, memory, flash, power, and responsiveness success criteria.
  - Define visible local decisions for unsupported or deferred inference without
    making Wi-Fi or a LAN service a usability requirement.

- `docs: inventory candidate runtimes and models`
  - Record candidate runtime options for MicroPython and ESP-IDF.
  - Record model artifact size, license, source, and expected memory needs.
  - Do not commit model binaries unless explicitly approved.

- `firmware: add inference resource probe`
  - Measure heap, flash, CPU timing, and UI responsiveness during simulated
    inference load.
  - Keep button, display, and LED checks active when available.
  - Do not require speaker output, Wi-Fi, local services, model downloads, or
    activation calls.

- `firmware: add local prompt-response experiment`
  - Use a tiny local fixture or mock model interface.
  - Keep all inference inputs and outputs on-device.
  - Avoid cloud model downloads or activation calls.

- `tests: add inference policy tests`
  - Verify network requirements and endpoints are blocked for the probe.
  - Verify local decision state is selected when inference is unavailable.
  - Verify model metadata validation rejects unknown artifacts.

- `docs: record feasibility decision`
  - Summarize measured resource use.
  - Decide whether to continue in MicroPython, move inference to ESP-IDF, or
    defer on-device inference.

Acceptance criteria:

- On-device inference feasibility is documented with measurements.
- No network endpoint is required for the experiment.
- Button, display, and LED responsiveness remain observable during the probe or
  the limitation is documented.
- A clear continue/defer/fallback decision is recorded.

Implementation notes:

- `INFERENCE_FEASIBILITY.md` defines the offline-first scope, candidate runtime
  inventory, decision states, success criteria, and hardware validation report.
- `src/lib/inference_probe.py` provides an explicit `run_probe()` entrypoint that
  measures heap and flash metrics when available, runs a bounded simulated
  CPU/memory load, polls GPIO42 when available, refreshes optional LED/display
  outputs, and returns `candidate_supported`, `defer_inference`, or
  `offline_unsupported`.
- The probe validates model provenance metadata without loading model binaries
  and rejects any endpoint or network requirement. It does not start Wi-Fi or
  call local, vendor, public, cloud, OTA, telemetry, or analytics services.
- The deterministic local prompt fixture is only a feasibility harness. It is
  not a supported model runtime and should not be wired into normal startup.
- The current feasibility decision remains `defer_inference` until a physical
  hardware run records heap, flash, timing, button, LED, and display behavior.
  A disconnected speaker does not block this validation path.
- `dev_install.sh` and `dev_install.cmd` can each run the offline probe after
  an application-only, no-reset upload and independently create a redacted
  GitHub issue when the connected host explicitly supplies `--gh` plus an
  authenticated GitHub CLI. Failed GitHub publishing leaves the issue body in
  ignored local tooling without changing the measured validation result.

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
  - Explain when inference runs locally, when the device reports a local
    unsupported/deferred state, and when an operator-configured local service is
    used as an optional assistant path.
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
- Keep developer install transcripts and GitHub issue payloads redacted, and
  post them only to an explicit issue target chosen by the operator.
- Keep all generated Python methods documented with docstrings.
- Add host-side tests for Python logic whenever code is generated.
- Update `SPEC.md` when hardware behavior is verified or corrected.
- Update `FIRMWARE_PLAN.md` when scope or fallback criteria change.
- Track hardware validation results in branch documentation before merge.
- Keep U.S. Federal security, privacy, accessibility, procurement, and
  supply-chain considerations visible in documentation and release notes.
