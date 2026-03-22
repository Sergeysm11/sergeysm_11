import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

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

class Settings(StatesGroup):
    waiting_for_count = State()
    waiting_for_schedule = State()


# ─── КЛАВИАТУРЫ ─────────────────────────────────────────────────────────────

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Добавить книгу", callback_data="add_book")],
        [InlineKeyboardButton(text="📖 Мои книги", callback_data="my_books")],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton(text="📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton(text="✨ Цитата дня", callback_data="send_now")],
    ])

async def settings_menu():
    count = await db.get_setting("send_count", "5")
    mode = await db.get_setting("send_mode", "schedule")
    hour = await db.get_setting("send_hour", "9")
    minute = await db.get_setting("send_minute", "0")
    mode_label = f"📅 {'равномерно весь день' if mode == 'spread' else f'в {int(hour):02d}:{int(minute):02d} МСК'}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🔢 Цитат в день: {count}", callback_data="set_count")],
        [InlineKeyboardButton(text=mode_label, callback_data="set_mode")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
    ])

def count_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="3", callback_data="count_3"),
            InlineKeyboardButton(text="5", callback_data="count_5"),
            InlineKeyboardButton(text="7", callback_data="count_7"),
        ],
        [
            InlineKeyboardButton(text="10", callback_data="count_10"),
            InlineKeyboardButton(text="15", callback_data="count_15"),
            InlineKeyboardButton(text="✏️ Своё", callback_data="count_custom"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings")],
    ])

def mode_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🕐 В одно время", callback_data="mode_schedule")],
        [InlineKeyboardButton(text="🌅 Равномерно весь день", callback_data="mode_spread")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="settings")],
    ])

def back_to_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
    ])


# ─── ГЛАВНОЕ МЕНЮ ───────────────────────────────────────────────────────────

async def show_main_menu(target, edit=False):
    stats = await db.get_stats()
    text = (
        "📚 Бот для интервального повторения цитат\n\n"
        f"Книг: {stats['books']}  |  Цитат: {stats['total']}"
    )
    if edit:
        await target.message.edit_text(text, reply_markup=main_menu())
    else:
        await target.answer(text, reply_markup=main_menu())


@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.clear()
    await show_main_menu(message)


@dp.message(Command("add"))
async def cmd_add_shortcut(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    await state.set_state(AddQuotes.waiting_for_book)
    await message.answer(
        "📖 Введи название книги:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
        ])
    )


@dp.message(Command("stats"))
async def cmd_stats_shortcut(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    stats = await db.get_stats()
    count = await db.get_setting("send_count", "5")
    mode = await db.get_setting("send_mode", "schedule")
    hour = await db.get_setting("send_hour", "9")
    minute = await db.get_setting("send_minute", "0")
    mode_text = "равномерно весь день" if mode == "spread" else f"в {int(hour):02d}:{int(minute):02d} МСК"
    await message.answer(
        f"📊 Статистика\n\n"
        f"📚 Книг: {stats['books']}\n"
        f"💬 Цитат: {stats['total']}\n"
        f"👁 Показов всего: {stats['shown']}\n\n"
        f"⚙️ Цитат в день: {count}\n"
        f"🕐 Режим: {mode_text}",
        reply_markup=back_to_menu()
    )


@dp.callback_query(F.data == "main_menu")
async def cb_main_menu(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_main_menu(cb, edit=True)
    await cb.answer()


# ─── ДОБАВИТЬ КНИГУ ─────────────────────────────────────────────────────────

@dp.callback_query(F.data == "add_book")
async def cb_add_book(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddQuotes.waiting_for_book)
    await cb.message.edit_text(
        "📖 Введи название книги:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
        ])
    )
    await cb.answer()


@dp.message(AddQuotes.waiting_for_book)
async def got_book_name(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    book = message.text.strip()
    await state.update_data(book=book)
    await state.set_state(AddQuotes.waiting_for_quotes)
    await message.answer(
        f"Книга: «{book}»\n\n"
        "Теперь отправь цитаты.\n\n"
        "Каждая строка — отдельная цитата.\n"
        "Или разделяй пустой строкой, если цитата многострочная.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="main_menu")]
        ])
    )


