"""Face detection and template-based recognition for UnitV/MaixPy."""

import config
import storage

try:
  import utime as _time
except ImportError:
  import time as _time


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


def _ticks_diff(now, old):
  if hasattr(_time, "ticks_diff"):
    return _time.ticks_diff(now, old)
  return now - old


def _clamp(v, lo, hi):
  if v < lo:
    return lo
  if v > hi:
    return hi
  return v


def _safe_stat_l_mean(stat):
  if stat is None:
    return 255
  if hasattr(stat, "l_mean"):
    try:
      return int(stat.l_mean())
    except Exception:
      pass
  try:
    return int(stat[0])
  except Exception:
    return 255


def _safe_stat_l_stdev(stat):
  if stat is None:
    return 0
  if hasattr(stat, "l_stdev"):
    try:
      return int(stat.l_stdev())
    except Exception:
      pass
  try:
    return int(stat[1])
  except Exception:
    return 0


def _person_from_votes(votes, best_conf):
  if not votes:
    return config.PERSON_NONE, 0.0

  counts = {}
  for person in votes:
    counts[person] = counts.get(person, 0) + 1

  winners = []
  max_count = 0
  for person in counts:
    c = counts[person]
    if c > max_count:
      winners = [person]
      max_count = c
    elif c == max_count:
      winners.append(person)

  if len(winners) == 1:
    person = winners[0]
    return person, best_conf.get(person, 0.0)

  tie_person = winners[0]
  tie_conf = best_conf.get(tie_person, 0.0)
  for person in winners[1:]:
    conf = best_conf.get(person, 0.0)
    if conf > tie_conf:
      tie_person = person
      tie_conf = conf
  return tie_person, tie_conf


