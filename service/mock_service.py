"""Stdlib-only mock local assistant service for AIPI-Lite development."""

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import argparse
import json
import struct

CONTRACT_VERSION = "aipi-lite-local-service-v1"
MOCK_AUDIO_ID = "mock-response"


class MockServiceState:
    """Hold deterministic mock sessions and uploaded audio metadata."""

    def __init__(self):
        """Create an empty mock service state."""
        self.next_session_number = 1
        self.sessions = {}

    def create_session(self):
        """Create and return a deterministic session payload."""
        session_id = "session-{:04d}".format(self.next_session_number)
        self.next_session_number += 1
        self.sessions[session_id] = {
            "session_id": session_id,
            "status": "ready",
            "bytes_received": 0,
        }
        return {
            "contract": CONTRACT_VERSION,
            "session_id": session_id,
            "status": "ready",
        }

    def record_audio(self, session_id, byte_count, content_type):
        """Record uploaded audio metadata for an existing session."""
        session = self.require_session(session_id)
        session["status"] = "complete"
        session["bytes_received"] = int(byte_count)
        session["content_type"] = content_type
        return {
            "contract": CONTRACT_VERSION,
            "session_id": session_id,
            "status": "processing",
            "bytes_received": int(byte_count),
        }

    def response_payload(self, session_id):
        """Return a deterministic assistant response payload."""
        session = self.require_session(session_id)
        if session.get("bytes_received", 0) <= 0:
            return {
                "contract": CONTRACT_VERSION,
                "session_id": session_id,
                "status": "processing",
                "display_text": "Waiting for audio",
                "audio_url": None,
            }
        return {
            "contract": CONTRACT_VERSION,
            "session_id": session_id,
            "status": "complete",
            "display_text": "Mock response for {}".format(session_id),
            "audio_url": "/audio/{}.wav".format(MOCK_AUDIO_ID),
        }

    def require_session(self, session_id):
        """Return a session or raise KeyError when it is unknown."""
        if session_id not in self.sessions:
            raise KeyError(session_id)
        return self.sessions[session_id]


def wav_bytes(pcm, sample_rate=16000):
    """Return a RIFF/WAVE byte string for 16-bit mono PCM."""
    byte_rate = sample_rate * 2
    riff_size = 36 + len(pcm)
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        sample_rate,
        byte_rate,
        2,
        16,
        b"data",
        len(pcm),
    ) + pcm


def mock_response_wav():
    """Return a short low-volume deterministic mock response WAV."""
    samples = []
    for index in range(1600):
        value = 1200 if (index // 20) % 2 == 0 else -1200
        samples.append(struct.pack("<h", value))
    return wav_bytes(b"".join(samples))


class AipiLiteMockHandler(BaseHTTPRequestHandler):
    """HTTP handler implementing the AIPI-Lite local service contract."""

    server_version = "AipiLiteMock/1.0"

    def do_GET(self):
        """Handle GET /health, /response/{session_id}, and response audio."""
        if self.path == "/health":
            self.write_json(
                {
                    "contract": CONTRACT_VERSION,
                    "status": "ok",
                    "service": "aipi-lite-mock",
                }
            )
            return

        if self.path.startswith("/response/"):
            session_id = self.path.split("/", 2)[2]
            try:
                self.write_json(self.server.state.response_payload(session_id))
            except KeyError:
                self.write_json({"status": "error", "error": "unknown session"}, status=404)
            return

        if self.path == "/audio/{}.wav".format(MOCK_AUDIO_ID):
            self.write_bytes(mock_response_wav(), "audio/wav")
            return

        self.write_json({"status": "error", "error": "not found"}, status=404)

    def do_POST(self):
        """Handle POST /session and /audio."""
        if self.path == "/session":
            self.write_json(self.server.state.create_session(), status=201)
            return

        if self.path == "/audio":
            session_id = self.headers.get("X-AIPI-Session-Id", "")
            content_type = self.headers.get("Content-Type", "application/octet-stream")
            length = int(self.headers.get("Content-Length", "0"))
            self.rfile.read(length)
            try:
                self.write_json(self.server.state.record_audio(session_id, length, content_type), status=202)
            except KeyError:
                self.write_json({"status": "error", "error": "unknown session"}, status=404)
            return

        self.write_json({"status": "error", "error": "not found"}, status=404)

    def write_json(self, payload, status=200):
        """Write a JSON response with a fixed UTF-8 content type."""
        data = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.write_bytes(data, "application/json", status=status)

    def write_bytes(self, payload, content_type, status=200):
        """Write a binary response with length and content type headers."""
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_string, *args):
        """Emit concise request logs through the server logger."""
        self.server.log_func("{} - {}".format(self.address_string(), format_string % args))


class AipiLiteMockServer(ThreadingHTTPServer):
    """Threading HTTP server with attached mock service state."""

    def __init__(self, server_address, handler_class=AipiLiteMockHandler, log_func=print):
        """Create a mock server with deterministic in-memory state."""
        super().__init__(server_address, handler_class)
        self.state = MockServiceState()
        self.log_func = log_func


def parse_args(argv=None):
    """Parse command-line arguments for the mock service."""
    parser = argparse.ArgumentParser(description="Run the AIPI-Lite mock local service")
    parser.add_argument("--host", default="127.0.0.1", help="interface to bind; use a LAN address for device testing")
    parser.add_argument("--port", type=int, default=8080, help="TCP port to listen on")
    return parser.parse_args(argv)


def main(argv=None):
    """Run the mock service until interrupted."""
    args = parse_args(argv)
    server = AipiLiteMockServer((args.host, args.port))
    print("AIPI-Lite mock service listening on http://{}:{}".format(args.host, args.port))
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping mock service.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
