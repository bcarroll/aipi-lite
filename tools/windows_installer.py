"""Windows application-first installer support for the AIPI-Lite.

The module is called by the repository's native CMD entry points. It keeps
Windows-specific host tooling under ``tools/.local`` and supports application
upload, developer capture, and physical device validation; firmware flash and
recovery actions remain available through the established Unix workflow.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Callable, Sequence, TextIO

from device_application import CLEANUP_COMPLETE_MARKER
from device_application import LEGACY_ROOT_MODULES
from device_application import application_cleanup_code
from device_application import application_manifest
from device_application import ignored_upload_artifacts


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
TOOLS_ROOT = REPO_ROOT / "tools" / ".local"
VENV_DIR = TOOLS_ROOT / "micropython-venv"
CAPTURE_ROOT = TOOLS_ROOT / "dev-install"
DEVICE_VALIDATION_ROOT = TOOLS_ROOT / "device-validation"
VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS = "1.0"
COM_PORT_PATTERN = re.compile(r"COM[1-9][0-9]*", re.IGNORECASE)
SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|key|ssid)\s*([=:])\s*[^\s]+"
)
MAC_ADDRESS_PATTERN = re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")
SERIAL_PORT_PATTERN = re.compile(r"(?i)\bCOM[1-9][0-9]*\b")
GITHUB_REPOSITORY_PATTERN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
GITHUB_ORIGIN_PATTERN = re.compile(
    r"(?:git@github\.com:|ssh://git@github\.com/|https?://github\.com/)([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
INFERENCE_CHECK_NAMES = {"display", "status-led", "button", "offline"}
INFERENCE_CHECK_STATUSES = {"pass", "fail", "not-observed"}
INFERENCE_DECISION_LINE_PATTERN = re.compile(
    r"^inference_probe: decision=(candidate_supported|defer_inference|offline_unsupported) reason=(.+)$"
)
LOCAL_PATH_PATTERN = re.compile(
    r"(?i)(?:[a-z]:[\\/][^\s`\"']+|/(?:Users|home|private|tmp|var|opt|workspace|workspaces)(?:/[^\s`\"']+)*)"
)
DEVICE_VALIDATION_OBSERVATIONS = (
    "display",
    "status-led",
    "button",
    "microphone",
    "speaker",
    "inference-ui",
)
DEVICE_VALIDATION_OBSERVATION_LABELS = {
    "display": "Display status screens were visible and readable",
    "status-led": "GPIO46 status LED cycled through its states",
    "button": "GPIO42 button press and release were observed",
    "microphone": "Microphone capture metrics were observed",
    "speaker": "Low-volume speaker playback was audible",
    "inference-ui": "Display, LED, and button remained responsive during inference",
}
DEVICE_VALIDATION_OBSERVATION_STATUSES = {"pass", "fail", "not-observed"}
DEVICE_VALIDATION_RESULT_PATTERN = re.compile(
    r"^device_validation_result: name=([a-z][a-z0-9-]*) status=([0-9]+)$"
)


class InstallerError(RuntimeError):
    """Represent an expected installer failure that should be shown to an operator."""


@dataclass(frozen=True)
class InstallRequest:
    """Describe an application-first upload request and its reset policy."""

    port: str
    no_reset: bool
    assume_yes: bool
    preflight_reset: bool = False


@dataclass(frozen=True)
class DeviceValidationProbe:
    """Describe one self-contained AIPI-Lite device validation probe."""

    name: str
    command: str
    serial_prefix: str
    observations: tuple[str, ...] = ()


DEVICE_VALIDATION_PROBES = (
    DeviceValidationProbe(
        name="display",
        command="import display_probe; display_probe.run_probe(cycles=2)",
        serial_prefix="display_probe:",
        observations=("display",),
    ),
    DeviceValidationProbe(
        name="io",
        command="import io_probe; io_probe.run_probe(cycles=1)",
        serial_prefix="io_probe:",
        observations=("status-led", "button"),
    ),
    DeviceValidationProbe(
        name="codec",
        command="import audio_probe; audio_probe.run_probe(toggle_speaker=False)",
        serial_prefix="audio_probe:",
    ),
    DeviceValidationProbe(
        name="capture",
        command="import capture_probe; capture_probe.run_probe()",
        serial_prefix="capture_probe:",
        observations=("microphone",),
    ),
    DeviceValidationProbe(
        name="playback",
        command="import playback_probe; playback_probe.run_probe()",
        serial_prefix="playback_probe:",
        observations=("speaker",),
    ),
    DeviceValidationProbe(
        name="inference",
        command="import inference_probe; inference_probe.run_probe()",
        serial_prefix="inference_probe:",
        observations=("inference-ui",),
    ),
)


class OutputSink:
    """Write installer output to the console while retaining a transcript."""

    def __init__(self, stdout: TextIO | None = None, stderr: TextIO | None = None):
        """Initialize a sink using the supplied streams or the process defaults."""
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr
        self._parts: list[str] = []

    def write(self, text: str, *, error: bool = False) -> None:
        """Display text and retain an exact copy for an optional capture artifact."""
        stream = self._stderr if error else self._stdout
        stream.write(text)
        if text and not text.endswith("\n"):
            stream.write("\n")
            text = f"{text}\n"
        stream.flush()
        self._parts.append(text)

    @property
    def transcript(self) -> str:
        """Return all text written through this sink in display order."""
        return "".join(self._parts)


def create_parser() -> argparse.ArgumentParser:
    """Create the command parser shared by both CMD entry points."""
    parser = argparse.ArgumentParser(
        description="Windows application-first installer support for AIPI-Lite."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    install = commands.add_parser(
        "install",
        help="Upload src/ to a connected MicroPython device.",
    )
    install.add_argument("--port", help="Windows serial port, for example COM3.")
    install.add_argument("--no-reset", action="store_true", help="Do not reset after upload.")
    install.add_argument(
        "-y",
        "--yes",
        dest="assume_yes",
        action="store_true",
        help="Approve local mpremote prerequisite setup.",
    )
    install.add_argument(
        "--list-ports",
        action="store_true",
        help="List detected Windows COM ports and exit.",
    )

    developer = commands.add_parser(
        "developer",
        help="Run an application install with local developer capture artifacts.",
    )
    developer.add_argument(
        "--capture-dir",
        type=Path,
        help="Directory for local capture artifacts.",
    )
    developer.add_argument("--device-label", default="", help="Optional non-secret device label.")
    developer.add_argument(
        "--hardware-note",
        action="append",
        default=[],
        help="Optional non-secret validation note; may be repeated.",
    )
    developer.add_argument(
        "--prepare-only",
        action="store_true",
        help="Create capture artifacts without uploading to a device.",
    )
    developer.add_argument(
        "--inference-probe",
        action="store_true",
        help="Run the offline inference feasibility probe after application upload.",
    )
    developer.add_argument(
        "--inference-check",
        action="append",
        default=[],
        metavar="NAME=STATUS",
        help="Record display, status-led, button, or offline as pass, fail, or not-observed.",
    )
    developer.add_argument(
        "--gh",
        nargs="?",
        const="",
        default=None,
        metavar="OWNER/REPO",
        help="Create a new GitHub issue from the redacted inference report.",
    )
    developer.add_argument(
        "--gh-title",
        default="",
        help="Optional title for a GitHub issue created with --gh.",
    )
    developer.add_argument(
        "install_args",
        nargs=argparse.REMAINDER,
        help="Installer options after --, such as -- --port COM3.",
    )

    validate = commands.add_parser(
        "validate",
        help="Run self-contained physical AIPI-Lite validation probes and report them.",
    )
    validate.add_argument("--port", required=True, help="Windows serial port, for example COM3.")
    validate.add_argument(
        "-y",
        "--yes",
        dest="assume_yes",
        action="store_true",
        help="Approve local mpremote prerequisite setup.",
    )
    validate.add_argument(
        "--capture-dir",
        type=Path,
        help="Directory for ignored local validation artifacts.",
    )
    validate.add_argument("--device-label", default="", help="Optional non-secret device label.")
    return parser


def normalize_com_port(port: str) -> str:
    """Validate and normalize a Windows serial port name."""
    normalized = port.strip().upper()
    if not COM_PORT_PATTERN.fullmatch(normalized):
        raise InstallerError("--port must use a Windows COM port name such as COM3")
    return normalized


def list_windows_serial_ports() -> list[str]:
    """Return COM ports registered by Windows without introducing pyserial."""
    if os.name != "nt":
        return []

    command = ["reg", "query", r"HKLM\HARDWARE\DEVICEMAP\SERIALCOMM"]
    result = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        return []
    return sorted({match.upper() for match in COM_PORT_PATTERN.findall(result.stdout)})


def mpremote_path() -> Path:
    """Return the expected Windows mpremote executable location."""
    return VENV_DIR / "Scripts" / "mpremote.exe"


def venv_python_path() -> Path:
    """Return the expected Windows virtual-environment Python location."""
    return VENV_DIR / "Scripts" / "python.exe"


def confirm_prerequisite_setup(assume_yes: bool) -> bool:
    """Ask before installing local host tooling unless approval was supplied."""
    if assume_yes:
        return True
    if not sys.stdin.isatty():
        return False
    answer = input("Install local mpremote tooling under tools\\.local? [y/N] ").strip()
    return answer.lower() in {"y", "yes"}


def run_streaming(command: Sequence[str], sink: OutputSink) -> int:
    """Run a command, forwarding its combined output to the supplied sink."""
    process = subprocess.Popen(
        list(command),
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.stdout is not None:
        for line in process.stdout:
            sink.write(line)
    return process.wait()


def ensure_mpremote(assume_yes: bool, sink: OutputSink) -> Path:
    """Create the local virtual environment and install mpremote when required."""
    executable = mpremote_path()
    if executable.is_file():
        return executable

    if not confirm_prerequisite_setup(assume_yes):
        raise InstallerError(
            "mpremote setup was not approved; rerun with --yes or approve the prompt"
        )

    sink.write(f"Creating local MicroPython tooling at {VENV_DIR}...")
    if run_streaming([sys.executable, "-m", "venv", str(VENV_DIR)], sink) != 0:
        raise InstallerError("unable to create the local Python virtual environment")

    venv_python = venv_python_path()
    sink.write("Installing mpremote into the local virtual environment...")
    if run_streaming(
        [str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "mpremote"], sink
    ) != 0:
        raise InstallerError("unable to install mpremote into the local virtual environment")
    if not executable.is_file():
        raise InstallerError(f"mpremote was not installed at the expected path: {executable}")
    return executable


def validate_upload_request(request: InstallRequest) -> None:
    """Check that the requested app upload can safely begin."""
    if not SRC_DIR.is_dir():
        raise InstallerError(f"application source directory is missing: {SRC_DIR}")

    ports = list_windows_serial_ports()
    if not ports:
        raise InstallerError("no Windows COM ports were detected; connect the AIPI-Lite and retry")
    if request.port not in ports:
        raise InstallerError(
            f"requested port {request.port} was not detected; available ports: {', '.join(ports)}"
        )


def stage_application_source(destination: Path) -> tuple[list[Path], tuple[str, ...]]:
    """Create a clean source tree and return its root children and file manifest."""
    shutil.copytree(SRC_DIR, destination, ignore=ignored_upload_artifacts)
    sources = sorted(destination.iterdir(), key=lambda path: path.name)
    manifest = application_manifest(destination)
    if not sources or not manifest:
        raise InstallerError(f"application source directory is empty: {SRC_DIR}")
    return sources, manifest


def application_upload_command(
    executable: Path,
    port: str,
    sources: Sequence[Path],
    *,
    preflight_reset: bool = False,
) -> list[str]:
    """Return one recursive copy command with an optional preflight hard reset."""
    command = [
        str(executable),
        "connect",
        port,
    ]
    if preflight_reset:
        command.extend(["reset", "sleep", VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS])
    command.extend(
        [
            "fs",
            "cp",
            "-r",
            *(str(source) for source in sources),
            ":",
        ]
    )
    return command


def application_cleanup_command(
    executable: Path,
    port: str,
    application_manifest: Sequence[str],
    *,
    reset: bool,
) -> list[str]:
    """Return cleanup and optional reset commands sharing one mpremote connection."""
    command = [
        str(executable),
        "connect",
        port,
        "exec",
        application_cleanup_code(application_manifest),
    ]
    if reset:
        command.append("reset")
    return command


def run_install_request(request: InstallRequest, sink: OutputSink) -> int:
    """Upload the application source and reset the target unless reset is disabled."""
    validate_upload_request(request)
    executable = ensure_mpremote(request.assume_yes, sink)
    if request.preflight_reset:
        sink.write(
            f"Hard-resetting {request.port} and waiting "
            f"{VALIDATION_PREFLIGHT_RESET_DELAY_SECONDS} seconds before validation upload..."
        )
    sink.write(f"Uploading application source to {request.port}...")
    with tempfile.TemporaryDirectory(prefix="aipi-lite-upload-") as temporary_directory:
        staging_root = Path(temporary_directory) / "application"
        upload_sources, application_manifest = stage_application_source(staging_root)
        upload_status = run_streaming(
            application_upload_command(
                executable,
                request.port,
                upload_sources,
                preflight_reset=request.preflight_reset,
            ),
            sink,
        )
    if upload_status != 0:
        sink.write(f"Application upload failed with status {upload_status}.", error=True)
        return upload_status

    sink.write("Cleaning legacy and misplaced application files...")
    if not request.no_reset:
        sink.write(f"Resetting {request.port} after cleanup...")
    cleanup_output_start = len(sink.transcript)
    cleanup_status = run_streaming(
        application_cleanup_command(
            executable,
            request.port,
            application_manifest,
            reset=not request.no_reset,
        ),
        sink,
    )
    cleanup_output = sink.transcript[cleanup_output_start:]
    cleanup_completed = CLEANUP_COMPLETE_MARKER in cleanup_output
    if cleanup_status != 0:
        if cleanup_completed and not request.no_reset:
            sink.write(
                "WARNING: Application upload and cleanup succeeded, but automatic reset "
                f"could not be confirmed (status {cleanup_status}). Power-cycle the "
                "AIPI-Lite by unplugging and reconnecting USB-C before use.",
                error=True,
            )
            return 0
        sink.write(
            f"Application upload succeeded but cleanup failed with status {cleanup_status}.",
            error=True,
        )
        return cleanup_status
    if not cleanup_completed:
        sink.write(
            "Application upload succeeded but cleanup completion was not confirmed.",
            error=True,
        )
        return 1

    if request.no_reset:
        sink.write("Application upload complete; reset skipped by --no-reset.")
        return 0

    sink.write("Application upload complete.")
    return 0


def install_request_from_args(args: Sequence[str]) -> InstallRequest:
    """Parse installer arguments passed through the developer wrapper."""
    parser = create_parser()
    install_args = list(args)
    if install_args[:1] == ["--"]:
        install_args.pop(0)
    try:
        parsed = parser.parse_args(["install", *install_args])
    except SystemExit as error:
        raise InstallerError(
            "invalid installer options; use -- --port COMx after developer options"
        ) from error
    if parsed.list_ports:
        raise InstallerError("--list-ports cannot be used through dev_install.cmd")
    if not parsed.port:
        raise InstallerError("--port COMx is required for an application upload")
    return InstallRequest(
        port=normalize_com_port(parsed.port),
        no_reset=parsed.no_reset,
        assume_yes=parsed.assume_yes,
    )


def inference_request_from_args(args: Sequence[str]) -> InstallRequest:
    """Parse one explicit COM-port upload request and force no-reset behavior."""
    install_args = list(args)
    if install_args[:1] == ["--"]:
        install_args.pop(0)

    port_count = 0
    index = 0
    while index < len(install_args):
        argument = install_args[index]
        if argument == "--port":
            if index + 1 >= len(install_args) or not install_args[index + 1]:
                raise InstallerError("--inference-probe requires -- --port COMx")
            port_count += 1
            index += 2
            continue
        if argument.startswith("--port="):
            if not argument.removeprefix("--port="):
                raise InstallerError("--inference-probe requires -- --port COMx")
            port_count += 1
        index += 1

    if port_count != 1:
        raise InstallerError("--inference-probe requires exactly one -- --port COMx")

    request = install_request_from_args(install_args)
    return InstallRequest(port=request.port, no_reset=True, assume_yes=request.assume_yes)


def parse_inference_checks(values: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Validate explicit operator observations for an inference capture."""
    checks: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    for value in values:
        name, separator, status = value.partition("=")
        if not separator:
            raise InstallerError("--inference-check must use NAME=STATUS")
        if name not in INFERENCE_CHECK_NAMES:
            raise InstallerError(f"unsupported inference check: {name}")
        if status not in INFERENCE_CHECK_STATUSES:
            raise InstallerError(f"unsupported inference check status: {status}")
        if name in seen_names:
            raise InstallerError(f"duplicate inference check: {name}")
        seen_names.add(name)
        checks.append((name, status))
    return tuple(checks)


