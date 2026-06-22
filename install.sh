#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_DIR="${SCRIPT_DIR}/tools"
SETUP_SCRIPT="${TOOLS_DIR}/setup_micropython_tools.sh"
TOOLS_ROOT="${TOOLS_DIR}/.local"
VENV_DIR="${TOOLS_ROOT}/micropython-venv"
DOWNLOAD_DIR="${TOOLS_ROOT}/downloads/firmware"
BACKUP_DIR="${TOOLS_ROOT}/backups"
LIB_ROOT="${TOOLS_ROOT}/micropython-libs"
LIB_DIR="${LIB_ROOT}/lib"
MICROPYTHON_BOARD_URL="https://micropython.org/download/ESP32_GENERIC_S3/"
MICROPYTHON_BASE_URL="https://micropython.org"

PORT="${AIPI_SERIAL_PORT:-}"
APP_DIR="${AIPI_APP_DIR:-}"
FIRMWARE_URL="${AIPI_MICROPYTHON_FIRMWARE_URL:-}"
BAUD="${AIPI_FLASH_BAUD:-}"
FLASH_SIZE="${AIPI_FLASH_SIZE:-}"
BACKUP_CHUNK_SIZE="${AIPI_BACKUP_CHUNK_SIZE:-}"
BACKUP_PATH="${AIPI_STOCK_BACKUP_PATH:-}"
RESTORE_BACKUP_PATH="${AIPI_RESTORE_BACKUP_PATH:-}"
RESET_AFTER_UPLOAD="${AIPI_RESET_AFTER_UPLOAD:-}"
CONF_FILE="${AIPI_INSTALL_CONF:-${SCRIPT_DIR}/.conf}"
ASSUME_YES=0
SKIP_ERASE=0
RESTORE_MODE=0

usage() {
  cat <<'USAGE'
Usage: ./install.sh [options]

Flash MicroPython firmware to the connected AIPI-Lite and copy application
source over USB-C with mpremote.

Options:
  --port PORT             Serial port, for example /dev/cu.usbmodem31101.
  --app-dir DIR           Application directory to upload instead of src/.
  --backup-path FILE      Stock firmware backup path. Defaults to tools/.local.
  --conf FILE             Answer/config file. Default: ./.conf.
  --firmware-url URL      MicroPython firmware .bin URL. Defaults to latest
                          stable ESP32_GENERIC_S3 from micropython.org.
  --flash-size SIZE       Stock firmware backup size. Default: 0x1000000.
  --backup-chunk-size SIZE
                          Stock backup read chunk size. Default: 0x80000.
  --baud RATE             Flash baud rate. Default: 460800.
  --no-reset              Do not reset the device after uploading source.
  --restore               Restore the backup path saved in .conf instead of
                          installing MicroPython.
  --restore-backup FILE   Restore this stock firmware backup instead of
                          installing MicroPython.
  --skip-erase            Write firmware without first erasing flash.
  -y, --yes               Approve prerequisite setup and flashing prompts.
  -h, --help              Show this help.

Environment overrides:
  AIPI_SERIAL_PORT
  AIPI_APP_DIR
  AIPI_MICROPYTHON_FIRMWARE_URL
  AIPI_FLASH_BAUD
  AIPI_FLASH_SIZE
  AIPI_BACKUP_CHUNK_SIZE
  AIPI_STOCK_BACKUP_PATH
  AIPI_RESTORE_BACKUP_PATH
  AIPI_RESET_AFTER_UPLOAD
  AIPI_INSTALL_CONF
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
    --backup-path)
      BACKUP_PATH="${2:?--backup-path requires a value}"
      shift 2
      ;;
    --conf)
      CONF_FILE="${2:?--conf requires a value}"
      shift 2
      ;;
    --firmware-url)
      FIRMWARE_URL="${2:?--firmware-url requires a value}"
      shift 2
      ;;
    --flash-size)
      FLASH_SIZE="${2:?--flash-size requires a value}"
      shift 2
      ;;
    --backup-chunk-size)
      BACKUP_CHUNK_SIZE="${2:?--backup-chunk-size requires a value}"
      shift 2
      ;;
    --baud)
      BAUD="${2:?--baud requires a value}"
      shift 2
      ;;
    --no-reset)
      RESET_AFTER_UPLOAD="no"
      shift
      ;;
    --restore)
      RESTORE_MODE=1
      shift
      ;;
    --restore-backup)
      RESTORE_MODE=1
      RESTORE_BACKUP_PATH="${2:?--restore-backup requires a value}"
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

