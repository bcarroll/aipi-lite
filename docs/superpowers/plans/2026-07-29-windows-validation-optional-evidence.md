# Windows Validation Optional Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Wi-Fi informational and `not-observed` acceptable in Windows physical validation while preserving strict structural checks, explicit failures, and secret-free diagnostic evidence.

**Architecture:** Add explicit required/optional policy to each validation probe and keep result completeness separate from probe success. Aggregate status will ignore an explicitly reported optional Wi-Fi failure and accept `not-observed`, while still failing required probes, malformed or missing result markers, transport failures, upload failures, and explicit observation failures. The firmware and report filters will prevent SSID disclosure and retain bounded `wifi_trace` evidence.

**Tech Stack:** Python 3 standard library, `unittest`, MicroPython-compatible Python, Windows CMD entry points backed by `tools/windows_installer.py`, Git, and GitHub CLI.

## Global Constraints

- Use only `install.cmd`, `dev_install.cmd`, and `validate.cmd` for active installer guidance.
- Add no production dependencies.
- Preserve the local-only network policy; do not add cloud endpoints, telemetry, OTA behavior, credentials, or public-network service calls.
- Do not drive GPIO10 or change hardware-control behavior.
- Keep `.conf`, credentials, device identifiers, raw transcripts, firmware downloads, and other local artifacts ignored.
- Continue running and reporting the Wi-Fi/local-service probe even though its explicit failure is informational.
- Accept `pass` and `not-observed`; preserve explicit `fail` as an aggregate validation failure.
- Preserve fatal behavior for upload errors, batch transport errors, incomplete or malformed probe evidence, and required-probe failures.
- Every generated Python method must have a docstring, and every Python behavior change must have regression coverage.
- Use `apply_patch` for edits and preserve unrelated worktree changes.

---

## File Map

- `tools/windows_installer.py`: Defines probe policy, parses trustworthy result markers, calculates aggregate validation status, and filters shareable serial evidence.
- `src/lib/wifi_probe.py`: Emits MicroPython Wi-Fi probe messages without exposing the configured SSID.
- `tests/test_windows_installer.py`: Covers required/optional aggregation, structural completeness, observation policy, and report evidence.
- `tests/test_wifi_policy.py`: Covers secret-free firmware Wi-Fi messages.
- `README.md`: Documents the operator-visible `validate.cmd` behavior.
- `tools/README.md`: Documents detailed Windows validation and evidence policy.
- `FIRMWARE_IMPL.md`: Records implementation status and remaining physical verification.

---

### Task 1: Separate Optional Probe Failure from Invalid Probe Evidence

**Files:**
- Modify: `tools/windows_installer.py:134-184`
- Modify: `tools/windows_installer.py:1064-1087`
- Modify: `tools/windows_installer.py:1363-1380`
- Test: `tests/test_windows_installer.py:1104-1150`

**Interfaces:**
- Consumes: `DeviceValidationProbe`, `DEVICE_VALIDATION_PROBES`, `parse_device_validation_probe_statuses(transcript, probes)`, and `device_validation_status(upload_status, batch_status, probe_statuses, observations)`.
- Produces: `DeviceValidationProbe.required: bool`; parser output containing only uniquely valid `(name, status)` entries; aggregate policy that ignores nonzero results only for probes with `required=False`.

- [ ] **Step 1: Write failing policy and parser tests**

Update the malformed-marker test so invalid or absent markers are not converted
into ordinary numeric failures:

```python
statuses = dict(
    installer.parse_device_validation_probe_statuses(
        transcript,
        installer.DEVICE_VALIDATION_PROBES,
    )
)

self.assertEqual(
    statuses,
    {
        "display": 0,
        "io": 1,
        "inference": 0,
    },
)
```

Extend the Wi-Fi sweep test with:

```python
self.assertFalse(wifi_probe.required)
self.assertTrue(
    all(
        probe.required
        for probe in installer.DEVICE_VALIDATION_PROBES
        if probe.name != "wifi"
    )
)
```

Add a focused aggregate-policy test:

