"""Tests for the developer installer capture wrapper."""

from pathlib import Path
import os
import subprocess
import tempfile
import textwrap
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
DEV_INSTALL_SCRIPT = REPO_ROOT / "dev_install.sh"
GITIGNORE = REPO_ROOT / ".gitignore"


class DevInstallCaptureTests(unittest.TestCase):
    """Validate host-side install capture behavior without attached hardware."""

    def make_script(self, directory, name, body):
        """Create an executable shell script for a test fixture."""
        script_path = Path(directory) / name
        script_path.write_text(textwrap.dedent(body), encoding="utf-8")
        script_path.chmod(0o755)
        return script_path

    def run_dev_install(self, args, installer_body, extra_env=None):
        """Run dev_install.sh against a stub installer and return the result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            capture_dir = tmp_path / "capture"
            installer = self.make_script(tmp_path, "stub_install.sh", installer_body)

            env = os.environ.copy()
            env.update(
                {
                    "AIPI_DEV_INSTALL_SCRIPT": str(installer),
                    "AIPI_DEV_GH_BIN": str(tmp_path / "missing-gh"),
                    "AIPI_DEV_INSTALL_MAX_ISSUE_BYTES": "20000",
                    "HOME": str(tmp_path),
                }
            )
            if extra_env:
                env.update(extra_env)

            result = subprocess.run(
                [str(DEV_INSTALL_SCRIPT), "--capture-dir", str(capture_dir), *args],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            artifacts = {
                path.name: path.read_text(encoding="utf-8")
                for path in capture_dir.iterdir()
                if path.is_file()
            }
            modes = {
                path.name: path.stat().st_mode & 0o777
                for path in capture_dir.iterdir()
                if path.is_file()
            }
            return result, artifacts, modes

    def test_passes_arguments_and_preserves_installer_status(self):
        """The wrapper should pass installer args through and return installer status."""
        result, artifacts, _modes = self.run_dev_install(
            [
                "--prepare-only",
                "--device-label",
                "bench-a",
                "--hardware-note",
                "button press observed",
                "--",
                "--port",
                "/dev/cu.TEST",
                "--debug",
            ],
            """
            #!/usr/bin/env bash
            printf 'stdout visible token=abc123 ssid=labwifi\\n'
            printf 'stderr visible password=hunter2\\n' >&2
            printf 'args:%s\\n' "$*"
            exit 7
            """,
        )

        self.assertEqual(result.returncode, 7)
        self.assertIn("stdout visible token=abc123 ssid=labwifi", result.stdout)
        self.assertIn("stderr visible password=hunter2", result.stdout)
        self.assertIn("args:--port /dev/cu.TEST --debug", result.stdout)
        self.assertIn("Installer exit status: 7", result.stdout)

        raw_transcript = artifacts["install-transcript-raw.txt"]
        redacted_transcript = artifacts["install-transcript-redacted.txt"]
        issue_body = artifacts["github-issue-body.md"]
        metadata = artifacts["run-metadata.txt"]

        self.assertIn("token=abc123", raw_transcript)
        self.assertIn("password=hunter2", raw_transcript)
        self.assertNotIn("token=abc123", redacted_transcript)
        self.assertNotIn("password=hunter2", redacted_transcript)
        self.assertIn("token=<redacted>", redacted_transcript)
        self.assertIn("password=<redacted>", redacted_transcript)
        self.assertIn("Installer exit status: `7`", issue_body)
        self.assertIn("bench-a", issue_body)
        self.assertIn("button press observed", issue_body)
        self.assertIn("<home>", issue_body)
        self.assertNotIn("hunter2", issue_body)
        self.assertIn("installer_exit_status=7", metadata)

    def test_posts_to_explicit_github_issue_when_gh_is_available(self):
        """An explicit GitHub issue target should post through gh when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            capture_dir = tmp_path / "capture"
            installer = self.make_script(
                tmp_path,
                "stub_install.sh",
                """
                #!/usr/bin/env bash
                printf 'install ok\\n'
                exit 0
                """,
            )
            gh_log = tmp_path / "gh-args.txt"
            gh = self.make_script(
                tmp_path,
                "gh",
                f"""
                #!/usr/bin/env bash
                printf '%s\\n' "$*" > {gh_log}
                exit 0
                """,
            )
            env = os.environ.copy()
            env.update(
                {
                    "AIPI_DEV_INSTALL_SCRIPT": str(installer),
                    "AIPI_DEV_GH_BIN": str(gh),
                }
            )

            result = subprocess.run(
                [
                    str(DEV_INSTALL_SCRIPT),
                    "--capture-dir",
                    str(capture_dir),
                    "--issue",
                    "owner/repo#42",
                    "--",
                    "--skip-self-update",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("Posted redacted install capture to owner/repo#42", result.stdout)
            self.assertIn("issue comment 42 --repo owner/repo --body-file", gh_log.read_text())

    def test_creates_github_issue_when_gh_option_is_available(self):
        """The --gh option should create a new issue from the redacted body."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            capture_dir = tmp_path / "capture"
            installer = self.make_script(
                tmp_path,
                "stub_install.sh",
                """
                #!/usr/bin/env bash
                printf 'args:%s\\n' "$*"
                printf 'install ok\\n'
                exit 0
                """,
            )
            gh_log = tmp_path / "gh-create-args.txt"
            gh = self.make_script(
                tmp_path,
                "gh",
                f"""
                #!/usr/bin/env bash
                printf '%s\\n' "$*" > {gh_log}
                printf 'https://github.com/owner/repo/issues/77\\n'
                exit 0
                """,
            )
            env = os.environ.copy()
            env.update(
                {
                    "AIPI_DEV_INSTALL_SCRIPT": str(installer),
                    "AIPI_DEV_GH_BIN": str(gh),
                    "HOME": str(tmp_path),
                }
            )

            result = subprocess.run(
                [
                    str(DEV_INSTALL_SCRIPT),
                    "--capture-dir",
                    str(capture_dir),
                    "--gh",
                    "owner/repo",
                    "--gh-title",
                    "Bench validation",
                    "--device-label",
                    "bench-a",
                    "--",
                    "--trace",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn(
                "Created GitHub issue: https://github.com/owner/repo/issues/77",
                result.stdout,
            )
            gh_args = gh_log.read_text(encoding="utf-8")
            self.assertIn(
                "issue create --repo owner/repo --title Bench validation --body-file",
                gh_args,
            )
            self.assertEqual(
                (capture_dir / "github-created-issue.txt").read_text(encoding="utf-8"),
                "https://github.com/owner/repo/issues/77\n",
            )
            self.assertIn(
                "Installer arguments: `--trace `",
                (capture_dir / "github-issue-body.md").read_text(encoding="utf-8"),
            )

    def test_stock_backup_blocked_gh_create_keeps_capture_local(self):
        """Known blocked stock-backup captures should not create duplicate issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            capture_dir = tmp_path / "capture"
            installer = self.make_script(
                tmp_path,
                "stub_install.sh",
                """
                #!/usr/bin/env bash
                printf 'error: failed to read stock firmware backup chunk at 0x100000 after retrying down to 0x1000\\n'
                printf 'hardware validation status: blocked - installer stopped before erase/write because no complete stock backup is available.\\n'
                exit 1
                """,
            )
            gh_marker = tmp_path / "gh-called.txt"
            gh = self.make_script(
                tmp_path,
                "gh",
                f"""
                #!/usr/bin/env bash
                printf called > {gh_marker}
                exit 0
                """,
            )
            env = os.environ.copy()
            env.update(
                {
                    "AIPI_DEV_INSTALL_SCRIPT": str(installer),
                    "AIPI_DEV_GH_BIN": str(gh),
                    "HOME": str(tmp_path),
                }
            )

            result = subprocess.run(
                [
                    str(DEV_INSTALL_SCRIPT),
                    "--capture-dir",
                    str(capture_dir),
                    "--gh",
                    "owner/repo",
                    "--",
                    "--trace",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 1)
            self.assertIn("Stock-backup-blocked capture kept local", result.stdout)
            self.assertIn("Use --issue OWNER/REPO#NUMBER", result.stdout)
            self.assertFalse(gh_marker.exists())
            self.assertFalse((capture_dir / "github-created-issue.txt").exists())
            self.assertIn(
                "hardware validation status: blocked",
                (capture_dir / "github-issue-body.md").read_text(encoding="utf-8"),
            )

    def test_help_only_gh_create_keeps_capture_local(self):
        """Help-only captures should not create automatic GitHub issues."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            capture_dir = tmp_path / "capture"
            installer = self.make_script(
                tmp_path,
                "stub_install.sh",
                """
                #!/usr/bin/env bash
                printf 'Usage: ./install.sh [options]\\n'
                printf 'args:%s\\n' "$*"
                exit 0
                """,
            )
            gh_marker = tmp_path / "gh-called.txt"
            gh = self.make_script(
                tmp_path,
                "gh",
                f"""
                #!/usr/bin/env bash
                printf called > {gh_marker}
                exit 0
                """,
            )
            env = os.environ.copy()
            env.update(
                {
                    "AIPI_DEV_INSTALL_SCRIPT": str(installer),
                    "AIPI_DEV_GH_BIN": str(gh),
                    "HOME": str(tmp_path),
                }
            )

            result = subprocess.run(
                [
                    str(DEV_INSTALL_SCRIPT),
                    "--capture-dir",
                    str(capture_dir),
                    "--gh",
                    "owner/repo",
                    "--",
                    "--help",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn("Help-only capture kept local", result.stdout)
            self.assertIn("Use --issue OWNER/REPO#NUMBER", result.stdout)
            self.assertFalse(gh_marker.exists())
            self.assertFalse((capture_dir / "github-created-issue.txt").exists())
            self.assertIn(
                "Installer arguments: `--help `",
                (capture_dir / "github-issue-body.md").read_text(encoding="utf-8"),
            )

    def test_bare_gh_option_uses_repository_environment(self):
        """Bare --gh should create an issue using AIPI_GITHUB_REPO."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            capture_dir = tmp_path / "capture"
            installer = self.make_script(
                tmp_path,
                "stub_install.sh",
                """
                #!/usr/bin/env bash
                printf 'install ok\\n'
                exit 0
                """,
            )
            gh_log = tmp_path / "gh-bare-args.txt"
            gh = self.make_script(
                tmp_path,
                "gh",
                f"""
                #!/usr/bin/env bash
                printf '%s\\n' "$*" > {gh_log}
                printf 'https://github.com/owner/repo/issues/78\\n'
                exit 0
                """,
            )
            env = os.environ.copy()
            env.update(
                {
                    "AIPI_DEV_INSTALL_SCRIPT": str(installer),
                    "AIPI_DEV_GH_BIN": str(gh),
                    "AIPI_GITHUB_REPO": "owner/repo",
                }
            )

            result = subprocess.run(
                [
                    str(DEV_INSTALL_SCRIPT),
                    "--capture-dir",
                    str(capture_dir),
                    "--gh",
                    "--gh-title",
                    "Bare GitHub issue",
                    "--",
                    "--skip-self-update",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 0)
            self.assertIn(
                "Created GitHub issue: https://github.com/owner/repo/issues/78",
                result.stdout,
            )
            self.assertIn(
                "issue create --repo owner/repo --title Bare GitHub issue --body-file",
                gh_log.read_text(encoding="utf-8"),
            )

    def test_clean_tools_option_is_passed_to_installer(self):
        """The wrapper should accept cleanup directly and capture its transcript."""
        result, artifacts, _modes = self.run_dev_install(
            ["--prepare-only", "--clean-tools"],
            """
            #!/usr/bin/env bash
            printf 'args:%s\\n' "$*"
            printf 'cleanup transcript\\n'
            exit 0
            """,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("args:--clean-tools", result.stdout)
        self.assertIn("cleanup transcript", artifacts["install-transcript-redacted.txt"])
        self.assertIn("--clean-tools", artifacts["github-issue-body.md"])

    def test_trace_option_is_passed_to_installer(self):
        """The wrapper should accept tracing directly and preserve trace path output."""
        result, artifacts, _modes = self.run_dev_install(
            ["--prepare-only", "--trace"],
            """
            #!/usr/bin/env bash
            printf 'args:%s\\n' "$*"
            printf 'Installer trace file: tools/.local/debug/install-trace-test.txt\\n'
            exit 0
            """,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("args:--trace", result.stdout)
        self.assertIn("Installer trace file:", artifacts["install-transcript-redacted.txt"])
        self.assertIn("--trace", artifacts["github-issue-body.md"])

    def test_missing_gh_leaves_issue_body_without_changing_installer_status(self):
        """A missing gh binary should leave local artifacts and preserve status."""
        result, artifacts, modes = self.run_dev_install(
            ["--issue", "owner/repo#99", "--", "--restore"],
            """
            #!/usr/bin/env bash
            printf 'restore failed secret=localvalue\\n'
            exit 3
            """,
        )

        self.assertEqual(result.returncode, 3)
        self.assertIn("gh CLI not available", result.stderr)
        self.assertIn("GitHub issue body:", result.stdout)
        self.assertIn("Installer exit status: 3", result.stdout)
        self.assertIn("secret=<redacted>", artifacts["github-issue-body.md"])
        self.assertEqual(modes["install-transcript-raw.txt"], 0o600)
        self.assertEqual(modes["install-transcript-redacted.txt"], 0o600)
        self.assertEqual(modes["github-issue-body.md"], 0o600)

    def test_missing_gh_for_create_leaves_issue_body_without_changing_status(self):
        """A missing gh binary for --gh should preserve the installer status."""
        result, artifacts, _modes = self.run_dev_install(
            ["--gh", "owner/repo", "--", "--restore"],
            """
            #!/usr/bin/env bash
            printf 'create issue fallback secret=localvalue\\n'
            exit 4
            """,
        )

        self.assertEqual(result.returncode, 4)
        self.assertIn("gh CLI not available", result.stderr)
        self.assertIn("GitHub issue body:", result.stdout)
        self.assertIn("Installer exit status: 4", result.stdout)
        self.assertIn("secret=<redacted>", artifacts["github-issue-body.md"])
        self.assertNotIn("github-created-issue.txt", artifacts)

    def test_gh_and_issue_options_are_mutually_exclusive(self):
        """The wrapper should reject simultaneous create and comment targets."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            capture_dir = tmp_path / "capture"
            marker = tmp_path / "installer-ran.txt"
            installer = self.make_script(
                tmp_path,
                "stub_install.sh",
                f"""
                #!/usr/bin/env bash
                printf ran > {marker}
                exit 0
                """,
            )
            env = os.environ.copy()
            env.update({"AIPI_DEV_INSTALL_SCRIPT": str(installer)})

            result = subprocess.run(
                [
                    str(DEV_INSTALL_SCRIPT),
                    "--capture-dir",
                    str(capture_dir),
                    "--gh",
                    "owner/repo",
                    "--issue",
                    "owner/repo#42",
                ],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

            self.assertEqual(result.returncode, 2)
            self.assertIn("use either --gh", result.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse(capture_dir.exists())

    def test_capture_artifacts_remain_under_ignored_local_tooling_by_default(self):
        """Default capture output should live under the ignored tools/.local tree."""
        script_text = DEV_INSTALL_SCRIPT.read_text(encoding="utf-8")
        gitignore_text = GITIGNORE.read_text(encoding="utf-8")

        self.assertIn('CAPTURE_ROOT="${TOOLS_ROOT}/dev-install"', script_text)
        self.assertIn('TOOLS_ROOT="${SCRIPT_DIR}/tools/.local"', script_text)
        self.assertIn("--clean-tools", script_text)
        self.assertIn("--clean-prereqs", script_text)
        self.assertIn("--trace", script_text)
        self.assertIn("--gh", script_text)
        self.assertIn("AIPI_GITHUB_REPO", script_text)
        self.assertIn("issue create", script_text)
        self.assertIn("tools/.local/", gitignore_text)


if __name__ == "__main__":
    unittest.main()
