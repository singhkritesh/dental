from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from services.auth_store import AuthStore


class AuthStoreTests(unittest.TestCase):
    def test_bootstrap_register_and_authenticate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = AuthStore(root / "users.json", root / "sessions.json", session_hours=1)
            self.assertTrue(store.bootstrap_required())

            created = store.register("Admin", "password123")
            self.assertEqual(created.role, "admin")
            self.assertFalse(store.bootstrap_required())

            user = store.authenticate("admin", "password123")
            token = store.create_session(user)
            looked_up = store.get_user_for_token(token)
            self.assertIsNotNone(looked_up)
            self.assertEqual(looked_up.username, "admin")

    def test_register_duplicate_user_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = AuthStore(root / "users.json", root / "sessions.json", session_hours=1)
            store.register("staff1", "password123")
            with self.assertRaises(Exception):
                store.register("staff1", "password123")


if __name__ == "__main__":
    unittest.main()
