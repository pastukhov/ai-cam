"""Vision orchestration for UnitV/MaixPy tool commands."""

import config
import storage
from faces import FaceRuntime, VisionError as FaceError
from objects import ObjectRuntime, VisionError as ObjectError

try:
  import utime as _time
except ImportError:
  import time as _time


def _usb_debug(*parts):
  if not getattr(config, "USB_DEBUG_LOG", False):
    return
  try:
    print("[vision.rt]", *parts)
  except Exception:
    pass


class VisionError(Exception):
  def __init__(self, code, message):
    self.code = code
    self.message = message
    try:
      self.args = (message,)
    except Exception:
      pass


def _ticks_ms():
  if hasattr(_time, "ticks_ms"):
    return _time.ticks_ms()
  return int(_time.time() * 1000)


def _ticks_diff(a, b):
  if hasattr(_time, "ticks_diff"):
    return _time.ticks_diff(a, b)
  return a - b


def _bool_arg(value, default=False):
  if value is None:
    return default
  if isinstance(value, bool):
    return value
  if isinstance(value, int):
    return value != 0
  text = str(value).lower()
  return text in ("1", "true", "yes", "on")


class VisionRuntime:
  def __init__(self, face_runtime=None, object_runtime=None):
    self._sensor = None
    self._face = face_runtime or FaceRuntime()
    self._objects = object_runtime or ObjectRuntime()
    self._debug_enabled = False
    self._last_debug = {}
    self._camera_ready = False
    _usb_debug("init")

  def _load_sensor(self):
    if self._sensor is None:
      _usb_debug("sensor", "import")
      import sensor as sensor_mod
      self._sensor = sensor_mod

  def _ensure_camera(self):
    if self._camera_ready:
      return
    self._load_sensor()
    try:
      _usb_debug("camera", "reset")
      self._sensor.reset()
      self._sensor.set_pixformat(self._sensor.RGB565)
      self._sensor.set_framesize(self._sensor.QVGA)
      self._sensor.run(1)
      self._sensor.skip_frames(time=250)
      self._camera_ready = True
      _usb_debug("camera", "ready")
    except Exception:
      self._camera_ready = False
      _usb_debug("camera", "init_failed")
      raise VisionError("VISION_FAILED", "camera")

  def _capture(self):
    self._ensure_camera()
    try:
      return self._sensor.snapshot()
    except Exception:
      _usb_debug("camera", "snapshot_failed")
      raise VisionError("VISION_FAILED", "snapshot")

  def _check_deadline(self, deadline_ms):
    if _ticks_diff(_ticks_ms(), deadline_ms) > 0:
      raise VisionError("TIMEOUT", "timeout")

  def boot(self):
    _usb_debug("boot", "start")
    self._ensure_camera()
    self._face.load_templates()
    try:
      _usb_debug(
        "boot",
        "templates=%d" % self._face.templates_loaded(),
        "obj_model=%s" % (self._objects.model_source() or "none"),
      )
    except Exception:
      pass

  def set_debug(self, enabled):
    self._debug_enabled = bool(enabled)
    _usb_debug("debug", "enabled=%s" % self._debug_enabled)
    return {"debug": self._debug_enabled}

  def capabilities(self):
    return {
      "faces": True,
      "objects": True,
      "learn": True,
      "sd": storage.sd_available(),
    }

  def info(self):
    return {
      "tool": config.TOOL_NAME,
      "fw_version": config.FW_VERSION,
      "protocol_version": config.PROTOCOL_VERSION,
      "capabilities": self.capabilities(),
    }

  def _scan_frames_count(self, args):
    mode = "RELIABLE"
    if isinstance(args, dict):
      mode = str(args.get("mode", "RELIABLE")).upper()

    default_frames = 3
    if mode == "FAST":
      default_frames = 1

    frames = default_frames
    if isinstance(args, dict) and "frames" in args:
      try:
        frames = int(args.get("frames"))
      except Exception:
        frames = default_frames

    if frames < 1:
      frames = 1
    if frames > config.MAX_SCAN_FRAMES:
      frames = config.MAX_SCAN_FRAMES
    return frames

  def _enrich_debug(self, result):
    if self._debug_enabled:
      result["debug"] = self._last_debug
    return result

  def recover(self):
    _usb_debug("recover", "start")
    try:
      self._face.deinit()
    except Exception:
      pass
    try:
      self._objects.deinit()
    except Exception:
      pass
    self._camera_ready = False
    _usb_debug("recover", "done")

  def _aggregate_objects(self, per_frame):
    seen = {}
    for labels in per_frame:
      for name in labels:
        if name in config.SUPPORTED_OBJECTS:
          seen[name] = True

    ordered = []
    for name in config.SUPPORTED_OBJECTS:
      if name in seen:
        ordered.append(name)

    truncated = False
    if len(ordered) > config.MAX_OBJECTS:
      ordered = ordered[:config.MAX_OBJECTS]
      truncated = True
    return ordered, truncated

  def scan(self, args, deadline_ms):
    if args is None:
      args = {}
    frames = self._scan_frames_count(args)
    allow_partial = _bool_arg(args.get("allow_partial"), False)

    person_samples = []
    objects_samples = []
    begin_ms = _ticks_ms()

    for _ in range(frames):
      self._check_deadline(deadline_ms)
      frame = self._capture()

      try:
        face = self._face.recognize_frame(frame)
      except FaceError as err:
        raise VisionError(err.code, err.message)

      try:
        objs = self._objects.detect_frame(frame, allow_partial=allow_partial)
      except ObjectError as err:
        raise VisionError(err.code, err.message)

      person_samples.append(face)
      objects_samples.append(objs)

    agg = self._face.vote_people(person_samples)
    objects, truncated = self._aggregate_objects(objects_samples)

    self._last_debug = {
      "elapsed_ms": _ticks_diff(_ticks_ms(), begin_ms),
      "templates": self._face.templates_loaded(),
      "object_model": self._objects.model_source(),
    }

    result = {
      "person": agg["person"],
      "faces_detected": int(agg["faces_detected"]),
      "objects": objects,
      "frames": frames,
      "truncated": truncated,
    }
    if agg["person"] != config.PERSON_NONE:
      result["confidence"] = {"person": round(float(agg["confidence"]), 2)}
    _usb_debug("scan", "frames=%d" % frames, "person=%s" % result["person"], "objs=%d" % len(objects))
    return self._enrich_debug(result)

  def who(self, args, deadline_ms):
    if args is None:
      args = {}
    frames = self._scan_frames_count(args)
    begin_ms = _ticks_ms()
    samples = []

    for _ in range(frames):
      self._check_deadline(deadline_ms)
      frame = self._capture()
      try:
        samples.append(self._face.recognize_frame(frame))
      except FaceError as err:
        raise VisionError(err.code, err.message)

    agg = self._face.vote_people(samples)
    self._last_debug = {
      "elapsed_ms": _ticks_diff(_ticks_ms(), begin_ms),
      "templates": self._face.templates_loaded(),
    }

    result = {
      "person": agg["person"],
      "frames": frames,
    }
    if agg["person"] != config.PERSON_NONE:
      result["confidence"] = {"person": round(float(agg["confidence"]), 2)}
    _usb_debug("who", "frames=%d" % frames, "person=%s" % result["person"])
    return self._enrich_debug(result)

  def objects(self, args, deadline_ms):
    if args is None:
      args = {}
    frames = self._scan_frames_count(args)
    allow_partial = _bool_arg(args.get("allow_partial"), False)
    begin_ms = _ticks_ms()

    per_frame = []
    for _ in range(frames):
      self._check_deadline(deadline_ms)
      frame = self._capture()
      try:
        per_frame.append(self._objects.detect_frame(frame, allow_partial=allow_partial))
      except ObjectError as err:
        raise VisionError(err.code, err.message)

    labels, truncated = self._aggregate_objects(per_frame)
    self._last_debug = {
      "elapsed_ms": _ticks_diff(_ticks_ms(), begin_ms),
      "object_model": self._objects.model_source(),
    }

    result = {
      "objects": labels,
      "frames": frames,
      "truncated": truncated,
    }
    _usb_debug("objects", "frames=%d" % frames, "count=%d" % len(labels), "trunc=%s" % truncated)
    return self._enrich_debug(result)

  def learn(self, args, deadline_ms):
    if not isinstance(args, dict):
      args = {}

    person = args.get("person")
    try:
      frames = int(args.get("frames", 7))
    except Exception:
      frames = 7

    if frames < 1:
      frames = 1
    if frames > config.MAX_LEARN_FRAMES:
      frames = config.MAX_LEARN_FRAMES

    begin_ms = _ticks_ms()
    try:
      result = self._face.learn(self._capture, person, frames, deadline_ms)
    except FaceError as err:
      raise VisionError(err.code, err.message)

    self._last_debug = {
      "elapsed_ms": _ticks_diff(_ticks_ms(), begin_ms),
      "templates": self._face.templates_loaded(),
    }
    _usb_debug("learn", "person=%s" % person, "frames=%d" % frames)
    return self._enrich_debug(result)

  def reset_faces(self):
    try:
      result = self._face.reset_faces()
    except FaceError as err:
      raise VisionError(err.code, err.message)
    self._last_debug = {"templates": 0}
    _usb_debug("reset_faces", "ok")
    return self._enrich_debug(result)
