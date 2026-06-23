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
BACKUP_MIN_CHUNK_SIZE="${AIPI_BACKUP_MIN_CHUNK_SIZE:-}"
BACKUP_PATH="${AIPI_STOCK_BACKUP_PATH:-}"
RESTORE_BACKUP_PATH="${AIPI_RESTORE_BACKUP_PATH:-}"
RESET_AFTER_UPLOAD="${AIPI_RESET_AFTER_UPLOAD:-}"
CONF_FILE="${AIPI_INSTALL_CONF:-${SCRIPT_DIR}/.conf}"
SKIP_SELF_UPDATE="${AIPI_SKIP_SELF_UPDATE:-0}"
DEBUG_ENABLED="${AIPI_INSTALL_DEBUG:-0}"
DEBUG_FILE="${AIPI_INSTALL_DEBUG_FILE:-}"
TRACE_ENABLED="${AIPI_INSTALL_TRACE:-0}"
TRACE_FILE="${AIPI_INSTALL_TRACE_FILE:-}"
ASSUME_YES=0
SKIP_ERASE=0
RESTORE_MODE=0
CLEAN_TOOLS=0
DEBUG_CONTEXT_WRITTEN=0

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
  --backup-min-chunk-size SIZE
                          Smallest retry chunk size. Default: 0x1000.
  --baud RATE             Flash baud rate. Default: 460800.
  --no-reset              Do not reset the device after uploading source.
  --restore               Restore the backup path saved in .conf instead of
                          installing MicroPython.
  --restore-backup FILE   Restore this stock firmware backup instead of
                          installing MicroPython.
  --skip-erase            Write firmware without first erasing flash.
  --skip-self-update      Do not run git pull before installer actions.
  --clean-tools, --clean-prereqs
                          Delete downloaded prerequisite artifacts under
                          tools/.local and exit. Preserves stock backups,
                          debug logs, and dev install captures.
  --debug                 Write a sanitized installer debug file for issues.
  --debug-file FILE       Write --debug output to this file.
  --trace                 Enable --debug and write detailed install/device
                          trace data for hardware feedback analysis.
  --trace-file FILE       Write --trace output to this file.
  -y, --yes               Approve prerequisite setup and flashing prompts.
  -h, --help              Show this help.

Environment overrides:
  AIPI_SERIAL_PORT
  AIPI_APP_DIR
  AIPI_MICROPYTHON_FIRMWARE_URL
  AIPI_FLASH_BAUD
  AIPI_FLASH_SIZE
  AIPI_BACKUP_CHUNK_SIZE
  AIPI_BACKUP_MIN_CHUNK_SIZE
  AIPI_STOCK_BACKUP_PATH
  AIPI_RESTORE_BACKUP_PATH
  AIPI_RESET_AFTER_UPLOAD
  AIPI_INSTALL_CONF
  AIPI_SKIP_SELF_UPDATE
  AIPI_INSTALL_DEBUG
  AIPI_INSTALL_DEBUG_FILE
  AIPI_INSTALL_TRACE
  AIPI_INSTALL_TRACE_FILE
USAGE
}

remove_path_if_present() {
  local path="$1"

  if [[ -e "${path}" || -L "${path}" ]]; then
    echo "Deleting prerequisite artifact: ${path}"
    rm -rf -- "${path}"
  else
    echo "Already clean: ${path}"
  fi
}

clean_prerequisite_artifacts() {
  echo "Cleaning downloaded prerequisite artifacts under ${TOOLS_ROOT}..."
  remove_path_if_present "${VENV_DIR}"
  remove_path_if_present "${DOWNLOAD_DIR}"
  remove_path_if_present "${LIB_ROOT}"
  rmdir "${TOOLS_ROOT}/downloads" 2>/dev/null || true
  echo "Preserved local artifacts:"
  echo "  ${BACKUP_DIR}"
  echo "  ${TOOLS_ROOT}/debug"
  echo "  ${TOOLS_ROOT}/dev-install"
  echo "Prerequisite cleanup complete."
}

