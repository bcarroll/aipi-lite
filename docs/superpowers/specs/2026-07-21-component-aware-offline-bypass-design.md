# Component-Aware OFFLINE Screen and Long-Press Bypass Design

Date: 2026-07-21
Status: Approved for implementation planning

## Summary

Replace the current single-cause `OFFLINE` presentation with a component-aware
connectivity screen for Wi-Fi and the configured local service. The GPIO42 right
function button will retain its push-to-talk behavior while fully online. While
offline, a short press will retry only the first offline component and a
two-second hold will bypass the blocking screen into a limited mode.

The design remains local-only. It does not add cloud endpoints, telemetry,
background connectivity polling, new production dependencies, or control of the
unverified left/power button.

## Goals

- Show independent `ONLINE` or `OFFLINE` status for Wi-Fi and the local service.
- Pair component graphics and status graphics with explicit text so color is not
  the only status indicator.
- Retry the first offline dependency with a short GPIO42 press.
- Bypass the blocking `OFFLINE` screen with a two-second GPIO42 hold.
- Keep the device responsive in a limited mode without falsely claiming that
  push-to-talk is available.
- Preserve existing push-to-talk press/release behavior when both dependencies
  are online.
- Preserve local-only endpoint enforcement, bounded retry behavior, safe GPIO10
  handling, serial diagnostics, and Wi-Fi tracing.

## Non-Goals

- Do not read or assign the left/power button; its application GPIO behavior is
  not hardware-validated.
- Do not retry connectivity automatically every 15 seconds. GPIO42 has no
  competing application action while connectivity blocks push-to-talk, so
  recovery remains operator-triggered.
- Do not allow recording or service requests while limited.
- Do not display the SSID, service URL, credentials, approved hostnames, or
  arbitrary exception messages on the LCD.
- Do not add an offline assistant, on-device inference routing, or another
  user-facing application mode.
- Do not change firmware flashing, recovery, or installer defaults.

## Component Status Model

The assistant will maintain a structured connectivity status with two Boolean
values:

1. `wifi_online`
2. `service_online`

Wi-Fi is the first dependency. The service cannot be online when Wi-Fi is
offline. Whenever Wi-Fi becomes offline, the service is also marked offline.

The status outcomes are deterministic:

| Outcome | Wi-Fi | Local service |
| --- | --- | --- |
| Missing or invalid local configuration | `OFFLINE` | `OFFLINE` |
| Wi-Fi connection failure | `OFFLINE` | `OFFLINE` |
| Wi-Fi succeeds; `/health` fails | `ONLINE` | `OFFLINE` |
| Wi-Fi and `/health` succeed | `ONLINE` | `ONLINE` |

The first offline component is Wi-Fi when `wifi_online` is false. Otherwise it
is the local service when `service_online` is false. There is no retry target
when both values are true.

## Startup and Retry Flow

Normal startup continues to attempt the dependencies in order:

1. Validate the ignored local configuration and local-only endpoint policy.
2. Connect Wi-Fi.
3. Call the local service `GET /health` endpoint.
4. Enter `READY` only after both components succeed.

If startup stops on a failure, the component status is rendered and the button
loop remains active.

A short offline press retries exactly one component:

- If Wi-Fi is offline, reconnect Wi-Fi. A successful retry marks Wi-Fi online
  but leaves the service offline; a later short press retries the service.
- If Wi-Fi is online and the service is offline, call `/health` without
  reconnecting an already-connected WLAN.
- If the retry produces two online components, transition immediately to
  `READY` and render the normal `ONLINE` screen.

The same retry rules apply in limited mode. No periodic background retry loop is
added.

## Button Event Design

`src/lib/button.py` will add one debounced long-press event. The default threshold
is 2,000 milliseconds measured from the debounced press transition with
MicroPython-safe `ticks_diff()` arithmetic.

The button emits the long-press event once per physical hold. Releasing after a
long press still emits the normal release event, but the controller records that
the hold was consumed so the release does not also trigger a retry.

State-specific behavior is:

| Assistant state | Press behavior | Release behavior | Long-press behavior |
| --- | --- | --- | --- |
| `READY` | Begin recording | Complete the push-to-talk exchange | Ignored; a long hold remains a long recording |
| `OFFLINE` | Arm gesture classification | Retry first offline component when hold was shorter than two seconds | Enter `LIMITED` once, without retrying |
| `LIMITED` | Arm gesture classification | Retry first offline component when hold was shorter than two seconds | Ignored because bypass already occurred |

The existing 50-millisecond debounce behavior remains unchanged. The long-press
threshold is independently configurable for host tests but defaults to two
seconds on the device.

## Assistant States and Output Routing

