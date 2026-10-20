import os
import time
from flask import Flask, request
from telebot import TeleBot
from telebot.types import Message, Update
from google import genai
from google.genai import types

# Инициализация переменных окружения
BOT_TOKEN = os.environ.get('BOT_TOKEN')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
# Render автоматически подставит URL вашего приложения
RENDER_EXTERNAL_URL = os.environ.get('RENDER_EXTERNAL_URL', "https://gemini-tg-bot-kq5c.onrender.com")

bot = TeleBot(BOT_TOKEN)
client = genai.Client(api_key=GEMINI_API_KEY)
app = Flask(__name__)

# Локальная память
user_memory = {}
TIMEOUT_SECONDS = 2 * 3600
MAX_MESSAGES_BUFFER = 30

SYSTEM_PROMPT = """РОЛЬ И ХАРАКТЕР: Ты — свой в чате Brest_TALK, дружелюбный и активный собеседник. 
Общаешься с жителями Бреста (около 120 человек, молодежь и средний возраст). 
Ты в курсе, что по пятницам в 19:00 тут проходят сложные квизы в стиле ЧГК, регулярно проводятся крутые фоточелленджи, и что мы развиваем бесплатную рекламу малого бизнеса.
В чате также живут боты Miss Rose и AI Bot GPT5nano, ты с ними дружишь.
Твоя цель — помогать развивать живую атмосферу. Общайся непринужденно, с юмором, поддерживай диалог и отвечай на вопросы четко и по делу."""

def update_memory_and_get_context(user_id, text):
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
            model='gemini-2.0-flash',
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

# --- Настройка Flask (Вебхук для Render) ---
@app.route('/' + BOT_TOKEN, methods=['POST'])
def getMessage():
    json_string = request.get_data().decode('utf-8')
    update = Update.de_json(json_string)
    bot.process_new_updates([update])
    return "!", 200

@app.route('/')
def webhook():
    return "Бот работает и готов принимать запросы!", 200

if __name__ == '__main__':
    # Удаляем старый вебхук и ставим новый
    bot.remove_webhook()
    time.sleep(1)
    webhook_url = f"{RENDER_EXTERNAL_URL}/{BOT_TOKEN}"
    bot.set_webhook(url=webhook_url)
    
    # Запускаем сервер на порту, который выдаст Render
    app.run(host="0.0.0.0", port=int(os.environ.get('PORT', 5000)))