preparse_preflight_flags() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --skip-self-update)
        SKIP_SELF_UPDATE=1
        shift
        ;;
      --clean-tools|--clean-prereqs)
        CLEAN_TOOLS=1
        SKIP_SELF_UPDATE=1
        shift
        ;;
      --debug)
        DEBUG_ENABLED=1
        shift
        ;;
      --debug-file)
        DEBUG_ENABLED=1
        DEBUG_FILE="${2:?--debug-file requires a value}"
        shift 2
        ;;
      --debug-file=*)
        DEBUG_ENABLED=1
        DEBUG_FILE="${1#*=}"
        shift
        ;;
      --trace)
        DEBUG_ENABLED=1
        TRACE_ENABLED=1
        shift
        ;;
      --trace-file)
        DEBUG_ENABLED=1
        TRACE_ENABLED=1
        TRACE_FILE="${2:?--trace-file requires a value}"
        shift 2
        ;;
      --trace-file=*)
        DEBUG_ENABLED=1
        TRACE_ENABLED=1
        TRACE_FILE="${1#*=}"
        shift
        ;;
      --)
        return
        ;;
      *)
        shift
        ;;
    esac
  done
}

is_truthy_value() {
  case "$1" in
    y|Y|yes|YES|true|TRUE|1)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

redact_stream() {
  sed -E \
    -e 's#(https?://)[^/@[:space:]]+:[^/@[:space:]]+@#\1<redacted>@#g' \
    -e 's#(https?://)[^/@[:space:]]+@#\1<redacted>@#g' \
    -e 's/([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Pp][Aa][Ss][Ss][Ww][Dd]|[Tt][Oo][Kk][Ee][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Kk][Ee][Yy])=([^[:space:]]+)/\1=<redacted>/g' \
    -e 's/([Ss][Ss][Ii][Dd])=([^[:space:]]+)/\1=<redacted>/g' \
    -e 's/([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}/<redacted-mac>/g'
}

default_debug_file() {
  local timestamp

  timestamp="$(date -u +%Y%m%d-%H%M%S)"
  printf '%s/debug/install-debug-%s.txt\n' "${TOOLS_ROOT}" "${timestamp}"
}

default_trace_file() {
  local timestamp

  timestamp="$(date -u +%Y%m%d-%H%M%S)"
  printf '%s/debug/install-trace-%s.txt\n' "${TOOLS_ROOT}" "${timestamp}"
}

quote_args() {
  local arg

  for arg in "$@"; do
    printf '%q ' "${arg}"
  done
  printf '\n'
}

trace_enabled() {
  is_truthy_value "${TRACE_ENABLED}" && [[ -n "${TRACE_FILE:-}" ]]
}

trace_line() {
  if ! trace_enabled; then
    return
  fi

  printf '%s\n' "$*" | redact_stream >>"${TRACE_FILE}"
}

trace_event() {
  local event="$1"
  shift
  local field

  if ! trace_enabled; then
    return
  fi

  {
    printf 'ts=%s event=%s' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${event}"
    for field in "$@"; do
      printf ' %s' "${field}"
    done
    printf '\n'
  } | redact_stream >>"${TRACE_FILE}"
}

debug_command_output() {
  local label="$1"
  shift
  local output
  local status

  if ! is_truthy_value "${DEBUG_ENABLED}"; then
    return
  fi

  {
    printf '\n### %s\n' "${label}"
    printf '$'
    printf ' %q' "$@"
    printf '\n'
  } >>"${DEBUG_FILE}"

  set +e
  output="$("$@" 2>&1)"
  status=$?
  set -e

  {
    printf '%s\n' "${output}"
    if [[ "${status}" -ne 0 ]]; then
      printf '(exit %s)\n' "${status}"
    fi
  } | redact_stream >>"${DEBUG_FILE}"
}

trace_command_output() {
  local label="$1"
  shift
  local output
  local status
  local command_line

  if ! trace_enabled; then
    return
  fi

  command_line="$(quote_args "$@" | redact_stream)"
  trace_event "probe_start" "label=${label}"
  {
    printf '\n### %s\n' "${label}"
    printf '$ %s\n' "${command_line}"
  } >>"${TRACE_FILE}"

  set +e
  output="$("$@" 2>&1)"
  status=$?
  set -e

  {
    printf '%s\n' "${output}"
    printf '(exit %s)\n' "${status}"
  } | redact_stream >>"${TRACE_FILE}"
  trace_event "probe_end" "label=${label}" "status=${status}"
}

