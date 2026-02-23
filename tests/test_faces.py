import unittest
from unittest import mock

import config
import faces


class FakeDet:
    def __init__(self, x=0, y=0, w=10, h=10):
        self._x = x
        self._y = y
        self._w = w
        self._h = h

    def x(self):
        return self._x

    def y(self):
        return self._y

    def w(self):
        return self._w

    def h(self):
        return self._h


class FakeStat:
    def __init__(self, l_mean=0, l_stdev=0):
        self._l_mean = l_mean
        self._l_stdev = l_stdev

    def l_mean(self):
        return self._l_mean

    def l_stdev(self):
        return self._l_stdev


class FakeImage:
    def __init__(self, score=10, sharp=5):
        self.score = score
        self.sharp = sharp
        self.saved_path = None

    def copy(self, roi=None):
        return FakeImage(self.score, self.sharp)

    def difference(self, template):
        self.score = getattr(template, "score", self.score)

    def get_statistics(self):
        return FakeStat(l_mean=self.score, l_stdev=self.sharp)

    def resize(self, _w, _h):
        return self

    def compress(self, quality=90):
        return b"jpeg"

    def save(self, path):
        self.saved_path = path


class FakeFrame(FakeImage):
    def __init__(self, score=10, sharp=5, width=320, height=240):
        super().__init__(score, sharp)
        self._width = width
        self._height = height

    def width(self):
        return self._width

    def height(self):
        return self._height


class FaceRuntimeTests(unittest.TestCase):
    def test_person_vote_tie_break_by_conf(self):
        p, c = faces._person_from_votes(
            [config.PERSON_OWNER_1, config.PERSON_OWNER_2],
            {config.PERSON_OWNER_1: 0.8, config.PERSON_OWNER_2: 0.9},
        )
        self.assertEqual(p, config.PERSON_OWNER_2)
        self.assertEqual(c, 0.9)

    def test_recognize_none_when_no_face(self):
        rt = faces.FaceRuntime(image_mod=object(), kpu_mod=object())
        rt._primary_face = lambda _frame: (None, 0)
        out = rt.recognize_frame(FakeFrame())
        self.assertEqual(out["person"], config.PERSON_NONE)

    def test_recognize_unknown_without_templates(self):
        rt = faces.FaceRuntime(image_mod=object(), kpu_mod=object())
        rt._primary_face = lambda _frame: (FakeDet(), 1)
        rt._extract_roi = lambda _frame, _bbox: (FakeImage(score=50), (0, 0, 10, 10))
        out = rt.recognize_frame(FakeFrame())
        self.assertEqual(out["person"], config.PERSON_UNKNOWN)

    def test_recognize_best_template(self):
        rt = faces.FaceRuntime(image_mod=object(), kpu_mod=object())
        rt._primary_face = lambda _frame: (FakeDet(), 1)
        rt._extract_roi = lambda _frame, _bbox: (FakeImage(score=10), (0, 0, 10, 10))
        rt._known_templates = {
            config.PERSON_OWNER_1: FakeImage(score=11),
            config.PERSON_OWNER_2: FakeImage(score=16),
        }
        out = rt.recognize_frame(FakeFrame())
        self.assertEqual(out["person"], config.PERSON_OWNER_1)
        self.assertGreater(out["confidence"], 0.7)

    def test_learn_bad_person(self):
        rt = faces.FaceRuntime(image_mod=object(), kpu_mod=object())
        with self.assertRaises(faces.VisionError) as ctx:
            rt.learn(lambda: FakeFrame(), "NOPE", 1, faces._ticks_ms() + 10000)
        self.assertEqual(ctx.exception.code, "BAD_REQUEST")

    def test_learn_storage_missing(self):
        rt = faces.FaceRuntime(image_mod=object(), kpu_mod=object())
        with mock.patch("storage.sd_available", return_value=False), mock.patch(
            "storage.ensure_sd_layout", return_value=False
        ):
            with self.assertRaises(faces.VisionError) as ctx:
                rt.learn(lambda: FakeFrame(), config.PERSON_OWNER_1, 1, faces._ticks_ms() + 10000)
        self.assertEqual(ctx.exception.code, "STORAGE_UNAVAILABLE")

    def test_learn_no_face(self):
        rt = faces.FaceRuntime(image_mod=object(), kpu_mod=object())
        rt._primary_face = lambda _frame: (None, 0)
        with mock.patch("storage.sd_available", return_value=True), mock.patch(
            "storage.ensure_sd_layout", return_value=True
        ):
            with self.assertRaises(faces.VisionError) as ctx:
                rt.learn(lambda: FakeFrame(), config.PERSON_OWNER_1, 2, faces._ticks_ms() + 10000)
        self.assertEqual(ctx.exception.code, "VISION_FAILED")
        self.assertEqual(ctx.exception.message, "no_face")

    def test_learn_success_and_cache_update(self):
        rt = faces.FaceRuntime(image_mod=object(), kpu_mod=object())
        rt._primary_face = lambda _frame: (FakeDet(w=20, h=20), 1)
        rt._extract_roi = lambda _frame, _bbox: (FakeImage(score=10, sharp=7), (0, 0, 20, 20))
        with mock.patch("storage.sd_available", return_value=True), mock.patch(
            "storage.ensure_sd_layout", return_value=True
        ), mock.patch("storage.save_face_jpeg", return_value=True):
            out = rt.learn(lambda: FakeFrame(), config.PERSON_OWNER_1, 1, faces._ticks_ms() + 10000)
        self.assertEqual(out["status"], "learned")
        self.assertIn(config.PERSON_OWNER_1, rt._known_templates)

    def test_reset_faces(self):
        rt = faces.FaceRuntime(image_mod=object(), kpu_mod=object())
        rt._known_templates = {config.PERSON_OWNER_1: FakeImage()}
        with mock.patch("storage.sd_available", return_value=True), mock.patch(
            "storage.ensure_sd_layout", return_value=True
        ), mock.patch("storage.reset_faces", return_value=1):
            out = rt.reset_faces()
        self.assertEqual(out["status"], "reset")
        self.assertEqual(rt._known_templates, {})


if __name__ == "__main__":
    unittest.main()
