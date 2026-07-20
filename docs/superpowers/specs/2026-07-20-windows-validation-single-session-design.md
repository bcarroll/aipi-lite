# Windows Device Validation Single-Session Design

## Context

GitHub issue #27 records a Windows `validate.cmd` run that uploaded the
application without reset, then completed the display probe but failed before
the IO probe could enter raw REPL. The failure occurred during a fresh
`mpremote` process for the second probe.

The current validation helper starts one `mpremote connect COMx exec` process
per probe. Each process has an independent raw-REPL connection lifecycle. That
introduces a disconnect and re-entry boundary after every probe, even though
the application is deliberately held out of normal startup for the validation
run. `mpremote` supports executing a scripted action after it has established
one raw-REPL session, so the validation sequence can avoid those boundaries.

## Goals

- Run the complete physical validation sequence through one `mpremote`
  connection and one raw-REPL session.
- Retain per-probe status in the redacted report.
- Continue to later probes when an earlier probe raises a regular device-side
  exception.
- Treat a transport failure, a missing result marker, a failed probe, or a
  non-passing operator observation as a failed validation run.
- Preserve the application-first, no-reset validation workflow and existing
  local-artifact/redaction behavior.

## Non-Goals

- Do not change the firmware probe implementations, normal application
  startup, Wi-Fi configuration, local-service behavior, or GPIO10 safeguards.
- Do not add dependencies or attempt automatic physical-device recovery.
- Do not claim physical validation from host-side tests.

## Design

`tools/windows_installer.py` will generate one static MicroPython batch program
from `DEVICE_VALIDATION_PROBES`. The generated program executes the existing
probe commands in their established order: display, IO, codec, capture,
playback, then offline inference.

Before and after each probe, the batch prints a stable, machine-readable result
line. A regular probe exception is caught by the batch, recorded as a failure
marker, and does not prevent subsequent probes from running. Result markers use
only fixed probe names and numeric statuses; arbitrary exception text is not
placed into the GitHub-ready report.

The host invokes the batch as one command:

```text
mpremote connect COMx exec <generated-validation-batch>
```

It does not launch another `mpremote` process between probes. The first action
establishes raw REPL and performs the normal `mpremote` soft-reset setup; every
probe then runs in that same session, so `main.py` does not resume between
probe commands.

The helper parses only result markers emitted after the batch begins. It maps
each configured probe to its marker status. A missing or malformed marker is a
failure for that probe. The overall `mpremote` process status is recorded as a
separate batch/transport result and must be zero for aggregate validation to
pass, even if all expected device markers were printed.

Operator observation prompts remain explicit and conservative. The console
will identify the probes while they run, and the existing `pass`, `fail`, and
`not-observed` questions will be asked in established observation order after
the batch completes. This keeps the serial connection open for the entire
probe sequence while preserving the existing report fields and all-pass exit
criteria.

## Failure Handling

- A device-side probe exception prints that probe's failure marker and allows
  the remaining probes to run.
- A host transport error or nonzero `mpremote` exit marks the validation batch
  as failed. Parsed markers are still retained as diagnostic evidence.
- Missing/malformed result markers mark the corresponding probe as failed.
- A failed or unavailable operator observation still causes an aggregate
  failure; host tooling never infers a physical pass.
- The existing redacted local transcript, metadata, and GitHub issue body are
  still written for every parsed run. Publishing problems remain separate from
  the measured validation status.

## Implementation Boundaries

- Replace the per-probe `mpremote` subprocess loop with one focused batch
  command builder, result parser, and batch runner in
  `tools/windows_installer.py`.
- Keep `DeviceValidationProbe` as the single source for ordering, probe code,
  serial prefixes, and requested observations.
- Retain the existing no-reset upload, COM-port validation, ignored capture
  paths, redaction helpers, GitHub issue publishing, and offline-only policy.
- Do not modify production firmware or introduce external services.

## Validation and Documentation

Host-side tests in `tests/test_windows_installer.py` will cover:

- generated batch syntax and ordered inclusion of every probe command;
- a single `mpremote` invocation for the full validation run;
- parsing successful, failed, missing, and malformed result markers;
- continued device-side execution after a reported probe failure;
- aggregate failure for a nonzero transport status or missing marker; and
- retained/redacted validation artifacts and explicit operator observations.

The implementation will update `README.md`, `tools/README.md`, and
`FIRMWARE_IMPL.md` to state that Windows validation holds one raw-REPL session
for the full probe sequence and presents operator observations after the batch.
Before committing the implementation, the repository checks will run the
focused Windows tests, the full Python test suite, both required shell syntax
checks, and `git diff --check`.
