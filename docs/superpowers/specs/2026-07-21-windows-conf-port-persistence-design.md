# Windows Installer Serial-Port Persistence Design

Date: 2026-07-21
Status: Implemented; Windows hardware validation pending

## Summary

Allow the direct Windows `install.cmd` workflow to reuse a validated serial port
from the ignored root `.conf` file so routine application uploads do not require
`--port`. On a first run without a saved port, the installer will select and
persist the port only when Windows reports exactly one COM port. Zero or multiple
detected ports require an explicit `--port COMx` selection.

The change remains application-first and local-only. It does not add firmware
flashing, backup, restore, automatic repository updates, a production dependency,
or broader configuration persistence for the developer and validation commands.

## Goals

- Reuse `AIPI_SERIAL_PORT` in the existing ignored root `.conf` file.
- Make `install.cmd` usable without `--port` after a port has been selected.
- Auto-select a port on first use only when exactly one COM port is detected.
- Keep explicit `--port COMx` authoritative and use it to seed or replace the
  saved value.
- Preserve unrelated `.conf` answers and avoid partial configuration writes.
- Retain current port validation before prerequisites are installed or the
  device is modified.

## Non-Goals

- Do not add `.conf` persistence to `validate.cmd`.
- Do not relax the explicit-port requirement for inference capture through
  `dev_install.cmd`.
- Do not add interactive device-selection menus.
- Do not silently switch away from a stale or invalid saved COM port.
- Do not add `pyserial` or another port-discovery dependency.
- Do not change Unix flashing, backup, restore, or application-upload behavior.

## Existing Behavior

`install.cmd` delegates to the `install` subcommand in
`tools/windows_installer.py`. The command-line parser permits an omitted
`--port`, but the shared install-request builder rejects the upload because it
requires a COM port. Windows port discovery already reads the native serial
registry without an external dependency.

The Unix `install.sh` workflow already stores `AIPI_SERIAL_PORT` as a plain
`KEY=value` entry in the ignored root `.conf`. The Windows implementation will
use that same file and key so the repository has one installer answer file.

## Configuration Interface

`tools/windows_installer.py` will define the repository-root `.conf` path and
small helpers with these responsibilities:

- Read the first exact `AIPI_SERIAL_PORT=` entry as plain text without sourcing
  or executing the file.
- Treat a missing entry, an empty value, or the Unix sentinel value `auto` as no
  saved Windows port.
- Validate any other saved value through the existing `normalize_com_port()`
  function.
- Update matching `AIPI_SERIAL_PORT=` lines to one normalized value, or append
  the key when it is absent.
- Preserve comments, blank lines, and every unrelated configuration entry.
- Write a sibling `.conf.tmp.<process-id>` file and atomically replace `.conf`
  only after the complete new content has been written successfully.

The helpers will not interpret shell expansions, quotes, environment variables,
or arbitrary expressions. The persisted form is exactly:

```text
AIPI_SERIAL_PORT=COM7
```

## Direct Install Selection Flow

Only the direct `install.cmd` path gains implicit port resolution. Its order is
deterministic:

1. List the currently detected Windows COM ports.
2. If `--port COMx` was supplied, normalize it and require it to be present in
   the detected list.
3. Otherwise, read `AIPI_SERIAL_PORT` from `.conf`. If it contains a normalized
   COM port, require that port to be present in the detected list.
4. If no saved port exists and exactly one COM port is detected, select it.
5. If no ports are detected, stop and tell the operator to connect the device.
6. If multiple ports are detected, list them and require
   `install.cmd --port COMx`.

The source precedence is therefore:

| Priority | Source | Result |
| --- | --- | --- |
| 1 | Explicit `--port COMx` | Validate, select, and replace the saved value. |
| 2 | Saved `AIPI_SERIAL_PORT` | Validate and reuse without changing targets. |
| 3 | Exactly one detected COM port | Select and save it automatically. |
| 4 | Zero or multiple detected ports | Stop without selecting a port. |

An explicit or newly auto-selected port is persisted after it passes current
Windows port detection and before prerequisite setup or application upload.
Consequently, a later tooling, transport, cleanup, or reset failure does not
discard a valid operator selection. The upload path retains its existing
defensive validation before touching the device.

## Stale and Invalid Configuration

A saved value that is neither empty, `auto`, nor a valid COM-port name is an
invalid configuration error. A syntactically valid saved port that is not
currently detected is stale. In either case, direct install stops and explains
how to correct the selection with `install.cmd --port COMx`.

The installer will not silently replace a stale saved port with another detected
port, even when only one alternative is present. This prevents an unattended
upload from switching to a different serial device. An explicit valid port
replaces the stale value.

`install.cmd --list-ports` remains read-only and never creates or updates
`.conf`.

## Command Scope

- `install.cmd`: explicit, saved, or exactly-one detected port selection.
- `dev_install.cmd` normal capture: retains its current explicit install argument
  behavior.
- `dev_install.cmd --inference-probe`: continues requiring exactly one explicit
  `-- --port COMx` argument.
- `validate.cmd`: continues requiring `--port COMx` in its command parser.

This narrow scope implements the requested routine-install convenience without
weakening workflows that collect evidence for a specifically identified device.

## Error Messages

Errors will be actionable and avoid exposing configuration contents beyond the
non-secret COM-port names already shown by `--list-ports`:

- No detected ports: connect the AIPI-Lite and retry.
- Multiple detected ports: list the available COM names and require an explicit
  selection.
- Invalid saved value: identify `AIPI_SERIAL_PORT` as invalid and show the
  corrective explicit command shape.
- Stale saved port: identify the saved COM name, list detected COM names when
  present, and show the corrective explicit command shape.
- Configuration write failure: stop before prerequisite setup or device upload
  and leave the original `.conf` intact.

## Testing

Host-side tests in `tests/test_windows_installer.py` will cover:

- An explicit port taking precedence over a different saved value.
- A valid saved port being reused when `--port` is omitted.
- Exactly one detected port being selected and persisted with no prior value.
- Missing, empty, and `auto` configuration values using first-run discovery.
- Zero detected ports failing without modifying `.conf`.
- Multiple detected ports failing and listing the choices without modifying
  `.conf`.
- An invalid or stale saved port requiring explicit correction rather than
  silently switching devices.
- Atomic updates preserving comments, blank lines, and unrelated values.
- An explicit or auto-selected port remaining persisted when a later upload
  fails.
- `--list-ports` remaining read-only.
- Existing explicit-port requirements for inference and validation remaining
  unchanged.

No device hardware is required for these tests. Existing mocks for Windows
registry discovery, prerequisite setup, and upload execution will remain the
test boundary.

## Documentation and Validation

`README.md` and `tools/README.md` will document the first-run auto-selection,
saved-port reuse, explicit correction path, and scope limitation to
`install.cmd`. The current examples with explicit `--port` remain valid.

Before the implementation commit, validation will run:

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
bash -n tools/setup_micropython_tools.sh
git diff --check
```

The implementation will add docstrings to all new Python methods and functions,
retain the existing U.S. Federal requirements posture, avoid new dependencies,
and keep `.conf`, temporary configuration files, local tools, and device-specific
answers outside Git.
