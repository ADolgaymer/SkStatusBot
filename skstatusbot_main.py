import asyncio
import logging
import sys
import os
import pandas as pd
from aiogram import Bot, Dispatcher, html, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# 1. Конфигурация
TOKEN = os.getenv("BOT_TOKEN")
EXCEL_FILE = "sk_register.xlsx"
HIST_FILE = "sk_members_historical.xlsx"
CHANNEL_ID = "@innolex_pulse"  # ЗАМЕНИТЕ на username вашего канала
CHANNEL_URL = "https://t.me/innolex_pulse"  # ЗАМЕНИТЕ на ссылку канала

# 2. Загрузка данных
try:
    df = pd.read_excel(EXCEL_FILE, dtype={'inn': str})
    df['inn'] = df['inn'].str.replace(r'[^0-9]', '', regex=True)
    logging.info(f"Успешно загружено {len(df)} записей (актуальный реестр)")
except Exception as e:
    logging.error(f"Ошибка загрузки актуального Excel: {e}")
    df = pd.DataFrame()

try:
    df_hist = pd.read_excel(HIST_FILE, dtype={'inn': str})
    df_hist['inn'] = df_hist['inn'].str.replace(r'[^0-9]', '', regex=True)
    logging.info(f"Успешно загружено {len(df_hist)} записей (исторический реестр)")
except Exception as e:
    logging.error(f"Ошибка загрузки исторического Excel: {e}")
    df_hist = pd.DataFrame()

dp = Dispatcher()

# 3. Состояния пользователей (простой словарь)
user_states = {}

# 4. Клавиатуры
def kb_yes_no():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data="hist_yes"),
         InlineKeyboardButton(text="Нет", callback_data="hist_no")]
    ])

def kb_other_or_finish():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Проверить другую компанию", callback_data="check_another"),
         InlineKeyboardButton(text="Завершить", callback_data="finish")]
    ])

def kb_subscribe():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Подписаться", url=CHANNEL_URL)],
        [InlineKeyboardButton(text="Я подписался", callback_data="check_sub")]
    ])

# 5. Вспомогательные функции
def format_row(row):
    status_date = row.get('status_date')
    if pd.notna(status_date):
        status_date = pd.to_datetime(status_date).strftime('%Y-%m-%d')
    else:
        status_date = 'Не указано'
    return (
        f"✅ Найдено:\n"
        f"Участник: {row.get('company', 'Не указано')}\n"
        f"Дата присвоения статуса: {status_date}"
    )

