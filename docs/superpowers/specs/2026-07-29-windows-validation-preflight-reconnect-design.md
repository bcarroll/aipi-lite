# Windows Validation Preflight Reconnect Design

**Date:** 2026-07-29
**Issue:** #36
**Status:** Approved for specification review

## Goal

Allow `validate.cmd` to reconnect after its required preflight hard reset so
the existing, proven application copy can complete and physical probes can
start.

## Observed Failure

Issue #36 records a physical validation run with:

```text
Hard-resetting <redacted-serial-port> and waiting 1.0 seconds before validation upload...
Uploading application source to <redacted-serial-port>...
mpremote: cp: destination does not exist
Application upload failed with status 1.
```

The same device accepts the application copy when the operator runs
`install.cmd`. The relevant command difference is:

```text
install.cmd:
mpremote connect COMx fs cp -r SOURCE_CHILDREN :/.

validate.cmd:
mpremote connect COMx reset sleep 1.0 fs cp -r SOURCE_CHILDREN :/.
```

The destination and staged source are therefore not sufficient explanations
for the validation-only failure.

## Root Cause

In `mpremote` 1.28.0, the `reset` alias executes a delayed
`machine.reset()` through `exec --no-follow`. Entering that command establishes
raw REPL and changes the process state so later commands do not automatically
enter raw REPL again.

After the device resets, the host-side transport object still records that it
is in raw REPL. The following `sleep` changes no connection state. The
filesystem command therefore reuses the stale transport instead of reopening
the serial connection and establishing a new raw-REPL session. Its
multi-source destination check can then report that `:/.` does not exist.

Normal `install.cmd` does not place a hard reset before its copy. Its first
filesystem action enters raw REPL through a fresh transport, which is
consistent with the reported successful upload.

## Scope

Change only preflight-reset uploads so they reconnect to the selected COM port
after the existing one-second wait and before the existing copy:

```text
mpremote connect COMx
  reset
  sleep 1.0
  connect COMx
  fs cp -r SOURCE_CHILDREN :/.
```

The second `connect` makes `mpremote` close the stale transport, reopen the same
operator-selected COM port, restore automatic raw-REPL setup, and let the
filesystem command establish a fresh session.

Preflight reset is currently used by:

- `validate.cmd` before its no-reset application upload; and
- `install.cmd --flash-micropython` after the flashed device has rebooted.

Both paths will receive the reconnect because both otherwise place a hard
reset before the shared upload. A normal `install.cmd` run, developer capture,
and other uploads without a preflight reset retain their current command
unchanged.

Keep all other behavior unchanged:

- Continue staging a cache-free copy of the children of `src/`.
- Continue copying the staged root children recursively to `:/.`.
- Continue placing files at `/boot.py`, `/main.py`, and `/lib/...`.
- Continue using one `mpremote` process for the ordered preflight and upload.
- Continue failing closed on a nonzero upload result.
- Continue skipping cleanup and physical probes after an upload failure.
- Continue running guarded cleanup after a successful upload.
- Continue leaving validation uploads without a post-cleanup reset.
- Continue bounding and redacting validation diagnostics.

This change does not add dependencies or alter firmware source, flashing
parameters, COM-port selection, GitHub reporting, network behavior,
credentials, device pin control, probe behavior, or operator observations.

## Alternatives Considered

### Separate reset and upload processes

Run the hard reset in one `mpremote` process, wait on the host, and start the
existing upload in a second process. This would guarantee fresh process state,
but it introduces an additional subprocess result and complicates the existing
single upload-transaction failure boundary.

### Explicit-file upload rewrite

Replace every recursive multi-source upload with directory preparation and one
copy per manifest file. This avoids the destination-directory check, but it is
broader than the physical evidence requires and can still encounter the stale
transport left by the reset. It is superseded by this reconnect design.

### Selected approach

Reconnect inside the existing `mpremote` process. It directly repairs the
identified state transition, leaves the working ordinary-install command
untouched, and retains one preflight/upload subprocess result.

## Error Handling

The existing `run_streaming` call remains the preflight/upload transaction
boundary. A reset, reconnect, raw-REPL entry, or copy failure returns a nonzero
status through the existing handling:

- Report `Application upload failed with status N`.
- Skip guarded cleanup.
- Skip physical validation probes.
- Preserve bounded, redacted diagnostics in validation artifacts.

The reconnect always targets the already validated COM port. There is no
fallback device selection, retry loop, firmware erase, or partial-upload
cleanup.

## Test Plan

Use red-green development in `tests/test_windows_installer.py`.

Tests will require that:

- A normal install command remains exactly one `connect` followed by the
  existing recursive copy to `:/.`.
- A preflight-reset upload contains `reset`, the one-second `sleep`, and a
  second `connect` to the same port before `fs cp`.
- The reconnect occurs for both physical validation and post-flash uploads.
- The existing root-child source mapping and destination remain unchanged.
- A preflight/upload failure still stops before cleanup and validation probes.
- No new process, retry, or device-selection fallback is introduced.

Update `README.md`, `tools/README.md`, and `FIRMWARE_IMPL.md` to describe the
validation preflight reconnect and its preserved failure boundary.

Run:

```text
python3 -m unittest tests.test_windows_installer -v
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
```

## Federal and Security Considerations

The change is local host orchestration only. It does not transmit data, add a
service, introduce credentials, change cryptography, alter public-network
policy, or add a production dependency. Existing redaction, local-artifact,
traceability, least-change, and fail-closed behavior remain in force.

## Delivery and Hardware Gate

After host validation, commit the implementation, push the issue branch, merge
it into `main`, and push `main`.

Host tests cannot prove that the device re-enumerates and accepts the fresh
raw-REPL session. Keep issue #36 open until a physical:

```cmd
validate.cmd --port COMx --yes
```

reports application upload status `0` and a validation batch status other than
`not-run`.
