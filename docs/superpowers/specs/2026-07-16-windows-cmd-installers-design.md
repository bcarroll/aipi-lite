# Windows CMD Installer Design

## Goal

Provide Windows-native `install.cmd` and `dev_install.cmd` entry points for
the normal AIPI-Lite application upload and developer capture workflows. The
scripts target an AIPI-Lite that already runs ESP32_GENERIC_S3 MicroPython and
is connected as a Windows `COM` port.

## Scope

The initial Windows implementation supports application-first uploads only. It
does not implement firmware flashing, stock backup, restore, installer
self-update, GitHub issue posting, or installer trace artifacts. The existing
Unix scripts retain their current full feature set without modification.

## Architecture

The two `.cmd` files are native Command Prompt entry points. Each locates a
supported Python interpreter using the Windows `py` launcher or `python` on
`PATH`, then delegates to one tracked standard-library Python helper. No new
third-party application dependency is introduced; the helper installs
`mpremote` into the ignored `tools\\.local\\micropython-venv` virtual
environment when necessary.

The Python helper has a small command interface selected by the CMD wrapper:

- `install.cmd` runs the application upload command.
- `dev_install.cmd` runs the developer-capture command.

Keeping parsing, subprocess handling, redaction, and filesystem operations in
Python avoids the quoting and error-propagation limitations of batch files,
while the operator-facing commands remain native `.cmd` files.

## Installer Behavior

`install.cmd` accepts `--port COMx`, `--no-reset`, `--yes`, `--list-ports`, and
`--help`. It requires an explicit port for upload, creates or reuses the
repository-local virtual environment, installs `mpremote`, then uses
`mpremote connect COMx fs cp -r src/ :` to upload the MicroPython application.
It resets the device afterward unless `--no-reset` is passed. `--yes` accepts
the prerequisite-install prompt without interaction. `--list-ports` reports
Windows serial candidates without changing a device.

All host-side generated artifacts remain under ignored `tools/.local/`; the
scripts do not write credentials, Wi-Fi settings, or device tokens to tracked
files.

## Developer Capture Behavior

`dev_install.cmd` accepts `--capture-dir`, `--device-label`, repeatable
`--hardware-note`, `--prepare-only`, and `--help`, followed by installer
arguments after `--`. It runs the same upload path as `install.cmd`, sends its
output to the console, and stores a raw transcript, a redacted transcript, and
non-secret run metadata under
`tools/.local/dev-install/install-TIMESTAMP-PID/` by default. `--prepare-only`
creates the local capture artifacts but does not perform the device upload.

Redaction removes common credential, token, password, SSID, MAC-address, and
serial-port values from shareable capture output. The wrapper returns the
installer result so a capture failure cannot make a failed install appear to
succeed.

## Error Handling

The helper stops with a clear nonzero result when Python is unavailable, a
virtual environment cannot be created, `mpremote` cannot be installed, the
specified `COM` port is missing, the source tree is unavailable, or an
`mpremote` command fails. It does not attempt firmware-changing recovery
operations.

## Testing and Documentation

Host-side Python unit tests will cover command parsing, interpreter selection
behavior, virtual-environment command construction, `COM` port validation,
upload/reset sequencing, developer artifact creation, redaction, and exit-code
propagation. `README.md` will provide Windows examples and state the initial
feature boundary. The existing Unix installer tests remain unchanged.
