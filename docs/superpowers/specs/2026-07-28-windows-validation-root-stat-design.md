# Windows Validation Root-Stat Upload Design

**Date:** 2026-07-28
**Issue:** #32
**Status:** Approved for specification review

## Goal

Allow `validate.cmd` to finish its application upload and continue into the
physical probe batch by giving `mpremote fs cp` a device-root destination that
can be stat-ed without becoming an empty remote path.

## Observed Failure

`validate.cmd` delegates to the `validate` command in
`tools/windows_installer.py`. That path hard-resets the selected device, waits
one second, and calls the shared application uploader with post-upload reset
disabled. The upload currently ends with this multi-source copy destination:

```text
:/
```

The validation report records:

```text
mpremote: cp: destination does not exist
```

No cleanup or physical probe runs after that nonzero upload result.

In `mpremote` 1.28.0, the copy implementation removes trailing path separators
before checking a remote destination. Both `:` and `:/` therefore become an
empty remote path for the existence check. The connected device does not report
that empty path as an existing directory, so `mpremote` rejects a multi-source
copy before reading any staged source.

## Scope

Change the shared Windows upload command to use `:/.` as its remote
device-root destination.

Keep all other behavior unchanged:

- `validate.cmd` still performs its pre-upload hard reset and one-second wait.
- The uploader still stages a cache-free copy of the children of `src/`.
- One `mpremote` process and connection still perform the recursive copy.
- Successful uploads still run guarded cleanup for recognized misplaced and
  legacy application files.
- Validation uploads still skip the post-cleanup reset before running probes.
- Ordinary `install.cmd`, developer capture, and post-flash uploads continue
  using the same shared uploader.
- Upload failures still stop cleanup and probes and retain redacted
  diagnostics.

This change does not alter firmware flashing, dependencies, network policy,
GitHub reporting, device pin control, probe behavior, operator observations, or
local-only data handling.

## Design

`application_upload_command` will continue to build one multi-source recursive
copy command. Its destination changes from `:/` to `:/.`.

Ordinary application upload:

```text
mpremote connect COMx fs cp -r SOURCE_CHILDREN :/.
```

Physical validation upload:

```text
mpremote connect COMx reset sleep 1.0 fs cp -r SOURCE_CHILDREN :/.
```

The trailing `.` prevents `mpremote` from reducing the destination to an empty
path. Its existence check therefore evaluates the absolute root-equivalent
path `/.`, while recursive copies still place the staged children at
`/boot.py`, `/main.py`, and `/lib`.

## Error Handling

Existing status handling remains authoritative. A nonzero copy status is
reported as an application-upload failure, cleanup and probes remain skipped,
and the validation artifacts retain redacted upload diagnostics. No retry or
fallback destination is added because that could conceal a partial upload or
change which remote directory receives application files.

## Test and Documentation Plan

Use a red-green test cycle in `tests/test_windows_installer.py`:

1. Change the ordinary and validation-preflight upload assertions to require
   `:/.` and confirm they fail against the current `:/` implementation.
2. Make the one-token production change in `application_upload_command`.
3. Run the focused Windows installer tests and confirm the regression passes.

Update `README.md`, `tools/README.md`, and `FIRMWARE_IMPL.md` to name `:/.` as
the explicit root-stat-safe `mpremote` destination. Then run:

```text
python3 -m unittest tests.test_windows_installer -v
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
```

After host validation, commit the fix, merge it to `main`, and push `main`.
Keep issue #32 open until a physical `validate.cmd --port COMx --yes` rerun
confirms that application upload succeeds and the validation probe batch
starts.
