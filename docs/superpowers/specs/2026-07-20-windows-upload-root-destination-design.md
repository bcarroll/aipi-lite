# Windows Upload Root-Destination Design

**Date:** 2026-07-20
**Issue:** #31
**Status:** Approved for specification review

## Goal

Correct the Windows application uploader so `mpremote fs cp` targets the device
filesystem root with a valid remote-path destination and physical validation can
continue past application upload.

## Observed Failure

The Windows validation run reaches the filesystem copy after its approved
preflight reset, but `mpremote` rejects its current `:` destination with
`mpremote: cp: destination does not exist`. The uploader stages the children of
`src/` specifically so they land at device root, but it currently appends `:`
instead of an explicit root path.

## Scope

Change only the Windows upload command produced by
`application_upload_command`:

- Replace its remote destination argument `:` with `:/`.
- Keep the staged source children, recursive copy, one `mpremote` invocation,
  validation-only hard reset, one-second wait, guarded cleanup, and no-reset
  validation behavior unchanged.
- Update host-side assertions and Windows upload documentation.

This change does not alter Unix installation, firmware flashing, reset policy,
Wi-Fi, local services, GPIO behavior, automatic issue reporting, or the
existing redacted diagnostics section.

## Design

`application_upload_command` will continue to construct one command in this
shape for an ordinary install:

```text
mpremote connect COMx fs cp -r SOURCE_CHILDREN :/
```

For physical validation, the existing preflight remains in the same command:

```text
mpremote connect COMx reset sleep 1.0 fs cp -r SOURCE_CHILDREN :/
```

The explicit `:/` target denotes the remote filesystem root while preserving
the staged root-child layout: `/boot.py`, `/main.py`, and `/lib` rather than a
nested `/src` directory. A nonzero copy result still stops cleanup and probes,
so no additional recovery action or retry is introduced.

## Test and Documentation Plan

Update Windows installer tests to require `:/` as the ordinary and preflight
upload destination while retaining existing assertions for source-child layout,
failure short-circuiting, cleanup, and no-reset behavior. Update the Windows
workflow documentation and implementation roadmap to state that the uploader
uses the explicit remote-root destination. Run the focused Windows installer
suite, full repository suite, required shell syntax checks, Python compilation,
and `git diff --check`.
