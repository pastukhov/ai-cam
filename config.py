"""Shared constants for K210 UART vision firmware."""

TOOL_NAME = "vision_k210"
FW_VERSION = "1.0.0"
PROTOCOL_VERSION = "1"

# UART transport (Grove connector on UnitV: pins 34=TX, 35=RX)
# MaixPy UART IDs are zero-based here (UART1=0, UART2=1, UART3=2).
UART_ID = 0
UART_TX_PIN = 34
UART_RX_PIN = 35
UART_BAUD = 115200
UART_READ_TIMEOUT_MS = 120
UART_LINE_TIMEOUT_MS = 300
UART_MAX_LINE_BYTES = 1024

# USB REPL / stdout debug logging (does not affect Grove JSONL UART).
USB_DEBUG_LOG = True

# Protocol and runtime limits
MAX_JSON_BYTES = 768
MAX_OBJECTS = 16
MAX_SCAN_FRAMES = 5
MAX_LEARN_FRAMES = 15
# K210 object/scan inference can exceed 3s on some frames after cold/recover paths.
COMMAND_TIMEOUT_MS = 5000
DEDUP_TTL_MS = 2000

# Canonical labels
PERSON_OWNER_1 = "OWNER_1"
PERSON_OWNER_2 = "OWNER_2"
PERSON_UNKNOWN = "UNKNOWN"
PERSON_NONE = "NONE"
KNOWN_PERSONS = (PERSON_OWNER_1, PERSON_OWNER_2)

# Vision thresholds
FACE_SCORE_THRESH_STRONG = 12
FACE_SCORE_THRESH = 18

# KPU model locations
FACE_MODEL_ADDR = 0x300000
OBJECT_MODEL_SD_PATH = "/sd/models/objects.kmodel"
OBJECT_MODEL_FLASH_ADDR = None
OBJECT_CLASSES_SD_PATH = "/sd/models/classes.txt"
OBJECT_LABEL_MAP_SD_PATH = "/sd/models/label_map.json"

# YOLOv2 anchors (face detector defaults for K210 face model at 0x300000)
FACE_YOLO_ANCHORS = (
  1.889,
  2.5245,
  2.9465,
  3.94056,
  3.99987,
  5.3658,
  5.155437,
  6.92275,
  6.718375,
  9.01025,
)

# Object detector anchors can differ from face model anchors.
# Keep a dedicated constant to allow per-model tuning.
OBJECT_YOLO_ANCHORS = FACE_YOLO_ANCHORS

# Supported object labels that can be returned to the rover side.
SUPPORTED_OBJECTS = (
  "door",
  "window",
  "sofa",
  "chair",
  "table",
  "cup",
  "person",
)

# SD storage layout
# Keep template directory name different from module file names (e.g. faces.py),
# otherwise some MicroPython builds may import the directory instead of the module.
SD_ROOT = "/sd"
SD_FACES_DIR = "/sd/faces_data"
SD_MODELS_DIR = "/sd/models"
SD_CONFIG_PATH = "/sd/config.json"
OWNER_1_FACE_PATH = "/sd/faces_data/owner_1.jpg"
OWNER_2_FACE_PATH = "/sd/faces_data/owner_2.jpg"

# WS2812 status LED (UnitV onboard, 1 LED on pin 8)
LED_PIN = 8

ERROR_MESSAGES = {
  "BAD_REQUEST": "bad_req",
  "BUSY": "busy",
  "TIMEOUT": "timeout",
  "VISION_FAILED": "vision",
  "STORAGE_UNAVAILABLE": "storage",
  "MODEL_MISSING": "model",
}