run_with_trace() {
  local phase="$1"
  shift
  local status
  local command_line

  command_line="$(quote_args "$@" | redact_stream)"
  trace_event "command_start" "phase=${phase}"
  trace_line "command=${command_line}"

  set +e
  "$@"
  status=$?
  set -e

  trace_event "command_end" "phase=${phase}" "status=${status}"
  return "${status}"
}

sha256_file() {
  local path="$1"

  if command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "${path}" | awk '{print $1}'
  elif command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${path}" | awk '{print $1}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "${path}" | awk '{print $NF}'
  else
    python3 - "${path}" <<'PY'
import hashlib
import sys

with open(sys.argv[1], "rb") as handle:
    digest = hashlib.sha256()
    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
        digest.update(chunk)
print(digest.hexdigest())
PY
  fi
}

trace_file_metadata() {
  local label="$1"
  local path="$2"
  local bytes
  local digest

  if ! trace_enabled; then
    return
  fi

  if [[ ! -f "${path}" ]]; then
    trace_event "file" "label=${label}" "path=${path}" "status=missing"
    return
  fi

  bytes="$(file_size_bytes "${path}")"
  digest="$(sha256_file "${path}")"
  trace_event "file" "label=${label}" "path=${path}" "status=present" "bytes=${bytes}" "sha256=${digest}"
}

trace_source_inventory() {
  local label="$1"
  local root="$2"
  local file
  local relative
  local bytes
  local digest
  local file_count=0
  local byte_count=0

  if ! trace_enabled; then
    return
  fi

  if [[ ! -d "${root}" ]]; then
    trace_event "source_inventory" "label=${label}" "path=${root}" "status=missing"
    return
  fi

  while IFS= read -r file; do
    file_count=$((file_count + 1))
    bytes="$(file_size_bytes "${file}")"
    byte_count=$((byte_count + bytes))
  done < <(find "${root}" -type d \
    -name __pycache__ -prune -o \
    -type f ! -name '*.pyc' ! -name '.DS_Store' -print)

  trace_event "source_inventory" "label=${label}" "path=${root}" "status=present" "files=${file_count}" "bytes=${byte_count}"

  while IFS= read -r file; do
    relative="${file#"${root}"}"
    relative="${relative#/}"
    bytes="$(file_size_bytes "${file}")"
    digest="$(sha256_file "${file}")"
    trace_event "source_file" "label=${label}" "path=${relative}" "bytes=${bytes}" "sha256=${digest}"
  done < <(find "${root}" -type d \
    -name __pycache__ -prune -o \
    -type f ! -name '*.pyc' ! -name '.DS_Store' -print)
}

trace_device_probe() {
  local esptool_py="$1"
  shift
  local port_args=("$@")

  if ! trace_enabled; then
    return
  fi

  trace_event "device_probe" "tool=esptool" "status=start"
  trace_command_output "esptool chip id" "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" --before no-reset --after no-reset chip-id
  trace_command_output "esptool flash id" "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" --before no-reset --after no-reset flash-id
  trace_command_output "esptool read mac" "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" --before no-reset --after no-reset read-mac
  trace_event "device_probe" "tool=esptool" "status=complete"
}

trace_micropython_probe() {
  local mpremote_bin="$1"
  local connect_target="$2"

  if ! trace_enabled; then
    return
  fi

  trace_event "device_probe" "tool=mpremote" "status=start"
  trace_command_output "mpremote runtime info" "${mpremote_bin}" connect "${connect_target}" exec 'import sys, os, gc; print("sys.platform=%s" % getattr(sys, "platform", "unknown")); print("sys.implementation=%s" % (sys.implementation,)); print("os.uname=%s" % (os.uname(),)); print("gc.mem_free=%s" % gc.mem_free())'
  trace_command_output "mpremote root listing" "${mpremote_bin}" connect "${connect_target}" fs ls ":"
  trace_event "device_probe" "tool=mpremote" "status=complete"
}

