"""Wi-Fi and local /health probe for AIPI-Lite firmware bring-up."""

import time

from local_endpoint import EndpointPolicyError
from local_endpoint import health_url_for_endpoint
from wifi_config import load_config

STATUS_OK = "ok"
STATUS_ERROR = "error"


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


def create_wlan(network_module=None):
    """Create and activate the MicroPython station WLAN interface."""
    network_mod = _load_network_module(network_module)
    wlan = network_mod.WLAN(network_mod.STA_IF)
    wlan.active(True)
    return wlan


def connect_wifi(config, wlan=None, network_module=None, timeout_ms=15000, sleep_ms_func=sleep_ms, ticks_ms_func=ticks_ms):
    """Connect to configured Wi-Fi and return the active WLAN object."""
    if wlan is None:
        wlan = create_wlan(network_module)

    if hasattr(wlan, "isconnected") and wlan.isconnected():
        return wlan

    wlan.connect(config.ssid, config.password)
    started = ticks_ms_func()
    while hasattr(wlan, "isconnected") and not wlan.isconnected():
        if ticks_diff(ticks_ms_func(), started) >= timeout_ms:
            raise WiFiProbeError("Wi-Fi connection timed out")
        sleep_ms_func(250)
    return wlan


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
    print_func("wifi_probe: connecting to {}".format(config.ssid))

    try:
        wlan = connect_wifi(
            config,
            wlan=wlan,
            network_module=network_module,
            timeout_ms=timeout_ms,
            sleep_ms_func=sleep_ms_func,
            ticks_ms_func=ticks_ms_func,
        )
        if hasattr(wlan, "ifconfig"):
            print_func("wifi_probe: network {}".format(wlan.ifconfig()))
        result = health_check(health_url, request_get=request_get)
    except WiFiProbeError as exc:
        _set_led_state(status_led, "offline")
        _render_display(status_display, "offline")
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
