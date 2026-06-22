"""Tests for ES8311 codec control and speaker-gate safety."""

import importlib
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

MODULES_TO_CLEAR = ("audio_probe", "es8311", "pins")


class FakeI2C:
    """Record I2C scans and register writes for host-side codec tests."""

    def __init__(self, addresses=(0x18,), registers=None):
        """Create a fake I2C bus with deterministic scan and register state."""
        self.addresses = tuple(addresses)
        self.registers = dict(registers or {})
        self.writes = []
        self.scan_count = 0

    def scan(self):
        """Return the configured fake I2C addresses."""
        self.scan_count += 1
        return list(self.addresses)

    def writeto_mem(self, address, register, data):
        """Record one fake register write."""
        value = data[0]
        self.writes.append((address, register, value))
        self.registers[register] = value

    def readfrom_mem(self, address, register, length):
        """Return one fake register value."""
        if length != 1:
            raise ValueError("fake ES8311 tests only read one byte")
        return bytes((self.registers.get(register, 0),))


class FakePin:
    """Record speaker-gate pin construction and writes."""

    OUT = "OUT"
    created = []

    def __init__(self, pin_id, mode=None):
        """Create a fake pin with a MicroPython-like value API."""
        self.pin_id = pin_id
        self.mode = mode
        self.values = []
        FakePin.created.append(self)

    def value(self, level=None):
        """Read or write the fake GPIO level."""
        if level is None:
            if not self.values:
                return None
            return self.values[-1]
        self.values.append(level)


class FakeI2CFactory:
    """Record construction arguments passed by create_i2c."""

    def __init__(self):
        """Create a callable fake I2C factory."""
        self.calls = []

    def __call__(self, bus_id, scl, sda, freq):
        """Record construction arguments and return a fake bus."""
        self.calls.append((bus_id, scl, sda, freq))
        return FakeI2C()


