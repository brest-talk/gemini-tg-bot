import os
import time
from telebot import TeleBot
from telebot.types import Message
from pymongo import MongoClient

# Инициализация переменных окружения (настраивается в Render)
BOT_TOKEN = os.environ.get('BOT_TOKEN')
MONGO_URI = os.environ.get('MONGO_URI')

# Инициализация бота и базы данных MongoDB
bot = TeleBot(BOT_TOKEN)
client = MongoClient(MONGO_URI)
db = client['community_bot_db']
memory_collection = db['user_memory']

# Настройки памяти
TIMEOUT_SECONDS = 2 * 3600  # 2 часа
MAX_MESSAGES_BUFFER = 30    # Буфер сообщений

# Универсальный системный промпт: теперь бот работает как помощник для любых чатов и задач
SYSTEM_PROMPT = (
    "Ты — полезный и универсальный AI-ассистент. Твоя задача — помогать пользователям с любыми вопросами, "
    "генерировать идеи, писать тексты, решать задачи и поддерживать общение в любых чатах и группах."
)

def update_memory_and_get_context(user_id, text):
    """
    Управляет памятью пользователя: проверяет таймаут, обновляет буфер сообщений 
    и возвращает актуальный контекст (резюме + последние сообщения).
    """
    current_time = time.time()
    user_data = memory_collection.find_one({"user_id": user_id})

    # Если пользователя еще нет в базе
    if not user_data:
        new_data = {
            "user_id": user_id,
            "last_interaction": current_time,
            "messages": [text],
            "resume": ""
        }
        memory_collection.insert_one(new_data)
        return new_data["resume"], new_data["messages"]

    last_interaction = user_data.get("last_interaction", 0)
    messages = user_data.get("messages", [])
    resume = user_data.get("resume", "")

    # Проверка таймаута на 2 часа
    if current_time - last_interaction > TIMEOUT_SECONDS:
        # Эмулируем сохранение старых данных в расширенное резюме:
        if messages:
            new_resume_addition = " | ".join(messages)
            resume = f"{resume} [Ключевые детали прошлой беседы: {new_resume_addition}]"
        
        # Очищаем буфер сообщений, оставляем только новое сообщение
        messages = [text]
    else:
        # Диалог продолжается, добавляем сообщение
        messages.append(text)
        # Сдвигаем окно, если превышен лимит
        if len(messages) > MAX_MESSAGES_BUFFER:
            messages = messages[-MAX_MESSAGES_BUFFER:]

    # Обновляем данные в MongoDB
    memory_collection.update_one(
        {"user_id": user_id},
        {"$set": {
            "last_interaction": current_time,
            "messages": messages,
            "resume": resume
        }}
    )

    return resume, messages

@bot.message_handler(commands=['start'])
def send_welcome(message: Message):
    update_memory_and_get_context(message.from_user.id, "/start")
    bot.reply_to(message, "Привет! Я универсальный AI-ассистент. Готов помочь с любыми вопросами и задачами в этом чате. Жду твоих сообщений!")

@bot.message_handler(func=lambda message: True)
def handle_message(message: Message):
    user_id = message.from_user.id
    text = message.text

    # Получаем актуальное резюме и буфер из MongoDB
    resume, recent_messages = update_memory_and_get_context(user_id, text)
    
    # Заглушка для демонстрации
    debug_reply = (
        f"Принято. В буфере сейчас {len(recent_messages)} сообщений.\n"
        f"Резюме: {'Пусто' if not resume else 'Сохранено (в памяти)'}\n"
        f"Таймаут сброса: 2 часа."
    )
    bot.reply_to(message, debug_reply)

if __name__ == '__main__':
    bot.polling(none_stop=True)