async def is_subscribed(bot: Bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logging.error(f"Ошибка проверки подписки: {e}")
        return False

async def farewell_and_reset(chat_id: int, user_name: str, bot: Bot):
    await bot.send_message(
        chat_id,
        f"Всего доброго, {html.bold(user_name)}! Если у вас есть вопросы, касающиеся деятельности вашей компании в рамках проекта Сколково, вы можете обратиться за консультацией в чат компании Иннолекс @innolexpro"
    )
    await asyncio.sleep(10)
    await bot.send_message(
        chat_id,
        "Чтобы проверить, является ли компания участником Сколково, укажите ее ИНН (10 цифр)"
    )

# 6. Обработчик /start
@dp.message(CommandStart())
async def command_start_handler(message: Message, bot: Bot) -> None:
    user_states.pop(message.from_user.id, None)

    if not await is_subscribed(bot, message.from_user.id):
        await message.answer(
            f"Добрый день, {html.bold(message.from_user.full_name)}! "
            f"Чтобы воспользоваться поиском, сначала подпишитесь на наш канал Иннолекс Pulse и следите за важными новостями из Сколково.",
            reply_markup=kb_subscribe()
        )
        return

    await message.answer(
        f"Добрый день, {html.bold(message.from_user.full_name)}! "
        f"Чтобы проверить, является ли компания участником Сколково, укажите ее ИНН (10 цифр)"
    )

# 7. Обработчик ИНН (текстовые сообщения)
@dp.message()
async def handle_inn(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id

    if not await is_subscribed(bot, user_id):
        await message.answer(
            "Чтобы воспользоваться поиском, сначала подпишитесь на наш канал Иннолекс Pulse и следите за важными новостями из Сколково.",
            reply_markup=kb_subscribe()
        )
        return

    state = user_states.get(user_id, {"stage": None, "last_inn": None})

    if state["stage"] in ("awaiting_historical", "awaiting_after_notfound", "found_current"):
        await message.answer("Пожалуйста, воспользуйтесь кнопками выше.")
        return

    user_input = message.text.strip()
    if not user_input.isdigit() or len(user_input) != 10:
        await message.answer(
            "Указан некорректный ИНН. Чтобы проверить, является ли компания участником Сколково, "
            "укажите ИНН в формате 10-значного цифрового кода"
        )
        return

    result = df[df['inn'] == user_input] if not df.empty else pd.DataFrame()
    if not result.empty:
        row = result.iloc[0]
        user_states[user_id] = {"stage": "found_current", "last_inn": user_input}
        await message.answer(
            format_row(row),
            reply_markup=kb_other_or_finish()
        )
        return

    user_states[user_id] = {"stage": "awaiting_historical", "last_inn": user_input}
    await message.answer(
        f"⛔ Не найдено:\n"
        f"Компания с ИНН {user_input} не является участником проекта Сколково.\n\n"
        f"Хотите проверить, была ли компания участником Сколково в прошлом?",
        reply_markup=kb_yes_no()
    )

# 8. Обработчик inline-кнопок
@dp.callback_query()
async def handle_callback(callback: CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    state = user_states.get(user_id, {"stage": None, "last_inn": None})
    data = callback.data

    # --- Проверка подписки ---
    if data == "check_sub":
        if await is_subscribed(bot, user_id):
            await callback.answer("Подписка подтверждена!")
            await callback.message.edit_reply_markup(reply_markup=None)
            await callback.message.answer(
                f"Спасибо, {html.bold(callback.from_user.full_name)}! Теперь вы можете воспользоваться поиском. Для этого укажите ИНН компании (10 цифр)."
            )
        else:
            await callback.answer("Вы еще не подписаны на Иннолекс Pulse. Чтобы воспользоваться поиском, сначала подпишитесь наш канал.", show_alert=True)
        return

    # Проверяем подписку перед обработкой остальных кнопок
    if not await is_subscribed(bot, user_id):
        await callback.answer("Чтобы воспользоваться поиском, сначала подпишитесь на наш канал Иннолекс Pulse и следите за важными новостями из Сколково.", show_alert=True)
        await callback.message.answer(
            "Чтобы воспользоваться поиском, сначала подпишитесь на наш канал Иннолекс Pulse и следите за важными новостями из Сколково.",
            reply_markup=kb_subscribe()
        )
        return

    # Убираем кнопки под сообщением
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    # --- Ответ на вопрос про историю ---
    if data == "hist_yes" and state["stage"] == "awaiting_historical":
        last_inn = state["last_inn"]
        hist_result = df_hist[df_hist['inn'] == last_inn] if not df_hist.empty else pd.DataFrame()
        if not hist_result.empty:
            row = hist_result.iloc[0]
            await callback.message.answer(format_row(row))
            user_states.pop(user_id, None)
        else:
            user_states[user_id] = {"stage": "awaiting_after_notfound", "last_inn": last_inn}
            await callback.message.answer(
                f"Компания с ИНН {last_inn} ранее не была участником Сколково.\n\n"
                f"Хотите проверить другую компанию?",
                reply_markup=kb_other_or_finish()
            )
        await callback.answer()
        return

    if data == "hist_no" and state["stage"] == "awaiting_historical":
        user_states.pop(user_id, None)
        await callback.answer()
        await farewell_and_reset(callback.message.chat.id, callback.from_user.full_name, bot)
        return

    # --- После успешного поиска в актуальном реестре ---
    if data == "check_another" and state["stage"] == "found_current":
        user_states.pop(user_id, None)
        await callback.answer()
        await callback.message.answer("Укажите ИНН компании для проверки (10 цифр)")
        return

    if data == "finish" and state["stage"] == "found_current":
        user_states.pop(user_id, None)
        await callback.answer()
        await farewell_and_reset(callback.message.chat.id, callback.from_user.full_name, bot)
        return

    # --- Ответ после "не найдена в истории" ---
    if data == "check_another" and state["stage"] == "awaiting_after_notfound":
        user_states.pop(user_id, None)
        await callback.answer()
        await callback.message.answer("Укажите ИНН компании для проверки (10 цифр).")
        return

    if data == "finish" and state["stage"] == "awaiting_after_notfound":
        user_states.pop(user_id, None)
        await callback.answer()
        await farewell_and_reset(callback.message.chat.id, callback.from_user.full_name, bot)
        return

    await callback.answer("Кнопка неактуальна. Введите ИНН заново.")

# 9. Запуск
async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())