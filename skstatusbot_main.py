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
# user_states[user_id] = {"stage": None | "awaiting_historical" | "awaiting_after_notfound", "last_inn": str}
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
        f"Проект: {row.get('project', 'Не указано')}\n"
        f"Дата присвоения статуса: {status_date}"
    )

async def farewell_and_reset(chat_id: int, bot: Bot):
    await bot.send_message(
        chat_id,
        "Всего доброго! Если у вас есть вопросы, касающиеся участия в проекте Сколково, "
        "напишите в чат @innolexpro."
    )
    await asyncio.sleep(10)
    await bot.send_message(
        chat_id,
        "Чтобы проверить, является ли компания участником Сколково, укажите ее ИНН (10 цифр)"
    )

# 6. Обработчик /start
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    user_states.pop(message.from_user.id, None)
    await message.answer(
        f"Добрый день, {html.bold(message.from_user.full_name)}! "
        f"Чтобы проверить, является ли компания участником Сколково, укажите ее ИНН (10 цифр)"
    )

# 7. Обработчик ИНН (текстовые сообщения)
@dp.message()
async def handle_inn(message: Message) -> None:
    user_id = message.from_user.id
    state = user_states.get(user_id, {"stage": None, "last_inn": None})

    # Если ждём ответа на кнопки — текстовый ввод игнорируем
    if state["stage"] in ("awaiting_historical", "awaiting_after_notfound"):
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
        await message.answer(format_row(row))
        user_states.pop(user_id, None)
        return

    # Не найдено в актуальном реестре
    user_states[user_id] = {"stage": "awaiting_historical", "last_inn": user_input}
    await message.answer(
        f"Компания с ИНН {user_input} не является участником проекта Сколково.\n\n"
        f"Хотите ли вы проверить, была ли компания в прошлом участником Сколково?",
        reply_markup=kb_yes_no()
    )

# 8. Обработчик inline-кнопок
@dp.callback_query()
async def handle_callback(callback: CallbackQuery, bot: Bot) -> None:
    user_id = callback.from_user.id
    state = user_states.get(user_id, {"stage": None, "last_inn": None})
    data = callback.data

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
                f"Компания с ИНН {last_inn} не найдена и в историческом реестре участников Сколково.\n\n"
                f"Хотите проверить другую компанию или завершить?",
                reply_markup=kb_other_or_finish()
            )
        await callback.answer()
        return

    if data == "hist_no" and state["stage"] == "awaiting_historical":
        user_states.pop(user_id, None)
        await callback.answer()
        await farewell_and_reset(callback.message.chat.id, bot)
        return

    # --- Ответ после "не найдена в истории" ---
    if data == "check_another" and state["stage"] == "awaiting_after_notfound":
        user_states.pop(user_id, None)
        await callback.answer()
        await callback.message.answer(
            "Укажите ИНН компании для проверки (10 цифр)"
        )
        return

    if data == "finish" and state["stage"] == "awaiting_after_notfound":
        user_states.pop(user_id, None)
        await callback.answer()
        await farewell_and_reset(callback.message.chat.id, bot)
        return

    await callback.answer("Кнопка неактуальна. Введите ИНН заново.")

# 9. Запуск
async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())