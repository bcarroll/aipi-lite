#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_ROOT="${SCRIPT_DIR}/tools/.local"
CAPTURE_ROOT="${TOOLS_ROOT}/dev-install"
INSTALL_SCRIPT="${AIPI_DEV_INSTALL_SCRIPT:-${SCRIPT_DIR}/install.sh}"
GH_BIN="${AIPI_DEV_GH_BIN:-gh}"
MAX_ISSUE_TRANSCRIPT_BYTES="${AIPI_DEV_INSTALL_MAX_ISSUE_BYTES:-45000}"

CAPTURE_DIR=""
GITHUB_ISSUE=""
DEVICE_LABEL=""
PREPARE_ONLY=0
INSTALL_ARGS=()
HARDWARE_NOTES=()

usage() {
  cat <<'USAGE'
Usage: ./dev_install.sh [dev options] [--] [install.sh options]

Run the normal installer, show the same stdout/stderr a developer would see,
and capture a redacted transcript for GitHub issue inspection or hardware
validation analysis.

Developer options:
  --issue TARGET, --github-issue TARGET
                          Post the redacted issue body to TARGET when gh is
                          available. TARGET must be OWNER/REPO#NUMBER or a
                          https://github.com/OWNER/REPO/issues/NUMBER URL.
  --prepare-only          Prepare local artifacts but do not post to GitHub.
  --capture-dir DIR       Store run artifacts in DIR instead of the default
                          tools/.local/dev-install/install-TIMESTAMP-PID.
  --device-label LABEL    Optional non-secret device or bench label for
                          hardware validation context.
  --hardware-note TEXT    Optional hardware validation note. May be repeated.
  --clean-tools, --clean-prereqs
                          Pass the installer cleanup option through and capture
                          the cleanup transcript.
  --trace                 Pass installer tracing through and capture the trace
                          file path in the transcript.
  -h, --help              Show this help.

All remaining arguments are passed through to install.sh unchanged. Use -- when
an installer option could be confused with a developer option.

Environment overrides:
  AIPI_DEV_INSTALL_SCRIPT
  AIPI_DEV_GH_BIN
  AIPI_DEV_INSTALL_MAX_ISSUE_BYTES
USAGE
}

redact_stream() {
  local escaped_home=""

  if [[ -n "${HOME:-}" ]]; then
    escaped_home="${HOME//\\/\\\\}"
    escaped_home="${escaped_home//|/\\|}"
  fi

  sed -E \
    -e 's#(https?://)[^/@[:space:]]+:[^/@[:space:]]+@#\1<redacted>@#g' \
    -e 's#(https?://)[^/@[:space:]]+@#\1<redacted>@#g' \
    -e 's/([Aa]uthorization:[[:space:]]*(Bearer|Basic))[[:space:]]+[^[:space:]]+/\1 <redacted>/g' \
    -e 's/([Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]|[Pp][Aa][Ss][Ss][Ww][Dd]|[Tt][Oo][Kk][Ee][Nn]|[Ss][Ee][Cc][Rr][Ee][Tt]|[Kk][Ee][Yy])([=:])([^[:space:]]+)/\1\2<redacted>/g' \
    -e 's/([Ss][Ss][Ii][Dd])([=:])([^[:space:]]+)/\1\2<redacted>/g' \
    -e 's/([[:xdigit:]]{2}:){5}[[:xdigit:]]{2}/<redacted-mac>/g' |
    if [[ -n "${escaped_home}" ]]; then
      sed "s|${escaped_home}|<home>|g"
    else
      cat
    fi
}

quote_args() {
  local arg

  for arg in "$@"; do
    printf '%q ' "${arg}"
  done
  printf '\n'
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --issue|--github-issue)
        GITHUB_ISSUE="${2:?$1 requires a value}"
        shift 2
        ;;
      --issue=*|--github-issue=*)
        GITHUB_ISSUE="${1#*=}"
        shift
        ;;
      --prepare-only)
        PREPARE_ONLY=1
        shift
        ;;
      --capture-dir)
        CAPTURE_DIR="${2:?--capture-dir requires a value}"
        shift 2
        ;;
      --capture-dir=*)
        CAPTURE_DIR="${1#*=}"
        shift
        ;;
      --device-label)
        DEVICE_LABEL="${2:?--device-label requires a value}"
        shift 2
        ;;
      --device-label=*)
        DEVICE_LABEL="${1#*=}"
        shift
        ;;
      --hardware-note|--validation-note)
        HARDWARE_NOTES+=("${2:?$1 requires a value}")
        shift 2
        ;;
      --hardware-note=*|--validation-note=*)
        HARDWARE_NOTES+=("${1#*=}")
        shift
        ;;
      --clean-tools|--clean-prereqs|--trace)
        INSTALL_ARGS+=("$1")
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      --)
        shift
        INSTALL_ARGS+=("$@")
        break
        ;;
      *)
        INSTALL_ARGS+=("$@")
        break
        ;;
    esac
  done
}

