"""Offline on-device inference feasibility probe for AIPI-Lite."""

import gc
import time

DECISION_CANDIDATE_SUPPORTED = "candidate_supported"
DECISION_DEFER_INFERENCE = "defer_inference"
DECISION_OFFLINE_UNSUPPORTED = "offline_unsupported"

FEASIBILITY_DECISIONS = (
    DECISION_CANDIDATE_SUPPORTED,
    DECISION_DEFER_INFERENCE,
    DECISION_OFFLINE_UNSUPPORTED,
)

REQUIRED_MODEL_METADATA_FIELDS = (
    "model_id",
    "version",
    "source",
    "license",
    "checksum_sha256",
    "artifact_size_bytes",
)

FORBIDDEN_MODEL_METADATA_FIELDS = (
    "model_bytes",
    "weights",
    "binary",
    "token",
    "credential",
)

DEFAULT_PROMPT_RESPONSES = {
    "status": "offline fixture ready",
    "help": "offline fixture only; no network required",
    "privacy": "all inputs remain on device",
}


class InferencePolicyError(ValueError):
    """Raised when the inference probe would require networking."""


class ModelMetadataError(ValueError):
    """Raised when model metadata is missing, unsafe, or unapproved."""


class ResourceSnapshot:
    """Hold one resource measurement from the current runtime."""

    def __init__(
        self,
        timestamp_ms,
        heap_free=None,
        heap_alloc=None,
        flash_free=None,
        flash_size=None,
    ):
        """Create a resource snapshot with optional runtime metrics."""
        self.timestamp_ms = timestamp_ms
        self.heap_free = heap_free
        self.heap_alloc = heap_alloc
        self.flash_free = flash_free
        self.flash_size = flash_size

    def as_dict(self):
        """Return the snapshot as primitive values for serial reporting."""
        return {
            "timestamp_ms": self.timestamp_ms,
            "heap_free": self.heap_free,
            "heap_alloc": self.heap_alloc,
            "flash_free": self.flash_free,
            "flash_size": self.flash_size,
        }


class InferenceProbeConfig:
    """Configure an offline simulated inference workload."""

    def __init__(
        self,
        simulated_load_ms=750,
        memory_probe_bytes=4096,
        poll_interval_ms=50,
        max_iterations=40000,
        min_heap_free_bytes=65536,
        max_elapsed_ms=2000,
        require_io_poll=True,
    ):
        """Create bounded feasibility thresholds and workload settings."""
        self.simulated_load_ms = _positive_int(simulated_load_ms, "simulated_load_ms")
        self.memory_probe_bytes = _positive_or_zero_int(
            memory_probe_bytes,
            "memory_probe_bytes",
        )
        self.poll_interval_ms = _positive_int(poll_interval_ms, "poll_interval_ms")
        self.max_iterations = _positive_int(max_iterations, "max_iterations")
        self.min_heap_free_bytes = _positive_int(min_heap_free_bytes, "min_heap_free_bytes")
        self.max_elapsed_ms = _positive_int(max_elapsed_ms, "max_elapsed_ms")
        self.require_io_poll = bool(require_io_poll)


class ModelMetadata:
    """Hold validated model provenance metadata without loading artifacts."""

    def __init__(self, model_id, version, source, license_name, checksum_sha256, artifact_size_bytes):
        """Create a validated model metadata record."""
        self.model_id = model_id
        self.version = version
        self.source = source
        self.license = license_name
        self.checksum_sha256 = checksum_sha256
        self.artifact_size_bytes = artifact_size_bytes

    def as_dict(self):
        """Return model metadata as primitive values."""
        return {
            "model_id": self.model_id,
            "version": self.version,
            "source": self.source,
            "license": self.license,
            "checksum_sha256": self.checksum_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
        }


class LocalPromptFixture:
    """Return deterministic offline responses for feasibility experiments."""

    def __init__(self, responses=None):
        """Create a prompt fixture from an optional response mapping."""
        self.responses = dict(DEFAULT_PROMPT_RESPONSES)
        if responses:
            for key in responses:
                self.responses[_normalize_prompt(key)] = str(responses[key])

    def respond(self, prompt):
        """Return an offline fixture response for a prompt."""
        key = _normalize_prompt(prompt)
        if key in self.responses:
            return self.responses[key]
        return "unsupported offline prompt"


