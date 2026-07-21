"""Tests for local Wi-Fi configuration, endpoint policy, and health probing."""

import importlib
from pathlib import Path
import sys
import types
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
SRC_LIB_ROOT = SRC_ROOT / "lib"

MODULES_TO_CLEAR = ("local_endpoint", "wifi_config", "wifi_probe", "network", "requests", "urequests")


def clear_imported_modules():
    """Remove firmware modules imported by these Wi-Fi tests."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    for source_root in (SRC_ROOT, SRC_LIB_ROOT):
        source_path = str(source_root)
        if source_path not in sys.path:
            sys.path.insert(0, source_path)


class FakeWLAN:
    """Test double for MicroPython station WLAN."""

    def __init__(
        self,
        connected_after=1,
        statuses=None,
        connect_error=None,
        status_error=None,
        ifconfig_values=None,
        ifconfig_error=None,
    ):
        """Create a fake WLAN that connects after a fixed poll count."""
        self.active_values = []
        self.connect_calls = []
        self.connected_after = connected_after
        self.polls = 0
        self.statuses = list(statuses or ())
        self.status_calls = 0
        self.connect_error = connect_error
        self.status_error = status_error
        self.ifconfig_error = ifconfig_error
        self.active_state = True
        self.ifconfig_values = ifconfig_values or (
            "192.168.1.44",
            "255.255.255.0",
            "192.168.1.1",
            "192.168.1.1",
        )

    def active(self, enabled=None):
        """Record or return the fake interface active state."""
        if enabled is None:
            return self.active_state
        self.active_state = bool(enabled)
        self.active_values.append(enabled)

    def connect(self, ssid, password):
        """Record Wi-Fi connection credentials without logging the password."""
        self.connect_calls.append((ssid, password))
        if self.connect_error is not None:
            raise self.connect_error

    def isconnected(self):
        """Return connected after the configured number of polls."""
        self.polls += 1
        return self.polls > self.connected_after

    def ifconfig(self):
        """Return a fake network tuple."""
        if self.ifconfig_error is not None:
            raise self.ifconfig_error
        return self.ifconfig_values

    def status(self):
        """Return an injected status or derive one from connection progress."""
        if self.status_error is not None:
            raise self.status_error
        if self.statuses:
            index = min(self.status_calls, len(self.statuses) - 1)
            self.status_calls += 1
            return self.statuses[index]
        if self.polls > self.connected_after:
            return FakeNetwork.STAT_GOT_IP
        return FakeNetwork.STAT_CONNECTING


class FakeNetwork(types.ModuleType):
    """Test double for MicroPython's network module."""

    STA_IF = "STA_IF"
    STAT_IDLE = 0
    STAT_CONNECTING = 1
    STAT_WRONG_PASSWORD = -3
    STAT_NO_AP_FOUND = -2
    STAT_CONNECT_FAIL = -1
    STAT_GOT_IP = 3

    def __init__(self, wlan):
        """Create a fake network module that returns the supplied WLAN."""
        super().__init__("network")
        self.wlan = wlan
        self.calls = []

    def WLAN(self, interface):
        """Return the fake WLAN and record the requested interface."""
        self.calls.append(interface)
        return self.wlan


class FakeResponse:
    """Test double for a urequests/requests response."""

    def __init__(self, status_code=200, text="ok"):
        """Create a fake HTTP response."""
        self.status_code = status_code
        self.text = text
        self.closed = False

    def close(self):
        """Record that the response was closed."""
        self.closed = True


class FakeStatusLed:
    """Record status LED state transitions."""

    def __init__(self):
        """Create a fake status LED."""
        self.states = []

    def set_state(self, state):
        """Record a requested LED state."""
        self.states.append(state)


class FakeStatusDisplay:
    """Record display status renders."""

    def __init__(self):
        """Create a fake display recorder."""
        self.screens = []

    def render_status(self, status, detail=None):
        """Record a requested display screen."""
        self.screens.append((status, detail))


