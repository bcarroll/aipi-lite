"""Wi-Fi and local /health probe for AIPI-Lite firmware bring-up."""

import time

from local_endpoint import EndpointPolicyError
from local_endpoint import health_url_for_endpoint
from wifi_config import load_config
from wifi_config import offline_network_detail

STATUS_OK = "ok"
STATUS_ERROR = "error"
TRACE_HEARTBEAT_MS = 1000
INTERFACE_ACTIVATION_ATTEMPTS = 3
INTERFACE_RETRY_DELAY_MS = 500
_SAFE_ERROR_DETAILS = (
    ("Wifi Internal Error", "Wifi_Internal_Error"),
    ("Wifi Out of Memory", "Wifi_Out_of_Memory"),
)

WIFI_STATUS_NAMES = (
    ("STAT_IDLE", 0, "idle"),
    ("STAT_CONNECTING", 1, "connecting"),
    ("STAT_WRONG_PASSWORD", -3, "wrong_password"),
    ("STAT_NO_AP_FOUND", -2, "no_ap_found"),
    ("STAT_CONNECT_FAIL", -1, "connect_fail"),
    ("STAT_GOT_IP", 3, "got_ip"),
)

# Short, secret-free labels shown on the LCD for each driver status name.
WIFI_STAGE_LABELS = {
    "idle": "Idle",
    "connecting": "Associating",
    "wrong_password": "Auth failed",
    "no_ap_found": "AP not found",
    "connect_fail": "Join failed",
    "got_ip": "Got IP",
}


def _emit_stage(stage_func, label):
    """Report a human-readable connection stage without affecting serial trace."""
    if stage_func is None:
        return
    try:
        stage_func(label)
    except Exception:
        pass


def _stage_label_for_status(status_name):
    """Map a driver status name to a short LCD stage label."""
    return WIFI_STAGE_LABELS.get(status_name, "Working")


class WiFiProbeError(Exception):
    """Raised when Wi-Fi or local health probing fails."""


class HealthCheckResult:
    """Hold a local service health check result."""

    def __init__(self, ok, status_code=None, body=""):
        """Create a health check result."""
        self.ok = ok
        self.status_code = status_code
        self.body = body


def sleep_ms(milliseconds):
    """Sleep for the requested milliseconds on MicroPython or CPython."""
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(milliseconds)
        return
    time.sleep(milliseconds / 1000)


def ticks_ms():
    """Return monotonic milliseconds on MicroPython or CPython."""
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


def ticks_diff(new, old):
    """Return elapsed milliseconds on MicroPython or CPython."""
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(new, old)
    return new - old


def _load_network_module(network_module=None):
    """Return an injected or imported MicroPython network module."""
    if network_module is not None:
        return network_module
    import network

    return network


def _collect_garbage():
    """Free heap before the Wi-Fi driver's large contiguous allocation."""
    try:
        import gc

        gc.collect()
    except Exception:
        pass


def create_wlan(
    network_module=None,
    attempts=INTERFACE_ACTIVATION_ATTEMPTS,
    print_func=print,
    sleep_ms_func=sleep_ms,
    collect_garbage=_collect_garbage,
):
    """Create and activate the MicroPython station WLAN interface.

    The radio driver needs a large contiguous heap allocation, so a garbage
    collection precedes each activation and transient ``OSError`` failures
    (for example "Wifi Internal Error") are retried a bounded number of times
    before giving up. This keeps a momentarily busy or memory-starved radio
    from failing the whole connect instantly.
    """
    network_mod = _load_network_module(network_module)
    wlan = network_mod.WLAN(network_mod.STA_IF)
    total_attempts = max(1, int(attempts))
    for attempt in range(1, total_attempts + 1):
        collect_garbage()
        try:
            wlan.active(True)
            return wlan
        except OSError as exc:
            if attempt >= total_attempts:
                raise
            _emit_exception_trace(
                print_func,
                "interface_retry",
                exc,
                extra_fields=(("attempt", attempt),),
            )
            sleep_ms_func(INTERFACE_RETRY_DELAY_MS)
    return wlan


def _emit_trace(print_func, phase, fields=()):
    """Print one stable Wi-Fi trace line without affecting connection behavior."""
    parts = ["wifi_trace", "phase={}".format(phase)]
    for key, value in fields:
        parts.append("{}={}".format(key, value))
    try:
        print_func(" ".join(parts))
    except Exception:
        pass


