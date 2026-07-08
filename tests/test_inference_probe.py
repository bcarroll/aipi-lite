"""Tests for the offline inference feasibility probe."""

import importlib
from pathlib import Path
import sys
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"

MODULES_TO_CLEAR = ("inference_probe",)


class FakeButton:
    """Return deterministic button events during probe polling."""

    def __init__(self, events=()):
        """Create a fake button with queued events."""
        self.events = list(events)
        self.update_calls = 0

    def update(self):
        """Record a button poll and return the next queued event."""
        self.update_calls += 1
        if self.events:
            return self.events.pop(0)
        return None


class FakeStatusLed:
    """Record status LED states requested by the probe."""

    def __init__(self):
        """Create an empty LED recorder."""
        self.states = []

    def set_state(self, state):
        """Record the requested LED state."""
        self.states.append(state)


class FakeStatusDisplay:
    """Record display status renders requested by the probe."""

    def __init__(self):
        """Create an empty display recorder."""
        self.screens = []

    def render_status(self, status, detail=None):
        """Record the requested status screen and detail."""
        self.screens.append((status, detail))


class IncrementingTicks:
    """Return monotonically increasing milliseconds."""

    def __init__(self, step_ms=30):
        """Create a monotonic counter with a fixed step."""
        self.step_ms = step_ms
        self.current = -step_ms

    def __call__(self):
        """Return the next timestamp."""
        self.current += self.step_ms
        return self.current


def clear_imported_modules():
    """Remove imported firmware modules after each test."""
    for module_name in MODULES_TO_CLEAR:
        sys.modules.pop(module_name, None)


def ensure_src_path():
    """Make the device-side source tree importable by host-side tests."""
    src_path = str(SRC_ROOT)
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


