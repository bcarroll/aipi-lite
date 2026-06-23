"""Tests for the local assistant service contract and mock service."""

import importlib
from pathlib import Path
import json
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

MODULES_TO_CLEAR = (
    "local_endpoint",
    "service_client",
    "service_contract",
    "service.mock_service",
)


class FakeResponse:
    """Test double for urequests/requests responses."""

    def __init__(self, status_code=200, payload=None, text=None, content=b""):
        """Create a fake HTTP response."""
        self.status_code = status_code
        self.payload = payload
        if text is None and payload is not None:
            text = json.dumps(payload)
        self.text = text or ""
        self.content = content
        self.closed = False

    def json(self):
        """Return the configured JSON payload."""
        if self.payload is None:
            return json.loads(self.text)
        return self.payload

    def close(self):
        """Record response closure."""
        self.closed = True


class FakeRequests:
    """Record fake GET and POST calls for the local service client."""

    def __init__(self):
        """Create an empty request recorder."""
        self.get_calls = []
        self.post_calls = []
        self.responses = []

    def queue(self, response):
        """Append a response returned by the next request."""
        self.responses.append(response)
        return response

    def get(self, url):
        """Record a GET request and return the next response."""
        self.get_calls.append(url)
        return self.responses.pop(0)

    def post(self, url, data=None, headers=None):
        """Record a POST request and return the next response."""
        self.post_calls.append((url, data, dict(headers or {})))
        return self.responses.pop(0)


