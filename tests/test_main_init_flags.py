import os
import unittest
from unittest.mock import patch

from bot.init_flags import should_run_schema_init, should_run_schema_init_webhook


class MainInitFlagsTests(unittest.TestCase):
    def test_auto_init_db_override_true(self):
        with patch.dict(os.environ, {"AUTO_INIT_DB": "true"}, clear=False):
            self.assertTrue(should_run_schema_init())

    def test_auto_init_db_override_false(self):
        with patch.dict(os.environ, {"AUTO_INIT_DB": "0"}, clear=False):
            self.assertFalse(should_run_schema_init())

    def test_default_enabled_on_vds(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(should_run_schema_init())

    def test_webhook_default_disabled_without_override(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(should_run_schema_init_webhook())

    def test_webhook_respects_auto_init_override(self):
        with patch.dict(os.environ, {"AUTO_INIT_DB": "1"}, clear=True):
            self.assertTrue(should_run_schema_init_webhook())


if __name__ == "__main__":
    unittest.main()
