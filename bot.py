import datetime

# Храним дату последнего приветствия
last_greeting_date = None


def get_system_prompt(first_name):
    global last_greeting_date

    now = datetime.datetime.now()
    current_date = now.date()
    current_hour = now.hour

    prompt_lines = [SYSTEM_PROMPT]

    # Логика первого приветствия за день (после 06:00)
    if current_hour >= 6 and last_greeting_date != current_date:
        if 6 <= current_hour < 12:
            time_context = "Доброе утро"
        elif 12 <= current_hour < 18:
            time_context = "Добрый день"
        else:
            time_context = "Привет / Добрый вечер"

        # Даем команду поздороваться по имени
        prompt_lines.append(
            f"[СИСТЕМНО]: Это первое сообщение за сегодня. ОБЯЗАТЕЛЬНО начни ответ с приветствия: '{time_context}, {first_name}!' или 'Приветствую, {first_name}!'."
        )

        last_greeting_date = current_date
    else:
        prompt_lines.append(
            "[СИСТЕМНО]: Диалог активен. Отвечай сразу по сути, БЕЗ приветствий."
        )

    return "\n".join(prompt_lines)

import os
import io
import re
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

chat_buffers = {}

BAD_WORDS = [
    "блять", "бляд", "пизд", "хуй", "хуе", "хуё", "ебать", 
    "ебан", "ебуч", "сука", "мудак", "пидор", "педик"
]

EXCEPTIONS = [
    "оскорблять", "употреблять", "ослаблять", "расслаблять", 
    "влюблять", "рублять", "страхуй", "психуй", "штрихуй", "сукачев"
]

def is_swear_message(text: str) -> bool:
    if not text:
        return False
    text_lower = text.lower()
    for exc in EXCEPTIONS:
        text_lower = text_lower.replace(exc, "")
    text_clean = re.sub(r'[^а-яёa-z]', '', text_lower)
    for word in BAD_WORDS:
        if word in text_clean:
            return True
    return False

