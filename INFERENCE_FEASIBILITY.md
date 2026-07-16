# AIPI-Lite On-Device Inference Feasibility

This note defines the scope and validation path for
`spike/13-on-device-inference-feasibility`.

## Scope

The feasibility spike is offline-first. It does not require Wi-Fi, a LAN
service, cloud endpoints, telemetry, model downloads, activation calls, or
speaker output. The current test AIPI-Lite has its speaker disconnected, so
speaker playback remains outside this spike's acceptance path.

The goal is to decide whether a useful on-device inference feature is worth
building after measuring resource headroom and visible responsiveness. This
spike is not a supported model runtime.

Candidate use cases:

- Intent routing for a small fixed command set.
- Constrained local responses for device status or help text.
- Lightweight local pre-processing before a later assistant exchange.
- Wake-word assistance only after the audio path is separately validated.

Non-goals:

- No production model runtime integration.
- No committed model binaries or generated weights.
- No public-network, vendor, OTA, analytics, or cloud AI calls.
- No dependency on Wi-Fi for the probe to be usable.
- No speaker-output validation.

## Candidate Runtime Inventory

| Runtime / model path | Status | Notes |
| --- | --- | --- |
| MicroPython deterministic fixture | Implemented for spike | `src/lib/inference_probe.py` returns fixed local responses and measures resource use under simulated load. |
| MicroPython tiny intent table | Candidate | Could fit if heap remains stable and controls stay responsive. No artifact is committed yet. |
| ESP-IDF native inference | Candidate fallback | Consider only if MicroPython cannot host a useful local feature or timing remains unstable. |
| Larger LLM or speech model | Deferred | Requires memory, flash, thermal, latency, license, and provenance evidence before any runtime work. |

Any future model artifact must have metadata with model ID, version, source,
license, SHA-256 checksum, and artifact size. The spike validates metadata but
does not load model binaries.

## Probe Behavior

`src/lib/inference_probe.py` provides an explicit offline probe:

- Captures heap and flash metrics when the runtime exposes them.
- Runs a bounded simulated CPU and memory workload.
- Polls the GPIO42 button when available.
- Refreshes optional display and status LED outputs.
- Runs a deterministic local prompt/response fixture.
- Produces one of three decisions:
  - `candidate_supported`
  - `defer_inference`
  - `offline_unsupported`

Run it after uploading `src/`:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import inference_probe; inference_probe.run_probe()"
```

Expected serial output includes elapsed time, iteration count, heap metrics,
button poll count, fixture response, and the decision reason.

## Captured Bench Run

Use `dev_install.sh --inference-probe` when the current application should be
uploaded, the probe evidence should be captured, and the redacted result should
be prepared as a new GitHub issue. The mode remains offline-first: it does not
configure Wi-Fi, call an endpoint, load a model, use the speaker, back up
firmware, flash firmware, or reset into the normal Wi-Fi application flow.

```bash
./dev_install.sh \
  --inference-probe \
  --gh \
  --device-label bench-a \
  --inference-check display=pass \
  --inference-check status-led=pass \
  --inference-check button=pass \
  --inference-check offline=pass \
  -- --port /dev/cu.usbmodem31101
```

The explicit `--port` is required. Each `--inference-check` accepts one of
`pass`, `fail`, or `not-observed`; checks not supplied are reported as
`not-observed`. The wrapper retains raw output locally, redacts the serial
device path, secrets, Wi-Fi values, tokens, and MAC addresses from the issue
body, then records the installer/probe statuses, decision, reason, stable
serial lines, and operator checks. `--gh OWNER/REPO` creates one new issue per
run, while a bare `--gh` resolves the configured repository or `origin`.

If `gh` is unavailable or unauthenticated, the wrapper leaves the redacted
`github-issue-body.md` under ignored `tools/.local/dev-install/` and preserves
the actual installer/probe exit status. A `defer_inference` or
`offline_unsupported` decision is recorded evidence, not a wrapper failure.

### Windows Captured Bench Run

On the Windows machine physically connected to the AIPI-Lite, use the native
Command Prompt wrapper. It runs independently and publishes the same redacted
evidence for later GitHub Issue Worker review:

```cmd
gh auth login
dev_install.cmd --inference-probe --gh bcarroll/aipi-lite --device-label bench-a --inference-check display=pass --inference-check status-led=pass --inference-check button=pass --inference-check offline=pass -- --port COM3 --yes
```

The `COM` port must be explicit. Inference mode forces a no-reset upload, then
runs the offline probe without generating Wi-Fi configuration or starting the
normal application flow. `--gh OWNER/REPO` creates a new issue; bare `--gh`
uses a GitHub `origin` remote when it can be resolved. A missing or
unauthenticated `gh` CLI leaves the redacted body in ignored
`tools\.local\dev-install\` without changing the real validation result.

## Success Criteria

The spike can proceed toward `feat/14-on-device-inference` only if a hardware
run records:

- Heap metrics are available and remain above the configured threshold.
- The simulated workload completes within the configured timing threshold.
- GPIO42 button polling remains observable during load.
- Display and LED updates remain visible when those devices are available.
- No network endpoint is required.
- No model binary is loaded without approved provenance metadata.

If the probe cannot observe heap, timing, or button responsiveness, record
`defer_inference`. If heap falls below the threshold, record
`offline_unsupported`.

## Feasibility Decision

Current decision: `defer_inference`

Reason: host-side tests validate the offline policy, fixture behavior, metadata
checks, and decision logic, but physical AIPI-Lite resource measurements have
not been captured yet.

Hardware validation still needs:

```text
AIPI-Lite Inference Feasibility Report

Date:
Operator:
Hardware model: XY006PL01
MicroPython image:
Firmware commit:
Speaker connected: no

Command:
mpremote connect /dev/cu.usbmodem31101 exec "import inference_probe; inference_probe.run_probe()"

Observed serial lines:
- elapsed_ms / iterations:
- heap_before / heap_after:
- flash_free:
- button_polls:
- button_events:
- prompt_response:
- decision:
- reason:

Visible checks:
- Display updated during load:
- GPIO46 status LED updated during load:
- GPIO42 button remained responsive:
- No Wi-Fi or endpoint required:

Decision:
- candidate_supported / defer_inference / offline_unsupported:

Follow-up actions:
```

Keep transcripts, photos, and device-specific notes under ignored local tooling
paths unless a redacted issue body is intentionally prepared.
