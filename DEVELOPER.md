# Developer Device Test Runbook

Use this workflow to test the current firmware application against a connected
AIPI-Lite and automatically report redacted findings to a GitHub issue.

## Prerequisites

- Put the device into ESP32-S3 bootloader mode and connect it over USB-C.
- Install and authenticate the GitHub CLI:

```bash
gh auth status
```

- Choose the issue that should receive the report:

```bash
export AIPI_GITHUB_ISSUE="OWNER/REPO#123"
export AIPI_PORT="/dev/cu.usbmodem31101"
export AIPI_DEVICE_LABEL="bench-a"
```

## Install, Trace, And Report

Run the normal installer through the developer wrapper. The wrapper preserves
the installer exit status, captures the visible install output, enables detailed
installer tracing, redacts common secrets, and posts the issue body to GitHub.

```bash
./dev_install.sh \
  --issue "${AIPI_GITHUB_ISSUE}" \
  --device-label "${AIPI_DEVICE_LABEL}" \
  --hardware-note "connected device install and trace run" \
  --trace \
  -- --port "${AIPI_PORT}"
```

The run writes local artifacts under ignored paths:

```text
tools/.local/dev-install/
tools/.local/debug/
```

Do not commit or manually attach stock firmware backups, firmware dumps,
credentials, `.conf`, Wi-Fi settings, or device tokens.

## Optional Post-Install Probes

After install, use `mpremote` for focused hardware checks. Record pass/fail
observations as GitHub issue comments or as `--hardware-note` values on the next
developer install capture.

```bash
tools/.local/micropython-venv/bin/mpremote connect "${AIPI_PORT}" exec "import io_probe; io_probe.run_probe(cycles=1)"
tools/.local/micropython-venv/bin/mpremote connect "${AIPI_PORT}" exec "import display_probe; display_probe.run_probe(cycles=1)"
tools/.local/micropython-venv/bin/mpremote connect "${AIPI_PORT}" exec "import audio_probe; audio_probe.run_probe()"
tools/.local/micropython-venv/bin/mpremote connect "${AIPI_PORT}" exec "import capture_probe; capture_probe.run_probe()"
tools/.local/micropython-venv/bin/mpremote connect "${AIPI_PORT}" exec "import playback_probe; playback_probe.run_probe()"
```

For Wi-Fi and local service validation, create ignored `src/local_wifi_config.py`
on the device first, then run:

```bash
tools/.local/micropython-venv/bin/mpremote connect "${AIPI_PORT}" exec "import wifi_probe; wifi_probe.run_probe()"
```

To post a short probe report automatically, capture the relevant command output
to an ignored local file and comment on the issue:

```bash
export AIPI_REPORT_DIR="tools/.local/dev-install/probes-$(date -u +%Y%m%d-%H%M%S)"
mkdir -p "${AIPI_REPORT_DIR}"

{
  printf '# AIPI-Lite post-install probe report\n\n'
  printf 'device_label=%s\n' "${AIPI_DEVICE_LABEL}"
  printf 'port=%s\n' "${AIPI_PORT}"
  printf 'created_utc=%s\n\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  tools/.local/micropython-venv/bin/mpremote connect "${AIPI_PORT}" exec "import io_probe; io_probe.run_probe(cycles=1)"
  tools/.local/micropython-venv/bin/mpremote connect "${AIPI_PORT}" exec "import display_probe; display_probe.run_probe(cycles=1)"
} 2>&1 | sed -E \
  -e 's/([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Tt][Oo][Kk][Ee][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Kk][Ee][Yy]|[Ss][Ss][Ii][Dd])=([^[:space:]]+)/\1=<redacted>/g' \
  -e 's/([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}/<redacted-mac>/g' \
  | tee "${AIPI_REPORT_DIR}/probe-report.md"

gh issue comment "${AIPI_GITHUB_ISSUE##*#}" \
  --repo "${AIPI_GITHUB_ISSUE%#*}" \
  --body-file "${AIPI_REPORT_DIR}/probe-report.md"
```

If a run fails, rerun the traced capture with a short non-secret note:

```bash
./dev_install.sh \
  --issue "${AIPI_GITHUB_ISSUE}" \
  --device-label "${AIPI_DEVICE_LABEL}" \
  --hardware-note "failure observed: describe visible LED/display/serial symptom" \
  --trace \
  -- --port "${AIPI_PORT}"
```