def inference_check_status(checks: Sequence[tuple[str, str]], name: str) -> str:
    """Return one explicitly supplied check status or the safe default."""
    for check_name, status in checks:
        if check_name == name:
            return status
    return "not-observed"


def redact_text(text: str) -> str:
    """Remove common secrets, identifiers, and local paths from shareable text."""
    redacted = SECRET_PATTERN.sub(r"\1\2<redacted>", text)
    redacted = MAC_ADDRESS_PATTERN.sub("<redacted-mac>", redacted)
    redacted = SERIAL_PORT_PATTERN.sub("<redacted-serial-port>", redacted)
    return LOCAL_PATH_PATTERN.sub("<redacted-local-path>", redacted)


def prompt_device_validation_observation(
    observation: str,
    sink: OutputSink,
    input_func: Callable[[str], str] = input,
) -> str:
    """Collect one explicit physical observation without inferring a pass result."""
    label = DEVICE_VALIDATION_OBSERVATION_LABELS[observation]
    prompt = f"{label} [pass/fail/not-observed]: "
    while True:
        try:
            answer = input_func(prompt)
        except (EOFError, OSError):
            sink.write(f"{observation}: not-observed (interactive input unavailable)")
            return "not-observed"
        status = str(answer).strip().lower()
        if status in DEVICE_VALIDATION_OBSERVATION_STATUSES:
            sink.write(f"{observation}: {status}")
            return status
        sink.write("Enter pass, fail, or not-observed.", error=True)


