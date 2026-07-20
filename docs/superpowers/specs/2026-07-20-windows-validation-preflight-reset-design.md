# Windows Validation Preflight Reset Design

## Context

GitHub issue #28 records a Windows `validate.cmd --port COM8` run that failed
before it copied any application files. `mpremote fs cp` could not enter raw
REPL and received no device serial response. The no-reset validation workflow
currently attempts the first filesystem operation while the normal
push-to-talk application may already be running.

The upload failure is recoverable without changing firmware, erasing flash, or
changing network configuration. `mpremote` supports a hard reset followed by a
wait and later filesystem action in one command sequence. A filesystem action
then establishes the raw-REPL state required for the copy, while MicroPython
skips normal `main.py` execution during that raw-REPL reset.

## Goals

- Establish a fresh device state before the Windows physical-validation upload.
- Keep the validation upload and its preflight reset in one `mpremote`
  invocation.
- Preserve the validation workflow's existing no-reset behavior after upload,
  cleanup, and probe execution.
- Fail before copying files if the preflight command cannot complete.
- Preserve the application-first, local-only firmware policy.

## Non-Goals

- Do not change ordinary `install.cmd` behavior.
- Do not flash or erase firmware, enter the bootloader, configure Wi-Fi, call a
  network service, or drive GPIO10.
- Do not retry indefinitely or infer that a physical device is healthy from a
  successful host command.
- Do not modify the device-side push-to-talk application solely to accommodate
  the installer.

## Design

`InstallRequest` will gain an explicit preflight-reset flag whose default is
disabled. The `validate` subcommand alone will enable it. Normal Windows
application installs keep their current upload command and reset-after-upload
policy unchanged.

When the flag is enabled, the existing application upload command will be one
ordered `mpremote` command sequence:

```text
mpremote connect COMx reset sleep 1.0 fs cp -r SOURCE_CHILDREN :
```

`reset` is a hard reset, and the one-second `sleep` provides a bounded startup
window before the first filesystem action enters raw REPL and copies the already
staged source children to device root. `SOURCE_CHILDREN` is the exact ordered
output of the existing `stage_application_source` helper. The command uses no
erase, bootloader, or firmware-write operation. Because the reset and copy share
one process, there is no separate host-side reconnect between them.

The validation flow continues to pass `no_reset=True` to the shared installer.
That still skips the post-upload reset after guarded cleanup, leaving the
device in the raw-REPL state needed for the one-session validation-probe batch.

## Failure Handling

- A nonzero preflight/upload command result is an upload failure; cleanup and
  validation probes do not run.
- The command transcript remains in the ignored local validation capture and
  the generated issue records the non-passing upload status.
- A continued raw-REPL failure after the preflight reset remains non-destructive
  and instructs the operator through the existing failure transcript to verify
  the selected port and power-cycle the device before a new run.
- The helper performs no automatic flashing, erase, or unbounded retry loop.

## Implementation Boundaries

- Change only the Windows host helper and its host-side tests plus the related
  validation documentation and roadmap evidence.
- Reuse the existing staged source tree, COM-port validation, local `mpremote`
  virtual environment, upload status handling, redacted capture artifacts, and
  automatic validation issue creation.
- Keep the preflight delay as a named bounded host-tool constant, not an
  operator-specific tracked setting.

## Validation and Documentation

Host-side tests in `tests/test_windows_installer.py` will verify that:

- a normal install keeps the existing direct upload command;
- a validation request emits exactly one preflight-reset, delay, and filesystem
  copy sequence in that order;
- staged source children still map to device root; and
- a preflight/upload failure stops before cleanup or validation probes.

Update `README.md`, `tools/README.md`, and `FIRMWARE_IMPL.md` to describe the
validation-only preflight reset, post-upload no-reset behavior, safe failure
boundary, and required physical-device follow-up. Before committing the
implementation, run the focused Windows tests, the full Python suite, required
shell syntax checks, and `git diff --check`.