config_get() {
  local key="$1"
  local line

  [[ -f "${CONF_FILE}" ]] || return 1

  while IFS= read -r line || [[ -n "${line}" ]]; do
    case "${line}" in
      ''|\#*)
        continue
        ;;
      "${key}="*)
        printf '%s\n' "${line#*=}"
        return 0
        ;;
    esac
  done <"${CONF_FILE}"

  return 1
}

config_has_key() {
  config_get "$1" >/dev/null
}

config_set() {
  local key="$1"
  local value="$2"
  local tmp_path="${CONF_FILE}.tmp.$$"
  local line
  local found=0

  mkdir -p "$(dirname "${CONF_FILE}")"
  touch "${CONF_FILE}"
  chmod 600 "${CONF_FILE}"

  : >"${tmp_path}"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    case "${line}" in
      "${key}="*)
        printf '%s=%s\n' "${key}" "${value}" >>"${tmp_path}"
        found=1
        ;;
      *)
        printf '%s\n' "${line}" >>"${tmp_path}"
        ;;
    esac
  done <"${CONF_FILE}"

  if [[ "${found}" -eq 0 ]]; then
    printf '%s=%s\n' "${key}" "${value}" >>"${tmp_path}"
  fi

  mv "${tmp_path}" "${CONF_FILE}"
  chmod 600 "${CONF_FILE}"
}

is_yes() {
  case "$1" in
    y|Y|yes|YES|true|TRUE|1)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

is_no() {
  case "$1" in
    n|N|no|NO|false|FALSE|0)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

confirm_from_config() {
  local key="$1"
  local prompt="$2"
  local default_answer="${3:-no}"
  local answer

  if [[ "${ASSUME_YES}" -eq 1 ]]; then
    config_set "${key}" "yes"
    return 0
  fi

  if answer="$(config_get "${key}")"; then
    if is_yes "${answer}"; then
      return 0
    fi
    if is_no "${answer}"; then
      return 1
    fi
  fi

  read -r -p "${prompt} [${default_answer}] " answer
  answer="${answer:-${default_answer}}"
  if is_yes "${answer}"; then
    config_set "${key}" "yes"
    return 0
  fi

  config_set "${key}" "no"
  return 1
}

prompt_value_from_config() {
  local key="$1"
  local prompt="$2"
  local default_value="${3:-}"
  local answer

  if answer="$(config_get "${key}")"; then
    printf '%s\n' "${answer}"
    return
  fi

  if [[ "${ASSUME_YES}" -eq 1 ]]; then
    if [[ -z "${default_value}" ]]; then
      echo "error: ${key} must be set in ${CONF_FILE} or passed on the command line" >&2
      exit 1
    fi
    config_set "${key}" "${default_value}"
    printf '%s\n' "${default_value}"
    return
  fi

  read -r -p "${prompt} [${default_value}] " answer
  answer="${answer:-${default_value}}"
  if [[ -z "${answer}" ]]; then
    echo "error: ${key} is required" >&2
    exit 1
  fi

  config_set "${key}" "${answer}"
  printf '%s\n' "${answer}"
}

prompt_serial_port() {
  local answer

  if [[ -n "${PORT}" ]]; then
    config_set "AIPI_SERIAL_PORT" "${PORT}"
    return
  fi

  if config_has_key "AIPI_SERIAL_PORT"; then
    config_set "AIPI_SERIAL_PORT" "auto"
    return
  fi

  if [[ "${ASSUME_YES}" -eq 1 ]]; then
    config_set "AIPI_SERIAL_PORT" "auto"
    return
  fi

  read -r -p "Serial port, or blank for auto-detect [auto] " answer
  PORT="${answer}"
  config_set "AIPI_SERIAL_PORT" "${PORT:-auto}"
}

