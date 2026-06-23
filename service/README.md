# AIPI-Lite Local Service Contract

This directory contains the development-only local mock service used by the
firmware local-service contract milestone. It uses only the Python standard
library and makes no outbound network calls.

## Run The Mock Service

Start the mock service on localhost for host-side checks:

```bash
python3 -m service.mock_service --host 127.0.0.1 --port 8080
```

For device testing, bind to a LAN address controlled by the operator, then set
`LOCAL_SERVICE_URL` in ignored `src/local_wifi_config.py` to that local URL:

```python
LOCAL_SERVICE_URL = "http://192.168.1.10:8080"
```

Do not expose this development service to the public internet. It has no
authentication, persistence, or production hardening.

## API

All endpoints are local-only. Firmware validates the configured base URL before
issuing requests.

### `GET /health`

Purpose: confirm the local service is reachable.

Success response:

```json
{
  "contract": "aipi-lite-local-service-v1",
  "service": "aipi-lite-mock",
  "status": "ok"
}
```

### `POST /session`

Purpose: start a push-to-talk exchange.

Request body:

```json
{
  "contract": "aipi-lite-local-service-v1",
  "audio_format": "wav",
  "sample_rate": 16000,
  "bits_per_sample": 16,
  "channels": 1,
  "device_id": "optional-non-secret-label"
}
```

Success response:

```json
{
  "contract": "aipi-lite-local-service-v1",
  "session_id": "session-0001",
  "status": "ready"
}
```

### `POST /audio`

Purpose: upload bounded 16 kHz, 16-bit, mono PCM/WAV audio for a session.

Required headers:

```text
X-AIPI-Contract: aipi-lite-local-service-v1
X-AIPI-Session-Id: session-0001
Content-Type: audio/wav
```

Success response:

```json
{
  "contract": "aipi-lite-local-service-v1",
  "session_id": "session-0001",
  "status": "processing",
  "bytes_received": 3200
}
```

### `GET /response/{session_id}`

Purpose: poll for assistant response status.

Pending response:

```json
{
  "contract": "aipi-lite-local-service-v1",
  "session_id": "session-0001",
  "status": "processing",
  "display_text": "Waiting for audio",
  "audio_url": null
}
```

Complete response:

```json
{
  "contract": "aipi-lite-local-service-v1",
  "session_id": "session-0001",
  "status": "complete",
  "display_text": "Mock response for session-0001",
  "audio_url": "/audio/mock-response.wav"
}
```

### `GET /audio/{response_id}.wav`

Purpose: download the local response audio for playback.

Success response:

```text
Content-Type: audio/wav
```

The mock service returns a deterministic 16 kHz, 16-bit, mono WAV tone.

## Errors

Unknown sessions and routes return JSON with `status: "error"` and a 4xx status
code. Firmware clients treat non-2xx responses as request failures and close the
response object before raising.
