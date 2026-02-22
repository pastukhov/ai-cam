# Tools

## `k210_loader.py`

Loader for K210/UnitV that can:

- flash firmware and face model with `kflash.py`
- upload files via `maixctl` (default in `auto` mode when installed)
- upload runtime files (`main.py`, `vision.py`, `faces.py`, `objects.py`, `storage.py`, `protocol.py`, `config.py`)
- upload object-model artifacts to `/sd/models/`

### Examples

Flash firmware + face model, then upload code and sample object model:

```bash
python3 tools/k210_loader.py \
  --port /dev/ttyUSB0 \
  --firmware maixpy_v0.6.3_2_gd8901fd22_m5stickv.bin \
  --flash-face \
  --use-sample-model
```

Upload only code (no flashing):

```bash
python3 tools/k210_loader.py --port /dev/ttyUSB0 --no-models
```

Force `maixctl` backend (recommended / policy path):

```bash
python3 tools/k210_loader.py --port /dev/ttyUSB0 --deploy-backend maixctl --no-models
```

Force legacy raw REPL backend (debug only; not default policy):

```bash
python3 tools/k210_loader.py --port /dev/ttyUSB0 --deploy-backend raw --no-models
```

Upload custom model files:

```bash
python3 tools/k210_loader.py \
  --port /dev/ttyUSB0 \
  --object-model /path/to/objects.kmodel \
  --object-classes /path/to/classes.txt \
  --object-label-map /path/to/label_map.json
```

### Notes

- Upload backend:
  - `--deploy-backend auto` (default): prefer `maixctl`, fallback to raw REPL if `maixctl` is not installed
  - `--deploy-backend maixctl`: use MaixPy IDE protocol (`maixctl`) for file upload
  - `--deploy-backend raw`: use legacy raw REPL uploader (diagnostic fallback only)
- `maixctl` uses:
  - `--ide-baud` (default `1500000`) for IDE protocol
  - `--uart-baud` (default `115200`) as normal REPL baud before `--enter-ide`
- Raw backend uses MicroPython raw REPL over serial (`--uart-baud`, default `115200`).
- Flashing uses `kflash_gui/kflash_py/kflash.py` (`--flash-baud`, default `1500000`).
- `--flash-face` without value uses `face_model_at_0x300000.kfpkg` from repository root.
