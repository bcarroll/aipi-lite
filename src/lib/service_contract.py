"""Local assistant service contract constants for AIPI-Lite."""

CONTRACT_VERSION = "aipi-lite-local-service-v1"

HEALTH_PATH = "/health"
SESSION_PATH = "/session"
AUDIO_UPLOAD_PATH = "/audio"
RESPONSE_PATH_PREFIX = "/response"
RESPONSE_AUDIO_PATH_PREFIX = "/audio"

CONTENT_TYPE_JSON = "application/json"
CONTENT_TYPE_WAV = "audio/wav"
CONTENT_TYPE_PCM = "application/octet-stream"

STATUS_READY = "ready"
STATUS_PROCESSING = "processing"
STATUS_COMPLETE = "complete"
STATUS_ERROR = "error"


class ServiceContractError(ValueError):
    """Raised when a service contract value is invalid."""


def join_url(base_url, path):
    """Join a normalized base URL and absolute contract path."""
    if not path.startswith("/"):
        raise ServiceContractError("contract path must start with /")
    return "{}{}".format(base_url.rstrip("/"), path)


def health_url(base_url):
    """Return the local service health URL."""
    return join_url(base_url, HEALTH_PATH)


def session_url(base_url):
    """Return the local service session URL."""
    return join_url(base_url, SESSION_PATH)


def audio_upload_url(base_url):
    """Return the local service audio upload URL."""
    return join_url(base_url, AUDIO_UPLOAD_PATH)


def response_url(base_url, session_id):
    """Return the response polling URL for a session identifier."""
    return join_url(base_url, "{}/{}".format(RESPONSE_PATH_PREFIX, safe_path_segment(session_id)))


def response_audio_url(base_url, response_id):
    """Return the response WAV URL for a response identifier."""
    return join_url(
        base_url,
        "{}/{}.wav".format(RESPONSE_AUDIO_PATH_PREFIX, safe_path_segment(response_id)),
    )


def safe_path_segment(value):
    """Return value as a safe single URL path segment or raise."""
    text = _required_text(value, "path segment")
    for unsafe in ("/", "?", "#", "\\"):
        if unsafe in text:
            raise ServiceContractError("path segment contains unsafe character: {}".format(unsafe))
    return text


def _required_text(value, field_name):
    """Return stripped text or raise when it is empty."""
    if value is None:
        raise ServiceContractError("missing {}".format(field_name))
    text = str(value).strip()
    if not text:
        raise ServiceContractError("missing {}".format(field_name))
    return text
