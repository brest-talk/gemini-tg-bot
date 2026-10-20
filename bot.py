import os
import time
from telebot import TeleBot
from telebot.types import Message
from google import genai
from google.genai import types

# Инициализация переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY') # Добавь этот ключ в Render!

bot = TeleBot(BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)

# Локальная память
user_memory = {}
TIMEOUT_SECONDS = 2 * 3600
MAX_MESSAGES_BUFFER = 30

SYSTEM_PROMPT = """РОЛЬ И ХАРАКТЕР: Ты — свой в чате... (оставь тут свой текст полностью)"""

def update_memory_and_get_context(user_id, text):
    # ... (весь твой код функции памяти оставляем без изменений) ...
    current_time = time.time()
    if user_id not in user_memory:
        user_memory[user_id] = {"last_interaction": current_time, "messages": [text], "resume": ""}
        return "", [text]

    user_data = user_memory[user_id]
    last_interaction = user_data.get("last_interaction", 0)
    messages = user_data.get("messages", [])
    resume = user_data.get("resume", "")

    if current_time - last_interaction > TIMEOUT_SECONDS:
        if messages:
            resume = f"{resume} [Прошлая беседа: {' | '.join(messages)}]"
        messages = [text]
    else:
        messages.append(text)
        if len(messages) > MAX_MESSAGES_BUFFER:
            messages = messages[-MAX_MESSAGES_BUFFER:]

    user_memory[user_id]["last_interaction"] = current_time
    user_memory[user_id]["messages"] = messages
    user_memory[user_id]["resume"] = resume
    return resume, messages

@bot.message_handler(commands=['start'])
def send_welcome(message: Message):
    update_memory_and_get_context(message.from_user.id, "/start")
    bot.reply_to(message, "Здарова. Располагайся, я тут за порядком слежу и на вопросы отвечаю.")

@bot.message_handler(func=lambda message: True)
def handle_message(message: Message):
    user_id = message.from_user.id
    text = message.text

    # 1. Получаем историю
    resume, recent_messages = update_memory_and_get_context(user_id, text)
    
    # 2. Собираем контекст для нейросети
    chat_history = "\n".join(recent_messages)
    prompt = f"Контекст прошлых бесед: {resume}\n\nИстория диалога:\n{chat_history}\n\nОтветь на последнее сообщение."

    # 3. Отправляем в Gemini
    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash', # или gemini-1.5-flash
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
            )
        )
        bot_reply = response.text
    except Exception as e:
        bot_reply = "Слушай, что-то мысли путаются. Давай чуть позже."
        print(f"Ошибка Gemini: {e}")

    # 4. Отвечаем пользователю
    bot.reply_to(message, bot_reply)

if __name__ == '__main__':
    bot.polling(none_stop=True)
