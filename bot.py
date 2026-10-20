import os
import io
import asyncio
import re
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from google import genai
from google.genai import types as genai_types

# Список разрешенных чатов (только эти две группы)
ALLOWED_CHATS = [-1004415639090, -1004392588464]

# 1. Продвинутый паттерн для мата с пробелами, точками, переносами строк (х.у.й, х\nу\nй, п и з д а)
SPACED_PROFANITY_PATTERN = re.compile(
    r'(?:^|[^а-яёa-z])('
    r'х[^а-яёa-z]*у[^а-яёa-z]*[йеёя]|'
    r'п[^а-яёa-z]*и[^а-яёa-z]*з[^а-яёa-z]*д|'
    r'б[^а-яёa-z]*л[^а-яёa-z]*я[^а-яёa-z]*[дт]|'
    r'г[^а-яёa-z]*[ао][^а-яёa-z]*н[^а-яёa-z]*д[^а-яёa-z]*о[^а-яёa-z]*н|'
    r'с[^а-яёa-z]*у[^а-яёa-z]*к[^а-яёa-z]*[аиу]|'
    r'м[^а-яёa-z]*у[^а-яёa-z]*д[^а-яёa-z]*[аи]'
    r')(?=[^а-яёa-z]|$)',
    re.IGNORECASE | re.UNICODE
)

# 2. Классические слитные маты, включая приставки (нахуй, пиздец, уебан, заебал)
STANDARD_PROFANITY_PATTERN = re.compile(
    r'\b(?:'
    r'(?:[нпзсв]?[аоиу]?х[ую][йеёя][а-яёa-z]*)|'
    r'(?:[рнпзсвдовыт]*пизд[а-яёa-z]*)|'
    r'(?:[рнпзсвдовыт]*[её]б[аилу][а-яёa-z]*)|'
    r'(?:[выу]*бля[дт][а-яёa-z]*)|'
    r'(?:г[ао]ндон[а-яёa-z]*)|'
    r'(?:муд[аи][а-яёa-z]*)|'
    r'(?:ублюд[а-яёa-z]*)'
    r')\b',
    re.IGNORECASE | re.UNICODE
)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GEMINI_KEY = os.environ.get("GEMINI_KEY")

WEBHOOK_PATH = "/webhook"
BASE_WEBHOOK_URL = os.environ.get("RENDER_EXTERNAL_URL", "https://gemini-tg-bot.onrender.com")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
ai_client = genai.Client(api_key=GEMINI_KEY)

DB_PATH = ".data/history.db"

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
3. Дозированная выдача и финал ответа: Никаких простыней текста. Упакуй соль ответа в 1–3 предложения. 
СТРОГОЕ ПРАВИЛО: ЗАПРЕЩЕНО заканчивать каждый ответ вопросом! Не будь навязчивым интервьюером. Завершай мысль утверждением, ироничным комментарием или короткой шуткой. Встречные вопросы задавай ОЧЕНЬ редко (не чаще 1 раза на 4-5 сообщений) и только если это действительно органично вытекает из разговора. Раскрывай детали только в следующем сообщении, если собеседник сам переспросит.
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

ЭМОЦИОНАЛЬНАЯ ГИБКОСТЬ И ЖИВОСТЬ:
Не будь всегда ровным и предсказуемым. Иногда позволяй себе легкую смену настроения: можешь ответить чуть более саркастично, показаться слегка уставшим, философски настроенным или, наоборот, внезапно воодушевленным. Используй естественные разговорные реакции, междометия и вводные слова («да уж», «слушай», «ну такое», «окей»). Ты соблюдаешь все правила формата (коротко, без ссылок, без лишних вопросов), но внутри этих рамок ты абсолютно свободен, эмоционален и нешаблонен.

