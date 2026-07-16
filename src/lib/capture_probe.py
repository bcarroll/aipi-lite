"""Serial-visible I2S microphone capture probe for AIPI-Lite."""

from audio_capture import AudioCaptureConfig
from audio_capture import capture_metrics
from audio_capture import capture_pcm
from es8311 import ES8311CodecControl
from es8311 import MODE_INPUT
from es8311 import SpeakerAmplifierGate


def run_probe(
    print_func=print,
    codec=None,
    speaker_gate=None,
    config=None,
    i2s=None,
    i2s_factory=None,
    pin_factory=None,
):
    """Initialize input audio, capture a short PCM sample, and print metrics."""
    if codec is None:
        codec = ES8311CodecControl()
    if speaker_gate is None:
        speaker_gate = SpeakerAmplifierGate()
    if config is None:
        config = AudioCaptureConfig(capture_ms=500)

    print_func("capture_probe: starting microphone capture probe")
    speaker_gate.disable()
    print_func("capture_probe: speaker gate disabled")

    codec.initialize(mode=MODE_INPUT)
    print_func(
        "capture_probe: codec initialized for {} Hz {}-bit mono input".format(
            config.sample_rate,
            config.bits_per_sample,
        )
    )

    pcm = capture_pcm(
        config=config,
        i2s=i2s,
        i2s_factory=i2s_factory,
        pin_factory=pin_factory,
    )
    metrics = capture_metrics(pcm)
    print_func(
        "capture_probe: captured {} bytes, {} samples".format(
            metrics.byte_count,
            metrics.sample_count,
        )
    )
    print_func(
        "capture_probe: peak {}, clipped {} ({:.1f}%)".format(
            metrics.peak,
            metrics.clipping_count,
            metrics.clipping_percent(),
        )
    )
    print_func("capture_probe: complete")
    return metrics


if __name__ == "__main__":
    run_probe()
