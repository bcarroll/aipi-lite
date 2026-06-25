#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
TOOLS_ROOT="${SCRIPT_DIR}/.local"
VENV_DIR="${TOOLS_ROOT}/micropython-venv"
DOWNLOAD_DIR="${TOOLS_ROOT}/downloads/firmware"
DEFAULT_FIRMWARE_URL="https://micropython.org/resources/firmware/ESP32_GENERIC_S3-20260406-v1.28.0.bin"

FIRMWARE_URL="${AIPI_MICROPYTHON_FIRMWARE_URL:-${DEFAULT_FIRMWARE_URL}}"
PORT="${AIPI_SERIAL_PORT:-}"
APP_DIR="${REPO_ROOT}/src"
LIB_ROOT="${APP_DIR}/lib"
LIB_DIR="${LIB_ROOT}"
DOWNLOAD_FIRMWARE=1
DOWNLOAD_LIBRARIES=1

MICROPYTHON_LIBRARY_FILES=(
  "drivers/boolpalette.py|https://raw.githubusercontent.com/peterhinch/micropython-nano-gui/master/drivers/boolpalette.py"
  "drivers/st7735r/package.json|https://raw.githubusercontent.com/peterhinch/micropython-nano-gui/master/drivers/st7735r/package.json"
  "drivers/st7735r/st7735r.py|https://raw.githubusercontent.com/peterhinch/micropython-nano-gui/master/drivers/st7735r/st7735r.py"
  "drivers/st7735r/st7735r_4bit.py|https://raw.githubusercontent.com/peterhinch/micropython-nano-gui/master/drivers/st7735r/st7735r_4bit.py"
  "drivers/st7735r/st7735r144.py|https://raw.githubusercontent.com/peterhinch/micropython-nano-gui/master/drivers/st7735r/st7735r144.py"
  "drivers/st7735r/st7735r144_4bit.py|https://raw.githubusercontent.com/peterhinch/micropython-nano-gui/master/drivers/st7735r/st7735r144_4bit.py"
  "metadata/micropython-nano-gui-LICENSE|https://raw.githubusercontent.com/peterhinch/micropython-nano-gui/master/LICENSE"
)

usage() {
  cat <<'USAGE'
Usage: tools/setup_micropython_tools.sh [options]

Downloads repo-local tools for flashing MicroPython firmware and uploading
MicroPython application source to the AIPI-Lite over USB-C.

Options:
  --port PORT             Serial port, for example /dev/cu.usbmodem31101.
  --app-dir DIR           MicroPython application directory to upload.
  --firmware-url URL      MicroPython firmware .bin URL to download.
  --skip-firmware         Install tools but do not download firmware.
  --skip-libraries        Install tools but do not download MicroPython libs.
  -h, --help              Show this help.

Environment overrides:
  AIPI_SERIAL_PORT
  AIPI_MICROPYTHON_FIRMWARE_URL

Host tooling and firmware downloads are placed under tools/.local/, which is
ignored by Git. MicroPython library source is staged under src/lib/.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)
      PORT="${2:?--port requires a value}"
      shift 2
      ;;
    --app-dir)
      APP_DIR="${2:?--app-dir requires a value}"
      shift 2
      ;;
    --firmware-url)
      FIRMWARE_URL="${2:?--firmware-url requires a value}"
      DOWNLOAD_FIRMWARE=1
      shift 2
      ;;
    --skip-firmware)
      DOWNLOAD_FIRMWARE=0
      shift
      ;;
    --skip-libraries)
      DOWNLOAD_LIBRARIES=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

LIB_ROOT="${APP_DIR}/lib"
LIB_DIR="${LIB_ROOT}"

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "error: required command not found: ${command_name}" >&2
    exit 1
  fi
}

firmware_filename() {
  local url="$1"
  local path="${url%%\?*}"

  basename "${path}"
}