class InferenceProbeTests(unittest.TestCase):
    """Validate offline inference feasibility logic without hardware."""

    def setUp(self):
        """Import a fresh inference probe module."""
        clear_imported_modules()
        ensure_src_path()
        self.inference_probe = importlib.import_module("inference_probe")

    def tearDown(self):
        """Clean imported firmware modules after each test."""
        clear_imported_modules()

    def snapshots(self, before_heap=200000, after_heap=180000):
        """Return a snapshot provider with deterministic before/after data."""
        snapshots = [
            self.inference_probe.ResourceSnapshot(
                0,
                heap_free=before_heap,
                heap_alloc=1000,
                flash_free=1024 * 1024,
                flash_size=2 * 1024 * 1024,
            ),
            self.inference_probe.ResourceSnapshot(
                120,
                heap_free=after_heap,
                heap_alloc=2000,
                flash_free=1024 * 1024,
                flash_size=2 * 1024 * 1024,
            ),
        ]

        def snapshot_func():
            """Return the next fake resource snapshot."""
            return snapshots.pop(0)

        return snapshot_func

    def test_offline_policy_rejects_network_requirements_and_endpoints(self):
        """Inference feasibility should not require Wi-Fi, LAN, or public endpoints."""
        self.assertTrue(self.inference_probe.assert_offline_probe_config())

        with self.assertRaises(self.inference_probe.InferencePolicyError):
            self.inference_probe.assert_offline_probe_config(network_required=True)

        with self.assertRaises(self.inference_probe.InferencePolicyError):
            self.inference_probe.assert_offline_probe_config(endpoint_url="https://example.com")

    def test_model_metadata_validation_requires_traceable_approved_artifact(self):
        """Model metadata should be complete, checksummed, and approved when an allow-list is used."""
        metadata = {
            "model_id": "tiny-local-fixture",
            "version": "0.1",
            "source": "repo fixture",
            "license": "test-only",
            "checksum_sha256": "a" * 64,
            "artifact_size_bytes": 4096,
        }

        validated = self.inference_probe.validate_model_metadata(
            metadata,
            approved_model_ids=("tiny-local-fixture",),
        )

        self.assertEqual(validated.model_id, "tiny-local-fixture")
        self.assertEqual(validated.artifact_size_bytes, 4096)
        self.assertEqual(validated.as_dict()["checksum_sha256"], "a" * 64)

        with self.assertRaises(self.inference_probe.ModelMetadataError):
            self.inference_probe.validate_model_metadata(
                metadata,
                approved_model_ids=("different-model",),
            )

    def test_model_metadata_rejects_missing_checksum_and_embedded_binary(self):
        """Model metadata should reject unknown or unsafe artifact descriptions."""
        missing_checksum = {
            "model_id": "tiny-local-fixture",
            "version": "0.1",
            "source": "repo fixture",
            "license": "test-only",
            "artifact_size_bytes": 4096,
        }
        with self.assertRaises(self.inference_probe.ModelMetadataError):
            self.inference_probe.validate_model_metadata(missing_checksum)

        embedded_binary = dict(missing_checksum)
        embedded_binary["checksum_sha256"] = "b" * 64
        embedded_binary["model_bytes"] = b"not allowed"
        with self.assertRaises(self.inference_probe.ModelMetadataError):
            self.inference_probe.validate_model_metadata(embedded_binary)

    def test_probe_can_reach_candidate_supported_without_networking(self):
        """A bounded offline load with button polling should be marked candidate supported."""
        led = FakeStatusLed()
        display = FakeStatusDisplay()
        button = FakeButton(events=("pressed",))
        messages = []
        config = self.inference_probe.InferenceProbeConfig(
            simulated_load_ms=100,
            poll_interval_ms=25,
            min_heap_free_bytes=65536,
            max_elapsed_ms=1000,
        )

        result = self.inference_probe.run_feasibility_probe(
            config=config,
            button=button,
            status_led=led,
            status_display=display,
            print_func=messages.append,
            snapshot_func=self.snapshots(),
            ticks_ms_func=IncrementingTicks(step_ms=30),
            sleep_ms_func=lambda milliseconds: None,
        )

        self.assertEqual(result.decision, self.inference_probe.DECISION_CANDIDATE_SUPPORTED)
        self.assertEqual(result.button_events, ("pressed",))
        self.assertGreaterEqual(result.button_poll_count, 1)
        self.assertEqual(result.prompt_response, "offline fixture ready")
        self.assertEqual(led.states[-1], "ready")
        self.assertEqual(display.screens[-1], ("ready", "candidate_supported"))
        self.assertIn("inference_probe: complete", messages)

    def test_probe_defers_when_button_responsiveness_is_not_observed(self):
        """The probe should defer inference when required button polling is absent."""
        config = self.inference_probe.InferenceProbeConfig(
            simulated_load_ms=30,
            poll_interval_ms=100,
            max_elapsed_ms=1000,
        )

        result = self.inference_probe.run_feasibility_probe(
            config=config,
            print_func=lambda message: None,
            snapshot_func=self.snapshots(),
            ticks_ms_func=IncrementingTicks(step_ms=30),
            sleep_ms_func=lambda milliseconds: None,
        )

        self.assertEqual(result.decision, self.inference_probe.DECISION_DEFER_INFERENCE)
        self.assertEqual(result.reason, "button responsiveness was not observed")

    def test_probe_marks_low_heap_as_offline_unsupported(self):
        """The probe should reject offline inference when heap falls below threshold."""
        config = self.inference_probe.InferenceProbeConfig(
            simulated_load_ms=100,
            poll_interval_ms=25,
            min_heap_free_bytes=65536,
            max_elapsed_ms=1000,
        )

        result = self.inference_probe.run_feasibility_probe(
            config=config,
            button=FakeButton(),
            print_func=lambda message: None,
            snapshot_func=self.snapshots(before_heap=70000, after_heap=64000),
            ticks_ms_func=IncrementingTicks(step_ms=30),
            sleep_ms_func=lambda milliseconds: None,
        )

        self.assertEqual(result.decision, self.inference_probe.DECISION_OFFLINE_UNSUPPORTED)
        self.assertEqual(result.reason, "heap below threshold")

    def test_local_prompt_fixture_stays_deterministic_and_offline(self):
        """Prompt experiments should use deterministic local fixture responses."""
        fixture = self.inference_probe.LocalPromptFixture({"custom": "local answer"})

        self.assertEqual(
            self.inference_probe.run_local_prompt_experiment("custom", fixture=fixture),
            "local answer",
        )
        self.assertEqual(
            self.inference_probe.run_local_prompt_experiment("unknown", fixture=fixture),
            "unsupported offline prompt",
        )


if __name__ == "__main__":
    unittest.main()
