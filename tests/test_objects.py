import unittest
from unittest import mock
import tempfile
import os

import config
import objects


class FakeDet:
    def __init__(self, cid):
        self._cid = cid

    def classid(self):
        return self._cid


class FakeKPU:
    def __init__(self, detections=None, fail_load=False, fail_run=False):
        self.detections = detections if detections is not None else []
        self.fail_load = fail_load
        self.fail_run = fail_run
        self.loaded = None

    def load(self, model_ref):
        if self.fail_load:
            raise RuntimeError("load")
        self.loaded = model_ref
        return "task"

    def init_yolo2(self, *args, **kwargs):
        return None

    def run_yolo2(self, _task, _frame):
        if self.fail_run:
            raise RuntimeError("run")
        return self.detections

    def deinit(self, _task):
        return None


class ObjectRuntimeTests(unittest.TestCase):
    def test_model_missing(self):
        rt = objects.ObjectRuntime(kpu_mod=FakeKPU())
        with mock.patch("storage.sd_available", return_value=False), mock.patch(
            "storage.ensure_sd_layout", return_value=False
        ), mock.patch.object(config, "OBJECT_MODEL_FLASH_ADDR", None):
            with self.assertRaises(objects.VisionError) as ctx:
                rt.ensure_loaded()
        self.assertEqual(ctx.exception.code, "MODEL_MISSING")

    def test_allow_partial_on_missing_model(self):
        rt = objects.ObjectRuntime(kpu_mod=FakeKPU())
        with mock.patch("storage.sd_available", return_value=False), mock.patch(
            "storage.ensure_sd_layout", return_value=False
        ), mock.patch.object(config, "OBJECT_MODEL_FLASH_ADDR", None):
            labels = rt.detect_frame(object(), allow_partial=True)
        self.assertEqual(labels, [])

    def test_detect_filters_and_orders_labels(self):
        dets = [FakeDet(1), FakeDet(0), FakeDet(1), FakeDet(99)]
        kpu = FakeKPU(detections=dets)
        rt = objects.ObjectRuntime(kpu_mod=kpu)

        with mock.patch("storage.sd_available", return_value=True), mock.patch(
            "storage.ensure_sd_layout", return_value=True
        ), mock.patch("objects._os.stat", return_value=True):
            labels = rt.detect_frame(object())

        self.assertEqual(labels, ["door", "window"])
        self.assertEqual(rt.model_source(), "sd")

    def test_detect_vision_failure_when_run_fails(self):
        rt = objects.ObjectRuntime(kpu_mod=FakeKPU(fail_run=True))
        with mock.patch("storage.sd_available", return_value=True), mock.patch(
            "storage.ensure_sd_layout", return_value=True
        ), mock.patch("objects._os.stat", return_value=True):
            with self.assertRaises(objects.VisionError) as ctx:
                rt.detect_frame(object())
        self.assertEqual(ctx.exception.code, "VISION_FAILED")

    def test_detect_uses_label_map(self):
        dets = [FakeDet(0)]
        kpu = FakeKPU(detections=dets)
        rt = objects.ObjectRuntime(kpu_mod=kpu)

        with mock.patch("storage.sd_available", return_value=True), mock.patch(
            "storage.ensure_sd_layout", return_value=True
        ), mock.patch("objects._os.stat", return_value=True), mock.patch.object(
            rt, "_load_class_names", return_value=["apple"]
        ), mock.patch.object(
            rt, "_load_label_map", return_value={"apple": "cup"}
        ):
            labels = rt.detect_frame(object())

        self.assertEqual(labels, ["cup"])

    def test_load_class_names_from_csv_file(self):
        rt = objects.ObjectRuntime(kpu_mod=FakeKPU())
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "classes.txt")
            with open(p, "w") as f:
                f.write("apple, banana,orange")
            with mock.patch.object(config, "OBJECT_CLASSES_SD_PATH", p), mock.patch(
                "storage.sd_available", return_value=True
            ):
                names = rt._load_class_names()
        self.assertEqual(names, ["apple", "banana", "orange"])


if __name__ == "__main__":
    unittest.main()
