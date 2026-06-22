# AIPI-Lite MicroPython Application

This directory is the MicroPython application tree copied to the AIPI-Lite
ESP32-S3 image by the repository installer.

## Layout

| Path | Purpose |
| --- | --- |
| `boot.py` | Safe startup defaults. It emits serial status and does not construct GPIO pins or change GPIO10 board-power control. |
| `main.py` | Skeleton application entrypoint. It prints bring-up status and runs the imported display baseline when the ST7735 driver is available. |
| `pins.py` | Central pin constants from `SPEC.md`, grouped by display, audio, status LED, button, and power. |
| `aipi_lite_config.py` | Display wiring helper for the current ST7735 baseline. |
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
main: display baseline rendered
main: skeleton ready
```

If display libraries or hardware initialization are unavailable, `main.py`
prints `main: display baseline skipped: <ErrorName>` and still reaches the
skeleton-ready line.

## Safety Notes

- `boot.py` must remain safe to run before hardware probes. It should not
  instantiate `machine.Pin`, start Wi-Fi, configure audio, or toggle GPIO10.
- `pins.py` is declarative only. Later branches should import constants from it
  instead of repeating numeric GPIO assignments.
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
