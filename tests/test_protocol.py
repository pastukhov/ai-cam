import json
import unittest

import config
import protocol


class FakeUART:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        return len(data)


class ProtocolTests(unittest.TestCase):
    def test_parse_json_line_success(self):
        payload, err = protocol.parse_json_line(b'{"cmd":"PING","req_id":"1"}')
        self.assertIsNone(err)
        self.assertEqual(payload["cmd"], "PING")
        self.assertEqual(payload["req_id"], "1")

    def test_parse_json_line_bad_json(self):
        payload, err = protocol.parse_json_line(b'{bad')
        self.assertIsNone(payload)
        self.assertEqual(err["error"]["code"], "BAD_REQUEST")

    def test_safe_json_encode_respects_limit(self):
        huge = {"req_id": "x", "ok": True, "result": {"blob": "a" * 3000}}
        raw = protocol.safe_json_encode(huge)
        self.assertLessEqual(len(raw), config.MAX_JSON_BYTES)
        decoded = json.loads(raw.decode("utf-8"))
        self.assertFalse(decoded["ok"])
        self.assertEqual(decoded["error"]["code"], "BAD_REQUEST")

    def test_uart_writeline_adds_newline(self):
        uart = FakeUART()
        ok = protocol.uart_writeline(uart, {"req_id": "1", "ok": True, "result": {"x": 1}})
        self.assertTrue(ok)
        self.assertEqual(len(uart.writes), 1)
        self.assertTrue(uart.writes[0].endswith(b"\n"))


if __name__ == "__main__":
    unittest.main()
