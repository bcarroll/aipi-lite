# Windows Inference Validation Capture Design

## Purpose

Extend the native Windows developer workflow, invoked as `dev_install.cmd`, so
the machine attached to an AIPI-Lite can independently upload the current
application, run the existing offline inference feasibility probe, retain local
redacted evidence, and create a new GitHub issue for review.

The implementation remains in `tools/windows_installer.py`; `dev_install.cmd`
continues to be a small Command Prompt entry point. No Bash, WSL, Git Bash,
third-party Python package, model runtime, model artifact, cloud inference, or
firmware-flashing support is added.

## Command Interface

The Windows command is:

```cmd
dev_install.cmd --inference-probe --gh bcarroll/aipi-lite --device-label bench-a --inference-check display=pass --inference-check status-led=pass --inference-check button=pass --inference-check offline=pass -- --port COM3 --yes
```

New developer options are:

- `--inference-probe`: opt in to the probe after a successful application
  upload.
- `--inference-check NAME=STATUS`: repeatable operator observation. Supported
  names are `display`, `status-led`, `button`, and `offline`; statuses are
  `pass`, `fail`, and `not-observed`. Duplicate names and invalid values fail
  before device activity.
- `--gh [OWNER/REPO]`: explicitly request one new GitHub issue. The repository
  may be supplied directly; when omitted, the helper resolves the GitHub
  `origin` remote. `--gh-title TITLE` optionally replaces the generated title.

`--inference-probe` requires exactly one explicit `-- --port COMx` installer
argument. The wrapper forces `--no-reset` for the upload so normal application
startup does not run before the probe. The Windows installer never generates
local Wi-Fi configuration, and the inference mode must not add such behavior.

## Execution Flow

1. Parse and validate the developer options and forwarded installer arguments.
   Reject flash/recovery options, ambiguous or missing ports, and invalid
   inference checks before creating tools or touching the device.
2. Perform the existing application-first upload with `no_reset=True`. If it
   fails, do not execute the probe.
3. Reuse the same locally installed `mpremote.exe` to execute
   `import inference_probe; inference_probe.run_probe()` against the selected
   `COM` port. Stream the command output into the existing transcript sink.
4. Require one valid probe decision line: `candidate_supported`,
   `defer_inference`, or `offline_unsupported`. The latter two are valid
   evidence and return success when the command itself succeeded; an absent or
   invalid decision is a validation failure.
5. Write raw and redacted transcripts, metadata, and `github-issue-body.md`
   under ignored `tools/.local/dev-install/`. The issue body contains only
   redacted installer/probe evidence and operator checks; it does not include
   raw artifacts, COM ports, credentials, tokens, Wi-Fi values, MAC addresses,
   or local capture paths.
6. With explicit `--gh`, invoke an installed and authenticated `gh issue
   create --repo OWNER/REPO --title TITLE --body-file github-issue-body.md`.
   Record the created URL only in the local capture directory. If repository
   resolution, `gh` availability/authentication, or issue creation fails, keep
   the redacted issue body locally and preserve the real installation or probe
   result.

`--prepare-only` continues to create local artifacts without uploading,
probing, or creating an issue.

## Data Handling and Safety

The helper reuses the existing redaction for credentials, Wi-Fi values, MAC
addresses, and COM ports. All issue text is built from redacted output, and
operator fields are individually redacted before issue creation. The new
GitHub subprocess is the only network operation in the inference-capture path;
the firmware probe remains offline-first and does not call an endpoint or use
speaker playback.

The mode rejects operations that could flash, restore, back up, clean tools,
or self-update. It never attempts GPIO10 power control.

## Testing and Documentation

Host-side tests will mock Windows serial discovery, application upload,
`mpremote`, and `gh` to prove no-reset sequencing, valid decision capture,
redaction, metadata/issue-body content, explicit GitHub creation, local
fallback, and failure paths. Existing Windows developer-capture tests remain
valid. `README.md`, `INFERENCE_FEASIBILITY.md`, and `tools/README.md` will add
the Windows `dev_install.cmd` invocation and fallback behavior.

The physical validation decision remains `defer_inference` until an operator
runs this command on the device-attached machine and the resulting issue is
reviewed.
