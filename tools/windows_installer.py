"""Windows application-first installer support for the AIPI-Lite.

The module is called by the repository's native CMD entry points. It keeps
Windows-specific host tooling under ``tools/.local`` and deliberately supports
only application upload and developer capture; firmware flash and recovery
actions remain available through the established Unix workflow.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Sequence, TextIO


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
TOOLS_ROOT = REPO_ROOT / "tools" / ".local"
VENV_DIR = TOOLS_ROOT / "micropython-venv"
CAPTURE_ROOT = TOOLS_ROOT / "dev-install"
COM_PORT_PATTERN = re.compile(r"COM[1-9][0-9]*", re.IGNORECASE)
SECRET_PATTERN = re.compile(
    r"(?i)\b(password|passwd|token|secret|key|ssid)\s*([=:])\s*[^\s]+"
)
MAC_ADDRESS_PATTERN = re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")
SERIAL_PORT_PATTERN = re.compile(r"(?i)\bCOM[1-9][0-9]*\b")


class InstallerError(RuntimeError):
    """Represent an expected installer failure that should be shown to an operator."""


@dataclass(frozen=True)
class InstallRequest:
    """Describe a normal application-first upload request."""

    port: str
    no_reset: bool
    assume_yes: bool


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
        "install_args",
        nargs=argparse.REMAINDER,
        help="Installer options after --, such as -- --port COM3.",
    )
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


def run_install_request(request: InstallRequest, sink: OutputSink) -> int:
    """Upload the application source and reset the target unless reset is disabled."""
    validate_upload_request(request)
    executable = ensure_mpremote(request.assume_yes, sink)
    source_path = f"{SRC_DIR}{os.sep}"
    upload_command = [
        str(executable),
        "connect",
        request.port,
        "fs",
        "cp",
        "-r",
        source_path,
        ":",
    ]
    sink.write(f"Uploading application source to {request.port}...")
    upload_status = run_streaming(upload_command, sink)
    if upload_status != 0:
        sink.write(f"Application upload failed with status {upload_status}.", error=True)
        return upload_status

    if request.no_reset:
        sink.write("Application upload complete; reset skipped by --no-reset.")
        return 0

    sink.write(f"Resetting {request.port}...")
    reset_status = run_streaming([str(executable), "connect", request.port, "reset"], sink)
    if reset_status != 0:
        sink.write(f"Application upload succeeded but reset failed with status {reset_status}.", error=True)
        return reset_status
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


def redact_text(text: str) -> str:
    """Remove common secrets, MAC addresses, and COM ports from shareable text."""
    redacted = SECRET_PATTERN.sub(r"\1\2<redacted>", text)
    redacted = MAC_ADDRESS_PATTERN.sub("<redacted-mac>", redacted)
    return SERIAL_PORT_PATTERN.sub("<redacted-serial-port>", redacted)


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
) -> None:
    """Write raw, redacted, and non-secret metadata files for a capture run."""
    capture_dir.mkdir(parents=True, exist_ok=True)
    raw_transcript = capture_dir / "install-transcript-raw.txt"
    redacted_transcript = capture_dir / "install-transcript-redacted.txt"
    metadata = capture_dir / "run-metadata.txt"
    raw_transcript.write_text(sink.transcript, encoding="utf-8")
    redacted_transcript.write_text(redact_text(sink.transcript), encoding="utf-8")
    metadata_lines = [
        "workflow=windows-dev-install",
        f"prepared_only={'yes' if prepared_only else 'no'}",
        f"installer_exit_status={install_status if install_status is not None else 'not-run'}",
        f"device_label={redact_text(device_label)}",
    ]
    metadata_lines.extend(f"hardware_note={redact_text(note)}" for note in hardware_notes)
    metadata.write_text("\n".join(metadata_lines) + "\n", encoding="utf-8")


def run_developer_capture(args: argparse.Namespace, sink: OutputSink) -> int:
    """Run or prepare a developer capture and return the installer outcome."""
    capture_dir = args.capture_dir or default_capture_directory()
    sink.write(f"Developer capture directory: {capture_dir}")
    install_status: int | None = None
    prepared_only = bool(args.prepare_only)
    try:
        if prepared_only:
            sink.write("Preparation-only mode selected; no device upload was performed.")
            return 0
        request = install_request_from_args(args.install_args)
        install_status = run_install_request(request, sink)
        sink.write(f"Installer exit status: {install_status}")
        return install_status
    except (InstallerError, OSError, subprocess.SubprocessError) as error:
        install_status = 1
        sink.write(f"error: {error}", error=True)
        sink.write("Installer exit status: 1")
        return 1
    finally:
        write_capture_artifacts(
            capture_dir,
            sink,
            device_label=args.device_label,
            hardware_notes=args.hardware_note,
            install_status=install_status,
            prepared_only=prepared_only,
        )


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
    parser.error(f"unsupported command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
