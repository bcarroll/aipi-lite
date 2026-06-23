"""Tests for bounded I2S speaker playback and WAV parsing."""

import importlib
from pathlib import Path
import struct
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

MODULES_TO_CLEAR = ("audio_playback", "playback_probe", "es8311", "pins")


class FakePin:
    """Test double for MicroPython Pin construction."""

    created = []

    def __init__(self, pin_id):
        """Record the requested pin identifier."""
        self.pin_id = pin_id
        FakePin.created.append(self)


class FakeI2S:
    """Test double for MicroPython I2S speaker writes."""

    TX = "TX"
    MONO = "MONO"
    created = []

    def __init__(self, bus_id, **kwargs):
        """Record construction arguments and prepare deterministic writes."""
        self.bus_id = bus_id
        self.kwargs = kwargs
        self.deinitialized = False
        self.write_sizes = []
        self.write_calls = 0
        FakeI2S.created.append(self)

    def write(self, buffer):
        """Pretend to write the entire supplied buffer."""
        self.write_calls += 1
        self.write_sizes.append(len(buffer))
        return len(buffer)

    def deinit(self):
        """Record deinitialization."""
        self.deinitialized = True


class PartialI2S(FakeI2S):
    """Fake I2S object that reports partial writes."""

    def write(self, buffer):
        """Write at most half the supplied bytes."""
        self.write_calls += 1
        written = max(2, len(buffer) // 2)
        written -= written % 2
        self.write_sizes.append(written)
        return written


class FailingI2S(FakeI2S):
    """Fake I2S object that cannot accept playback data."""

    def write(self, buffer):
        """Report a failed write."""
        self.write_calls += 1
        return 0


class FakeSpeakerGate:
    """Record speaker gate transitions."""

    def __init__(self):
        """Create an empty gate event list."""
        self.events = []

    def enable(self):
        """Record a speaker enable request."""
        self.events.append("enable")

    def disable(self):
        """Record a speaker disable request."""
        self.events.append("disable")


class FakeCodec:
    """Record codec output initialization and DAC mute transitions."""

    def __init__(self):
        """Create a fake codec recorder."""
        self.modes = []
        self.mutes = []

    def initialize(self, mode=None):
        """Record the requested codec initialization mode."""
        self.modes.append(mode)

    def set_dac_muted(self, muted=True):
        """Record DAC mute state changes."""
        self.mutes.append(bool(muted))


def clear_imported_modules():
    """Remove imported firmware modules after each test."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def make_wav(pcm, sample_rate=16000, bits_per_sample=16, channels=1, audio_format=1):
    """Return a minimal RIFF/WAVE byte string for tests."""
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    block_align = channels * (bits_per_sample // 8)
    fmt_chunk = struct.pack(
        "<4sIHHIIHH",
        b"fmt ",
        16,
        audio_format,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
    )
    data_chunk = b"data" + struct.pack("<I", len(pcm)) + pcm
    riff_size = 4 + len(fmt_chunk) + len(data_chunk)
    return b"RIFF" + struct.pack("<I", riff_size) + b"WAVE" + fmt_chunk + data_chunk


class AudioPlaybackTests(unittest.TestCase):
    """Validate playback helpers without attached hardware."""

    def setUp(self):
        """Import fresh playback modules for each test."""
        clear_imported_modules()
        ensure_src_path()
        self.audio_playback = importlib.import_module("audio_playback")
        FakePin.created.clear()
        FakeI2S.created.clear()

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def test_playback_config_is_fixed_format_and_bounded(self):
        """Playback config should support only bounded 16-bit mono output."""
        config = self.audio_playback.AudioPlaybackConfig(buffer_bytes=1025)

        self.assertEqual(config.bytes_per_second(), 32000)
        self.assertEqual(config.frame_bytes(), 2)
        self.assertEqual(config.chunk_bytes(), 1024)

        with self.assertRaises(self.audio_playback.AudioPlaybackError):
            self.audio_playback.AudioPlaybackConfig(bits_per_sample=8)
        with self.assertRaises(self.audio_playback.AudioPlaybackError):
            self.audio_playback.AudioPlaybackConfig(channels=2)
        with self.assertRaises(self.audio_playback.AudioPlaybackError):
            self.audio_playback.validate_pcm(b"\x00" * 8, config=self.audio_playback.AudioPlaybackConfig(max_playback_bytes=4))

    def test_create_i2s_uses_documented_speaker_pins(self):
        """create_i2s should wire the ES8311 speaker path to documented pins."""
        config = self.audio_playback.AudioPlaybackConfig(buffer_bytes=4096)

        i2s = self.audio_playback.create_i2s(
            config=config,
            i2s_factory=FakeI2S,
            pin_factory=FakePin,
        )

        self.assertEqual(i2s.bus_id, 0)
        self.assertEqual(i2s.kwargs["mode"], FakeI2S.TX)
        self.assertEqual(i2s.kwargs["format"], FakeI2S.MONO)
        self.assertEqual(i2s.kwargs["bits"], 16)
        self.assertEqual(i2s.kwargs["rate"], 16000)
        self.assertEqual(i2s.kwargs["ibuf"], 4096)
        self.assertEqual(i2s.kwargs["mck"].pin_id, 6)
        self.assertEqual(i2s.kwargs["sd"].pin_id, 11)
        self.assertEqual(i2s.kwargs["ws"].pin_id, 12)
        self.assertEqual(i2s.kwargs["sck"].pin_id, 14)

    def test_parse_wav_accepts_supported_pcm_and_rejects_other_formats(self):
        """WAV parsing should accept only the supported output format."""
        pcm = struct.pack("<hhhh", 0, 100, -100, 3000)
        wav = make_wav(pcm)

        self.assertEqual(self.audio_playback.parse_wav(wav), pcm)

        for bad_wav in (
            make_wav(pcm, sample_rate=8000),
            make_wav(pcm, channels=2),
            make_wav(pcm, bits_per_sample=8),
            make_wav(pcm, audio_format=3),
            b"not a wav",
        ):
            with self.assertRaises(self.audio_playback.AudioPlaybackError):
                self.audio_playback.parse_wav(bad_wav)

    def test_write_pcm_reports_partial_writes_as_underruns(self):
        """write_pcm should keep writing partial chunks and report underruns."""
        config = self.audio_playback.AudioPlaybackConfig(buffer_bytes=8)
        pcm = bytes(range(16))
        i2s = PartialI2S(0)

        metrics = self.audio_playback.write_pcm(i2s, pcm, config)

        self.assertEqual(metrics.byte_count, 16)
        self.assertEqual(metrics.sample_count, 8)
        self.assertEqual(metrics.write_calls, 5)
        self.assertEqual(metrics.underrun_count, 4)

    def test_play_pcm_enables_speaker_only_while_playing_and_deinitializes(self):
        """play_pcm should disable the speaker gate before and after playback."""
        config = self.audio_playback.AudioPlaybackConfig(buffer_bytes=8)
        gate = FakeSpeakerGate()

        metrics = self.audio_playback.play_pcm(
            bytes(range(16)),
            config=config,
            i2s_factory=FakeI2S,
            pin_factory=FakePin,
            speaker_gate=gate,
        )

        self.assertEqual(metrics.write_calls, 2)
        self.assertEqual(gate.events, ["disable", "enable", "disable"])
        self.assertTrue(FakeI2S.created[0].deinitialized)

    def test_play_pcm_disables_speaker_after_write_failure(self):
        """play_pcm should leave the speaker gate disabled when I2S write fails."""
        gate = FakeSpeakerGate()
        i2s = FailingI2S(0)

        with self.assertRaises(self.audio_playback.AudioPlaybackError):
            self.audio_playback.play_pcm(
                b"\x00\x00",
                i2s=i2s,
                speaker_gate=gate,
            )

        self.assertEqual(gate.events, ["disable", "enable", "disable"])

    def test_test_tone_is_bounded_signed_16_bit_pcm(self):
        """The generated probe tone should be fixed-format signed PCM."""
        config = self.audio_playback.AudioPlaybackConfig()

        pcm = self.audio_playback.test_tone_pcm(config=config, frequency=400, duration_ms=10, amplitude=1234)

        self.assertEqual(len(pcm), 320)
        self.assertIn(struct.pack("<h", 1234), pcm)
        self.assertIn(struct.pack("<h", -1234), pcm)


class PlaybackProbeTests(unittest.TestCase):
    """Validate serial-visible playback probe behavior."""

    def setUp(self):
        """Import fresh playback probe modules for each test."""
        clear_imported_modules()
        ensure_src_path()
        self.audio_playback = importlib.import_module("audio_playback")
        self.playback_probe = importlib.import_module("playback_probe")

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def test_playback_probe_initializes_output_and_reports_metrics(self):
        """playback_probe should initialize output, unmute DAC, and play a tone."""
        codec = FakeCodec()
        speaker_gate = FakeSpeakerGate()
        messages = []
        i2s = FakeI2S(0)
        config = self.audio_playback.AudioPlaybackConfig(buffer_bytes=64)

        metrics = self.playback_probe.run_probe(
            print_func=messages.append,
            codec=codec,
            speaker_gate=speaker_gate,
            config=config,
            i2s=i2s,
            tone_frequency=400,
            tone_ms=10,
            tone_amplitude=1200,
        )

        self.assertEqual(codec.modes, ["output"])
        self.assertEqual(codec.mutes, [False, True])
        self.assertEqual(metrics.byte_count, 320)
        self.assertEqual(speaker_gate.events, ["disable", "disable", "enable", "disable", "disable"])
        self.assertIn("playback_probe: DAC unmuted", messages)
        self.assertIn("playback_probe: played 320 bytes, 160 samples", messages)
        self.assertEqual(messages[-1], "playback_probe: DAC muted")


if __name__ == "__main__":
    unittest.main()