```python
def test_device_validation_accepts_reported_optional_wifi_failure_only(self):
    """Wi-Fi may report failure, but its marker and required probes remain mandatory."""
    observations = {
        name: "pass" for name in installer.DEVICE_VALIDATION_OBSERVATIONS
    }
    wifi_failed = [
        (probe.name, 1 if probe.name == "wifi" else 0)
        for probe in installer.DEVICE_VALIDATION_PROBES
    ]

    self.assertEqual(
        installer.device_validation_status(0, 0, wifi_failed, observations),
        0,
    )
    self.assertEqual(
        installer.device_validation_status(
            0,
            0,
            [result for result in wifi_failed if result[0] != "wifi"],
            observations,
        ),
        1,
    )

    required_failed = [
        (name, 1 if name == "io" else status)
        for name, status in wifi_failed
    ]
    self.assertEqual(
        installer.device_validation_status(0, 0, required_failed, observations),
        1,
    )
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_probe_status_parser_rejects_missing_and_malformed_markers \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_sweep_includes_the_local_wifi_probe \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_accepts_reported_optional_wifi_failure_only \
  -v
```

Expected: failures because `required` does not exist, malformed/missing markers
are synthesized as `1`, and Wi-Fi failure currently fails aggregate status.

- [ ] **Step 3: Add explicit probe policy and trustworthy parsing**

Add the policy field to the existing dataclass:

```python
@dataclass(frozen=True)
class DeviceValidationProbe:
    """Describe one self-contained AIPI-Lite device validation probe."""

    name: str
    command: str
    serial_prefix: str
    observations: tuple[str, ...] = ()
    required: bool = True
```

Set only the Wi-Fi probe to optional:

```python
DeviceValidationProbe(
    name="wifi",
    command="import wifi_probe; assert wifi_probe.run_probe() == 'ok'",
    serial_prefix="wifi_probe:",
    required=False,
),
```

Change the parser return expression so only one valid marker is returned:

```python
return [
    (probe.name, parsed_statuses[probe.name])
    for probe in probes
    if probe.name in parsed_statuses and probe.name not in malformed_names
]
```

In `device_validation_status`, build the expected and received maps after the
upload/batch checks:

```python
expected_probes = {probe.name: probe for probe in DEVICE_VALIDATION_PROBES}
status_by_probe = dict(probe_statuses)
if (
    len(probe_statuses) != len(DEVICE_VALIDATION_PROBES)
    or set(status_by_probe) != set(expected_probes)
):
    return 1
if any(
    status_by_probe[probe.name] != 0
    for probe in DEVICE_VALIDATION_PROBES
    if probe.required
):
    return 1
```

Remove the existing unconditional `any(status != 0 ...)` check. Leave the
observation check unchanged for Task 2.

- [ ] **Step 4: Run focused and installer tests and verify GREEN**

Run:

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_probe_status_parser_rejects_missing_and_malformed_markers \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_sweep_includes_the_local_wifi_probe \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_accepts_reported_optional_wifi_failure_only \
  -v
python3 -m unittest discover -s tests -p 'test_windows_installer.py' -v
```

Expected: all selected and Windows installer tests pass.

- [ ] **Step 5: Commit the optional-probe policy**

```bash
git add tools/windows_installer.py tests/test_windows_installer.py
git commit -m "fix: make validation Wi-Fi probe optional"
```

---

### Task 2: Accept Not-Observed Evidence but Preserve Explicit Failures

**Files:**
- Modify: `tools/windows_installer.py:1363-1380`
- Test: `tests/test_windows_installer.py` near the aggregate-policy tests from Task 1

**Interfaces:**
- Consumes: `DEVICE_VALIDATION_OBSERVATIONS`, `observation_status(observations, name)`, and the structurally valid probe list from Task 1.
- Produces: aggregate observation policy where only the literal normalized status `fail` is fatal.

- [ ] **Step 1: Write the failing observation-policy test**

```python
def test_device_validation_accepts_not_observed_but_rejects_explicit_fail(self):
    """Unobserved evidence is acceptable, while an explicit failure remains fatal."""
    probe_statuses = [
        (probe.name, 0) for probe in installer.DEVICE_VALIDATION_PROBES
    ]
    unobserved = {
        name: "not-observed"
        for name in installer.DEVICE_VALIDATION_OBSERVATIONS
    }

    self.assertEqual(
        installer.device_validation_status(0, 0, probe_statuses, unobserved),
        0,
    )

    explicit_failure = dict(unobserved)
    explicit_failure["speaker"] = "fail"
    self.assertEqual(
        installer.device_validation_status(
            0,
            0,
            probe_statuses,
            explicit_failure,
        ),
        1,
    )
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_accepts_not_observed_but_rejects_explicit_fail \
  -v