start_debug_logging() {
  local debug_pipe

  if ! is_truthy_value "${DEBUG_ENABLED}"; then
    return
  fi

  if [[ -z "${DEBUG_FILE}" ]]; then
    DEBUG_FILE="$(default_debug_file)"
  fi

  export AIPI_INSTALL_DEBUG=1
  export AIPI_INSTALL_DEBUG_FILE="${DEBUG_FILE}"
  export AIPI_INSTALL_TRACE="${TRACE_ENABLED}"

  if is_truthy_value "${AIPI_INSTALL_DEBUG_ACTIVE:-0}"; then
    return
  fi

  mkdir -p "$(dirname "${DEBUG_FILE}")"
  : >"${DEBUG_FILE}"
  chmod 600 "${DEBUG_FILE}"

  {
    printf '# AIPI-Lite installer debug log\n'
    printf 'created_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'redaction=common secrets tokens passwords ssids credentials and MAC-like identifiers are redacted\n'
  } >>"${DEBUG_FILE}"

  if is_truthy_value "${TRACE_ENABLED}"; then
    if [[ -z "${TRACE_FILE}" ]]; then
      TRACE_FILE="$(default_trace_file)"
    fi
    export AIPI_INSTALL_TRACE_FILE="${TRACE_FILE}"
    mkdir -p "$(dirname "${TRACE_FILE}")"
    : >"${TRACE_FILE}"
    chmod 600 "${TRACE_FILE}"
    {
      printf '# AIPI-Lite installer trace log\n'
      printf 'created_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      printf 'redaction=common secrets tokens passwords ssids credentials and MAC-like identifiers are redacted\n'
      printf 'debug_file=%s\n' "${DEBUG_FILE}"
    } >>"${TRACE_FILE}"
    trace_event "installer_start" "script_dir=${SCRIPT_DIR}" "working_dir=$(pwd)"
  fi

  export AIPI_INSTALL_DEBUG_ACTIVE=1
  debug_pipe="${DEBUG_FILE}.pipe.$$"
  rm -f "${debug_pipe}"
  mkfifo "${debug_pipe}"
  redact_stream <"${debug_pipe}" | tee -a "${DEBUG_FILE}" &
  exec >"${debug_pipe}" 2>&1
  rm -f "${debug_pipe}"
  echo "Installer debug file: ${DEBUG_FILE}"
  if trace_enabled; then
    echo "Installer trace file: ${TRACE_FILE}"
  fi
}

finish_debug_logging() {
  local status=$?

  if is_truthy_value "${DEBUG_ENABLED}" && [[ -n "${DEBUG_FILE:-}" ]]; then
    echo "Installer debug file: ${DEBUG_FILE}"
  fi
  if trace_enabled; then
    echo "Installer trace file: ${TRACE_FILE}"
    trace_event "installer_finish" "status=${status}"
  fi

  return "${status}"
}

write_debug_context() {
  local worktree_root=""
  local command_line

  if ! is_truthy_value "${DEBUG_ENABLED}"; then
    return
  fi
  if [[ "${DEBUG_CONTEXT_WRITTEN}" -eq 1 ]]; then
    return
  fi
  DEBUG_CONTEXT_WRITTEN=1

  command_line="$(quote_args "$@" | redact_stream)"

  {
    printf '\n## Sanitized run context\n'
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'script_dir=%s\n' "${SCRIPT_DIR}"
    printf 'working_dir=%s\n' "$(pwd)"
    printf 'argv=%s\n' "${command_line}"
    printf 'conf_file=%s\n' "${CONF_FILE}"
    printf 'serial_port=%s\n' "${PORT:-auto}"
    printf 'app_dir=%s\n' "${APP_DIR:-${SCRIPT_DIR}/src}"
    printf 'firmware_url=%s\n' "${FIRMWARE_URL}"
    printf 'baud=%s\n' "${BAUD}"
    printf 'flash_size=%s\n' "${FLASH_SIZE}"
    printf 'backup_chunk_size=%s\n' "${BACKUP_CHUNK_SIZE}"
    printf 'backup_min_chunk_size=%s\n' "${BACKUP_MIN_CHUNK_SIZE}"
    printf 'backup_path=%s\n' "${BACKUP_PATH:-auto}"
    printf 'restore_backup_path=%s\n' "${RESTORE_BACKUP_PATH:-none}"
    printf 'reset_after_upload=%s\n' "${RESET_AFTER_UPLOAD}"
    printf 'skip_self_update=%s\n' "${SKIP_SELF_UPDATE}"
  } | redact_stream >>"${DEBUG_FILE}"

  trace_event "run_context" "serial_port=${PORT:-auto}" "app_dir=${APP_DIR:-${SCRIPT_DIR}/src}" "firmware_url=${FIRMWARE_URL}" "baud=${BAUD}" "flash_size=${FLASH_SIZE}" "reset_after_upload=${RESET_AFTER_UPLOAD}" "skip_self_update=${SKIP_SELF_UPDATE}"
  trace_file_metadata "conf_file" "${CONF_FILE}"

  debug_command_output "uname" uname -a
  debug_command_output "git version" git --version
  debug_command_output "python version" python3 --version

  if git -C "${SCRIPT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    worktree_root="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
    debug_command_output "git branch" git -C "${worktree_root}" branch --show-current
    debug_command_output "git commit" git -C "${worktree_root}" rev-parse HEAD
    debug_command_output "git status" git -C "${worktree_root}" status --short --branch
    debug_command_output "git remotes" git -C "${worktree_root}" remote -v
    trace_command_output "git status" git -C "${worktree_root}" status --short --branch
  fi

  if [[ -x "${VENV_DIR}/bin/python" ]]; then
    debug_command_output "esptool version" "${VENV_DIR}/bin/python" -m esptool version
    trace_command_output "esptool version" "${VENV_DIR}/bin/python" -m esptool version
  else
    printf '\n### esptool version\nnot staged at %s\n' "${VENV_DIR}/bin/python" >>"${DEBUG_FILE}"
    trace_event "tool" "name=esptool" "status=missing" "path=${VENV_DIR}/bin/python"
  fi

  if [[ -x "${VENV_DIR}/bin/mpremote" ]]; then
    debug_command_output "mpremote help header" "${VENV_DIR}/bin/mpremote" --help
    trace_command_output "mpremote help header" "${VENV_DIR}/bin/mpremote" --help
  else
    printf '\n### mpremote help header\nnot staged at %s\n' "${VENV_DIR}/bin/mpremote" >>"${DEBUG_FILE}"
    trace_event "tool" "name=mpremote" "status=missing" "path=${VENV_DIR}/bin/mpremote"
  fi
}

