# Windows Device Validation Wi-Fi Probe Design

**Date:** 2026-07-24
**Status:** Approved

## Goal

Extend the Windows physical device validation sweep so it also exercises the
local Wi-Fi/health path, keeping one command (`validate.cmd`) that validates
AIPI-Lite hardware end-to-end on a connected device and files the redacted
results as a GitHub issue for later parsing.

## Current Behavior

`validate.cmd` calls `tools/windows_installer.py validate`
(`run_device_validation`), which uploads `src/`, runs the display, io, codec,
capture, playback, and inference probes in one raw-REPL `mpremote` session,
prompts the operator for physical observations, redacts secrets, writes
artifacts under `tools/.local/device-validation/`, and creates a structured
GitHub issue via `gh issue create`.

The sweep does not currently include the `wifi_probe` local-health check, so a
validation run never confirms the device connects to the configured local
network and reaches the local `/health` endpoint.

## Chosen Approach

Add a `wifi` entry to `DEVICE_VALIDATION_PROBES` in
`tools/windows_installer.py`, placed after `playback` and before `inference`.

Because `wifi_probe.run_probe()` returns a status string (`"ok"` / `"error"`)
instead of raising, it is driven with `assert wifi_probe.run_probe() == "ok"`.
This fails the shared try/except wrapper in `device_validation_batch_code`
exactly like every other probe, so the existing batch generator, result parser
(`parse_device_validation_probe_statuses`), aggregate-status logic
(`device_validation_status`), and issue body (`write_device_validation_issue_body`)
all pick up the new probe with no other changes. The `wifi` probe has no
operator observation of its own — its result is fully determined by the serial
status marker, mirroring the existing `codec` probe.

The probe's `wifi_probe:` serial prefix is already covered by the generic prefix
filter in `device_validation_serial_lines`, and all issue output passes through
`redact_text`, so credentials, MAC addresses, serial ports, and local paths
remain redacted.

## Serial and Issue Contract

The batch program continues to print, per probe:

```text
device_validation_probe: starting <name>
device_validation_result: name=<name> status=<0|1>
```

New probe order: `display`, `io`, `codec`, `capture`, `playback`, `wifi`,
`inference`. The issue body `## Probe Results` section gains a `wifi` line, and
`run-metadata.txt` gains a `probe_wifi_status=` line. Aggregate status remains
`0` only when the upload, the batch, every probe, and every observation passed.

## Safety

The `wifi` probe only connects to the operator-configured local network and
calls the local `/health` endpoint. It does not drive GPIO10 board power or the
speaker gate.

## Prerequisite

The `wifi` probe requires an uploaded `src/local_wifi_config.py` and a reachable
local mock service (`python3 -m service.mock_service ...`). Without both, the
`wifi` probe fails and the aggregate validation status is non-zero, which is the
correct signal for an incomplete bench setup.

## Testing

`tests/test_windows_installer.py` is extended to expect `wifi` in the probe set,
in the generated batch program (including the `assert ... == 'ok'` idiom), in
`parse_device_validation_probe_statuses`, and in the device validation issue
body Probe Results section.
