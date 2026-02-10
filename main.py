import os
import requests
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- НАСТРОЙКА ---
# Мы используем новое имя переменной, чтобы гарантированно обойти кэш
TOKEN = os.environ.get('NEURO_ADVOCAT_TOKEN')

# --- ДИАГНОСТИКА ---
if not TOKEN:
    logging.critical("--- DIAGNOSTIC RESULT: FAILURE ---")
    logging.critical("FATAL ERROR: Environment variable 'NEURO_ADVOCAT_TOKEN' was NOT found.")
    logging.critical("Please check your 'Variables' tab in the Railway project settings again.")
    exit(1)
else:
    logging.info("--- DIAGNOSTIC RESULT: SUCCESS ---")
    logging.info("SUCCESS: Environment variable 'NEURO_ADVOCAT_TOKEN' was found!")

# --- ТЕСТОВЫЙ ЗАПРОС К TELEGRAM API ---
# Мы делаем самый простой запрос, который только возможен
url = f"https://api.telegram.org/bot{TOKEN}/getMe"

try:
    logging.info(f"Attempting to connect to Telegram API at: {url.split('/bot')[0]}/...")
    response = requests.get(url)
    
    # Проверяем статус ответа
    if response.status_code == 200:
        bot_info = response.json()
        if bot_info.get("ok"):
            bot_name = bot_info["result"]["first_name"]
            bot_username = bot_info["result"]["username"]
            logging.info("--- FINAL VERDICT: SUCCESS! ---")
            logging.info(f"Successfully connected to Telegram. Bot Name: {bot_name}, Username: @{bot_username}")
            logging.info("Your hosting and token are working correctly. You can now upload the full bot code.")
        else:
            logging.error("--- FINAL VERDICT: FAILURE! ---")
            logging.error(f"Telegram API rejected the token. Response: {response.text}")
    else:
        logging.error("--- FINAL VERDICT: FAILURE! ---")
        logging.error(f"Failed to connect to Telegram API. Status Code: {response.status_code}, Response: {response.text}")

except Exception as e:
    logging.error("--- FINAL VERDICT: FAILURE! ---")
    logging.error(f"An unexpected error occurred during the HTTP request: {e}")

