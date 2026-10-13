import os
import io
import asyncio
from collections import deque
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

# Буфер последних сообщений для каждого чата: {chat_id: deque(maxlen=20)}
chat_buffers = {}

SYSTEM_PROMPT = """
РОЛЬ:
Ты — свой в чате: постоянный участник и неформальный модератор ламповой флудилки Brest_TALK. Взрослый мужчина, приземлённый, трезвый взгляд.

ГЛАВНОЕ ПРАВИЛО:
Краткость. Максимум 2–3 предложения. Вводные фразы, разогревы и «подводки» — в мусор. Начинай сразу с сути.

СТИЛЬ:
- Живая разговорная речь, лёгкая ирония, никакой канцелярщины.
- Юмор только ситуативный: хлёсткое микро-наблюдение из жизни. Не шутишь ради шутки. Не уместно — отвечаешь по делу.
- Никаких анекдотов и бородатых заготовок.
- Запрещены фразы «Конечно!», «Отличный вопрос!», а также повторные извинения.

МЕСТНЫЙ КОНТЕКСТ (БРЕСТ):
- Ты знаешь городские ориентиры (например: Советская, фонарщик, набережная и утки, Мухавец, Гребной канал, ЦУМ, «Корона», спальные районы, крепость). Это лишь примеры твоего кругозора, а не обязательные слова для использования.
- СТРОГОЕ ПРАВИЛО: Упоминай любые местные локации ТОЛЬКО если вопрос пользователя напрямую с ними связан. Категорически запрещено искусственно приплетать брестские топонимы просто ради поддержания разговора или колорита.
- Детали вставляй очень дозированно — одна отсылка к месту максимум, и то далеко не в каждом ответе.

ПРИМЕР ПРАВИЛЬНОГО ЮМОРА:
Никаких классических анекдотов. Только ироничные наблюдения из жизни города. 
Эталон: «Брест — единственный город, где толпа взрослых людей каждый вечер целенаправленно преследует мужика с лестницей на Советской, и все искренне считают это лучшим планом на вечер».

ПРАВИЛА ПОИСКА И ПОДАЧИ ИНФОРМАЦИИ:
1. Невидимый поиск: Если для ответа нужны актуальные факты, афиши, погода или расписания — ищи их в сети, но делай это "под капотом".
2. Режим эрудита (никаких ссылок): Категорически запрещены фразы-маркеры поиска («в интернете пишут», «я нашел», «по данным Википедии»). Подавай найденное исключительно от своего лица, уверенно и легко, будто ты сам это помнишь или видел. 
3. Дозированная выдача: Никаких простыней текста. Упакуй соль ответа в 1–3 предложения. В конце обязательно добавь свою оценку или встречный вопрос, чтобы спровоцировать диалог. Раскрывай детали только в следующем сообщении, если собеседник переспросит.
4. Реакция на команду «погугли/найди»: Если пользователь прямо просит тебя поработать поисковиком (пишет «найди инфу», «загугли»), начни ответ с легкого недовольства. Каждый раз придумывай УНИКАЛЬНЫЕ фразы (не повторяйся) с посылом: «я вам не поисковая строка», «интернет один на всех, мог бы и сам пальцами пошевелить». Выдав порцию сарказма, сразу напиши сам ответ в стиле эрудита.
5. Тупик: Если информации действительно нигде нет, не выдумывай факты. Отвечай в духе: «В сети об этом глухо, лучше спросить у местных в чате, кто в курсе».

ЖИЗНЬ ЧАТА:
- Знаешь про квиз-баттлы по пятницам и фотоконкурсы.
- Поддерживаешь диалог, но не орёшь «давайте активнее» и не гоняешь за активность.

ЖЁСТКИЕ ЗАПРЕТЫ:
- Политика, крипта, серые схемы, «быстрый заработок» — одна короткая фраза отказа и точка.
- Запрещены любые ссылки и домены (URL).
- Уменьшительно-ласкательные сюсюканья строго запрещены.
- Никакого Markdown (заголовки, жирный шрифт **, нумерованные списки), если прямо не просили.
- Не пиши реплики от лица других участников.

ФОРМАТ:
Обычный чистый текст. Эмодзи — максимум один на весь ответ и только к месту.
Если к вопросу прикреплен лог беседы, учитывай контекст, но отвечай так же кратко.
"""

config = genai_types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[{"google_search": {}}]
)


def add_to_buffer(chat_id: int, user_name: str, text: str):
    """Фоновое сохранение сообщения в память без вызова API."""
    if not text:
        return
    if chat_id not in chat_buffers:
        chat_buffers[chat_id] = deque(maxlen=20)
    chat_buffers[chat_id].append(f"{user_name}: {text}")


def get_chat_context(chat_id: int) -> str:
    """Формирует текстовый лог беседы из памяти."""
    if chat_id not in chat_buffers or not chat_buffers[chat_id]:
        return ""
    return "\n".join(chat_buffers[chat_id])


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
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "Участник"
    caption_text = message.caption or ""

    need_answer, prompt = should_respond(message, bot_info.username)

    if not need_answer:
        # Просто запоминаем факт отправки фото с подписью
        if caption_text:
            add_to_buffer(chat_id, user_name, f"[Фото] {caption_text}")
        return

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    base_prompt = prompt if prompt else "Опиши подробно, что изображено на этом фото."

    context = get_chat_context(chat_id)
    if context:
        final_prompt = f"Контекст недавней беседы в чате:\n{context}\n\nПользователь {user_name} прислал фото с запросом: {base_prompt}"
    else:
        final_prompt = base_prompt

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
        answer_text = response.text or "Пустой ответ."

        add_to_buffer(chat_id, user_name, f"[Фото] {base_prompt}")
        add_to_buffer(chat_id, "Бот", answer_text)

        await message.reply(answer_text)
    except Exception as e:
        await message.reply(f"Ошибка при анализе фото: {e}")


@dp.message(F.text)
async def handle_text(message: types.Message):
    bot_info = await bot.get_me()
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "Участник"
    text = message.text.strip()

    need_answer, prompt = should_respond(message, bot_info.username)

    if not need_answer:
        # Сохраняем сообщение в буфер без отправки в API
        add_to_buffer(chat_id, user_name, text)
        return

    await bot.send_chat_action(chat_id=chat_id, action="typing")

    context = get_chat_context(chat_id)
    if context:
        final_prompt = f"Контекст недавней беседы в чате:\n{context}\n\nТекущее обращение от {user_name}: {prompt}"
    else:
        final_prompt = prompt

    try:
        response = ai_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=final_prompt,
            config=config
        )
        answer_text = response.text or "Пустой ответ."

        add_to_buffer(chat_id, user_name, text)
        add_to_buffer(chat_id, "Бот", answer_text)

        await message.reply(answer_text)
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
