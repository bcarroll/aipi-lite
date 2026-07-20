"""Shared host helpers for deploying the AIPI-Lite MicroPython application."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


LEGACY_ROOT_MODULES = (
    "aipi_lite_config.py",
    "assistant_state.py",
    "audio_capture.py",
    "audio_playback.py",
    "audio_probe.py",
    "button.py",
    "capture_probe.py",
    "display.py",
    "display_probe.py",
    "es8311.py",
    "io_probe.py",
    "local_endpoint.py",
    "pins.py",
    "playback_probe.py",
    "push_to_talk.py",
    "reliability.py",
    "service_client.py",
    "service_contract.py",
    "status_led.py",
    "version.py",
    "wifi_config.py",
    "wifi_probe.py",
)
CLEANUP_COMPLETE_MARKER = "aipi-lite installer cleanup complete"
MISPLACED_SOURCE_SIGNATURES = ("boot.py", "main.py", "lib/pins.py")
UPLOAD_IGNORED_NAMES = {"__pycache__", ".DS_Store"}


def ignored_upload_artifacts(_directory: str, names: list[str]) -> set[str]:
    """Return host-only source artifacts that must not be copied to the device."""
    return {
        name
        for name in names
        if name in UPLOAD_IGNORED_NAMES or name.endswith(".pyc")
    }


def application_manifest(source_root: Path) -> tuple[str, ...]:
    """Return filtered application file paths relative to the supplied source root."""
    return tuple(
        sorted(
            path.relative_to(source_root).as_posix()
            for path in source_root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.relative_to(source_root).parts
            and path.name != ".DS_Store"
            and not path.name.endswith(".pyc")
        )
    )


def application_cleanup_code(source_manifest: Sequence[str]) -> str:
    """Return guarded device-side cleanup code for legacy and misplaced files."""
    return (
        "import os\n"
        f"expected_files = set({tuple(source_manifest)!r})\n"
        f"required_files = {MISPLACED_SOURCE_SIGNATURES!r}\n"
        "def walk_tree(root, prefix=''):\n"
        "    files = []\n"
        "    directories = []\n"
        "    for name in os.listdir(root):\n"
        "        path = root + '/' + name\n"
        "        relative = prefix + name\n"
        "        if os.stat(path)[0] & 0x4000:\n"
        "            directories.append(path)\n"
        "            child_files, child_directories = walk_tree(path, relative + '/')\n"
        "            files.extend(child_files)\n"
        "            directories.extend(child_directories)\n"
        "        else:\n"
        "            files.append((path, relative))\n"
        "    return files, directories\n"
        "try:\n"
        "    misplaced_files, misplaced_directories = walk_tree('/src')\n"
        "except OSError:\n"
        "    misplaced_files, misplaced_directories = [], []\n"
        "misplaced_names = set(relative for path, relative in misplaced_files)\n"
        "recognized = all(path in misplaced_names for path in required_files)\n"
        "recognized = recognized and all(\n"
        "    relative in expected_files or '__pycache__' in relative.split('/') or relative.endswith('.pyc')\n"
        "    for path, relative in misplaced_files\n"
        ")\n"
        "if recognized:\n"
        "    for path, relative in misplaced_files:\n"
        "        os.remove(path)\n"
        "    for path in reversed(misplaced_directories):\n"
        "        os.rmdir(path)\n"
        "    os.rmdir('/src')\n"
        "    print('removed misplaced application tree: /src')\n"
        "elif misplaced_files or misplaced_directories:\n"
        "    print('warning: preserved /src because it contains unknown device files')\n"
        f"for path in {LEGACY_ROOT_MODULES!r}:\n"
        "    try:\n"
        "        os.remove(path)\n"
        "        print('removed legacy root module: {}'.format(path))\n"
        "    except OSError:\n"
        "        pass\n"
        f"print({CLEANUP_COMPLETE_MARKER!r})"
    )


def create_parser() -> argparse.ArgumentParser:
    """Create the command parser used by the Unix installer."""
    parser = argparse.ArgumentParser(
        description="Generate guarded AIPI-Lite device application cleanup code."
    )
    parser.add_argument("--source", required=True, type=Path, help="Application source tree.")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    """Print cleanup code for an application source tree."""
    args = create_parser().parse_args(arguments)
    if not args.source.is_dir():
        raise SystemExit(f"application source directory is missing: {args.source}")
    manifest = application_manifest(args.source)
    if not manifest:
        raise SystemExit(f"application source directory is empty: {args.source}")
    print(application_cleanup_code(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
