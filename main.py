import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

# --- ДИАГНОСТИЧЕСКИЙ БЛОК ---
# Эта программа не делает ничего, кроме проверки переменных.

logging.info("--- STARTING FINAL DIAGNOSTIC TEST ---")

# Проверяем каждую переменную отдельно, используя .get(), который никогда не падает
token_value = os.environ.get('NEURO_ADVOCAT_TOKEN')
chat_id_value = os.environ.get('CHAT_ID_FOR_ALERTS')
channel_url_value = os.environ.get('TELEGRAM_CHANNEL_URL')

# Выводим отчет
logging.info("--- VARIABLE REPORT ---")

if token_value:
    logging.info("✅ NEURO_ADVOCAT_TOKEN: FOUND (Value is hidden for security)")
else:
    logging.critical("❌ NEURO_ADVOCAT_TOKEN: !!! NOT FOUND !!!")

if chat_id_value:
    logging.info("✅ CHAT_ID_FOR_ALERTS: FOUND")
else:
    logging.critical("❌ CHAT_ID_FOR_ALERTS: !!! NOT FOUND !!!")

if channel_url_value:
    logging.info("✅ TELEGRAM_CHANNEL_URL: FOUND")
else:
    logging.critical("❌ TELEGRAM_CHANNEL_URL: !!! NOT FOUND !!!")
    
logging.info("--- END OF DIAGNOSTIC TEST ---")

# Программа завершает свою работу.