apply_config_defaults() {
  local configured_value

  if [[ -z "${PORT}" ]] && configured_value="$(config_get "AIPI_SERIAL_PORT")"; then
    PORT="${configured_value}"
  fi
  if [[ "${PORT}" == "auto" ]]; then
    PORT=""
  fi

  if [[ -z "${APP_DIR}" ]] && configured_value="$(config_get "AIPI_APP_DIR")"; then
    APP_DIR="${configured_value}"
  fi

  if [[ -z "${FIRMWARE_URL}" ]] && configured_value="$(config_get "AIPI_MICROPYTHON_FIRMWARE_URL")"; then
    FIRMWARE_URL="${configured_value}"
  fi
  FIRMWARE_URL="${FIRMWARE_URL:-latest}"

  if [[ -z "${BAUD}" ]] && configured_value="$(config_get "AIPI_FLASH_BAUD")"; then
    BAUD="${configured_value}"
  fi
  BAUD="${BAUD:-460800}"

  if [[ -z "${FLASH_SIZE}" ]] && configured_value="$(config_get "AIPI_FLASH_SIZE")"; then
    FLASH_SIZE="${configured_value}"
  fi
  FLASH_SIZE="${FLASH_SIZE:-0x1000000}"

  if [[ -z "${BACKUP_CHUNK_SIZE}" ]] && configured_value="$(config_get "AIPI_BACKUP_CHUNK_SIZE")"; then
    BACKUP_CHUNK_SIZE="${configured_value}"
  fi
  BACKUP_CHUNK_SIZE="${BACKUP_CHUNK_SIZE:-0x80000}"

  if [[ -z "${BACKUP_PATH}" ]] && configured_value="$(config_get "AIPI_STOCK_BACKUP_PATH")"; then
    BACKUP_PATH="${configured_value}"
  fi

  if [[ -z "${RESTORE_BACKUP_PATH}" ]] && configured_value="$(config_get "AIPI_RESTORE_BACKUP_PATH")"; then
    RESTORE_BACKUP_PATH="${configured_value}"
  fi

  if [[ -z "${RESET_AFTER_UPLOAD}" ]] && configured_value="$(config_get "AIPI_RESET_AFTER_UPLOAD")"; then
    RESET_AFTER_UPLOAD="${configured_value}"
  fi
  RESET_AFTER_UPLOAD="${RESET_AFTER_UPLOAD:-yes}"
}

persist_config_defaults() {
  config_set "AIPI_SERIAL_PORT" "${PORT:-auto}"
  if [[ -n "${APP_DIR}" ]]; then
    config_set "AIPI_APP_DIR" "${APP_DIR}"
  fi
  if [[ -n "${RESTORE_BACKUP_PATH}" ]]; then
    config_set "AIPI_RESTORE_BACKUP_PATH" "${RESTORE_BACKUP_PATH}"
  fi
  config_set "AIPI_MICROPYTHON_FIRMWARE_URL" "${FIRMWARE_URL}"
  config_set "AIPI_FLASH_BAUD" "${BAUD}"
  config_set "AIPI_FLASH_SIZE" "${FLASH_SIZE}"
  config_set "AIPI_BACKUP_CHUNK_SIZE" "${BACKUP_CHUNK_SIZE}"
  config_set "AIPI_RESET_AFTER_UPLOAD" "${RESET_AFTER_UPLOAD}"
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
  elif command -v python3 >/dev/null 2>&1; then
    python3 - "${url}" <<'PY'
import sys
from urllib.request import urlopen

with urlopen(sys.argv[1], timeout=60) as response:
    sys.stdout.write(response.read().decode("utf-8"))
PY
  else
    echo "error: python3, curl, or wget is required to resolve the latest firmware" >&2
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
  local setup_app_dir

  missing="$(collect_missing_prerequisites "${firmware_path}")"
  if [[ -z "${missing}" ]]; then
    return
  fi

  cat <<EOF
Missing prerequisite components:
${missing}

These components will be installed or downloaded under tools/.local/.
EOF

  if ! confirm_from_config "AIPI_DOWNLOAD_PREREQUISITES" "Download missing components and continue" "no"; then
    echo "aborted: prerequisites are missing" >&2
    exit 1
  fi

  setup_args=(--firmware-url "${firmware_url}")
  if [[ -n "${PORT}" ]]; then
    setup_args+=(--port "${PORT}")
  fi
  setup_app_dir="${APP_DIR:-${SCRIPT_DIR}/src}"
  setup_args+=(--app-dir "${setup_app_dir}")

  bash "${SETUP_SCRIPT}" "${setup_args[@]}"
}

