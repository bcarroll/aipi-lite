# AIPI-Lite MicroPython Application

This directory is the MicroPython application tree copied to the AIPI-Lite
ESP32-S3 image by the repository installer.

## Layout

| Path | Purpose |
| --- | --- |
| `boot.py` | Safe startup defaults. It emits serial status and does not construct GPIO pins or change GPIO10 board-power control. |
| `main.py` | Application entrypoint. It prints bring-up status and renders the boot status screen when the ST7735 driver is available. |
| `pins.py` | Central pin constants from `SPEC.md`, grouped by display, audio, status LED, button, and power. |
| `status_led.py` | WS2812/NeoPixel status LED driver for GPIO46 with named firmware states. |
| `button.py` | Active-low GPIO42 side button reader with debounce and press/release events. |
| `io_probe.py` | Explicit GPIO-only probe that cycles status LED states and prints button events. |
| `display.py` | ST7735 display wrapper, PWM backlight control, text layout, and named status screen renderer. |
| `display_probe.py` | Explicit LCD probe that cycles boot, Wi-Fi, ready, recording, processing, speaking, and error screens. |
| `aipi_lite_config.py` | Compatibility shim for the imported ST7735 baseline. |
| `lib/st7735/` | Imported ST7735 display driver and font files. |

## Firmware Image Selection

Use the root installer to resolve and flash the latest stable official
MicroPython `ESP32_GENERIC_S3` image:

```bash
./install.sh --port /dev/cu.usbmodem31101
```

Pass an explicit image when hardware testing requires a known version:

```bash
./install.sh --port /dev/cu.usbmodem31101 \
  --firmware-url https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20260406-v1.28.0.bin
```

The installer stores downloaded firmware and MicroPython tooling under ignored
`tools/.local/` paths. Do not commit firmware downloads, stock flash backups,
credentials, tokens, or local serial configuration.

## Copy and Run Workflow

The default installer uploads this full `src/` tree after flashing
MicroPython. To upload a changed application tree without changing the
firmware image, use the installer flow once prerequisites are installed, or run
the equivalent `mpremote` copy sequence from the root documentation.

On boot, expected serial output includes:

```text
boot: AIPI-Lite safe startup
boot: collecting garbage before application start
boot: GPIO10 board power left unchanged
main: AIPI-Lite MicroPython skeleton starting
main: serial bring-up active
main: GPIO10 board power left unchanged
main: safe boot leaves board_power_control on GPIO10 untouched
main: display boot status rendered
main: skeleton ready
```

If display libraries or hardware initialization are unavailable, `main.py`
prints `main: display boot status skipped: <ErrorName>` and still reaches the
skeleton-ready line.

## GPIO Status/Input Probe

After the application tree is uploaded, run the GPIO-only probe explicitly when
you want to validate the status LED and side function button:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import io_probe; io_probe.run_probe(cycles=2)"
```

The probe cycles these named LED states over the GPIO46 WS2812/NeoPixel status
LED: `offline`, `connecting`, `ready`, `recording`, `processing`, `speaking`,
and `error`. It then watches the active-low GPIO42 right function button and
prints debounced `pressed` and `released` events to serial.

This probe intentionally avoids Wi-Fi, display initialization, audio setup, and
GPIO10 board-power control.

## Display Probe

After the application tree is uploaded, run the display probe explicitly when
you want to validate the LCD, backlight, orientation, color order, and status
screen readability:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import display_probe; display_probe.run_probe(cycles=2)"
```

The probe cycles through `boot`, `wifi`, `ready`, `recording`, `processing`,
`speaking`, and `error` screens and prints each transition to serial. The
renderer uses the ST7735-compatible driver, SPI bus 1 at 20 MHz, rotation `1`,
RGB color order enabled, and GPIO3 PWM backlight control. These assumptions are
not yet physically validated on this exact unit.

## Safety Notes

- `boot.py` must remain safe to run before hardware probes. It should not
  instantiate `machine.Pin`, start Wi-Fi, configure audio, or toggle GPIO10.
- `pins.py` is declarative only. Later branches should import constants from it
  instead of repeating numeric GPIO assignments.
- `io_probe.py` is opt-in. Keep normal boot behavior safe and serial-visible so
  a failed LED or button experiment cannot block recovery access.
- `display_probe.py` is opt-in. It initializes only the LCD and backlight and
  should remain independent of Wi-Fi, audio, and GPIO10 board-power control.
- Local Wi-Fi credentials, service URLs, and operator overrides belong in
  ignored local configuration files, not in source control.
- Replacement firmware must remain local-only by default. Do not add cloud,
  telemetry, analytics, OTA, or vendor endpoints without an explicit design and
  approval step.

## Host Tests

Run the host-side regression tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

The tests use local stubs for MicroPython-only modules and do not require
attached hardware.
