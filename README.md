# aipi-lite

## Flash Micropython firmware to device.  Binaries are in the micropython folder.

**NOTE:** ***The AIPI-LITE device must be put in BOOTLOADER mode by removing four screws on the back of the device, then press the button under the display while plugging the device into a USB port (The screen will stay black).***  

Create a Python virtual environment:

```bash
python -m venv esp-env
```

Activate Virtual Environment:

```bash
source esp-env/bin/activate
```

Install esptool python package:

```bash
pip install esptool
```

Use esptool to flash the micropython binaries

```bash
cd micropython
python -m esptool --chip esp32s3 -b 460800 --before default-reset --after no-reset write-flash --flash-mode dio --flash-size 16MB --flash-freq 80m 0x0 bootloader.bin 0x8000 partition-table.bin 0x10000 micropython.bin
```

Once flashing via esptool completes, the AIPI-LITE device is ready to be programmed using Micropython.

Micropython binary source:
[PIBSAS/MicroPython_ESP32-S3-WROOM-1-N16R8_with_SmartConfig](https://github.com/PIBSAS/MicroPython_ESP32-S3-WROOM-1-N16R8_with_SmartConfig/releases)




## Micropython packages

### ST7735 TFT Display module

https://github.com/alastairhm/micropython-st7735

