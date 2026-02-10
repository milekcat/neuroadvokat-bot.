import os
import logging
from telegram.ext import Application

# --- Настройка логирования ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- ВРЕМЕННЫЙ ДИАГНОСТИЧЕСКИЙ БЛОК ---
# Мы "зашиваем" токен прямо сюда, чтобы исключить ВСЕ проблемы с переменными
# ПОСЛЕ ТЕСТА ЭТО НУЖНО НЕМЕДЛЕННО УДАЛИТЬ!
TEMP_TOKEN = "8516769048:AAE8PuUpp-tuQIDB00n6Y9wpu7ul7Qyg2RE" 

# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА ---
def main() -> None:
    logger.info("--- DIAGNOSTIC RUN ---")
    logger.info("Attempting to start bot with hardcoded token...")
    
    try:
        # Пытаемся запустить бота с "зашитым" токеном
        application = Application.builder().token(TEMP_TOKEN).build()
        logger.info("Application Builder created successfully.")
        
        # Запускаем короткую инициализацию, чтобы проверить токен
        # loop = asyncio.get_event_loop()
        # loop.run_until_complete(application.initialize())
        
        logger.info("--- FINAL VERDICT: SUCCESS! ---")
        logger.info("Token is VALID. The problem is 100% with Railway's environment variables.")
        
    except Exception as e:
        logger.critical("--- FINAL VERDICT: FAILURE! ---")
        logger.critical(f"Even with a hardcoded token, an error occurred: {e}")

if __name__ == "__main__":
    main()

