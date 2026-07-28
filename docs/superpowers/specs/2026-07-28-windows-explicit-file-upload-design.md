# Windows Explicit-File Upload Design

**Date:** 2026-07-28
**Issue:** #35
**Status:** Approved for specification review

## Goal

Allow `validate.cmd` and the other Windows upload workflows to deploy the
staged MicroPython application without relying on `mpremote`'s failing
multi-source destination-directory check.

## Observed Failure

Issue #35 was created after the uploader had changed its remote-root
destination from `:/` to `:/.`. The physical validation run still stopped
before cleanup and probes with:

```text
mpremote: cp: destination does not exist
```

The current uploader passes every staged root child to one recursive
`mpremote fs cp` command. `mpremote` therefore treats the operation as a
multi-source copy and requires the destination to exist and report itself as a
directory before it reads any source.

Local analysis against `mpremote` 1.28.0 confirmed the relevant behavior:

- A copy with `multiple=True` rejects a destination that does not pass its
  existence check.
- The same copy with `multiple=False` writes directly to an explicit remote
  file path without requiring the destination file to exist.

The retired Unix installer avoided this failure branch by creating required
directories and copying every application file to an explicit remote path.
Its repeated process connections are not carried forward.

## Scope

Replace the shared Windows uploader's multi-source recursive copy with one
`mpremote` process that chains:

1. The existing optional validation or post-flash reset and wait.
2. One idempotent remote-directory preparation command.
3. One explicit, non-recursive copy command per staged manifest file.

Keep all other behavior unchanged:

- The source is still staged under an ignored temporary directory.
- Host caches, bytecode, and `.DS_Store` remain excluded.
- Application files still land at `/boot.py`, `/main.py`, and `/lib/...`.
- One `mpremote` process and transport connection perform the upload.
- A nonzero upload result still stops cleanup and validation probes.
- Successful uploads still run the existing guarded cleanup.
- Validation uploads still skip the post-cleanup reset.
- Ordinary installation, developer capture, validation, and post-flash upload
  still share the same command builder.
- Upload diagnostics remain bounded and redacted.

This change does not add dependencies or alter firmware flashing, COM-port
selection, GitHub reporting, local-only network policy, credentials, device
pin control, probe behavior, or operator observations.

## Architecture

### Staging contract

`stage_application_source(destination)` will continue to copy the filtered
contents of `src/` into `destination`. Its result will become the ordered file
manifest rather than a list of root children because the upload unit is now an
individual file.

Every manifest entry is a POSIX-style path relative to the staging root, for
example:

```text
boot.py
lib/pins.py
main.py
```

### Directory preparation

A dedicated helper will derive the unique parent directories from the
manifest, order them from shallowest to deepest, and generate device-side
Python that creates missing directories.

For an existing path, the code will confirm that it is a directory. An
existing non-directory at a required directory path will raise instead of
being overwritten or silently ignored.

Directory paths are absolute and derived only from the repository manifest,
not operator input.

### Upload command

`application_upload_command` will receive the staging root and manifest. It
will construct one argument list in this logical form:

```text
mpremote connect COMx
  + reset + sleep 1.0
  + exec DIRECTORY_PREPARATION_CODE
  + fs cp LOCAL_BOOT :/boot.py
  + fs cp LOCAL_PIN_MAP :/lib/pins.py
  + fs cp LOCAL_MAIN :/main.py
```

The reset and wait are included only when the existing `preflight_reset`
request flag is true. The `+` tokens are `mpremote` command separators; they
keep all operations in one process and connection while ensuring that each
`fs cp` parser receives exactly one source and one destination.

Each destination names a complete remote file path. No command uses `-r`, a
multi-source copy, `:`, `:/`, or `:/.` as a destination directory.

The command builder will reject an empty manifest rather than returning a
connection-only command. Staging already rejects an empty application, so this
is defense at the command boundary rather than a new user-facing mode.

## Error Handling

The existing `run_streaming` call remains the upload transaction boundary.
`mpremote` stops its chained command sequence at the first failed directory or
file operation and returns nonzero. `run_install_request` will retain the
current behavior:

- Report `Application upload failed with status N`.
- Skip guarded cleanup.
- Skip physical probes.
- Preserve bounded, redacted diagnostics in validation artifacts.

No fallback destination, automatic retry, or partial-upload cleanup is added.
A rerun safely overwrites explicit application files after directory
preparation succeeds.

## Test Plan

Use red-green development in `tests/test_windows_installer.py`.

Tests will require that:

- Staging returns a filtered, ordered file manifest.
- The upload command contains exactly one `connect`.
- The optional reset and wait precede all directory and file operations.
- Directory preparation is ordered shallowest-to-deepest and rejects a
  non-directory collision.
- Every manifest file maps from its staged local path to the corresponding
  explicit `:/relative/path` destination.
- Every copy has one source, one destination, and no recursive flag.
- `+` separates every chained operation.
- The old multi-source root destinations are absent.
- The generated command remains below Windows' `CreateProcess` command-line
  limit for the current application manifest.
- Existing upload failures still stop cleanup and probes.

Update `README.md`, `tools/README.md`, and `FIRMWARE_IMPL.md` to describe the
single-session explicit-file upload strategy.

Run:

```text
python3 -m unittest tests.test_windows_installer -v
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
```

## Delivery and Hardware Gate

After host validation, commit the implementation, merge it into `main`, and
push `main`. Keep issue #35 open until a physical:

```cmd
validate.cmd --port COMx --yes
```

reports application upload status `0` and a validation batch status other than
`not-run`.
