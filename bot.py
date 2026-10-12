import os
import io
import asyncio
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from google import genai
from google.genai import types as genai_types

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_KEY)

# ----------------- НАСТРОЙКА РОЛИ И ИНСТРУМЕНТОВ -----------------
SYSTEM_PROMPT = """
Ты — умный, дружелюбный и харизматичный ИИ-помощник чата жителей Бреста.
Твой стиль общения: теплый, живой, грамотный, с легким уместным юмором, без занудства и канцелярита.
Ты отлично знаешь историю, географию, культуру и атмосферу города Бреста (Беларусь).
Ты умеешь детально анализировать фотографии, отвечать на сложные интеллектуальные вопросы (в стиле ЧГК) и помогать участникам с практическими советами.
Отвечай емко, по делу и дружелюбно, избегая роботизированных шаблонов.
"""

config = genai_types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[{"google_search": {}}]
)
# -----------------------------------------------------------------

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    await message.answer("Привет! Я Gemini 3.8 AI на связи. Задавай вопросы, присылай фото или проверяй меня на эрудицию!")

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    prompt = message.caption or "Опиши подробно, что изображено на этом фото."
    try:
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        image_bytes = file_io.getvalue()

        response = ai_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                prompt
            ],
            config=config
        )
        await message.answer(response.text or "Пустой ответ.")
    except Exception as e:
        await message.answer(f"Ошибка при анализе фото: {e}")

@dp.message(F.text)
async def handle_text(message: types.Message):
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        response = ai_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=message.text,
            config=config
        )
        await message.answer(response.text or "Пустой ответ.")
    except Exception as e:
        await message.answer(f"Ошибка: {e}")

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
