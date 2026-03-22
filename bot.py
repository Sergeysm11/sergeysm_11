import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from config import BOT_TOKEN, OWNER_ID
from database import Database

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db = Database()
scheduler = AsyncIOScheduler(timezone="Europe/Moscow")


# ─── СОСТОЯНИЯ ──────────────────────────────────────────────────────────────

class AddQuotes(StatesGroup):
    waiting_for_book = State()
    waiting_for_quotes = State()


# ─── КОМАНДЫ ────────────────────────────────────────────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    stats = db.get_stats()
    await message.answer(
        "📚 Бот для интервального повторения цитат\n\n"
        f"В базе: {stats['books']} книг, {stats['total']} цитат\n\n"
        "Команды:\n"
        "/add — добавить цитаты из книги\n"
        "/list — список всех книг\n"
        "/quotes Название — цитаты из книги\n"
        "/delete 42 — удалить цитату по ID\n"
        "/send — получить цитаты прямо сейчас\n"
        "/schedule 09:00 5 — настроить время и количество\n"
        "/status — текущие настройки\n"
        "/stats — статистика"
    )


@dp.message(Command("add"))
async def cmd_add(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.set_state(AddQuotes.waiting_for_book)
    await message.answer("📖 Введи название книги:")


@dp.message(AddQuotes.waiting_for_book)
async def got_book_name(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    book = message.text.strip()
    await state.update_data(book=book)
    await state.set_state(AddQuotes.waiting_for_quotes)
    await message.answer(
        f"Книга: «{book}»\n\n"
        "Теперь отправь цитаты — каждая с новой строки:\n\n"
        "Первая цитата\n"
        "Вторая цитата\n"
        "Третья цитата"
    )


@dp.message(AddQuotes.waiting_for_quotes)
async def got_quotes(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return

    data = await state.get_data()
    book = data["book"]

    # Поддерживаем оба формата:
    # 1. Каждая строка = цитата
    # 2. Цитаты разделены пустой строкой (многострочные цитаты)
    text = message.text.strip()
    if "\n\n" in text:
        # Пустая строка = разделитель между цитатами
        lines = [b.strip() for b in text.split("\n\n") if b.strip()]
    else:
        # Каждая строка = отдельная цитата
        lines = [l.strip() for l in text.split("\n") if l.strip()]

    if not lines:
        await message.answer("Не получил ни одной цитаты. Попробуй ещё раз.")
        return

    for quote in lines:
        db.add_quote(book, quote)

    await state.clear()
    stats = db.get_stats()
    await message.answer(
        f"Добавлено {len(lines)} цитат из книги «{book}»\n\n"
        f"Всего в базе: {stats['total']} цитат из {stats['books']} книг\n\n"
        "Добавить ещё книгу — /add\n"
        "Получить цитаты сейчас — /send"
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.clear()
    await message.answer("Отменено.")


@dp.message(Command("list"))
async def cmd_list(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    books = db.get_books()
    if not books:
        await message.answer("База пуста. Добавь цитаты командой /add")
        return

    text = "Книги в базе:\n\n"
    for book, count in books:
        text += f"• {book} — {count} цит.\n"

    await message.answer(text)


@dp.message(Command("quotes"))
async def cmd_quotes(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    book = message.text[7:].strip()
    if not book:
        await message.answer("Укажи название книги: /quotes Атомные привычки")
        return

    quotes = db.get_quotes_by_book(book)
    if not quotes:
        await message.answer(f"Книга не найдена.")
        return

    text = f"{book} ({len(quotes)} цит.)\n\n"
    for q_id, q_text in quotes:
        short = q_text[:120] + "..." if len(q_text) > 120 else q_text
        text += f"ID {q_id}: {short}\n\n"

    if len(text) > 4000:
        text = text[:4000] + "\n\n... (показаны первые записи)"

    await message.answer(text)


@dp.message(Command("delete"))
async def cmd_delete(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    args = message.text[7:].strip()
    if not args.isdigit():
        await message.answer("Укажи числовой ID: /delete 42")
        return

    quote_id = int(args)
    success = db.delete_quote(quote_id)
    if success:
        await message.answer(f"Цитата ID {quote_id} удалена.")
    else:
        await message.answer(f"Цитата с ID {quote_id} не найдена.")


@dp.message(Command("send"))
async def cmd_send(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    await send_daily_quotes(manual=True)


@dp.message(Command("schedule"))
async def cmd_schedule(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    args = message.text[9:].strip().split()
    if len(args) != 2 or not args[1].isdigit():
        await message.answer(
            "Формат: /schedule ЧЧ:ММ количество\n\n"
            "Пример: /schedule 09:00 5"
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
        await message.answer("Неверный формат времени. Используй ЧЧ:ММ, например 09:00")
        return

    if count < 1 or count > 50:
        await message.answer("Количество цитат должно быть от 1 до 50.")
        return

    db.set_setting("send_hour", str(hour))
    db.set_setting("send_minute", str(minute))
    db.set_setting("send_count", str(count))

    reschedule_job(hour, minute)

    await message.answer(
        f"Расписание обновлено\n\n"
        f"Время: {time_str} МСК\n"
        f"Цитат за раз: {count}"
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
        f"Текущие настройки\n\n"
        f"Время рассылки: {int(hour):02d}:{int(minute):02d} МСК\n"
        f"Цитат за раз: {count}\n"
        f"Книг в базе: {stats['books']}\n"
        f"Цитат в базе: {stats['total']}"
    )


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    stats = db.get_stats()
    await message.answer(
        f"Статистика\n\n"
        f"Книг: {stats['books']}\n"
        f"Цитат: {stats['total']}\n"
        f"Показов всего: {stats['shown']}"
    )


# ─── ОТПРАВКА ЦИТАТ ─────────────────────────────────────────────────────────

async def send_daily_quotes(manual=False):
    count = int(db.get_setting("send_count", "5"))
    quotes = db.get_random_quotes(count)

    if not quotes:
        await bot.send_message(OWNER_ID, "База цитат пуста. Добавь цитаты через /add")
        return

    if not manual:
        now = datetime.now().strftime("%d.%m.%Y")
        await bot.send_message(OWNER_ID, f"Цитаты на {now} — {len(quotes)} шт.")

    for i, (q_id, book, quote) in enumerate(quotes, 1):
        await bot.send_message(OWNER_ID, f"📖 {book}\n\n{quote}")
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
