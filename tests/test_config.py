import unittest

import config


class ConfigTests(unittest.TestCase):
    def test_core_limits_are_sane(self):
        self.assertGreater(config.MAX_JSON_BYTES, 0)
        self.assertGreater(config.MAX_OBJECTS, 0)
        self.assertGreater(config.MAX_SCAN_FRAMES, 0)
        self.assertGreater(config.MAX_LEARN_FRAMES, 0)
        self.assertGreater(config.COMMAND_TIMEOUT_MS, 0)
        self.assertGreater(config.DEDUP_TTL_MS, 0)

    def test_known_persons(self):
        self.assertIn(config.PERSON_OWNER_1, config.KNOWN_PERSONS)
        self.assertIn(config.PERSON_OWNER_2, config.KNOWN_PERSONS)
        self.assertNotEqual(config.PERSON_OWNER_1, config.PERSON_OWNER_2)

    def test_error_messages_present(self):
        for code in (
            "BAD_REQUEST",
            "BUSY",
            "TIMEOUT",
            "VISION_FAILED",
            "STORAGE_UNAVAILABLE",
            "MODEL_MISSING",
        ):
            self.assertIn(code, config.ERROR_MESSAGES)


if __name__ == "__main__":
    unittest.main()
