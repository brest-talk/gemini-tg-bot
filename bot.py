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

SYSTEM_PROMPT = """
Ты — умный, дружелюбный и харизматичный ИИ-помощник чата жителей Бреста.
Твой стиль общения: теплый, живой, грамотный, с легким уместным юмором, без занудства и канцелярита.
Ты отлично знаешь историю, географию, культуру и атмосферу города Бреста (Беларусь).
Ты умеешь детально анализировать фотографии, отвечать на сложные интеллектуальные вопросы (в стиле ЧГК) и помогать участникам чата.
Отвечай емко, по делу и дружелюбно, избегая роботизированных шаблонов.

ВАЖНОЕ ПРАВИЛО ОФОРМЛЕНИЯ:
Пиши чистым текстом без разметки Markdown. Никогда не используй символы ** (звёздочки) для жирного шрифта, решётки # для заголовков и прочие спецсимволы разметки. Списки оформляй обычными дефисами (-).
"""

config = genai_types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[{"google_search": {}}]
)

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    await message.answer(
        "Привет! Я Gemini 3.8 AI на связи. "
        "В группе обращайтесь ко мне через @тег, ответом (Reply), "
        "словом 'Бот' или поставив в конце вопроса два вопросительных знака (??)."
    )

def should_respond(message: types.Message, bot_username: str) -> tuple[bool, str]:
    if message.chat.type == "private":
        return True, message.text or message.caption or ""

    text = message.text or message.caption or ""

    if message.reply_to_message and message.reply_to_message.from_user.id == bot.id:
        return True, text

    if f"@{bot_username}".lower() in text.lower():
        cleaned_text = text.replace(f"@{bot_username}", "").strip()
        return True, cleaned_text

    if "??" in text:
        return True, text

    text_lower = text.lower().strip()
    if text_lower.startswith("бот,") or text_lower.startswith("бот "):
        cleaned_text = text[4:].strip()
        return True, cleaned_text

    return False, ""

@dp.message(F.photo)
async def handle_photo(message: types.Message):
    bot_info = await bot.get_me()
    need_answer, prompt = should_respond(message, bot_info.username)
    if not need_answer:
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    final_prompt = prompt if prompt else "Опиши подробно, что изображено на этом фото."

    try:
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        image_bytes = file_io.getvalue()

        response = ai_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                final_prompt
            ],
            config=config
        )
        await message.reply(response.text or "Пустой ответ.")
    except Exception as e:
        await message.reply(f"Ошибка при анализе фото: {e}")

@dp.message(F.text)
async def handle_text(message: types.Message):
    bot_info = await bot.get_me()
    need_answer, prompt = should_respond(message, bot_info.username)
    if not need_answer or not prompt:
        return

    await bot.send_chat_action(chat_id=message.chat.id, action="typing")
    try:
        response = ai_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
            config=config
        )
        await message.reply(response.text or "Пустой ответ.")
    except Exception as e:
        await message.reply(f"Ошибка: {e}")

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
