# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Local-only replacement MicroPython firmware for the XORIGIN AI PI-Lite / AIPI Lite
(model `XY006PL01`, ESP32-S3, 128x128 TFT, ES8311 codec, WS2812 status LED, single
side button). The device runs a push-to-talk assistant that talks *only* to a
local-network service — there is deliberately no cloud, telemetry, OTA, or
public-network behavior. The other half of the repo is host-side installer/probe
tooling that uploads `src/` to a device already flashed with ESP32_GENERIC_S3
MicroPython.

## Commands

```bash
# Host-side regression tests (the primary check — no device needed)
python3 -m unittest discover -s tests -v
# Single test module / case
python3 -m unittest tests.test_main_startup -v
python3 -m unittest tests.test_main_startup.ClassName.test_method

# Pre-commit checks expected by AGENTS.md
bash -n install.sh
bash -n tools/setup_micropython_tools.sh
git diff --check

# Upload the app to a MicroPython-flashed device (Unix)
./install.sh --port /dev/cu.usbmodem31101
./install.sh --list-ports          # probe serial ports, read-only

# Run the stdlib-only local mock service for development
python3 -m service.mock_service --host 127.0.0.1 --port 8080
```

Windows uses `install.cmd` / `dev_install.cmd` / `validate.cmd` (backed by
`tools/windows_installer.py`); Windows does not support firmware flash/backup/restore.
Explicit firmware flashing, stock backup, and restore are Unix-only via
`install.sh --flash-micropython` (see RECOVERY.md).

## Architecture

**Two trees, two languages, one boundary.** `src/` is MicroPython that runs on the
device; everything else (`tools/`, `service/`, `tests/`, `install.sh`) is CPython/bash
that runs on the host. They meet only at the serial upload — the host copies `src/`
children to the device root `:/`, producing `/boot.py`, `/main.py`, `/lib`.

**Device import model.** `src/lib/` is uploaded to device `/lib`, so device code imports
by *bare module name* (`import pins`, `from display import ...`), never `from src.lib...`.
Do NOT make `src` a Python package. Host tests reproduce this by inserting
`src/` and `src/lib/` onto `sys.path` and stubbing MicroPython-only modules
(`machine`, `network`, etc.) via `sys.modules` before import — follow the existing
pattern in `tests/test_main_startup.py` / `tests/test_es8311_codec.py` when adding tests.

**Startup flow** (`src/boot.py` → `src/main.py`): boot does GC and prints safe status
without constructing GPIO. `main.py` disables the GPIO9 speaker gate, renders the boot
screen, inits LED/display, then hands off to the push-to-talk controller. It is written
defensively — every hardware init is wrapped so a missing/failed component degrades to a
printed skip rather than a crash. `main()` takes factory/`print_func` injection points
purely so host tests can drive it without hardware.

**Push-to-talk state machine** (`src/lib/push_to_talk.py`, `assistant_state.py`,
`reliability.py`): one assistant state machine drives UI. Component-aware states
distinguish Wi-Fi vs. local-service failure. Key behaviors that tests enforce: a short
press retries exactly *one* offline component (Wi-Fi before service); a 2s long-press
bypasses OFFLINE into LIMITED without reconnecting. The LCD uses text + icons (not color
alone) and never displays SSID/password/service URL.

**Local-only network policy** (`src/lib/service_client.py`, `local_endpoint.py`,
`wifi_probe.py`): the service client validates the configured URL is local-only
(RFC1918, loopback/link-local, `.local`, or explicitly approved hosts) *before* any
connection. Public endpoints are rejected and never contacted. Endpoints:
`/health`, `/session`, `/audio`, `/response/{session_id}`. This policy is load-bearing —
preserve it.

**Pin map** (`src/lib/pins.py`) is the single source of documented ESP32-S3 pin
assignments, cross-checked against `SPEC.md`. `BOARD_POWER_CONTROL` (GPIO10) is in
`DO_NOT_TOUCH_DURING_BOOT` — do not drive it until hardware testing confirms it is safe.

**Opt-in probes** (`src/lib/*_probe.py`: `io_probe`, `display_probe`, `audio_probe`,
`capture_probe`, `playback_probe`, `wifi_probe`, `inference_probe`): each is a
self-contained hardware check run manually via `mpremote ... exec "import X; X.run_probe()"`.
They are kept out of the normal boot path so a bad probe never bricks startup. The Windows
`validate.cmd` and `dev_install.cmd --inference-probe` chain these into redacted,
GitHub-ready bench reports.

**Installer internals** (`install.sh`, `tools/device_application.py`,
`tools/windows_installer.py`): `device_application.py` holds shared upload logic — the
list of `LEGACY_ROOT_MODULES` to clean up (modules that used to live at root, now under
`/lib`), guarded `/src` removal (only when contents match the app manifest), and cache
artifact filtering. Both the Unix and Windows installers share this cleanup + single
`mpremote` connection for reset. Installer answers persist to a git-ignored root `.conf`.

## Conventions and guardrails

- **Commit, push, and merge to `main` automatically** for completed, validated changes,
  so other machines can pull finished work. Only `main` should carry completed work.
- **Never commit local-only artifacts**: generated downloads, local virtualenvs, firmware
  dumps, stock backups, credentials, device tokens, `.conf`, `.conf.tmp.*`, `__pycache__`,
  `*.pyc`, and `**/local_wifi_config.py`. All such state belongs under ignored
  `tools/.local/`. Installer answers (ports, backup paths, Wi-Fi settings, secrets,
  operator answers) go in ignored `.conf`, never hard-coded in tracked files.
- **Preserve the local-only firmware policy by default.** Do not add cloud endpoints,
  telemetry, OTA behavior, credentials, or public-network service calls unless the user
  explicitly asks and documentation is updated.
- **Keep device imports root-relative** (`from lib...`, `import pins`); do not turn `src`
  into a Python package.
- **Do not drive unverified hardware controls**, especially GPIO10 board power, until
  `SPEC.md` and hardware testing confirm safe behavior.
- Include tests for new Python code and update docs where appropriate.
- **Before committing** firmware, installer, or tooling changes, run the relevant checks:
  `python3 -m unittest discover -s tests -v`, `bash -n install.sh`,
  `bash -n tools/setup_micropython_tools.sh`, and `git diff --check`.

## Docs as source of truth

Update these alongside behavior changes; they are authoritative for their domains:
`SPEC.md` (hardware/pinout), `FIRMWARE_PLAN.md` (architecture), `FIRMWARE_IMPL.md`
(roadmap/status), `RECOVERY.md` (backup/restore), `README.md` (user workflow),
`service/README.md` (service payloads), `INFERENCE_FEASIBILITY.md` (inference probe scope).
