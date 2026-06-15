import unittest

from aiogram.fsm.storage.base import StorageKey

from bot.fsm_storage_pg import PgStorage


class PgStorageKeyParamsTests(unittest.TestCase):
    def test_key_parameters_use_sentinels_for_nullable_parts(self):
        key = StorageKey(
            bot_id=None,
            chat_id=100,
            user_id=200,
            thread_id=None,
            business_connection_id=None,
            destiny="default",
        )
        params = PgStorage._key_parameters(key)
        self.assertEqual(params["bot_id"], 0)
        self.assertEqual(params["thread_id"], 0)
        self.assertEqual(params["business_connection_id"], "")
        self.assertEqual(params["destiny"], "default")

    def test_key_parameters_from_mapping(self):
        params = PgStorage._key_parameters({
            "bot_id": 1,
            "chat_id": 2,
            "user_id": 3,
            "thread_id": 4,
            "business_connection_id": "bc",
            "destiny": "wizard",
        })
        self.assertEqual(params["business_connection_id"], "bc")
        self.assertEqual(params["destiny"], "wizard")


if __name__ == "__main__":
    unittest.main()
