# AIPI-Lite MicroPython Library Bundle

This directory is tracked application source. tools/setup_micropython_tools.sh
stages missing external MicroPython library files in place.

The current bundle contains the MicroPython libraries expected by the first
AIPI-Lite firmware bring-up:

- ST7735R display driver from micropython-nano-gui for the 128 x 128 TFT LCD.
- BoolPalette dependency used by the ST7735R driver.

MicroPython built-in modules used by the planned firmware, such as machine,
network, socket, framebuf, neopixel, and machine.I2S, come from the downloaded
ESP32-S3 MicroPython firmware image and are not copied here.

Source:
  https://github.com/peterhinch/micropython-nano-gui

License:
  MIT license downloaded to metadata/micropython-nano-gui-LICENSE.
