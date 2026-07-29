# Windows Preflight Five-Second Delay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wait five seconds after a preflight hard reset before validation and
post-flash uploads reconnect to the selected COM port.

**Architecture:** Retain the existing shared
`VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS` interface and change its value from
`"1.0"` to `"5.0"`. Both preflight-reset workflows already consume that value
for the `mpremote sleep` argument and validation transcript, so no branching or
new interface is needed. Normal uploads remain unchanged.

**Tech Stack:** Python 3 standard library, `unittest`, Windows CMD wrappers,
Markdown documentation.

## Global Constraints

- Add no production dependency or command-line option.
- Apply the five-second wait to both validation and post-flash preflight
  uploads.
- Preserve normal uploads with no preflight `sleep`.
- Preserve the same-port reconnect, recursive copy to `:/.`, cleanup,
  validation no-reset behavior, diagnostics, and local-only policy.
- Do not change firmware content, flashing parameters, device selection,
  network calls, credentials, probes, or GPIO behavior.
- Keep issue #36 open until physical validation reaches the probe batch.

## File Structure

- Modify `tests/test_windows_installer.py`: require literal five-second command
  and transcript behavior and align diagnostic fixtures.
- Modify `tools/windows_installer.py`: change the shared delay value.
- Modify `README.md`: update the active workflow timing.
- Modify `tools/README.md`: update validation and post-flash timing.
- Modify `FIRMWARE_IMPL.md`: update current implementation evidence.

---

### Task 1: Change Shared Preflight Timing to Five Seconds

**Files:**

- Modify: `tests/test_windows_installer.py:443-483`
- Modify: `tests/test_windows_installer.py:890-938`
- Modify: `tests/test_windows_installer.py:1480-1505`
- Modify: `tools/windows_installer.py:50-60`

**Interfaces:**

- Consumes:
  `VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS: str`
- Produces: literal `"5.0"` as the shared `mpremote sleep` argument and
  operator-visible preflight duration.
- Preserves:
  `application_upload_command(executable: Path, port: str,
  sources: Sequence[Path], *, preflight_reset: bool = False) -> list[str]`
  and `run_install_request(request: InstallRequest, sink: OutputSink) -> int`.

- [ ] **Step 1: Write failing five-second behavior expectations**

In
`WindowsInstallerTests.test_preflight_reset_upload_failure_stops_before_cleanup`,
replace the constant-derived expected delay with the literal and strengthen
the transcript assertion:

```python
self.assertEqual(
    upload_command[:11],
    [
        str(executable),
        "connect",
        "COM7",
        "reset",
        "sleep",
        "5.0",
        "connect",
        "COM7",
        "fs",
        "cp",
        "-r",
    ],
)
self.assertIn(
    "Hard-resetting COM7 and waiting 5.0 seconds before validation upload...",
    sink.transcript,
)
```

In
`WindowsFirmwareFlashTests.test_flash_then_upload_waits_for_reboot_then_resets_before_copy`,
replace the constant-derived expected delay with literal `"5.0"`:

```python
self.assertEqual(
    commands[2][3:11],
    [
        "reset",
        "sleep",
        "5.0",
        "connect",
        "COM7",
        "fs",
        "cp",
        "-r",
    ],
)
```

Align the literal failure-diagnostic fixtures in
`test_upload_failure_diagnostics_are_redacted_and_bounded` and
`test_upload_failure_issue_includes_diagnostics_but_success_does_not` from
`1.0` to `5.0`.

- [ ] **Step 2: Run focused tests and verify the shared timing is still one second**

Run:

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_preflight_reset_upload_failure_stops_before_cleanup \
  tests.test_windows_installer.WindowsFirmwareFlashTests.test_flash_then_upload_waits_for_reboot_then_resets_before_copy \
  -v
```

Expected: both tests fail because the generated commands contain `"1.0"`
instead of `"5.0"`; the validation transcript also reports `1.0`.

- [ ] **Step 3: Change the shared production delay**

In `tools/windows_installer.py`, change:

```python
VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS = "1.0"
```

to:

```python
VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS = "5.0"
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_preflight_reset_upload_failure_stops_before_cleanup \
  tests.test_windows_installer.WindowsFirmwareFlashTests.test_flash_then_upload_waits_for_reboot_then_resets_before_copy \
  -v
```

Expected: two tests pass.

- [ ] **Step 5: Run all Windows installer tests**

Run:

```bash
python3 -m unittest tests.test_windows_installer -v
```

Expected: all 59 Windows installer tests pass with no errors or failures.

- [ ] **Step 6: Commit the timing behavior and tests**

```bash
git add tools/windows_installer.py tests/test_windows_installer.py
git commit -m "fix: wait five seconds before preflight reconnect"
```

### Task 2: Document the Five-Second Wait

**Files:**

- Modify: `README.md:47-53`
- Modify: `tools/README.md:17-20`
- Modify: `tools/README.md:65-67`
- Modify: `tools/README.md:129-132`
- Modify: `FIRMWARE_IMPL.md:74`

**Interfaces:**

- Consumes: the shared `"5.0"` timing implemented in Task 1.
- Produces: active operator documentation that consistently says five seconds.
- Preserves: historical design and implementation-plan records.

- [ ] **Step 1: Update the root workflow**

In `README.md`, replace `wait one second` with `wait five seconds` in the
validation/post-flash upload paragraph.

- [ ] **Step 2: Update the tooling workflow**

In `tools/README.md`:

- Replace `waits one second` with `waits five seconds` in the shared preflight
  description.
- Replace `one-second wait` with `five-second wait` in the post-flash
  description.
- Replace `waits one second` with `waits five seconds` in the physical
  validation description.

- [ ] **Step 3: Update current roadmap evidence**

In the `tooling/windows-device-validation` row of `FIRMWARE_IMPL.md`, replace
`a one-second wait` with `a five-second wait`.

- [ ] **Step 4: Verify active documentation no longer claims one second**

Run:

```bash
rg -n "five seconds|five-second wait" README.md tools/README.md FIRMWARE_IMPL.md
rg -n "waits? one second|one-second wait" README.md tools/README.md FIRMWARE_IMPL.md
git diff --check
```

Expected: the first search finds all three active workflow documents; the
second search returns no matches; the diff check reports no errors.

- [ ] **Step 5: Run full repository validation**

Run:

```bash
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
```

Expected: at least 203 tests pass; shell syntax, Python compilation, and diff
checks exit zero.

- [ ] **Step 6: Commit active documentation**

```bash
git add README.md tools/README.md FIRMWARE_IMPL.md
git commit -m "docs: document five-second preflight wait"
```

## Delivery After Task Commits

Inspect, push, and verify the issue branch:

```bash
git status --short --branch
git diff --check origin/main...HEAD
git log --oneline origin/main..HEAD
git push origin bcarroll/issue36-delay
git fetch origin bcarroll/issue36-delay
git rev-parse HEAD
git rev-parse origin/bcarroll/issue36-delay
```

Merge from the clean primary checkout, validate the merged result, push
`main`, and verify local and remote refs:

```bash
git switch main
git merge --no-ff bcarroll/issue36-delay
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check HEAD^..HEAD
git push origin main
git fetch origin main
git rev-parse main
git rev-parse origin/main
```

Keep issue #36 open until the operator reruns:

```cmd
validate.cmd --port COMx --yes
```

Close the issue only after the physical report records application upload
status `0` and a validation batch status other than `not-run`.
