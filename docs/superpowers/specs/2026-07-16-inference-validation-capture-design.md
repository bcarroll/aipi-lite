# Inference Validation Capture Design

## Purpose

Extend `dev_install.sh` with an opt-in `--inference-probe` mode that runs the
existing offline `inference_probe.run_probe()` after an application-first
upload. The mode captures a redacted, issue-ready feasibility report and, when
explicitly requested with `--gh`, creates one new GitHub issue for that bench
run.

The extension records physical validation evidence without adding a model
runtime, a model artifact, Wi-Fi, speaker playback, telemetry, or firmware
flashing.

## Invocation and Scope

The supported form is:

```bash
./dev_install.sh \
  --inference-probe \
  --gh \
  --device-label bench-a \
  --inference-check display=pass \
  --inference-check status-led=pass \
  --inference-check button=pass \
  --inference-check offline=pass \
  -- --port /dev/cu.usbmodem31101
```

`--inference-probe` requires one explicit installer `--port PORT` argument.
This prevents the wrapper from issuing the probe against an ambiguous device.
The normal installer remains responsible for uploading the current `src/`
application tree. Its existing defaults continue to skip stock backup, erase,
and MicroPython flashing. The wrapper also disables generated local Wi-Fi
configuration and appends `--no-reset` unless it was already supplied, so the
normal Wi-Fi application flow cannot start as part of the capture.

`--inference-check NAME=STATUS` is repeatable. Supported names are `display`,
`status-led`, `button`, and `offline`; supported statuses are `pass`, `fail`,
and `not-observed`. Missing checks are recorded as `not-observed`. The wrapper
does not claim that a physical observation passed without an operator-supplied
value.

## Execution Flow

1. Parse and validate the existing developer options plus the inference
   options. Reject invalid check values, duplicate check names, a missing
   explicit port, and incompatible cleanup/help operations before the
   installer starts.
2. Run `install.sh` through the existing visible, captured application-first
   path. If installation fails, do not run the probe.
3. Resolve `mpremote` from the local tooling environment, with a documented
   test-only command override. Run the existing explicit offline probe on the
   selected port. Capture its stdout and stderr into the same raw transcript
   and record the probe command, status, stable serial lines, and decision.
4. Redact the transcript and all report fields. In addition to existing secret,
   credential, Wi-Fi, MAC, and home-path rules, redact serial-device paths.
5. Write `run-metadata.txt` and `github-issue-body.md` with an inference
   validation section: installer status, probe status, decision/reason, heap,
   flash, elapsed-time, button metrics when present, and the four operator
   checks.
6. If `--gh` is present, create one new issue from the redacted body. Use an
   inference-specific default title. Store the returned issue URL only in the
   local capture directory. If GitHub tooling, authentication, or creation
   fails, retain the redacted local body and return the real installer/probe
   status rather than masking it.

The wrapper exits with the installer failure status when installation fails;
otherwise it returns the probe execution status. A valid `defer_inference` or
`offline_unsupported` decision is evidence, not a wrapper failure. A probe
that cannot run or emit a valid decision is a validation failure.

## Data Handling and GitHub Safety

All artifacts remain in ignored `tools/.local/dev-install/` directories with
restricted permissions. GitHub receives only the redacted issue body; it does
not receive the raw transcript, local capture directory, serial port, Wi-Fi
details, credentials, tokens, device identifiers, firmware dumps, model
binaries, or generated weights.

GitHub creation occurs only with explicit `--gh`; `--prepare-only` always
leaves the issue body local. The current `gh` authentication state is not a
prerequisite for local capture and is never treated as a successful upload.

## Error Handling

- Invalid inference options fail before installer execution.
- Installer failure prevents probe execution and preserves the installer exit
  status.
- Missing `mpremote`, a probe command failure, or missing/invalid decision is
  recorded as a failed validation after a successful install.
- GitHub creation failure leaves a redacted local issue body and does not
  overwrite installer or probe status.
- A failed or unobserved physical check is reported exactly as supplied; it
  does not change the probe decision or promote the spike.

## Validation

Host tests will stub the installer, `mpremote`, and `gh` to verify option
validation, application-first argument passthrough, probe execution only after
successful installation, stable report extraction, redaction of secrets and
serial paths, operator-check recording, issue creation, and local fallback.
The repository validation set will include the focused capture tests, the full
unit-test suite, shell syntax checks, and `git diff --check`.

Documentation will update `README.md`, `INFERENCE_FEASIBILITY.md`, and the
developer tooling guide with the exact command, evidence expectations, and
GitHub fallback. The feasibility decision remains `defer_inference` until an
actual bench report is captured.

## Out of Scope

- Supported inference runtime or model integration.
- Model download, storage, or provenance approval.
- Wi-Fi, LAN, cloud, telemetry, or public endpoint use.
- Speaker playback or GPIO10 power control.
- Automatic issue closure, labels, assignment, or pull-request creation.