def _numeric_error(error):
    """Return a numeric exception code without exposing arbitrary error text."""
    error_number = getattr(error, "errno", None)
    if isinstance(error_number, int):
        return error_number
    arguments = getattr(error, "args", ())
    if arguments and isinstance(arguments[0], int):
        return arguments[0]
    return None


def _config_secrets(config):
    """Return the configured values that must never leak into trace output."""
    return (
        getattr(config, "ssid", ""),
        getattr(config, "password", ""),
        getattr(config, "local_service_url", ""),
    )


def _error_detail(error, redact=()):
    """Return a constant label only for an allowlisted driver exception.

    Driver errors like "Wifi Internal Error" carry no numeric ``errno``. Known
    constant messages retain a useful label, while arbitrary exception text is
    omitted so credentials and local service details cannot enter trace output.
    """
    arguments = getattr(error, "args", ())
    text = str(arguments[0]) if arguments else str(error)
    if not text:
        return None
    for secret in redact:
        secret_text = str(secret)
        if secret_text:
            text = text.replace(secret_text, "***")
    for known_message, detail_label in _SAFE_ERROR_DETAILS:
        if text == known_message:
            return detail_label
    return None


def _emit_exception_trace(print_func, operation, error, redact=(), extra_fields=()):
    """Trace an exception type with a numeric code or a redacted detail token."""
    fields = [("operation", operation), ("error_type", type(error).__name__)]
    error_number = _numeric_error(error)
    if error_number is not None:
        fields.append(("errno", error_number))
    else:
        detail = _error_detail(error, redact)
        if detail is not None:
            fields.append(("detail", detail))
    fields.extend(extra_fields)
    _emit_trace(print_func, "exception", fields)


def _status_name(network_module, status_code):
    """Map a MicroPython WLAN status code to a stable trace name."""
    for constant_name, fallback_code, trace_name in WIFI_STATUS_NAMES:
        expected_code = fallback_code
        if network_module is not None and hasattr(network_module, constant_name):
            expected_code = getattr(network_module, constant_name)
        if status_code == expected_code:
            return trace_name
    return "unknown"


def _read_wlan_status(wlan, network_module, print_func, status_enabled=True):
    """Return a best-effort WLAN status code, name, and future-read flag."""
    if not status_enabled or not hasattr(wlan, "status"):
        return None, "unavailable", False
    try:
        status_code = wlan.status()
    except Exception as exc:
        _emit_exception_trace(print_func, "status", exc)
        return None, "unavailable", False
    return status_code, _status_name(network_module, status_code), True


def _active_trace_value(wlan, created, print_func):
    """Return the known or inspected active state for interface tracing."""
    if created:
        return 1
    if not hasattr(wlan, "active"):
        return "unavailable"
    try:
        return int(bool(wlan.active()))
    except Exception as exc:
        _emit_exception_trace(print_func, "active_status", exc)
        return "unavailable"


def _is_connected(wlan, print_func):
    """Return the current WLAN connection state and trace inspection errors."""
    try:
        return bool(hasattr(wlan, "isconnected") and wlan.isconnected())
    except Exception as exc:
        _emit_exception_trace(print_func, "isconnected", exc)
        raise


def _ifconfig_trace_fields(wlan, print_func):
    """Return bounded local IP fields while keeping inspection nonfatal."""
    if not hasattr(wlan, "ifconfig"):
        _emit_trace(
            print_func,
            "exception",
            (("operation", "ifconfig"), ("error_type", "AttributeError")),
        )
        return []
    try:
        network_config = wlan.ifconfig()
    except Exception as exc:
        _emit_exception_trace(print_func, "ifconfig", exc)
        return []
    if not isinstance(network_config, (tuple, list)) or len(network_config) != 4:
        _emit_trace(
            print_func,
            "exception",
            (("operation", "ifconfig"), ("error_type", "ValueError")),
        )
        return []
    return [
        ("ip", network_config[0]),
        ("netmask", network_config[1]),
        ("gateway", network_config[2]),
        ("dns", network_config[3]),
    ]


def _connected_trace_fields(elapsed_ms, status_code, status_name, wlan, print_func):
    """Build the successful connection trace fields with local IP details."""
    fields = [
        ("elapsed_ms", elapsed_ms),
        ("connected", 1),
        ("status", status_name),
        ("status_code", status_code if status_code is not None else "unavailable"),
    ]
    fields.extend(_ifconfig_trace_fields(wlan, print_func))
    return fields