ensure_restore_prerequisites() {
  local missing=()
  local setup_args
  local setup_app_dir

  if ! has_esptool; then
    missing+=("esptool in ${VENV_DIR}")
  fi

  if [[ "${#missing[@]}" -eq 0 ]]; then
    return
  fi

  cat <<EOF
Missing restore prerequisite components:
$(printf '%s\n' "${missing[@]}")

These components will be installed under tools/.local/.
EOF

  if ! confirm_from_config "AIPI_DOWNLOAD_PREREQUISITES" "Download missing components and continue" "no"; then
    echo "aborted: restore prerequisites are missing" >&2
    exit 1
  fi

  setup_args=(--skip-firmware --skip-libraries)
  if [[ -n "${PORT}" ]]; then
    setup_args+=(--port "${PORT}")
  fi
  setup_app_dir="${APP_DIR:-${SCRIPT_DIR}/src}"
  setup_args+=(--app-dir "${setup_app_dir}")

  bash "${SETUP_SCRIPT}" "${setup_args[@]}"
}

print_bootloader_instructions() {
  cat <<'EOF'

Before flashing:
  1. Remove the four back screws from the AIPI-Lite.
  2. Hold the BOOT button under the display.
  3. Plug the device into USB-C while holding BOOT.
  4. Confirm the screen stays black and the USB serial device is visible.
EOF
}

ensure_bootloader_ready() {
  print_bootloader_instructions
  if ! confirm_from_config "AIPI_BOOTLOADER_CONFIRMED" "Confirm the device is in bootloader mode and connected" "no"; then
    echo "aborted: device bootloader confirmation is required" >&2
    exit 1
  fi
}

default_backup_path() {
  local timestamp

  timestamp="$(date +%Y%m%d-%H%M%S)"
  printf '%s/aipi-lite-stock-%s.bin\n' "${BACKUP_DIR}" "${timestamp}"
}

size_to_bytes() {
  local value="$1"
  local field_name="$2"
  local digits

  case "${value}" in
    0x*|0X*)
      digits="${value#0x}"
      digits="${digits#0X}"
      if [[ ! "${digits}" =~ ^[0-9a-fA-F]+$ ]]; then
        echo "error: ${field_name} must be a positive decimal or hex byte count" >&2
        exit 1
      fi
      printf '%d\n' "$((16#${digits}))"
      ;;
    *)
      if [[ ! "${value}" =~ ^[0-9]+$ ]]; then
        echo "error: ${field_name} must be a positive decimal or hex byte count" >&2
        exit 1
      fi
      printf '%d\n' "$((10#${value}))"
      ;;
  esac
}

positive_size_to_bytes() {
  local value="$1"
  local field_name="$2"
  local bytes

  bytes="$(size_to_bytes "${value}" "${field_name}")"
  if [[ "${bytes}" -le 0 ]]; then
    echo "error: ${field_name} must be greater than zero" >&2
    exit 1
  fi
  printf '%s\n' "${bytes}"
}

format_hex_size() {
  local bytes="$1"

  printf '0x%x\n' "${bytes}"
}

file_size_bytes() {
  local path="$1"

  if stat -f %z "${path}" >/dev/null 2>&1; then
    stat -f %z "${path}"
    return
  fi

  stat -c %s "${path}"
}