class InferenceProbeResult:
    """Summarize one offline inference feasibility probe run."""

    def __init__(
        self,
        before,
        after,
        elapsed_ms,
        iterations,
        checksum,
        button_poll_count,
        button_events,
        prompt_response,
        decision,
        reason,
        memory_probe_bytes,
    ):
        """Create a result with resource, responsiveness, and decision data."""
        self.before = before
        self.after = after
        self.elapsed_ms = elapsed_ms
        self.iterations = iterations
        self.checksum = checksum
        self.button_poll_count = button_poll_count
        self.button_events = tuple(button_events)
        self.prompt_response = prompt_response
        self.decision = _validate_decision(decision)
        self.reason = reason
        self.memory_probe_bytes = memory_probe_bytes

    def as_dict(self):
        """Return the probe result as primitive values."""
        return {
            "before": self.before.as_dict(),
            "after": self.after.as_dict(),
            "elapsed_ms": self.elapsed_ms,
            "iterations": self.iterations,
            "checksum": self.checksum,
            "button_poll_count": self.button_poll_count,
            "button_events": self.button_events,
            "prompt_response": self.prompt_response,
            "decision": self.decision,
            "reason": self.reason,
            "memory_probe_bytes": self.memory_probe_bytes,
        }

    def serial_lines(self):
        """Return stable serial-friendly probe output lines."""
        return (
            "inference_probe: elapsed_ms={} iterations={} checksum={}".format(
                self.elapsed_ms,
                self.iterations,
                self.checksum,
            ),
            "inference_probe: heap_before={} heap_after={} flash_free={}".format(
                _metric_text(self.before.heap_free),
                _metric_text(self.after.heap_free),
                _metric_text(self.after.flash_free),
            ),
            "inference_probe: button_polls={} button_events={}".format(
                self.button_poll_count,
                ",".join(self.button_events) if self.button_events else "none",
            ),
            "inference_probe: prompt_response={}".format(self.prompt_response),
            "inference_probe: decision={} reason={}".format(self.decision, self.reason),
        )


def ticks_ms():
    """Return monotonic milliseconds on MicroPython or CPython."""
    if hasattr(time, "ticks_ms"):
        return time.ticks_ms()
    return int(time.time() * 1000)


def ticks_diff(newer, older):
    """Return the signed millisecond difference between two tick values."""
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(newer, older)
    return newer - older


def sleep_ms(milliseconds):
    """Sleep for a bounded probe delay on MicroPython or CPython."""
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(milliseconds)
        return
    time.sleep(milliseconds / 1000)


def assert_offline_probe_config(network_required=False, endpoint_url=None):
    """Raise when a feasibility probe would require network connectivity."""
    if network_required:
        raise InferencePolicyError("inference feasibility probe must be offline-first")
    if endpoint_url:
        raise InferencePolicyError("inference feasibility probe must not require an endpoint")
    return True


def validate_model_metadata(metadata, approved_model_ids=()):
    """Validate traceable model metadata without loading a model artifact."""
    if not isinstance(metadata, dict):
        raise ModelMetadataError("model metadata must be a dict")

    for field in FORBIDDEN_MODEL_METADATA_FIELDS:
        if field in metadata:
            raise ModelMetadataError("model metadata must not include {}".format(field))

    for field in REQUIRED_MODEL_METADATA_FIELDS:
        if field not in metadata or metadata[field] in ("", None):
            raise ModelMetadataError("model metadata missing {}".format(field))

    model_id = str(metadata["model_id"])
    if approved_model_ids and model_id not in tuple(approved_model_ids):
        raise ModelMetadataError("unknown model artifact: {}".format(model_id))

    checksum = str(metadata["checksum_sha256"]).lower()
    if len(checksum) != 64 or not all(character in "0123456789abcdef" for character in checksum):
        raise ModelMetadataError("checksum_sha256 must be a 64-character hex digest")

    artifact_size_bytes = _positive_int(metadata["artifact_size_bytes"], "artifact_size_bytes")

    return ModelMetadata(
        model_id=model_id,
        version=str(metadata["version"]),
        source=str(metadata["source"]),
        license_name=str(metadata["license"]),
        checksum_sha256=checksum,
        artifact_size_bytes=artifact_size_bytes,
    )


