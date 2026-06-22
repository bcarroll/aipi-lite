# XORIGIN AI PI-Lite Hardware Specifications

Model number: `XY006PL01`

Last verified: 2026-06-22

This document summarizes the hardware specifications for the XORIGIN AI PI-Lite,
also published by AIPI as the AIPI Lite or AI PI-Lite. The model number comes
from the physical model sticker reported for this unit. Hardware specifications
are sourced from AIPI's public product page, product manual, battery module
page, and community reverse-engineering notes linked from AIPI.

## Product Identity

| Item | Specification |
| --- | --- |
| Product name | XORIGIN AI PI-Lite / AIPI Lite / AI PI-Lite |
| Model number | `XY006PL01` |
| Manufacturer named in manual | X-ORIGIN (Shenzhen Xuanyuan Technology Co., Ltd.) |
| Product class | ESP32-S3 smart development board with display, microphone, speaker, Wi-Fi, and cloud AI service integration |

## Core Hardware

| Component | Specification |
| --- | --- |
| Processor | ESP32-S3 |
| CPU detail | Dual-core, up to 240 MHz |
| Memory | 8 MB PSRAM |
| Storage | 16 MB Quad SPI flash |
| Display | TFT LCD |
| Display resolution | 128 x 128 pixels |
| Microphone | Single MEMS microphone |
| Microphone pickup range | Up to 5 m |
| Speaker | 8 ohm, 0.8 W speaker, quantity 1 |
| Status indicator | Multi-color status light |
| Primary control | Side function button |
| Power control | Battery module power button when running from battery only |

## Connectivity and Developer Access

| Interface | Specification |
| --- | --- |
| Wi-Fi | 2.4 GHz Wi-Fi. The product page lists 802.11 b/g/n; the full manual technical table lists 802.11 b/g. |
| Network requirement | Private/home Wi-Fi. Public networks requiring browser login are not supported. The product FAQ also states password-protected WPA2 Wi-Fi is required. |
| Bluetooth | Bluetooth 5 LE hardware is present, but AIPI states it is not currently enabled for user-facing features. |
| USB | USB Type-C for power and charging |
| Serial access | USB CDC serial and UART access |
| GPIO | Exposed GPIO for maker use |
| Flash access | Product page describes the flash as unencrypted |

## ESP32-S3 Pinout for Custom Firmware

AIPI's public manual does not publish a board schematic or complete ESP32-S3
pinout. The table below is the best-known pinout from community ESPHome
templates and teardown boot logs. Treat it as custom-firmware notation, not an
official vendor schematic. Verify pins electrically before attaching external
hardware or changing power-control behavior.

| ESP32-S3 GPIO | Signal / firmware role | Connected device | Notes |
| --- | --- | --- | --- |
| GPIO3 | LCD backlight / `lcd_backlight` | TFT LCD backlight | Used as GPIO on/off in one ESPHome template and PWM in another. |
| GPIO4 | I2C SCL | ES8311 audio codec control bus | Shared I2C bus for codec configuration. |
| GPIO5 | I2C SDA | ES8311 audio codec control bus | Shared I2C bus for codec configuration. |
| GPIO6 | I2S MCLK | ES8311 audio codec | Master clock for audio codec. |
| GPIO7 | LCD D/C | ST7735-compatible TFT LCD | SPI display data/command select. |
| GPIO9 | `speaker_enable` | Speaker amplifier / audio output path | Community firmware disables this during microphone capture to reduce audio noise. |
| GPIO10 | `board_power` | Board power-control path | Observed in one community voice-bridge template; verify before use. |
| GPIO11 | I2S DOUT | ES8311 speaker output path | ESP32 audio output to codec/speaker path. |
| GPIO12 | I2S LRCLK / WS | ES8311 audio codec | I2S word-select / left-right clock. |
| GPIO13 | I2S DIN | ES8311 microphone input path | Codec/microphone audio input to ESP32. |
| GPIO14 | I2S BCLK | ES8311 audio codec | I2S bit clock. |
| GPIO15 | LCD CS | ST7735-compatible TFT LCD | SPI display chip select. |
| GPIO16 | SPI SCLK | ST7735-compatible TFT LCD | SPI display clock. |
| GPIO17 | SPI MOSI | ST7735-compatible TFT LCD | SPI display data output from ESP32. |
| GPIO18 | LCD RESET | ST7735-compatible TFT LCD | Display reset. |
| GPIO21 | Charge pulse / `CHRG` input | Battery charging status logic | Stock boot logs initialize a pulse counter on this input. |
| GPIO42 | Right function button | Side function button | Active-low / inverted in ESPHome templates. |
| GPIO46 | WS2812 data | Single addressable status LED | Community notes identify one WS2812-style RGB LED using GRB order. |

Known unconfirmed or indirect controls:

- Left/power button: community notes indicate the left tactile button is not
  useful as a normal direct GPIO input in ESPHome and appears tied to
  sleep/wake or power-management behavior.
- BOOT button: a physical BOOT button exists under the cover for flashing, but
  the reviewed sources did not publish a custom-firmware GPIO assignment.
- USB serial/JTAG: exposed through the ESP32-S3 native USB interface, not listed
  as an application GPIO above.

## Power and Battery

| Item | Specification |
| --- | --- |
| Wired power | USB Type-C power input |
| Battery module | 450 mAh rechargeable magnetic snap-on module |
| Battery charging | Charges through USB Type-C while the device remains usable |
| Charge indicator | Yellow screen-bottom bar while charging below full; green bar when fully charged |
| Low-battery indicator | Red screen-bottom bar below 20 percent |
| Battery-only auto-off | Powers down after five minutes in standby when running only on the battery module |

## Physical and Environmental

| Parameter | Specification |
| --- | --- |
| Weight | 25 g |
| Dimensions | 55.5 x 47.5 x 7.8 mm |
| Operating temperature | -20 to 55 degrees C |
| Water resistance | Not waterproof; vendor instructions say not to wet, submerge, or use in rain |
| Magnetic components | Contains magnets; vendor safety guidance says to keep magnet-sensitive items and implanted medical devices at least 15 cm away |

## Included / Related Hardware

Current AIPI product materials list the AIPI Lite device, a 450 mAh battery
module, and a quick start guide as included hardware/documentation. The separate
AIPI Lite Battery Modules product page describes the battery as a 450 mAh
high-density, magnetic snap-on module.

## Federal Use Considerations

The public materials reviewed for this specification do not state U.S. Federal
procurement, FedRAMP, FIPS, Section 508, FCC, UL, or supply-chain compliance
certifications for this model. Federal deployment or procurement decisions should
therefore verify applicable compliance artifacts directly with the vendor before
use.

## Sources

- AIPI Lite product page: https://aipi.com/products/aipi-lite
- AIPI setup manual page: https://aipi.com/pages/manual
- AIPI full product manual: https://static.aipi.com/AIPI_InstructionBook/AIPI_InstructionBook.html
- AIPI Lite Battery Modules product page: https://aipi.com/products/xorigin-ai-pi-battery-modules
- AIPI-linked ESPHome template: https://github.com/sticks918/AIPI-Lite-ESPHome/blob/main/aipi.yaml
- AIPI-linked teardown blog: https://www.robertlipe.com/449-2/
- Community voice bridge template: https://github.com/noise754/AIPI-Lite-Voice-Bridge/blob/main/aipi.yaml
