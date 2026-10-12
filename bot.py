import os
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from google import genai

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_KEY)

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    await message.answer("Привет! Я Gemini 3.8 AI на связи и готов к работе. Напиши мне любой вопрос.")

@dp.message()
async def handle_message(message: types.Message):
    if not message.text:
        return
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        response = ai_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=message.text
        )
        await message.answer(response.text or "Пустой ответ.")
    except Exception as e:
        await message.answer(f"Ошибка при обращении к нейросети: {e}")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is running!"))
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
