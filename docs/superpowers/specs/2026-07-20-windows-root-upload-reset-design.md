# Windows Root Upload and Reset Recovery Design

## Context

GitHub issue #26 records a Windows `install.cmd` run where application upload
and legacy-module cleanup succeeded, but the final `mpremote reset` process
could not enter raw REPL. The device then remained blank because raw-REPL soft
reset does not execute `main.py`.

The same transcript exposes a separate path-layout defect. The recursive copy
reports `./src/main.py` and `./src/lib/...`, proving that the Windows installer
copies the source directory itself to device `/src`. The intended MicroPython
layout is `/boot.py`, `/main.py`, and reusable modules under `/lib`.

The Unix `install.sh` uploader already maps every source-relative file to an
explicit device-root destination and filters host cache artifacts. Its reset
failure is already nonfatal. However, it does not remove legacy root modules,
so those files can shadow `/lib` after an application update. It must also be
able to repair a recognized `/src` tree left by an earlier Windows install.

Bare imports such as `from pins import BOARD_POWER_CONTROL` remain intentional.
MicroPython includes `/lib` in its module search path, so application modules
under `/lib` are imported by module name rather than as `lib.*` packages.

## Goals

- Copy the contents of the repository's `src/` tree to the device root.
- Exclude host-only `__pycache__`, `*.pyc`, and `.DS_Store` artifacts.
- Guardedly remove `/src` when it is the tree created by the defective Windows
  installer.
- Preserve `/src` and warn when it contains unknown files.
- Avoid a second raw-REPL connection between cleanup and reset.
- Treat upload and cleanup failures as fatal.
- Treat an unconfirmed reset after successful cleanup as a successful install
  that requires a manual power cycle.
- Preserve `--no-reset` behavior.
- Apply the same guarded cleanup and cleanup/reset lifecycle through both the
  Windows and Unix installers.

## Non-Goals

- Do not change firmware import statements to `lib.*` imports.
- Do not erase unrecognized device files or directories.
- Do not change the Unix upload layout, firmware image, Wi-Fi configuration,
  or application runtime behavior.
- Do not add production dependencies.

## Design

### Clean application staging

The Windows helper will copy `src/` into a temporary host staging directory
while filtering `__pycache__`, `*.pyc`, and `.DS_Store`. It will pass each
immediate child of that clean staging root as a source to one recursive
`mpremote fs cp` operation whose destination is device root. Using multiple
children as sources produces `/boot.py`, `/main.py`, `/README.md`, and `/lib`
instead of `/src/...`.

The temporary tree exists only for the duration of the upload command and is
removed automatically. Ignored `local_wifi_config.py`, when present, remains
part of the application upload without exposing its contents.

### Guarded mistaken-tree cleanup

A shared host helper will derive the expected relative file manifest from an
application source tree and generate device-side cleanup code. The Windows
installer will use the clean staging manifest; the Unix installer will use the
same filtered source manifest that its uploader uses. Device-side cleanup will
inspect `/src` before deletion. A tree is recognized as the defective installer
output only when:

- its non-cache files are all present in the staged application manifest;
- it contains the AIPI-Lite startup signatures `main.py`, `boot.py`, and
  `lib/pins.py`; and
- any additional files are confined to `__pycache__` directories or use the
  `.pyc` suffix.

When recognized, the cleanup removes `/src` recursively and reports that the
misplaced application tree was removed. When any unknown file is found, it
preserves the complete `/src` tree and prints a warning. This check happens
before deletion so a partial cleanup cannot destroy an unrecognized tree.

The targeted cleanup of root-level modules moved to `/lib` runs through both
installers and continues to preserve `/boot.py`, `/main.py`, and
`/local_wifi_config.py`.

### Cleanup and reset lifecycle

For a normal Windows or Unix install, legacy cleanup, guarded `/src` cleanup,
and reset will be commands in one `mpremote` process. Cleanup prints a unique
completion marker before the reset command begins.

- A nonzero command result without the marker is a fatal cleanup failure.
- A zero result with the marker is a successful upload, cleanup, and reset.
- A nonzero result after the marker is a successful upload and cleanup with an
  unconfirmed reset. The installer returns success and prominently instructs
  the operator to unplug and reconnect USB-C or otherwise power-cycle the
  device.

Keeping reset in the cleanup connection eliminates the raw-REPL reconnect that
failed in issue #26. The warning fallback handles USB timing or disconnect
conditions where `mpremote` still cannot confirm reset.

With Windows `--no-reset` or Unix `AIPI_RESET_AFTER_UPLOAD=no`, the installer
runs upload and cleanup without appending the reset command. Cleanup failure
remains fatal, and successful cleanup reports that reset was intentionally
skipped.

## Error Handling

- Missing source directory, unavailable COM port, tooling setup failure, upload
  failure, or cleanup failure returns nonzero.
- Unknown content under device `/src` is preserved and reported, but does not
  fail installation because the corrected root application is already present.
- Reset-only failure returns zero with an explicit manual-power-cycle warning.
- Output never includes Wi-Fi credentials or file contents.

## Validation

Host-side tests will verify:

- staged upload sources map to device root rather than `/src`;
- host cache artifacts are excluded while application and ignored local
  configuration files remain eligible;
- known mistaken `/src` content is removable and unknown content is preserved;
- cleanup and reset share one `mpremote` invocation;
- cleanup failure remains fatal;
- reset-only failure returns success and prints the manual-power-cycle warning;
- `--no-reset` runs cleanup without reset; and
- all generated device-side Python snippets compile.

Unix installer tests will additionally verify that its existing explicit
device-root mapping and cache filters remain intact, that it invokes the shared
cleanup generator, and that cleanup/reset marker handling matches Windows.

Repository validation will run the focused Windows installer tests, the full
Python test suite, required shell syntax checks, and `git diff --check` before
the implementation commit.

## Documentation

`README.md`, `tools/README.md`, and `FIRMWARE_IMPL.md` will describe the device
root layout, shared guarded `/src` and legacy-module cleanup, cache filtering,
combined reset lifecycle, and manual power-cycle fallback on Windows and Unix.
