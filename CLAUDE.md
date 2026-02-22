# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MicroPython firmware for Kendryte K210 (Unit V-M12, M5Stack) providing a deterministic UART JSONL vision protocol for an ESP32 rover with LLM agent. Capabilities: face recognition (2 owners), object detection (7 classes), SD-persistent learned identities.

Hardware: K210 dual-core RISC-V @ 400 MHz, 8 MB SRAM, OV7740 camera, microSD, UART via Grove connector.

## Build & Development Commands

No formal build pipeline. All commands run from repo root.

```bash
# Syntax check any module
python3 -m py_compile config.py

# Run all tests (45 tests across 7 files)
python3 -m unittest discover tests

# Run single test module
python3 -m unittest tests.test_protocol

# Run single test with verbose output
python3 -m unittest tests.test_protocol -v

# Setup venv for flashing tools
python3 -m venv .venv && source .venv/bin/activate && pip install kflash pyserial

# Flash face model to K210
kflash -p /dev/ttyUSB0 -b 1500000 -a 0x300000 face_model_at_0x300000.kfpkg

# Upload code and models to device via raw REPL
python3 tools/k210_loader.py --port /dev/ttyUSB0 --firmware <.bin> --flash-face --use-sample-model
```

## Architecture

All modules are dual-compatible: CPython (host testing) and MicroPython (device). Imports use `try/except` fallbacks (e.g. `ujson` → `json`, `utime` → `time`).

```
main.py          UART event loop, request validation, dedup cache (2s TTL), command dispatch
├── protocol.py  JSON encode/decode (768-byte cap), UART read/write, error formatting
├── vision.py    Orchestration: camera init, frame capture, command handlers
│   ├── faces.py Face detection (KPU YOLO2), 64×64 template matching, confidence mapping, enrollment
│   ├── objects.py Object detection (KPU YOLO2), class filtering, label mapping
│   └── storage.py SD card mount, face template I/O, directory creation
└── config.py    All constants (no logic): UART params, thresholds, model addresses, SD paths, error codes
```

**Request flow:** UART line → JSON parse → validate → dedup check → timeout guard → command dispatch → vision pipeline → JSON response (capped 768 bytes) → UART write.

**Commands:** PING, INFO, SCAN (face+objects), WHO (face only), OBJECTS (objects only), LEARN (enroll), RESET_FACES, DEBUG.

## Key Conventions

- `config.py` is the single source of truth for all constants and thresholds
- All exceptions are caught at the top-level loop in `main.py`; the device never crashes to REPL—always returns a JSON error response
- Single-threaded: concurrent requests get `BUSY` error
- Face recognition uses template difference scoring (l_mean on 64×64 grayscale), not embeddings
- Responses are deterministic: same input → same output (given same scene)
- `kflash_gui/` and `references/` are third-party/vendor content—do not modify

## Testing

Tests use `unittest` with mocks (FakeSensor, FakeUART, etc.)—no device needed. Test files mirror source modules: `test_faces.py` tests `faces.py`, etc. When modifying a module, run its corresponding test file.

## SD Card Layout (on device)

```
/sd/
├── main.py, config.py, protocol.py, storage.py, faces.py, objects.py, vision.py
├── faces/owner_1.jpg, owner_2.jpg    # enrolled face templates
├── models/objects.kmodel              # YOLOv2 object model
├── models/classes.txt                 # optional class names
├── models/label_map.json             # optional model→canonical label remap
└── config.json                        # reserved
```

## Style

PEP 8, 4-space indentation, UTF-8, LF endings. Private functions: `_leading_underscore`. Constants: `UPPER_CASE`. Python file names use underscores, shell scripts use hyphens.
