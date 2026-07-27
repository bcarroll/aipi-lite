# Windows-Only Installer Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the Unix installer entry points and make Windows command scripts the repository's only supported install, developer-capture, and device-validation workflows.

**Architecture:** Remove the two root Unix entry points and the tests coupled to their retired implementations. Add a focused regression test for the supported installer surface, update active workflow documentation to Windows commands, and preserve historical roadmap detail while marking the Unix workflows retired.

**Tech Stack:** Python 3 `unittest`, Windows CMD entry points, Markdown documentation, Git

## Global Constraints

- Do not add production dependencies.
- Keep `install.cmd`, `dev_install.cmd`, `validate.cmd`, and `tools/windows_installer.py` behavior unchanged.
- Preserve the local-only firmware policy; do not add cloud endpoints, telemetry, OTA behavior, credentials, or public-network service calls.
- Do not imply that Windows scripts provide firmware backup, flashing, or restore.
- Preserve historical design documents where they accurately describe completed work.
- Do not commit generated downloads, virtual environments, firmware dumps, credentials, device tokens, `.conf`, captures, `__pycache__`, or `*.pyc`.
- Generated Python tests must include module, class, and method docstrings and remain compatible with `unittest`.
- Documentation and commands must remain accessible as plain text and comply with U.S. Federal Government security and accessibility expectations.

---

### Task 1: Retire Unix installer entry points with regression coverage

**Files:**
- Create: `tests/test_windows_only_installers.py`
- Delete: `install.sh`
- Delete: `dev_install.sh`
- Delete: `tests/test_install_script.py`
- Delete: `tests/test_dev_install_capture.py`
- Test: `tests/test_windows_only_installers.py`
- Test: `tests/test_windows_installer.py`

**Interfaces:**
- Consumes: repository-root entry-point paths
- Produces: a regression contract that Unix installers stay absent and Windows CMD entry points stay present

- [ ] **Step 1: Add the failing supported-surface regression test**

Create `tests/test_windows_only_installers.py` with this content:

```python
"""Regression tests for the supported Windows-only installer surface."""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class WindowsOnlyInstallerTests(unittest.TestCase):
    """Protect the Windows-only installer entry-point policy."""

    def test_retired_unix_installers_are_absent(self):
        """Unix installer entry points should stay retired."""
        for name in ("install.sh", "dev_install.sh"):
            with self.subTest(name=name):
                self.assertFalse((REPO_ROOT / name).exists())

    def test_supported_windows_entrypoints_are_present(self):
        """Windows install, capture, and validation entry points should remain."""
        for name in ("install.cmd", "dev_install.cmd", "validate.cmd"):
            with self.subTest(name=name):
                self.assertTrue((REPO_ROOT / name).is_file())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new test and verify the retirement check fails**

Run:

```bash
python3 -m unittest tests.test_windows_only_installers -v
```

Expected: `test_retired_unix_installers_are_absent` fails because
`install.sh` and `dev_install.sh` still exist; the Windows-entry-point test
passes.

- [ ] **Step 3: Delete the retired scripts and their implementation-specific tests**

Delete these tracked files without changing the Windows implementation:

```text
install.sh
dev_install.sh
tests/test_install_script.py
tests/test_dev_install_capture.py
```

- [ ] **Step 4: Run focused tests and verify the supported surface passes**

Run:

```bash
python3 -m unittest tests.test_windows_only_installers tests.test_windows_installer -v
```

Expected: all supported-surface and Windows installer tests pass.

- [ ] **Step 5: Commit and push the retired entry points**

```bash
git add install.sh dev_install.sh tests/test_install_script.py tests/test_dev_install_capture.py tests/test_windows_only_installers.py
git commit -m "tooling: retire Unix installer entry points"
git push origin main
```

### Task 2: Convert active workflow documentation to Windows-only commands

**Files:**
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `RECOVERY.md`
- Modify: `DEVELOPER.md`
- Modify: `MVP.md`
- Modify: `src/README.md`
- Modify: `tools/README.md`
- Modify: `INFERENCE_FEASIBILITY.md`
- Modify: `tests/test_recovery_docs.py`
- Modify: `tests/test_mvp_release.py`

**Interfaces:**
- Consumes: existing `install.cmd`, `dev_install.cmd`, and `validate.cmd` command-line interfaces
- Produces: one consistent Windows-only operator and developer workflow plus static regression coverage for the supported recovery guidance

- [ ] **Step 1: Replace obsolete recovery-documentation assertions**

In `tests/test_recovery_docs.py`, retain the existing module, imports,
`setUpClass`, and class structure but replace the four test methods with:

```python
    def test_documents_supported_application_recovery(self):
        """Recovery docs should explain the supported Windows application path."""
        for expected in (
            "Bootloader Mode",
            "Application Recovery",
            "install.cmd --port COM3 --yes",
            "validate.cmd --port COM3 --yes",
            "already-flashed ESP32_GENERIC_S3 MicroPython",
        ):
            self.assertIn(expected, self.recovery_text)

    def test_documents_unavailable_firmware_automation(self):
        """Recovery docs should clearly bound unsupported firmware operations."""
        for expected in (
            "does not automate",
            "stock firmware backup",
            "MicroPython flashing",
            "stock firmware restore",
            "separately approved",
        ):
            self.assertIn(expected, self.recovery_text)
        for retired in (
            "./install.sh",
            "--flash-micropython",
            "--restore-backup",
            "read-flash 0 0x1000000",
        ):
            self.assertNotIn(retired, self.recovery_text)

    def test_documents_recovery_safety_checklist(self):
        """Recovery docs should retain federal and hardware safety boundaries."""
        for expected in (
            "Recovery Safety Checklist",
            "stable USB power",
            "SPEC.md",
            "public cloud",
            "not staged in Git",
            "GPIO10",
        ):
            self.assertIn(expected, self.recovery_text)

    def test_roadmap_and_readme_reference_current_recovery(self):
        """Top-level docs should point to the Windows-only recovery boundary."""
        self.assertIn("[RECOVERY.md](RECOVERY.md)", self.readme_text)
        self.assertIn("install.cmd --port COM3 --yes", self.readme_text)
        self.assertIn("does not automate firmware backup", self.readme_text)
        self.assertIn("`feat/01-backup-recovery` | Retired", self.impl_text)
        self.assertIn("Windows CMD", self.impl_text)