def device_validation_batch_code(probes: Sequence[DeviceValidationProbe]) -> str:
    """Build one MicroPython program that reports each validation probe result."""
    lines = [
        "def _aipi_validation_result(name, status):",
        "    print('device_validation_result: name={} status={}'.format(name, status))",
    ]
    for probe in probes:
        lines.extend(
            [
                "",
                f"print('device_validation_probe: starting {probe.name}')",
                "try:",
                f"    exec({probe.command!r})",
                "except Exception:",
                f"    _aipi_validation_result({probe.name!r}, 1)",
                "else:",
                f"    _aipi_validation_result({probe.name!r}, 0)",
            ]
        )
    return "\n".join(lines)


def device_validation_batch_command(
    executable: Path,
    request: InstallRequest,
    probes: Sequence[DeviceValidationProbe],
) -> list[str]:
    """Return one raw-REPL command for the complete validation probe sequence."""
    return [
        str(executable),
        "connect",
        request.port,
        "exec",
        device_validation_batch_code(probes),
    ]


def parse_device_validation_probe_statuses(
    transcript: str,
    probes: Sequence[DeviceValidationProbe],
) -> list[tuple[str, int]]:
    """Parse one result marker per configured probe, failing missing or malformed values."""
    expected_names = {probe.name for probe in probes}
    parsed_statuses: dict[str, int] = {}
    malformed_names: set[str] = set()
    for line in transcript.splitlines():
        match = DEVICE_VALIDATION_RESULT_PATTERN.fullmatch(line.strip())
        if match is None:
            continue
        name, status_text = match.groups()
        if name not in expected_names:
            continue
        if name in parsed_statuses or status_text not in {"0", "1"}:
            malformed_names.add(name)
            continue
        parsed_statuses[name] = int(status_text)
    return [
        (probe.name, 1 if probe.name in malformed_names else parsed_statuses.get(probe.name, 1))
        for probe in probes
    ]