class FaceRuntime:
  def __init__(self, image_mod=None, kpu_mod=None):
    self._image = image_mod
    self._kpu = kpu_mod
    self._task_fd = None
    self._known_templates = {}
    self._loaded = False
    self._last_error = None

  def _load_modules(self):
    if self._image is None:
      import image as image_mod
      self._image = image_mod
    if self._kpu is None:
      import KPU as kpu_mod
      self._kpu = kpu_mod

  def _ensure_detector(self):
    if self._loaded:
      return
    self._load_modules()
    try:
      self._task_fd = self._kpu.load(config.FACE_MODEL_ADDR)
      self._kpu.init_yolo2(self._task_fd, 0.5, 0.3, 5, config.FACE_YOLO_ANCHORS)
      self._loaded = True
    except Exception:
      self.deinit()
      raise VisionError("VISION_FAILED", "face_model")

  def deinit(self):
    if self._kpu is not None and self._task_fd is not None:
      try:
        self._kpu.deinit(self._task_fd)
      except Exception:
        pass
    self._task_fd = None
    self._loaded = False

  def templates_loaded(self):
    return len(self._known_templates)

  def clear_templates(self):
    self._known_templates = {}

  def load_templates(self):
    self._load_modules()
    loaded = {}
    for person in config.KNOWN_PERSONS:
      if storage.load_face_bytes(person) is None:
        continue
      path = storage.face_path(person)
      if not path:
        continue
      try:
        loaded[person] = self._image.Image(path)
      except Exception:
        continue
    self._known_templates = loaded
    return len(loaded)

  def _extract_roi(self, frame, bbox):
    x = int(getattr(bbox, "x", lambda: 0)())
    y = int(getattr(bbox, "y", lambda: 0)())
    w = int(getattr(bbox, "w", lambda: 0)())
    h = int(getattr(bbox, "h", lambda: 0)())

    fw = int(frame.width())
    fh = int(frame.height())

    x = _clamp(x, 0, fw - 1)
    y = _clamp(y, 0, fh - 1)
    w = _clamp(w, 1, fw - x)
    h = _clamp(h, 1, fh - y)

    roi = None
    try:
      roi = frame.copy(roi=(x, y, w, h))
    except Exception:
      try:
        roi = frame.cut(x, y, w, h)
      except Exception:
        return None, (x, y, w, h)

    try:
      roi = roi.resize(64, 64)
    except Exception:
      return None, (x, y, w, h)

    return roi, (x, y, w, h)

  def _primary_face(self, frame):
    self._ensure_detector()
    try:
      detections = self._kpu.run_yolo2(self._task_fd, frame)
    except Exception:
      raise VisionError("VISION_FAILED", "face_detect")

    if not detections:
      return None, 0

    best = detections[0]
    best_area = int(best.w() * best.h())
    for det in detections[1:]:
      area = int(det.w() * det.h())
      if area > best_area:
        best = det
        best_area = area
    return best, len(detections)

  def _score_match(self, candidate, template):
    try:
      diff = candidate.copy()
      diff.difference(template)
      stat = diff.get_statistics()
      return _safe_stat_l_mean(stat)
    except Exception:
      return 255

  def _confidence(self, score, person):
    if person == config.PERSON_NONE:
      return 0.0
    if person == config.PERSON_UNKNOWN:
      return 0.40

    strong = config.FACE_SCORE_THRESH_STRONG
    weak = config.FACE_SCORE_THRESH
    if score <= strong:
      return 0.95
    if score <= weak:
      span = weak - strong
      if span <= 0:
        return 0.70
      ratio = float(score - strong) / float(span)
      return 0.95 - (0.25 * ratio)
    return 0.40

  def recognize_frame(self, frame):
    bbox, face_count = self._primary_face(frame)
    if bbox is None:
      return {
        "person": config.PERSON_NONE,
        "confidence": 0.0,
        "faces_detected": 0,
        "score": None,
      }

    candidate, _ = self._extract_roi(frame, bbox)
    if candidate is None:
      raise VisionError("VISION_FAILED", "face_roi")

    if not self._known_templates:
      return {
        "person": config.PERSON_UNKNOWN,
        "confidence": 0.40,
        "faces_detected": face_count,
        "score": None,
      }

    best_person = config.PERSON_UNKNOWN
    best_score = 255
    for person in self._known_templates:
      score = self._score_match(candidate, self._known_templates[person])
      if score < best_score:
        best_score = score
        best_person = person

    if best_score > config.FACE_SCORE_THRESH:
      person = config.PERSON_UNKNOWN
    else:
      person = best_person

    return {
      "person": person,
      "confidence": self._confidence(best_score, person),
      "faces_detected": face_count,
      "score": best_score,
    }

  def vote_people(self, samples):
    votes = []
    best_conf = {}
    max_faces = 0
    for sample in samples:
      person = sample.get("person", config.PERSON_NONE)
      conf = float(sample.get("confidence", 0.0))
      votes.append(person)
      if conf > best_conf.get(person, 0.0):
        best_conf[person] = conf
      max_faces = max(max_faces, int(sample.get("faces_detected", 0)))

    person, conf = _person_from_votes(votes, best_conf)
    return {
      "person": person,
      "confidence": conf,
      "faces_detected": max_faces,
    }

  def _encode_jpeg(self, img):
    try:
      return img.compress(quality=90)
    except Exception:
      return None

  def learn(self, capture_cb, person, frames, deadline_ms):
    if person not in config.KNOWN_PERSONS:
      raise VisionError("BAD_REQUEST", "bad_person")
    if not storage.sd_available() or not storage.ensure_sd_layout():
      raise VisionError("STORAGE_UNAVAILABLE", "sd_missing")

    best_img = None
    best_area = -1
    best_sharp = -1

    for _ in range(frames):
      if _ticks_diff(_ticks_ms(), deadline_ms) > 0:
        raise VisionError("TIMEOUT", "timeout")

      frame = capture_cb()
      bbox, _ = self._primary_face(frame)
      if bbox is None:
        continue

      roi, xywh = self._extract_roi(frame, bbox)
      if roi is None:
        continue

      _, _, w, h = xywh
      area = int(w * h)
      sharp = 0
      try:
        sharp = _safe_stat_l_stdev(roi.get_statistics())
      except Exception:
        sharp = 0

      if area > best_area or (area == best_area and sharp > best_sharp):
        best_img = roi
        best_area = area
        best_sharp = sharp

    if best_img is None:
      raise VisionError("VISION_FAILED", "no_face")

    encoded = self._encode_jpeg(best_img)
    if encoded is not None:
      if not storage.save_face_jpeg(person, encoded):
        raise VisionError("STORAGE_UNAVAILABLE", "sd_write")
    else:
      path = storage.face_path(person)
      try:
        best_img.save(path)
      except Exception:
        raise VisionError("STORAGE_UNAVAILABLE", "sd_write")

    self._known_templates[person] = best_img
    return {"status": "learned", "person": person}

  def reset_faces(self):
    if not storage.sd_available() or not storage.ensure_sd_layout():
      raise VisionError("STORAGE_UNAVAILABLE", "sd_missing")
    storage.reset_faces()
    self.clear_templates()
    return {"status": "reset"}