def connect_wifi(
    config,
    wlan=None,
    network_module=None,
    timeout_ms=15000,
    print_func=print,
    sleep_ms_func=sleep_ms,
    ticks_ms_func=ticks_ms,
    stage_func=None,
    skip_check=None,
):
    """Connect to configured Wi-Fi and return the active WLAN object.

    ``stage_func`` is an optional callback that receives short, secret-free stage
    labels (for example "Starting radio", "Associating", "Got IP") so callers can
    show connection progress on a display. It never receives credentials.

    ``skip_check`` is an optional callable polled during the connection wait; when
    it returns True the wait is abandoned and ``WiFiProbeError`` is raised so the
    caller can move on instead of waiting out the timeout.
    """
    started = ticks_ms_func()
    _emit_trace(print_func, "start", (("timeout_ms", timeout_ms),))
    _emit_stage(stage_func, "Starting radio")

    created = wlan is None
    active_network_module = network_module
    try:
        if created:
            active_network_module = _load_network_module(network_module)
            wlan = create_wlan(
                active_network_module,
                print_func=print_func,
                sleep_ms_func=sleep_ms_func,
            )
        elif active_network_module is None:
            try:
                active_network_module = _load_network_module()
            except Exception:
                active_network_module = None
    except Exception as exc:
        _emit_exception_trace(print_func, "interface", exc, redact=_config_secrets(config))
        _emit_stage(stage_func, "Radio error")
        raise

    _emit_trace(
        print_func,
        "interface",
        (("active", _active_trace_value(wlan, created, print_func)),),
    )
    _emit_stage(stage_func, "Radio ready")

    connected = _is_connected(wlan, print_func)
    status_enabled = True
    if connected:
        status_code, status_name, status_enabled = _read_wlan_status(
            wlan,
            active_network_module,
            print_func,
            status_enabled,
        )
        _emit_trace(
            print_func,
            "status",
            (
                ("elapsed_ms", 0),
                ("connected", 1),
                ("status", status_name),
                ("status_code", status_code if status_code is not None else "unavailable"),
            ),
        )
        _emit_trace(
            print_func,
            "connected",
            _connected_trace_fields(0, status_code, status_name, wlan, print_func),
        )
        _emit_stage(stage_func, "Connected")
        return wlan

    try:
        wlan.connect(config.ssid, config.password)
    except Exception as exc:
        _emit_exception_trace(print_func, "connect", exc, redact=_config_secrets(config))
        _emit_stage(stage_func, "Join failed")
        raise
    credentials_present = int(bool(config.ssid) and bool(config.password))
    _emit_trace(
        print_func,
        "connect_requested",
        (("credentials_present", credentials_present),),
    )
    _emit_stage(stage_func, "Requesting join")

    last_status_key = None
    last_status_trace_ms = None
    while True:
        if skip_check is not None and skip_check():
            _emit_trace(print_func, "skipped", (("elapsed_ms", ticks_diff(ticks_ms_func(), started)),))
            _emit_stage(stage_func, "Skipped")
            raise WiFiProbeError("Wi-Fi connection skipped")
        connected = _is_connected(wlan, print_func)
        elapsed_ms = ticks_diff(ticks_ms_func(), started)
        status_code, status_name, status_enabled = _read_wlan_status(
            wlan,
            active_network_module,
            print_func,
            status_enabled,
        )
        status_key = (connected, status_code, status_name)
        status_changed = status_key != last_status_key
        heartbeat_due = (
            last_status_trace_ms is None
            or ticks_diff(elapsed_ms, last_status_trace_ms) >= TRACE_HEARTBEAT_MS
        )
        if status_changed or heartbeat_due:
            _emit_trace(
                print_func,
                "status",
                (
                    ("elapsed_ms", elapsed_ms),
                    ("connected", int(connected)),
                    ("status", status_name),
                    ("status_code", status_code if status_code is not None else "unavailable"),
                ),
            )
            if status_changed and not connected:
                _emit_stage(stage_func, _stage_label_for_status(status_name))
            last_status_key = status_key
            last_status_trace_ms = elapsed_ms

        if connected:
            _emit_trace(
                print_func,
                "connected",
                _connected_trace_fields(
                    elapsed_ms,
                    status_code,
                    status_name,
                    wlan,
                    print_func,
                ),
            )
            _emit_stage(stage_func, "Connected")
            return wlan
        if elapsed_ms >= timeout_ms:
            _emit_trace(
                print_func,
                "timeout",
                (
                    ("elapsed_ms", elapsed_ms),
                    ("connected", 0),
                    ("status", status_name),
                    ("status_code", status_code if status_code is not None else "unavailable"),
                ),
            )
            _emit_stage(stage_func, "Timed out")
            raise WiFiProbeError("Wi-Fi connection timed out")
        sleep_ms_func(250)


