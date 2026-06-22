#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${SCRIPT_DIR}/tools"
SETUP_SCRIPT="${TOOLS_DIR}/setup_micropython_tools.sh"
TOOLS_ROOT="${TOOLS_DIR}/.local"
VENV_DIR="${TOOLS_ROOT}/micropython-venv"
DOWNLOAD_DIR="${TOOLS_ROOT}/downloads/firmware"
LIB_ROOT="${TOOLS_ROOT}/micropython-libs"
LIB_DIR="${LIB_ROOT}/lib"
MICROPYTHON_BOARD_URL="https://micropython.org/download/ESP32_GENERIC_S3/"
MICROPYTHON_BASE_URL="https://micropython.org"

PORT="${AIPI_SERIAL_PORT:-}"
APP_DIR=""
FIRMWARE_URL="${AIPI_MICROPYTHON_FIRMWARE_URL:-latest}"
BAUD="460800"
ASSUME_YES=0
SKIP_ERASE=0

usage() {
  cat <<'USAGE'
Usage: ./install.sh [options]

Flash MicroPython firmware to the connected AIPI-Lite and copy application
source over USB-C with mpremote.

Options:
  --port PORT             Serial port, for example /dev/cu.usbmodem31101.
  --app-dir DIR           Application directory to upload instead of the current
                          repository baseline.
  --firmware-url URL      MicroPython firmware .bin URL. Defaults to latest
                          stable ESP32_GENERIC_S3 from micropython.org.
  --baud RATE             Flash baud rate. Default: 460800.
  --skip-erase            Write firmware without first erasing flash.
  -y, --yes               Approve prerequisite setup and flashing prompts.
  -h, --help              Show this help.

Environment overrides:
  AIPI_SERIAL_PORT
  AIPI_MICROPYTHON_FIRMWARE_URL
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
      shift 2
      ;;
    --baud)
      BAUD="${2:?--baud requires a value}"
      shift 2
      ;;
    --skip-erase)
      SKIP_ERASE=1
      shift
      ;;
    -y|--yes)
      ASSUME_YES=1
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

confirm() {
  local prompt="$1"
  local answer

  if [[ "${ASSUME_YES}" -eq 1 ]]; then
    return 0
  fi

  read -r -p "${prompt} [y/N] " answer
  case "${answer}" in
    y|Y|yes|YES)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

require_command() {
  local command_name="$1"

  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "error: required command not found: ${command_name}" >&2
    exit 1
  fi
}

download_to_stdout() {
  local url="$1"

  if command -v curl >/dev/null 2>&1; then
    curl --fail --location --silent --show-error "${url}"
  elif command -v wget >/dev/null 2>&1; then
    wget --quiet --output-document=- "${url}"
  else
    echo "error: curl or wget is required to resolve the latest firmware" >&2
    exit 1
  fi
}

extract_latest_standard_firmware_url() {
  local html="$1"
  local standard_section
  local firmware_path

  standard_section="$(printf '%s\n' "${html}" | sed '/Firmware (Support for Octal-SPIRAM)/,$d')"
  firmware_path="$(
    printf '%s\n' "${standard_section}" \
      | grep -Eo '/resources/firmware/ESP32_GENERIC_S3-[^"]+\.bin' \
      | head -n 1
  )"

  if [[ -z "${firmware_path}" ]]; then
    echo "error: could not find the latest ESP32_GENERIC_S3 .bin firmware URL" >&2
    exit 1
  fi

  printf '%s%s\n' "${MICROPYTHON_BASE_URL}" "${firmware_path}"
}

resolve_firmware_url() {
  if [[ "${FIRMWARE_URL}" != "latest" ]]; then
    printf '%s\n' "${FIRMWARE_URL}"
    return
  fi

  echo "Resolving latest stable ESP32-S3 MicroPython firmware..." >&2
  extract_latest_standard_firmware_url "$(download_to_stdout "${MICROPYTHON_BOARD_URL}")"
}

firmware_filename() {
  local url="$1"
  local path="${url%%\?*}"

  basename "${path}"
}

has_esptool() {
  [[ -x "${VENV_DIR}/bin/python" ]] \
    && "${VENV_DIR}/bin/python" -m esptool version >/dev/null 2>&1
}

has_mpremote() {
  [[ -x "${VENV_DIR}/bin/mpremote" ]] \
    && "${VENV_DIR}/bin/mpremote" --help >/dev/null 2>&1
}

collect_missing_prerequisites() {
  local firmware_path="$1"
  local missing=()

  if ! has_esptool; then
    missing+=("esptool in ${VENV_DIR}")
  fi

  if ! has_mpremote; then
    missing+=("mpremote in ${VENV_DIR}")
  fi

  if [[ ! -f "${firmware_path}" ]]; then
    missing+=("MicroPython firmware image $(basename "${firmware_path}")")
  fi

  if [[ ! -d "${LIB_DIR}" ]]; then
    missing+=("staged MicroPython libraries in ${LIB_ROOT}")
  fi

  printf '%s\n' "${missing[@]}"
}

