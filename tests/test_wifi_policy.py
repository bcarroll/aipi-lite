"""Tests for local Wi-Fi configuration, endpoint policy, and health probing."""

import importlib
from pathlib import Path
import sys
import types
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

MODULES_TO_CLEAR = ("local_endpoint", "wifi_config", "wifi_probe", "network", "requests", "urequests")


def clear_imported_modules():
    """Remove firmware modules imported by these Wi-Fi tests."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


class FakeWLAN:
    """Test double for MicroPython station WLAN."""

    def __init__(self, connected_after=1):
        """Create a fake WLAN that connects after a fixed poll count."""
        self.active_values = []
        self.connect_calls = []
        self.connected_after = connected_after
        self.polls = 0

    def active(self, enabled):
        """Record active state changes."""
        self.active_values.append(enabled)

    def connect(self, ssid, password):
        """Record Wi-Fi connection credentials without logging the password."""
        self.connect_calls.append((ssid, password))

    def isconnected(self):
        """Return connected after the configured number of polls."""
        self.polls += 1
        return self.polls > self.connected_after

    def ifconfig(self):
        """Return a fake network tuple."""
        return ("192.168.1.44", "255.255.255.0", "192.168.1.1", "192.168.1.1")


class FakeNetwork(types.ModuleType):
    """Test double for MicroPython's network module."""

    STA_IF = "STA_IF"

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

    def test_connect_wifi_uses_station_interface_and_credentials(self):
        """connect_wifi should activate station mode and connect with configured values."""
        wifi_config = self.import_module("wifi_config")
        wifi_probe = self.import_module("wifi_probe")
        config = wifi_config.WiFiConfig("LabNet", "secret-password", "http://192.168.1.10")
        wlan = FakeWLAN(connected_after=2)
        network = FakeNetwork(wlan)
        sleeps = []
        ticks = iter((0, 100, 200))

        connected = wifi_probe.connect_wifi(
            config,
            network_module=network,
            sleep_ms_func=sleeps.append,
            ticks_ms_func=lambda: next(ticks),
        )

        self.assertIs(connected, wlan)
        self.assertEqual(network.calls, ["STA_IF"])
        self.assertEqual(wlan.active_values, [True])
        self.assertEqual(wlan.connect_calls, [("LabNet", "secret-password")])
        self.assertEqual(sleeps, [250])

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


if __name__ == "__main__":
    unittest.main()
