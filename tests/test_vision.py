import unittest
from unittest import mock

import config
import vision


class DummySensor:
    RGB565 = "rgb565"
    QVGA = "qvga"

    def __init__(self):
        self.calls = []

    def reset(self):
        self.calls.append("reset")

    def set_pixformat(self, fmt):
        self.calls.append(("pix", fmt))

    def set_framesize(self, size):
        self.calls.append(("size", size))

    def run(self, val):
        self.calls.append(("run", val))

    def skip_frames(self, time=0):
        self.calls.append(("skip", time))

    def snapshot(self):
        return object()


class FakeFace:
    def __init__(self):
        self.samples = []
        self.learn_calls = []

    def load_templates(self):
        return 1

    def recognize_frame(self, _frame):
        if self.samples:
            return self.samples.pop(0)
        return {"person": config.PERSON_NONE, "confidence": 0.0, "faces_detected": 0}

    def vote_people(self, samples):
        return {"person": samples[0]["person"], "confidence": samples[0].get("confidence", 0.0), "faces_detected": 1}

    def templates_loaded(self):
        return 1

    def learn(self, capture_cb, person, frames, deadline_ms):
        self.learn_calls.append((person, frames))
        capture_cb()
        return {"status": "learned", "person": person}

    def reset_faces(self):
        return {"status": "reset"}

    def deinit(self):
        return None


class FakeObjects:
    def __init__(self):
        self.calls = []

    def detect_frame(self, _frame, allow_partial=False):
        self.calls.append(allow_partial)
        return ["door"]

    def model_source(self):
        return "sd"

    def deinit(self):
        return None


class VisionRuntimeTests(unittest.TestCase):
    def _new_runtime(self):
        rt = vision.VisionRuntime()
        rt._sensor = DummySensor()
        rt._camera_ready = True
        rt._face = FakeFace()
        rt._objects = FakeObjects()
        return rt

    def test_info_and_capabilities(self):
        rt = self._new_runtime()
        with mock.patch("storage.sd_available", return_value=True):
            info = rt.info()
        self.assertEqual(info["tool"], config.TOOL_NAME)
        self.assertTrue(info["capabilities"]["sd"])

    def test_scan_success(self):
        rt = self._new_runtime()
        rt._face.samples = [{"person": config.PERSON_OWNER_1, "confidence": 0.92, "faces_detected": 1}]
        out = rt.scan({"mode": "FAST", "frames": 1, "allow_partial": True}, vision._ticks_ms() + 10000)
        self.assertEqual(out["person"], config.PERSON_OWNER_1)
        self.assertEqual(out["objects"], ["door"])
        self.assertIn("confidence", out)

    def test_who_none_has_no_confidence(self):
        rt = self._new_runtime()
        rt._face.samples = [{"person": config.PERSON_NONE, "confidence": 0.0, "faces_detected": 0}]
        out = rt.who({"frames": 1}, vision._ticks_ms() + 10000)
        self.assertEqual(out["person"], config.PERSON_NONE)
        self.assertNotIn("confidence", out)

    def test_objects_success(self):
        rt = self._new_runtime()
        out = rt.objects({"mode": "FAST", "frames": 1}, vision._ticks_ms() + 10000)
        self.assertEqual(out["objects"], ["door"])
        self.assertEqual(out["frames"], 1)

    def test_learn_clamps_frames(self):
        rt = self._new_runtime()
        out = rt.learn({"person": config.PERSON_OWNER_1, "frames": 999}, vision._ticks_ms() + 10000)
        self.assertEqual(out["status"], "learned")
        self.assertEqual(rt._face.learn_calls[-1][1], config.MAX_LEARN_FRAMES)

    def test_reset_faces(self):
        rt = self._new_runtime()
        out = rt.reset_faces()
        self.assertEqual(out["status"], "reset")

    def test_recover_resets_camera_ready(self):
        rt = self._new_runtime()
        rt._camera_ready = True
        rt.recover()
        self.assertFalse(rt._camera_ready)


if __name__ == "__main__":
    unittest.main()
