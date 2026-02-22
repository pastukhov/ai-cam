"""UnitV vision tool runtime entrypoint (UART JSONL, one request-one response)."""

import config
import led
import protocol
from vision import VisionRuntime, VisionError

try:
  import machine
except ImportError:
  machine = None

try:
  import utime as _time
except ImportError:
  import time as _time


def _usb_debug(*parts):
  if not getattr(config, "USB_DEBUG_LOG", False):
    return
  try:
    print("[vision]", *parts)
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


def _ticks_add(base, delta):
  if hasattr(_time, "ticks_add"):
    return _time.ticks_add(base, delta)
  return base + delta


class DedupCache:
  def __init__(self, ttl_ms):
    self._ttl_ms = ttl_ms
    self._items = {}

  def _gc(self, now):
    to_delete = []
    for req_id in self._items:
      created_ms, _ = self._items[req_id]
      if _ticks_diff(now, created_ms) > self._ttl_ms:
        to_delete.append(req_id)
    for req_id in to_delete:
      try:
        del self._items[req_id]
      except Exception:
        pass

  def get(self, req_id, now):
    self._gc(now)
    item = self._items.get(req_id)
    if not item:
      return None
    created_ms, raw = item
    if _ticks_diff(now, created_ms) > self._ttl_ms:
      try:
        del self._items[req_id]
      except Exception:
        pass
      return None
    return raw

  def set(self, req_id, raw_bytes, now):
    self._gc(now)
    self._items[req_id] = (now, raw_bytes)