def run_device_validation_batch(
    executable: Path,
    request: InstallRequest,
    sink: OutputSink,
) -> tuple[int, list[tuple[str, int]]]:
    """Run every validation probe in one raw-REPL session and return recorded statuses."""
    sink.write("Running device validation probes in one raw-REPL session.")
    transcript_start = len(sink.transcript)
    batch_status = run_streaming(
        device_validation_batch_command(executable, request, DEVICE_VALIDATION_PROBES),
        sink,
    )
    probe_statuses = parse_device_validation_probe_statuses(
        sink.transcript[transcript_start:],
        DEVICE_VALIDATION_PROBES,
    )
    for name, status in probe_statuses:
        sink.write(f"{name} probe exit status: {status}")
    sink.write(f"Device validation batch exit status: {batch_status}")
    return batch_status, probe_statuses


def run_inference_probe(request: InstallRequest, sink: OutputSink) -> int:
    """Run the explicit offline inference probe through the local mpremote tool."""
    executable = ensure_mpremote(request.assume_yes, sink)
    command = [
        str(executable),
        "connect",
        request.port,
        "exec",
        "import inference_probe; inference_probe.run_probe()",
    ]
    sink.write("Running offline on-device inference feasibility probe.")
    return run_streaming(command, sink)


def extract_inference_decision(transcript: str) -> tuple[str, str]:
    """Return the last valid feasibility decision and reason from probe output."""
    decision: tuple[str, str] | None = None
    for line in transcript.splitlines():
        match = INFERENCE_DECISION_LINE_PATTERN.fullmatch(line)
        if match is not None:
            decision = (match.group(1), match.group(2))
    if decision is None:
        raise InstallerError("inference probe did not report a valid feasibility decision")
    return decision


