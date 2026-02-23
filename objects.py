"""Object detection runtime for UnitV/MaixPy."""

import config
import storage

try:
  import ujson as _json
except ImportError:
  import json as _json

try:
  import uos as _os
except ImportError:
  import os as _os


class VisionError(Exception):
  def __init__(self, code, message):
    self.code = code
    self.message = message
    try:
      self.args = (message,)
    except Exception:
      pass


class ObjectRuntime:
  def __init__(self, kpu_mod=None):
    self._kpu = kpu_mod
    self._task = None
    self._loaded = False
    self._source = None
    self._class_names = list(config.SUPPORTED_OBJECTS)
    self._label_map = {}
    self._input_w = None
    self._input_h = None

  def _load_module(self):
    if self._kpu is None:
      import KPU as kpu_mod
      self._kpu = kpu_mod

  def deinit(self):
    if self._kpu is not None and self._task is not None:
      try:
        self._kpu.deinit(self._task)
      except Exception:
        pass
    self._task = None
    self._loaded = False
    self._source = None

  def _resolve_model(self):
    if storage.sd_available() and storage.ensure_sd_layout():
      try:
        _os.stat(config.OBJECT_MODEL_SD_PATH)
        return config.OBJECT_MODEL_SD_PATH, "sd"
      except Exception:
        pass
    if config.OBJECT_MODEL_FLASH_ADDR is not None:
      return config.OBJECT_MODEL_FLASH_ADDR, "flash"
    return None, None

  def _load_class_names(self):
    default = list(config.SUPPORTED_OBJECTS)
    if not storage.sd_available():
      return default
    try:
      _os.stat(config.OBJECT_CLASSES_SD_PATH)
    except Exception:
      return default

    try:
      with open(config.OBJECT_CLASSES_SD_PATH, "r") as f:
        raw = f.read().strip()
    except Exception:
      return default

    if not raw:
      return default
    # Support either csv ("a,b,c") or one-label-per-line.
    if "," in raw:
      items = [x.strip() for x in raw.split(",")]
    else:
      items = [x.strip() for x in raw.splitlines()]
    items = [x for x in items if x]
    if not items:
      return default
    return items

  def _load_label_map(self):
    if not storage.sd_available():
      return {}
    try:
      _os.stat(config.OBJECT_LABEL_MAP_SD_PATH)
    except Exception:
      return {}
    try:
      with open(config.OBJECT_LABEL_MAP_SD_PATH, "r") as f:
        data = _json.loads(f.read())
      if not isinstance(data, dict):
        return {}
      clean = {}
      for key in data:
        k = str(key).strip().lower()
        v = str(data[key]).strip().lower()
        if not k or not v:
          continue
        clean[k] = v
      return clean
    except Exception:
      return {}

  def ensure_loaded(self):
    if self._loaded:
      return

    self._load_module()
    model_ref, source = self._resolve_model()
    if model_ref is None:
      raise VisionError("MODEL_MISSING", "objects_model")

    try:
      self._task = self._kpu.load(model_ref)
      # Conservative defaults compatible with YOLO2 KPU models.
      self._kpu.init_yolo2(self._task, 0.5, 0.3, 5, config.OBJECT_YOLO_ANCHORS)
      self._class_names = self._load_class_names()
      self._label_map = self._load_label_map()
      self._loaded = True
      self._source = source
    except Exception:
      self.deinit()
      raise VisionError("MODEL_MISSING", "objects_model")

  def model_source(self):
    return self._source

  def _parse_model_dims_from_error(self, err_text):
    # Example from MaixPy:
    # "[MAIXPY]kpu: img w=320,h=240, but model w=224,h=224"
    if not err_text:
      return None
    marker = "model w="
    p = err_text.find(marker)
    if p < 0:
      return None
    p += len(marker)
    q = err_text.find(",", p)
    if q < 0:
      return None
    r = err_text.find("h=", q)
    if r < 0:
      return None
    r += 2
    # read digits for width / height
    w_txt = ""
    for ch in err_text[p:q]:
      if "0" <= ch <= "9":
        w_txt += ch
    h_txt = ""
    for ch in err_text[r:]:
      if "0" <= ch <= "9":
        h_txt += ch
      elif h_txt:
        break
    if not w_txt or not h_txt:
      return None
    try:
      w = int(w_txt)
      h = int(h_txt)
    except Exception:
      return None
    if w <= 0 or h <= 0:
      return None
    return (w, h)

  def _usb_debug(self, message):
    try:
      if not getattr(config, "USB_DEBUG_LOG", False):
        return
      print("[vision.obj] %s" % message)
    except Exception:
      pass

  def _prepare_frame_for_kpu(self, frame):
    try:
      frame.pix_to_ai()
    except Exception:
      pass
    return frame

  def _run_yolo2_with_resize_fallback(self, frame):
    try:
      return self._kpu.run_yolo2(self._task, self._prepare_frame_for_kpu(frame))
    except Exception as ex:
      # Some MaixPy builds print mismatch details to stdout but raise an empty exception.
      # Retry parsed dims first, then a common YOLO2 sample-model size.
      err_text = str(ex)
      dims = self._parse_model_dims_from_error(err_text)
      candidates = []
      if dims is not None:
        candidates.append(dims)
      if (224, 224) not in candidates:
        candidates.append((224, 224))

      last_ex = ex
      for (w, h) in candidates:
        try:
          self._usb_debug("run_yolo2 retry %dx%d" % (w, h))
          resized = frame.resize(w, h)
          self._input_w, self._input_h = (w, h)
          return self._kpu.run_yolo2(self._task, self._prepare_frame_for_kpu(resized))
        except Exception as retry_ex:
          last_ex = retry_ex
      raise last_ex

  def _label_from_det(self, det):
    class_id = None
    try:
      class_id = int(det.classid())
    except Exception:
      class_id = None

    if class_id is None:
      return None
    if class_id < 0 or class_id >= len(self._class_names):
      return None

    label = str(self._class_names[class_id]).strip().lower()
    if not label:
      return None

    mapped = self._label_map.get(label, label)
    if mapped not in config.SUPPORTED_OBJECTS:
      return None
    return mapped

  def detect_frame(self, frame, allow_partial=False):
    try:
      self.ensure_loaded()
    except VisionError as err:
      if allow_partial and err.code == "MODEL_MISSING":
        return []
      raise

    try:
      detections = self._run_yolo2_with_resize_fallback(frame)
    except Exception:
      raise VisionError("VISION_FAILED", "objects_detect")

    if not detections:
      return []

    seen = {}
    for det in detections:
      label = self._label_from_det(det)
      if not label:
        continue
      seen[label] = True

    # Deterministic output order.
    ordered = []
    for name in config.SUPPORTED_OBJECTS:
      if name in seen:
        ordered.append(name)

    if len(ordered) > config.MAX_OBJECTS:
      ordered = ordered[:config.MAX_OBJECTS]
    return ordered
