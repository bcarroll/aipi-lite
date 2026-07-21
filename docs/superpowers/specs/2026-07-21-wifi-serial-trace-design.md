# Always-On Wi-Fi Serial Trace Design

**Date:** 2026-07-21
**Status:** Approved

## Goal

Add always-on, bounded, redacted serial trace output to the normal Wi-Fi
connection path so an operator can distinguish interface setup, connection
progress, timeout, driver status, exceptions, and DHCP completion without
exposing credentials or changing the device's connection policy.

## Current Behavior

Normal startup creates a `DiagnosticsLog`, builds a `ReconnectManager`, and
calls `wifi_probe.connect_wifi()` before checking the local service. The
reconnect manager currently records only a generic reconnect event, and a
connection failure is reduced to its exception type. `connect_wifi()` waits up
to 15 seconds for `WLAN.isconnected()` but does not expose `WLAN.status()` or
elapsed connection progress to serial.

The explicit `wifi_probe.run_probe()` command prints high-level progress and
the network configuration after a successful connection, but it also lacks the
bounded status trace needed to diagnose a failing connection.

## Chosen Approach

Instrument `wifi_probe.connect_wifi()` because it is the shared connection
boundary used by normal boot, reconnect attempts, and the explicit Wi-Fi probe.
The connector will accept an injectable `print_func` and emit the same stable
trace format for each caller. Normal startup and `run_probe()` will pass their
existing serial output function into the connector so tests and device output
follow the same path.

Tracing is always enabled. There is no configuration flag, new production
dependency, persistent trace file, telemetry, or network upload.

## Serial Trace Contract

Each trace line begins with `wifi_trace` and contains space-separated
`key=value` fields. Fields remain single-line and use stable lowercase names so
operators can read them directly or filter them with simple tools.

The connection lifecycle emits:

1. `phase=start` with the configured timeout.
2. `phase=interface` after the station interface is created or reused and
   activated.
3. `phase=connect_requested` after `WLAN.connect()` accepts the request.
4. `phase=status` immediately for a new driver status and at most once per
   second while the same status continues.
5. `phase=connected` with elapsed time, final driver status, and `ifconfig()`
   values after a valid IP configuration is available.
6. `phase=timeout` with elapsed time and the final observed connection state.
7. `phase=exception` when interface activation, connection, status inspection,
   or configuration inspection raises an exception.

Example timeout output:

```text
wifi_trace phase=start timeout_ms=15000
wifi_trace phase=interface active=1
wifi_trace phase=connect_requested credentials_present=1
wifi_trace phase=status elapsed_ms=0 connected=0 status=connecting status_code=1
wifi_trace phase=status elapsed_ms=1000 connected=0 status=connecting status_code=1
wifi_trace phase=timeout elapsed_ms=15000 connected=0 status=connecting status_code=1
```

If a supplied WLAN is already connected, the connector emits `start`,
`interface`, one `status`, and `connected` without calling `WLAN.connect()` or
emitting `connect_requested`. A successful `connected` line uses the explicit
fields `ip`, `netmask`, `gateway`, and `dns` when `ifconfig()` returns the normal
four-value tuple.

The trace maps values exposed by the active MicroPython `network` module to the
standard names `idle`, `connecting`, `wrong_password`, `no_ap_found`,
`connect_fail`, and `got_ip`. An unknown numeric value is reported as `unknown`
while retaining its numeric code. If the runtime does not provide
`WLAN.status()`, the trace reports `unavailable` and connection behavior
continues unchanged.

The ESP32 port may continue reporting `connecting` while its driver retries
authentication or access-point discovery. The bounded heartbeat makes that
condition visible without claiming a more specific cause than the runtime
reports.

## Redaction and Local-Only Boundaries

Trace output must never include:

- Wi-Fi password or any derived representation of it.
- SSID value.
- Local service URL or approved hostname values.
- MAC address, BSSID, or device identifier.
- Nearby access-point names or scan results.
- Arbitrary exception strings that could contain configuration values.

`credentials_present=1` indicates only that non-empty SSID and password values
were supplied. Exception traces include the exception type and a numeric error
code when one is available. They do not include `str(exception)` or arbitrary
exception arguments. Successful `ifconfig()` output may include only the local
IP address, netmask, gateway, and DNS address already returned by MicroPython.
The trace remains serial-only and is not persisted or transmitted.

## Error Handling and Compatibility

The existing 15-second timeout and `WiFiProbeError` behavior remain intact.
Normal startup must continue to enter the recoverable offline state when Wi-Fi
cannot connect. The explicit probe must continue returning its existing failed
status and rendering the normal offline UI for a timeout.

Trace inspection is best effort. Missing or failing `status()` and `ifconfig()`
inspection is reported with `phase=exception`, an `operation` field, the
exception type, and a numeric error when available. These inspection failures
do not replace a successful connection or the primary timeout result. Failure
to create or activate the station interface or call `connect()` remains a
primary connection failure after its trace line is emitted. Trace formatting
must remain compatible with MicroPython and CPython; it will not depend on
`logging`, `inspect`, dataclasses, or a new package.

No active Wi-Fi scan will be added. Scanning changes radio behavior, exposes
nearby network metadata, and can misdiagnose hidden networks. This change
reports only the state already available from the connection attempt.

## Testing

Host-side tests will cover:

- Station interface activation and the connection request still use the
  configured credentials without printing their values.
- Known MicroPython status constants map to stable trace names.
- Unknown and unavailable statuses remain nonfatal and visible.
- Status changes print immediately while unchanged status heartbeats are
  limited to once per second.
- Timeout output includes elapsed time, final status name/code, and connection
  state before `WiFiProbeError` is raised.
- Connection and status exceptions include only type and numeric error data.
- Successful connection output includes the bounded `ifconfig()` tuple.
- Normal startup and the explicit probe route traces through their injected
  serial `print_func`.
- Password, SSID, service URL, MAC/BSSID, and arbitrary exception text are
  absent from captured output.

The complete repository regression suite, shell syntax checks, and
`git diff --check` will run before the implementation commit.

## Documentation

Update `README.md` and `src/README.md` with the always-on trace format, redaction
guarantees, status meanings, and an example timeout. Update `FIRMWARE_IMPL.md`
to record the diagnostic behavior while keeping physical Wi-Fi validation
pending until device output is captured.

## Success Criteria

- Every normal boot and reconnect attempt produces bounded Wi-Fi trace output
  on the active serial stream.
- The final trace identifies the last driver-reported state and numeric code,
  or explicitly reports that status is unavailable.
- Failed connections preserve current timeout and offline recovery behavior.
- Captured trace output contains no credential values or nearby network data.
- Host-side regression tests and repository checks pass.
