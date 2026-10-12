import asyncio
import os
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from google import genai

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_KEY)

@dp.message(CommandStart())
async def start_handler(message: types.Message):
    await message.answer("Привет! Я Gemini 3.8 AI. Готов к общению в чате!")

@dp.message()
async def chat_handler(message: types.Message):
    if not message.text:
        return
    
    bot_info = await bot.get_me()
    is_group = message.chat.type in ["group", "supergroup"]
    is_reply_to_bot = bool(message.reply_to_message and message.reply_to_message.from_user.id == bot_info.id)
    is_mentioned = bool(bot_info.username and bot_info.username.lower() in message.text.lower())

    # В группе отвечает только если тегнули или ответили реплаем
    if is_group and not (is_reply_to_bot or is_mentioned):
        return

    prompt = message.text.replace(f"@{bot_info.username}", "").strip()
    if not prompt:
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        await message.reply(response.text)
    except Exception as e:
        await message.reply(f"Ошибка ИИ: {e}")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