class Runtime:
  def __init__(self, uart):
    self._uart = uart
    self._vision = VisionRuntime()
    self._dedup = DedupCache(config.DEDUP_TTL_MS)
    self._processing = False
    _usb_debug("runtime_init")

  def _write_raw(self, raw_bytes):
    protocol.uart_writeline(self._uart, raw_bytes)

  def _write_payload(self, payload, req_id=None):
    raw = protocol.safe_json_encode(payload, req_id=req_id)
    protocol.uart_writeline(self._uart, raw)
    return raw

  def _bad_request(self, req_id, message):
    return protocol.short_error(req_id, "BAD_REQUEST", message)

  def _validate_request(self, payload):
    if not isinstance(payload, dict):
      return None, self._bad_request(None, "bad_obj")

    req_id = payload.get("req_id")
    cmd = payload.get("cmd")
    args = payload.get("args", {})

    if req_id is None:
      return None, self._bad_request(None, "missing_req")
    if cmd is None:
      return None, self._bad_request(req_id, "missing_cmd")

    if not isinstance(args, dict):
      args = {}

    return {
      "req_id": req_id,
      "cmd": str(cmd).upper(),
      "args": args,
    }, None

  def _dispatch(self, req, deadline_ms):
    cmd = req["cmd"]
    args = req["args"]

    if cmd == "PING":
      return {
        "status": "ok",
        "tool": config.TOOL_NAME,
      }

    if cmd == "INFO":
      return self._vision.info()

    if cmd == "SCAN":
      return self._vision.scan(args, deadline_ms)

    if cmd == "WHO":
      return self._vision.who(args, deadline_ms)

    if cmd == "OBJECTS":
      return self._vision.objects(args, deadline_ms)

    if cmd == "LEARN":
      led.learning()
      return self._vision.learn(args, deadline_ms)

    if cmd == "RESET_FACES":
      return self._vision.reset_faces()

    if cmd == "DEBUG":
      enabled = args.get("enabled", False)
      return self._vision.set_debug(enabled)

    raise VisionError("BAD_REQUEST", "unknown_cmd")

  def _led_for_result(self, result):
    if not isinstance(result, dict):
      led.idle()
      return
    person = result.get("person")
    if person in config.KNOWN_PERSONS:
      led.owner()
    elif person == config.PERSON_UNKNOWN:
      led.unknown()
    elif "status" in result:
      led.ok()
    else:
      led.idle()

  def _handle_line(self, line_bytes):
    led.busy()

    payload, err = protocol.parse_json_line(line_bytes)
    if err is not None:
      _usb_debug("bad_json", "len=%d" % len(line_bytes))
      self._write_payload(err, req_id=err.get("req_id"))
      led.error()
      return

    req, err = self._validate_request(payload)
    if err is not None:
      _usb_debug("bad_request", err.get("error", {}).get("message", "bad_req"))
      self._write_payload(err, req_id=err.get("req_id"))
      led.error()
      return

    _usb_debug("req", req["cmd"], "req_id=%s" % req["req_id"])

    req_id = req["req_id"]
    now = _ticks_ms()
    cached = self._dedup.get(req_id, now)
    if cached is not None:
      _usb_debug("dedup_hit", "req_id=%s" % req_id)
      self._write_raw(cached)
      return

    if self._processing:
      _usb_debug("busy", "req_id=%s" % req_id)
      err_payload = protocol.short_error(req_id, "BUSY", "busy")
      raw = self._write_payload(err_payload, req_id=req_id)
      self._dedup.set(req_id, raw, now)
      return

    self._processing = True
    raw = None
    started = now
    deadline_ms = _ticks_add(started, config.COMMAND_TIMEOUT_MS)

    try:
      result = self._dispatch(req, deadline_ms)
      if _ticks_diff(_ticks_ms(), deadline_ms) > 0:
        raise VisionError("TIMEOUT", "timeout")
      payload = {"req_id": req_id, "ok": True, "result": result}
      raw = self._write_payload(payload, req_id=req_id)
      _usb_debug("ok", req["cmd"], "req_id=%s" % req_id)
      self._led_for_result(result)
    except VisionError as err_ex:
      if err_ex.code in ("VISION_FAILED", "TIMEOUT"):
        self._vision.recover()
      payload = protocol.short_error(req_id, err_ex.code, err_ex.message)
      raw = self._write_payload(payload, req_id=req_id)
      _usb_debug("err", req["cmd"], "req_id=%s" % req_id, err_ex.code, err_ex.message)
      led.error()
    except Exception:
      self._vision.recover()
      payload = protocol.short_error(req_id, "VISION_FAILED", "internal")
      raw = self._write_payload(payload, req_id=req_id)
      _usb_debug("err", req["cmd"], "req_id=%s" % req_id, "VISION_FAILED", "internal")
      led.error()
    finally:
      self._processing = False

    if raw is not None:
      self._dedup.set(req_id, raw, _ticks_ms())

  def run_forever(self):
    _usb_debug("boot", "runtime_loop_start")
    led.init()
    led.boot()
    try:
      self._vision.boot()
      _usb_debug("boot", "vision_ready")
    except Exception:
      _usb_debug("boot", "vision_boot_failed")
      # Keep serving requests even if boot preloading failed.
      pass
    led.idle()

    while True:
      try:
        line = protocol.uart_readline(self._uart)
        if line is None:
          continue
        self._handle_line(line)
      except Exception:
        _usb_debug("loop", "recover")
        # Keep loop alive without emitting unsolicited UART output.
        self._vision.recover()


def _register_uart_pins():
  """Map Grove connector pins to UART via FPIOA (K210-specific)."""
  try:
    from fpioa_manager import fm
    fm.register(config.UART_TX_PIN, fm.fpioa.UART1_TX)
    fm.register(config.UART_RX_PIN, fm.fpioa.UART1_RX)
  except Exception:
    pass


def _build_uart():
  if machine is None:
    raise RuntimeError("machine module unavailable")

  _register_uart_pins()
  _usb_debug("uart", "id=%d" % config.UART_ID, "baud=%d" % config.UART_BAUD)

  kwargs = {}
  kwargs["timeout"] = config.UART_READ_TIMEOUT_MS
  kwargs["timeout_char"] = config.UART_READ_TIMEOUT_MS

  try:
    _usb_debug("uart", "open_with_kwargs")
    return machine.UART(config.UART_ID, config.UART_BAUD, **kwargs)
  except Exception:
    _usb_debug("uart", "open_with_kwargs_failed")
    pass
  try:
    _usb_debug("uart", "open_basic")
    return machine.UART(config.UART_ID, config.UART_BAUD)
  except Exception:
    _usb_debug("uart", "open_basic_failed")
    pass
  raise RuntimeError("No UART available")


def main():
  uart = _build_uart()
  Runtime(uart).run_forever()


if __name__ == "__main__":
  main()