def _load_request_get(request_get=None):
    """Return an injected or imported HTTP GET callable."""
    if request_get is not None:
        return request_get
    try:
        import urequests

        return urequests.get
    except ImportError:
        import requests

        return requests.get


def health_check(health_url, request_get=None):
    """Call the validated local health URL and return a HealthCheckResult."""
    get = _load_request_get(request_get)
    response = get(health_url)
    try:
        status_code = getattr(response, "status_code", getattr(response, "status", None))
        body = ""
        if hasattr(response, "text"):
            body = response.text
        ok = 200 <= int(status_code) < 300
        return HealthCheckResult(ok, status_code, body)
    finally:
        if hasattr(response, "close"):
            response.close()


def _create_status_led():
    """Return a status LED when available, otherwise None."""
    try:
        from status_led import StatusLed

        return StatusLed()
    except Exception:
        return None


def _create_status_display():
    """Return a status display when available, otherwise None."""
    try:
        from display import create_status_display

        return create_status_display()
    except Exception:
        return None


def _set_led_state(status_led, state):
    """Set the status LED when one is available."""
    if status_led is not None:
        status_led.set_state(state)


def _render_display(status_display, status, detail=None):
    """Render a display status when one is available."""
    if status_display is not None:
        status_display.render_status(status, detail=detail)


def run_probe(
    config=None,
    config_loader=load_config,
    approved_hosts=None,
    wlan=None,
    network_module=None,
    request_get=None,
    status_led=None,
    status_display=None,
    print_func=print,
    sleep_ms_func=sleep_ms,
    ticks_ms_func=ticks_ms,
    timeout_ms=15000,
):
    """Connect Wi-Fi, call local /health, and report status to serial/UI."""
    print_func("wifi_probe: starting local Wi-Fi probe")
    if config is None:
        config = config_loader()

    if approved_hosts is None:
        approved_hosts = config.approved_hosts

    try:
        health_url = health_url_for_endpoint(config.local_service_url, approved_hosts)
    except EndpointPolicyError as exc:
        print_func("wifi_probe: endpoint rejected: {}".format(exc))
        _set_led_state(status_led or _create_status_led(), "error")
        _render_display(status_display or _create_status_display(), "error", "endpoint rejected")
        return STATUS_ERROR

    if status_led is None:
        status_led = _create_status_led()
    if status_display is None:
        status_display = _create_status_display()

    _set_led_state(status_led, "connecting")
    _render_display(status_display, "wifi", "connecting")
    print_func("wifi_probe: endpoint accepted {}".format(health_url))
    print_func("wifi_probe: connecting to configured local network")

    try:
        wlan = connect_wifi(
            config,
            wlan=wlan,
            network_module=network_module,
            timeout_ms=timeout_ms,
            print_func=print_func,
            sleep_ms_func=sleep_ms_func,
            ticks_ms_func=ticks_ms_func,
        )
        if hasattr(wlan, "ifconfig"):
            print_func("wifi_probe: network {}".format(wlan.ifconfig()))
        result = health_check(health_url, request_get=request_get)
    except WiFiProbeError as exc:
        _set_led_state(status_led, "offline")
        _render_display(status_display, "offline", offline_network_detail(config.ssid))
        print_func("wifi_probe: offline: {}".format(type(exc).__name__))
        return STATUS_ERROR
    except Exception as exc:
        _set_led_state(status_led, "error")
        _render_display(status_display, "error", type(exc).__name__)
        print_func("wifi_probe: failed: {}".format(type(exc).__name__))
        return STATUS_ERROR

    if result.ok:
        _set_led_state(status_led, "ready")
        _render_display(status_display, "ready", "health {}".format(result.status_code))
        print_func("wifi_probe: health ok {}".format(result.status_code))
        return STATUS_OK

    _set_led_state(status_led, "error")
    _render_display(status_display, "error", "health {}".format(result.status_code))
    print_func("wifi_probe: health failed {}".format(result.status_code))
    return STATUS_ERROR


if __name__ == "__main__":
    run_probe()
