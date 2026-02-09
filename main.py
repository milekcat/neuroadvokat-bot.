import os
import sys

# --- ДИАГНОСТИЧЕСКИЙ БЛОК ---
# Этот блок распечатает все переменные, которые видит сервер.
print("--- DEBUG: Printing all environment variables ---")
for key, value in os.environ.items():
    # Мы не будем печатать сами значения, чтобы не раскрывать секреты,
    # только проверим наличие нужных ключей.
    if "TOKEN" in key or "CHAT_ID" in key or "URL" in key:
        print(f"Found secret-like key: {key}")
    else:
        # Печатаем несекретные переменные для общей информации
        print(f"{key}: {value}")

print("--- DEBUG: End of environment variables ---")

# Проверяем наличие ключа и выходим, если его нет
if 'BOT_TOKEN' not in os.environ:
    print("\nFATAL ERROR: Environment variable 'BOT_TOKEN' was NOT found.")
    print("Please check your 'Variables' tab in the Railway project settings.")
    sys.exit(1) # Выходим из программы с ошибкой
else:
    print("\nSUCCESS: Environment variable 'BOT_TOKEN' was found!")

# --- КОНЕЦ ДИАГНОСТИЧЕСКОГО БЛОКА ---


# -- Остальная часть кода, она не будет выполнена, если токена нет --
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.environ['BOT_TOKEN']
CHAT_ID_FOR_ALERTS = os.environ['CHAT_ID_FOR_ALERTS']
TELEGRAM_CHANNEL_URL = os.environ['TELEGRAM_CHANNEL_URL']

# ... (здесь должен быть остальной код вашего бота, но для теста он сейчас не важен)
# Для чистоты диагностики, пока просто выйдем
print("Bot would start now, but we are in debug mode. Exiting.")
sys.exit(0)