self_update_from_git() {
  local worktree_root

  if is_truthy_value "${AIPI_INSTALL_SELF_UPDATED:-0}"; then
    return
  fi

  if is_truthy_value "${SKIP_SELF_UPDATE}"; then
    echo "Installer self-update skipped."
    return
  fi

  if ! command -v git >/dev/null 2>&1; then
    echo "error: git is required for installer self-update; pass --skip-self-update to continue without pulling" >&2
    exit 1
  fi

  if ! git -C "${SCRIPT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "Installer self-update skipped: ${SCRIPT_DIR} is not a Git worktree."
    return
  fi

  worktree_root="$(git -C "${SCRIPT_DIR}" rev-parse --show-toplevel)"
  echo "Updating installer source with git pull --ff-only..."
  if ! git -C "${worktree_root}" pull --ff-only; then
    echo "error: git pull failed; installer stopped before device operations" >&2
    exit 1
  fi

  echo "Restarting installer after self-update..."
  exec env AIPI_INSTALL_SELF_UPDATED=1 "${SCRIPT_DIR}/install.sh" "$@"
}

preparse_preflight_flags "$@"
if is_truthy_value "${TRACE_ENABLED}"; then
  DEBUG_ENABLED=1
fi
start_debug_logging
trap finish_debug_logging EXIT
self_update_from_git "$@"

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
    --backup-min-chunk-size)
      BACKUP_MIN_CHUNK_SIZE="${2:?--backup-min-chunk-size requires a value}"
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
    --skip-self-update)
      SKIP_SELF_UPDATE=1
      shift
      ;;
    --clean-tools|--clean-prereqs)
      CLEAN_TOOLS=1
      shift
      ;;
    --debug)
      DEBUG_ENABLED=1
      shift
      ;;
    --debug-file)
      DEBUG_ENABLED=1
      DEBUG_FILE="${2:?--debug-file requires a value}"
      shift 2
      ;;
    --debug-file=*)
      DEBUG_ENABLED=1
      DEBUG_FILE="${1#*=}"
      shift
      ;;
    --trace)
      DEBUG_ENABLED=1
      TRACE_ENABLED=1
      shift
      ;;
    --trace-file)
      DEBUG_ENABLED=1
      TRACE_ENABLED=1
      TRACE_FILE="${2:?--trace-file requires a value}"
      shift 2
      ;;
    --trace-file=*)
      DEBUG_ENABLED=1
      TRACE_ENABLED=1
      TRACE_FILE="${1#*=}"
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

