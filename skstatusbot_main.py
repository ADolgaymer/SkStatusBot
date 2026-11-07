import asyncio
import logging
import sys
import os
import pandas as pd
from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message

# 1. Конфигурация
TOKEN = os.getenv("BOT_TOKEN")
EXCEL_FILE = "sk_register.xlsx"

# 2. Загрузка данных (при запуске)
try:
    df = pd.read_excel(EXCEL_FILE, dtype={'inn': str})
    df['inn'] = df['inn'].str.replace(r'[^0-9]', '', regex=True)
    logging.info(f"Успешно загружено {len(df)} записей")
except Exception as e:
    logging.error(f"Ошибка загрузки Excel: {e}")
    df = pd.DataFrame()

dp = Dispatcher()

# 3. Обработчик /start
@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Добрый день, {html.bold(message.from_user.full_name)}! Укажите ИНН компании")

# 4. Обработчик ИНН
@dp.message()
async def handle_inn(message: Message) -> None:
    user_input = message.text.strip()
    if not user_input.isdigit() or len(user_input) not in [10]:
        await message.answer("Введите корректный ИНН (10 цифр)")
        return
    
    result = df[df['inn'] == user_input] if not df.empty else pd.DataFrame()
    if result.empty:
        await message.answer(f"Компния с ИНН {user_input} не найдена в реестре участников проекта Сколково")
    else:
        row = result.iloc[0]
        # Предполагается, что в Excel есть эти столбцы, при необходимости измените названия
        await message.answer(
            f"✅ Найдено:\n"
            f"Участник: {row.get('company', 'Не указано')}\n"
            f"Проект: {row.get('project', 'Не указано')}\n"
            f"Дата присвоения статуса: {row.get('status_date', 'Не указано')}"
        )

# 5. Запуск
async def main() -> None:
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())