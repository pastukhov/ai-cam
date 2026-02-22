"""SD card persistence helpers for face templates and config."""

import config

try:
  import ujson as _json
except ImportError:
  import json as _json

try:
  import uos as _os
except ImportError:
  import os as _os


def _path_exists(path):
  try:
    _os.stat(path)
    return True
  except Exception:
    return False


def _ensure_dir(path):
  if _path_exists(path):
    return True

  parts = path.split("/")
  current = ""
  for part in parts:
    if not part:
      continue
    current = current + "/" + part
    if not _path_exists(current):
      try:
        _os.mkdir(current)
      except Exception:
        return False
  return True


def sd_available():
  return _path_exists(config.SD_ROOT)


def ensure_sd_layout():
  if not sd_available():
    return False
  if not _ensure_dir(config.SD_FACES_DIR):
    return False
  if not _ensure_dir(config.SD_MODELS_DIR):
    return False
  return True


def face_path(person):
  if person == config.PERSON_OWNER_1:
    return config.OWNER_1_FACE_PATH
  if person == config.PERSON_OWNER_2:
    return config.OWNER_2_FACE_PATH
  return None


def load_face_bytes(person):
  path = face_path(person)
  if not path or not _path_exists(path):
    return None
  try:
    with open(path, "rb") as f:
      return f.read()
  except Exception:
    return None


def save_face_jpeg(person, jpeg_bytes):
  if not ensure_sd_layout():
    return False
  path = face_path(person)
  if not path or jpeg_bytes is None:
    return False
  try:
    with open(path, "wb") as f:
      f.write(jpeg_bytes)
    return True
  except Exception:
    return False


def delete_face(person):
  path = face_path(person)
  if not path or not _path_exists(path):
    return False
  try:
    _os.remove(path)
    return True
  except Exception:
    return False


def reset_faces():
  removed = 0
  if delete_face(config.PERSON_OWNER_1):
    removed += 1
  if delete_face(config.PERSON_OWNER_2):
    removed += 1
  return removed


def load_face_files():
  faces = {}
  b1 = load_face_bytes(config.PERSON_OWNER_1)
  b2 = load_face_bytes(config.PERSON_OWNER_2)
  if b1 is not None:
    faces[config.PERSON_OWNER_1] = b1
  if b2 is not None:
    faces[config.PERSON_OWNER_2] = b2
  return faces


def read_config(default_value=None):
  if default_value is None:
    default_value = {}
  if not _path_exists(config.SD_CONFIG_PATH):
    return default_value
  try:
    with open(config.SD_CONFIG_PATH, "r") as f:
      data = _json.loads(f.read())
    if isinstance(data, dict):
      return data
  except Exception:
    pass
  return default_value


def write_config(data):
  if not ensure_sd_layout():
    return False
  if not isinstance(data, dict):
    return False
  try:
    payload = _json.dumps(data, separators=(",", ":"))
  except TypeError:
    payload = _json.dumps(data)
  try:
    with open(config.SD_CONFIG_PATH, "w") as f:
      f.write(payload)
    return True
  except Exception:
    return False

