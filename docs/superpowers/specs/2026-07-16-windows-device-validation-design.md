# Windows Physical AIPI-Lite Validation Design

## Purpose

Provide `validate.cmd` as the Windows entry point for a repeatable, physical
AIPI-Lite bench-validation run. The command uploads the current application
without resetting into normal startup, runs the self-contained device probes,
records explicit operator observations, and creates one redacted GitHub issue
for each parsed validation run.

The workflow deliberately excludes Wi-Fi, local-service, and push-to-talk
validation. Those checks require operator-specific configuration and a local
service endpoint, so they remain explicit workflows rather than side effects of
the physical validation command.

## Command Interface

The native entry point is:

```cmd
validate.cmd --port COM8 --yes --device-label bench-a
```

`validate.cmd` locates `py -3` or `python` and delegates to the existing
`tools/windows_installer.py` helper using a new `validate` subcommand. The
subcommand requires exactly one Windows `--port COMx` value. `--yes` approves
creation of the ignored local `mpremote` virtual environment when it is not
already available. `--device-label` is optional and is redacted before it is
placed in a GitHub issue.

The command uses `AIPI_GITHUB_REPO` when it contains a valid `OWNER/REPO`
value; otherwise it resolves the repository from the local `origin` remote.
There is no `--gh` opt-in flag: every successfully parsed validation run
attempts to create a new issue.

## Validation Flow

1. Validate the requested COM port, ensure local `mpremote` tooling, and copy
   the current `src/` tree to the device with reset disabled. A reset is not
   performed because normal startup may enter the local Wi-Fi and push-to-talk
   workflow, which is out of scope for this command.
2. Invoke each probe in a separate `mpremote connect COMx exec` command. The
   helper records the command status and its complete serial transcript, then
   continues to later independent probes after a failure.
3. Run the probes in this order:
   - `display_probe.run_probe(cycles=2)`;
   - `io_probe.run_probe(cycles=1)`;
   - `audio_probe.run_probe(toggle_speaker=False)`;
   - `capture_probe.run_probe()`;
   - `playback_probe.run_probe()`;
   - `inference_probe.run_probe()`.
4. Prompt the operator for `pass`, `fail`, or `not-observed` after the relevant
   serial probe completes. The reported observations are display, status LED,
   button, microphone capture, speaker playback, and inference UI behavior.
   Input is case-insensitive. Invalid input is retried; unavailable interactive
   input records `not-observed` rather than inferring a physical result.
5. Aggregate probe exit statuses and operator observations. Any failed probe or
   `fail`/`not-observed` observation produces a nonzero validation result, so a
   successful process status never overstates physical validation. A malformed
   command line prints usage and does not create an issue because it is not a
   validation run.

All probe execution remains application-first and local. The flow does not
flash firmware, back up or erase flash, configure Wi-Fi, call a local service,
or drive GPIO10. The playback probe is intentionally retained because it is a
low-volume, bounded speaker validation; the codec-only probe leaves the speaker
gate disabled.

## Reporting and Failure Handling

Each parsed run receives a unique ignored capture directory under
`tools/.local/device-validation/`. It stores the raw transcript, redacted
transcript, run metadata, and the generated GitHub issue body.

The issue contains the aggregate result, per-probe statuses, explicit operator
observations, and a redacted serial transcript. Redaction reuses the existing
Windows helper rules for secrets, COM ports, MAC addresses, and local paths.
No credentials, device token, serial port, or local filesystem path is included
in the GitHub body.

The helper calls `gh issue create` for every parsed run, even when upload or one
or more probes fail, so failure evidence is reported. If `gh` is missing,
unauthenticated, repository resolution fails, or issue creation fails, the
generated issue body remains in the ignored capture directory and the console
reports the publishing failure. GitHub publishing failure is reported separately
from physical validation status and does not convert an otherwise accurate
validation result into a false pass.

## Implementation Boundaries

- Add `validate.cmd` as a minimal launcher parallel to `install.cmd` and
  `dev_install.cmd`.
- Extend `tools/windows_installer.py` with a focused validation request,
  device-probe runner, observation prompt/parser, capture artifact writer, and
  issue-body formatter. Reuse existing COM-port validation, local `mpremote`,
  streaming output, redaction, repository resolution, and GitHub issue creation
  helpers rather than duplicating them.
- Keep all generated local artifacts in ignored `tools/.local/` paths.
- Do not add a production dependency. The existing operator-installed `gh` CLI
  remains the publishing mechanism.

## Tests and Documentation

Add host-side tests in `tests/test_windows_installer.py` for:

- `validate.cmd` delegation and Python fallback;
- required COM-port parsing and forced no-reset upload;
- ordered probe execution that continues after a failure;
- explicit operator observations, including noninteractive `not-observed`;
- aggregate failure status for failed or unobserved checks;
- redacted capture and GitHub issue content; and
- automatic new-issue creation plus a retained local body when publishing fails.

Document the Windows command, required operator interaction, GitHub CLI
authentication, expected local artifacts, probe scope, and no-reset safety in
`README.md` and `tools/README.md`. Update `FIRMWARE_IMPL.md` to record the
physical validation/reporting capability and its remaining bench evidence.