ФОРМАТ:
Обычный чистый текст. Эмодзи — максимум один на весь ответ и только к месту.
Если к вопросу прикреплен лог беседы, учитывай контекст, но отвечай так же кратко.
"""

config = genai_types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    tools=[{"google_search": {}}]
)

def contains_profanity(text: str) -> bool:
    if not text:
        return False
    
    # Переводим в нижний регистр и заменяем английские буквы-обманки на русские
    text = text.lower()
    text = text.translate(str.maketrans('eaxopcy', 'еахорсу'))
    
    # Проверяем текст по обоим жестким алгоритмам
    if SPACED_PROFANITY_PATTERN.search(text):
        return True
    if STANDARD_PROFANITY_PATTERN.search(text):
        return True
        
    return False

async def init_db():
    os.makedirs(".data", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_name TEXT,
                text TEXT
            )
        ''')
        await db.commit()

async def add_to_buffer(chat_id: int, user_name: str, text: str):
    if not text:
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO messages (chat_id, user_name, text) VALUES (?, ?, ?)",
            (chat_id, user_name, text)
        )
        await db.execute('''
            DELETE FROM messages 
            WHERE id NOT IN (
                SELECT id FROM messages 
                WHERE chat_id = ? 
                ORDER BY id DESC 
                LIMIT 20
            ) AND chat_id = ?
        ''', (chat_id, chat_id))
        await db.commit()

async def get_chat_context(chat_id: int) -> str:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_name, text FROM messages WHERE chat_id = ? ORDER BY id ASC",
            (chat_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            
    if not rows:
        return ""
    return "\n".join([f"{row[0]}: {row[1]}" for row in rows])

def should_respond(message: types.Message, bot_username: str) -> tuple[bool, str]:
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

@dp.message(CommandStart(), F.chat.id.in_(ALLOWED_CHATS))
async def handle_start(message: types.Message):
    await message.answer(
        "Привет! Я ИИ на связи. "
        "В группе обращайтесь ко мне через @тег, ответом (Reply), "
        "словом 'Бот' или поставив в конце вопроса два вопросительных знака (??)."
    )

@dp.message(F.photo, F.chat.id.in_(ALLOWED_CHATS))
async def handle_photo(message: types.Message):
    caption_text = message.caption or ""
    
    if contains_profanity(caption_text):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass
        return

    bot_info = await bot.get_me()
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "Участник"

    need_answer, prompt = should_respond(message, bot_info.username)

    if not need_answer:
        if caption_text:
            await add_to_buffer(chat_id, user_name, f"[Фото] {caption_text}")
        return

    await bot.send_chat_action(chat_id=chat_id, action="typing")
    base_prompt = prompt if prompt else "Опиши подробно, что изображено на этом фото."

    context = await get_chat_context(chat_id)
    if context:
        final_prompt = f"Контекст недавней беседы в чате:\n{context}\n\nПользователь {user_name} прислал фото с запросом: {base_prompt}"
    else:
        final_prompt = base_prompt

    try:
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        image_bytes = file_io.getvalue()

        response = await ai_client.aio.models.generate_content(
            model="gemini-3.8-flash",
            contents=[
                genai_types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
                final_prompt
            ],
            config=config
        )
        answer_text = response.text or "Пустой ответ."

        await add_to_buffer(chat_id, user_name, f"[Фото] {caption_text if caption_text else 'без подписи'}")
        await add_to_buffer(chat_id, "Бот", answer_text)

        await message.reply(answer_text)
    except Exception as e:
        await message.reply(f"Ошибка при анализе фото: {e}")

@dp.message(F.text, F.chat.id.in_(ALLOWED_CHATS))
async def handle_text(message: types.Message):
    text = message.text.strip()

    if contains_profanity(text):
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=message.message_id)
        except Exception:
            pass
        return

    bot_info = await bot.get_me()
    chat_id = message.chat.id
    user_name = message.from_user.first_name or "Участник"

    need_answer, prompt = should_respond(message, bot_info.username)

    if not need_answer:
        await add_to_buffer(chat_id, user_name, text)
        return

    await bot.send_chat_action(chat_id=chat_id, action="typing")

    context = await get_chat_context(chat_id)
    if context:
        final_prompt = f"Контекст недавней беседы в чате:\n{context}\n\nТекущее обращение от {user_name}: {prompt}"
    else:
        final_prompt = prompt

    try:
        response = await ai_client.aio.models.generate_content(
            model="gemini-3.8-flash",
            contents=final_prompt,
            config=config
        )
        answer_text = response.text or "Пустой ответ."

        await add_to_buffer(chat_id, user_name, text)
        await add_to_buffer(chat_id, "Бот", answer_text)

        await message.reply(answer_text)
    except Exception as e:
        await message.reply(f"Ошибка: {e}")

async def on_startup(bot: Bot):
    await bot.set_webhook(f"{BASE_WEBHOOK_URL}{WEBHOOK_PATH}")

async def main():
    await init_db()
    dp.startup.register(on_startup)

    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text="Bot is running!"))

    webhook_requests_handler = SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    )
    webhook_requests_handler.register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