```

Expected: the `not-observed` assertion fails with aggregate status `1`.

- [ ] **Step 3: Implement the narrow observation rule**

Replace the all-pass observation condition with:

```python
if any(
    observation_status(observations, name) == "fail"
    for name in DEVICE_VALIDATION_OBSERVATIONS
):
    return 1
```

Do not change prompting or persisted observation values.

- [ ] **Step 4: Run focused and installer tests and verify GREEN**

```bash
python3 -m unittest \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_accepts_not_observed_but_rejects_explicit_fail \
  -v
python3 -m unittest discover -s tests -p 'test_windows_installer.py' -v
```

Expected: all selected and Windows installer tests pass. The existing
integration test
`test_device_validation_records_unobserved_checks_and_keeps_report_local`
supplies no result markers, so add this local test helper:

```python
def successful_batch(_command, probe_sink):
    """Emit one successful result marker for every configured probe."""
    for probe in installer.DEVICE_VALIDATION_PROBES:
        probe_sink.write(
            f"device_validation_result: name={probe.name} status=0"
        )
    return 0
```

Use `side_effect=successful_batch` for its `run_streaming` patch. Change the
expected return and issue aggregate status from `1` to `0`, update the docstring
to say unobserved checks are accepted, and keep the assertion that literal
`not-observed` values are retained.

- [ ] **Step 5: Commit the observation policy**

```bash
git add tools/windows_installer.py tests/test_windows_installer.py
git commit -m "fix: accept unobserved validation evidence"
```

---

### Task 3: Keep Wi-Fi Evidence Diagnostic and SSID-Safe

**Files:**
- Modify: `src/lib/wifi_probe.py:538-565`
- Modify: `tools/windows_installer.py:1383-1391`
- Test: `tests/test_wifi_policy.py:674-742`
- Test: `tests/test_windows_installer.py` near device serial/report tests

**Interfaces:**
- Consumes: the existing `wifi_trace` contract and `device_validation_serial_lines(transcript)`.
- Produces: constant firmware connection text, exclusion of legacy SSID-bearing connection lines from shareable evidence, and inclusion of `wifi_trace` lines.

- [ ] **Step 1: Write the failing firmware privacy test**

Extend `test_wifi_probe_connects_and_reports_ready_on_health_ok`:

```python
self.assertIn(
    "wifi_probe: connecting to configured local network",
    messages,
)
self.assertNotIn("LabNet", "\n".join(messages))
self.assertNotIn("secret-password", "\n".join(messages))
```

- [ ] **Step 2: Write the failing report-evidence test**

Add:

```python
def test_device_validation_serial_keeps_wifi_trace_and_drops_legacy_ssid_line(self):
    """Shareable evidence should retain safe Wi-Fi diagnostics without an SSID."""
    transcript = "\n".join(
        [
            "wifi_probe: starting local Wi-Fi probe",
            "wifi_probe: connecting to GalaxyWifi",
            "wifi_trace phase=status elapsed_ms=1000 connected=0 "
            "status=no_ap_found status_code=-2",
            "unrelated host output",
        ]
    )

    lines = installer.device_validation_serial_lines(transcript)

    self.assertIn("wifi_probe: starting local Wi-Fi probe", lines)
    self.assertIn(
        "wifi_trace phase=status elapsed_ms=1000 connected=0 "
        "status=no_ap_found status_code=-2",
        lines,
    )
    self.assertNotIn("GalaxyWifi", "\n".join(lines))
    self.assertNotIn("unrelated host output", lines)