class WifiPolicyTests(unittest.TestCase):
    """Validate Wi-Fi policy and health probe behavior without hardware."""

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def import_module(self, name):
        """Import a firmware module with src on sys.path."""
        ensure_src_path()
        return importlib.import_module(name)

    def test_endpoint_policy_accepts_local_addresses(self):
        """Local endpoint policy should accept private, loopback, link-local, and mDNS hosts."""
        endpoint = self.import_module("local_endpoint")

        accepted = (
            "http://10.1.2.3:8080",
            "http://172.16.0.9",
            "http://172.31.255.254/service",
            "http://192.168.1.20",
            "http://127.0.0.1:5000",
            "http://169.254.10.20",
            "http://assistant.local:8080",
        )

        for url in accepted:
            self.assertEqual(endpoint.validate_local_endpoint(url).scheme, "http")

    def test_endpoint_policy_rejects_public_and_malformed_urls(self):
        """Local endpoint policy should reject public or malformed endpoints by default."""
        endpoint = self.import_module("local_endpoint")

        rejected = (
            "https://example.com",
            "http://8.8.8.8",
            "ftp://192.168.1.2",
            "http://user:pass@192.168.1.2",
            "http://192.168.1.2?token=secret",
            "192.168.1.2",
        )

        for url in rejected:
            with self.assertRaises(endpoint.EndpointPolicyError):
                endpoint.validate_local_endpoint(url)

    def test_endpoint_policy_allows_operator_approved_hostname(self):
        """Operator-approved hostnames should pass policy exactly."""
        endpoint = self.import_module("local_endpoint")

        parsed = endpoint.validate_local_endpoint(
            "http://assistant.lan:8080/api",
            approved_hosts=("assistant.lan",),
        )

        self.assertEqual(parsed.host, "assistant.lan")
        self.assertEqual(endpoint.health_url_for_endpoint("http://assistant.lan:8080/api", ("assistant.lan",)), "http://assistant.lan:8080/api/health")

    def test_wifi_config_loads_ignored_local_module(self):
        """Wi-Fi config loader should read the expected local module fields."""
        wifi_config = self.import_module("wifi_config")
        module = types.SimpleNamespace(
            WIFI_SSID="LabNet",
            WIFI_PASSWORD="secret-password",
            LOCAL_SERVICE_URL="http://192.168.1.10:8080",
            APPROVED_LOCAL_HOSTS=("assistant.lan",),
        )

        config = wifi_config.load_config(importer=lambda name: module)

        self.assertEqual(config.ssid, "LabNet")
        self.assertEqual(config.password, "secret-password")
        self.assertEqual(config.local_service_url, "http://192.168.1.10:8080")
        self.assertEqual(config.approved_hosts, ("assistant.lan",))
        self.assertNotIn("password", config.as_dict())

    def test_wifi_config_requires_credentials_and_service_url(self):
        """Wi-Fi config loader should fail closed when required values are missing."""
        wifi_config = self.import_module("wifi_config")

        with self.assertRaises(wifi_config.WiFiConfigError):
            wifi_config.config_from_mapping({"ssid": "LabNet", "password": "", "local_service_url": "http://192.168.1.2"})

        with self.assertRaises(wifi_config.WiFiConfigError):
            wifi_config.load_config(importer=lambda name: (_ for _ in ()).throw(ImportError(name)))

    def test_offline_network_detail_names_ssid_or_reports_missing_configuration(self):
        """The offline LCD note should expose only the configured network name."""
        wifi_config = self.import_module("wifi_config")

        self.assertEqual(wifi_config.offline_network_detail("LabNet"), "Wi-Fi: LabNet")
        self.assertEqual(wifi_config.offline_network_detail("  "), "Wi-Fi not configured")
        self.assertEqual(wifi_config.offline_network_detail(), "Wi-Fi not configured")

    def test_wifi_config_reports_available_module_names_when_ssid_is_missing(self):
        """Wi-Fi config errors should show imported config names without values."""
        wifi_config = self.import_module("wifi_config")
        module = types.SimpleNamespace(
            WIFI_PASSWORD="secret-password",
            LOCAL_SERVICE_URL="http://192.168.1.10:8080",
        )
        module.__name__ = "local_wifi_config"

        with self.assertRaises(wifi_config.WiFiConfigError) as context:
            wifi_config.config_from_module(module)

        message = str(context.exception)
        self.assertIn("missing ssid in local_wifi_config", message)
        self.assertIn("expected one of WIFI_SSID, SSID", message)
        self.assertIn("LOCAL_SERVICE_URL", message)
        self.assertIn("WIFI_PASSWORD", message)
        self.assertNotIn("secret-password", message)
        self.assertNotIn("192.168.1.10", message)

    def test_connect_wifi_uses_station_interface_and_credentials(self):
        """connect_wifi should activate station mode and connect with configured values."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig("LabNet", "secret-password", "http://192.168.1.10")
        wlan = FakeWLAN(connected_after=2)
        network = FakeNetwork(wlan)
        sleeps = []
        messages = []
        ticks = iter((0, 100, 200))

        connected = wifi_probe.connect_wifi(
            config,
            network_module=network,
            print_func=messages.append,
            sleep_ms_func=sleeps.append,
            ticks_ms_func=lambda: next(ticks),
        )

        self.assertIs(connected, wlan)
        self.assertEqual(network.calls, ["STA_IF"])
        self.assertEqual(wlan.active_values, [True])
        self.assertEqual(wlan.connect_calls, [("LabNet", "secret-password")])
        self.assertEqual(sleeps, [250])
        self.assertIn("wifi_trace phase=start timeout_ms=15000", messages)
        self.assertIn("wifi_trace phase=interface active=1", messages)
        self.assertIn("wifi_trace phase=connect_requested credentials_present=1", messages)
        self.assertIn(
            "wifi_trace phase=status elapsed_ms=100 connected=0 status=connecting status_code=1",
            messages,
        )
        self.assertIn(
            "wifi_trace phase=connected elapsed_ms=200 connected=1 status=got_ip status_code=3 "
            "ip=192.168.1.44 netmask=255.255.255.0 gateway=192.168.1.1 dns=192.168.1.1",
            messages,
        )
        trace_text = "\n".join(messages)
        self.assertNotIn("LabNet", trace_text)
        self.assertNotIn("secret-password", trace_text)
        self.assertNotIn("http://192.168.1.10", trace_text)

    def test_connect_wifi_throttles_status_heartbeats_and_reports_timeout(self):
        """Unchanged status should print once per second before the final timeout."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig("LabNet", "secret-password", "http://192.168.1.10")
        wlan = FakeWLAN(connected_after=100, statuses=(1, 1, 1, 1, 1, -2))
        network = FakeNetwork(wlan)
        messages = []
        sleeps = []
        ticks = iter((0, 0, 250, 500, 750, 1000, 1250))

        with self.assertRaises(wifi_probe.WiFiProbeError):
            wifi_probe.connect_wifi(
                config,
                network_module=network,
                timeout_ms=1250,
                print_func=messages.append,
                sleep_ms_func=sleeps.append,
                ticks_ms_func=lambda: next(ticks),
            )

        status_lines = [line for line in messages if "phase=status" in line]
        self.assertEqual(
            status_lines,
            [
                "wifi_trace phase=status elapsed_ms=0 connected=0 status=connecting status_code=1",
                "wifi_trace phase=status elapsed_ms=1000 connected=0 status=connecting status_code=1",
                "wifi_trace phase=status elapsed_ms=1250 connected=0 status=no_ap_found status_code=-2",
            ],
        )
        self.assertEqual(
            messages[-1],
            "wifi_trace phase=timeout elapsed_ms=1250 connected=0 status=no_ap_found status_code=-2",
        )
        self.assertEqual(sleeps, [250, 250, 250, 250, 250])

    def test_connect_wifi_redacts_exception_text_and_reports_numeric_error(self):
        """Connection exceptions should expose type and errno without secret text."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig("LabNet", "secret-password", "http://192.168.1.10")
        error = OSError(17, "LabNet secret-password http://192.168.1.10")
        wlan = FakeWLAN(connect_error=error)
        messages = []

        with self.assertRaises(OSError):
            wifi_probe.connect_wifi(
                config,
                network_module=FakeNetwork(wlan),
                print_func=messages.append,
                ticks_ms_func=lambda: 0,
            )

        self.assertEqual(
            messages[-1],
            "wifi_trace phase=exception operation=connect error_type={} errno=17".format(
                type(error).__name__
            ),
        )
        trace_text = "\n".join(messages)
        self.assertNotIn("LabNet", trace_text)
        self.assertNotIn("secret-password", trace_text)
        self.assertNotIn("http://192.168.1.10", trace_text)

    def test_connect_wifi_status_failure_is_visible_but_nonfatal(self):
        """A status inspection failure should not replace a successful connection."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig("LabNet", "secret-password", "http://192.168.1.10")
        wlan = FakeWLAN(connected_after=0, status_error=OSError(5, "sensitive driver text"))
        messages = []

        connected = wifi_probe.connect_wifi(
            config,
            wlan=wlan,
            network_module=FakeNetwork(wlan),
            print_func=messages.append,
            ticks_ms_func=lambda: 25,
        )

        self.assertIs(connected, wlan)
        self.assertIn(
            "wifi_trace phase=exception operation=status error_type=OSError errno=5",
            messages,
        )
        self.assertIn(
            "wifi_trace phase=status elapsed_ms=0 connected=1 status=unavailable "
            "status_code=unavailable",
            messages,
        )
        self.assertNotIn("phase=connect_requested", "\n".join(messages))
        self.assertNotIn("sensitive driver text", "\n".join(messages))

    def test_connect_wifi_reports_unknown_driver_status(self):
        """An unknown numeric driver status should remain visible without guessing."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig("LabNet", "secret-password", "http://192.168.1.10")
        wlan = FakeWLAN(connected_after=0, statuses=(99,))
        messages = []

        wifi_probe.connect_wifi(
            config,
            wlan=wlan,
            network_module=FakeNetwork(wlan),
            print_func=messages.append,
            ticks_ms_func=lambda: 10,
        )

        self.assertIn(
            "wifi_trace phase=status elapsed_ms=0 connected=1 status=unknown status_code=99",
            messages,
        )

    def test_wifi_status_constants_map_to_stable_trace_names(self):
        """Every standard MicroPython status constant should have a stable trace name."""
        wifi_probe = self.import_module("wifi_probe")
        network = FakeNetwork(FakeWLAN())

        expected_names = {
            network.STAT_IDLE: "idle",
            network.STAT_CONNECTING: "connecting",
            network.STAT_WRONG_PASSWORD: "wrong_password",
            network.STAT_NO_AP_FOUND: "no_ap_found",
            network.STAT_CONNECT_FAIL: "connect_fail",
            network.STAT_GOT_IP: "got_ip",
        }

        for status_code, expected_name in expected_names.items():
            self.assertEqual(wifi_probe._status_name(network, status_code), expected_name)

    def test_connect_wifi_ifconfig_failure_is_visible_but_nonfatal(self):
        """A local IP inspection failure should not replace a successful connection."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig("LabNet", "secret-password", "http://192.168.1.10")
        wlan = FakeWLAN(
            connected_after=0,
            ifconfig_error=OSError(12, "LabNet secret-password sensitive IP text"),
        )
        messages = []

        connected = wifi_probe.connect_wifi(
            config,
            wlan=wlan,
            network_module=FakeNetwork(wlan),
            print_func=messages.append,
            ticks_ms_func=lambda: 0,
        )

        self.assertIs(connected, wlan)
        self.assertIn(
            "wifi_trace phase=exception operation=ifconfig error_type=OSError errno=12",
            messages,
        )
        self.assertTrue(any(message.startswith("wifi_trace phase=connected") for message in messages))
        trace_text = "\n".join(messages)
        self.assertNotIn("LabNet", trace_text)
        self.assertNotIn("secret-password", trace_text)
        self.assertNotIn("sensitive IP text", trace_text)

    def test_health_check_closes_response_and_reports_status(self):
        """health_check should close the HTTP response after reading status."""
        wifi_probe = self.import_module("wifi_probe")
        response = FakeResponse(status_code=204)

        result = wifi_probe.health_check("http://192.168.1.10/health", request_get=lambda url: response)

        self.assertTrue(result.ok)
        self.assertEqual(result.status_code, 204)
        self.assertTrue(response.closed)

    def test_wifi_probe_rejects_public_endpoint_before_network_connect(self):
        """run_probe should reject public endpoints before creating a network connection."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig("LabNet", "secret-password", "https://example.com")
        messages = []
        led = FakeStatusLed()
        display = FakeStatusDisplay()

        status = wifi_probe.run_probe(
            config=config,
            status_led=led,
            status_display=display,
            print_func=messages.append,
        )

        self.assertEqual(status, wifi_probe.STATUS_ERROR)
        self.assertEqual(led.states, ["error"])
        self.assertEqual(display.screens, [("error", "endpoint rejected")])
        self.assertIn("wifi_probe: endpoint rejected:", messages[1])

    def test_wifi_probe_connects_and_reports_ready_on_health_ok(self):
        """run_probe should connect Wi-Fi, call local /health, and report ready."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig("LabNet", "secret-password", "http://192.168.1.10:8080")
        wlan = FakeWLAN(connected_after=0)
        led = FakeStatusLed()
        display = FakeStatusDisplay()
        messages = []
        requested_urls = []

        def fake_get(url):
            """Record the requested URL and return an OK response."""
            requested_urls.append(url)
            return FakeResponse(status_code=200)

        status = wifi_probe.run_probe(
            config=config,
            wlan=wlan,
            network_module=FakeNetwork(wlan),
            request_get=fake_get,
            status_led=led,
            status_display=display,
            print_func=messages.append,
        )

        self.assertEqual(status, wifi_probe.STATUS_OK)
        self.assertEqual(requested_urls, ["http://192.168.1.10:8080/health"])
        self.assertEqual(led.states, ["connecting", "ready"])
        self.assertEqual(display.screens[0], ("wifi", "connecting"))
        self.assertEqual(display.screens[-1], ("ready", "health 200"))
        self.assertIn("wifi_probe: health ok 200", messages)
        self.assertTrue(any(message.startswith("wifi_trace phase=start") for message in messages))

    def test_wifi_probe_timeout_renders_offline_instead_of_error(self):
        """A Wi-Fi timeout should preserve the device's nonfatal offline UI."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig(
            "LabNet",
            "secret-password",
            "http://192.168.1.10:8080",
        )
        wlan = FakeWLAN(connected_after=100)
        led = FakeStatusLed()
        display = FakeStatusDisplay()
        messages = []
        sleeps = []
        ticks = iter((0, 50, 100))

        status = wifi_probe.run_probe(
            config=config,
            wlan=wlan,
            network_module=FakeNetwork(wlan),
            request_get=lambda url: self.fail("health request should not run offline"),
            status_led=led,
            status_display=display,
            print_func=messages.append,
            sleep_ms_func=sleeps.append,
            ticks_ms_func=lambda: next(ticks),
            timeout_ms=100,
        )

        self.assertEqual(status, wifi_probe.STATUS_ERROR)
        self.assertEqual(led.states, ["connecting", "offline"])
        self.assertEqual(display.screens, [("wifi", "connecting"), ("offline", "Wi-Fi: LabNet")])
        self.assertEqual(sleeps, [250])
        self.assertIn("wifi_probe: offline: WiFiProbeError", messages)


if __name__ == "__main__":
    unittest.main()