def github_repository_from_origin() -> str:
    """Resolve an owner/repository target from the current GitHub origin remote."""
    try:
        result = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "remote", "get-url", "origin"],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        raise InstallerError(f"unable to resolve GitHub origin: {error}") from error
    if result.returncode != 0:
        raise InstallerError("unable to resolve a GitHub origin repository")
    match = GITHUB_ORIGIN_PATTERN.fullmatch(result.stdout.strip())
    if match is None:
        raise InstallerError("origin is not a supported GitHub repository")
    return match.group(1)


def resolve_github_repository(value: str) -> str:
    """Validate an explicit GitHub repository or resolve the local origin remote."""
    candidate = value.strip()
    if not candidate:
        return github_repository_from_origin()
    if not GITHUB_REPOSITORY_PATTERN.fullmatch(candidate):
        raise InstallerError(f"unsupported GitHub repository target: {candidate}")
    return candidate


def resolve_device_validation_repository() -> str:
    """Resolve the automatic validation issue target from configuration or origin."""
    configured = os.environ.get("AIPI_GITHUB_REPO", "").strip()
    if configured and GITHUB_REPOSITORY_PATTERN.fullmatch(configured):
        return configured
    return github_repository_from_origin()


def default_inference_issue_title(device_label: str, validation_status: int) -> str:
    """Build a redacted, timestamped GitHub issue title for one bench run."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    label = redact_text(device_label or "unspecified-device")
    return f"AIPI-Lite inference feasibility: {label} status {validation_status} {timestamp}"


def default_device_validation_issue_title(device_label: str, validation_status: int) -> str:
    """Build a redacted, timestamped issue title for one physical validation run."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    label = redact_text(device_label or "unspecified-device")
    return f"AIPI-Lite device validation: {label} status {validation_status} {timestamp}"


def write_inference_issue_body(
    issue_body: Path,
    *,
    sink: OutputSink,
    device_label: str,
    hardware_notes: Sequence[str],
    install_status: int | None,
    probe_status: int | None,
    decision: str,
    reason: str,
    checks: Sequence[tuple[str, str]],
) -> None:
    """Write a redacted inference-validation issue body without local paths."""
    redacted_transcript = redact_text(sink.transcript)
    serial_lines = [
        line for line in redacted_transcript.splitlines() if line.startswith("inference_probe:")
    ]
    lines = [
        "# AIPI-Lite On-Device Inference Feasibility",
        "",
        f"- Installer exit status: `{install_status if install_status is not None else 'not-run'}`",
        f"- Probe exit status: `{probe_status if probe_status is not None else 'not-run'}`",
        f"- Decision: `{decision or 'not-reported'}`",
        f"- Reason: {redact_text(reason or 'not-reported')}",
        f"- Device label: {redact_text(device_label or 'unspecified')}",
        "",
        "## Operator Checks",
        "",
        f"- Display updated during load: `{inference_check_status(checks, 'display')}`",
        f"- GPIO46 status LED updated during load: `{inference_check_status(checks, 'status-led')}`",
        f"- GPIO42 button remained responsive: `{inference_check_status(checks, 'button')}`",
        f"- No Wi-Fi or endpoint required: `{inference_check_status(checks, 'offline')}`",
        "",
        "## Hardware Notes",
        "",
    ]
    if hardware_notes:
        lines.extend(f"- {redact_text(note)}" for note in hardware_notes)
    else:
        lines.append("No additional hardware notes were supplied.")
    lines.extend(["", "## Probe Serial Report", "", "```text"])
    lines.extend(serial_lines or ["No stable inference probe serial lines were captured."])
    lines.extend(["```", ""])
    issue_body.write_text("\n".join(lines), encoding="utf-8")