backup_file_is_complete() {
  local path="$1"
  local expected_bytes="$2"
  local actual_bytes

  [[ -f "${path}" ]] || return 1
  actual_bytes="$(file_size_bytes "${path}")"
  [[ "${actual_bytes}" -eq "${expected_bytes}" ]]
}

backup_stock_firmware() {
  local esptool_py="$1"
  shift
  local port_args=("$@")
  local flash_size_bytes
  local chunk_size_bytes
  local actual_bytes
  local tmp_path
  local chunk_path
  local offset=0
  local remaining
  local read_size
  local offset_arg
  local read_size_arg

  if [[ -z "${BACKUP_PATH}" ]]; then
    BACKUP_PATH="$(default_backup_path)"
  fi

  config_set "AIPI_STOCK_BACKUP_PATH" "${BACKUP_PATH}"

  flash_size_bytes="$(positive_size_to_bytes "${FLASH_SIZE}" "AIPI_FLASH_SIZE")"
  chunk_size_bytes="$(positive_size_to_bytes "${BACKUP_CHUNK_SIZE}" "AIPI_BACKUP_CHUNK_SIZE")"

  if [[ "${chunk_size_bytes}" -gt "${flash_size_bytes}" ]]; then
    chunk_size_bytes="${flash_size_bytes}"
  fi

  if backup_file_is_complete "${BACKUP_PATH}" "${flash_size_bytes}"; then
    echo "Using existing complete stock firmware backup: ${BACKUP_PATH}"
    return
  fi

  if [[ -f "${BACKUP_PATH}" ]]; then
    actual_bytes="$(file_size_bytes "${BACKUP_PATH}")"
    echo "Existing stock firmware backup is incomplete (${actual_bytes}/${flash_size_bytes} bytes); replacing it."
  fi

  mkdir -p "$(dirname "${BACKUP_PATH}")"
  tmp_path="${BACKUP_PATH}.tmp.$$"
  chunk_path="${BACKUP_PATH}.chunk.$$"
  rm -f "${tmp_path}" "${chunk_path}"
  : >"${tmp_path}"

  echo "Backing up stock firmware to ${BACKUP_PATH}"
  echo "Reading ${flash_size_bytes} bytes in ${chunk_size_bytes}-byte chunks."

  while [[ "${offset}" -lt "${flash_size_bytes}" ]]; do
    remaining=$((flash_size_bytes - offset))
    read_size="${chunk_size_bytes}"
    if [[ "${read_size}" -gt "${remaining}" ]]; then
      read_size="${remaining}"
    fi

    offset_arg="$(format_hex_size "${offset}")"
    read_size_arg="$(format_hex_size "${read_size}")"
    echo "Backing up flash chunk ${offset_arg}+${read_size_arg}"
    if ! "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" \
      read_flash "${offset_arg}" "${read_size_arg}" "${chunk_path}"; then
      rm -f "${tmp_path}" "${chunk_path}"
      echo "error: failed to read stock firmware backup chunk at ${offset_arg}" >&2
      exit 1
    fi

    actual_bytes="$(file_size_bytes "${chunk_path}")"
    if [[ "${actual_bytes}" -ne "${read_size}" ]]; then
      rm -f "${tmp_path}" "${chunk_path}"
      echo "error: backup chunk size mismatch (${actual_bytes}/${read_size} bytes)" >&2
      exit 1
    fi

    cat "${chunk_path}" >>"${tmp_path}"
    rm -f "${chunk_path}"
    offset=$((offset + read_size))
  done

  actual_bytes="$(file_size_bytes "${tmp_path}")"
  if [[ "${actual_bytes}" -ne "${flash_size_bytes}" ]]; then
    rm -f "${tmp_path}" "${chunk_path}"
    echo "error: stock firmware backup size mismatch (${actual_bytes}/${flash_size_bytes} bytes)" >&2
    exit 1
  fi

  mv "${tmp_path}" "${BACKUP_PATH}"
  echo "Stock firmware backup complete: ${BACKUP_PATH}"
}

