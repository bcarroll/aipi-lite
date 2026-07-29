# Windows Preflight Five-Second Delay Design

**Date:** 2026-07-29
**Issue:** #36 follow-up
**Status:** Approved for specification review

## Goal

Give the AIPI-Lite five seconds to complete a hard reset before `mpremote`
reconnects for validation and post-flash application uploads.

## Context

The issue #36 reconnect fix currently builds this shared preflight sequence:

```text
reset
sleep 1.0
connect COMx
fs cp -r SOURCE_CHILDREN :/.
```

Both `validate.cmd` and `install.cmd --flash-micropython` use that sequence.
The operator requested a five-second wait for both workflows. Ordinary
`install.cmd` uploads do not request a preflight reset and must remain
unchanged.

## Scope

Change the existing shared
`VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS` value from `"1.0"` to `"5.0"`.
The resulting preflight sequence will be:

```text
reset
sleep 5.0
connect COMx
fs cp -r SOURCE_CHILDREN :/.
```

The shared value will continue to control:

- the `mpremote sleep` argument used by validation uploads;
- the `mpremote sleep` argument used after explicit firmware flashing; and
- the operator-visible preflight message and redacted failure diagnostics.

Keep all other behavior unchanged:

- Normal `install.cmd` uploads still connect once and copy immediately.
- Validation and post-flash uploads still reconnect to the same validated COM
  port.
- The existing recursive copy to `:/.` remains unchanged.
- Validation still skips the post-cleanup reset before its probe batch.
- Upload failures still stop cleanup and probes.
- Diagnostics remain bounded and redacted.
- No retry, device fallback, configurable delay, or second upload process is
  added.

## Alternatives Considered

### Separate validation and post-flash constants

Introduce two delay constants, both set to five seconds. This would allow
future divergence, but there is no current requirement for different timing
and duplicated values could drift.

### Configurable command-line delay

Add an operator option with a five-second default. This expands the public
interface and validation surface without a demonstrated need.

### Selected approach

Retain one shared constant and change it to five seconds. This is the smallest
change that applies the approved timing uniformly to both preflight-reset
workflows.

## Test Plan

Use red-green development in `tests/test_windows_installer.py`.

Behavior tests will use the literal `"5.0"` rather than deriving the expected
value from the production constant. They will require that:

- a validation preflight command places `sleep`, `"5.0"`, and the same-port
  reconnect before `fs cp`;
- a post-flash upload uses that same five-second preflight command;
- ordinary uploads still contain one `connect` and no `sleep`;
- the validation transcript and redacted diagnostics report a five-second
  wait; and
- existing upload-failure handling remains unchanged.

Update active workflow documentation in `README.md`, `tools/README.md`, and
`FIRMWARE_IMPL.md` from one second to five seconds. Historical design and
implementation-plan records will remain unchanged; this follow-up design
records the timing revision.

Run:

```text
python3 -m unittest tests.test_windows_installer -v
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
```

## Federal and Security Considerations

This change only increases a bounded local wait. It adds no dependency,
network call, credential, telemetry, device-selection behavior, firmware
content, or GPIO operation. Existing local-only, redaction, fail-closed, and
traceability behavior remains unchanged.

## Delivery and Hardware Gate

After host validation, commit and push the feature branch, merge it into
`main`, push `main`, and verify the remote refs.

Keep issue #36 open until a physical:

```cmd
validate.cmd --port COMx --yes
```

reports application upload status `0` and a validation batch status other than
`not-run`.