@dp.message(AddQuotes.waiting_for_quotes)
async def got_quotes(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    data = await state.get_data()
    book = data["book"]
    text = message.text.strip()

    if "\n\n" in text:
        lines = [b.strip() for b in text.split("\n\n") if b.strip()]
    else:
        lines = [l.strip() for l in text.split("\n") if l.strip()]

    for quote in lines:
        await db.add_quote(book, quote)

    await state.clear()
    stats = await db.get_stats()

    if stats["total"] == len(lines):
        await message.answer(
            f"Добавлено {len(lines)} цитат из книги «{book}»\n\n"
            "Это твоя первая книга! Сколько цитат присылать в день?",
            reply_markup=count_menu()
        )
    else:
        await message.answer(
            f"Добавлено {len(lines)} цитат из книги «{book}»\n\n"
            f"Всего в базе: {stats['total']} цитат из {stats['books']} книг",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📚 Добавить ещё книгу", callback_data="add_book")],
                [InlineKeyboardButton(text="◀️ В меню", callback_data="main_menu")],
            ])
        )


# ─── МОИ КНИГИ ──────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "my_books")
async def cb_my_books(cb: CallbackQuery):
    books = await db.get_books()
    if not books:
        await cb.message.edit_text(
            "База пуста. Добавь первую книгу!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📚 Добавить книгу", callback_data="add_book")],
                [InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu")],
            ])
        )
    else:
        text = "📚 Книги в базе:\n\n"
        for row in books:
            text += f"• {row['book']} — {row['cnt']} цит.\n"
        await cb.message.edit_text(text, reply_markup=back_to_menu())
    await cb.answer()


# ─── СТАТИСТИКА ─────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "stats")
async def cb_stats(cb: CallbackQuery):
    stats = await db.get_stats()
    count = await db.get_setting("send_count", "5")
    mode = await db.get_setting("send_mode", "schedule")
    hour = await db.get_setting("send_hour", "9")
    minute = await db.get_setting("send_minute", "0")
    mode_text = "равномерно весь день" if mode == "spread" else f"в {int(hour):02d}:{int(minute):02d} МСК"
    await cb.message.edit_text(
        f"📊 Статистика\n\n"
        f"📚 Книг: {stats['books']}\n"
        f"💬 Цитат: {stats['total']}\n"
        f"👁 Показов всего: {stats['shown']}\n\n"
        f"⚙️ Цитат в день: {count}\n"
        f"🕐 Режим: {mode_text}",
        reply_markup=back_to_menu()
    )
    await cb.answer()


# ─── НАСТРОЙКИ ──────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "settings")
async def cb_settings(cb: CallbackQuery):
    await cb.message.edit_text("⚙️ Настройки", reply_markup=await settings_menu())
    await cb.answer()


@dp.callback_query(F.data == "set_count")
async def cb_set_count(cb: CallbackQuery):
    await cb.message.edit_text("Сколько цитат присылать в день?", reply_markup=count_menu())
    await cb.answer()


@dp.callback_query(F.data.startswith("count_") & ~F.data.endswith("custom"))
async def cb_count_preset(cb: CallbackQuery):
    count = int(cb.data.split("_")[1])
    await db.set_setting("send_count", str(count))
    await reschedule_all()
    await cb.message.edit_text(
        f"Будет приходить {count} цитат в день.",
        reply_markup=back_to_menu()
    )
    await cb.answer()


@dp.callback_query(F.data == "count_custom")
async def cb_count_custom(cb: CallbackQuery, state: FSMContext):
    await state.set_state(Settings.waiting_for_count)
    await cb.message.edit_text(
        "Введи число от 1 до 50:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="settings")]
        ])
    )
    await cb.answer()


