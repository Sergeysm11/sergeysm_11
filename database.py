import sqlite3
from typing import Optional


class Database:
    def __init__(self, path: str = "quotes.db"):
        self.path = path

    def _conn(self):
        return sqlite3.connect(self.path)

    def init(self):
        with self._conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    book TEXT NOT NULL,
                    quote TEXT NOT NULL,
                    shown_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            conn.commit()

    def add_quote(self, book: str, quote: str) -> int:
        with self._conn() as conn:
            cursor = conn.execute(
                "INSERT INTO quotes (book, quote) VALUES (?, ?)",
                (book, quote)
            )
            conn.commit()
            return cursor.lastrowid

    def delete_quote(self, quote_id: int) -> bool:
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM quotes WHERE id = ?", (quote_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_books(self):
        with self._conn() as conn:
            return conn.execute(
                "SELECT book, COUNT(*) as cnt FROM quotes GROUP BY book ORDER BY cnt DESC"
            ).fetchall()

    def get_quotes_by_book(self, book: str):
        with self._conn() as conn:
            return conn.execute(
                "SELECT id, quote FROM quotes WHERE book LIKE ? ORDER BY id",
                (f"%{book}%",)
            ).fetchall()

    def get_random_quotes(self, count: int):
        with self._conn() as conn:
            # Сначала берём наименее показанные, среди них случайные
            return conn.execute(
                """
                SELECT id, book, quote FROM quotes
                ORDER BY shown_count ASC, RANDOM()
                LIMIT ?
                """,
                (count,)
            ).fetchall()

    def mark_shown(self, quote_id: int):
        with self._conn() as conn:
            conn.execute(
                "UPDATE quotes SET shown_count = shown_count + 1 WHERE id = ?",
                (quote_id,)
            )
            conn.commit()

    def get_stats(self):
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM quotes").fetchone()[0]
            books = conn.execute("SELECT COUNT(DISTINCT book) FROM quotes").fetchone()[0]
            shown = conn.execute("SELECT SUM(shown_count) FROM quotes").fetchone()[0] or 0
            return {"total": total, "books": books, "shown": shown}

    def set_setting(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, value)
            )
            conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else default
