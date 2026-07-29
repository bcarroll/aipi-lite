# Windows Validation Optional Evidence Design

## Status

Approved in conversation on 2026-07-29. This design resolves the validation
policy represented by GitHub issue #40.

## Context

`validate.cmd` uploads the MicroPython application, runs the complete physical
probe batch, collects operator observations, writes local evidence, and creates
a redacted GitHub issue. The current aggregate status requires every probe to
return zero and every operator observation to be `pass`.

Issue #40 demonstrated that this policy is too strict for the intended bench
workflow:

- The application upload and validation batch transport succeeded.
- Display, GPIO, codec, capture, playback, and offline inference probes
  succeeded.
- The local Wi-Fi/health probe failed while attempting to join the configured
  network.
- Microphone, speaker, and inference UI observations were recorded as
  `not-observed`.

The operator has established the following policy:

- Local Wi-Fi/service validation is optional.
- An operator may record any physical observation as `not-observed` without
  failing the aggregate run.
- An explicit `fail` observation remains a validation failure.

The report published for issue #40 also included the configured Wi-Fi network
name even though the section was described as redacted. Future shareable
reports must not expose that local identifier.

## Goals

1. Continue running the Wi-Fi/local-service probe and recording its actual
   result.
2. Exclude a Wi-Fi probe failure from the aggregate validation result.
3. Accept `pass` and `not-observed` operator observations.
4. Preserve explicit `fail` observations as aggregate failures.
5. Preserve strict failure behavior for application upload errors, batch
   transport errors, incomplete probe result sets, and failures from required
   probes.
6. Keep future GitHub-ready validation evidence free of the configured SSID
   while retaining secret-free Wi-Fi driver diagnostics.
7. Preserve the local-only networking policy and add no production dependency.

## Non-Goals

- Do not change Wi-Fi connection, retry, timeout, endpoint, or health-check
  behavior.
- Do not make public-network or cloud access permissible.
- Do not remove the Wi-Fi probe from the validation batch.
- Do not infer a physical observation that the operator did not make.
- Do not make an explicit operator `fail` nonfatal.
- Do not change firmware flashing, upload, COM-port selection, or reset
  behavior.
- Do not edit or delete previously published GitHub issue bodies.

## Design

### Explicit probe policy

`DeviceValidationProbe` will gain a required/optional policy field whose
default is required. The Wi-Fi probe will set that field to optional. All other
current probes remain required.

The aggregate-status calculation will match parsed results to the configured
probe definitions. A nonzero result from a required probe fails validation. A
nonzero result from the optional Wi-Fi probe remains visible in metadata and
the issue body but does not fail validation.

The structural checks remain strict. Upload status and batch transport status
must both be zero, and the parsed result collection must contain exactly one
uniquely valid entry for every configured probe. The result parser will omit a
probe whose marker is missing, duplicated, or malformed instead of synthesizing
a normal numeric failure result. The existing aggregate completeness check can
then distinguish an optional probe that explicitly returned `1` from a probe
that never returned trustworthy evidence. Optional means that the Wi-Fi probe
may report failure; it does not mean that the result marker may be absent.

### Operator observation policy

The existing three-state input remains unchanged:

- `pass`: accepted.
- `not-observed`: accepted and reported accurately.
- `fail`: aggregate validation failure.

All configured observation prompts still run. Missing interactive input
continues to be represented as `not-observed`; it is not silently converted to
`pass`.

### Evidence and redaction

The Wi-Fi firmware probe will replace the SSID-bearing serial message with a
constant message indicating that it is connecting to the configured local
network. The on-device display may continue showing its existing local-only
network detail because the display is not part of the shareable transcript.

The validation issue evidence filter will retain the existing stable
`wifi_probe:` lines and the bounded, secret-free `wifi_trace` lines. These
trace lines already exclude the SSID, password, service URL, approved
hostnames, MAC/BSSID, nearby access-point names, and arbitrary exception text.
They provide the driver status needed to distinguish timeout,
authentication, access-point, and interface failures.

Raw local transcripts remain under the ignored validation capture directory.
No credentials, local configuration, or device identifiers become tracked
files.

### User-visible reporting

The issue body and run metadata continue to report the numeric result for every
probe and the literal status for every observation. Documentation will state
that:

- Wi-Fi is an informational, optional probe.
- `not-observed` is an acceptable evidence state.
- Required probe failures, explicit observation failures, upload failures, and
  batch transport failures still produce a nonzero aggregate result.

No new command-line flag or installer prompt is introduced.

## Error Handling

- A failed optional Wi-Fi probe is recorded but ignored by aggregate status.
- A missing, duplicate, or malformed probe result remains a structural
  validation failure, including for Wi-Fi.
- A nonzero `mpremote` batch status remains fatal even if all individual
  markers were emitted.
- An explicit operator `fail` remains fatal.
- Failure to publish through `gh` remains separate from the measured device
  validation status and leaves the report available locally.

## Testing

Host-side regression coverage will prove:

1. The Wi-Fi probe is marked optional but remains ordered between playback and
   inference.
2. A reported Wi-Fi failure does not fail an otherwise successful aggregate
   run.
3. A required probe failure still fails the aggregate run.
4. A missing Wi-Fi result fails the structural completeness check.
5. `not-observed` is accepted for every operator observation.
6. An explicit `fail` observation fails the run.
7. Shareable Wi-Fi serial output does not contain the configured SSID.
8. Secret-free `wifi_trace` lines are retained in GitHub-ready device serial
   evidence.

Tests will follow red-green-refactor: each behavioral regression test will be
observed failing before the smallest production change is made.

After implementation, verification will include:

```text
python3 -m unittest tests.test_windows_installer tests.test_wifi_policy -v
python3 -m unittest discover -s tests -v
bash -n tools/setup_micropython_tools.sh
python3 -m py_compile tools/windows_installer.py
git diff --check
```

Physical validation remains useful but is not required to prove the host-side
aggregation and redaction policy. A later `validate.cmd --port COMx --yes` run
should report Wi-Fi accurately while allowing an otherwise successful
aggregate result.

## Documentation

Update:

- `README.md` for the operator-visible validation policy.
- `tools/README.md` for the Windows validation evidence behavior.
- `FIRMWARE_IMPL.md` for the implementation status and physical follow-up.

No hardware facts or recovery behavior change, so `SPEC.md`, `FIRMWARE_PLAN.md`,
and `RECOVERY.md` do not require edits.
