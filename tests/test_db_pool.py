import unittest

from bot.db_pool import prepare_query


class DbPoolQueryTests(unittest.TestCase):
    def test_named_params_are_converted_to_positional(self):
        sql, values = prepare_query(
            "SELECT * FROM users WHERE id = $user_id AND username = $username",
            {"user_id": 1, "username": "alice"},
        )
        self.assertEqual(sql, "SELECT * FROM users WHERE id = $1 AND username = $2")
        self.assertEqual(values, [1, "alice"])

    def test_repeated_param_uses_single_placeholder(self):
        sql, values = prepare_query(
            "SELECT $user_id, $user_id",
            {"user_id": 42},
        )
        self.assertEqual(sql, "SELECT $1, $1")
        self.assertEqual(values, [42])


if __name__ == "__main__":
    unittest.main()
