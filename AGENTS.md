# Repository Guidelines

## Project Structure & Module Organization
This repository contains K210/UnitV MicroPython vision helpers plus deployment tooling.

- Top-level runtime modules: `main.py`, `vision.py`, `faces.py`, `objects.py`, `protocol.py`, `storage.py`, `config.py`, `led.py`.
- Docs and design notes: `README.md`, `memory.md`, `docs/` (protocols, plans, deployment notes).
- Deployment tooling: `tools/k210_loader.py` and `tools/README.md`.
- ESP32/ATOM test fixture: `atoms3-e2e-tester/` (PlatformIO project).
- Agent metadata: `AGENTS.md`, `CLAUDE.md`, `.claude/`.

Treat `atoms3-e2e-tester/` and any bundled/vendor assets as separate concerns unless the task explicitly targets them.

## Build, Test, and Development Commands
There is no centralized build/test pipeline. Use targeted checks:

- `ls -la` — inspect repo contents.
- `rg --files` — fast file listing.
- `rg "<pattern>" -n` — search code/docs.
- `python3 -m py_compile main.py vision.py faces.py objects.py protocol.py storage.py config.py led.py` — syntax check runtime modules.
- `python3 -m py_compile tools/k210_loader.py` — syntax check loader utility.
- `python3 tools/k210_loader.py --help` — validate CLI interface after changes.
- `pio run -d atoms3-e2e-tester` — build ESP32 test firmware when touching `atoms3-e2e-tester/`.

## Device Flashing / Deployment
Use a virtual environment for local tooling when possible.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install kflash
```

Typical deploy flow is documented in `tools/README.md` and uses:

```bash
python3 tools/k210_loader.py --port /dev/ttyUSB0 --no-models
```

When changing deployment behavior, keep `tools/README.md` examples in sync.

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indentation, UTF-8, LF endings.
- Keep MicroPython compatibility in mind (avoid unnecessary CPython-only features in runtime modules).
- JSON examples in docs should be valid and minimal.
- New scripts/utilities: lowercase names with hyphens when shell scripts, `snake_case.py` for Python.
- Keep diffs focused; do not reformat unrelated files.

## Testing Guidelines
No automated suite is configured. For code changes:

- Run `python3 -m py_compile` on every edited Python file.
- Run the touched script/tool with `--help` or a realistic dry-run input when available.
- For protocol/doc changes, verify example JSON/commands against current code paths.
- For `atoms3-e2e-tester/` changes, build with PlatformIO and note the board/environment used.

If you add reusable tooling/tests, prefer `tools/tests/*_smoke.sh` and keep them fast.

## Commit & Pull Request Guidelines
- Use concise imperative commits, optionally scoped (examples: `docs: update UART protocol examples`, `tools: fix maixctl upload fallback`).
- Group related changes only; do not mix protocol logic, docs, and firmware artifacts unnecessarily.
- PRs should include:
  - Purpose/scope
  - Files changed
  - Manual verification steps and outcomes
  - Risks (especially deployment, flashing, and serial protocol compatibility)

## Security & Configuration Tips
- Do not commit secrets, private tokens, or local device identifiers/ports.
- Avoid committing large binaries/firmware artifacts unless required and sourced.
- Double-check serial port paths and flashing targets before running destructive device operations.
- Preserve backward compatibility for UART JSONL protocol fields unless coordinated with the ESP-side consumer.

## Local Network Notes (Observed 2026-02-22)
- AI Rover is discoverable via mDNS/DNS-SD as `ai-rover.local` (`_http._tcp`, port `80`).
- Observed IPv4 address during verification: `192.168.11.114` (DHCP; may change).
- DNS-SD TXT records matched `docs/protocols/esp-mdns-discovery.md` (`api_cmd`, `api_status`, `api_vision`, `api_chat`, `api_chat_result`).
- `GET /status` responded with rover state and battery data; one observed response included `"vision":"offline"` even while the camera endpoint was reachable.
- `GET /vision?cmd=PING` and `GET /vision?cmd=INFO` both returned `ok:true`.
- `GET /vision?cmd=WHO` returned `ok:true` with `person:"NONE"` during test.
- `GET /vision?cmd=OBJECTS` returned `ok:true` and detected sample objects (`table`, `cup`, `person`) during test.
- `GET /vision?cmd=SCAN&mode=RELIABLE` showed one transient `VISION_FAILED` (`objects_detect`) and then succeeded on retry.
- Practical note: if `/status` reports `"vision":"offline"`, verify with direct `/vision?cmd=PING` before assuming UnitV is actually down.
