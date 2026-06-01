import sqlite3
import tempfile
import unittest
from pathlib import Path

from cloudmailmanual_app.repositories import accounts


class AccountHistorySearchTest(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = str(Path(self.tmpdir.name) / "accounts.db")
        self.original_db_path = accounts.DB_PATH
        accounts.DB_PATH = self.db_path

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT NOT NULL,
                    password TEXT NOT NULL,
                    app_password TEXT NOT NULL,
                    name TEXT NOT NULL,
                    age INTEGER NOT NULL,
                    birthday TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    used INTEGER NOT NULL DEFAULT 0,
                    used_at TEXT,
                    platforms TEXT NOT NULL DEFAULT ''
                )
                """
            )
            rows = [
                ("ben_s_gao@occ.edge.mailyplus.com", "p1", "a1", "Ben Gao"),
                ("mary.wilson@example.com", "p2", "a2", "Mary Wilson"),
                ("alex_gao@test.com", "p3", "a3", "Alex Gao"),
            ]
            for email, password, app_password, name in rows:
                conn.execute(
                    """
                    INSERT INTO accounts (
                        email, password, app_password, name, age, birthday, created_at,
                        used, used_at, platforms
                    )
                    VALUES (?, ?, ?, ?, 25, '2000-01-01', '2026-01-01 00:00:00', 0, NULL, '')
                    """,
                    (email, password, app_password, name),
                )
            conn.commit()

    def tearDown(self):
        accounts.DB_PATH = self.original_db_path
        self.tmpdir.cleanup()

    def test_history_can_filter_by_email_keyword(self):
        data = accounts.get_accounts_history(page=1, page_size=20, email_query="gao")

        emails = [item["email"] for item in data["items"]]
        self.assertEqual(data["total"], 2)
        self.assertEqual(
            emails,
            ["alex_gao@test.com", "ben_s_gao@occ.edge.mailyplus.com"],
        )

    def test_history_filter_escapes_like_wildcards(self):
        data = accounts.get_accounts_history(page=1, page_size=20, email_query="%")

        self.assertEqual(data["total"], 0)
        self.assertEqual(data["items"], [])

    def test_bulk_delete_selected_account_ids_only(self):
        deleted, remaining = accounts.bulk_delete_accounts(mode="selected", ids=[1, 3])

        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute("SELECT id, email FROM accounts ORDER BY id").fetchall()

        self.assertEqual(deleted, 2)
        self.assertEqual(remaining, 1)
        self.assertEqual(rows, [(2, "mary.wilson@example.com")])


if __name__ == "__main__":
    unittest.main()
