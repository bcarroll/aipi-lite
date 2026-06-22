"""Documented AIPI-Lite ESP32-S3 pin assignments.

The constants in this module mirror the hardware map in the repository
specification. Keep risky power-control pins declarative here; do not toggle
them during the safe skeleton boot sequence.
"""

# Display / ST7735-compatible TFT.
DISPLAY_BACKLIGHT = 3
DISPLAY_DC = 7
DISPLAY_CS = 15
DISPLAY_SCLK = 16
DISPLAY_MOSI = 17
DISPLAY_RESET = 18

# ES8311 audio codec control and I2S audio path.
AUDIO_I2C_SCL = 4
AUDIO_I2C_SDA = 5
AUDIO_I2S_MCLK = 6
AUDIO_I2S_DOUT = 11
AUDIO_I2S_LRCLK = 12
AUDIO_I2S_DIN = 13
AUDIO_I2S_BCLK = 14
SPEAKER_ENABLE = 9

# User I/O.
RIGHT_FUNCTION_BUTTON = 42
STATUS_LED_WS2812_DATA = 46

# Power and charge observations.
BOARD_POWER_CONTROL = 10
CHARGE_PULSE = 21

DISPLAY_PINS = {
    "backlight": DISPLAY_BACKLIGHT,
    "dc": DISPLAY_DC,
    "cs": DISPLAY_CS,
    "sclk": DISPLAY_SCLK,
    "mosi": DISPLAY_MOSI,
    "reset": DISPLAY_RESET,
}

AUDIO_PINS = {
    "i2c_scl": AUDIO_I2C_SCL,
    "i2c_sda": AUDIO_I2C_SDA,
    "i2s_mclk": AUDIO_I2S_MCLK,
    "i2s_dout": AUDIO_I2S_DOUT,
    "i2s_lrclk": AUDIO_I2S_LRCLK,
    "i2s_din": AUDIO_I2S_DIN,
    "i2s_bclk": AUDIO_I2S_BCLK,
    "speaker_enable": SPEAKER_ENABLE,
}

STATUS_LED_PINS = {
    "ws2812_data": STATUS_LED_WS2812_DATA,
}

BUTTON_PINS = {
    "right_function": RIGHT_FUNCTION_BUTTON,
}

POWER_PINS = {
    "board_power_control": BOARD_POWER_CONTROL,
    "charge_pulse": CHARGE_PULSE,
}

PIN_GROUPS = {
    "display": DISPLAY_PINS,
    "audio": AUDIO_PINS,
    "status_led": STATUS_LED_PINS,
    "button": BUTTON_PINS,
    "power": POWER_PINS,
}

DO_NOT_TOUCH_DURING_BOOT = {
    "board_power_control": BOARD_POWER_CONTROL,
}


def required_group_names():
    """Return the pin group names required by the firmware roadmap."""
    return tuple(PIN_GROUPS.keys())


def all_grouped_pins():
    """Return every grouped pin as ``(group, signal, pin_number)`` tuples."""
    grouped = []
    for group_name, group_pins in PIN_GROUPS.items():
        for signal_name, pin_number in group_pins.items():
            grouped.append((group_name, signal_name, pin_number))
    return tuple(grouped)


def grouped_pin_numbers():
    """Return all declared pin numbers from the grouped pin map."""
    return tuple(pin_number for _, _, pin_number in all_grouped_pins())
