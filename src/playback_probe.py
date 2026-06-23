"""Serial-visible I2S speaker playback probe for AIPI-Lite."""

from audio_playback import AudioPlaybackConfig
from audio_playback import play_pcm
from audio_playback import test_tone_pcm
from es8311 import ES8311CodecControl
from es8311 import MODE_OUTPUT
from es8311 import SpeakerAmplifierGate


def run_probe(
    print_func=print,
    codec=None,
    speaker_gate=None,
    config=None,
    i2s=None,
    i2s_factory=None,
    pin_factory=None,
    tone_frequency=440,
    tone_ms=250,
    tone_amplitude=3000,
):
    """Initialize output audio, play a test tone, and print playback metrics."""
    if codec is None:
        codec = ES8311CodecControl()
    if speaker_gate is None:
        speaker_gate = SpeakerAmplifierGate()
    if config is None:
        config = AudioPlaybackConfig()

    dac_unmuted = False

    print_func("playback_probe: starting speaker playback probe")
    speaker_gate.disable()
    print_func("playback_probe: speaker gate disabled")

    try:
        codec.initialize(mode=MODE_OUTPUT)
        print_func(
            "playback_probe: codec initialized for {} Hz {}-bit mono output".format(
                config.sample_rate,
                config.bits_per_sample,
            )
        )

        pcm = test_tone_pcm(
            config=config,
            frequency=tone_frequency,
            duration_ms=tone_ms,
            amplitude=tone_amplitude,
        )
        print_func(
            "playback_probe: generated {} Hz test tone, {} bytes".format(
                tone_frequency,
                len(pcm),
            )
        )

        codec.set_dac_muted(False)
        dac_unmuted = True
        print_func("playback_probe: DAC unmuted")

        metrics = play_pcm(
            pcm,
            config=config,
            i2s=i2s,
            i2s_factory=i2s_factory,
            pin_factory=pin_factory,
            speaker_gate=speaker_gate,
        )
        print_func(
            "playback_probe: played {} bytes, {} samples".format(
                metrics.byte_count,
                metrics.sample_count,
            )
        )
        print_func(
            "playback_probe: write calls {}, underruns {}".format(
                metrics.write_calls,
                metrics.underrun_count,
            )
        )
        print_func("playback_probe: complete")
        return metrics
    finally:
        speaker_gate.disable()
        if dac_unmuted:
            codec.set_dac_muted(True)
            print_func("playback_probe: DAC muted")


if __name__ == "__main__":
    run_probe()
