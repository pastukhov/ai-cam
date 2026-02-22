# Memory / Current Status

## Current Device State (2026-02-22)
- Device firmware: `M5StickV_Firmware_v5.1.2.kfpkg` (official UnitV MaixPy path from M5 docs).
- `microSD` mounts correctly (`/` contains `flash` and `sd`).
- `/flash/boot.py` was replaced with a minimal bootstrap that starts `/sd/main.py` to avoid old demo `pmu` dependency.
- App now autostarts on boot (camera init visible in UART log: `init i2c2`, `find ov7740`).

## What Is Implemented (todo.md progress)
- Sections `2`, `3`, `4`, `5`, `7`, `8`: implemented in Python modules:
  - `main.py`, `protocol.py`, `vision.py`, `faces.py`, `objects.py`, `storage.py`, `config.py`
- JSONL UART protocol implemented:
  - one request line -> one JSON response line
  - `BAD_REQUEST`, `BUSY`, `TIMEOUT`, `VISION_FAILED`, `STORAGE_UNAVAILABLE`, `MODEL_MISSING`
  - `req_id` echo and dedup cache (`DEDUP_TTL_MS=2000`)
- Commands implemented:
  - `PING`, `INFO`, `SCAN`, `WHO`, `OBJECTS`, `LEARN`, `RESET_FACES`, `DEBUG`
- SD persistence implemented:
  - `/sd/faces/owner_1.jpg`, `/sd/faces/owner_2.jpg`, `/sd/config.json`
- Object model support implemented:
  - `/sd/models/objects.kmodel`
  - `/sd/models/classes.txt`
  - optional `/sd/models/label_map.json`
- Loader tooling implemented:
  - `tools/k210_loader.py` (flash/upload via `kflash` + raw REPL)

## Test Status
- Host-side unit tests: full Python runtime covered, `45 tests OK`.
- Syntax checks pass (`py_compile`).
- On-device boot verified after official firmware flash.
- Acceptance test harness: `tools/acceptance_test.py` (todo.md section 9).
  - Protocol group (automatic): PING, INFO, DEDUP, MALFORMED, UNKNOWN_CMD.
  - Vision group (interactive): LEARN, WHO, SCAN, OBJECTS, PERSISTENCE (reboot), RESET_FACES.
  - Run: `python3 tools/acceptance_test.py --port /dev/ttyUSB0 --group protocol|vision|all`

## UART Configuration
- Grove connector on UnitV: pin 34 = TX, pin 35 = RX.
- FPIOA registration required: `fm.register(34, fm.fpioa.UART1_TX)` etc.
- `UART_ID = 1` (UART1), matching official M5Stack examples.
- USB-C is always MicroPython REPL (independent of Grove UART).
- Reference: `M5-ProductExampleCodes/App/UnitV/track_ball/track_ball.py`.

## What Still Needs To Be Done
- Run acceptance tests on device and fix any issues found.
- Optional cleanup:
  - add CI for unit tests

## Notes
- Sample object model currently maps:
  - `apple -> cup`
  - `banana -> person`
  - `orange -> table`
- Final deployment should replace sample `.kmodel` and mapping with task-specific model/classes.