def collect_resource_snapshot(ticks_ms_func=ticks_ms, gc_module=gc, os_module=None, filesystem_path="/"):
    """Collect heap and flash metrics exposed by the current runtime."""
    if os_module is None:
        try:
            import os as os_module
        except ImportError:
            os_module = None

    heap_free = _call_optional(gc_module, "mem_free")
    heap_alloc = _call_optional(gc_module, "mem_alloc")
    flash_free = None
    flash_size = None

    if os_module is not None and hasattr(os_module, "statvfs"):
        try:
            stats = os_module.statvfs(filesystem_path)
            block_size = int(stats[0])
            flash_size = int(stats[2]) * block_size
            flash_free = int(stats[3]) * block_size
        except (AttributeError, IndexError, OSError, TypeError, ValueError):
            flash_free = None
            flash_size = None

    return ResourceSnapshot(
        timestamp_ms=ticks_ms_func(),
        heap_free=heap_free,
        heap_alloc=heap_alloc,
        flash_free=flash_free,
        flash_size=flash_size,
    )


def run_local_prompt_experiment(prompt="status", fixture=None):
    """Run a deterministic prompt experiment without network access."""
    if fixture is None:
        fixture = LocalPromptFixture()
    return fixture.respond(prompt)


def run_feasibility_probe(
    config=None,
    prompt="status",
    fixture=None,
    button=None,
    status_led=None,
    status_display=None,
    print_func=print,
    snapshot_func=collect_resource_snapshot,
    ticks_ms_func=ticks_ms,
    sleep_ms_func=sleep_ms,
    network_required=False,
    endpoint_url=None,
):
    """Measure offline resource use and UI responsiveness under simulated load."""
    assert_offline_probe_config(network_required=network_required, endpoint_url=endpoint_url)
    if config is None:
        config = InferenceProbeConfig()

    before = snapshot_func()
    prompt_response = run_local_prompt_experiment(prompt=prompt, fixture=fixture)
    button_events = []
    button_poll_count = 0
    checksum = 0
    payload = bytearray(config.memory_probe_bytes) if config.memory_probe_bytes else None
    start_ms = ticks_ms_func()
    last_poll_ms = start_ms

    _set_probe_status(status_led, status_display, "processing", "offline inference")
    print_func("inference_probe: starting offline simulated inference load")

    iterations = 0
    while iterations < config.max_iterations:
        now_ms = ticks_ms_func()
        if ticks_diff(now_ms, start_ms) >= config.simulated_load_ms:
            break

        checksum = _run_work_iteration(iterations, checksum, payload)
        if ticks_diff(now_ms, last_poll_ms) >= config.poll_interval_ms:
            button_poll_count += 1
            _poll_button(button, button_events)
            _set_probe_status(status_led, status_display, "processing", "offline inference")
            last_poll_ms = now_ms
        iterations += 1

    after = snapshot_func()
    elapsed_ms = ticks_diff(ticks_ms_func(), start_ms)
    decision, reason = decide_feasibility(
        before,
        after,
        elapsed_ms,
        button_poll_count,
        config,
    )
    final_status = "ready" if decision == DECISION_CANDIDATE_SUPPORTED else "error"
    _set_probe_status(status_led, status_display, final_status, decision)

    result = InferenceProbeResult(
        before=before,
        after=after,
        elapsed_ms=elapsed_ms,
        iterations=iterations,
        checksum=checksum,
        button_poll_count=button_poll_count,
        button_events=button_events,
        prompt_response=prompt_response,
        decision=decision,
        reason=reason,
        memory_probe_bytes=config.memory_probe_bytes,
    )
    for line in result.serial_lines():
        print_func(line)
    print_func("inference_probe: complete")
    return result


