# Developer Device Test Runbook

Use this workflow to test the current firmware application against a connected
AIPI-Lite from a Windows host and automatically report redacted findings to a
GitHub issue.

## Prerequisites

- Connect the device over USB-C. Bootloader mode is only required for explicit
  firmware flashing, not for application uploads or validation.
- Install Python 3 for Windows with the `py` launcher, or make `python`
  available on `PATH`.
- Install and authenticate GitHub CLI. The `gh` command comes from GitHub CLI,
  GitHub's official command-line tool. Use the official installation
  instructions at <https://cli.github.com/>, then authenticate:

```cmd
gh auth login
gh auth status
```

- Choose the repository that should receive new install capture issues and
  identify the COM port. If the port is uncertain, probe first:

```cmd
install.cmd --list-ports
```

  To comment on an existing issue instead of creating a new one, use
  `--issue OWNER/REPO#123` in place of `--gh` on the developer wrapper.

## Install And Report

Run the installer through the developer wrapper. The wrapper preserves the
installer exit status, captures the visible install output, redacts common
secrets, and posts the issue body to GitHub.

```cmd
dev_install.cmd --gh bcarroll/aipi-lite --gh-title "AIPI-Lite bench-a install capture" --device-label bench-a --hardware-note "MVP install validation" -- --port COM3 --yes
```

The run writes local artifacts under the ignored path:

```text
tools\.local\dev-install\
```

Do not commit or manually attach stock firmware backups, firmware dumps,
credentials, `.conf`, Wi-Fi settings, or device tokens.

The wrapper prints the created issue URL and stores it in the local capture
directory. For follow-up probe comments, use `--issue OWNER/REPO#123` on the
next capture.

## Physical Device Validation

Use the dedicated validation command to hard-reset the device, upload the
application, run the self-contained device probes, collect operator
observations, and create one redacted GitHub issue for the run:

```cmd
validate.cmd --port COM3 --yes --device-label bench-a
```

The command reports each probe result, prompts for `pass`, `fail`, or
`not-observed` for each physical observation, and records that evidence in the
GitHub report. Raw and redacted transcripts, metadata, and the GitHub-ready body
are retained under ignored `tools\.local\device-validation\`.

## Optional Post-Install Probes

After install, use `mpremote` for focused hardware checks. Record pass/fail
observations as GitHub issue comments or as `--hardware-note` values on the next
developer install capture.

```cmd
tools\.local\micropython-venv\Scripts\mpremote connect COM3 exec "import io_probe; io_probe.run_probe(cycles=1)"
tools\.local\micropython-venv\Scripts\mpremote connect COM3 exec "import display_probe; display_probe.run_probe(cycles=1)"
tools\.local\micropython-venv\Scripts\mpremote connect COM3 exec "import audio_probe; audio_probe.run_probe()"
tools\.local\micropython-venv\Scripts\mpremote connect COM3 exec "import capture_probe; capture_probe.run_probe()"
tools\.local\micropython-venv\Scripts\mpremote connect COM3 exec "import playback_probe; playback_probe.run_probe()"
```

For Wi-Fi and local service validation, create ignored `src/local_wifi_config.py`
on the device first, then run:

```cmd
tools\.local\micropython-venv\Scripts\mpremote connect COM3 exec "import wifi_probe; wifi_probe.run_probe()"
```

## Reporting A Failed Run

If a run fails, rerun the capture with a short non-secret note describing the
visible LED, display, or serial symptom:

```cmd
dev_install.cmd --gh bcarroll/aipi-lite --gh-title "AIPI-Lite bench-a failed install capture" --device-label bench-a --hardware-note "failure observed: describe visible LED/display/serial symptom" -- --port COM3 --yes
```

The issue body excludes raw transcripts, COM ports, secrets, MAC addresses, and
local paths. If `gh` is unavailable or unauthenticated, the redacted body remains
under ignored `tools\.local\dev-install\` without masking the installer exit
status.
