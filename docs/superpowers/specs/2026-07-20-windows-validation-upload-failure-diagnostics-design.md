# Windows Validation Upload-Failure Diagnostics Design

**Date:** 2026-07-20  
**Issue:** #30  
**Status:** Approved for specification review

## Goal

Make automatic GitHub issues from failed Windows physical-device validation runs
actionable without publishing raw transcripts, local paths, COM ports,
credentials, or other broad host output.

## Observed Gap

The validation report currently publishes only stable probe serial lines. An
application upload failure prevents every probe from running, so its automatic
GitHub issue reports an upload status of `1` but no diagnostic context. Issue
#30 demonstrates this with the filesystem-copy failure `mpremote: cp:
destination does not exist`.

## Scope

The change is limited to `validate.cmd` / `run_device_validation` GitHub issue
reports:

- Add a redacted, bounded upload-failure diagnostics section when application
  upload returns a nonzero status.
- Preserve the complete raw and redacted local artifacts under the existing
  ignored validation capture directory.
- Add focused host-side tests and update Windows validation documentation.

Normal Windows installs, developer/inference captures, probe execution,
automatic issue creation, network behavior, firmware handling, Wi-Fi, and GPIO
behavior remain unchanged.

## Design

### Diagnostic Selection and Redaction

Add a dedicated helper that accepts the validation transcript and returns a
small ordered list of report-safe upload diagnostics. It will redact text before
selection and retain only these high-signal line forms:

- `Hard-resetting ...`
- `Uploading application source ...`
- `Application upload failed with status ...`
- `mpremote: ...`
- `mpremote. ...` transport or Python-level errors
- `error: ...` emitted by the validation upload path

The helper will preserve order, discard duplicate lines, and cap the result at
12 lines. It will not include copy-command lines, capture directories, GitHub
URLs, arbitrary traceback lines, or the complete transcript. Existing
`redact_text` handling remains mandatory for every retained line.

### Report Rendering

`write_device_validation_issue_body` will render a new section titled
`Redacted Upload Failure Diagnostics` only when the application upload status
is nonzero. The section will contain the selected lines in a text code block.
If no selected line exists, the code block will state that no high-signal upload
diagnostics were captured. The existing probe results, operator observations,
and redacted device-serial sections retain their current format and order after
the new failure section.

### Error Handling

The report generator must still create a GitHub-ready body when upload setup or
copying fails. The diagnostics section is evidence only: it does not retry a
device action, change the resulting status, suppress local artifacts, or expose
the raw transcript. A successful application upload omits the section entirely.

## Test and Documentation Plan

Host-side tests will verify that the helper selects and redacts upload errors,
excludes unrelated/path-bearing lines, preserves a bounded ordered result, and
captures `mpremote:` and `mpremote.` failures. Report tests will verify that a
failed upload includes the new section before device serial and that a
successful upload omits it. Documentation will state that automatic validation
issues include bounded redacted upload diagnostics while the complete evidence
remains local.

Validation will run the focused Windows installer tests, the full repository
test suite, both required shell syntax checks, Python compilation for the
changed helper, and `git diff --check`.
