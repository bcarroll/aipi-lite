# Windows Validation Preflight Reconnect Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconnect `mpremote` to the selected COM port after a preflight hard
reset so validation and post-flash uploads use a fresh raw-REPL transport.

**Architecture:** Keep the shared recursive application copy and its single
`run_streaming` transaction. When `InstallRequest.preflight_reset` is true,
extend the command with a second `connect PORT` after `reset` and `sleep`; this
forces `mpremote` to replace its stale transport before `fs cp`. Ordinary
uploads without a preflight reset remain byte-for-byte unchanged.

**Tech Stack:** Python 3 standard library, `unittest`, Windows CMD wrappers,
`mpremote` 1.28.0 command semantics, Markdown documentation.

## Global Constraints

- Add no production dependency.
- Preserve the normal `install.cmd` upload command exactly.
- Reconnect only after a requested preflight reset and its existing
  one-second wait.
- Reconnect to the same already validated COM port; do not select or fall back
  to another device.
- Preserve the recursive root-child copy to `:/.`, guarded cleanup, validation
  no-reset behavior, bounded redaction, and local-only network policy.
- Do not change firmware source, flashing parameters, credentials, probes,
  operator observations, or GPIO behavior.
- Keep issue #36 open until physical validation reports upload status `0` and a
  validation batch status other than `not-run`.

## File Structure

- Modify `tools/windows_installer.py`: add the preflight reconnect to the
  shared upload command builder.
- Modify `tests/test_windows_installer.py`: prove ordinary uploads remain
  unchanged and preflight validation/post-flash uploads reconnect before copy.
- Modify `README.md`: document the ordinary and preflight-reset upload
  connection behavior.
- Modify `tools/README.md`: document the validation and post-flash reconnect.
- Modify `FIRMWARE_IMPL.md`: record the reconnect in implementation evidence
  and the physical follow-up gate.

---

### Task 1: Reconnect Preflight Uploads Before Copy

**Files:**

- Modify: `tests/test_windows_installer.py:400-485`
- Modify: `tests/test_windows_installer.py:1460-1500`
- Modify: `tools/windows_installer.py:778-805`

**Interfaces:**

- Consumes:
  `application_upload_command(executable: Path, port: str,
  sources: Sequence[Path], *, preflight_reset: bool = False) -> list[str]`
- Produces: the existing command list, with
  `["reset", "sleep", VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS,
  "connect", port]` before `["fs", "cp", "-r", ...]` only when
  `preflight_reset` is true.
- Preserves: `run_install_request(request: InstallRequest, sink: OutputSink)
  -> int` and its single upload `run_streaming` call.

- [ ] **Step 1: Write failing command-order regression tests**

In
`WindowsInstallerTests.test_upload_runs_copy_then_reset`, retain the current
ordinary-upload prefix assertion and add:

```python
self.assertEqual(upload_command.count("connect"), 1)
```

In
`WindowsInstallerTests.test_preflight_reset_upload_failure_stops_before_cleanup`,
replace the nine-token prefix assertion with:

```python
self.assertEqual(
    upload_command[:11],
    [
        str(executable),
        "connect",
        "COM7",
        "reset",
        "sleep",
        installer.VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS,
        "connect",
        "COM7",
        "fs",
        "cp",
        "-r",
    ],
)
self.assertEqual(upload_command.count("connect"), 2)
```

In
`WindowsFirmwareFlashTests.test_flash_then_upload_waits_for_reboot_then_resets_before_copy`,
replace the existing reset-prefix assertion with:

```python
self.assertEqual(
    commands[2][3:11],
    [
        "reset",
        "sleep",
        installer.VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS,
        "connect",
        "COM7",
        "fs",
        "cp",
        "-r",
    ],
)
self.assertEqual(commands[2].count("connect"), 2)
```

- [ ] **Step 2: Run the focused tests and verify the reconnect assertions fail**

Run:

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_upload_runs_copy_then_reset \
  tests.test_windows_installer.WindowsInstallerTests.test_preflight_reset_upload_failure_stops_before_cleanup \
  tests.test_windows_installer.WindowsFirmwareFlashTests.test_flash_then_upload_waits_for_reboot_then_resets_before_copy \
  -v
```

Expected: the ordinary-install test passes; both preflight tests fail because
the token at index 6 is currently `fs`, not the required second `connect`.

- [ ] **Step 3: Add the minimal reconnect to the command builder**

Change `application_upload_command` to:

```python
def application_upload_command(
    executable: Path,
    port: str,
    sources: Sequence[Path],
    *,
    preflight_reset: bool = False,
) -> list[str]:
    """Return one recursive copy command with an optional reset and reconnect."""
    command = [
        str(executable),
        "connect",
        port,
    ]
    if preflight_reset:
        command.extend(
            [
                "reset",
                "sleep",
                VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS,
                "connect",
                port,
            ]
        )
    command.extend(
        [
            "fs",
            "cp",
            "-r",
            *(str(source) for source in sources),
            ":/.",
        ]
    )
    return command