ensure_capture_dir() {
  local timestamp

  if [[ -z "${CAPTURE_DIR}" ]]; then
    timestamp="$(date -u +%Y%m%d-%H%M%S)"
    CAPTURE_DIR="${CAPTURE_ROOT}/install-${timestamp}-$$"
  fi

  mkdir -p "${CAPTURE_DIR}"
  chmod 700 "${CAPTURE_DIR}"
}

git_value() {
  local fallback="$1"
  shift

  if git -C "${SCRIPT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    "$@" 2>/dev/null || printf '%s\n' "${fallback}"
  else
    printf '%s\n' "${fallback}"
  fi
}

validate_max_issue_bytes() {
  if ! [[ "${MAX_ISSUE_TRANSCRIPT_BYTES}" =~ ^[0-9]+$ ]]; then
    MAX_ISSUE_TRANSCRIPT_BYTES=45000
  fi
}

write_metadata() {
  local metadata_file="$1"
  local install_status="$2"
  local note

  {
    printf '# AIPI-Lite developer install capture\n'
    printf 'created_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'installer_exit_status=%s\n' "${install_status}"
    printf 'install_script=%s\n' "${INSTALL_SCRIPT}"
    printf 'installer_argv=%s\n' "$(quote_args "${INSTALL_ARGS[@]}")"
    printf 'device_label=%s\n' "${DEVICE_LABEL:-unspecified}"
    printf 'git_branch=%s\n' "$(git_value unknown git -C "${SCRIPT_DIR}" branch --show-current)"
    printf 'git_commit=%s\n' "$(git_value unknown git -C "${SCRIPT_DIR}" rev-parse HEAD)"
    printf 'git_status=%s\n' "$(git_value unavailable git -C "${SCRIPT_DIR}" status --short --branch)"
    printf 'capture_dir=%s\n' "${CAPTURE_DIR}"
    if [[ "${#HARDWARE_NOTES[@]}" -gt 0 ]]; then
      printf 'hardware_notes=\n'
      for note in "${HARDWARE_NOTES[@]}"; do
        printf -- '- %s\n' "${note}"
      done
    else
      printf 'hardware_notes=none\n'
    fi
  } | redact_stream >"${metadata_file}"
  chmod 600 "${metadata_file}"
}

append_transcript_for_issue() {
  local redacted_transcript="$1"
  local transcript_size

  transcript_size="$(wc -c <"${redacted_transcript}" | tr -d '[:space:]')"

  if [[ "${transcript_size}" -le "${MAX_ISSUE_TRANSCRIPT_BYTES}" ]]; then
    cat "${redacted_transcript}"
    return
  fi

  printf '[transcript truncated to last %s bytes for GitHub comment size]\n' \
    "${MAX_ISSUE_TRANSCRIPT_BYTES}"
  printf '[full redacted transcript remains in the local capture directory]\n\n'
  tail -c "${MAX_ISSUE_TRANSCRIPT_BYTES}" "${redacted_transcript}"
}

write_issue_body() {
  local issue_body="$1"
  local metadata_file="$2"
  local redacted_transcript="$3"
  local install_status="$4"
  local command_line
  local note

  command_line="$(quote_args "${INSTALL_ARGS[@]}" | redact_stream)"

  {
    printf '# AIPI-Lite install capture\n\n'
    printf -- '- Installer exit status: `%s`\n' "${install_status}"
    printf -- '- Device label: `%s`\n' "${DEVICE_LABEL:-unspecified}" | redact_stream
    printf -- '- Installer arguments: `%s`\n' "${command_line}"
    printf -- '- Local artifact directory: `%s`\n\n' "${CAPTURE_DIR}" | redact_stream

    printf '## Hardware Validation Context\n\n'
    if [[ "${#HARDWARE_NOTES[@]}" -gt 0 ]]; then
      for note in "${HARDWARE_NOTES[@]}"; do
        printf -- '- %s\n' "${note}" | redact_stream
      done
      printf '\n'
    else
      printf 'No hardware validation notes were supplied.\n\n'
    fi

    printf '## Run Metadata\n\n'
    printf '```text\n'
    cat "${metadata_file}"
    printf '```\n\n'

    printf '## Redacted Installer Transcript\n\n'
    printf '```text\n'
    append_transcript_for_issue "${redacted_transcript}"
    printf '\n```\n'
  } >"${issue_body}"
  chmod 600 "${issue_body}"
}