download_file() {
  local url="$1"
  local output_path="$2"

  mkdir -p "$(dirname "${output_path}")"

  if [[ -f "${output_path}" ]]; then
    echo "already downloaded: ${output_path}"
    return
  fi

  if command -v curl >/dev/null 2>&1; then
    curl --fail --location --show-error --output "${output_path}" "${url}"
  elif command -v wget >/dev/null 2>&1; then
    wget --output-document="${output_path}" "${url}"
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "${url}" "${output_path}" <<'PY'
import sys
from pathlib import Path
from urllib.request import urlopen

url = sys.argv[1]
output_path = Path(sys.argv[2])

with urlopen(url, timeout=60) as response:
    output_path.write_bytes(response.read())
PY
  else
    echo "error: python3, curl, or wget is required to download firmware" >&2
    exit 1
  fi
}

write_library_manifest() {
  local manifest_path="${LIB_ROOT}/AIPI-LITE-MICROPYTHON-LIBRARIES.md"

  mkdir -p "${LIB_ROOT}"
  cat >"${manifest_path}" <<EOF
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
EOF
}

download_micropython_libraries() {
  local entry
  local destination
  local url

  for entry in "${MICROPYTHON_LIBRARY_FILES[@]}"; do
    destination="${entry%%|*}"
    url="${entry#*|}"
    download_file "${url}" "${LIB_ROOT}/${destination}"
  done

  write_library_manifest
}

print_next_steps() {
  local firmware_path="$1"
  local esptool_cmd="${VENV_DIR}/bin/python -m esptool"
  local mpremote_cmd="${VENV_DIR}/bin/mpremote"
  local port_arg=""
  local connect_arg="auto"

  if [[ -n "${PORT}" ]]; then
    port_arg="--port ${PORT}"
    connect_arg="${PORT}"
  fi

  cat <<EOF

Tooling is ready.

Installed:
  ${VENV_DIR}/bin/python
  ${VENV_DIR}/bin/mpremote

Firmware image:
  ${firmware_path}

MicroPython library source:
  ${LIB_DIR}

Before flashing:
  1. Back up stock firmware.
  2. Put the AIPI-Lite into ESP32-S3 bootloader mode.
  3. Connect the device over USB-C.

Erase flash:
  ${esptool_cmd} --chip esp32s3 ${port_arg} erase_flash
EOF

  if [[ "${firmware_path}" != "not downloaded" ]]; then
    cat <<EOF

Write MicroPython firmware:
  ${esptool_cmd} --chip esp32s3 ${port_arg} --baud 460800 write_flash 0 ${firmware_path}
EOF
  else
    cat <<EOF

MicroPython firmware was not downloaded. Re-run without --skip-firmware or pass
--firmware-url before writing firmware.
EOF
  fi

  cat <<EOF

Open a MicroPython REPL:
  ${mpremote_cmd} connect ${connect_arg} repl
EOF

  if [[ -d "${APP_DIR}" ]]; then
    cat <<EOF

Upload application source:
  ${mpremote_cmd} connect ${connect_arg} fs cp -r ${APP_DIR}/ :

The application upload includes MicroPython libraries from:
  ${APP_DIR}/lib
EOF
  else
    cat <<EOF

Application source directory does not exist yet:
  ${APP_DIR}

After src/ exists, upload it with:
  ${mpremote_cmd} connect ${connect_arg} fs cp -r src/ :
EOF
  fi
}

main() {
  local firmware_name
  local firmware_path

  require_command python3

  mkdir -p "${TOOLS_ROOT}" "${DOWNLOAD_DIR}"

  if [[ ! -d "${VENV_DIR}" ]]; then
    python3 -m venv "${VENV_DIR}"
  fi

  "${VENV_DIR}/bin/python" -m pip install --upgrade pip
  "${VENV_DIR}/bin/python" -m pip install --upgrade esptool mpremote

  firmware_path="not downloaded"
  if [[ "${DOWNLOAD_FIRMWARE}" -eq 1 ]]; then
    firmware_name="$(firmware_filename "${FIRMWARE_URL}")"
    firmware_path="${DOWNLOAD_DIR}/${firmware_name}"
    download_file "${FIRMWARE_URL}" "${firmware_path}"
  fi

  if [[ "${DOWNLOAD_LIBRARIES}" -eq 1 ]]; then
    download_micropython_libraries
  fi

  "${VENV_DIR}/bin/python" -m esptool version
  "${VENV_DIR}/bin/mpremote" --help >/dev/null

  print_next_steps "${firmware_path}"
}

main "$@"
