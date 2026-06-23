"""Tests for bounded I2S microphone capture and WAV packaging."""

import importlib
from pathlib import Path
import struct
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

MODULES_TO_CLEAR = ("audio_capture", "capture_probe", "es8311", "pins")


class FakePin:
    """Test double for MicroPython Pin construction."""

    created = []

    def __init__(self, pin_id):
        """Record the requested pin identifier."""
        self.pin_id = pin_id
        FakePin.created.append(self)


class FakeI2S:
    """Test double for MicroPython I2S capture reads."""

    RX = "RX"
    MONO = "MONO"
    created = []

    def __init__(self, bus_id, **kwargs):
        """Record construction arguments and prepare deterministic reads."""
        self.bus_id = bus_id
        self.kwargs = kwargs
        self.deinitialized = False
        self.read_chunks = []
        self.read_calls = 0
        FakeI2S.created.append(self)

    def readinto(self, buffer):
        """Fill the supplied buffer with deterministic sample bytes."""
        self.read_calls += 1
        count = min(len(buffer), 4)
        for index in range(count):
            buffer[index] = (self.read_calls + index) & 0xFF
        self.read_chunks.append(count)
        return count

    def deinit(self):
        """Record deinitialization."""
        self.deinitialized = True


class FakeCodec:
    """Record ES8311 initialization mode."""

    def __init__(self):
        """Create a fake codec recorder."""
        self.modes = []

    def initialize(self, mode=None):
        """Record the requested codec initialization mode."""
        self.modes.append(mode)


class FakeSpeakerGate:
    """Record speaker-gate disable calls."""

    def __init__(self):
        """Create a fake speaker gate recorder."""
        self.disable_count = 0

    def disable(self):
        """Record a speaker-disable request."""
        self.disable_count += 1


