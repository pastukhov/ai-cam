# K210 Vision UART Helpers

This workspace contains MicroPython-friendly helper modules for the K210
vision tool protocol:

- `config.py` - protocol limits, thresholds, model paths/addresses, anchors.
- `protocol.py` - UART JSONL read/write, short errors, safe JSON encode cap.
- `storage.py` - SD card helpers for faces and config persistence.

## Model Placement

### Face detector model

Flash the face model to K210 address `0x300000`:

```bash
kflash -p /dev/ttyUSB0 -b 1500000 -a 0x300000 face_model_at_0x300000.kfpkg
```

`config.py` expects:

- `FACE_MODEL_ADDR = 0x300000`

### Object model

Put object YOLOv2 model on SD card:

- `/sd/models/objects.kmodel`
- optional class names file: `/sd/models/classes.txt`
- optional remap file: `/sd/models/label_map.json`

If you use a flash fallback address instead, set:

- `OBJECT_MODEL_FLASH_ADDR = <address>`

`classes.txt` format:

- comma-separated: `door,window,sofa,...`
- or one label per line.

`label_map.json` format (optional, maps model labels to supported tool labels):

```json
{
  "apple": "cup",
  "banana": "person",
  "orange": "table"
}
```

Smoke-test with your найденная модель:

1. Copy `/home/artem/tmp/MaixPy-v1_scripts/machine_vision/fans_share/yolov2_apple,banana,orange/yolov2.kmodel` to `/sd/models/objects.kmodel`.
2. Copy `/home/artem/tmp/MaixPy-v1_scripts/machine_vision/fans_share/yolov2_apple,banana,orange/classes.txt` to `/sd/models/classes.txt`.
3. Create `/sd/models/label_map.json` if you want these classes to appear as supported output labels.

## SD Card Layout

Helpers in `storage.py` use:

- `/sd/faces/owner_1.jpg`
- `/sd/faces/owner_2.jpg`
- `/sd/config.json`

## UART JSONL Examples

Полное описание протокола (ESP <-> UnitV по Grove UART, JSONL):

- `docs/protocols/esp-unitv-grove-uart-jsonl.md`

Each request is one JSON line ending with `\n`.
Each response is exactly one JSON line ending with `\n`.

### PING

Request:

```json
{"cmd":"PING","req_id":"1"}
```

Response:

```json
{"req_id":"1","ok":true,"result":{"status":"ok","tool":"vision_k210"}}
```

### SCAN

Request:

```json
{"cmd":"SCAN","req_id":"42","args":{"mode":"RELIABLE","frames":3}}
```

Response:

```json
{"req_id":"42","ok":true,"result":{"person":"OWNER_1","faces_detected":1,"objects":["sofa","table"],"confidence":{"person":0.91},"frames":3,"truncated":false}}
```

### Error (short format)

```json
{"req_id":"42","ok":false,"error":{"code":"BAD_REQUEST","message":"bad_json"}}
```

`protocol.safe_json_encode(...)` guarantees encoded JSON payload is capped at
`768` bytes (`config.MAX_JSON_BYTES`).
