"""Local-only assistant service client for AIPI-Lite firmware."""

from local_endpoint import validate_local_endpoint
from service_contract import CONTENT_TYPE_JSON
from service_contract import CONTENT_TYPE_WAV
from service_contract import CONTRACT_VERSION
from service_contract import STATUS_COMPLETE
from service_contract import audio_upload_url
from service_contract import health_url
from service_contract import response_url
from service_contract import session_url


class LocalServiceError(Exception):
    """Raised when the local service contract cannot be completed."""


class LocalServiceHTTPError(LocalServiceError):
    """Raised when the local service returns a non-success HTTP status."""

    def __init__(self, status_code, message="local service request failed"):
        """Create an HTTP error with the returned status code."""
        super().__init__("{}: {}".format(message, status_code))
        self.status_code = status_code


class LocalServiceClient:
    """Call the configured local assistant service contract."""

    def __init__(
        self,
        base_url,
        approved_hosts=(),
        request_get=None,
        request_post=None,
        json_module=None,
    ):
        """Create a client after validating the endpoint is local-only."""
        self.approved_hosts = tuple(approved_hosts or ())
        self.endpoint = validate_local_endpoint(base_url, self.approved_hosts)
        self.base_url = self.endpoint.base_url()
        self.root_url = "{}://{}".format(self.endpoint.scheme, self.endpoint.authority())
        self.request_get = request_get
        self.request_post = request_post
        self.json = json_module

    def health(self):
        """Call GET /health and return the decoded JSON response."""
        return self._request_json("GET", health_url(self.base_url))

    def start_session(self, device_id=None):
        """Call POST /session and return the created session identifier."""
        payload = {
            "contract": CONTRACT_VERSION,
            "audio_format": "wav",
            "sample_rate": 16000,
            "bits_per_sample": 16,
            "channels": 1,
        }
        if device_id:
            payload["device_id"] = str(device_id)

        data = self._request_json("POST", session_url(self.base_url), json_body=payload)
        session_id = data.get("session_id")
        if not session_id:
            raise LocalServiceError("session response did not include session_id")
        return session_id

    def upload_audio(self, session_id, audio_bytes, content_type=CONTENT_TYPE_WAV):
        """Call POST /audio with captured audio bytes for a session."""
        if not session_id:
            raise LocalServiceError("session_id is required for audio upload")
        if not audio_bytes:
            raise LocalServiceError("audio upload payload is empty")

        headers = {
            "Content-Type": content_type,
            "X-AIPI-Contract": CONTRACT_VERSION,
            "X-AIPI-Session-Id": str(session_id),
        }
        return self._request_json(
            "POST",
            audio_upload_url(self.base_url),
            data=audio_bytes,
            headers=headers,
        )

    def get_response(self, session_id):
        """Call GET /response/{session_id} and return the decoded JSON response."""
        return self._request_json("GET", response_url(self.base_url, session_id))

    def download_audio(self, audio_url):
        """Download response audio from a local absolute or relative URL."""
        url = self._resolve_audio_url(audio_url)
        response = self._request("GET", url)
        try:
            self._require_success(response)
            if hasattr(response, "content"):
                return response.content
            if hasattr(response, "text"):
                return response.text
            if hasattr(response, "read"):
                return response.read()
            raise LocalServiceError("audio response did not include content")
        finally:
            self._close_response(response)

    def response_ready(self, response_payload):
        """Return True when a response payload reports a complete answer."""
        return response_payload.get("status") == STATUS_COMPLETE

    def _resolve_audio_url(self, audio_url):
        """Resolve an absolute or relative audio URL and enforce local-only policy."""
        if not audio_url:
            raise LocalServiceError("audio_url is required")
        text = str(audio_url).strip()
        if "://" in text:
            endpoint = validate_local_endpoint(text, self.approved_hosts)
            return endpoint.base_url()
        if text.startswith("/"):
            return "{}{}".format(self.root_url, text)
        return "{}/{}".format(self.base_url.rstrip("/"), text)

    def _request_json(self, method, url, json_body=None, data=None, headers=None):
        """Run a request, validate status, decode JSON, and close the response."""
        headers = dict(headers or {})
        if json_body is not None:
            headers["Content-Type"] = CONTENT_TYPE_JSON
            data = self._json_dumps(json_body)

        response = self._request(method, url, data=data, headers=headers)
        try:
            self._require_success(response)
            return self._response_json(response)
        finally:
            self._close_response(response)

    def _request(self, method, url, data=None, headers=None):
        """Dispatch a GET or POST request through injected or imported callables."""
        method = method.upper()
        if method == "GET":
            get = self.request_get or _load_request_get()
            return get(url)
        if method == "POST":
            post = self.request_post or _load_request_post()
            return post(url, data=data, headers=headers or {})
        raise LocalServiceError("unsupported HTTP method: {}".format(method))

    def _json_dumps(self, payload):
        """Serialize a JSON payload using MicroPython or CPython JSON support."""
        json_module = self.json or _load_json_module()
        return json_module.dumps(payload)

    def _response_json(self, response):
        """Decode a JSON response using response.json or response text."""
        if hasattr(response, "json"):
            return response.json()
        if hasattr(response, "text"):
            json_module = self.json or _load_json_module()
            return json_module.loads(response.text)
        raise LocalServiceError("JSON response did not include text")

    def _require_success(self, response):
        """Raise when a response status code is not 2xx."""
        status_code = getattr(response, "status_code", getattr(response, "status", None))
        if status_code is None:
            raise LocalServiceError("response did not include status code")
        if not 200 <= int(status_code) < 300:
            raise LocalServiceHTTPError(status_code)

    def _close_response(self, response):
        """Close a response object when it provides a close method."""
        if hasattr(response, "close"):
            response.close()


def _load_request_get():
    """Return a urequests or requests GET callable."""
    try:
        import urequests

        return urequests.get
    except ImportError:
        import requests

        return requests.get


def _load_request_post():
    """Return a urequests or requests POST callable."""
    try:
        import urequests

        return urequests.post
    except ImportError:
        import requests

        return requests.post


def _load_json_module():
    """Return a MicroPython-compatible JSON module."""
    try:
        import ujson

        return ujson
    except ImportError:
        import json

        return json
