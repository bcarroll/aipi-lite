# Offline-Tolerant AIPI-Lite Startup Design

## Purpose

The AIPI-Lite must complete normal startup when the configured Wi-Fi network or
local assistant service is unavailable. Wi-Fi remains required for network
assistant exchanges, but it is not required to initialize local hardware,
render status, or enter the GPIO42 button loop.

## Scope

- Add an explicit assistant `offline` state for failed initial and
  button-initiated connection attempts.
- Add explicit LCD `OFFLINE` and `ONLINE` status screens.
- Render a small upper-right status dot as a secondary network cue: red when
  offline and green when online. The text label remains the primary accessible
  indicator.
- Retry Wi-Fi plus local `/health` only when the user presses GPIO42 while the
  assistant is offline.
- Require a second button press to start recording after a successful
  reconnect.

This change does not add cloud access, background Wi-Fi polling, credentials,
telemetry, OTA behavior, or GPIO10 board-power control.

## State and Control Flow

`PushToTalkController.connect()` will retain the existing connection and
bounded local-service health checks. Instead of re-raising a connection-phase
failure, it will log the failure type through the existing diagnostics path,
transition to `offline`, and return that state. The normal startup caller will
then create the button and begin its existing poll loop.

When `PushToTalkController.handle_button_event()` receives a press while in
`offline`, it will run `connect()` once. A successful check moves to the online
ready state but does not begin recording; the release of that reconnect press
is ignored. A failed check remains in `offline`. A subsequent press/release
pair follows the existing capture and local-service exchange path.

There is no automatic background reconnect activity while offline. Connection
failures occurring during an active capture or service exchange continue to
use the existing visible `error` behavior because those failures can be caused
by audio, protocol, or service conditions as well as network loss.

## User Interface

The assistant state mapping will render `offline` through an LCD `OFFLINE`
screen with the fixed instruction "Press button" / "to reconnect" and a red
upper-right status dot. It will render a successful ready state through an LCD
`ONLINE` screen with the existing record instruction and a green upper-right
dot. The text is always shown with the color cue so that color is never the
only status signal.

The existing physical status LED behavior remains unchanged. The LCD is the
selected offline/online indicator surface; changing the LED would conflict
with its existing red recording state.

The display must not expose exception types, credentials, SSIDs, passwords, or
endpoint details. Serial diagnostics may record the exception type only,
following the existing redaction policy.

## Validation

Host-side tests will cover:

- failed initial connection reaching the poll loop in `offline` rather than
  returning a boot error;
- correct offline and online display labels plus red/green status-dot calls;
- a failed offline reconnect press remaining offline without capturing audio;
- a successful offline reconnect press reaching ready without recording until a
  second press/release pair;
- unchanged error handling for active assistant exchanges.

Documentation will state that Wi-Fi is optional for boot and local status, but
required for network assistant exchanges. The full unit suite, installer shell
syntax checks, and `git diff --check` will run before the implementation
commit.
