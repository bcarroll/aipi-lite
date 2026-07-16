"""ES8311 codec control helpers for the AIPI-Lite audio path.

This module only configures the ES8311 control plane over I2C and the external
speaker-amplifier gate on GPIO9. I2S microphone capture and speaker playback are
left to later firmware milestones.
"""

from pins import AUDIO_I2C_SCL
from pins import AUDIO_I2C_SDA
from pins import SPEAKER_ENABLE

DEFAULT_I2C_BUS_ID = 0
DEFAULT_I2C_FREQUENCY = 100000
DEFAULT_I2C_ADDRESS = 0x18
EXPECTED_I2C_ADDRESSES = (0x18, 0x19)

MODE_INPUT = "input"
MODE_OUTPUT = "output"
MODE_BOTH = "both"
MODE_SHUTDOWN = "shutdown"

REG_RESET = 0x00
REG_CLK_MANAGER_01 = 0x01
REG_CLK_MANAGER_02 = 0x02
REG_CLK_MANAGER_03 = 0x03
REG_CLK_MANAGER_04 = 0x04
REG_CLK_MANAGER_05 = 0x05
REG_CLK_MANAGER_06 = 0x06
REG_CLK_MANAGER_07 = 0x07
REG_CLK_MANAGER_08 = 0x08
REG_SDPIN = 0x09
REG_SDPOUT = 0x0A
REG_SYSTEM_0D = 0x0D
REG_SYSTEM_0E = 0x0E
REG_SYSTEM_12 = 0x12
REG_SYSTEM_13 = 0x13
REG_SYSTEM_14 = 0x14
REG_ADC_15 = 0x15
REG_ADC_16 = 0x16
REG_ADC_17 = 0x17
REG_ADC_1C = 0x1C
REG_DAC_31 = 0x31
REG_DAC_32 = 0x32
REG_DAC_37 = 0x37
REG_GP_45 = 0x45

DAC_MUTE_MASK = 0x60

RESET_SEQUENCE = (
    (REG_RESET, 0x1F),
    (REG_RESET, 0x00),
)

# Standard MicroPython I2S provides BCLK, LRCLK/WS, and serial data. At the
# fixed 16 kHz, 16-bit mono configuration it generates BCLK at 1.024 MHz
# (64 x Fs). Select BCLK as the ES8311 clock source and multiply it by four
# to retain the codec's 4.096 MHz internal clock.
CLOCK_SEQUENCE_16K_BCLK_DERIVED = (
    (REG_CLK_MANAGER_01, 0x9F),
    (REG_CLK_MANAGER_02, 0x10),
    (REG_CLK_MANAGER_03, 0x10),
    (REG_CLK_MANAGER_04, 0x20),
    (REG_CLK_MANAGER_05, 0x00),
    (REG_CLK_MANAGER_06, 0x03),
    (REG_CLK_MANAGER_07, 0x00),
    (REG_CLK_MANAGER_08, 0xFF),
)

FORMAT_SEQUENCE_16BIT_I2S = (
    (REG_SDPIN, 0x0C),
    (REG_SDPOUT, 0x0C),
)

INPUT_INITIALIZATION_SEQUENCE = (
    (REG_SYSTEM_14, 0x1A),
    (REG_ADC_15, 0x40),
    (REG_ADC_16, 0x24),
    (REG_ADC_17, 0xBF),
    (REG_ADC_1C, 0x6A),
)

OUTPUT_INITIALIZATION_SEQUENCE = (
    (REG_DAC_32, 0xBF),
    (REG_SYSTEM_12, 0x00),
    (REG_SYSTEM_13, 0x10),
    (REG_DAC_31, DAC_MUTE_MASK),
    (REG_DAC_37, 0x08),
)

POWER_ON_SEQUENCE = (
    (REG_SYSTEM_0D, 0x01),
    (REG_SYSTEM_0E, 0x02),
    (REG_RESET, 0x80),
)

SHUTDOWN_SEQUENCE = (
    (REG_DAC_31, DAC_MUTE_MASK),
    (REG_DAC_32, 0x00),
    (REG_ADC_17, 0x00),
    (REG_SYSTEM_0E, 0xFF),
    (REG_SYSTEM_12, 0x02),
    (REG_SYSTEM_14, 0x00),
    (REG_SYSTEM_0D, 0xFA),
    (REG_ADC_15, 0x00),
    (REG_GP_45, 0x01),
)


class ES8311CodecError(Exception):
    """Raised when the ES8311 codec cannot be detected or configured."""


def format_i2c_addresses(addresses):
    """Return scan addresses formatted for serial logs."""
    addresses = tuple(addresses)
    if not addresses:
        return "none"
    return ", ".join("0x{:02X}".format(address) for address in addresses)


def find_expected_address(addresses, expected_addresses=EXPECTED_I2C_ADDRESSES):
    """Return the first expected ES8311 address from an I2C scan result."""
    scanned = set(addresses)
    for address in expected_addresses:
        if address in scanned:
            return address
    return None


def initialization_sequence(mode=MODE_BOTH):
    """Return the ES8311 register sequence for the requested codec mode."""
    common = RESET_SEQUENCE + CLOCK_SEQUENCE_16K_BCLK_DERIVED + FORMAT_SEQUENCE_16BIT_I2S
    if mode == MODE_INPUT:
        return common + INPUT_INITIALIZATION_SEQUENCE + POWER_ON_SEQUENCE
    if mode == MODE_OUTPUT:
        return common + OUTPUT_INITIALIZATION_SEQUENCE + POWER_ON_SEQUENCE
    if mode == MODE_BOTH:
        return common + INPUT_INITIALIZATION_SEQUENCE + OUTPUT_INITIALIZATION_SEQUENCE + POWER_ON_SEQUENCE
    if mode == MODE_SHUTDOWN:
        return SHUTDOWN_SEQUENCE
    raise ValueError("unknown ES8311 initialization mode: {}".format(mode))


