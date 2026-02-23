import json
import unittest
from unittest import mock

import config
import main
from vision import VisionError


class FakeUART:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        return len(data)


class FakeVision:
    def __init__(self):
        self.calls = []
        self.recover_called = 0

    def info(self):
        self.calls.append(("INFO", None))
        return {"tool": "vision_k210"}

    def scan(self, args, deadline_ms):
        self.calls.append(("SCAN", args))
        return {"person": "NONE", "objects": [], "frames": 1, "truncated": False, "faces_detected": 0}

    def who(self, args, deadline_ms):
        self.calls.append(("WHO", args))
        return {"person": "NONE", "frames": 1}

    def objects(self, args, deadline_ms):
        self.calls.append(("OBJECTS", args))
        return {"objects": [], "frames": 1, "truncated": False}

    def learn(self, args, deadline_ms):
        self.calls.append(("LEARN", args))
        return {"status": "learned", "person": "OWNER_1"}

    def reset_faces(self):
        self.calls.append(("RESET_FACES", None))
        return {"status": "reset"}

    def set_debug(self, enabled):
        self.calls.append(("DEBUG", enabled))
        return {"debug": bool(enabled)}

    def recover(self):
        self.recover_called += 1


class RuntimeTests(unittest.TestCase):
    def _new_runtime(self):
        uart = FakeUART()
        rt = main.Runtime(uart)
        rt._vision = FakeVision()
        return rt, uart

    def _last_json(self, uart):
        self.assertTrue(uart.writes)
        return json.loads(uart.writes[-1].decode("utf-8"))

    def test_ping(self):
        rt, uart = self._new_runtime()
        rt._handle_line(b'{"cmd":"PING","req_id":"1"}')
        data = self._last_json(uart)
        self.assertTrue(data["ok"])
        self.assertEqual(data["result"]["status"], "ok")

    def test_dedup_returns_byte_identical_response(self):
        rt, uart = self._new_runtime()
        line = b'{"cmd":"PING","req_id":"same"}'
        rt._handle_line(line)
        first = uart.writes[-1]
        rt._handle_line(line)
        second = uart.writes[-1]
        self.assertEqual(first, second)

    def test_unknown_command_returns_bad_request(self):
        rt, uart = self._new_runtime()
        rt._handle_line(b'{"cmd":"NOPE","req_id":"2"}')
        data = self._last_json(uart)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "BAD_REQUEST")

    def test_bad_json_returns_bad_request(self):
        rt, uart = self._new_runtime()
        rt._handle_line(b'{bad')
        data = self._last_json(uart)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "BAD_REQUEST")

    def test_busy_returns_busy(self):
        rt, uart = self._new_runtime()
        rt._processing = True
        rt._handle_line(b'{"cmd":"PING","req_id":"3"}')
        data = self._last_json(uart)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "BUSY")

    def test_vision_error_triggers_recover(self):
        rt, uart = self._new_runtime()

        def boom(_args, _deadline):
            raise VisionError("VISION_FAILED", "x")

        rt._vision.scan = boom
        rt._handle_line(b'{"cmd":"SCAN","req_id":"4","args":{}}')
        data = self._last_json(uart)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "VISION_FAILED")
        self.assertEqual(rt._vision.recover_called, 1)

    def test_missing_req_id(self):
        rt, uart = self._new_runtime()
        rt._handle_line(b'{"cmd":"PING"}')
        data = self._last_json(uart)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "BAD_REQUEST")

    def test_debug_dispatch(self):
        rt, uart = self._new_runtime()
        rt._handle_line(b'{"cmd":"DEBUG","req_id":"d","args":{"enabled":true}}')
        data = self._last_json(uart)
        self.assertTrue(data["ok"])
        self.assertTrue(data["result"]["debug"])

    def test_timeout_error_triggers_recover(self):
        rt, uart = self._new_runtime()

        def boom(_req, _deadline):
            raise VisionError("TIMEOUT", "timeout")

        rt._dispatch = boom
        rt._handle_line(b'{"cmd":"PING","req_id":"t"}')
        data = self._last_json(uart)
        self.assertFalse(data["ok"])
        self.assertEqual(data["error"]["code"], "TIMEOUT")
        self.assertEqual(rt._vision.recover_called, 1)


class DedupCacheTests(unittest.TestCase):
    def test_ttl_expiry(self):
        cache = main.DedupCache(ttl_ms=10)
        cache.set("x", b"abc", now=0)
        self.assertEqual(cache.get("x", now=5), b"abc")
        self.assertIsNone(cache.get("x", now=11))


class BuildUartTests(unittest.TestCase):
    def test_build_uart_fallback(self):
        class MachineMock:
            def __init__(self):
                self.calls = []

            def UART(self, uart_id, baud, **kwargs):
                self.calls.append((uart_id, baud, kwargs))
                if kwargs:
                    raise RuntimeError("kwargs unsupported")
                return "uart-ok"

        mm = MachineMock()
        with mock.patch.object(main, "machine", mm):
            out = main._build_uart()
        self.assertEqual(out, "uart-ok")
        self.assertEqual(mm.calls[0][0], config.UART_ID)


if __name__ == "__main__":
    unittest.main()
