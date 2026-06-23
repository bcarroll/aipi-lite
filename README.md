# aipi-lite

Local-only replacement firmware work for the XORIGIN AI PI-Lite / AIPI Lite.

## Current MicroPython Workflow

Use the repository installer to resolve the latest stable ESP32-S3 MicroPython
firmware, flash it, and upload the current application baseline:

```bash
./install.sh --port /dev/cu.usbmodem31101
```

Before any installer actions, `install.sh` runs `git pull --ff-only` from the
repository root and restarts itself once so the active script is current. Use
`--skip-self-update` or `AIPI_SKIP_SELF_UPDATE=1` only for intentional offline
or pinned-revision runs.

For issue reporting or future troubleshooting context, add `--debug` to keep a
sanitized installer transcript and environment summary under
`tools/.local/debug/`:

```bash
./install.sh --debug --port /dev/cu.usbmodem31101
```

The debug file path is printed during the run. Use `--debug-file FILE` when a
specific GitHub issue artifact path is needed. The generated file redacts common
secrets, credentials, SSIDs, tokens, and MAC-like identifiers before writing the
transcript.

If local prerequisites are missing, the installer prompts before downloading or
installing components under ignored `tools/.local/`, then continues with the
flash and upload workflow after approval.

Installer answers are stored in a root `.conf` file, which is ignored by Git.
The script reads that file on later runs for values such as serial port,
download approval, bootloader confirmation, flash approval, backup path, and
reset preference.

Run without `--port` to let `esptool` and `mpremote` auto-detect the attached
device:

```bash
./install.sh
```

Use a specific MicroPython firmware build when the latest standard
ESP32_GENERIC_S3 image is not the right target:

```bash
./install.sh --port /dev/cu.usbmodem31101 \
  --firmware-url https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20260406-v1.28.0.bin
```

Before erasing or writing flash, the installer now requires bootloader
confirmation and backs up the 16 MB stock flash image to `tools/.local/backups/`
unless `.conf` points at an existing exact-size backup. The backup read is
chunked by default so a failed transfer cannot be mistaken for a complete stock
image on the next run. If a backup stalls on a specific USB setup, reduce the
chunk size with `--backup-chunk-size 0x40000` or set
`AIPI_BACKUP_CHUNK_SIZE=0x40000` in `.conf`. The installer also retries failed
backup chunks down to 4 KiB without resetting the chip between chunks; a repeat
failure at the same offset should be treated as an address-specific read
failure or an unstable USB path.

The user still needs to put the AIPI-Lite into ESP32-S3 bootloader mode and
connect the device over USB-C because those are physical actions.

Bootloader access currently requires removing the four back screws, pressing the
button under the display while plugging the device into USB-C, and confirming
that the screen remains black.

After flashing and copying `src/`, the installer attempts to reset the device.
Set `AIPI_RESET_AFTER_UPLOAD=no` in `.conf` or pass `--no-reset` to skip that
step.

Backup, restore, expected output, and safety details are documented in
[RECOVERY.md](RECOVERY.md).

See [tools/README.md](tools/README.md) for lower-level setup tooling.

## MicroPython Application Skeleton

The MicroPython source under `src/` now provides the first safe application
skeleton, GPIO probe, and display status probe:

- `src/boot.py`
- `src/main.py`
- `src/pins.py`
- `src/status_led.py`
- `src/button.py`
- `src/io_probe.py`
- `src/display.py`
- `src/display_probe.py`
- `src/aipi_lite_config.py`
- `src/es8311.py`
- `src/audio_probe.py`
- `src/audio_capture.py`
- `src/capture_probe.py`
- `src/wifi_config.py`
- `src/local_endpoint.py`
- `src/wifi_probe.py`
- `src/lib/st7735/`

`boot.py` emits serial-visible safe startup status without constructing GPIO
pins or touching GPIO10 board-power control. `main.py` prints the bring-up
sequence, drives GPIO9 speaker enable low, and renders a best-effort boot
status screen through the reusable display wrapper. `pins.py` centralizes the
documented pin map for later hardware probe branches. `aipi_lite_config.py`
remains as a compatibility shim for the imported display baseline. `es8311.py`
provides codec I2C control and the speaker amplifier gate; `audio_probe.py` is
the opt-in ES8311 hardware probe. `audio_capture.py` and `capture_probe.py`
add bounded 16 kHz 16-bit mono microphone capture and WAV packaging helpers for
the ES8311/I2S path. `wifi_probe.py` connects only to configured local Wi-Fi
and calls only a local `/health` endpoint after endpoint policy validation
passes.

The GPIO status/input probe remains opt-in so normal boot stays recoverable. To
cycle the GPIO46 WS2812/NeoPixel status LED states and print debounced GPIO42
right-function-button events after uploading `src/`, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import io_probe; io_probe.run_probe(cycles=2)"
```

The probe does not start Wi-Fi, initialize audio, initialize the display, or
touch GPIO10 board-power control.

The display probe is also opt-in. To cycle the 128 x 128 LCD through boot,
Wi-Fi, ready, recording, processing, speaking, and error screens, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import display_probe; display_probe.run_probe(cycles=2)"
```

The display probe initializes only the ST7735-compatible LCD and GPIO3
backlight. It does not start Wi-Fi, audio, or GPIO10 board-power control.

The ES8311 codec probe remains opt-in as well. After uploading `src/`, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import audio_probe; audio_probe.run_probe()"
```

It scans the GPIO4/GPIO5 I2C bus for expected codec address `0x18`, writes the
16 kHz 16-bit initialization registers, keeps the DAC muted, briefly pulses the
GPIO9 speaker amplifier gate, and disables the gate before returning.

The microphone capture probe is opt-in. To initialize ES8311 input, capture a
short bounded PCM sample, and print level/clipping metrics, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import capture_probe; capture_probe.run_probe()"
```

The capture probe keeps GPIO9 speaker enable disabled and does not write audio
to flash by default.

The Wi-Fi/local-service probe requires an ignored `src/local_wifi_config.py`
file on the device. After uploading `src/`, run:

```bash
mpremote connect /dev/cu.usbmodem31101 exec "import wifi_probe; wifi_probe.run_probe()"
```

The probe validates the configured endpoint before connecting to Wi-Fi. It
accepts RFC1918 IPv4 addresses, loopback/link-local IPv4 for bench testing,
`.local` names, and explicitly approved local hostnames. Public internet
endpoints are rejected by default and are not contacted.

See [src/README.md](src/README.md) for firmware image selection, upload, serial
log, and safety notes for the MicroPython application tree.

## Host-side tests

Run the host-side regression tests from the repository root:

```bash
python3 -m unittest discover -s tests -v
```

These tests use local stubs for MicroPython-only modules so they can validate
display layout, GPIO logic, and setup tooling without an attached AIPI-Lite
device.