```

- [ ] **Step 3: Run the two tests and verify RED**

```bash
python3 -m unittest \
  tests.test_wifi_policy.WifiPolicyTests.test_wifi_probe_connects_and_reports_ready_on_health_ok \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_serial_keeps_wifi_trace_and_drops_legacy_ssid_line \
  -v
```

Expected: firmware output contains `LabNet`, and `wifi_trace` is omitted from
shareable validation serial evidence.

- [ ] **Step 4: Make firmware output constant and report filtering defensive**

In `run_probe`, replace the SSID-bearing message:

```python
print_func("wifi_probe: connecting to configured local network")
```

In `device_validation_serial_lines`, retain safe trace lines and exclude the
legacy SSID-bearing prefix:

```python
prefixes = tuple(probe.serial_prefix for probe in DEVICE_VALIDATION_PROBES)
safe_prefixes = prefixes + ("wifi_trace ",)
legacy_sensitive_prefixes = ("wifi_probe: connecting to ",)
return [
    line
    for line in redact_text(transcript).splitlines()
    if line.startswith(safe_prefixes)
    and not line.startswith(legacy_sensitive_prefixes)
]
```

The local raw transcript still contains the new constant connection message;
the shareable issue body omits both new and legacy connection lines so an older
firmware transcript cannot expose an SSID.

- [ ] **Step 5: Run focused policy and installer tests and verify GREEN**

```bash
python3 -m unittest \
  tests.test_wifi_policy.WifiPolicyTests.test_wifi_probe_connects_and_reports_ready_on_health_ok \
  tests.test_windows_installer.WindowsInstallerTests.test_device_validation_serial_keeps_wifi_trace_and_drops_legacy_ssid_line \
  -v
python3 -m unittest discover -s tests -p 'test_wifi_policy.py' -v
python3 -m unittest discover -s tests -p 'test_windows_installer.py' -v
```

Expected: all selected, Wi-Fi policy, and Windows installer tests pass.

- [ ] **Step 6: Commit the evidence-safety change**

```bash
git add src/lib/wifi_probe.py tools/windows_installer.py \
  tests/test_wifi_policy.py tests/test_windows_installer.py
git commit -m "fix: redact validation Wi-Fi evidence"
```

---

### Task 4: Document the Optional Evidence Policy

**Files:**
- Modify: `README.md:303-336`
- Modify: `tools/README.md:125-150`
- Modify: `FIRMWARE_IMPL.md:74`

**Interfaces:**
- Consumes: the implemented policy and evidence behavior from Tasks 1-3.
- Produces: consistent operator guidance and roadmap status with no obsolete all-pass or one-second wording.

- [ ] **Step 1: Update the root workflow documentation**

In `README.md`:

- Correct the physical-validation pre-upload delay from one second to five
  seconds.
- Include the local Wi-Fi/health probe in the probe sequence.
- State that Wi-Fi is informational and its reported failure does not fail the
  aggregate result.
- State that `pass` and `not-observed` are accepted evidence, while explicit
  `fail` remains fatal.
- State that required probe, upload, batch transport, and incomplete-result
  failures remain fatal.
- State that GitHub-ready evidence retains secret-free `wifi_trace` lines and
  excludes configured SSIDs.

- [ ] **Step 2: Update the tooling reference**

Replace the `tools/README.md` statements that only an all-pass run succeeds and
that Wi-Fi failure makes aggregate status nonzero. Document the exact same
policy as `README.md`, while retaining the requirement for a local config and
mock service when an operator wants the informational Wi-Fi probe itself to
pass.

- [ ] **Step 3: Update implementation status**

In the `tooling/windows-device-validation` row of `FIRMWARE_IMPL.md`, add:

- Wi-Fi is an informational optional probe.
- `not-observed` is accepted evidence.
- Explicit operator failures and required/structural/transport failures remain
  nonzero.
- Shareable validation evidence includes SSID-free `wifi_trace` diagnostics.

Keep the remaining-work cell focused on a future physical rerun that confirms
the new aggregate behavior and captures Wi-Fi diagnostics.

- [ ] **Step 4: Check documentation consistency**

```bash
rg -n "one second|all-pass|unobserved check makes|Wi-Fi.*aggregate status|wifi.*aggregate status" \
  README.md tools/README.md FIRMWARE_IMPL.md
