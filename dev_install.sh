#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOOLS_ROOT="${SCRIPT_DIR}/tools/.local"
CAPTURE_ROOT="${TOOLS_ROOT}/dev-install"
INSTALL_SCRIPT="${AIPI_DEV_INSTALL_SCRIPT:-${SCRIPT_DIR}/install.sh}"
GH_BIN="${AIPI_DEV_GH_BIN:-gh}"
MPREMOTE_BIN="${AIPI_DEV_MPREMOTE:-${TOOLS_ROOT}/micropython-venv/bin/mpremote}"
MAX_ISSUE_TRANSCRIPT_BYTES="${AIPI_DEV_INSTALL_MAX_ISSUE_BYTES:-45000}"

CAPTURE_DIR=""
GITHUB_ISSUE=""
GITHUB_CREATE_REQUESTED=0
GITHUB_CREATE_REPO=""
GITHUB_ISSUE_TITLE=""
DEVICE_LABEL=""
PREPARE_ONLY=0
INFERENCE_PROBE_REQUESTED=0
INSTALL_ARGS=()
HARDWARE_NOTES=()
INFERENCE_CHECKS=()
INFERENCE_PORT=""
INFERENCE_DECISION=""
INFERENCE_REASON=""

usage() {
  cat <<'USAGE'
Usage: ./dev_install.sh [dev options] [--] [install.sh options]

Run the normal installer, show the same stdout/stderr a developer would see,
and capture a redacted transcript for GitHub issue inspection or hardware
validation analysis. The default installer path uploads to an existing
MicroPython runtime; pass --flash-micropython after -- only for intentional
firmware flashing.

Developer options:
  --gh [REPOSITORY]        Create a new GitHub issue from the redacted issue
                          body when gh is available. REPOSITORY may be
                          OWNER/REPO or HOST/OWNER/REPO. If omitted, the
                          script uses AIPI_GITHUB_REPO or the local origin
                          remote when possible.
  --gh-title TITLE         Optional title for a new issue created with --gh.
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
  --inference-probe       After a successful application-only install, run the
                          offline on-device inference feasibility probe.
  --inference-check NAME=STATUS
                          Record a physical check for display, status-led,
                          button, or offline. STATUS is pass, fail, or
                          not-observed. May be repeated with unique names.
  --clean-tools, --clean-prereqs
                          Pass the installer cleanup option through and capture
                          the cleanup transcript.
  --trace                 Pass installer tracing through and capture the trace
                          file path in the transcript.
  -h, --help              Show this help.

All remaining arguments are passed through to install.sh unchanged. Use -- when
an installer option could be confused with a developer option.

Environment overrides:
  AIPI_GITHUB_REPO
  AIPI_DEV_INSTALL_SCRIPT
  AIPI_DEV_GH_BIN
  AIPI_DEV_MPREMOTE
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
    -e 's#/dev/(cu|tty)[^[:space:]]+#<redacted-serial-port>#g' \
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
      --gh)
        GITHUB_CREATE_REQUESTED=1
        if [[ $# -gt 1 && -z "${2}" ]]; then
          shift 2
        elif [[ $# -gt 1 && "${2}" != --* ]]; then
          GITHUB_CREATE_REPO="$2"
          shift 2
        else
          shift
        fi
        ;;
      --gh=*)
        GITHUB_CREATE_REQUESTED=1
        GITHUB_CREATE_REPO="${1#*=}"
        shift
        ;;
      --gh-title)
        GITHUB_ISSUE_TITLE="${2:?--gh-title requires a value}"
        shift 2
        ;;
      --gh-title=*)
        GITHUB_ISSUE_TITLE="${1#*=}"
        shift
        ;;
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
      --inference-probe)
        INFERENCE_PROBE_REQUESTED=1
        shift
        ;;
      --inference-check)
        INFERENCE_CHECKS+=("${2:?--inference-check requires NAME=STATUS}")
        shift 2
        ;;
      --inference-check=*)
        INFERENCE_CHECKS+=("${1#*=}")
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

