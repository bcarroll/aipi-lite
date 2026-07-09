"""Local-only service endpoint validation for AIPI-Lite firmware."""

ALLOWED_SCHEMES = ("http", "https")


class EndpointPolicyError(ValueError):
    """Raised when a configured service endpoint violates local-only policy."""


class ParsedEndpoint:
    """Hold a parsed local service endpoint."""

    def __init__(self, scheme, host, port=None, path=""):
        """Create an immutable parsed endpoint record."""
        self.scheme = scheme
        self.host = host
        self.port = port
        self.path = path

    def authority(self):
        """Return the endpoint authority as host or host:port."""
        if self.port is None:
            return self.host
        return "{}:{}".format(self.host, self.port)

    def base_url(self):
        """Return the normalized endpoint base URL."""
        path = self.path.rstrip("/")
        return "{}://{}{}".format(self.scheme, self.authority(), path)


def _is_decimal_octet(value):
    """Return True when value is an IPv4 decimal octet."""
    if value == "" or not value.isdigit():
        return False
    if len(value) > 1 and value.startswith("0"):
        return False
    return 0 <= int(value) <= 255


def is_ipv4_address(host):
    """Return True when host is a dotted decimal IPv4 address."""
    parts = host.split(".")
    return len(parts) == 4 and all(_is_decimal_octet(part) for part in parts)


def ipv4_octets(host):
    """Return host as a tuple of IPv4 octets or raise EndpointPolicyError."""
    if not is_ipv4_address(host):
        raise EndpointPolicyError("not an IPv4 address: {}".format(host))
    return tuple(int(part) for part in host.split("."))


def is_private_ipv4(host):
    """Return True when host is in an RFC1918 IPv4 network."""
    first, second, _, _ = ipv4_octets(host)
    return first == 10 or (first == 172 and 16 <= second <= 31) or (first == 192 and second == 168)


def is_loopback_ipv4(host):
    """Return True when host is in the IPv4 loopback range."""
    first, _, _, _ = ipv4_octets(host)
    return first == 127


def is_link_local_ipv4(host):
    """Return True when host is in the IPv4 link-local range."""
    first, second, _, _ = ipv4_octets(host)
    return first == 169 and second == 254


def is_allowed_local_ip(host):
    """Return True when host is an accepted local IPv4 address."""
    if not is_ipv4_address(host):
        return False
    return is_private_ipv4(host) or is_loopback_ipv4(host) or is_link_local_ipv4(host)


def normalize_hostname(host):
    """Normalize a DNS hostname for local-only policy checks."""
    return host.strip().lower().rstrip(".")


def is_mdns_hostname(host):
    """Return True when host is a .local mDNS name."""
    normalized = normalize_hostname(host)
    return normalized.endswith(".local") and len(normalized) > len(".local")


def is_approved_hostname(host, approved_hosts=()):
    """Return True when host is explicitly approved by operator config."""
    normalized = normalize_hostname(host)
    approved = tuple(normalize_hostname(item) for item in approved_hosts)
    return normalized in approved


def parse_endpoint(url):
    """Parse a service URL into scheme, host, optional port, and path."""
    if not isinstance(url, str):
        raise EndpointPolicyError("endpoint URL must be a string")

    value = url.strip()
    if "://" not in value:
        raise EndpointPolicyError("endpoint URL must include a scheme")

    scheme, remainder = value.split("://", 1)
    scheme = scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise EndpointPolicyError("unsupported endpoint scheme: {}".format(scheme))
    if not remainder:
        raise EndpointPolicyError("endpoint URL must include a host")
    if "#" in remainder or "?" in remainder:
        raise EndpointPolicyError("endpoint URL must not include query or fragment")

    slash_index = remainder.find("/")
    if slash_index == -1:
        authority = remainder
        path = ""
    else:
        authority = remainder[:slash_index]
        path = remainder[slash_index:]

    if "@" in authority:
        raise EndpointPolicyError("endpoint URL must not include credentials")
    if authority.startswith("["):
        raise EndpointPolicyError("IPv6 endpoints are not supported by this policy")

    if ":" in authority:
        host, port_text = authority.rsplit(":", 1)
        if not port_text.isdigit():
            raise EndpointPolicyError("endpoint port must be numeric")
        port = int(port_text)
        if not 1 <= port <= 65535:
            raise EndpointPolicyError("endpoint port out of range")
    else:
        host = authority
        port = None

    host = normalize_hostname(host)
    if not host:
        raise EndpointPolicyError("endpoint URL must include a host")
    return ParsedEndpoint(scheme, host, port, path)


def validate_local_endpoint(url, approved_hosts=()):
    """Return a parsed endpoint only when it satisfies local-only policy."""
    endpoint = parse_endpoint(url)
    host = endpoint.host

    if is_allowed_local_ip(host):
        return endpoint
    if is_ipv4_address(host):
        raise EndpointPolicyError("public IPv4 endpoint is not allowed: {}".format(host))
    if is_mdns_hostname(host):
        return endpoint
    if is_approved_hostname(host, approved_hosts):
        return endpoint

    raise EndpointPolicyError("public hostname is not allowed: {}".format(host))


def health_url_for_endpoint(url, approved_hosts=()):
    """Return the validated endpoint URL with a /health path appended."""
    endpoint = validate_local_endpoint(url, approved_hosts)
    base = endpoint.base_url()
    if endpoint.path.rstrip("/").endswith("/health"):
        return base
    return "{}/health".format(base.rstrip("/"))