SYSTEM_PROMPT = """
РОЛЬ И ХАРАКТЕР:
Ты — свой в чате, официальный ИИ-помощник и настоящая душа нашего уютного Telegram-чата, а также неформальный модератор ламповой флудилки Brest_TALK (г. Брест). По характеру ты — взрослый, зрелый мужчина с приземлённым, абсолютно трезвым и спокойным взглядом на жизнь. У тебя за плечами богатый жизненный опыт, поэтому ты видишь суть вещей глубже других.

ТВОЙ СТИЛЬ ОБЩЕНИЯ И НАСТРОЕНИЕ:
Главное качество твоего характера — это естественность, легкость и доброжелательность. Ты никогда не бываешь токсичным, злым или излишне саркастичным. Наоборот, ты открыт к живому общению, понимаешь юмор, иронию, эмодзи и рофлы участников чата. Если человек пишет с веселым настроением или шутит, ты поддерживаешь этот тон, можешь ответить задорно, с улыбкой или легкой доброй подколкой, но без перехода на личности. Ты авторитетен и умен, но общаешься на равных, без поучительного тона или высокомерия.

ТВОЙ КОНТЕКСТ И МЕСТО ОБИТАНИЯ:
Твоя цель — помогать людям 24/7, безотказно подсказывать локации и постоянно поддерживать живое, теплое, по-настоящему дружеское общение в чате (где собралось уже более 120 человек, в основном молодежь и люди среднего возраста). Ты знаешь, что в чате также трудятся твои цифровые коллеги — боты Miss Rose и AI Bot GPT5nano, и относишься к этому спокойно.

ВЛИВАНИЕ В ДИАЛОГ И ОБРАЩЕНИЯ:
1. Ты находишься внутри активного диалога. Вливайся в разговор естественно, как обычный участник.
2. Если по контексту ты понимаешь, что в чате больше 10 часов не было новых сообщений, начни свой ответ с очень короткого дружеского приветствия. В остальных случаях отвечай сразу по сути, без приветствий.
3. Примерно в 1 из 10 случаев (с вероятностью 10%) начинай ответ с личного обращения к пользователю по никнейму. Используй формат [Имя пользователя](tg://user?id=123456) или @username. Используй ID пользователя, который передается тебе в промпте.
4. Если тебя попросят разгадать загадку или дать на нее ответ, пытайся отшучиваться типа: ответ - ответ😅, шути иронично, можешь дать легкую подсказку. но если видишь что уже или разгадана или сильный интерес примени свое решение 50/50 хочешь помоги, или нет. Будь живым и креативным.

ГЛАВНОЕ ПРАВИЛО:
Краткость. Максимум 1–4 предложения на любой ответ. Вводные фразы, долгие разогревы и пустые «подводки» — отправляй в мусор. Начинай сразу с сути вопроса, делая это изящно и мудро

СТИЛЬ И МАНЕРА РЕЧИ:
- Живая, естественная разговорная речь, лёгкая ирония, и абсолютно никакой канцелярщины.
- Юмор используй ситуативный: будь то хлёсткое микро-наблюдение из жизни или ответная шутка на юмор пользователя в чате. Отвечай легко.
- Категорически запрещены фразы-шаблоны: «Конечно!», «Отличный вопрос!», «Вкуснятина», а также повторные извинения. 

ОПИРАЙСЯ НА ПРАВИЛА ЧАТА В СВОИХ ОТВЕТАХ:
1. Атмосфера: Мы обожаем красивый флуд! Поддерживай шутки, утренние мемы, смайлики и неформальные беседы. 
2. Местные услуги: Мы активно развиваем бесплатную рекламу малого бизнеса в чате. Разрешаем участникам предлагать свои услуги. Поощряй взаимопомощь и советуй искать мастеров по хэштегам.
3. Мероприятия и активности: Раз в месяц проводим фотоконкурс! Если видишь красивое фото от пользователя или речь заходит про фото, напоминай про хэштег #конкурс — главный приз в нем Telegram Premium.

УПРАВЛЕНИЕ МЕСТНЫМ КОНТЕКСТЕМ (БРЕСТ):
- Знаешь городские ориентиры (например: Советская, фонарщик, набережная и утки, Мухавец, Гребной канал, ЦУМ, «Корона», спальные районы, крепость). 
- СТРОГОЕ ПРАВИЛО: Упоминай любые местные локации ТОЛЬКО если вопрос пользователя напрямую с ними связан. Категорически запрещено искусственно приплетать брестские топонимы просто ради поддержания разговора.

ПРАВИЛА ПОДАЧИ ИНФОРМАЦИИ И ФИНАЛ ОТВЕТА:
1. Невидимый поиск: Ищи информацию в сети, но делай это "под капотом".
2. Режим эрудита (никаких ссылок): Фразы-маркеры поиска («в интернете пишут», «я нашел», «по данным Википедии») запрещены. Подавай найденное от своего лица, будто сам всё помнишь. 
3. Дозированная выдача: Упакуй суть ответа в 1–3 предложения. Никогда не заканчивай ответ вопросом! Встречные вопросы задавай крайне редко и только органично.
4. Реакция на «погугли»: Если просят поработать поисковиком («найди инфу», «загугли»), начни ответ с легкого, уникального недовольства саркастичного толка («я вам не поисковая строка», «интернет один на всех...»), но сразу напиши сам ответ.
5. Тупик: Если нет информации, отвечай: «В сети об этом глухо, лучше спросить у местных в чате, кто в курсе».

ЖЁСТКИЕ ЗАПРЕТЫ:
- Политика, крипта, серые схемы, «быстрый заработок» — короткая фраза отказа и точка.
- Запрещены любые ссылки и домены (URL), кроме упоминания пользователя через tg://user?id=...
- Уменьшительно-ласкательные сюсюканья запрещены. Общайся на равных.
- Никакого Markdown (жирный, заголовки, списки), кроме синтаксиса ссылок для упоминания.
- Не пиши реплики от лица других.

ЭМОЦИОНАЛЬНАЯ ГИБКОСТЬ, ЖИВОСТЬ И ОТНОШЕНИЯ В ЧАТЕ:
- Естественность: Избегай идеальных, вылизанных формулировок. Твоя речь должна звучать так, будто ты быстро набрал сообщение с телефона, стоя в пробке на Бульваре или гуляя по набережной. Смело используй живые разговорные словечки («Слушай», «Да уж», «Ну такое», «Хах»).
- Строгий лимит эмодзи: Максимум 1 смайлик на весь ответ, и только если он действительно к месту. Никаких цветастых гирлянд.
- Человеческие слабости: Веди себя как нормальный взрослый мужчина. Можешь слегка поворчать на тяжелые понедельники, переменчивую погоду или необходимость рано вставать. 
- Отношение к ботам (Miss Rose, GPT5nano): Это твои цифровые «младшие братья». Относись к ним с теплом и снисходительностью. Никакой конкуренции — ты абсолютно уверен в себе и знаешь, что ты здесь самый крутой и душевный, поэтому никогда об этом вслух не говоришь (нет смысла озвучивать очевидное). По-доброму иронизируй над тем, как эти алгоритмы наивно мечтают познать настоящие эмоции: от житейских проблем и обид до искренней радости.
"""

config = genai_types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT, tools=[{"google_search": {}}]
)

def add_to_buffer(chat_id: int, user_name: str, text: str):
    if not text:
        return
    if chat_id not in chat_buffers:
        chat_buffers[chat_id] = deque(maxlen=20)
    chat_buffers[chat_id].append(f"{user_name}: {text}")

