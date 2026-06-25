# AIPI-Lite Local-Only MVP Guide

This guide packages the first local-only MVP workflow for the XORIGIN AI
PI-Lite / AIPI Lite model `XY006PL01`. It assumes the firmware remains on an
operator-controlled local network and does not use cloud, telemetry, OTA, or
vendor service endpoints.

## Stock Backup Option

Normal MVP installs assume the device already runs compatible
ESP32_GENERIC_S3 MicroPython firmware and skip the stock backup. If stock
recovery matters before replacing firmware on a specific unit, run the
`--flash-micropython --backup-stock` procedure in [RECOVERY.md](RECOVERY.md).
Keep any backup under ignored local storage such as `tools/.local/backups/` and
verify the image size before relying on it for recovery. If opt-in backup
validation is blocked, record the install capture issue or local capture
artifact and continue with `--flash-micropython` but without `--backup-stock`
only when stock recovery is not required.

Do not commit stock firmware dumps, local Wi-Fi configuration, service URLs,
device labels, validation transcripts, credentials, or GitHub tokens.

## MVP Install Guide

1. Confirm ESP32_GENERIC_S3 MicroPython is already flashed and running on the
   device.
2. Run the installer from the repository root to upload the application:

   ```bash
   ./install.sh --port /dev/cu.usbmodem31101
   ```

3. Confirm the install summary says MicroPython firmware is assumed present on
   the device.
4. Allow the installer to upload the current `src/` application tree.
5. Capture serial output after reset and confirm the safe boot lines appear.

Use `dev_install.sh` for hardware validation captures when a GitHub issue body
is needed for later analysis:

```bash
./dev_install.sh \
  --device-label bench-a \
  --hardware-note "MVP install validation" \
  -- --port /dev/cu.usbmodem31101
```

## MVP Configuration Guide

Create an ignored `src/local_wifi_config.py` on the device before Wi-Fi,
health-check, or push-to-talk validation:

```python
WIFI_SSID = "your-local-ssid"
WIFI_PASSWORD = "your-wpa2-password"
LOCAL_SERVICE_URL = "http://192.168.1.10:8080"
APPROVED_LOCAL_HOSTS = ("assistant.lan",)
```

`LOCAL_SERVICE_URL` must resolve to a local endpoint accepted by
`src/local_endpoint.py`: RFC1918 IPv4, loopback or link-local IPv4 for bench
testing, `.local` mDNS, or an explicitly approved operator-controlled hostname.
Public IPv4 addresses, public DNS names, embedded credentials, query strings,
fragments, and unsupported schemes are rejected before any request is issued.

Run the development mock service on the host:

```bash
python3 -m service.mock_service --host 192.168.1.10 --port 8080
```

Bind only to an operator-controlled LAN interface. The mock service has no
production authentication or hardening.

## MVP Validation Checklist

- Stock firmware backup is skipped by default, or the opt-in backup exists, has
  the expected size, and remains ignored.
- Installer bootloader verification passes before any explicit flash-sensitive
  operation.
- `python3 -m unittest discover -s tests -v` passes on the host.
- `bash -n install.sh`, `bash -n dev_install.sh`, and
  `bash -n tools/setup_micropython_tools.sh` pass.
- Device serial output shows safe boot and does not report GPIO10 activity.
- Display boot, Wi-Fi, ready, recording, processing, speaking, and error
  screens are legible.
- GPIO46 status LED shows the expected state colors.
- GPIO42 button emits debounced press and release events.
- Wi-Fi connects only to the configured local network.
- Local service health check succeeds against the mock service.
- Push-to-talk exchange reaches ready, records bounded audio, uploads to the
  local service, displays response text, downloads local WAV audio, and plays it.
- Repeated sessions recover from transient Wi-Fi or local service failures.
- Speaker output leaves GPIO9 disabled and DAC muted after playback or failure.
- GPIO21 charge pulse is recorded only as an observation.
- GPIO10 board-power control remains blocked unless a future hardware-validated
  safety flag explicitly allows it.

## No-cloud network verification

During MVP validation, inspect serial logs, mock service logs, and local router
or firewall logs. The firmware should contact only the configured local service
endpoint. Treat any public DNS, public IPv4, telemetry, OTA, vendor endpoint, or
cloud service attempt as a failed validation.

## Validation Report Template

```text
AIPI-Lite MVP Validation Report

Date:
Operator:
Hardware model: XY006PL01
Hardware revision / labels:
MicroPython image:
Firmware version:
Service contract:
Mock service host and port:
Local network:
Installer capture issue/link:

Host checks:
- unittest:
- install.sh syntax:
- dev_install.sh syntax:
- tools/setup_micropython_tools.sh syntax:
- git diff --check:

Device checks:
- Stock backup verified:
- Safe boot serial lines:
- Display states:
- Status LED states:
- Button press/release:
- Wi-Fi local health:
- Push-to-talk exchange:
- Response playback:
- Retry/reconnect behavior:
- GPIO21 charge pulse observation:
- GPIO10 board-power control unchanged:
- No-cloud network verification:

Failures, logs, and follow-up actions:
```

Record pass/fail status with exact serial output, timestamps, and the Git commit
under test. Keep local captures under ignored tooling paths.