```

In `tests/test_mvp_release.py`, replace
`test_mvp_documentation_contains_required_checklists` with:

```python
    def test_mvp_documentation_contains_required_checklists(self):
        """MVP docs should describe the Windows-only local release workflow."""
        mvp_text = (REPO_ROOT / "MVP.md").read_text(encoding="utf-8")

        for expected in (
            "Firmware Recovery Limitations",
            "MVP Install Guide",
            "MVP Configuration Guide",
            "MVP Validation Checklist",
            "Validation Report Template",
            "No-cloud network verification",
            "install.cmd",
            "validate.cmd",
            "GPIO10 board-power control",
            "Installer capture issue/link",
            "Windows installer command",
            "but without",
        ):
            self.assertIn(expected, mvp_text)
        self.assertNotIn("install.sh", mvp_text)
        self.assertNotIn("dev_install.sh", mvp_text)
```

- [ ] **Step 2: Run the updated documentation tests and verify they fail**

Run:

```bash
python3 -m unittest tests.test_recovery_docs tests.test_mvp_release -v
```

Expected: the documentation assertions fail because current active docs still
describe the retiring Unix workflows.

- [ ] **Step 3: Update repository instructions and top-level user workflow**

In `AGENTS.md`, replace the `install.sh` instruction with the supported Windows
entry points and remove `bash -n install.sh` from required checks. Keep
`bash -n tools/setup_micropython_tools.sh` because that shared maintenance tool
is not being removed.

In `README.md`:

- Lead with `install.cmd --port COM3 --yes`.
- Keep `install.cmd --list-ports`, saved `.conf` COM-port behavior, guarded
  cleanup, device-root upload, reset fallback, and `--no-reset`.
- Keep the existing `dev_install.cmd` and `validate.cmd` examples.
- Replace Unix inference-capture examples with:

```cmd
dev_install.cmd --inference-probe --gh bcarroll/aipi-lite --device-label bench-a --inference-check display=pass --inference-check status-led=pass --inference-check button=pass --inference-check offline=pass -- --port COM3 --yes
```

- Remove Unix self-update, trace, environment-listing, port-listing, flashing,
  backup, restore, and cleanup commands.
- State directly that repository scripts no longer automate firmware backup,
  MicroPython flashing, stock restore, or Unix trace capture.
- Keep local-only configuration, Wi-Fi probe, application behavior, physical
  validation, security, and host-test guidance.

- [ ] **Step 4: Update recovery and developer runbooks**

Rewrite `RECOVERY.md` so it:

- Preserves bootloader and electrical-safety warnings.
- States that the supported Windows scripts are application-first only.
- States that backup, firmware flashing, and stock restore require a
  separately approved/manual recovery procedure outside the supported
  repository scripts.
- Does not publish unvalidated Windows erase or flash commands.
- Directs ordinary application recovery to `install.cmd --port COM3 --yes` and
  physical validation to `validate.cmd --port COM3 --yes`.

Update `DEVELOPER.md` to use:

```cmd
install.cmd --list-ports
dev_install.cmd --device-label bench-a --hardware-note "MVP install validation" -- --port COM3 --yes
validate.cmd --port COM3 --yes --device-label bench-a
```

Remove WSL serial mappings and Unix trace instructions. Retain redaction,
GitHub authentication, ignored artifact, and failure-reporting guidance that is
implemented by the Windows helper.

- [ ] **Step 5: Update MVP, application, tooling, and inference guides**

In `MVP.md`, replace Unix install and capture commands with Windows CMD
equivalents, remove Unix syntax checks from the validation checklist and report
template, and keep the local-only/no-cloud acceptance criteria.

In `src/README.md`, replace Unix upload examples with
`install.cmd --port COM3 --yes`, explain that `src/local_wifi_config.py` must be
created locally before upload, and remove unsupported firmware-image selection
instructions.

In `tools/README.md`, remove the retired Unix capture, trace, and cleanup
sections; retain the Windows install, inference, and physical-validation
sections and the shared tooling information that remains accurate.

In `INFERENCE_FEASIBILITY.md`, remove the Unix captured-bench path and make the
existing Windows captured-bench command the sole supported wrapper workflow.
Use `COM3` rather than a Unix serial-device path in the report template.

- [ ] **Step 6: Review active documentation for stale operational references**

Run:

```bash
rg -n 'install\.sh|dev_install\.sh' AGENTS.md README.md RECOVERY.md DEVELOPER.md MVP.md src/README.md tools/README.md INFERENCE_FEASIBILITY.md
```

Expected: no matches.

- [ ] **Step 7: Run focused documentation-adjacent regression checks**

Run:

```bash
python3 -m unittest tests.test_windows_only_installers tests.test_windows_installer tests.test_recovery_docs tests.test_mvp_release tests.test_wifi_policy -v
bash -n tools/setup_micropython_tools.sh
git diff --check
```

Expected: all tests and syntax checks pass; `git diff --check` produces no
output.

- [ ] **Step 8: Commit and push the active documentation**

```bash
git add AGENTS.md README.md RECOVERY.md DEVELOPER.md MVP.md src/README.md tools/README.md INFERENCE_FEASIBILITY.md tests/test_recovery_docs.py tests/test_mvp_release.py
git commit -m "docs: make installer guidance Windows-only"
git push origin main
```

### Task 3: Mark Unix workflows retired in planning and status documents

**Files:**
- Modify: `FIRMWARE_PLAN.md`
- Modify: `FIRMWARE_IMPL.md`

**Interfaces:**
- Consumes: completed historical implementation records
- Produces: current status that distinguishes retired Unix tooling from supported Windows tooling

- [ ] **Step 1: Update current status tables**

In `FIRMWARE_PLAN.md`:

- Mark automated flashing support as retired from the supported repository
  workflow while retaining the historical milestone evidence.
- Change developer capture and inference feasibility descriptions to
  `dev_install.cmd` and Windows-only capture.
- Keep historical descriptions in their original sections but introduce them
  as retired implementation history.

In `FIRMWARE_IMPL.md`:

- Mark `feat/01-backup-recovery` and `tooling/dev-install-capture` as retired
  Unix workflows.
- Remove deleted paths from current Windows validation, Wi-Fi, and inference
  evidence rows.
- Make current remaining-work commands use Windows CMD entry points.
- Keep dated issue evidence and original branch acceptance criteria as
  historical records, explicitly labeled as retired where necessary.
- Add a 2026-07-27 roadmap note that Windows CMD scripts are the supported
  installer surface and automated backup/flash/restore is unavailable.

- [ ] **Step 2: Review every remaining retired-script reference**

Run:

```bash
rg -n 'install\.sh|dev_install\.sh' FIRMWARE_PLAN.md FIRMWARE_IMPL.md docs/superpowers/specs
```

Expected: every match in `FIRMWARE_PLAN.md`, `FIRMWARE_IMPL.md`, or an existing
design spec is historical and does not direct current operator action.

- [ ] **Step 3: Run roadmap consistency checks**

Run:

```bash
git diff --check
python3 -m unittest tests.test_windows_only_installers tests.test_windows_installer -v
```

Expected: no whitespace errors and all focused tests pass.

- [ ] **Step 4: Commit and push roadmap status**

```bash
git add FIRMWARE_PLAN.md FIRMWARE_IMPL.md
git commit -m "docs: retire Unix installer roadmap workflows"
git push origin main
```

### Task 4: Complete repository regression validation

**Files:**
- Verify: all changed and deleted files

**Interfaces:**
- Consumes: Tasks 1-3
- Produces: evidence that the supported Windows-only repository remains regression-free

- [ ] **Step 1: Run the complete Python suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: all discovered tests pass with zero failures and zero errors.

- [ ] **Step 2: Run remaining shell and whitespace checks**

Run:

```bash
bash -n tools/setup_micropython_tools.sh
git diff --check
```

Expected: both commands exit successfully and `git diff --check` produces no
output.

- [ ] **Step 3: Verify the final supported and retired surfaces**

Run:

```bash
test ! -e install.sh
test ! -e dev_install.sh
test -f install.cmd
test -f dev_install.cmd
test -f validate.cmd
rg -n 'install\.sh|dev_install\.sh' --glob '!docs/superpowers/specs/**' --glob '!docs/superpowers/plans/**' .
git status --short --branch
```

Expected: path checks pass. Any search matches are explicitly retired history
in roadmap documents, and Git reports `main` synchronized with `origin/main`
after all implementation commits are pushed.

- [ ] **Step 4: Inspect the final commit range**

Run:

```bash
git log --oneline --decorate -5
git diff 444eef1..HEAD --stat
```

Expected: the implementation commits cover only the approved installer
retirement, regression test, active documentation, and roadmap status changes.
