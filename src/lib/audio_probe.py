"""Serial-visible ES8311 codec probe for AIPI-Lite hardware bring-up."""

import time

from es8311 import ES8311CodecControl
from es8311 import SpeakerAmplifierGate
from es8311 import find_expected_address
from es8311 import format_i2c_addresses


def sleep_ms(milliseconds):
    """Sleep for the requested milliseconds on MicroPython or CPython."""
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(milliseconds)
        return
    time.sleep(milliseconds / 1000)


def run_probe(
    print_func=print,
    codec=None,
    speaker_gate=None,
    sleep_ms_func=sleep_ms,
    toggle_speaker=True,
    toggle_ms=50,
):
    """Scan I2C, initialize the ES8311, and safely pulse the speaker gate."""
    if codec is None:
        codec = ES8311CodecControl()
    if speaker_gate is None:
        speaker_gate = SpeakerAmplifierGate()

    print_func("audio_probe: starting ES8311 codec probe")
    speaker_gate.disable()
    print_func("audio_probe: speaker gate disabled")

    addresses = codec.scan()
    print_func("audio_probe: i2c scan: {}".format(format_i2c_addresses(addresses)))

    detected = find_expected_address(addresses)
    if detected is None:
        print_func("audio_probe: expected ES8311 codec address not found")
        return False

    codec.address = detected
    print_func("audio_probe: codec 0x{:02X} detected".format(detected))
    codec.initialize()
    print_func("audio_probe: codec initialized for 16000 Hz 16-bit I2S")

    if toggle_speaker:
        speaker_gate.enable()
        print_func("audio_probe: speaker gate enabled for {} ms".format(toggle_ms))
        sleep_ms_func(toggle_ms)
        speaker_gate.disable()
        print_func("audio_probe: speaker gate disabled")

    print_func("audio_probe: complete")
    return True


if __name__ == "__main__":
    run_probe()