resolve_restore_backup_path() {
  local configured_value

  if [[ -z "${RESTORE_BACKUP_PATH}" ]] && configured_value="$(config_get "AIPI_STOCK_BACKUP_PATH")"; then
    RESTORE_BACKUP_PATH="${configured_value}"
  fi

  if [[ -z "${RESTORE_BACKUP_PATH}" ]]; then
    RESTORE_BACKUP_PATH="$(prompt_value_from_config "AIPI_RESTORE_BACKUP_PATH" "Stock firmware backup path to restore" "")"
  fi

  if [[ ! -f "${RESTORE_BACKUP_PATH}" ]]; then
    echo "error: restore backup not found: ${RESTORE_BACKUP_PATH}" >&2
    exit 1
  fi

  config_set "AIPI_RESTORE_BACKUP_PATH" "${RESTORE_BACKUP_PATH}"
}

restore_stock_firmware() {
  local esptool_py="$1"
  shift
  local port_args=("$@")

  resolve_restore_backup_path

  cat <<EOF

Ready to restore stock firmware:
  Backup: ${RESTORE_BACKUP_PATH}
  Port: ${PORT:-auto}
  Baud: ${BAUD}
EOF

  if ! confirm_from_config "AIPI_CONFIRM_RESTORE" "Erase/write stock firmware backup" "no"; then
    echo "aborted: restore was not confirmed" >&2
    exit 1
  fi

  if [[ "${SKIP_ERASE}" -eq 0 ]]; then
    "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" erase_flash
  fi

  "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" --baud "${BAUD}" write_flash 0 "${RESTORE_BACKUP_PATH}"
  echo "Stock firmware restore complete. Power-cycle or reset the device."
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

  if [[ -d "${SCRIPT_DIR}/src" ]]; then
    upload_tree "${mpremote_bin}" "${connect_target}" "${SCRIPT_DIR}/src" ""
    return
  fi

  echo "error: application source directory not found: ${SCRIPT_DIR}/src" >&2
  exit 1
}

reset_device() {
  local mpremote_bin="$1"
  local connect_target="$2"

  if is_no "${RESET_AFTER_UPLOAD}"; then
    echo "Device reset skipped by AIPI_RESET_AFTER_UPLOAD=${RESET_AFTER_UPLOAD}."
    return
  fi

  echo "Resetting device..."
  if ! "${mpremote_bin}" connect "${connect_target}" reset; then
    echo "warning: automatic reset failed; reset or power-cycle the device manually." >&2
  fi
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

  apply_config_defaults
  prompt_serial_port
  persist_config_defaults

  if [[ -n "${PORT}" ]]; then
    port_args=(--port "${PORT}")
    connect_target="${PORT}"
  fi

  if [[ "${RESTORE_MODE}" -eq 1 ]]; then
    ensure_restore_prerequisites
    esptool_py="${VENV_DIR}/bin/python"
    ensure_bootloader_ready
    restore_stock_firmware "${esptool_py}" "${port_args[@]}"
    return
  fi

  firmware_url="$(resolve_firmware_url)"
  firmware_name="$(firmware_filename "${firmware_url}")"
  firmware_path="${DOWNLOAD_DIR}/${firmware_name}"

  ensure_prerequisites "${firmware_url}" "${firmware_path}"

  esptool_py="${VENV_DIR}/bin/python"
  mpremote_bin="${VENV_DIR}/bin/mpremote"

  ensure_bootloader_ready
  backup_stock_firmware "${esptool_py}" "${port_args[@]}"

  cat <<EOF

Ready to install:
  Firmware: ${firmware_path}
  Stock backup: ${BACKUP_PATH}
  Port: ${connect_target}
  Baud: ${BAUD}
EOF

  if ! confirm_from_config "AIPI_CONFIRM_FLASH" "Erase/write flash and upload application source" "no"; then
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
  reset_device "${mpremote_bin}" "${connect_target}"

  echo "Install complete."
}

main "$@"