Add a `LIMITED` assistant state. It maps to the existing conservative offline
LED treatment and a dedicated LCD presentation. `READY` remains the only state
that accepts push-to-talk recording.

The controller owns connectivity transitions. The state/output layer receives a
structured component-status snapshot with `OFFLINE` and `LIMITED` transitions so
serial, LED, and display output remain coordinated from one state source.

Serial diagnostics will identify the failed stage and exception type, such as a
Wi-Fi connection failure or service health failure. They will not print
credentials, SSIDs, service URLs, approved hostnames, or arbitrary exception
text. Existing `wifi_trace` output remains unchanged.

## LCD Design

The approved layout is the fixed-row status list shown as layout A in the visual
design review. The rows never reorder, so operators can scan the same positions
across updates.

The `OFFLINE` screen contains:

- Title: `OFFLINE`
- Wi-Fi graphic, `WI-FI`, status badge, and `ONLINE` or `OFFLINE`
- Service graphic, `SERVICE`, status badge, and `ONLINE` or `OFFLINE`
- Context action: `Tap: Retry Wi-Fi` or `Tap: Retry service`
- Bypass action: `Hold 2s: Bypass`

The `LIMITED` screen contains:

- Title: `LIMITED`
- The same two fixed component rows
- `PTT unavailable`
- The same component-specific short-press retry instruction

The renderer will draw the Wi-Fi, service, check, and cross graphics with the
existing ST7735 line, rectangle, circle, and filled-circle primitives. It will
not add bitmap assets or another graphics dependency. Green and red reinforce
status, while the check/cross shapes and `ONLINE`/`OFFLINE` text provide
non-color indicators. Text and graphics must remain inside the 128 x 128 display
bounds.

When both components become online, the display returns to the existing
`ONLINE`/ready screen. The LCD does not show local network identifiers or
endpoint details.

## Implementation Boundaries

Expected localized changes are:

- `src/lib/button.py`: two-second, once-per-hold long-press event generation.
- `src/lib/assistant_state.py`: `LIMITED` state and structured connectivity
  status/output support.
- `src/lib/push_to_talk.py`: staged component tracking, one-component retry,
  offline gesture classification, limited-mode behavior, and ready recovery.
- `src/lib/display.py`: component-row graphics and bounded `OFFLINE`/`LIMITED`
  layouts.
- `src/main.py`: startup messages only if needed to describe the new limited
  state without changing safe boot behavior.
- Existing focused host tests for buttons, display, push-to-talk, and startup.
- `README.md`, `src/README.md`, `FIRMWARE_PLAN.md`, and `FIRMWARE_IMPL.md` for
  user workflow, architecture, and status updates.

No production package or external firmware asset is required.

## Error Handling

- Missing configuration fails closed with both components offline.
- Wi-Fi failure prevents a service request and marks both components offline.
- Service failure preserves the successful Wi-Fi status.
- A failed short-press retry remains in the current `OFFLINE` or `LIMITED` mode
  and refreshes the component rows.
- A successful Wi-Fi-only retry does not silently retry the service in the same
  gesture.
- A long-press bypass never marks either component online and never starts
  recording.
- Unexpected exchange failures after `READY` continue to use the existing
  recoverable error path.

## Testing

Host-side Python tests will cover:

- Debounced short press and release behavior.
- A two-second hold and configurable threshold.
- Tick wraparound-safe duration measurement.
- Only one long-press event per physical hold.
- Release after a consumed long press does not trigger a retry.
- Existing ready-state push-to-talk behavior, including long recordings.
- Initial missing-configuration, Wi-Fi-failure, and service-failure status.
- Fixed Wi-Fi-before-service retry ordering.
- Exactly one component retried per short press.
- Bypass into `LIMITED` without connectivity or capture side effects.
- Push-to-talk disabled while limited.
- Successful limited/offline recovery into `READY`.
- Fixed LCD row order, icon drawing, explicit status text, action text, and
  128 x 128 bounds.
- No sensitive configuration values in LCD or serial output.

Every generated or changed Python method will retain a docstring. Verification
before commit will run:

```bash
python3 -m unittest discover -s tests -v
bash -n install.sh
bash -n tools/setup_micropython_tools.sh
git diff --check
```

Physical confirmation of the two-second hold, icon readability, component status
accuracy, and ready recovery will remain explicitly pending until tested on an
AIPI-Lite device.

## Documentation and Compliance

Documentation will explain the short-press retry, two-second bypass, limited-mode
restrictions, component status meanings, and hardware-validation status. The
screen uses redundant graphics, text, and color cues to support accessible
interpretation. Implementation must retain the repository's U.S. Federal
requirements posture, local-only service boundary, least-data display behavior,
and prohibition on storing credentials or device tokens in Git.
