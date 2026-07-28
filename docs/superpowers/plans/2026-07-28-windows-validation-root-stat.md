# Windows Validation Root-Stat Upload Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared Windows uploader use the root-stat-safe `mpremote`
destination `:/.` so `validate.cmd` can upload the application and continue
into its physical probe batch.

**Architecture:** Preserve the existing staged, multi-source recursive upload
and change only its remote destination token from `:/` to `:/.`. The same
command builder remains shared by ordinary installation, developer capture,
post-flash upload, and physical validation; existing reset, cleanup, error, and
redaction paths remain unchanged.

**Tech Stack:** Python 3 standard library, `unittest`, Windows CMD entry points,
`mpremote` 1.28.0 command semantics, Markdown documentation, Git.

## Global Constraints

- Use only the Windows entry points `install.cmd`, `dev_install.cmd`, and
  `validate.cmd`; do not restore or document retired Unix installers.
- Add no production dependency.
- Preserve local-only operation: no cloud endpoint, telemetry, OTA,
  credential, or public-network behavior.
- Do not change firmware flashing, GPIO behavior, validation probes, operator
  observations, cleanup policy, reset policy, or redacted issue reporting.
- Keep device application imports root-relative.
- Add or update tests before production Python changes and retain docstrings on
  generated Python methods.
- Do not commit local virtual environments, downloads, firmware images,
  captures, `.conf`, credentials, device tokens, caches, or bytecode.
- Keep GitHub issue #32 open until a physical `validate.cmd --port COMx --yes`
  rerun confirms upload success and the validation probe batch starts.

---

### Task 1: Use a stat-safe device-root destination

**Files:**

- Modify: `tests/test_windows_installer.py:396`
- Modify: `tests/test_windows_installer.py:443`
- Modify: `tools/windows_installer.py:775`
- Modify: `README.md:39`
- Modify: `tools/README.md:7`
- Modify: `FIRMWARE_IMPL.md:74`

**Interfaces:**

- Consumes: `application_upload_command(executable: Path, port: str, sources:
  Sequence[Path], *, preflight_reset: bool = False) -> list[str]`
- Produces: the existing command list with `:/.` as its final remote
  destination argument
- Preserves: `run_install_request(request: InstallRequest, sink: OutputSink) ->
  int`, including its upload-failure short circuit, guarded cleanup, and reset
  behavior

- [ ] **Step 1: Change the ordinary upload regression to require `:/.`**

In `WindowsInstallerTests.test_upload_runs_copy_then_reset`, change only the
destination assertion:

```python
self.assertEqual(upload_command[-1], ":/.")
```

- [ ] **Step 2: Change the validation-preflight regression to require `:/.`**

In
`WindowsInstallerTests.test_preflight_reset_upload_failure_stops_before_cleanup`,
change only the final destination assertion:

```python
self.assertEqual(upload_command[-1], ":/.")
```

- [ ] **Step 3: Run the two tests and verify the red state**

Run:

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_upload_runs_copy_then_reset \
  tests.test_windows_installer.WindowsInstallerTests.test_preflight_reset_upload_failure_stops_before_cleanup \
  -v
```

Expected: both tests fail because the current command ends in `:/` instead of
`:/.`. No test should error during setup.

- [ ] **Step 4: Make the minimal production change**

In `application_upload_command`, keep the command shape and replace only its
last argument:

```python
    command.extend(
        [
            "fs",
            "cp",
            "-r",
            *(str(source) for source in sources),
            ":/.",
        ]
    )
```

- [ ] **Step 5: Run the two tests and verify the green state**

Run:

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_upload_runs_copy_then_reset \
  tests.test_windows_installer.WindowsInstallerTests.test_preflight_reset_upload_failure_stops_before_cleanup \
  -v
```

Expected: both tests pass.

- [ ] **Step 6: Update user and maintainer documentation**

In `README.md`, replace the description of the explicit `mpremote`
device-root destination `:/` with:

```markdown
The upload stages a cache-free copy of `src\` and copies its children to the
root-stat-safe `mpremote` device-root destination `:/.`, producing `/boot.py`,
`/main.py`, and `/lib` rather than `/src`.
```

In `tools/README.md`, describe the same destination and its purpose:

```markdown
The Windows `install.cmd` flow stages a cache-free source tree and copies its
children to the root-stat-safe `mpremote` device-root destination `:/.`, so
startup files land at `/boot.py` and `/main.py` and application modules land
under `/lib`.
```

In the `tooling/windows-device-validation` row of `FIRMWARE_IMPL.md`, replace
the explicit destination `:/` with the root-stat-safe destination `:/.`.
Preserve the remainder of the roadmap row, including its hardware-validation
status and next action.

- [ ] **Step 7: Run focused Windows installer validation**

Run:

```bash
python3 -m unittest tests.test_windows_installer -v
```

Expected: all Windows installer tests pass.

- [ ] **Step 8: Run the complete repository validation**

Run:

```bash
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
```

Expected: the complete unit-test suite passes; shell syntax and Python
compilation return status 0; `git diff --check` prints no errors.

- [ ] **Step 9: Review the scoped diff**

Run:

```bash
git status --short
git diff -- tests/test_windows_installer.py tools/windows_installer.py README.md tools/README.md FIRMWARE_IMPL.md
```

Expected: only the two regression assertions, one production destination
token, and the three matching documentation descriptions have changed. No
local-only artifact appears.

- [ ] **Step 10: Commit the validated fix**

Run:

```bash
git add tests/test_windows_installer.py tools/windows_installer.py README.md tools/README.md FIRMWARE_IMPL.md
git commit -m "fix: use stat-safe device root for uploads"
```

Expected: one feature-branch commit containing the tested implementation and
documentation updates.

### Task 2: Integrate and publish the completed fix

**Files:**

- Modify: no repository files
- Validate: local feature branch, local `main`, and `origin/main`

**Interfaces:**

- Consumes: the validated Task 1 commit on
  `fix/windows-validation-root-stat`
- Produces: the same commit reachable from pushed `main`
- Preserves: open GitHub issue #32 pending physical validation

- [ ] **Step 1: Verify the feature branch is clean and contains the fix**

Run:

```bash
git status --short --branch
git log -1 --oneline
```

Expected: a clean `fix/windows-validation-root-stat` branch whose latest
commit message is `fix: use stat-safe device root for uploads`.

- [ ] **Step 2: Fast-forward local `main` from the primary checkout**

Run from `/Users/Brett.Carroll/src/aipi-lite`:

```bash
git status --short --branch
git merge --ff-only fix/windows-validation-root-stat
```

Expected: the primary checkout is clean before the merge, and `main`
fast-forwards to the validated fix commit without a merge commit.

- [ ] **Step 3: Push and verify `main`**

Run:

```bash
git push origin main
git fetch origin main
git rev-parse main
git rev-parse origin/main
```

Expected: the push succeeds and the two printed commit IDs are identical.

- [ ] **Step 4: Report the physical validation command without closing #32**

Ask the operator to run:

```cmd
validate.cmd --port COMx --yes
```

Success evidence must show application upload status `0` and a validation batch
status other than `not-run`. Do not close issue #32 during this implementation
session unless the operator supplies that physical-device evidence.
