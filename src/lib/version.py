"""Version metadata for the local-only AIPI-Lite MVP firmware."""

from service_contract import CONTRACT_VERSION

FIRMWARE_NAME = "aipi-lite"
FIRMWARE_VERSION = "0.1.0-local-mvp"
FIRMWARE_PROFILE = "local-only-mvp"
TARGET_MODEL = "XY006PL01"
LOCAL_ONLY = True


def firmware_metadata(runtime_name="MicroPython", runtime_version="unknown"):
    """Return traceable firmware and runtime metadata."""
    return {
        "firmware_name": FIRMWARE_NAME,
        "firmware_version": FIRMWARE_VERSION,
        "firmware_profile": FIRMWARE_PROFILE,
        "target_model": TARGET_MODEL,
        "local_only": LOCAL_ONLY,
        "service_contract": CONTRACT_VERSION,
        "runtime_name": runtime_name,
        "runtime_version": runtime_version,
    }


def firmware_banner(runtime_name="MicroPython", runtime_version="unknown"):
    """Return a serial-friendly firmware version banner."""
    metadata = firmware_metadata(runtime_name=runtime_name, runtime_version=runtime_version)
    return "{firmware_name} {firmware_version} {firmware_profile} {target_model}".format(**metadata)