if [[ "${CLEAN_TOOLS}" -eq 1 ]]; then
  trace_event "phase" "name=clean_tools" "status=start"
  clean_prerequisite_artifacts
  trace_event "phase" "name=clean_tools" "status=complete"
  exit 0
fi

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

  if [[ -z "${BACKUP_MIN_CHUNK_SIZE}" ]] && configured_value="$(config_get "AIPI_BACKUP_MIN_CHUNK_SIZE")"; then
    BACKUP_MIN_CHUNK_SIZE="${configured_value}"
  fi
  BACKUP_MIN_CHUNK_SIZE="${BACKUP_MIN_CHUNK_SIZE:-0x1000}"

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
  config_set "AIPI_BACKUP_MIN_CHUNK_SIZE" "${BACKUP_MIN_CHUNK_SIZE}"
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

  run_with_trace "setup_prerequisites" bash "${SETUP_SCRIPT}" "${setup_args[@]}"
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

  run_with_trace "setup_restore_prerequisites" bash "${SETUP_SCRIPT}" "${setup_args[@]}"
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

extract_esptool_connected_port() {
  local output="$1"
  local line
  local serial_candidate=""
  local detected_port=""

  while IFS= read -r line || [[ -n "${line}" ]]; do
    if [[ "${line}" =~ Connected[[:space:]]to[[:space:]].*[[:space:]]on[[:space:]]([^:[:space:]]+):? ]]; then
      detected_port="${BASH_REMATCH[1]}"
      break
    fi

    if [[ "${line}" =~ ^Serial[[:space:]]port[[:space:]]([^:[:space:]]+): ]]; then
      serial_candidate="${BASH_REMATCH[1]}"
      continue
    fi

    if [[ -n "${serial_candidate}" && "${line}" =~ ^(Chip[[:space:]]is|Detecting[[:space:]]chip[[:space:]]type) ]]; then
      detected_port="${serial_candidate}"
      break
    fi
  done <<<"${output}"

  detected_port="${detected_port%:}"
  if [[ -n "${detected_port}" ]]; then
    printf '%s\n' "${detected_port}"
  fi
}

lock_esptool_auto_port() {
  local esptool_py="$1"
  local output
  local status
  local detected_port
  local command_line

  if [[ -n "${PORT}" ]]; then
    return
  fi

  echo "Auto-detecting ESP32-S3 serial port..."
  command_line="$(quote_args "${esptool_py}" -m esptool --chip esp32s3 --before no-reset --after no-reset chip-id | redact_stream)"
  trace_event "command_start" "phase=auto_port_detect"
  trace_line "command=${command_line}"

  set +e
  output="$("${esptool_py}" -m esptool --chip esp32s3 --before no-reset --after no-reset chip-id 2>&1)"
  status=$?
  set -e

  if trace_enabled; then
    {
      printf '\n### esptool auto port detection\n'
      printf '$ %s\n' "${command_line}"
      printf '%s\n' "${output}"
      printf '(exit %s)\n' "${status}"
    } | redact_stream >>"${TRACE_FILE}"
  fi
  trace_event "command_end" "phase=auto_port_detect" "status=${status}"

  if [[ "${status}" -ne 0 ]]; then
    echo "warning: esptool auto-detect probe failed; later commands will continue with esptool auto-detect." >&2
    return
  fi

  detected_port="$(extract_esptool_connected_port "${output}")"
  if [[ -z "${detected_port}" ]]; then
    echo "warning: esptool auto-detect probe succeeded but did not report a serial port; later commands will continue with esptool auto-detect." >&2
    return
  fi

  PORT="${detected_port}"
  config_set "AIPI_SERIAL_PORT" "${PORT}"
  trace_event "port_detect" "tool=esptool" "status=locked" "port=${PORT}"
  echo "Detected ESP32-S3 serial port: ${PORT}"
}