```

- [ ] **Step 4: Run the focused tests and verify they pass**

Run:

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_upload_runs_copy_then_reset \
  tests.test_windows_installer.WindowsInstallerTests.test_preflight_reset_upload_failure_stops_before_cleanup \
  tests.test_windows_installer.WindowsFirmwareFlashTests.test_flash_then_upload_waits_for_reboot_then_resets_before_copy \
  -v
```

Expected: three tests pass.

- [ ] **Step 5: Run all Windows installer tests**

Run:

```bash
python3 -m unittest tests.test_windows_installer -v
```

Expected: every Windows installer test passes with no errors or failures.

- [ ] **Step 6: Commit the behavior and regression coverage**

```bash
git add tools/windows_installer.py tests/test_windows_installer.py
git commit -m "fix: reconnect before preflight uploads"
```

### Task 2: Document the Fresh-Connection Boundary

**Files:**

- Modify: `README.md:42-60`
- Modify: `tools/README.md:7-15`
- Modify: `tools/README.md:37-55`
- Modify: `tools/README.md:104-125`
- Modify: `FIRMWARE_IMPL.md:74`

**Interfaces:**

- Consumes: the preflight command order implemented in Task 1.
- Produces: operator-facing documentation distinguishing normal uploads from
  validation and post-flash preflight uploads.
- Preserves: Windows-only entry points and the physical validation gate.

- [ ] **Step 1: Update the root Windows upload documentation**

After the `README.md` paragraph describing copies to `:/.`, add:

```text
A normal application upload establishes its first raw-REPL session when the
copy begins. Validation and post-flash uploads first hard-reset the device,
wait one second, and reconnect to the same validated COM port before starting
that same copy. The reconnect replaces the transport invalidated by the hard
reset; it does not select another device or add another upload process.
```

- [ ] **Step 2: Update the tooling guide**

After the opening upload paragraph in `tools/README.md`, add:

```text
Normal uploads connect once before copying. A validation or post-flash upload
that requests a preflight hard reset waits one second and reconnects to the
same validated COM port before the copy, ensuring `mpremote` enters raw REPL
through a fresh transport.
```

Change the physical-validation sequence sentence to:

```text
The command hard-resets the device, waits one second, reconnects to the same
validated COM port, uploads `src/`, then runs the display, GPIO status/button,
codec, capture, playback, local Wi-Fi/health, and offline inference probes
through one raw-REPL probe session.
```

Extend the flashing paragraph to state that the post-flash upload uses the
same reset, wait, and reconnect sequence before copying.

- [ ] **Step 3: Update the firmware implementation roadmap**

In the `tooling/windows-device-validation` evidence cell, replace
`a validation-only preflight hard reset with a one-second wait before the
no-reset physical validation run` with:

```text
a preflight hard reset with a one-second wait and same-port reconnect before
validation and post-flash uploads, including the no-reset physical validation
run
```

Keep the remaining-work cell explicit that physical
`validate.cmd --port COMx --yes` evidence is still required.

- [ ] **Step 4: Verify the documented reconnect contract**

Run:

```bash
rg -n "reconnect|same validated COM port|preflight hard reset" \
  README.md tools/README.md FIRMWARE_IMPL.md
git diff --check
```

Expected: each active workflow document names the reconnect; no whitespace
errors are reported.

- [ ] **Step 5: Run the full repository validation**

Run:

```bash
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
```

Expected: 203 or more tests pass; shell syntax, Python compilation, and diff
checks exit zero.

- [ ] **Step 6: Commit the documentation**

```bash
git add README.md tools/README.md FIRMWARE_IMPL.md
git commit -m "docs: explain preflight upload reconnect"
```

## Delivery After Task Commits

Inspect the complete branch:

```bash
git status --short --branch
git diff --check origin/main...HEAD
git log --oneline origin/main..HEAD
```

Push and verify the issue branch:

```bash
git push origin bcarroll/issue36
git fetch origin bcarroll/issue36
git rev-parse HEAD
git rev-parse origin/bcarroll/issue36
```

Merge from the clean primary checkout, push `main`, and verify both local and
remote `main` identify the merge result:

```bash
git switch main
git merge --no-ff bcarroll/issue36
git push origin main
git fetch origin main
git rev-parse main
git rev-parse origin/main
```

Do not close issue #36 after host-only validation. Ask the operator to rerun:

```cmd
validate.cmd --port COMx --yes
```

Close issue #36 only after the resulting physical report records application
upload status `0` and a validation batch status other than `not-run`.
