# Repository Instructions

- Always commit completed changes automatically in this repository.
- Always push completed commits automatically in this repository.
- Always merge completed, validated feature-branch work into `main` and push
  `main` automatically so other machines can pull the finished changes.
- Do not commit generated downloads, local virtual environments, firmware dumps,
  credentials, device tokens, or other local-only artifacts.
- Continue to include tests for generated Python code and documentation updates
  where appropriate.

## Project-Specific Workflow

- Treat `FIRMWARE_IMPL.md` as the implementation roadmap, `FIRMWARE_PLAN.md` as
  the firmware architecture, `SPEC.md` as the hardware/pinout source of truth,
  and `RECOVERY.md` as the backup/restore procedure.
- Treat `src/` as the MicroPython application tree copied to the device root.
  Keep device imports root-relative, such as `from lib...` and `import pins`,
  rather than turning `src` into a Python package.
- Use `install.sh` for install and restore flows. Installer answers belong in
  ignored `.conf`; do not hard-code local ports, backup paths, Wi-Fi settings,
  secrets, or operator answers in tracked files.
- Keep generated host tooling, downloads, firmware images, stock backups,
  virtual environments, `.conf`, `.conf.tmp.*`, `__pycache__`, and `*.pyc`
  out of Git. These belong under ignored local paths such as `tools/.local/`.
- Preserve the local-only firmware policy by default. Do not add cloud
  endpoints, telemetry, OTA behavior, credentials, or public-network service
  calls unless the user explicitly asks and documentation is updated.
- Avoid driving unverified hardware controls, especially GPIO10 board power,
  until `SPEC.md` and hardware testing confirm safe behavior.
- When changing firmware source, installer behavior, or tooling, run the
  relevant checks before committing: `python3 -m unittest discover -s tests -v`,
  `bash -n install.sh`, `bash -n tools/setup_micropython_tools.sh`, and
  `git diff --check`.
- Update related docs with behavior changes: `README.md` for user workflow,
  `RECOVERY.md` for backup/restore, `FIRMWARE_PLAN.md` and
  `FIRMWARE_IMPL.md` for roadmap/status, and `SPEC.md` for hardware facts.