def clear_imported_modules():
    """Remove imported firmware modules after each test."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


class AudioCaptureTests(unittest.TestCase):
    """Validate bounded PCM capture helpers without attached hardware."""

    def setUp(self):
        """Import fresh capture modules for each test."""
        clear_imported_modules()
        ensure_src_path()
        self.audio_capture = importlib.import_module("audio_capture")
        FakePin.created.clear()
        FakeI2S.created.clear()

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def test_capture_config_calculates_bounded_target_bytes(self):
        """AudioCaptureConfig should compute exact 16-bit mono capture sizes."""
        config = self.audio_capture.AudioCaptureConfig(capture_ms=500)

        self.assertEqual(config.bytes_per_second(), 32000)
        self.assertEqual(config.target_bytes(), 16000)
        self.assertEqual(config.validate_target_size(), 16000)

    def test_capture_config_rejects_oversized_capture(self):
        """Capture config should fail before allocating oversized buffers."""
        config = self.audio_capture.AudioCaptureConfig(capture_ms=3000, max_capture_bytes=1024)

        with self.assertRaises(self.audio_capture.AudioCaptureError):
            config.validate_target_size()

    def test_create_i2s_uses_documented_microphone_pins(self):
        """create_i2s should wire the ES8311 microphone path to documented pins."""
        config = self.audio_capture.AudioCaptureConfig(buffer_bytes=4096)

        i2s = self.audio_capture.create_i2s(
            config=config,
            i2s_factory=FakeI2S,
            pin_factory=FakePin,
        )

        self.assertEqual(i2s.bus_id, 0)
        self.assertEqual(i2s.kwargs["mode"], FakeI2S.RX)
        self.assertEqual(i2s.kwargs["format"], FakeI2S.MONO)
        self.assertEqual(i2s.kwargs["bits"], 16)
        self.assertEqual(i2s.kwargs["rate"], 16000)
        self.assertEqual(i2s.kwargs["ibuf"], 4096)
        self.assertEqual(i2s.kwargs["mck"].pin_id, 6)
        self.assertEqual(i2s.kwargs["sd"].pin_id, 13)
        self.assertEqual(i2s.kwargs["ws"].pin_id, 12)
        self.assertEqual(i2s.kwargs["sck"].pin_id, 14)

    def test_create_i2s_reports_constructor_rejection(self):
        """create_i2s should raise a capture error when I2S rejects config."""
        class RejectingI2S(FakeI2S):
            """Fake I2S constructor that rejects keyword arguments."""

            def __init__(self, bus_id, **kwargs):
                """Raise the same exception shape as a strict constructor."""
                raise TypeError("unexpected keyword argument 'mck'")

        with self.assertRaises(self.audio_capture.AudioCaptureError) as raised:
            self.audio_capture.create_i2s(
                i2s_factory=RejectingI2S,
                pin_factory=FakePin,
            )

        self.assertIn("I2S constructor rejected", str(raised.exception))

    def test_capture_pcm_reads_to_target_and_deinitializes_owned_i2s(self):
        """capture_pcm should fill the target buffer and deinitialize owned I2S."""
        config = self.audio_capture.AudioCaptureConfig(capture_ms=1)

        pcm = self.audio_capture.capture_pcm(
            config=config,
            i2s_factory=FakeI2S,
            pin_factory=FakePin,
        )

        self.assertEqual(len(pcm), 32)
        self.assertEqual(FakeI2S.created[0].read_chunks, [4] * 8)
        self.assertTrue(FakeI2S.created[0].deinitialized)

    def test_wav_bytes_contains_expected_header_fields(self):
        """wav_bytes should prepend a valid PCM RIFF/WAVE header."""
        config = self.audio_capture.AudioCaptureConfig(sample_rate=16000)
        pcm = struct.pack("<hhhh", 0, 100, -100, 32767)

        wav = self.audio_capture.wav_bytes(pcm, config)

        self.assertEqual(wav[:4], b"RIFF")
        self.assertEqual(wav[8:12], b"WAVE")
        self.assertEqual(wav[12:16], b"fmt ")
        self.assertEqual(struct.unpack_from("<H", wav, 20)[0], 1)
        self.assertEqual(struct.unpack_from("<H", wav, 22)[0], 1)
        self.assertEqual(struct.unpack_from("<I", wav, 24)[0], 16000)
        self.assertEqual(struct.unpack_from("<H", wav, 34)[0], 16)
        self.assertEqual(wav[36:40], b"data")
        self.assertEqual(struct.unpack_from("<I", wav, 40)[0], len(pcm))
        self.assertEqual(wav[44:], pcm)

    def test_capture_metrics_reports_peak_and_clipping(self):
        """capture_metrics should report absolute peak and clipped samples."""
        pcm = struct.pack("<hhhh", 0, -12, 32760, -32768)

        metrics = self.audio_capture.capture_metrics(pcm)

        self.assertEqual(metrics.byte_count, 8)
        self.assertEqual(metrics.sample_count, 4)
        self.assertEqual(metrics.peak, 32768)
        self.assertEqual(metrics.clipping_count, 2)
        self.assertEqual(metrics.clipping_percent(), 50.0)


class CaptureProbeTests(unittest.TestCase):
    """Validate serial-visible capture probe behavior."""

    def setUp(self):
        """Import fresh capture probe modules for each test."""
        clear_imported_modules()
        ensure_src_path()
        self.audio_capture = importlib.import_module("audio_capture")
        self.capture_probe = importlib.import_module("capture_probe")

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def test_capture_probe_initializes_input_and_reports_metrics(self):
        """capture_probe should initialize input, capture PCM, and report metrics."""
        codec = FakeCodec()
        speaker_gate = FakeSpeakerGate()
        messages = []
        i2s = FakeI2S(0)
        config = self.audio_capture.AudioCaptureConfig(capture_ms=1)

        metrics = self.capture_probe.run_probe(
            print_func=messages.append,
            codec=codec,
            speaker_gate=speaker_gate,
            config=config,
            i2s=i2s,
        )

        self.assertEqual(codec.modes, ["input"])
        self.assertEqual(speaker_gate.disable_count, 1)
        self.assertEqual(metrics.byte_count, 32)
        self.assertIn("capture_probe: speaker gate disabled", messages)
        self.assertIn("capture_probe: captured 32 bytes, 16 samples", messages)
        self.assertEqual(messages[-1], "capture_probe: complete")


if __name__ == "__main__":
    unittest.main()
