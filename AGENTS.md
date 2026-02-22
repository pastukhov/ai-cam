# Repository Guidelines

## Project Structure & Module Organization
This repository is a device-flashing workspace, not a typical application codebase.

- Top-level firmware artifacts: `*.bin`, `*.kfpkg`, `*.run`, `*.AppImage`.
- `kflash_gui/`: bundled upstream flashing tool files and runtime libraries.
- `references/MaixPy/`: vendor/reference source tree for documentation and examples.
- `owner.py`: local utility script.
- `todo.md`: working notes.

Treat `kflash_gui/` and `references/` as third-party or reference content unless a task explicitly requires changes there.

## Build, Test, and Development Commands
There is no formal build pipeline in this repo. Use lightweight verification commands:

- `ls -la` — inspect top-level files and artifacts.
- `rg --files` — list tracked files quickly.
- `rg "<pattern>" -n` — search code or docs.
- `python3 owner.py` — run the local utility script (if relevant to your change).
- `python3 -m py_compile owner.py` — syntax-check Python edits.

## Flashing Firmware
Use a local virtual environment for flashing tools to avoid polluting the system Python.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install kflash
```

Flash the official UnitV MaixPy firmware (per M5 docs):

```bash
kflash M5StickV_Firmware_v5.1.2.kfpkg
```

If `kflash` is already installed in an active environment, skip the setup and run the flashing command directly.

## Coding Style & Naming Conventions
- Python: follow PEP 8 defaults, 4-space indentation, UTF-8, LF endings.
- Shell snippets in docs should be copy-paste safe and minimal.
- New helper scripts should use lowercase names with hyphens (example: `flash-check.sh`).
- Keep changes narrow; avoid reformatting unrelated files.

## Testing Guidelines
No automated test suite is currently configured. For code changes:

- Run a syntax check (`python3 -m py_compile <file>`).
- Execute the changed script with a realistic local input.
- For command docs, validate each command once before committing.

If you add reusable tooling, place tests under `tools/tests/` as `*_smoke.sh`.

## Commit & Pull Request Guidelines
- Use concise imperative commits (example: `docs: add flashing workflow notes`).
- Group related changes; avoid mixing docs, binaries, and refactor work in one commit.
- PRs should include:
  - Purpose and scope
  - Files changed
  - Manual verification steps and outcomes
  - Risks (especially around firmware artifacts or flashing instructions)

## Security & Configuration Tips
- Do not commit secrets, device IDs, or private tokens.
- Avoid editing or rehosting large vendor binaries unless explicitly required.
- Verify checksums/source authenticity for newly added firmware artifacts.
