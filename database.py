import os
import psycopg2
from psycopg2.extras import RealDictCursor


class Database:
    def __init__(self):
        self.url = os.getenv("DATABASE_URL")

    def _conn(self):
        return psycopg2.connect(self.url)

    def init(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS quotes (
                        id SERIAL PRIMARY KEY,
                        book TEXT NOT NULL,
                        quote TEXT NOT NULL,
                        shown_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    )
                """)
            conn.commit()

    def add_quote(self, book: str, quote: str) -> int:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO quotes (book, quote) VALUES (%s, %s) RETURNING id",
                    (book, quote)
                )
                row = cur.fetchone()
            conn.commit()
            return row[0]

    def delete_quote(self, quote_id: int) -> bool:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM quotes WHERE id = %s", (quote_id,))
                deleted = cur.rowcount > 0
            conn.commit()
            return deleted

    def get_books(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT book, COUNT(*) as cnt FROM quotes GROUP BY book ORDER BY cnt DESC"
                )
                return cur.fetchall()

    def get_quotes_by_book(self, book: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, quote FROM quotes WHERE book ILIKE %s ORDER BY id",
                    (f"%{book}%",)
                )
                return cur.fetchall()

    def get_random_quotes(self, count: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, book, quote FROM quotes
                    ORDER BY shown_count ASC, RANDOM()
                    LIMIT %s
                    """,
                    (count,)
                )
                return cur.fetchall()

    def mark_shown(self, quote_id: int):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE quotes SET shown_count = shown_count + 1 WHERE id = %s",
                    (quote_id,)
                )
            conn.commit()

    def get_stats(self):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM quotes")
                total = cur.fetchone()[0]
                cur.execute("SELECT COUNT(DISTINCT book) FROM quotes")
                books = cur.fetchone()[0]
                cur.execute("SELECT COALESCE(SUM(shown_count), 0) FROM quotes")
                shown = cur.fetchone()[0]
                return {"total": total, "books": books, "shown": shown}

    def set_setting(self, key: str, value: str):
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s",
                    (key, value, value)
                )
            conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        with self._conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM settings WHERE key = %s", (key,))
                row = cur.fetchone()
                return row[0] if row else default
