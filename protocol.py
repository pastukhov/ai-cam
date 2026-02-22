"""UART JSONL protocol helpers (MicroPython compatible)."""

import config

try:
  import ujson as _json
except ImportError:
  import json as _json

try:
  import utime as _time
except ImportError:
  import time as _time


def _ticks_ms():
  if hasattr(_time, "ticks_ms"):
    return _time.ticks_ms()
  return int(_time.time() * 1000)


def _ticks_diff(now, old):
  if hasattr(_time, "ticks_diff"):
    return _time.ticks_diff(now, old)
  return now - old


def _trim_message(message):
  if message is None:
    return ""
  text = str(message)
  if len(text) > 24:
    return text[:24]
  return text


def short_error(req_id, code, message=None):
  msg = _trim_message(message)
  if not msg:
    msg = config.ERROR_MESSAGES.get(code, "error")
  return {
    "req_id": req_id,
    "ok": False,
    "error": {
      "code": code,
      "message": msg,
    },
  }


def _json_dumps(obj):
  try:
    return _json.dumps(obj, separators=(",", ":"))
  except TypeError:
    return _json.dumps(obj)


def safe_json_encode(payload, req_id=None, max_bytes=config.MAX_JSON_BYTES):
  text = _json_dumps(payload)
  data = text.encode("utf-8")
  if len(data) <= max_bytes:
    return data

  err_req_id = req_id
  if err_req_id is None and isinstance(payload, dict):
    err_req_id = payload.get("req_id")
  fallback = short_error(err_req_id, "BAD_REQUEST", "too_long")
  raw = _json_dumps(fallback).encode("utf-8")
  if len(raw) <= max_bytes:
    return raw

  # Last-resort minimal JSON to always respect transport cap.
  return b'{"req_id":null,"ok":false,"error":{"code":"BAD_REQUEST","message":"too_long"}}'


def uart_writeline(uart, payload, req_id=None):
  if isinstance(payload, bytes):
    line = payload
  elif isinstance(payload, str):
    line = payload.encode("utf-8")
  else:
    line = safe_json_encode(payload, req_id=req_id)

  if not line.endswith(b"\n"):
    line = line + b"\n"

  if len(line) > config.MAX_JSON_BYTES:
    line = safe_json_encode(short_error(req_id, "BAD_REQUEST", "too_long"))
    line = line + b"\n"

  try:
    uart.write(line)
  except Exception:
    return False
  return True


def uart_readline(uart, timeout_ms=config.UART_LINE_TIMEOUT_MS, max_bytes=config.UART_MAX_LINE_BYTES):
  start = _ticks_ms()
  buf = bytearray()

  while _ticks_diff(_ticks_ms(), start) < timeout_ms:
    chunk = None
    try:
      if hasattr(uart, "readline"):
        chunk = uart.readline()
      else:
        if hasattr(uart, "any") and uart.any():
          chunk = uart.read(1)
    except Exception:
      return None

    if not chunk:
      if hasattr(_time, "sleep_ms"):
        _time.sleep_ms(2)
      else:
        _time.sleep(0.002)
      continue

    if isinstance(chunk, str):
      chunk = chunk.encode("utf-8")

    for b in chunk:
      if b == 10:  # '\n'
        return bytes(buf)
      if b == 13:  # '\r'
        continue
      if len(buf) >= max_bytes:
        return None
      buf.append(b)

    if len(buf) >= max_bytes:
      return None

  if buf:
    return bytes(buf)
  return None


def parse_json_line(line_bytes):
  if line_bytes is None:
    return None, short_error(None, "BAD_REQUEST", "empty")

  try:
    if isinstance(line_bytes, bytes):
      text = line_bytes.decode("utf-8")
    else:
      text = str(line_bytes)
    payload = _json.loads(text)
  except Exception:
    return None, short_error(None, "BAD_REQUEST", "bad_json")

  if not isinstance(payload, dict):
    return None, short_error(None, "BAD_REQUEST", "bad_obj")

  return payload, None

