import os
import logging
import json
from datetime import datetime
from threading import Lock
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- Настройка логирования ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- НАСТРОЙКА ---
NEURO_ADVOCAT_TOKEN = os.environ.get('NEURO_ADVOCAT_TOKEN')
CHAT_ID_FOR_ALERTS = os.environ.get('CHAT_ID_FOR_ALERTS')
TELEGRAM_CHANNEL_URL = os.environ.get('TELEGRAM_CHANNEL_URL')

# Проверка ключевых переменных
if not NEURO_ADVOCAT_TOKEN or not CHAT_ID_FOR_ALERTS:
    logger.critical("FATAL ERROR: A required environment variable was NOT found.")
    logger.critical("Please ensure 'NEURO_ADVOCAT_TOKEN' and 'CHAT_ID_FOR_ALERTS' are set correctly.")
    exit(1)

# --- ПУТИ К ФАЙЛАМ В ПОСТОЯННОМ ХРАНИЛИЩЕ ---
DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/app/data"))
TICKET_COUNTER_FILE = DATA_DIR / "ticket_counter.txt"
USER_STATES_FILE = DATA_DIR / "user_states.json"
MESSAGE_MAP_FILE = DATA_DIR / "message_map.json" # НОВЫЙ ФАЙЛ для связи сообщений

# --- СИСТЕМА НУМЕРАЦИИ ЗАЯВОК ---
counter_lock = Lock()
def get_and_increment_ticket_number():
    with counter_lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            number = int(TICKET_COUNTER_FILE.read_text().strip())
        except (FileNotFoundError, ValueError):
            number = 1023
        next_number = number + 1
        TICKET_COUNTER_FILE.write_text(str(next_number))
        return next_number

# --- УПРАВЛЕНИЕ ДАННЫМИ (Состояния и Карта Сообщений) ---
states_lock = Lock()
message_map_lock = Lock()

def load_json_data(file_path, lock):
    with lock:
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

def save_json_data(data, file_path, lock):
    with lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

# Загружаем начальные данные
user_states = load_json_data(USER_STATES_FILE, states_lock)
message_map = load_json_data(MESSAGE_MAP_FILE, message_map_lock)

# --- ТЕКСТЫ И КОНСТАНТЫ ---
SERVICE_DESCRIPTIONS = { "civil": "...", "family": "...", "housing": "...", "military": "...", "admin": "...", "business": "..." } # Ваши тексты
FAQ_ANSWERS = { "price": "...", "payment_and_delivery": "...", "template": "...", "timing": "...", "guarantee": "..." } # Ваши тексты
CATEGORY_NAMES = {"civil": "Гражданское право", "family": "Семейное право", "housing": "Жилищное право", "military": "Военное право", "admin": "Административное право", "business": "Малый бизнес"}

