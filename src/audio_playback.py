"""Bounded I2S speaker playback and WAV parsing for AIPI-Lite."""

import struct

from pins import AUDIO_I2S_BCLK
from pins import AUDIO_I2S_DOUT
from pins import AUDIO_I2S_LRCLK
from pins import AUDIO_I2S_MCLK

DEFAULT_I2S_BUS_ID = 0
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_BITS_PER_SAMPLE = 16
DEFAULT_CHANNELS = 1
DEFAULT_BUFFER_BYTES = 2048
DEFAULT_TONE_MS = 250
DEFAULT_TONE_FREQUENCY = 440
DEFAULT_TONE_AMPLITUDE = 3000
MAX_PLAYBACK_BYTES = 64 * 1024


class AudioPlaybackError(Exception):
    """Raised when playback input is invalid or I2S output fails."""


class AudioPlaybackConfig:
    """Describe the fixed-format PCM playback parameters."""

    def __init__(
        self,
        sample_rate=DEFAULT_SAMPLE_RATE,
        bits_per_sample=DEFAULT_BITS_PER_SAMPLE,
        channels=DEFAULT_CHANNELS,
        max_playback_bytes=MAX_PLAYBACK_BYTES,
        buffer_bytes=DEFAULT_BUFFER_BYTES,
    ):
        """Create a bounded PCM playback configuration."""
        self.sample_rate = _positive_int(sample_rate, "sample_rate")
        self.bits_per_sample = _positive_int(bits_per_sample, "bits_per_sample")
        self.channels = _positive_int(channels, "channels")
        self.max_playback_bytes = _positive_int(max_playback_bytes, "max_playback_bytes")
        self.buffer_bytes = _positive_int(buffer_bytes, "buffer_bytes")

        if self.bits_per_sample != 16:
            raise AudioPlaybackError("only 16-bit PCM playback is supported")
        if self.channels != 1:
            raise AudioPlaybackError("only mono PCM playback is supported")

    def frame_bytes(self):
        """Return the number of bytes in one PCM frame."""
        return self.channels * (self.bits_per_sample // 8)

    def bytes_per_second(self):
        """Return the PCM byte rate for this configuration."""
        return self.sample_rate * self.frame_bytes()

    def chunk_bytes(self):
        """Return an I2S write chunk size aligned to a full PCM frame."""
        frame_bytes = self.frame_bytes()
        chunk_bytes = self.buffer_bytes - (self.buffer_bytes % frame_bytes)
        if chunk_bytes <= 0:
            raise AudioPlaybackError("buffer_bytes is too small for one PCM frame")
        return chunk_bytes

    def validate_format(self, sample_rate, bits_per_sample, channels, byte_rate, block_align):
        """Raise when a WAV format does not match the supported playback format."""
        expected_block_align = self.frame_bytes()
        expected_byte_rate = self.bytes_per_second()
        if sample_rate != self.sample_rate:
            raise AudioPlaybackError("unsupported WAV sample rate: {}".format(sample_rate))
        if bits_per_sample != self.bits_per_sample:
            raise AudioPlaybackError("unsupported WAV bit depth: {}".format(bits_per_sample))
        if channels != self.channels:
            raise AudioPlaybackError("unsupported WAV channel count: {}".format(channels))
        if block_align != expected_block_align:
            raise AudioPlaybackError("unsupported WAV block alignment: {}".format(block_align))
        if byte_rate != expected_byte_rate:
            raise AudioPlaybackError("unsupported WAV byte rate: {}".format(byte_rate))


class PlaybackMetrics:
    """Summarize an I2S playback operation for serial diagnostics."""

    def __init__(self, byte_count, sample_count, write_calls, underrun_count):
        """Create immutable playback metrics."""
        self.byte_count = byte_count
        self.sample_count = sample_count
        self.write_calls = write_calls
        self.underrun_count = underrun_count


def _positive_int(value, field_name):
    """Return value as a positive integer or raise AudioPlaybackError."""
    try:
        integer = int(value)
    except (TypeError, ValueError):
        raise AudioPlaybackError("{} must be an integer".format(field_name))
    if integer <= 0:
        raise AudioPlaybackError("{} must be greater than zero".format(field_name))
    return integer


def validate_pcm(pcm, config=None):
    """Return PCM byte count or raise when payload cannot be played safely."""
    if config is None:
        config = AudioPlaybackConfig()

    byte_count = len(pcm)
    if byte_count <= 0:
        raise AudioPlaybackError("PCM payload is empty")
    if byte_count % config.frame_bytes():
        raise AudioPlaybackError("PCM byte count is not aligned to full samples")
    if byte_count > config.max_playback_bytes:
        raise AudioPlaybackError(
            "playback payload is {} bytes, limit is {}".format(
                byte_count,
                config.max_playback_bytes,
            )
        )
    return byte_count


def parse_wav(wav, config=None):
    """Return PCM data from a supported 16 kHz 16-bit mono PCM WAV file."""
    if config is None:
        config = AudioPlaybackConfig()

    wav = bytes(wav)
    if len(wav) < 12:
        raise AudioPlaybackError("WAV data is too short")
    if wav[0:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise AudioPlaybackError("WAV data must be RIFF/WAVE")

    offset = 12
    found_format = False
    pcm = None

    while offset + 8 <= len(wav):
        chunk_id = wav[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", wav, offset + 4)[0]
        offset += 8
        chunk_end = offset + chunk_size
        if chunk_end > len(wav):
            raise AudioPlaybackError("WAV chunk extends past end of data")

        if chunk_id == b"fmt ":
            if chunk_size < 16:
                raise AudioPlaybackError("WAV fmt chunk is too short")
            audio_format, channels, sample_rate, byte_rate, block_align, bits_per_sample = (
                struct.unpack_from("<HHIIHH", wav, offset)
            )
            if audio_format != 1:
                raise AudioPlaybackError("only PCM WAV playback is supported")
            config.validate_format(sample_rate, bits_per_sample, channels, byte_rate, block_align)
            found_format = True
        elif chunk_id == b"data":
            pcm = wav[offset:chunk_end]

        offset = chunk_end + (chunk_size % 2)

    if not found_format:
        raise AudioPlaybackError("WAV fmt chunk was not found")
    if pcm is None:
        raise AudioPlaybackError("WAV data chunk was not found")

    validate_pcm(pcm, config)
    return pcm


def create_i2s(
    config=None,
    bus_id=DEFAULT_I2S_BUS_ID,
    i2s_factory=None,
    pin_factory=None,
):
    """Create the MicroPython I2S TX bus for ES8311 speaker samples."""
    if config is None:
        config = AudioPlaybackConfig()

    if i2s_factory is None or pin_factory is None:
        from machine import I2S
        from machine import Pin

        if i2s_factory is None:
            i2s_factory = I2S
        if pin_factory is None:
            pin_factory = Pin

    try:
        return i2s_factory(
            bus_id,
            sck=pin_factory(AUDIO_I2S_BCLK),
            ws=pin_factory(AUDIO_I2S_LRCLK),
            sd=pin_factory(AUDIO_I2S_DOUT),
            mck=pin_factory(AUDIO_I2S_MCLK),
            mode=i2s_factory.TX,
            bits=config.bits_per_sample,
            format=i2s_factory.MONO,
            rate=config.sample_rate,
            ibuf=config.buffer_bytes,
        )
    except TypeError as exc:
        raise AudioPlaybackError(
            "I2S constructor rejected the speaker configuration: {}".format(exc)
        )


def write_pcm(i2s, pcm, config=None):
    """Write a bounded PCM payload to an I2S object and return metrics."""
    if config is None:
        config = AudioPlaybackConfig()

    byte_count = validate_pcm(pcm, config)
    chunk_bytes = config.chunk_bytes()
    view = memoryview(pcm)
    offset = 0
    write_calls = 0
    underrun_count = 0

    while offset < byte_count:
        chunk_end = min(offset + chunk_bytes, byte_count)
        chunk_length = chunk_end - offset
        written = i2s.write(view[offset:chunk_end])
        write_calls += 1
        if written is None:
            written = 0
        if written <= 0:
            raise AudioPlaybackError("I2S write returned no data")
        if written > chunk_length:
            raise AudioPlaybackError("I2S write reported more bytes than requested")
        if written % config.frame_bytes():
            raise AudioPlaybackError("I2S write split a PCM frame")
        if written < chunk_length:
            underrun_count += 1
        offset += written

    return PlaybackMetrics(
        byte_count=byte_count,
        sample_count=byte_count // config.frame_bytes(),
        write_calls=write_calls,
        underrun_count=underrun_count,
    )


def play_pcm(
    pcm,
    config=None,
    i2s=None,
    i2s_factory=None,
    pin_factory=None,
    speaker_gate=None,
):
    """Play PCM through I2S while enabling GPIO9 only during playback."""
    if config is None:
        config = AudioPlaybackConfig()

    owns_i2s = i2s is None
    if i2s is None:
        i2s = create_i2s(config=config, i2s_factory=i2s_factory, pin_factory=pin_factory)

    if speaker_gate is None:
        from es8311 import SpeakerAmplifierGate

        speaker_gate = SpeakerAmplifierGate()

    try:
        speaker_gate.disable()
        speaker_gate.enable()
        return write_pcm(i2s, pcm, config)
    finally:
        speaker_gate.disable()
        if owns_i2s and hasattr(i2s, "deinit"):
            i2s.deinit()


def play_wav(wav, config=None, **playback_kwargs):
    """Parse and play a supported WAV payload through I2S."""
    if config is None:
        config = AudioPlaybackConfig()
    pcm = parse_wav(wav, config)
    return play_pcm(pcm, config=config, **playback_kwargs)


def test_tone_pcm(
    config=None,
    frequency=DEFAULT_TONE_FREQUENCY,
    duration_ms=DEFAULT_TONE_MS,
    amplitude=DEFAULT_TONE_AMPLITUDE,
):
    """Return a bounded low-volume square-wave test tone as PCM bytes."""
    if config is None:
        config = AudioPlaybackConfig()

    frequency = _positive_int(frequency, "frequency")
    duration_ms = _positive_int(duration_ms, "duration_ms")
    amplitude = _positive_int(amplitude, "amplitude")
    if amplitude > 32767:
        raise AudioPlaybackError("amplitude must fit in signed 16-bit PCM")

    sample_count = (config.sample_rate * duration_ms) // 1000
    if sample_count <= 0:
        raise AudioPlaybackError("test tone duration is too short")

    pcm = bytearray(sample_count * config.frame_bytes())
    validate_pcm(pcm, config)

    period_samples = max(2, config.sample_rate // frequency)
    half_period = max(1, period_samples // 2)

    for sample_index in range(sample_count):
        if (sample_index % period_samples) < half_period:
            value = amplitude
        else:
            value = -amplitude
        struct.pack_into("<h", pcm, sample_index * 2, value)

    return bytes(pcm)