def create_i2c(
    bus_id=DEFAULT_I2C_BUS_ID,
    frequency=DEFAULT_I2C_FREQUENCY,
    i2c_factory=None,
    pin_factory=None,
):
    """Create the MicroPython I2C bus wired to the ES8311 control pins."""
    if i2c_factory is None or pin_factory is None:
        from machine import I2C
        from machine import Pin

        if i2c_factory is None:
            i2c_factory = I2C
        if pin_factory is None:
            pin_factory = Pin

    return i2c_factory(
        bus_id,
        scl=pin_factory(AUDIO_I2C_SCL),
        sda=pin_factory(AUDIO_I2C_SDA),
        freq=frequency,
    )


class SpeakerAmplifierGate:
    """Drive GPIO9 as an active-high speaker amplifier enable gate."""

    def __init__(self, pin_number=SPEAKER_ENABLE, active_high=True, pin_factory=None):
        """Create the speaker gate and immediately drive it to the off state."""
        if pin_factory is None:
            from machine import Pin

            pin_factory = Pin

        self.pin_number = pin_number
        self.active_high = active_high
        self.pin = self._create_output_pin(pin_factory, pin_number)
        self._enabled = None
        self.disable()

    def _create_output_pin(self, pin_factory, pin_number):
        """Create a GPIO output pin using MicroPython or a host-side fake."""
        try:
            return pin_factory(pin_number, pin_factory.OUT)
        except AttributeError:
            return pin_factory(pin_number)

    def _write_enabled(self, enabled):
        """Write the physical pin level for the requested enabled state."""
        if enabled:
            level = 1 if self.active_high else 0
        else:
            level = 0 if self.active_high else 1

        if hasattr(self.pin, "value"):
            self.pin.value(level)
        else:
            self.pin(level)
        self._enabled = enabled

    def enable(self):
        """Enable the external speaker amplifier."""
        self._write_enabled(True)

    def disable(self):
        """Disable the external speaker amplifier."""
        self._write_enabled(False)

    def is_enabled(self):
        """Return True when the speaker amplifier gate is enabled."""
        return bool(self._enabled)


class ES8311CodecControl:
    """Configure the ES8311 codec over the AIPI-Lite I2C control bus."""

    def __init__(
        self,
        i2c=None,
        address=DEFAULT_I2C_ADDRESS,
        bus_id=DEFAULT_I2C_BUS_ID,
        frequency=DEFAULT_I2C_FREQUENCY,
        i2c_factory=None,
        pin_factory=None,
    ):
        """Create an ES8311 control object with an existing or constructed I2C bus."""
        if i2c is None:
            i2c = create_i2c(
                bus_id=bus_id,
                frequency=frequency,
                i2c_factory=i2c_factory,
                pin_factory=pin_factory,
            )
        self.i2c = i2c
        self.address = address

    def scan(self):
        """Return the current I2C scan result as an immutable tuple."""
        return tuple(self.i2c.scan())

    def detect_address(self, expected_addresses=EXPECTED_I2C_ADDRESSES):
        """Return the detected ES8311 address or None when it is absent."""
        return find_expected_address(self.scan(), expected_addresses)

    def require_codec(self):
        """Ensure an expected ES8311 address is present and select it."""
        addresses = self.scan()
        detected = find_expected_address(addresses)
        if detected is None:
            raise ES8311CodecError(
                "ES8311 not found on I2C scan; found {}".format(format_i2c_addresses(addresses))
            )
        self.address = detected
        return detected

    def write_register(self, register, value):
        """Write a single ES8311 register value."""
        self.i2c.writeto_mem(self.address, register, bytearray((value & 0xFF,)))

    def read_register(self, register):
        """Read a single ES8311 register value."""
        data = self.i2c.readfrom_mem(self.address, register, 1)
        return data[0]

    def write_sequence(self, sequence):
        """Write a sequence of ``(register, value)`` pairs to the codec."""
        for register, value in sequence:
            self.write_register(register, value)

    def initialize(self, mode=MODE_BOTH):
        """Detect the codec and write the requested initialization sequence."""
        self.require_codec()
        sequence = initialization_sequence(mode)
        self.write_sequence(sequence)
        return sequence

    def initialize_input(self):
        """Initialize the ES8311 microphone input path."""
        return self.initialize(MODE_INPUT)

    def initialize_output(self):
        """Initialize the ES8311 speaker output path with the DAC muted."""
        return self.initialize(MODE_OUTPUT)

    def shutdown(self):
        """Write the ES8311 low-power shutdown sequence."""
        self.require_codec()
        self.write_sequence(SHUTDOWN_SEQUENCE)
        return SHUTDOWN_SEQUENCE

    def set_dac_muted(self, muted=True):
        """Mute or unmute the ES8311 DAC without changing other DAC bits."""
        current = self.read_register(REG_DAC_31)
        if muted:
            updated = current | DAC_MUTE_MASK
        else:
            updated = current & ~DAC_MUTE_MASK
        self.write_register(REG_DAC_31, updated)
        return updated