# --- ОСНОВНЫЕ ФУНКЦИИ БОТА ---
async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("✍️ Обратиться", callback_data='show_services_menu')], [InlineKeyboardButton("❓ Частые вопросы (FAQ)", callback_data='show_faq_menu')], [InlineKeyboardButton("📢 Наш канал", url=TELEGRAM_CHANNEL_URL)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "Здравствуйте! Это **«Нейро-Адвокат»**.\n\nМы создаем юридические документы нового поколения, объединяя опыт юриста-«Дирижера» и мощь ИИ-«Оркестра». Наша цель — не участие, а **результат**, закрепленный в документе.\n\nВыберите, что вас интересует:"
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
    await update.message.reply_text("Перезапускаю бота...", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
        await update.message.reply_text("Подача заявки отменена.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("Нечего отменять.", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    data = query.data

    if data.startswith('take_'):
        parts = data.split('_')
        ticket_number, client_user_id_str = parts[1], parts[2]
        
        try:
            await context.bot.send_message(
                chat_id=int(client_user_id_str),
                text=f"✅ **Статус обновлен:** Ваша заявка №{ticket_number} принята в работу. Специалист уже изучает ваши материалы и скоро свяжется с вами.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send status update to client {client_user_id_str}: {e}")
        
        original_text = query.message.text_markdown_v2
        operator_name = query.from_user.full_name.replace('_', '\_').replace('*', '\*').replace('`', '\`')
        new_text = f"{original_text}\n\n*✅ Взято в работу оператором {operator_name}*"
        
        operator_panel = InlineKeyboardMarkup([
            [InlineKeyboardButton("💬 Запросить информацию", callback_data=f"op_ask_{ticket_number}_{client_user_id_str}")],
            [InlineKeyboardButton("📄 Отправить на проверку", callback_data=f"op_review_{ticket_number}_{client_user_id_str}")],
            [InlineKeyboardButton("🏁 Закрыть заявку", callback_data=f"op_close_{ticket_number}_{client_user_id_str}")],
        ])

        await query.edit_message_text(new_text, parse_mode='MarkdownV2', reply_markup=operator_panel)
        return

    # ... (обработчики кнопок op_ask, op_review, op_close)
    if data.startswith('op_ask_') or data.startswith('op_review_') or data.startswith('op_close_'):
      # ... (Ваш код для этих кнопок)
      return

    if data.startswith('decline_'):
        # ... (Ваш код)
        return

    # ... (остальные обработчики меню: back_to_start, show_services_menu и т.д.)
    if query.data.startswith('order_'):
        user_id = str(query.from_user.id)
        category_key = query.data.split('_')[1]
        category_name = CATEGORY_NAMES.get(category_key, "Неизвестная категория")
        user_states[user_id] = {'category': category_name, 'state': 'ask_name'}
        save_json_data(user_states, USER_STATES_FILE, states_lock)
        await query.edit_message_text("Отлично. Прежде чем мы продолжим, пожалуйста, напишите, как к вам обращаться.")
        return

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    current_state_data = user_states.get(user_id)
    
    if not current_state_data:
        await update.message.reply_text("Чтобы начать, воспользуйтесь командой /start")
        return

    state = current_state_data.get('state')
    
    if state == 'ask_name':
        if not update.message.text or update.message.text.startswith('/'):
            await update.message.reply_text("Пожалуйста, отправьте ваше имя текстом.")
            return
            
        name = update.message.text
        user_states[user_id]['name'] = name
        user_states[user_id]['state'] = 'collecting_data'
        
        user_link = f"tg://user?id={user_id}"
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        ticket_number = get_and_increment_ticket_number()
        user_states[user_id]['ticket_number'] = ticket_number
        
        save_json_data(user_states, USER_STATES_FILE, states_lock)

        header_text = (
            f"🔔 **ЗАЯВКА №{ticket_number}**\n\n"
            f"**Время:** `{timestamp}`\n"
            f"**Категория:** `{current_state_data['category']}`\n\n"
            f"**Клиент:** `{name}`\n"
            f"**Контакт:** [Написать клиенту]({user_link})\n\n"
            "--- НАЧАЛО ЗАЯВКИ ---\n\n"
            "**ВАЖНО:** Чтобы ответить клиенту, используйте функцию «Ответить» (Reply) на его пересланные сообщения."
        )
        initial_keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Взять в работу", callback_data=f"take_{ticket_number}_{user_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{ticket_number}")
            ]
        ])
        
        try:
            await context.bot.send_message(
                chat_id=CHAT_ID_FOR_ALERTS, 
                text=header_text, 
                parse_mode='Markdown',
                reply_markup=initial_keyboard
            )
        except Exception as e:
            logger.error(f"Failed to send ticket {ticket_number} to the alert chat: {e}")

        reply_keyboard = [[ "✅ Завершить и отправить заявку" ]]
        await update.message.reply_text(
            f"Приятно познакомиться, {name}!\n\n"
            f"Вашему обращению присвоен **номер {ticket_number}**.\n\n"
            "Теперь расскажите о вашей ситуации. Вы можете отправить:\n"
            "• Текстовые сообщения\n• Голосовые сообщения\n• Фото или сканы документов\n\n"
            "Когда закончите, нажмите кнопку **'Завершить'** ниже. "
            "Если передумаете, используйте команду /cancel.",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
            parse_mode='Markdown'
        )

    elif state == 'collecting_data':
        ticket_number = current_state_data.get('ticket_number', 'N/A')
        
        if update.message.text == "✅ Завершить и отправить заявку":
            footer_text = f"--- КОНЕЦ ЗАЯВКИ №{ticket_number} ---"
            
            try:
                await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=footer_text)
            except Exception as e:
                logger.error(f"Failed to send end-of-application message for ticket {ticket_number}: {e}")

            await update.message.reply_text(
                f"✅ **Отлично! Ваша заявка №{ticket_number} полностью сформирована и передана специалисту.**\n\n"
                "«Дирижер» изучит все материалы и скоро свяжется с вами для уточнения деталей.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode='Markdown'
            )
            
            del user_states[user_id]
            save_json_data(user_states, USER_STATES_FILE, states_lock)
            return
            
        try:
            forwarded_message = await context.bot.forward_message(
                chat_id=CHAT_ID_FOR_ALERTS,
                from_chat_id=user_id,
                message_id=update.message.message_id
            )
            # СОХРАНЯЕМ СВЯЗЬ: ID пересланного сообщения -> ID клиента
            message_map[str(forwarded_message.message_id)] = user_id
            save_json_data(message_map, MESSAGE_MAP_FILE, message_map_lock)

        except Exception as e:
            logger.error(f"Could not forward message from user {user_id} for ticket {ticket_number}: {e}")

# НОВЫЙ ОБРАБОТЧИК ДЛЯ ОТВЕТОВ ОПЕРАТОРА
async def reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, что это ответ в рабочем чате
    if str(update.message.chat_id) != str(CHAT_ID_FOR_ALERTS):
        return
    
    replied_message = update.message.reply_to_message
    if not replied_message:
        return

    # Ищем ID клиента по ID сообщения, на которое ответили
    client_user_id = message_map.get(str(replied_message.message_id))
    
    if client_user_id:
        try:
            # Копируем сообщение оператора и отправляем его клиенту
            await context.bot.copy_message(
                chat_id=int(client_user_id),
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id
            )
            logger.info(f"Relayed reply from operator {update.message.from_user.id} to client {client_user_id}")
        except Exception as e:
            logger.error(f"Failed to relay reply to client {client_user_id}: {e}")
            await update.message.reply_text(f"⚠️ Не удалось доставить ответ клиенту: {e}")

def main() -> None:
    logger.info("Starting bot...")
    
    application = Application.builder().token(NEURO_ADVOCAT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(inline_button_handler))
    
    # НОВОЕ: Обработчик ответов оператора
    application.add_handler(MessageHandler(
        filters.REPLY & filters.Chat(chat_id=int(CHAT_ID_FOR_ALERTS)), 
        reply_handler
    ))

    # Основной обработчик сообщений от клиентов
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    logger.info("Application starting polling...")
    application.run_polling()
    logger.info("Bot has been stopped.")

if __name__ == "__main__":
    main()