validate_dev_options() {
  if [[ "${GITHUB_CREATE_REQUESTED}" -eq 1 && -n "${GITHUB_ISSUE}" ]]; then
    echo "error: use either --gh to create a new issue or --issue to comment on an existing issue" >&2
    return 2
  fi

  if [[ "${INFERENCE_PROBE_REQUESTED}" -eq 1 ]]; then
    validate_inference_options || return 1
  elif [[ "${#INFERENCE_CHECKS[@]}" -gt 0 ]]; then
    echo "error: --inference-check requires --inference-probe" >&2
    return 1
  fi

  return 0
}

validate_inference_options() {
  local arg
  local index
  local no_reset_requested=0
  local port_count=0
  local port_value=""

  for ((index = 0; index < ${#INSTALL_ARGS[@]}; index += 1)); do
    arg="${INSTALL_ARGS[${index}]}"
    case "${arg}" in
      --port)
        if [[ $((index + 1)) -ge ${#INSTALL_ARGS[@]} || -z "${INSTALL_ARGS[$((index + 1))]}" ]]; then
          echo "error: --inference-probe requires --port PORT" >&2
          return 1
        fi
        port_value="${INSTALL_ARGS[$((index + 1))]}"
        port_count=$((port_count + 1))
        index=$((index + 1))
        ;;
      --port=*)
        port_value="${arg#*=}"
        if [[ -z "${port_value}" ]]; then
          echo "error: --inference-probe requires --port PORT" >&2
          return 1
        fi
        port_count=$((port_count + 1))
        ;;
      --no-reset)
        no_reset_requested=1
        ;;
      --clean-tools|--clean-prereqs|-h|--help|--self-update|--flash-micropython|--backup-stock|--restore|--restore-backup|--restore-backup=*|--skip-erase)
        echo "error: --inference-probe only supports an application-first install; remove ${arg}" >&2
        return 1
        ;;
    esac
  done

  if [[ "${port_count}" -ne 1 ]]; then
    echo "error: --inference-probe requires exactly one explicit --port PORT" >&2
    return 1
  fi

  INFERENCE_PORT="${port_value}"
  if [[ "${no_reset_requested}" -eq 0 ]]; then
    INSTALL_ARGS+=("--no-reset")
  fi
  validate_inference_checks
}

validate_inference_checks() {
  local check
  local existing
  local name
  local status
  local seen_names="|"

  if [[ -z "${INFERENCE_CHECKS[0]:-}" ]]; then
    return 0
  fi

  for check in "${INFERENCE_CHECKS[@]}"; do
    if [[ "${check}" != *=* ]]; then
      echo "error: --inference-check must use NAME=STATUS" >&2
      return 1
    fi
    name="${check%%=*}"
    status="${check#*=}"
    case "${name}" in
      display|status-led|button|offline)
        ;;
      *)
        echo "error: unsupported inference check: ${name}" >&2
        return 1
        ;;
    esac
    case "${status}" in
      pass|fail|not-observed)
        ;;
      *)
        echo "error: unsupported inference check status: ${status}" >&2
        return 1
        ;;
    esac
    if [[ "${seen_names}" == *"|${name}|"* ]]; then
      echo "error: duplicate inference check: ${name}" >&2
      return 1
    fi
    seen_names="${seen_names}${name}|"
  done

  return 0
}