@dp.message(Settings.waiting_for_count)
async def got_custom_count(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    if not message.text.isdigit() or not (1 <= int(message.text) <= 50):
        await message.answer("Введи число от 1 до 50:")
        return
    count = int(message.text)
    await db.set_setting("send_count", str(count))
    await reschedule_all()
    await state.clear()
    await message.answer(f"Будет приходить {count} цитат в день.", reply_markup=back_to_menu())


@dp.callback_query(F.data == "set_mode")
async def cb_set_mode(cb: CallbackQuery):
    await cb.message.edit_text(
        "Как присылать цитаты?\n\n"
        "🕐 В одно время — все цитаты сразу в заданный час\n"
        "🌅 Равномерно весь день — по одной цитате с 8:00 до 22:00",
        reply_markup=mode_menu()
    )
    await cb.answer()


@dp.callback_query(F.data == "mode_schedule")
async def cb_mode_schedule(cb: CallbackQuery, state: FSMContext):
    await db.set_setting("send_mode", "schedule")
    await state.set_state(Settings.waiting_for_schedule)
    await cb.message.edit_text(
        "В какое время присылать?\nВведи время в формате ЧЧ:ММ (МСК)\n\nНапример: 09:00",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="settings")]
        ])
    )
    await cb.answer()


@dp.message(Settings.waiting_for_schedule)
async def got_schedule_time(message: Message, state: FSMContext):
    if message.from_user.id != OWNER_ID:
        return
    try:
        parts = message.text.strip().split(":")
        hour, minute = int(parts[0]), int(parts[1])
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except Exception:
        await message.answer("Неверный формат. Введи время как ЧЧ:ММ, например 09:00")
        return
    await db.set_setting("send_hour", str(hour))
    await db.set_setting("send_minute", str(minute))
    await reschedule_all()
    await state.clear()
    await message.answer(
        f"Все цитаты будут приходить в {hour:02d}:{minute:02d} МСК.",
        reply_markup=back_to_menu()
    )


@dp.callback_query(F.data == "mode_spread")
async def cb_mode_spread(cb: CallbackQuery):
    await db.set_setting("send_mode", "spread")
    await reschedule_all()
    await cb.message.edit_text(
        "Цитаты будут приходить равномерно с 8:00 до 22:00.",
        reply_markup=back_to_menu()
    )
    await cb.answer()


# ─── ЦИТАТА ДНЯ ─────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "send_now")
async def cb_send_now(cb: CallbackQuery):
    await cb.answer("Отправляю...")
    await send_single()


# ─── ФОРМАТИРОВАНИЕ И ОТПРАВКА ──────────────────────────────────────────────

def format_quote(book: str, quote: str) -> str:
    clean = quote.strip().strip('«»""\'\'')
    return f"«{clean}»\n\n— <b>{book}</b>"


async def send_batch():
    count = int(await db.get_setting("send_count", "5"))
    quotes = await db.get_random_quotes(count)
    if not quotes:
        await bot.send_message(OWNER_ID, "База пуста.", reply_markup=main_menu())
        return
    for i, row in enumerate(quotes, 1):
        await bot.send_message(OWNER_ID, format_quote(row["book"], row["quote"]), parse_mode="HTML")
        await db.mark_shown(row["id"])
        if i < len(quotes):
            await asyncio.sleep(0.3)


async def send_single():
    quotes = await db.get_random_quotes(1)
    if not quotes:
        await bot.send_message(OWNER_ID, "База пуста. Добавь цитаты через /add")
        return
    row = quotes[0]
    await bot.send_message(OWNER_ID, format_quote(row["book"], row["quote"]), parse_mode="HTML")
    await db.mark_shown(row["id"])


# ─── ПЛАНИРОВЩИК ────────────────────────────────────────────────────────────

async def reschedule_all():
    for job_id in ["daily_batch"] + [f"spread_{i}" for i in range(15)]:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    mode = await db.get_setting("send_mode", "schedule")
    count = int(await db.get_setting("send_count", "5"))

    if mode == "schedule":
        hour = int(await db.get_setting("send_hour", "9"))
        minute = int(await db.get_setting("send_minute", "0"))
        scheduler.add_job(send_batch, CronTrigger(hour=hour, minute=minute), id="daily_batch")
    elif mode == "spread":
        if count > 0:
            interval = 840 // count
            for i in range(count):
                total_minutes = 8 * 60 + i * interval
                h = total_minutes // 60
                m = total_minutes % 60
                scheduler.add_job(send_single, CronTrigger(hour=h, minute=m), id=f"spread_{i}")


async def main():
    await db.init()
    await reschedule_all()
    scheduler.start()
    logger.info("Бот запущен.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