def clear_imported_modules():
    """Remove imported firmware modules after each test."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_paths():
    """Make firmware and service modules importable by host tests."""
    src_path = str(SRC_ROOT)
    repo_path = str(REPO_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)
    if repo_path not in sys.path:
        sys.path.insert(0, repo_path)


class LocalServiceClientTests(unittest.TestCase):
    """Validate the MicroPython-side service client without live network I/O."""

    def setUp(self):
        """Import fresh modules for each test."""
        clear_imported_modules()
        ensure_paths()
        self.service_client = importlib.import_module("service_client")
        self.service_contract = importlib.import_module("service_contract")

    def tearDown(self):
        """Clean imported modules after each test."""
        clear_imported_modules()

    def test_client_rejects_public_endpoint_before_requests(self):
        """Public service endpoints should fail local-only validation."""
        requests = FakeRequests()

        with self.assertRaises(Exception):
            self.service_client.LocalServiceClient(
                "https://example.com",
                request_get=requests.get,
                request_post=requests.post,
            )

        self.assertEqual(requests.get_calls, [])
        self.assertEqual(requests.post_calls, [])

    def test_start_session_posts_contract_payload_and_closes_response(self):
        """start_session should POST JSON to /session and return session_id."""
        requests = FakeRequests()
        response = requests.queue(FakeResponse(payload={"session_id": "session-0001"}))
        client = self.service_client.LocalServiceClient(
            "http://192.168.1.10:8080/api",
            request_get=requests.get,
            request_post=requests.post,
        )

        session_id = client.start_session(device_id="bench-a")

        self.assertEqual(session_id, "session-0001")
        self.assertTrue(response.closed)
        self.assertEqual(requests.post_calls[0][0], "http://192.168.1.10:8080/api/session")
        payload = json.loads(requests.post_calls[0][1])
        self.assertEqual(payload["contract"], self.service_contract.CONTRACT_VERSION)
        self.assertEqual(payload["audio_format"], "wav")
        self.assertEqual(payload["device_id"], "bench-a")
        self.assertEqual(requests.post_calls[0][2]["Content-Type"], "application/json")

    def test_upload_audio_sends_session_header_and_raw_bytes(self):
        """upload_audio should POST audio bytes to /audio with session headers."""
        requests = FakeRequests()
        response = requests.queue(FakeResponse(status_code=202, payload={"status": "processing"}))
        client = self.service_client.LocalServiceClient(
            "http://assistant.local:8080",
            request_get=requests.get,
            request_post=requests.post,
        )

        result = client.upload_audio("session-0001", b"RIFFdata")

        self.assertEqual(result["status"], "processing")
        self.assertTrue(response.closed)
        url, data, headers = requests.post_calls[0]
        self.assertEqual(url, "http://assistant.local:8080/audio")
        self.assertEqual(data, b"RIFFdata")
        self.assertEqual(headers["X-AIPI-Session-Id"], "session-0001")
        self.assertEqual(headers["Content-Type"], "audio/wav")

    def test_get_response_and_audio_download_use_local_urls(self):
        """Response polling and audio download should stay on local URLs."""
        requests = FakeRequests()
        response_payload = {
            "status": "complete",
            "display_text": "Mock response",
            "audio_url": "/audio/mock-response.wav",
        }
        response = requests.queue(FakeResponse(payload=response_payload))
        audio_response = requests.queue(FakeResponse(content=b"wav-bytes"))
        client = self.service_client.LocalServiceClient(
            "http://assistant.lan:8080/api",
            approved_hosts=("assistant.lan",),
            request_get=requests.get,
            request_post=requests.post,
        )

        payload = client.get_response("session-0001")
        audio = client.download_audio(payload["audio_url"])

        self.assertTrue(client.response_ready(payload))
        self.assertEqual(audio, b"wav-bytes")
        self.assertTrue(response.closed)
        self.assertTrue(audio_response.closed)
        self.assertEqual(requests.get_calls[0], "http://assistant.lan:8080/api/response/session-0001")
        self.assertEqual(requests.get_calls[1], "http://assistant.lan:8080/audio/mock-response.wav")

        with self.assertRaises(Exception):
            client.download_audio("https://example.com/audio.wav")

    def test_http_errors_close_response_and_raise_status(self):
        """Non-2xx responses should close and raise a status-carrying error."""
        requests = FakeRequests()
        response = requests.queue(FakeResponse(status_code=503, payload={"status": "error"}))
        client = self.service_client.LocalServiceClient(
            "http://127.0.0.1:8080",
            request_get=requests.get,
            request_post=requests.post,
        )

        with self.assertRaises(self.service_client.LocalServiceHTTPError) as raised:
            client.health()

        self.assertEqual(raised.exception.status_code, 503)
        self.assertTrue(response.closed)


class MockServiceTests(unittest.TestCase):
    """Validate mock service helpers without opening sockets."""

    def setUp(self):
        """Import the mock service module for each test."""
        clear_imported_modules()
        ensure_paths()
        self.mock_service = importlib.import_module("service.mock_service")

    def tearDown(self):
        """Clean imported modules after each test."""
        clear_imported_modules()

    def test_mock_state_accepts_session_audio_and_response(self):
        """Mock state should follow the session/audio/response contract."""
        state = self.mock_service.MockServiceState()

        session = state.create_session()
        upload = state.record_audio(session["session_id"], 128, "audio/wav")
        response = state.response_payload(session["session_id"])

        self.assertEqual(session["status"], "ready")
        self.assertEqual(upload["status"], "processing")
        self.assertEqual(upload["bytes_received"], 128)
        self.assertEqual(response["status"], "complete")
        self.assertEqual(response["audio_url"], "/audio/mock-response.wav")

    def test_mock_response_wav_is_supported_format(self):
        """Mock response audio should be a 16 kHz 16-bit mono WAV."""
        wav = self.mock_service.mock_response_wav()

        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(wav[8:12], b"WAVE")
        self.assertEqual(wav[12:16], b"fmt ")
        self.assertEqual(wav[36:40], b"data")
        self.assertEqual(wav[22:24], b"\x01\x00")
        self.assertEqual(wav[24:28], b"\x80>\x00\x00")
        self.assertEqual(wav[34:36], b"\x10\x00")


if __name__ == "__main__":
    unittest.main()