def create_github_issue(
    repository: str,
    title: str,
    issue_body: Path,
    capture_dir: Path,
    sink: OutputSink,
) -> bool:
    """Create an issue with gh or retain the local report when publishing fails."""
    gh_path = shutil.which("gh")
    if gh_path is None:
        sink.write(f"warning: gh CLI not available; GitHub issue body prepared: {issue_body}", error=True)
        return False

    try:
        result = subprocess.run(
            [
                gh_path,
                "issue",
                "create",
                "--repo",
                repository,
                "--title",
                title,
                "--body-file",
                str(issue_body),
            ],
            cwd=REPO_ROOT,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        sink.write(f"warning: gh could not create issue: {error}", error=True)
        return False

    output = result.stdout.strip()
    if result.returncode != 0:
        sink.write(f"warning: gh failed to create issue: {output}", error=True)
        sink.write(f"GitHub issue body prepared for manual posting: {issue_body}")
        return False

    created_issue = capture_dir / "github-created-issue.txt"
    created_issue.write_text(f"{output}\n", encoding="utf-8")
    sink.write(f"Created GitHub issue: {output}")
    return True


def default_capture_directory() -> Path:
    """Build a unique local-only directory for a developer capture run."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return CAPTURE_ROOT / f"install-{timestamp}-{os.getpid()}"


def write_capture_artifacts(
    capture_dir: Path,
    sink: OutputSink,
    *,
    device_label: str,
    hardware_notes: Sequence[str],
    install_status: int | None,
    prepared_only: bool,
    inference_probe: bool = False,
    probe_status: int | None = None,
    inference_decision: str = "",
    inference_reason: str = "",
    inference_checks: Sequence[tuple[str, str]] = (),
) -> Path | None:
    """Write raw, redacted, and non-secret metadata files for a capture run."""
    capture_dir.mkdir(parents=True, exist_ok=True)
    raw_transcript = capture_dir / "install-transcript-raw.txt"
    redacted_transcript = capture_dir / "install-transcript-redacted.txt"
    metadata = capture_dir / "run-metadata.txt"
    raw_transcript.write_text(sink.transcript, encoding="utf-8")
    redacted_transcript.write_text(redact_text(sink.transcript), encoding="utf-8")
    metadata_lines = [
        f"workflow={'windows-inference-validation' if inference_probe else 'windows-dev-install'}",
        f"prepared_only={'yes' if prepared_only else 'no'}",
        f"installer_exit_status={install_status if install_status is not None else 'not-run'}",
        f"device_label={redact_text(device_label)}",
    ]
    metadata_lines.extend(f"hardware_note={redact_text(note)}" for note in hardware_notes)
    if inference_probe:
        metadata_lines.extend(
            [
                f"inference_probe_status={probe_status if probe_status is not None else 'not-run'}",
                f"inference_decision={inference_decision or 'not-reported'}",
                f"inference_reason={redact_text(inference_reason or 'not-reported')}",
                f"inference_check_display={inference_check_status(inference_checks, 'display')}",
                f"inference_check_status_led={inference_check_status(inference_checks, 'status-led')}",
                f"inference_check_button={inference_check_status(inference_checks, 'button')}",
                f"inference_check_offline={inference_check_status(inference_checks, 'offline')}",
            ]
        )
    metadata.write_text("\n".join(metadata_lines) + "\n", encoding="utf-8")
    if not inference_probe:
        return None

    issue_body = capture_dir / "github-issue-body.md"
    write_inference_issue_body(
        issue_body,
        sink=sink,
        device_label=device_label,
        hardware_notes=hardware_notes,
        install_status=install_status,
        probe_status=probe_status,
        decision=inference_decision,
        reason=inference_reason,
        checks=inference_checks,
    )
    return issue_body


def default_device_validation_capture_directory() -> Path:
    """Build a unique ignored directory for one Windows device validation run."""
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return DEVICE_VALIDATION_ROOT / f"validation-{timestamp}-{os.getpid()}"


def observation_status(observations: dict[str, str], name: str) -> str:
    """Return one recorded observation or the safe not-observed default."""
    return observations.get(name, "not-observed")


def device_validation_status(
    upload_status: int | None,
    batch_status: int | None,
    probe_statuses: Sequence[tuple[str, int]],
    observations: dict[str, str],
) -> int:
    """Return success only when every device probe and observation passed."""
    if (
        upload_status != 0
        or batch_status != 0
        or len(probe_statuses) != len(DEVICE_VALIDATION_PROBES)
    ):
        return 1
    if any(status != 0 for _, status in probe_statuses):
        return 1
    if any(observation_status(observations, name) != "pass" for name in DEVICE_VALIDATION_OBSERVATIONS):
        return 1
    return 0


def device_validation_serial_lines(transcript: str) -> list[str]:
    """Return stable redacted device serial lines safe to include in an issue."""
    prefixes = tuple(probe.serial_prefix for probe in DEVICE_VALIDATION_PROBES)
    return [
        line
        for line in redact_text(transcript).splitlines()
        if line.startswith(prefixes)
    ]


def write_device_validation_issue_body(
    issue_body: Path,
    *,
    sink: OutputSink,
    device_label: str,
    upload_status: int | None,
    batch_status: int | None,
    probe_statuses: Sequence[tuple[str, int]],
    observations: dict[str, str],
    validation_status: int,
) -> None:
    """Write a redacted physical-device validation report for a new GitHub issue."""
    status_by_probe = dict(probe_statuses)
    lines = [
        "# AIPI-Lite Physical Device Validation",
        "",
        f"- Aggregate validation status: `{validation_status}`",
        f"- Application upload status: `{upload_status if upload_status is not None else 'not-run'}`",
        f"- Device validation batch status: `{batch_status if batch_status is not None else 'not-run'}`",
        f"- Device label: {redact_text(device_label or 'unspecified')}",
        "",
        "## Probe Results",
        "",
    ]
    for probe in DEVICE_VALIDATION_PROBES:
        status = status_by_probe.get(probe.name, "not-run")
        lines.append(f"- {probe.name}: `{status}`")
    lines.extend(["", "## Operator Observations", ""])
    for observation in DEVICE_VALIDATION_OBSERVATIONS:
        lines.append(
            f"- {DEVICE_VALIDATION_OBSERVATION_LABELS[observation]}: "
            f"`{observation_status(observations, observation)}`"
        )
    lines.extend(["", "## Redacted Device Serial", "", "```text"])
    lines.extend(
        device_validation_serial_lines(sink.transcript)
        or ["No stable device probe serial lines were captured."]
    )
    lines.extend(["```", ""])
    issue_body.write_text("\n".join(lines), encoding="utf-8")


def write_device_validation_artifacts(
    capture_dir: Path,
    *,
    sink: OutputSink,
    device_label: str,
    upload_status: int | None,
    batch_status: int | None,
    probe_statuses: Sequence[tuple[str, int]],
    observations: dict[str, str],
    validation_status: int,
) -> Path:
    """Persist raw and redacted validation evidence plus the GitHub issue body."""
    capture_dir.mkdir(parents=True, exist_ok=True)
    (capture_dir / "validation-transcript-raw.txt").write_text(
        sink.transcript,
        encoding="utf-8",
    )
    (capture_dir / "validation-transcript-redacted.txt").write_text(
        redact_text(sink.transcript),
        encoding="utf-8",
    )
    metadata_lines = [
        "workflow=windows-device-validation",
        f"aggregate_validation_status={validation_status}",
        f"application_upload_status={upload_status if upload_status is not None else 'not-run'}",
        f"validation_batch_status={batch_status if batch_status is not None else 'not-run'}",
        f"device_label={redact_text(device_label)}",
    ]
    metadata_lines.extend(f"probe_{name}_status={status}" for name, status in probe_statuses)
    metadata_lines.extend(
        f"observation_{name}={observation_status(observations, name)}"
        for name in DEVICE_VALIDATION_OBSERVATIONS
    )
    (capture_dir / "run-metadata.txt").write_text(
        "\n".join(metadata_lines) + "\n",
        encoding="utf-8",
    )
    issue_body = capture_dir / "github-issue-body.md"
    write_device_validation_issue_body(
        issue_body,
        sink=sink,
        device_label=device_label,
        upload_status=upload_status,
        batch_status=batch_status,
        probe_statuses=probe_statuses,
        observations=observations,
        validation_status=validation_status,
    )
    return issue_body


def run_device_validation(
    args: argparse.Namespace,
    sink: OutputSink,
    input_func: Callable[[str], str] = input,
) -> int:
    """Run the approved self-contained device probes and publish their evidence."""
    capture_dir = args.capture_dir or default_device_validation_capture_directory()
    upload_status: int | None = None
    batch_status: int | None = None
    probe_statuses: list[tuple[str, int]] = []
    observations: dict[str, str] = {}
    sink.write(f"Device validation capture directory: {capture_dir}")
    try:
        request = InstallRequest(
            port=normalize_com_port(args.port),
            no_reset=True,
            assume_yes=args.assume_yes,
            preflight_reset=True,
        )
        upload_status = run_install_request(request, sink)
        sink.write(f"Application upload status: {upload_status}")
        if upload_status == 0:
            executable = ensure_mpremote(request.assume_yes, sink)
            try:
                batch_status, probe_statuses = run_device_validation_batch(executable, request, sink)
            except (InstallerError, OSError, subprocess.SubprocessError) as error:
                batch_status = 1
                probe_statuses = [(probe.name, 1) for probe in DEVICE_VALIDATION_PROBES]
                sink.write(f"error: device validation batch failed: {error}", error=True)
            for observation in DEVICE_VALIDATION_OBSERVATIONS:
                observations[observation] = prompt_device_validation_observation(
                    observation,
                    sink,
                    input_func,
                )
    except (InstallerError, OSError, subprocess.SubprocessError) as error:
        upload_status = 1
        sink.write(f"error: {error}", error=True)

    validation_status = device_validation_status(
        upload_status,
        batch_status,
        probe_statuses,
        observations,
    )
    sink.write(f"Device validation status: {validation_status}")
    issue_body = write_device_validation_artifacts(
        capture_dir,
        sink=sink,
        device_label=args.device_label,
        upload_status=upload_status,
        batch_status=batch_status,
        probe_statuses=probe_statuses,
        observations=observations,
        validation_status=validation_status,
    )
    try:
        repository = resolve_device_validation_repository()
    except InstallerError as error:
        sink.write(f"warning: {error}; GitHub issue body prepared: {issue_body}", error=True)
    else:
        create_github_issue(
            repository,
            default_device_validation_issue_title(args.device_label, validation_status),
            issue_body,
            capture_dir,
            sink,
        )
    return validation_status


def run_developer_capture(args: argparse.Namespace, sink: OutputSink) -> int:
    """Run or prepare a developer capture and return the installer outcome."""
    capture_dir = args.capture_dir or default_capture_directory()
    sink.write(f"Developer capture directory: {capture_dir}")
    install_status: int | None = None
    probe_status: int | None = None
    inference_decision = ""
    inference_reason = ""
    inference_checks: tuple[tuple[str, str], ...] = ()
    validation_status = 0
    prepared_only = bool(args.prepare_only)
    install_attempted = False
    issue_body: Path | None = None
    try:
        if not args.inference_probe and args.inference_check:
            raise InstallerError("--inference-check requires --inference-probe")
        if not args.inference_probe and args.gh is not None:
            raise InstallerError("--gh is currently supported only with --inference-probe")
        if args.gh_title and args.gh is None:
            raise InstallerError("--gh-title requires --gh")
        if prepared_only:
            sink.write("Preparation-only mode selected; no device upload was performed.")
        elif args.inference_probe:
            inference_checks = parse_inference_checks(args.inference_check)
            request = inference_request_from_args(args.install_args)
            install_attempted = True
            install_status = run_install_request(request, sink)
            sink.write(f"Installer exit status: {install_status}")
            validation_status = install_status
            if install_status == 0:
                probe_status = run_inference_probe(request, sink)
                sink.write(f"Inference probe exit status: {probe_status}")
                validation_status = probe_status
                if probe_status == 0:
                    inference_decision, inference_reason = extract_inference_decision(
                        sink.transcript
                    )
                    sink.write(f"Inference decision: {inference_decision}")
        else:
            request = install_request_from_args(args.install_args)
            install_attempted = True
            install_status = run_install_request(request, sink)
            sink.write(f"Installer exit status: {install_status}")
            validation_status = install_status
    except (InstallerError, OSError, subprocess.SubprocessError) as error:
        if args.inference_probe and install_status == 0 and probe_status == 0:
            probe_status = 1
        elif install_status is None:
            install_status = 1
        validation_status = 1
        sink.write(f"error: {error}", error=True)
        if args.inference_probe:
            sink.write("Inference probe exit status: 1")
        else:
            sink.write("Installer exit status: 1")
    finally:
        issue_body = write_capture_artifacts(
            capture_dir,
            sink,
            device_label=args.device_label,
            hardware_notes=args.hardware_note,
            install_status=install_status,
            prepared_only=prepared_only,
            inference_probe=args.inference_probe,
            probe_status=probe_status,
            inference_decision=inference_decision,
            inference_reason=inference_reason,
            inference_checks=inference_checks,
        )
        if (
            args.inference_probe
            and args.gh is not None
            and not prepared_only
            and install_attempted
            and issue_body is not None
        ):
            try:
                repository = resolve_github_repository(args.gh)
            except InstallerError as error:
                sink.write(f"warning: {error}; GitHub issue body prepared: {issue_body}", error=True)
            else:
                title = args.gh_title or default_inference_issue_title(
                    args.device_label,
                    validation_status,
                )
                create_github_issue(repository, title, issue_body, capture_dir, sink)
    return validation_status


def run_install_command(args: argparse.Namespace, sink: OutputSink) -> int:
    """Handle direct install.cmd invocation and return its process status."""
    if args.list_ports:
        ports = list_windows_serial_ports()
        if ports:
            sink.write("Detected Windows serial ports:")
            for port in ports:
                sink.write(f"  {port}")
            return 0
        sink.write("No Windows serial ports were detected.", error=True)
        return 1

    try:
        install_args: list[str] = []
        if args.port:
            install_args.extend(["--port", args.port])
        if args.no_reset:
            install_args.append("--no-reset")
        if args.assume_yes:
            install_args.append("--yes")
        request = install_request_from_args(install_args)
        return run_install_request(request, sink)
    except (InstallerError, OSError, subprocess.SubprocessError) as error:
        sink.write(f"error: {error}", error=True)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    """Run the requested Windows installer command and return an exit status."""
    parser = create_parser()
    args = parser.parse_args(argv)
    sink = OutputSink()
    if args.command == "install":
        return run_install_command(args, sink)
    if args.command == "developer":
        return run_developer_capture(args, sink)
    if args.command == "validate":
        return run_device_validation(args, sink)
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
