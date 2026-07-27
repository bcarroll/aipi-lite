# Windows-Only Installer Cleanup Design

Date: 2026-07-27
Status: Approved for implementation

## Goal

Retire the Unix installer entry points because future operator and developer
workflows will use the native Windows command scripts exclusively.

## Scope

Delete `install.sh` and `dev_install.sh`. Delete their dedicated host-side test
modules, `tests/test_install_script.py` and `tests/test_dev_install_capture.py`,
because those tests exercise retired entry points rather than reusable
firmware behavior.

Keep the supported Windows entry points and implementation:

- `install.cmd` for application-first installation
- `dev_install.cmd` for captured developer and inference runs
- `validate.cmd` for physical-device validation
- `tools/windows_installer.py` and its tests for the shared Windows behavior

Keep shared tooling that remains useful to repository maintenance or the
Windows implementation. Do not change MicroPython application code, pin
behavior, network policy, or device-side runtime behavior.

## Documentation

Update active operator, developer, recovery, architecture, roadmap, and
repository-instruction documents so that commands and supported workflows point
to the Windows scripts. Active documents must not instruct users to run either
deleted shell script.

The Windows installer currently supports application upload and validation but
does not provide the Unix installer's automated firmware backup, MicroPython
flashing, or stock-firmware restore features. Documentation will state that
these automated recovery operations are no longer available through repository
scripts; this cleanup will not silently imply that the Windows scripts implement
them.

Historical design specifications will remain unchanged where they describe work
that was accurate when implemented. Roadmap and status documents may retain
historical references when clearly labeled as retired history, but their current
status and next-step guidance will describe the Windows-only supported surface.

## Behavior and Failure Handling

Removing the Unix scripts must not alter Windows argument parsing, COM-port
selection, upload destinations, evidence redaction, offline-first behavior, or
validation probes. Windows failures will continue to use the existing Python
helper's error handling and command exit statuses.

References that are operational rather than historical will be checked after
editing. Any remaining `install.sh` or `dev_install.sh` occurrence must be
deliberately historical or part of this design record.

## Validation

Run the full Python unit test suite after removing the obsolete shell-script
tests. Run syntax validation for the remaining tracked shell setup tool and
`git diff --check`. Search active documentation for stale Unix installer
instructions and review every remaining match.

No new production dependencies are required. No generated downloads, local
configuration, credentials, captures, or device artifacts will be committed.