ensure_prerequisites() {
  local firmware_url="$1"
  local firmware_path="$2"
  local missing
  local setup_args

  missing="$(collect_missing_prerequisites "${firmware_path}")"
  if [[ -z "${missing}" ]]; then
    return
  fi

  cat <<EOF
Missing prerequisite components:
${missing}

These components will be installed or downloaded under tools/.local/.
EOF

  if ! confirm "Download missing components and continue"; then
    echo "aborted: prerequisites are missing" >&2
    exit 1
  fi

  setup_args=(--firmware-url "${firmware_url}")
  if [[ -n "${PORT}" ]]; then
    setup_args+=(--port "${PORT}")
  fi
  if [[ -n "${APP_DIR}" ]]; then
    setup_args+=(--app-dir "${APP_DIR}")
  fi

  bash "${SETUP_SCRIPT}" "${setup_args[@]}"
}

remote_mkdir() {
  local mpremote_bin="$1"
  local connect_target="$2"
  local remote_dir="$3"

  "${mpremote_bin}" connect "${connect_target}" fs mkdir ":${remote_dir}" >/dev/null 2>&1 || true
}

upload_file() {
  local mpremote_bin="$1"
  local connect_target="$2"
  local local_file="$3"
  local remote_file="$4"

  echo "Uploading ${local_file} -> :${remote_file}"
  "${mpremote_bin}" connect "${connect_target}" fs cp "${local_file}" ":${remote_file}"
}

upload_tree() {
  local mpremote_bin="$1"
  local connect_target="$2"
  local local_root="$3"
  local remote_root="$4"
  local directory
  local file
  local relative
  local remote_dir

  if [[ ! -d "${local_root}" ]]; then
    echo "error: application source directory not found: ${local_root}" >&2
    exit 1
  fi

  while IFS= read -r directory; do
    relative="${directory#"${local_root}"}"
    relative="${relative#/}"
    if [[ -n "${remote_root}" && -n "${relative}" ]]; then
      remote_dir="${remote_root}/${relative}"
    elif [[ -n "${remote_root}" ]]; then
      remote_dir="${remote_root}"
    else
      remote_dir="${relative}"
    fi

    if [[ -n "${remote_dir}" ]]; then
      remote_mkdir "${mpremote_bin}" "${connect_target}" "${remote_dir}"
    fi
  done < <(find "${local_root}" -type d \
    -name __pycache__ -prune -o \
    -type d -print)

  while IFS= read -r file; do
    relative="${file#"${local_root}"}"
    relative="${relative#/}"
    if [[ -n "${remote_root}" ]]; then
      upload_file "${mpremote_bin}" "${connect_target}" "${file}" "${remote_root}/${relative}"
    else
      upload_file "${mpremote_bin}" "${connect_target}" "${file}" "${relative}"
    fi
  done < <(find "${local_root}" -type d \
    -name __pycache__ -prune -o \
    -type f ! -name '*.pyc' ! -name '.DS_Store' -print)
}

upload_application() {
  local mpremote_bin="$1"
  local connect_target="$2"

  if [[ -n "${APP_DIR}" ]]; then
    upload_tree "${mpremote_bin}" "${connect_target}" "${APP_DIR}" ""
    return
  fi

  if [[ -d "${SCRIPT_DIR}/firmware/micropython" ]]; then
    upload_tree "${mpremote_bin}" "${connect_target}" "${SCRIPT_DIR}/firmware/micropython" ""
    return
  fi

  upload_file "${mpremote_bin}" "${connect_target}" "${SCRIPT_DIR}/main.py" "main.py"
  upload_file "${mpremote_bin}" "${connect_target}" "${SCRIPT_DIR}/aipi_lite_config.py" "aipi_lite_config.py"
  remote_mkdir "${mpremote_bin}" "${connect_target}" "lib"
  upload_tree "${mpremote_bin}" "${connect_target}" "${SCRIPT_DIR}/lib" "lib"
}

main() {
  local firmware_url
  local firmware_name
  local firmware_path
  local esptool_py
  local mpremote_bin
  local connect_target="auto"
  local port_args=()

  require_command python3
  [[ -f "${SETUP_SCRIPT}" ]] || {
    echo "error: setup script not found: ${SETUP_SCRIPT}" >&2
    exit 1
  }

  firmware_url="$(resolve_firmware_url)"
  firmware_name="$(firmware_filename "${firmware_url}")"
  firmware_path="${DOWNLOAD_DIR}/${firmware_name}"

  ensure_prerequisites "${firmware_url}" "${firmware_path}"

  esptool_py="${VENV_DIR}/bin/python"
  mpremote_bin="${VENV_DIR}/bin/mpremote"

  if [[ -n "${PORT}" ]]; then
    port_args=(--port "${PORT}")
    connect_target="${PORT}"
  fi

  cat <<EOF

Ready to install:
  Firmware: ${firmware_path}
  Port: ${connect_target}
  Baud: ${BAUD}
EOF

  if ! confirm "Erase/write flash and upload application source"; then
    echo "aborted: install was not confirmed" >&2
    exit 1
  fi

  if [[ "${SKIP_ERASE}" -eq 0 ]]; then
    "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" erase_flash
  fi

  "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" --baud "${BAUD}" write_flash 0 "${firmware_path}"

  echo "Waiting for MicroPython USB serial to reconnect..."
  sleep 3

  if [[ -d "${LIB_DIR}/drivers" ]]; then
    remote_mkdir "${mpremote_bin}" "${connect_target}" "lib"
    upload_tree "${mpremote_bin}" "${connect_target}" "${LIB_DIR}/drivers" "lib/drivers"
  fi

  upload_application "${mpremote_bin}" "${connect_target}"

  echo "Install complete."
}

main "$@"