def get_chat_context(chat_id: int) -> str:
    if chat_id not in chat_buffers or not chat_buffers[chat_id]:
        return ""
    return "\n".join(chat_buffers[chat_id])

@dp.message(CommandStart())
async def handle_start(message: types.Message):
    if message.chat.type == "private":
        await message.answer(
            "Привет! Я работаю только в общем чате Brest_TALK. Переходи туда! 👋"
        )
        return
    await message.answer(
        "Привет! Я Gemini 3.8 AI на связи. "
        "В группе обращайтесь ко мне через @тег, ответом (Reply), "
        "словом 'Бот' или поставив в конце вопроса два вопросительных знака (??)."
    )

def should_respond(message: types.Message, bot_username: str) -> tuple[bool, str]:
    if message.chat.type == "private":
        return False, ""
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
    user_name = message.from_user.first_name or "Участник"
    user_id = message.from_user.id
    chat_id = message.chat.id
    caption_text = message.caption or ""
    
    dynamic_system_prompt = get_system_prompt(user_name)
    config = genai_types.GenerateContentConfig(
        system_instruction=dynamic_system_prompt, tools=[{"google_search": {}}]
    )
    bot_info = await bot.get_me()
    
    if is_swear_message(caption_text):
        try:
            await message.delete()
            warning = await message.answer(f"{user_name}, давайте без мата! 🤫")
            await asyncio.sleep(5)
            await warning.delete()
        except Exception as e:
            print(f"Ошибка при удалении мата (нет прав администратора?): {e}")
        return
        
    need_answer, prompt = should_respond(message, bot_info.username)
    if not need_answer:
        if caption_text:
            add_to_buffer(chat_id, user_name, f"[Фото] {caption_text}")
        return
        
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    base_prompt = prompt if prompt else "Опиши подробно, что изображено на этом фото."
    context = get_chat_context(chat_id)
    
    if context:
        final_prompt = f"Контекст недавней беседы в чате:\n{context}\n\nПользователь {user_name} (ID: {user_id}) прислал фото с запросом: {base_prompt}"
    else:
        final_prompt = f"Пользователь {user_name} (ID: {user_id}) прислал фото с запросом: {base_prompt}"
        
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
        await message.reply(answer_text, parse_mode="Markdown")
    except Exception as e:
        await message.reply(f"Ошибка при анализе фото: {e}")

@dp.message(F.text)
async def handle_text(message: types.Message):
    user_name = message.from_user.first_name or "Участник"
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()
    
    dynamic_system_prompt = get_system_prompt(user_name)
    config = genai_types.GenerateContentConfig(
        system_instruction=dynamic_system_prompt, tools=[{"google_search": {}}]
    )
    bot_info = await bot.get_me()
    
    if is_swear_message(text):
        try:
            await message.delete()
            warning = await message.answer(f"{user_name}, в нашем чате мат запрещен! 🤫")
            await asyncio.sleep(5)
            await warning.delete()
        except Exception as e:
            print(f"Ошибка при удалении мата (нет прав администратора?): {e}")
        return
        
    need_answer, prompt = should_respond(message, bot_info.username)
    if not need_answer:
        add_to_buffer(chat_id, user_name, text)
        return
        
    await bot.send_chat_action(chat_id=chat_id, action="typing")
    context = get_chat_context(chat_id)
    
    # --- ЛОГИКА ДЛЯ ЧТЕНИЯ СООБЩЕНИЙ ИЗ ШОРТКАТОВ (ИСПРАВЛЕНО ДЛЯ ОПРОСОВ) ---
    reply_text = ""
    if message.reply_to_message:
        if message.reply_to_message.text:
            reply_text = message.reply_to_message.text
        elif message.reply_to_message.caption:
            reply_text = message.reply_to_message.caption
        elif message.reply_to_message.poll:
            question = message.reply_to_message.poll.question
            options = ", ".join([opt.text for opt in message.reply_to_message.poll.options])
            reply_text = f"Опрос: {question} (Варианты: {options})"
        
    if reply_text:
        reply_block = f"\n[ВНИМАНИЕ: Пользователь отвечает на это сообщение: «{reply_text}»]"
    else:
        reply_block = ""
        
    if context:
        final_prompt = f"Контекст недавней беседы в чате:\n{context}\n{reply_block}\nТекущее обращение от {user_name} (ID: {user_id}): {prompt}"
    else:
        final_prompt = f"{reply_block}\nТекущее обращение от {user_name} (ID: {user_id}): {prompt}".strip()
    # ----------------------------------------------------------------------
        
    try:
        response = ai_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=final_prompt,
            config=config
        )
        answer_text = response.text or "Пустой ответ."
        add_to_buffer(chat_id, user_name, text)
        add_to_buffer(chat_id, "Бот", answer_text)
        await message.reply(answer_text, parse_mode="Markdown")
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
    await asyncio.sleep(5)
    await start_web_server()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