parse_issue_target() {
  local target="$1"

  ISSUE_REPO=""
  ISSUE_NUMBER=""

  if [[ "${target}" =~ ^https://github\.com/([^/]+)/([^/]+)/issues/([0-9]+)([/?#].*)?$ ]]; then
    ISSUE_REPO="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    ISSUE_NUMBER="${BASH_REMATCH[3]}"
    return 0
  fi

  if [[ "${target}" =~ ^([^/[:space:]]+)/([^#[:space:]]+)#([0-9]+)$ ]]; then
    ISSUE_REPO="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    ISSUE_NUMBER="${BASH_REMATCH[3]}"
    return 0
  fi

  return 1
}

post_issue_body() {
  local issue_body="$1"

  if [[ -z "${GITHUB_ISSUE}" ]]; then
    echo "GitHub issue body prepared: ${issue_body}"
    return 0
  fi

  if [[ "${PREPARE_ONLY}" -eq 1 ]]; then
    echo "GitHub issue body prepared without posting: ${issue_body}"
    return 0
  fi

  if ! parse_issue_target "${GITHUB_ISSUE}"; then
    echo "warning: unsupported GitHub issue target: ${GITHUB_ISSUE}" >&2
    echo "GitHub issue body prepared for manual posting: ${issue_body}"
    return 1
  fi

  if ! command -v "${GH_BIN}" >/dev/null 2>&1; then
    echo "warning: gh CLI not available; GitHub issue body prepared: ${issue_body}" >&2
    return 1
  fi

  if "${GH_BIN}" issue comment "${ISSUE_NUMBER}" --repo "${ISSUE_REPO}" --body-file "${issue_body}"; then
    echo "Posted redacted install capture to ${ISSUE_REPO}#${ISSUE_NUMBER}"
    return 0
  fi

  echo "warning: gh failed; GitHub issue body remains at: ${issue_body}" >&2
  return 1
}

run_installer() {
  local raw_transcript="$1"
  local pipeline_status
  local install_status
  local tee_status

  if [[ ! -x "${INSTALL_SCRIPT}" ]]; then
    echo "error: installer is not executable: ${INSTALL_SCRIPT}" >&2
    return 127
  fi

  : >"${raw_transcript}"
  chmod 600 "${raw_transcript}"

  set +e
  "${INSTALL_SCRIPT}" "${INSTALL_ARGS[@]}" 2>&1 | tee "${raw_transcript}"
  pipeline_status=("${PIPESTATUS[@]}")

  install_status="${pipeline_status[0]}"
  tee_status="${pipeline_status[1]:-0}"
  if [[ "${tee_status}" -ne 0 ]]; then
    echo "warning: tee exited with status ${tee_status}; transcript may be incomplete" >&2
  fi

  return "${install_status}"
}

main() {
  local raw_transcript
  local redacted_transcript
  local metadata_file
  local issue_body
  local install_status=0

  parse_args "$@"
  validate_max_issue_bytes
  ensure_capture_dir

  raw_transcript="${CAPTURE_DIR}/install-transcript-raw.txt"
  redacted_transcript="${CAPTURE_DIR}/install-transcript-redacted.txt"
  metadata_file="${CAPTURE_DIR}/run-metadata.txt"
  issue_body="${CAPTURE_DIR}/github-issue-body.md"

  echo "Developer install capture directory: ${CAPTURE_DIR}"
  echo "Running installer: ${INSTALL_SCRIPT}"

  set +e
  run_installer "${raw_transcript}"
  install_status=$?
  set -e

  redact_stream <"${raw_transcript}" >"${redacted_transcript}"
  chmod 600 "${redacted_transcript}"
  write_metadata "${metadata_file}" "${install_status}"
  write_issue_body "${issue_body}" "${metadata_file}" "${redacted_transcript}" "${install_status}"
  post_issue_body "${issue_body}" || true

  echo "Raw transcript: ${raw_transcript}"
  echo "Redacted transcript: ${redacted_transcript}"
  echo "Run metadata: ${metadata_file}"
  echo "GitHub issue body: ${issue_body}"
  echo "Installer exit status: ${install_status}"

  return "${install_status}"
}

main "$@"