git diff --check
```

Expected: no active Windows-validation guidance contradicts the new five-second
delay or optional evidence policy; `git diff --check` exits zero.

- [ ] **Step 5: Commit documentation**

```bash
git add README.md tools/README.md FIRMWARE_IMPL.md
git commit -m "docs: explain optional validation evidence"
```

---

### Task 5: Verify, Integrate, Push, and Close Issue #40

**Files:**
- Verify: all changed source, tests, documentation, design, and plan files
- Merge: `bcarroll/issue40-optional-wifi` into `main`
- Remote action: close only GitHub issue #40 after the validated commit is on `origin/main`

**Interfaces:**
- Consumes: committed feature-branch changes from Tasks 1-4.
- Produces: a validated `origin/main` commit and a completed issue #40 with commit/test evidence.

- [ ] **Step 1: Run complete feature-branch verification**

```bash
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
git status --short --branch
```

Expected: 0 test failures, every command exits zero, and the worktree is clean.

- [ ] **Step 2: Audit the committed diff against the specification**

```bash
git diff --stat main...HEAD
git diff main...HEAD -- \
  tools/windows_installer.py src/lib/wifi_probe.py \
  tests/test_windows_installer.py tests/test_wifi_policy.py \
  README.md tools/README.md FIRMWARE_IMPL.md
git log --oneline main..HEAD
```

Confirm all eight testing requirements in the design have direct coverage and
that no credential, `.conf`, transcript, local path, firmware download, or
unrelated file is present.

- [ ] **Step 3: Push the completed feature branch**

```bash
git push origin bcarroll/issue40-optional-wifi
```

- [ ] **Step 4: Merge the validated branch into local `main`**

From `/Users/Brett.Carroll/src/aipi-lite`:

```bash
git status --short --branch
git fetch origin
git merge --no-ff bcarroll/issue40-optional-wifi \
  -m "merge: integrate optional validation evidence"
```

Stop if `main` is dirty or has diverged unexpectedly; preserve all user work.

- [ ] **Step 5: Re-run complete verification on the merge result**

```bash
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
git status --short --branch
```

Expected: 0 test failures, every command exits zero, and only the expected
unpushed merge commit separates `main` from `origin/main`.

- [ ] **Step 6: Push `main` and verify remote refs**

```bash
git push origin main
git fetch origin
git rev-parse HEAD
git rev-parse origin/main
```

Expected: local `HEAD` and `origin/main` resolve to the same commit.

- [ ] **Step 7: Close only issue #40**

Capture the actual merge commit from Step 6:

```bash
issue40_merge_commit="$(git rev-parse HEAD)"
gh issue close 40 --repo bcarroll/aipi-lite --reason completed \
  --comment "Implemented optional Windows validation evidence policy in ${issue40_merge_commit}. Wi-Fi remains reported but is informational; not-observed is accepted, explicit and required failures remain fatal, and Wi-Fi diagnostics are SSID-safe. Validation: the full unittest suite, shell syntax, Python compilation, and git diff checks passed."
```

Then verify:

```bash
gh issue view 40 --repo bcarroll/aipi-lite \
  --json number,state,url --jq '{number, state, url}'
```

Expected: issue #40 reports `CLOSED`.

- [ ] **Step 8: Remove the completed local worktree and branch**

From `/Users/Brett.Carroll/src/aipi-lite`:

```bash
git worktree remove .worktrees/issue40-optional-wifi
git branch -d bcarroll/issue40-optional-wifi
git status --short --branch
```

Keep the remote feature branch unless the user explicitly asks to delete it.
