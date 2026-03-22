import asyncio
import logging
import random
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import BOT_TOKEN, OWNER_ID
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
db = Database()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


# ─── КОМАНДЫ ────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await message.answer(
        "📚 Бот для интервального повторения цитат из книг\n\n"
        "Команды:\n"
        "/add Книга | Цитата — добавить цитату\n"
        "/list — список книг\n"
        "/quotes Название — цитаты из книги\n"
        "/delete 42 — удалить цитату по ID\n"
        "/send — получить случайные цитаты прямо сейчас\n"
        "/schedule 09:00 5 — настроить расписание\n"
        "/status — текущие настройки\n"
        "/stats — статистика базы"
    )


@dp.message(Command("add"))
async def cmd_add(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    args = message.text[4:].strip()
    if "|" not in args:
        await message.answer(
            "❌ Формат: /add Название книги | Текст цитаты\n\n"
            "Пример:\n/add Атомные привычки | Каждый день 1% лучше — это 37 раз лучше за год.",
            parse_mode=None
        )
        return

    parts = args.split("|", 1)
    book = parts[0].strip()
    quote = parts[1].strip()

    if not book or not quote:
        await message.answer("❌ Книга и цитата не могут быть пустыми.")
        return

    quote_id = db.add_quote(book, quote)
    total = db.get_stats()["total"]
    await message.answer(
        f"✅ Цитата добавлена (ID: {quote_id})\n"
        f"📖 <b>{book}</b>\n\n"
        f"<i>{quote}</i>\n\n"
        f"Всего цитат в базе: {total}",
        parse_mode="HTML"
    )


@dp.message(Command("bulk"))
async def cmd_bulk(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    # Убираем команду /bulk из текста
    text = message.text[5:].strip()

    if not text:
        await message.answer(
            "❌ Формат:\n\n"
            "/bulk\n"
            "Название книги\n"
            "Первая цитата\n"
            "Вторая цитата\n"
            "Третья цитата\n\n"
            "Другая книга\n"
            "Цитата из другой книги\n\n"
            "Пустая строка между книгами обязательна."
        )
        return

    # Разбиваем на блоки по пустой строке
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]

    total_added = 0
    report = []

    for block in blocks:
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 2:
            continue

        book = lines[0]
        quotes = lines[1:]
        added = 0

        for quote in quotes:
            if quote:
                db.add_quote(book, quote)
                added += 1
                total_added += 1

        report.append(f"📖 {book} — {added} цит.")

    if total_added == 0:
        await message.answer("❌ Не удалось распознать цитаты. Проверь формат.")
        return

    stats = db.get_stats()
    report_text = "\n".join(report)
    await message.answer(
        f"✅ Добавлено {total_added} цитат\n\n"
        f"{report_text}\n\n"
        f"Всего в базе: {stats['total']}"
    )


@dp.message(Command("list"))
async def cmd_list(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    books = db.get_books()
    if not books:
        await message.answer("📭 База пуста. Добавь цитаты командой /add")
        return

    text = "📚 <b>Книги в базе:</b>\n\n"
    for book, count in books:
        text += f"• {book} — {count} цит.\n"

    await message.answer(text, parse_mode="HTML")


@dp.message(Command("quotes"))
async def cmd_quotes(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    book = message.text[7:].strip()
    if not book:
        await message.answer("❌ Укажи название книги: /quotes Атомные привычки")
        return

    quotes = db.get_quotes_by_book(book)
    if not quotes:
        await message.answer(f"❌ Книга «{book}» не найдена.")
        return

    text = f"📖 <b>{book}</b> ({len(quotes)} цит.)\n\n"
    for q_id, q_text in quotes:
        short = q_text[:120] + "..." if len(q_text) > 120 else q_text
        text += f"<code>ID {q_id}</code>: {short}\n\n"

    # Telegram лимит 4096 символов
    if len(text) > 4000:
        text = text[:4000] + "\n\n... (показаны первые записи)"

    await message.answer(text, parse_mode="HTML")


@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    args = message.text[7:].strip()
    if not args.isdigit():
        await message.answer("❌ Укажи числовой ID: /delete 42")
        return

    quote_id = int(args)
    success = db.delete_quote(quote_id)
    if success:
        await message.answer(f"🗑 Цитата ID {quote_id} удалена.")
    else:
        await message.answer(f"❌ Цитата с ID {quote_id} не найдена.")


@dp.message(Command("send"))
async def cmd_send(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await send_daily_quotes(manual=True)
    await message.answer("✅ Цитаты отправлены!")


@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    args = message.text[9:].strip().split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer(
            "❌ Формат: /schedule ЧЧ:ММ количество\n\n"
            "Пример: /schedule 09:00 5\n"
            "Пример: /schedule 18:30 10"
        )
        return

    time_str = args[0]
    count = int(args[1])

    try:
        time_parts = time_str.split(":")
        hour = int(time_parts[0])
        minute = int(time_parts[1])
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except Exception:
        await message.answer("❌ Неверный формат времени. Используй ЧЧ:ММ, например 09:00")
        return

    if count < 1 or count > 50:
        await message.answer("❌ Количество цитат должно быть от 1 до 50.")
        return

    db.set_setting("send_hour", str(hour))
    db.set_setting("send_minute", str(minute))
    db.set_setting("send_count", str(count))

    # Пересоздаём задачу планировщика
    reschedule_job(hour, minute)

    await message.answer(
        f"✅ Расписание обновлено\n\n"
        f"🕐 Время: {time_str} (МСК)\n"
        f"📝 Цитат за раз: {count}"
    )


@dp.message(Command("status"))
async def cmd_status(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    hour = db.get_setting("send_hour", "9")
    minute = db.get_setting("send_minute", "0")
    count = db.get_setting("send_count", "5")
    stats = db.get_stats()

    await message.answer(
        f"⚙️ <b>Текущие настройки</b>\n\n"
        f"🕐 Время рассылки: {int(hour):02d}:{int(minute):02d} МСК\n"
        f"📝 Цитат за раз: {count}\n"
        f"📚 Книг в базе: {stats['books']}\n"
        f"💬 Цитат в базе: {stats['total']}",
        parse_mode="HTML"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    stats = db.get_stats()
    await message.answer(
        f"📊 <b>Статистика</b>\n\n"
        f"📚 Книг: {stats['books']}\n"
        f"💬 Цитат: {stats['total']}\n"
        f"📅 Показов всего: {stats['shown']}",
        parse_mode="HTML"
    )


# ─── ОТПРАВКА ЦИТАТ ─────────────────────────────────────────────────────────

async def send_daily_quotes(manual=False):
    count = int(db.get_setting("send_count", "5"))
    quotes = db.get_random_quotes(count)

    if not quotes:
        if manual:
            await bot.send_message(OWNER_ID, "📭 База цитат пуста.")
        return

    if not manual:
        now = datetime.now().strftime("%d.%m.%Y")
        header = await bot.send_message(
            OWNER_ID,
            f"☀️ <b>Цитаты на {now}</b> — {len(quotes)} шт.",
            parse_mode="HTML"
        )

    for i, (q_id, book, quote) in enumerate(quotes, 1):
        text = f"📖 <b>{book}</b>\n\n<i>{quote}</i>"
        await bot.send_message(OWNER_ID, text, parse_mode="HTML")
        db.mark_shown(q_id)
        if i < len(quotes):
            await asyncio.sleep(0.3)


# ─── ПЛАНИРОВЩИК ────────────────────────────────────────────────────────────

def reschedule_job(hour: int, minute: int):
    if scheduler.get_job("daily_quotes"):
        scheduler.remove_job("daily_quotes")
    scheduler.add_job(
        send_daily_quotes,
        CronTrigger(hour=hour, minute=minute),
        id="daily_quotes"
    )


async def main():
    db.init()

    hour = int(db.get_setting("send_hour", "9"))
    minute = int(db.get_setting("send_minute", "0"))
    reschedule_job(hour, minute)
    scheduler.start()

    logger.info(f"Бот запущен. Рассылка в {hour:02d}:{minute:02d} МСК")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