def decide_feasibility(before, after, elapsed_ms, button_poll_count, config):
    """Return a feasibility decision and reason for measured probe data."""
    if after.heap_free is None:
        return DECISION_DEFER_INFERENCE, "heap metric unavailable"
    if after.heap_free < config.min_heap_free_bytes:
        return DECISION_OFFLINE_UNSUPPORTED, "heap below threshold"
    if elapsed_ms > config.max_elapsed_ms:
        return DECISION_DEFER_INFERENCE, "simulated load exceeded timing threshold"
    if config.require_io_poll and button_poll_count <= 0:
        return DECISION_DEFER_INFERENCE, "button responsiveness was not observed"
    return DECISION_CANDIDATE_SUPPORTED, "offline probe stayed within thresholds"


def run_probe(
    print_func=print,
    config=None,
    prompt="status",
    status_led=None,
    status_display=None,
    button=None,
):
    """Run the explicit offline inference feasibility probe on device hardware."""
    if status_led is None:
        try:
            from status_led import StatusLed

            status_led = StatusLed()
        except Exception as exc:
            print_func("inference_probe: status LED skipped: {}".format(type(exc).__name__))
    if status_display is None:
        try:
            from display import create_status_display

            status_display = create_status_display()
        except Exception as exc:
            print_func("inference_probe: display skipped: {}".format(type(exc).__name__))
    if button is None:
        try:
            from button import DebouncedButton

            button = DebouncedButton()
        except Exception as exc:
            print_func("inference_probe: button skipped: {}".format(type(exc).__name__))

    return run_feasibility_probe(
        config=config,
        prompt=prompt,
        button=button,
        status_led=status_led,
        status_display=status_display,
        print_func=print_func,
    )


def _positive_int(value, field_name):
    """Return value as a positive integer or raise ValueError."""
    try:
        integer = int(value)
    except (TypeError, ValueError):
        raise ValueError("{} must be an integer".format(field_name))
    if integer <= 0:
        raise ValueError("{} must be greater than zero".format(field_name))
    return integer


def _positive_or_zero_int(value, field_name):
    """Return value as a non-negative integer or raise ValueError."""
    try:
        integer = int(value)
    except (TypeError, ValueError):
        raise ValueError("{} must be an integer".format(field_name))
    if integer < 0:
        raise ValueError("{} must not be negative".format(field_name))
    return integer


def _call_optional(module, function_name):
    """Call a no-argument runtime metric function when it exists."""
    if module is None or not hasattr(module, function_name):
        return None
    try:
        return getattr(module, function_name)()
    except (AttributeError, OSError, TypeError, ValueError):
        return None


def _normalize_prompt(prompt):
    """Return a stable prompt key for the local fixture."""
    return str(prompt).strip().lower()


def _metric_text(value):
    """Return a stable serial representation for optional metrics."""
    if value is None:
        return "unavailable"
    return str(value)


def _validate_decision(decision):
    """Return a supported feasibility decision or raise."""
    if decision not in FEASIBILITY_DECISIONS:
        raise ValueError("unknown feasibility decision: {}".format(decision))
    return decision


def _run_work_iteration(index, checksum, payload):
    """Run one deterministic CPU and optional memory-touch workload iteration."""
    checksum = (checksum + ((index + 1) * 31)) % 65535
    if payload is not None and len(payload):
        payload[index % len(payload)] = checksum % 256
    return checksum


def _poll_button(button, button_events):
    """Poll an optional debounced button and retain visible events."""
    if button is None or not hasattr(button, "update"):
        return
    event = button.update()
    if event is not None:
        button_events.append(event)


def _set_probe_status(status_led, status_display, status, detail):
    """Update optional LED and display outputs with probe state."""
    led_state = "processing" if status == "processing" else status
    display_status = "processing" if status == "processing" else status
    if status_led is not None:
        status_led.set_state(led_state)
    if status_display is not None:
        status_display.render_status(display_status, detail=detail)


if __name__ == "__main__":
    run_probe()