inference_check_status() {
  local expected_name="$1"
  local check

  if [[ -z "${INFERENCE_CHECKS[0]:-}" ]]; then
    printf '%s\n' "not-observed"
    return 0
  fi

  for check in "${INFERENCE_CHECKS[@]}"; do
    if [[ "${check%%=*}" == "${expected_name}" ]]; then
      printf '%s\n' "${check#*=}"
      return 0
    fi
  done
  printf '%s\n' "not-observed"
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
  local probe_status="$3"
  local raw_transcript="$4"
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
    if [[ "${INFERENCE_PROBE_REQUESTED}" -eq 1 ]]; then
      printf 'capture_dir=local-only\n'
      printf 'inference_probe_requested=yes\n'
      printf 'inference_probe_status=%s\n' "${probe_status}"
      printf 'inference_decision=%s\n' "${INFERENCE_DECISION:-not-reported}"
      printf 'inference_reason=%s\n' "${INFERENCE_REASON:-not-reported}"
      printf 'inference_checks=\n'
      printf -- '- display=%s\n' "$(inference_check_status display)"
      printf -- '- status-led=%s\n' "$(inference_check_status status-led)"
      printf -- '- button=%s\n' "$(inference_check_status button)"
      printf -- '- offline=%s\n' "$(inference_check_status offline)"
      printf 'inference_probe_serial_lines=\n'
      if ! grep '^inference_probe:' "${raw_transcript}"; then
        printf -- '- none\n'
      fi
    else
      printf 'capture_dir=%s\n' "${CAPTURE_DIR}"
    fi
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

append_inference_issue_section() {
  local redacted_transcript="$1"
  local probe_status="$2"

  printf '## On-Device Inference Feasibility\n\n'
  printf -- '- Probe execution status: `%s`\n' "${probe_status}"
  printf -- '- Decision: `%s`\n' "${INFERENCE_DECISION:-not-reported}"
  printf -- '- Reason: %s\n\n' "${INFERENCE_REASON:-not-reported}" | redact_stream

  printf '### Operator Checks\n\n'
  printf -- '- Display updated during load: `%s`\n' "$(inference_check_status display)"
  printf -- '- GPIO46 status LED updated during load: `%s`\n' "$(inference_check_status status-led)"
  printf -- '- GPIO42 button remained responsive: `%s`\n' "$(inference_check_status button)"
  printf -- '- No Wi-Fi or endpoint required: `%s`\n\n' "$(inference_check_status offline)"

  printf '### Probe Serial Report\n\n'
  printf '```text\n'
  if ! grep '^inference_probe:' "${redacted_transcript}"; then
    printf 'No stable inference probe serial lines were captured.\n'
  fi
  printf '```\n\n'
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
  local probe_status="$5"
  local command_line
  local note

  command_line="$(quote_args "${INSTALL_ARGS[@]}" | redact_stream)"

  {
    printf '# AIPI-Lite install capture\n\n'
    printf -- '- Installer exit status: `%s`\n' "${install_status}"
    printf -- '- Device label: `%s`\n' "${DEVICE_LABEL:-unspecified}" | redact_stream
    printf -- '- Installer arguments: `%s`\n' "${command_line}"
    if [[ "${INFERENCE_PROBE_REQUESTED}" -eq 1 ]]; then
      printf '%s\n\n' '- Local artifact directory: local-only (not included in this issue)'
      append_inference_issue_section "${redacted_transcript}" "${probe_status}"
    else
      printf -- '- Local artifact directory: `%s`\n\n' "${CAPTURE_DIR}" | redact_stream
    fi

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

parse_repository_target() {
  local target="$1"

  CREATE_REPO=""

  if [[ "${target}" =~ ^([A-Za-z0-9._-]+/)?[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]]; then
    CREATE_REPO="${target}"
    return 0
  fi

  return 1
}

repository_from_remote_url() {
  local remote_url="$1"
  local host
  local owner
  local repo

  if [[ "${remote_url}" =~ ^git@([^:]+):([^/]+)/([^/[:space:]]+)$ ]]; then
    host="${BASH_REMATCH[1]}"
    owner="${BASH_REMATCH[2]}"
    repo="${BASH_REMATCH[3]}"
  elif [[ "${remote_url}" =~ ^ssh://git@([^/]+)/([^/]+)/([^/[:space:]]+)$ ]]; then
    host="${BASH_REMATCH[1]}"
    owner="${BASH_REMATCH[2]}"
    repo="${BASH_REMATCH[3]}"
  elif [[ "${remote_url}" =~ ^https?://([^/]+)/([^/]+)/([^/?#[:space:]]+)([/?#].*)?$ ]]; then
    host="${BASH_REMATCH[1]}"
    owner="${BASH_REMATCH[2]}"
    repo="${BASH_REMATCH[3]}"
  else
    return 1
  fi

  repo="${repo%.git}"
  if [[ -z "${host}" || -z "${owner}" || -z "${repo}" ]]; then
    return 1
  fi

  if [[ "${host}" == "github.com" ]]; then
    printf '%s/%s\n' "${owner}" "${repo}"
  else
    printf '%s/%s/%s\n' "${host}" "${owner}" "${repo}"
  fi
}

resolve_create_repository() {
  local candidate="${GITHUB_CREATE_REPO}"
  local remote_url

  if [[ -z "${candidate}" && -n "${AIPI_GITHUB_REPO:-}" ]]; then
    candidate="${AIPI_GITHUB_REPO}"
  fi

  if [[ -z "${candidate}" ]]; then
    if remote_url="$(git -C "${SCRIPT_DIR}" remote get-url origin 2>/dev/null)" &&
      candidate="$(repository_from_remote_url "${remote_url}")"; then
      :
    else
      echo "warning: --gh could not infer a GitHub repository; set AIPI_GITHUB_REPO or pass --gh OWNER/REPO" >&2
      return 1
    fi
  fi

  if parse_repository_target "${candidate}"; then
    return 0
  fi

  echo "warning: unsupported GitHub repository target: ${candidate}" >&2
  return 1
}

default_github_issue_title() {
  local install_status="$1"
  local title

  if [[ "${INFERENCE_PROBE_REQUESTED}" -eq 1 ]]; then
    title="AIPI-Lite inference feasibility: ${DEVICE_LABEL:-unspecified-device} status ${install_status} $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  else
    title="AIPI-Lite install capture: ${DEVICE_LABEL:-unspecified-device} status ${install_status} $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  fi
  printf '%s\n' "${title}" | redact_stream
}

installer_help_requested() {
  local arg

  for arg in "${INSTALL_ARGS[@]}"; do
    case "${arg}" in
      -h|--help)
        return 0
        ;;
    esac
  done

  return 1
}

create_github_issue() {
  local issue_body="$1"
  local install_status="$2"
  local created_issue_file="${CAPTURE_DIR}/github-created-issue.txt"
  local issue_url
  local title

  if [[ "${PREPARE_ONLY}" -eq 1 ]]; then
    echo "GitHub issue body prepared without creating an issue: ${issue_body}"
    return 0
  fi

  if [[ "${install_status}" -eq 0 ]] && installer_help_requested; then
    echo "Help-only capture kept local instead of creating a GitHub issue: ${issue_body}"
    echo "Use --issue OWNER/REPO#NUMBER to append this capture to a chosen tracking issue if needed."
    return 0
  fi

  if grep -Eq "hardware validation status: blocked .*stock backup" "${issue_body}"; then
    echo "Stock-backup-blocked capture kept local instead of creating a duplicate GitHub issue: ${issue_body}"
    echo "Use --issue OWNER/REPO#NUMBER to append this capture to a chosen tracking issue after bench triage."
    return 0
  fi

  if ! resolve_create_repository; then
    echo "GitHub issue body prepared for manual posting: ${issue_body}"
    return 1
  fi

  if ! command -v "${GH_BIN}" >/dev/null 2>&1; then
    echo "warning: gh CLI not available; GitHub issue body prepared: ${issue_body}" >&2
    return 1
  fi

  title="${GITHUB_ISSUE_TITLE:-$(default_github_issue_title "${install_status}")}"
  if issue_url="$("${GH_BIN}" issue create --repo "${CREATE_REPO}" --title "${title}" --body-file "${issue_body}" 2>&1)"; then
    printf '%s\n' "${issue_url}" >"${created_issue_file}"
    chmod 600 "${created_issue_file}"
    echo "Created GitHub issue: ${issue_url}"
    return 0
  fi

  echo "warning: gh failed to create issue: ${issue_url}" >&2
  echo "GitHub issue body prepared for manual posting: ${issue_body}"
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

report_issue_body() {
  local issue_body="$1"
  local install_status="$2"

  if [[ "${GITHUB_CREATE_REQUESTED}" -eq 1 ]]; then
    create_github_issue "${issue_body}" "${install_status}"
    return
  fi

  post_issue_body "${issue_body}"
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
  if [[ "${INFERENCE_PROBE_REQUESTED}" -eq 1 ]]; then
    AIPI_CREATE_LOCAL_WIFI_CONFIG=no "${INSTALL_SCRIPT}" "${INSTALL_ARGS[@]}" 2>&1 | tee "${raw_transcript}"
  else
    "${INSTALL_SCRIPT}" "${INSTALL_ARGS[@]}" 2>&1 | tee "${raw_transcript}"
  fi
  pipeline_status=("${PIPESTATUS[@]}")

  install_status="${pipeline_status[0]}"
  tee_status="${pipeline_status[1]:-0}"
  if [[ "${tee_status}" -ne 0 ]]; then
    echo "warning: tee exited with status ${tee_status}; transcript may be incomplete" >&2
  fi

  return "${install_status}"
}

run_inference_probe() {
  local raw_transcript="$1"
  local pipeline_status
  local probe_status
  local tee_status

  printf 'Running offline on-device inference feasibility probe.\n' | tee -a "${raw_transcript}"
  if [[ ! -x "${MPREMOTE_BIN}" ]]; then
    printf 'error: mpremote is not executable: %s\n' "${MPREMOTE_BIN}" | tee -a "${raw_transcript}" >&2
    return 127
  fi

  set +e
  "${MPREMOTE_BIN}" connect "${INFERENCE_PORT}" exec "import inference_probe; inference_probe.run_probe()" 2>&1 | tee -a "${raw_transcript}"
  pipeline_status=("${PIPESTATUS[@]}")

  probe_status="${pipeline_status[0]}"
  tee_status="${pipeline_status[1]:-0}"
  if [[ "${tee_status}" -ne 0 ]]; then
    echo "warning: tee exited with status ${tee_status}; probe transcript may be incomplete" >&2
  fi

  return "${probe_status}"
}

capture_inference_decision() {
  local raw_transcript="$1"
  local decision_line

  decision_line="$(grep '^inference_probe: decision=' "${raw_transcript}" | tail -n 1 || true)"
  if [[ -z "${decision_line}" ]]; then
    return 1
  fi

  INFERENCE_DECISION="${decision_line#*decision=}"
  INFERENCE_DECISION="${INFERENCE_DECISION%% *}"
  INFERENCE_REASON="${decision_line#* reason=}"
  if [[ "${INFERENCE_REASON}" == "${decision_line}" ]]; then
    INFERENCE_REASON="not-reported"
  fi

  case "${INFERENCE_DECISION}" in
    candidate_supported|defer_inference|offline_unsupported)
      return 0
      ;;
  esac
  return 1
}

main() {
  local raw_transcript
  local redacted_transcript
  local metadata_file
  local issue_body
  local install_status=0
  local probe_status="not-requested"
  local validation_status=0

  parse_args "$@"
  if ! validate_dev_options; then
    return 2
  fi
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

  validation_status="${install_status}"
  if [[ "${INFERENCE_PROBE_REQUESTED}" -eq 1 ]]; then
    if [[ "${install_status}" -eq 0 ]]; then
      set +e
      run_inference_probe "${raw_transcript}"
      probe_status=$?
      set -e
      if [[ "${probe_status}" -eq 0 ]] && ! capture_inference_decision "${raw_transcript}"; then
        printf 'error: inference probe did not report a valid feasibility decision\n' | tee -a "${raw_transcript}" >&2
        probe_status=1
      fi
      validation_status="${probe_status}"
    else
      probe_status="not-run"
    fi
  fi

  redact_stream <"${raw_transcript}" >"${redacted_transcript}"
  chmod 600 "${redacted_transcript}"
  write_metadata "${metadata_file}" "${install_status}" "${probe_status}" "${raw_transcript}"
  write_issue_body "${issue_body}" "${metadata_file}" "${redacted_transcript}" "${install_status}" "${probe_status}"
  report_issue_body "${issue_body}" "${validation_status}" || true

  echo "Raw transcript: ${raw_transcript}"
  echo "Redacted transcript: ${redacted_transcript}"
  echo "Run metadata: ${metadata_file}"
  echo "GitHub issue body: ${issue_body}"
  echo "Installer exit status: ${install_status}"
  if [[ "${INFERENCE_PROBE_REQUESTED}" -eq 1 ]]; then
    echo "Inference probe exit status: ${probe_status}"
    echo "Inference decision: ${INFERENCE_DECISION:-not-reported}"
  fi

  return "${validation_status}"
}

main "$@"
