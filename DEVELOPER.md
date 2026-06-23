# Developer Device Test Runbook

Use this workflow to test the current firmware application against a connected
AIPI-Lite and automatically report redacted findings to a GitHub issue.

## Prerequisites

- Put the device into ESP32-S3 bootloader mode and connect it over USB-C.
- Install and authenticate GitHub CLI. The `gh` command comes from GitHub CLI,
  GitHub's official command-line tool. On macOS with Homebrew:

```bash
brew install gh
gh auth login
gh auth status
```

  On WSL with Ubuntu or Debian, use GitHub CLI's official apt repository:

```bash
(type -p wget >/dev/null || (sudo apt update && sudo apt install wget -y)) \
  && sudo mkdir -p -m 755 /etc/apt/keyrings \
  && out="$(mktemp)" && wget -nv -O"${out}" https://cli.github.com/packages/githubcli-archive-keyring.gpg \
  && cat "${out}" | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null \
  && sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
  && sudo mkdir -p -m 755 /etc/apt/sources.list.d \
  && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
    | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null \
  && sudo apt update \
  && sudo apt install gh -y
gh auth login
gh auth status
```

  For Windows, Linux, or non-Homebrew macOS installs, use the official
  installation instructions at <https://cli.github.com/>.

- Choose the repository that should receive new install capture issues:

```bash
export AIPI_GITHUB_REPO="OWNER/REPO"
export AIPI_PORT="/dev/cu.usbmodem31101"
export AIPI_DEVICE_LABEL="bench-a"
```

  To comment on an existing issue instead of creating a new one, set
  `AIPI_GITHUB_ISSUE="OWNER/REPO#123"` and use `--issue` in place of `--gh`.

## Install, Trace, And Report

Run the normal installer through the developer wrapper. The wrapper preserves
the installer exit status, captures the visible install output, enables detailed
installer tracing, redacts common secrets, and posts the issue body to GitHub.

```bash
./dev_install.sh \
  --gh "${AIPI_GITHUB_REPO}" \
  --gh-title "AIPI-Lite ${AIPI_DEVICE_LABEL} install capture" \
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

The wrapper prints the created issue URL and stores it in the local capture
directory as `github-created-issue.txt`. For follow-up probe comments, set
`AIPI_GITHUB_ISSUE` to the created issue target, such as `OWNER/REPO#123`.

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
  --gh "${AIPI_GITHUB_REPO}" \
  --gh-title "AIPI-Lite ${AIPI_DEVICE_LABEL} failed install capture" \
  --device-label "${AIPI_DEVICE_LABEL}" \
  --hardware-note "failure observed: describe visible LED/display/serial symptom" \
  --trace \
  -- --port "${AIPI_PORT}"
```
