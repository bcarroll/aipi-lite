"""Bounded I2S microphone capture and WAV packaging for AIPI-Lite."""

import struct

from pins import AUDIO_I2S_BCLK
from pins import AUDIO_I2S_DIN
from pins import AUDIO_I2S_LRCLK
from pins import AUDIO_I2S_MCLK

DEFAULT_I2S_BUS_ID = 0
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_BITS_PER_SAMPLE = 16
DEFAULT_CHANNELS = 1
DEFAULT_CAPTURE_MS = 1000
DEFAULT_BUFFER_BYTES = 2048
MAX_CAPTURE_BYTES = 64 * 1024
WAV_HEADER_BYTES = 44


class AudioCaptureError(Exception):
    """Raised when an audio capture request is invalid or cannot complete."""


class AudioCaptureConfig:
    """Describe the fixed-format PCM capture parameters."""

    def __init__(
        self,
        sample_rate=DEFAULT_SAMPLE_RATE,
        bits_per_sample=DEFAULT_BITS_PER_SAMPLE,
        channels=DEFAULT_CHANNELS,
        capture_ms=DEFAULT_CAPTURE_MS,
        max_capture_bytes=MAX_CAPTURE_BYTES,
        buffer_bytes=DEFAULT_BUFFER_BYTES,
    ):
        """Create a bounded PCM capture configuration."""
        self.sample_rate = _positive_int(sample_rate, "sample_rate")
        self.bits_per_sample = _positive_int(bits_per_sample, "bits_per_sample")
        self.channels = _positive_int(channels, "channels")
        self.capture_ms = _positive_int(capture_ms, "capture_ms")
        self.max_capture_bytes = _positive_int(max_capture_bytes, "max_capture_bytes")
        self.buffer_bytes = _positive_int(buffer_bytes, "buffer_bytes")

        if self.bits_per_sample != 16:
            raise AudioCaptureError("only 16-bit PCM capture is supported")
        if self.channels != 1:
            raise AudioCaptureError("only mono PCM capture is supported")

    def bytes_per_second(self):
        """Return the PCM byte rate for this configuration."""
        return self.sample_rate * self.channels * (self.bits_per_sample // 8)

    def target_bytes(self):
        """Return the capture size in bytes, rounded down to a full sample."""
        sample_bytes = self.channels * (self.bits_per_sample // 8)
        raw_bytes = (self.bytes_per_second() * self.capture_ms) // 1000
        return raw_bytes - (raw_bytes % sample_bytes)

    def validate_target_size(self):
        """Return target bytes or raise when the capture would exceed limits."""
        target_bytes = self.target_bytes()
        if target_bytes <= 0:
            raise AudioCaptureError("capture duration is too short")
        if target_bytes > self.max_capture_bytes:
            raise AudioCaptureError(
                "capture would allocate {} bytes, limit is {}".format(
                    target_bytes,
                    self.max_capture_bytes,
                )
            )
        return target_bytes


class CaptureMetrics:
    """Summarize basic PCM capture levels for serial diagnostics."""

    def __init__(self, byte_count, sample_count, peak, clipping_count):
        """Create immutable level metrics for a captured PCM buffer."""
        self.byte_count = byte_count
        self.sample_count = sample_count
        self.peak = peak
        self.clipping_count = clipping_count

    def clipping_percent(self):
        """Return clipped samples as a percentage of total samples."""
        if self.sample_count == 0:
            return 0.0
        return (self.clipping_count * 100.0) / self.sample_count


def _positive_int(value, field_name):
    """Return value as a positive integer or raise AudioCaptureError."""
    try:
        integer = int(value)
    except (TypeError, ValueError):
        raise AudioCaptureError("{} must be an integer".format(field_name))
    if integer <= 0:
        raise AudioCaptureError("{} must be greater than zero".format(field_name))
    return integer


def create_i2s(
    config=None,
    bus_id=DEFAULT_I2S_BUS_ID,
    i2s_factory=None,
    pin_factory=None,
):
    """Create the MicroPython I2S RX bus for ES8311 microphone samples."""
    if config is None:
        config = AudioCaptureConfig()

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
            sd=pin_factory(AUDIO_I2S_DIN),
            mck=pin_factory(AUDIO_I2S_MCLK),
            mode=i2s_factory.RX,
            bits=config.bits_per_sample,
            format=i2s_factory.MONO,
            rate=config.sample_rate,
            ibuf=config.buffer_bytes,
        )
    except TypeError as exc:
        raise AudioCaptureError(
            "I2S constructor rejected the microphone configuration: {}".format(exc)
        )


def read_pcm(i2s, config=None):
    """Read a bounded PCM sample from an I2S object and return bytes."""
    if config is None:
        config = AudioCaptureConfig()

    target_bytes = config.validate_target_size()
    pcm = bytearray(target_bytes)
    view = memoryview(pcm)
    offset = 0

    while offset < target_bytes:
        read_count = i2s.readinto(view[offset:])
        if read_count is None:
            read_count = 0
        if read_count <= 0:
            raise AudioCaptureError("I2S read returned no data")
        offset += read_count

    return bytes(pcm)


def capture_pcm(config=None, i2s=None, i2s_factory=None, pin_factory=None):
    """Create I2S if needed, capture bounded PCM, and deinitialize I2S."""
    if config is None:
        config = AudioCaptureConfig()

    owns_i2s = i2s is None
    if i2s is None:
        i2s = create_i2s(config=config, i2s_factory=i2s_factory, pin_factory=pin_factory)

    try:
        return read_pcm(i2s, config)
    finally:
        if owns_i2s and hasattr(i2s, "deinit"):
            i2s.deinit()


def wav_header(config, pcm_byte_count):
    """Return a RIFF/WAVE header for a PCM payload size."""
    pcm_byte_count = _positive_or_zero_int(pcm_byte_count, "pcm_byte_count")
    byte_rate = config.bytes_per_second()
    block_align = config.channels * (config.bits_per_sample // 8)
    riff_size = 36 + pcm_byte_count

    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        config.channels,
        config.sample_rate,
        byte_rate,
        block_align,
        config.bits_per_sample,
        b"data",
        pcm_byte_count,
    )


def wav_bytes(pcm, config=None):
    """Return a complete WAV byte string for 16-bit mono PCM data."""
    if config is None:
        config = AudioCaptureConfig()
    return wav_header(config, len(pcm)) + bytes(pcm)


def _positive_or_zero_int(value, field_name):
    """Return value as a non-negative integer or raise AudioCaptureError."""
    try:
        integer = int(value)
    except (TypeError, ValueError):
        raise AudioCaptureError("{} must be an integer".format(field_name))
    if integer < 0:
        raise AudioCaptureError("{} must not be negative".format(field_name))
    return integer


def capture_metrics(pcm, clipping_threshold=32760):
    """Return peak and clipping metrics for signed 16-bit little-endian PCM."""
    if len(pcm) % 2:
        raise AudioCaptureError("PCM byte count must be even for 16-bit samples")

    peak = 0
    clipping_count = 0
    sample_count = len(pcm) // 2

    for index in range(0, len(pcm), 2):
        sample = struct.unpack_from("<h", pcm, index)[0]
        magnitude = abs(sample)
        if magnitude > peak:
            peak = magnitude
        if magnitude >= clipping_threshold:
            clipping_count += 1

    return CaptureMetrics(len(pcm), sample_count, peak, clipping_count)
