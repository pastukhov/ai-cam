import os
import tempfile
import unittest

import config
import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        self.orig = {
            "SD_ROOT": config.SD_ROOT,
            "SD_FACES_DIR": config.SD_FACES_DIR,
            "SD_MODELS_DIR": config.SD_MODELS_DIR,
            "SD_CONFIG_PATH": config.SD_CONFIG_PATH,
            "OWNER_1_FACE_PATH": config.OWNER_1_FACE_PATH,
            "OWNER_2_FACE_PATH": config.OWNER_2_FACE_PATH,
        }

        config.SD_ROOT = self.root
        config.SD_FACES_DIR = os.path.join(self.root, "faces")
        config.SD_MODELS_DIR = os.path.join(self.root, "models")
        config.SD_CONFIG_PATH = os.path.join(self.root, "config.json")
        config.OWNER_1_FACE_PATH = os.path.join(config.SD_FACES_DIR, "owner_1.jpg")
        config.OWNER_2_FACE_PATH = os.path.join(config.SD_FACES_DIR, "owner_2.jpg")

    def tearDown(self):
        for k, v in self.orig.items():
            setattr(config, k, v)
        self.tmp.cleanup()

    def test_sd_layout_and_face_roundtrip(self):
        self.assertTrue(storage.sd_available())
        self.assertTrue(storage.ensure_sd_layout())

        data = b"jpeg-bytes"
        self.assertTrue(storage.save_face_jpeg(config.PERSON_OWNER_1, data))
        self.assertEqual(storage.load_face_bytes(config.PERSON_OWNER_1), data)

    def test_face_path_and_delete_reset(self):
        storage.ensure_sd_layout()
        storage.save_face_jpeg(config.PERSON_OWNER_1, b"1")
        storage.save_face_jpeg(config.PERSON_OWNER_2, b"2")
        self.assertEqual(storage.reset_faces(), 2)
        self.assertIsNone(storage.load_face_bytes(config.PERSON_OWNER_1))
        self.assertIsNone(storage.load_face_bytes(config.PERSON_OWNER_2))

    def test_load_face_files(self):
        storage.ensure_sd_layout()
        storage.save_face_jpeg(config.PERSON_OWNER_1, b"1")
        faces = storage.load_face_files()
        self.assertIn(config.PERSON_OWNER_1, faces)
        self.assertNotIn(config.PERSON_OWNER_2, faces)

    def test_read_write_config(self):
        self.assertEqual(storage.read_config({"a": 1}), {"a": 1})
        self.assertTrue(storage.write_config({"x": 2}))
        self.assertEqual(storage.read_config({}), {"x": 2})

    def test_write_config_rejects_non_dict(self):
        self.assertFalse(storage.write_config([1, 2, 3]))


if __name__ == "__main__":
    unittest.main()
