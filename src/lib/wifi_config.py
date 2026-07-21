"""Local Wi-Fi configuration loading for AIPI-Lite firmware."""

LOCAL_WIFI_CONFIG_MODULE = "local_wifi_config"


class WiFiConfigError(ValueError):
    """Raised when local Wi-Fi configuration is missing or invalid."""


class WiFiConfig:
    """Hold local Wi-Fi and service endpoint settings."""

    def __init__(self, ssid, password, local_service_url, approved_hosts=()):
        """Create a validated Wi-Fi configuration."""
        self.ssid = _required_text(ssid, "ssid")
        self.password = _required_text(password, "password")
        self.local_service_url = _required_text(local_service_url, "local_service_url")
        self.approved_hosts = tuple(_required_text(host, "approved host") for host in approved_hosts or ())

    def as_dict(self):
        """Return a non-secret-friendly dictionary representation."""
        return {
            "ssid": self.ssid,
            "local_service_url": self.local_service_url,
            "approved_hosts": self.approved_hosts,
        }


def _required_text(value, field_name):
    """Return stripped text or raise WiFiConfigError when it is empty."""
    if value is None:
        raise WiFiConfigError("missing {}".format(field_name))
    text = str(value).strip()
    if not text:
        raise WiFiConfigError("missing {}".format(field_name))
    return text


def offline_network_detail(ssid=None):
    """Return a non-secret LCD note identifying the configured Wi-Fi network."""
    if ssid is None:
        return "Wi-Fi not configured"
    network_name = str(ssid).strip()
    if not network_name:
        return "Wi-Fi not configured"
    return "Wi-Fi: {}".format(network_name)


def _module_value(module, names, default=None):
    """Return the first matching attribute from a config module."""
    for name in names:
        if hasattr(module, name):
            return getattr(module, name)
    return default


def _module_name(module):
    """Return a printable module name for configuration errors."""
    return getattr(module, "__name__", LOCAL_WIFI_CONFIG_MODULE)


def _public_module_names(module):
    """Return public attribute names exposed by a config module."""
    try:
        names = dir(module)
    except Exception:
        return ()
    return tuple(name for name in names if not name.startswith("_"))


def _required_module_value(module, names, field_name):
    """Return a required config attribute with a source-aware error."""
    try:
        return _required_text(_module_value(module, names), field_name)
    except WiFiConfigError:
        available_names = _public_module_names(module)
        available_label = ", ".join(available_names) if available_names else "none"
        raise WiFiConfigError(
            "missing {} in {} (expected one of {}; available: {})".format(
                field_name,
                _module_name(module),
                ", ".join(names),
                available_label,
            )
        )


def config_from_mapping(mapping):
    """Build WiFiConfig from a dictionary-like object."""
    approved_hosts = mapping.get("approved_hosts", mapping.get("APPROVED_LOCAL_HOSTS", ()))
    return WiFiConfig(
        mapping.get("ssid", mapping.get("WIFI_SSID")),
        mapping.get("password", mapping.get("WIFI_PASSWORD")),
        mapping.get("local_service_url", mapping.get("LOCAL_SERVICE_URL")),
        approved_hosts,
    )


def config_from_module(module):
    """Build WiFiConfig from an imported local config module."""
    return WiFiConfig(
        _required_module_value(module, ("WIFI_SSID", "SSID"), "ssid"),
        _required_module_value(module, ("WIFI_PASSWORD", "PASSWORD"), "password"),
        _required_module_value(
            module,
            ("LOCAL_SERVICE_URL", "SERVICE_URL"),
            "local_service_url",
        ),
        _module_value(module, ("APPROVED_LOCAL_HOSTS", "APPROVED_HOSTS"), ()),
    )


def load_config(module_name=LOCAL_WIFI_CONFIG_MODULE, importer=None):
    """Load Wi-Fi config from an ignored local MicroPython module."""
    if importer is None:
        importer = __import__
    try:
        module = importer(module_name)
    except ImportError:
        raise WiFiConfigError(
            "missing local Wi-Fi config module: {}".format(module_name)
        )
    return config_from_module(module)