backup_stock_firmware() {
  local esptool_py="$1"
  shift
  local port_args=("$@")
  local flash_size_bytes
  local chunk_size_bytes
  local minimum_chunk_size_bytes
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
  minimum_chunk_size_bytes="$(positive_size_to_bytes "${BACKUP_MIN_CHUNK_SIZE}" "AIPI_BACKUP_MIN_CHUNK_SIZE")"

  if [[ "${chunk_size_bytes}" -gt "${flash_size_bytes}" ]]; then
    chunk_size_bytes="${flash_size_bytes}"
  fi
  if [[ "${minimum_chunk_size_bytes}" -gt "${chunk_size_bytes}" ]]; then
    minimum_chunk_size_bytes="${chunk_size_bytes}"
  fi

  if backup_file_is_complete "${BACKUP_PATH}" "${flash_size_bytes}"; then
    echo "Using existing complete stock firmware backup: ${BACKUP_PATH}"
    trace_file_metadata "stock_backup" "${BACKUP_PATH}"
    return
  fi

  if [[ -f "${BACKUP_PATH}" ]]; then
    actual_bytes="$(file_size_bytes "${BACKUP_PATH}")"
    echo "Existing stock firmware backup is incomplete (${actual_bytes}/${flash_size_bytes} bytes); replacing it."
    trace_event "stock_backup" "status=incomplete" "path=${BACKUP_PATH}" "bytes=${actual_bytes}" "expected_bytes=${flash_size_bytes}"
  fi

  mkdir -p "$(dirname "${BACKUP_PATH}")"
  tmp_path="${BACKUP_PATH}.tmp.$$"
  chunk_path="${BACKUP_PATH}.chunk.$$"
  rm -f "${tmp_path}" "${chunk_path}"
  : >"${tmp_path}"

  echo "Backing up stock firmware to ${BACKUP_PATH}"
  echo "Reading ${flash_size_bytes} bytes in ${chunk_size_bytes}-byte chunks."
  echo "Retrying failed chunks down to ${minimum_chunk_size_bytes} bytes."

  while [[ "${offset}" -lt "${flash_size_bytes}" ]]; do
    remaining=$((flash_size_bytes - offset))
    read_size="${chunk_size_bytes}"
    if [[ "${read_size}" -gt "${remaining}" ]]; then
      read_size="${remaining}"
    fi

    offset_arg="$(format_hex_size "${offset}")"
    read_size_arg="$(format_hex_size "${read_size}")"
    echo "Backing up flash chunk ${offset_arg}+${read_size_arg}"
    if ! run_with_trace "backup_read_flash" "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" \
      --before no-reset --after no-reset \
      read-flash "${offset_arg}" "${read_size_arg}" "${chunk_path}"; then
      rm -f "${chunk_path}"
      if [[ "${read_size}" -le "${minimum_chunk_size_bytes}" ]]; then
        rm -f "${tmp_path}"
        echo "error: failed to read stock firmware backup chunk at ${offset_arg} after retrying down to ${read_size_arg}" >&2
        echo "error: if this repeats at the same offset, the stock firmware region may be read-protected or the USB link is unstable." >&2
        echo "hint: rerun with --port ${PORT:-PORT} --backup-chunk-size 0x40000 --backup-min-chunk-size 0x1000 after confirming the device is still in bootloader mode." >&2
        exit 1
      fi

      chunk_size_bytes=$((read_size / 2))
      if [[ "${chunk_size_bytes}" -lt "${minimum_chunk_size_bytes}" ]]; then
        chunk_size_bytes="${minimum_chunk_size_bytes}"
      fi
      echo "warning: retrying ${offset_arg} with smaller ${chunk_size_bytes}-byte chunks" >&2
      continue
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
  trace_file_metadata "stock_backup" "${BACKUP_PATH}"
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
    run_with_trace "restore_erase_flash" "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" erase_flash
  fi

  trace_file_metadata "restore_backup" "${RESTORE_BACKUP_PATH}"
  run_with_trace "restore_write_flash" "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" --baud "${BAUD}" write_flash 0 "${RESTORE_BACKUP_PATH}"
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
  run_with_trace "upload_file" "${mpremote_bin}" connect "${connect_target}" fs cp "${local_file}" ":${remote_file}"
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
    trace_source_inventory "application" "${APP_DIR}"
    upload_tree "${mpremote_bin}" "${connect_target}" "${APP_DIR}" ""
    return
  fi

  if [[ -d "${SCRIPT_DIR}/src" ]]; then
    trace_source_inventory "application" "${SCRIPT_DIR}/src"
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
  if ! run_with_trace "reset_device" "${mpremote_bin}" connect "${connect_target}" reset; then
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
  trace_event "phase" "name=main" "status=start"
  [[ -f "${SETUP_SCRIPT}" ]] || {
    echo "error: setup script not found: ${SETUP_SCRIPT}" >&2
    exit 1
  }

  trace_event "phase" "name=config" "status=start"
  apply_config_defaults
  prompt_serial_port
  persist_config_defaults
  write_debug_context "$@"
  trace_event "phase" "name=config" "status=complete" "port=${PORT:-auto}" "baud=${BAUD}" "firmware_url=${FIRMWARE_URL}" "restore_mode=${RESTORE_MODE}"

  if [[ -n "${PORT}" ]]; then
    port_args=(--port "${PORT}")
    connect_target="${PORT}"
  fi

  if [[ "${RESTORE_MODE}" -eq 1 ]]; then
    trace_event "phase" "name=restore" "status=start"
    ensure_restore_prerequisites
    esptool_py="${VENV_DIR}/bin/python"
    ensure_bootloader_ready
    lock_esptool_auto_port "${esptool_py}"
    if [[ -n "${PORT}" ]]; then
      port_args=(--port "${PORT}")
      connect_target="${PORT}"
    fi
    trace_device_probe "${esptool_py}" "${port_args[@]}"
    restore_stock_firmware "${esptool_py}" "${port_args[@]}"
    trace_event "phase" "name=restore" "status=complete"
    return
  fi

  trace_event "phase" "name=firmware_resolve" "status=start"
  firmware_url="$(resolve_firmware_url)"
  firmware_name="$(firmware_filename "${firmware_url}")"
  firmware_path="${DOWNLOAD_DIR}/${firmware_name}"
  trace_event "phase" "name=firmware_resolve" "status=complete" "firmware_url=${firmware_url}" "firmware_name=${firmware_name}" "firmware_path=${firmware_path}"

  trace_event "phase" "name=prerequisites" "status=start"
  ensure_prerequisites "${firmware_url}" "${firmware_path}"
  trace_event "phase" "name=prerequisites" "status=complete"
  trace_file_metadata "micropython_firmware" "${firmware_path}"
  trace_source_inventory "staged_libraries" "${LIB_DIR}"

  esptool_py="${VENV_DIR}/bin/python"
  mpremote_bin="${VENV_DIR}/bin/mpremote"

  ensure_bootloader_ready
  lock_esptool_auto_port "${esptool_py}"
  if [[ -n "${PORT}" ]]; then
    port_args=(--port "${PORT}")
    connect_target="${PORT}"
  fi
  trace_device_probe "${esptool_py}" "${port_args[@]}"
  trace_event "phase" "name=stock_backup" "status=start"
  backup_stock_firmware "${esptool_py}" "${port_args[@]}"
  trace_event "phase" "name=stock_backup" "status=complete"

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
    run_with_trace "install_erase_flash" "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" erase_flash
  else
    trace_event "command_skip" "phase=install_erase_flash" "reason=skip_erase"
  fi

  run_with_trace "install_write_flash" "${esptool_py}" -m esptool --chip esp32s3 "${port_args[@]}" --baud "${BAUD}" write_flash 0 "${firmware_path}"

  echo "Waiting for MicroPython USB serial to reconnect..."
  trace_event "phase" "name=micropython_reconnect_wait" "status=start" "seconds=3"
  sleep 3
  trace_event "phase" "name=micropython_reconnect_wait" "status=complete"
  trace_micropython_probe "${mpremote_bin}" "${connect_target}"

  if [[ -d "${LIB_DIR}/drivers" ]]; then
    trace_source_inventory "driver_libraries" "${LIB_DIR}/drivers"
    trace_event "phase" "name=upload_libraries" "status=start"
    remote_mkdir "${mpremote_bin}" "${connect_target}" "lib"
    upload_tree "${mpremote_bin}" "${connect_target}" "${LIB_DIR}/drivers" "lib/drivers"
    trace_event "phase" "name=upload_libraries" "status=complete"
  else
    trace_event "phase" "name=upload_libraries" "status=skipped" "reason=no_driver_directory"
  fi

  trace_event "phase" "name=upload_application" "status=start"
  upload_application "${mpremote_bin}" "${connect_target}"
  trace_event "phase" "name=upload_application" "status=complete"
  reset_device "${mpremote_bin}" "${connect_target}"

  echo "Install complete."
  trace_event "phase" "name=main" "status=complete"
}

main "$@"
