import os
import asyncpg


class Database:
    def __init__(self):
        self.url = os.getenv("DATABASE_URL")
        self.pool = None

    async def init(self):
        self.pool = await asyncpg.create_pool(self.url)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS quotes (
                    id SERIAL PRIMARY KEY,
                    book TEXT NOT NULL,
                    quote TEXT NOT NULL,
                    shown_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

    async def add_quote(self, book: str, quote: str) -> int:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO quotes (book, quote) VALUES ($1, $2) RETURNING id",
                book, quote
            )
            return row["id"]

    async def delete_quote(self, quote_id: int) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM quotes WHERE id = $1", quote_id)
            return result == "DELETE 1"

    async def get_books(self):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT book, COUNT(*) as cnt FROM quotes GROUP BY book ORDER BY cnt DESC"
            )

    async def get_quotes_by_book(self, book: str):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, quote FROM quotes WHERE book ILIKE $1 ORDER BY id",
                f"%{book}%"
            )

    async def get_random_quotes(self, count: int):
        async with self.pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, book, quote FROM quotes ORDER BY shown_count ASC, RANDOM() LIMIT $1",
                count
            )

    async def mark_shown(self, quote_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE quotes SET shown_count = shown_count + 1 WHERE id = $1",
                quote_id
            )

    async def get_stats(self):
        async with self.pool.acquire() as conn:
            total = await conn.fetchval("SELECT COUNT(*) FROM quotes")
            books = await conn.fetchval("SELECT COUNT(DISTINCT book) FROM quotes")
            shown = await conn.fetchval("SELECT COALESCE(SUM(shown_count), 0) FROM quotes")
            return {"total": total, "books": books, "shown": shown}

    async def set_setting(self, key: str, value: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value = $2",
                key, value
            )

    async def get_setting(self, key: str, default: str = "") -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT value FROM settings WHERE key = $1", key)
            return row["value"] if row else default