def clear_imported_modules():
    """Remove imported firmware modules after each test."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


class ES8311CodecControlTests(unittest.TestCase):
    """Validate ES8311 register control without attached hardware."""

    def setUp(self):
        """Import a fresh codec module for each test."""
        clear_imported_modules()
        ensure_src_path()
        self.es8311 = importlib.import_module("es8311")
        FakePin.created.clear()

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def test_default_address_matches_board_esphome_configuration(self):
        """The expected ES8311 scan address should be the 7-bit 0x18 value."""
        self.assertEqual(self.es8311.DEFAULT_I2C_ADDRESS, 0x18)
        self.assertEqual(self.es8311.EXPECTED_I2C_ADDRESSES, (0x18, 0x19))
        self.assertEqual(self.es8311.format_i2c_addresses((0x18, 0x3C)), "0x18, 0x3C")

    def test_create_i2c_uses_documented_control_pins(self):
        """create_i2c should construct the ES8311 bus on GPIO4/GPIO5."""
        factory = FakeI2CFactory()

        bus = self.es8311.create_i2c(i2c_factory=factory, pin_factory=FakePin)

        self.assertIsInstance(bus, FakeI2C)
        self.assertEqual(len(factory.calls), 1)
        bus_id, scl, sda, frequency = factory.calls[0]
        self.assertEqual(bus_id, 0)
        self.assertEqual(scl.pin_id, 4)
        self.assertEqual(sda.pin_id, 5)
        self.assertEqual(frequency, 100000)

    def test_initialize_writes_expected_register_sequence(self):
        """Initializing both paths should write the named register sequence."""
        fake_i2c = FakeI2C(addresses=(0x18,))
        codec = self.es8311.ES8311CodecControl(i2c=fake_i2c)

        sequence = codec.initialize()

        self.assertEqual(sequence, self.es8311.initialization_sequence(self.es8311.MODE_BOTH))
        self.assertEqual(fake_i2c.writes, [(0x18, register, value) for register, value in sequence])
        self.assertEqual(fake_i2c.writes[:2], [(0x18, 0x00, 0x1F), (0x18, 0x00, 0x00)])
        self.assertIn((0x18, 0x31, 0x60), fake_i2c.writes)
        self.assertEqual(fake_i2c.writes[-1], (0x18, 0x00, 0x80))

    def test_named_modes_include_only_requested_path_registers(self):
        """Input and output modes should keep their path-specific writes separate."""
        input_sequence = self.es8311.initialization_sequence(self.es8311.MODE_INPUT)
        output_sequence = self.es8311.initialization_sequence(self.es8311.MODE_OUTPUT)

        self.assertIn((0x16, 0x24), input_sequence)
        self.assertNotIn((0x32, 0xBF), input_sequence)
        self.assertIn((0x32, 0xBF), output_sequence)
        self.assertNotIn((0x16, 0x24), output_sequence)

    def test_shutdown_writes_low_power_sequence(self):
        """Shutdown should mute DAC and write the low-power register sequence."""
        fake_i2c = FakeI2C(addresses=(0x18,))
        codec = self.es8311.ES8311CodecControl(i2c=fake_i2c)

        sequence = codec.shutdown()

        self.assertEqual(sequence, self.es8311.SHUTDOWN_SEQUENCE)
        self.assertEqual(fake_i2c.writes, [(0x18, register, value) for register, value in sequence])
        self.assertEqual(fake_i2c.writes[0], (0x18, 0x31, 0x60))

    def test_missing_codec_raises_with_scan_result(self):
        """A missing expected address should produce a useful probe failure."""
        codec = self.es8311.ES8311CodecControl(i2c=FakeI2C(addresses=(0x3C,)))

        with self.assertRaises(self.es8311.ES8311CodecError) as raised:
            codec.initialize()

        self.assertIn("0x3C", str(raised.exception))

    def test_speaker_gate_defaults_off_and_toggles_gpio9(self):
        """The speaker amplifier gate should drive GPIO9 low on construction."""
        gate = self.es8311.SpeakerAmplifierGate(pin_factory=FakePin)
        pin = FakePin.created[-1]

        self.assertEqual(pin.pin_id, 9)
        self.assertEqual(pin.mode, FakePin.OUT)
        self.assertFalse(gate.is_enabled())
        self.assertEqual(pin.values, [0])

        gate.enable()
        gate.disable()

        self.assertEqual(pin.values, [0, 1, 0])
        self.assertFalse(gate.is_enabled())

    def test_set_dac_muted_preserves_non_mute_bits(self):
        """DAC mute writes should only change the documented mute bits."""
        fake_i2c = FakeI2C(registers={0x31: 0x05})
        codec = self.es8311.ES8311CodecControl(i2c=fake_i2c)

        muted = codec.set_dac_muted(True)
        unmuted = codec.set_dac_muted(False)

        self.assertEqual(muted, 0x65)
        self.assertEqual(unmuted, 0x05)
        self.assertEqual(fake_i2c.writes, [(0x18, 0x31, 0x65), (0x18, 0x31, 0x05)])


class AudioProbeTests(unittest.TestCase):
    """Validate the serial-visible codec probe behavior."""

    def setUp(self):
        """Import fresh audio modules for each probe test."""
        clear_imported_modules()
        ensure_src_path()
        self.es8311 = importlib.import_module("es8311")
        self.audio_probe = importlib.import_module("audio_probe")
        FakePin.created.clear()

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def test_probe_initializes_codec_and_leaves_speaker_disabled(self):
        """The probe should pulse GPIO9 briefly and end with the gate disabled."""
        fake_i2c = FakeI2C(addresses=(0x18,))
        codec = self.es8311.ES8311CodecControl(i2c=fake_i2c)
        gate = self.es8311.SpeakerAmplifierGate(pin_factory=FakePin)
        messages = []
        sleeps = []

        result = self.audio_probe.run_probe(
            print_func=messages.append,
            codec=codec,
            speaker_gate=gate,
            sleep_ms_func=sleeps.append,
        )

        self.assertTrue(result)
        self.assertFalse(gate.is_enabled())
        self.assertEqual(FakePin.created[-1].values, [0, 0, 1, 0])
        self.assertEqual(sleeps, [50])
        self.assertIn("audio_probe: codec 0x18 detected", messages)
        self.assertEqual(messages[-1], "audio_probe: complete")
        self.assertIn((0x18, 0x31, 0x60), fake_i2c.writes)

    def test_probe_reports_missing_codec_without_toggling_speaker(self):
        """A failed probe should leave GPIO9 disabled and return False."""
        codec = self.es8311.ES8311CodecControl(i2c=FakeI2C(addresses=(0x3C,)))
        gate = self.es8311.SpeakerAmplifierGate(pin_factory=FakePin)
        messages = []

        result = self.audio_probe.run_probe(
            print_func=messages.append,
            codec=codec,
            speaker_gate=gate,
        )

        self.assertFalse(result)
        self.assertFalse(gate.is_enabled())
        self.assertEqual(FakePin.created[-1].values, [0, 0])
        self.assertIn("audio_probe: expected ES8311 codec address not found", messages)


if __name__ == "__main__":
    unittest.main()
