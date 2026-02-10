import os
import logging
import json
from datetime import datetime
from threading import Lock
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- 1. НАСТРОЙКА ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

NEURO_ADVOCAT_TOKEN = os.environ.get('NEURO_ADVOCAT_TOKEN')
CHAT_ID_FOR_ALERTS = os.environ.get('CHAT_ID_FOR_ALERTS')
TELEGRAM_CHANNEL_URL = os.environ.get('TELEGRAM_CHANNEL_URL')

if not all([NEURO_ADVOCAT_TOKEN, CHAT_ID_FOR_ALERTS, TELEGRAM_CHANNEL_URL]):
    logger.critical("FATAL ERROR: One or more environment variables are missing.")
    exit(1)

# --- 2. УПРАВЛЕНИЕ ДАННЫМИ ---
DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/app/data"))
TICKET_COUNTER_FILE = DATA_DIR / "ticket_counter.txt"
USER_STATES_FILE = DATA_DIR / "user_states.json"
TICKETS_DB_FILE = DATA_DIR / "tickets.json"

counter_lock = Lock()
states_lock = Lock()
tickets_lock = Lock()

def load_json_data(file_path, lock):
    with lock:
        if not file_path.exists():
            return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

def save_json_data(data, file_path, lock):
    with lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)

def get_and_increment_ticket_number():
    with counter_lock:
        try:
            number = int(TICKET_COUNTER_FILE.read_text().strip())
        except (FileNotFoundError, ValueError):
            number = 1023
        next_number = number + 1
        TICKET_COUNTER_FILE.write_text(str(next_number))
        return next_number

user_states = load_json_data(USER_STATES_FILE, states_lock)
tickets_db = load_json_data(TICKETS_DB_FILE, tickets_lock)

# --- 3. ТЕКСТЫ И КОНСТАНТЫ ---
LEGAL_POLICY_TEXT = """... (Ваш полный текст Политики конфиденциальности) ..."""
LEGAL_DISCLAIMER_TEXT = """... (Ваш полный текст Отказа от ответственности) ..."""
LEGAL_OFERTA_TEXT = """... (Ваш полный текст Договора оферты) ..."""
SERVICE_DESCRIPTIONS = {
    "civil": ("⚖️ **Гражданское право: Защита в повседневной жизни**\n\n... (Полный текст)"),
    "family": ("👨‍👩‍👧‍👦 **Семейное право: Деликатная помощь**\n\n... (Полный текст)"),
    "housing": ("🏠 **Жилищное право: Ваш дом — ваша крепость**\n\n... (Полный текст)"),
    "military": ("🛡️ **Военное право и соцобеспечение: Поддержка для защитников**\n\n... (Полный текст)"),
    "admin": ("🏢 **Административное право: Борьба с бюрократией**\n\n... (Полный текст)"),
    "business": ("💼 **Для малого бизнеса и самозанятых: Юридический щит**\n\n... (Полный текст)")
}
FAQ_ANSWERS = {
    "price": "Стоимость подготовки любого документа — **3500 ₽** ... (Полный текст)",
    "payment_and_delivery": ("Процесс построен на **полной прозрачности и оплате за результат**:\n\n... (Полный текст)"),
    "template": "Это **не шаблон**.\n\n... (Полный текст)",
    "timing": "Обычно от **3 до 24 часов** ... (Полный текст)",
    "guarantee": "Ни один юрист не может дать 100% гарантию выигрыша ... (Полный текст)"
}
CATEGORY_NAMES = {"civil": "Гражданское право", "family": "Семейное право", "housing": "Жилищное право", "military": "Военное право", "admin": "Административное право", "business": "Малый бизнес"}
STATUS_EMOJI = {"new": "🆕", "in_progress": "⏳", "closed": "✅"}
STATUS_TEXT = {"new": "Новая", "in_progress": "В работе", "closed": "Закрыта"}

# --- 4. ФУНКЦИИ ИНТЕРФЕЙСА И КОМАНДЫ ---

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню."""
    keyboard = [
        [InlineKeyboardButton("✍️ Обратиться", callback_data='show_services_menu')],
        [InlineKeyboardButton("🗂️ Мои заявки", callback_data='my_tickets')],
        [InlineKeyboardButton("❓ Частые вопросы (FAQ)", callback_data='show_faq_menu')],
        [InlineKeyboardButton("⚖️ Юридическая информация", callback_data='show_legal_menu')],
        [InlineKeyboardButton("📢 Наш канал", url=TELEGRAM_CHANNEL_URL)]
    ]
    text = "Здравствуйте! Это **«Нейро-Адвокат»**.\n\nИспользуйте кнопку 'Мои заявки' для доступа к вашему личному кабинету.\n\nВыберите, что вас интересует:"
    
    target_message = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await target_message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await target_message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start."""
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
    await show_main_menu(update, context)

# ИСПРАВЛЕНО: ВОЗВРАЩЕНА НЕДОСТАЮЩАЯ ФУНКЦИЯ
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменяет текущий процесс подачи заявки."""
    user_id = str(update.effective_user.id)
    if user_states.get(user_id, {}).get('state') in ['ask_name', 'collecting_data']:
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
        await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
        logger.info(f"User {user_id} executed /cancel and cleared their state.")
    else:
        await update.message.reply_text("Нечего отменять. Вы уже в главном меню.", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

# --- 5. ЛИЧНЫЙ КАБИНЕТ ПОЛЬЗОВАТЕЛЯ ---

async def my_tickets_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает пользователю список его заявок (обработчик и для команды, и для кнопки)."""
    user_id = str(update.effective_user.id)
    user_tickets = {k: v for k, v in tickets_db.items() if v.get('user_id') == user_id}

    message_text = "🗂️ **Ваши заявки:**"
    if not user_tickets:
        message_text = "У вас пока нет ни одной заявки."
        keyboard = [[InlineKeyboardButton("✍️ Создать первую заявку", callback_data='show_services_menu')]]
    else:
        keyboard = []
        sorted_tickets = sorted(user_tickets.items(), key=lambda item: int(item[0]), reverse=True)
        for ticket_id, ticket_data in sorted_tickets:
            status_emoji = STATUS_EMOJI.get(ticket_data.get('status', 'new'), '❓')
            category = ticket_data.get('category', 'Без категории')
            button_text = f"{status_emoji} Заявка №{ticket_id} ({category})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_ticket_{ticket_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')])
    
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await target.edit_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await target.reply_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def view_ticket_action(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id: str):
    """Показывает детали заявки и историю чата."""
    user_id = str(update.effective_user.id)
    ticket_data = tickets_db.get(ticket_id)

    if not ticket_data or ticket_data.get('user_id') != user_id:
        await update.callback_query.edit_message_text("Заявка не найдена или у вас нет к ней доступа.")
        return

    chat_history = "💬 **История переписки:**\n\n"
    if not ticket_data.get('chat_history'):
        chat_history += "_Переписка пока пуста._"
    else:
        for msg in ticket_data['chat_history']:
            sender = "Вы" if msg['sender'] == 'user' else "Оператор"
            chat_history += f"**{sender}:** {msg['text']}\n"
    
    status_text = STATUS_TEXT.get(ticket_data.get('status', 'new'), "Неизвестен")
    
    user_states[user_id] = {'state': 'in_ticket_chat', 'active_ticket': ticket_id}
    save_json_data(user_states, USER_STATES_FILE, states_lock)

    reply_text = (f"**Заявка №{ticket_id}**\n"
                  f"**Статус:** {status_text}\n\n{chat_history}\n\n"
                  "------------------\n"
                  "Вы находитесь в режиме чата по этой заявке. Все ваши следующие сообщения будут отправлены оператору.\n"
                  "Чтобы выйти, отправьте команду /exit_chat")
    
    await update.callback_query.edit_message_text(reply_text, parse_mode='Markdown')

async def exit_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выводит пользователя из режима чата."""
    user_id = str(update.effective_user.id)
    if user_states.get(user_id, {}).get('state') == 'in_ticket_chat':
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
        await update.message.reply_text("Вы вышли из режима чата.")
        await show_main_menu(update, context)

# --- 6. ОБРАБОТЧИКИ ДЕЙСТВИЙ ---

async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все нажатия на inline-кнопки."""
    query = update.callback_query
    await query.answer()
    data = query.data

    # Маршрутизация по типу callback_data
    if data == 'my_tickets':
        await my_tickets_action(query, context)
    elif data.startswith('view_ticket_'):
        await view_ticket_action(query, context, data.split('_')[2])
    elif data.startswith('take_'):
        await take_ticket_action(query, context)
    elif data.startswith('op_'):
        await operator_panel_action(query, context)
    elif data.startswith('legal_') or data == 'show_legal_menu':
        await legal_menu_action(query, context)
    elif data.startswith('service_') or data == 'show_services_menu':
        await services_menu_action(query, context)
    elif data.startswith('faq_') or data == 'show_faq_menu':
        await faq_menu_action(query, context)
    elif data.startswith('order_'):
        await order_action(query, context)
    elif data == 'back_to_start':
        await show_main_menu(query, context)


async def take_ticket_action(query, context):
    """Действие 'Взять в работу'."""
    parts = query.data.split('_')
    ticket_id, client_user_id = parts[1], parts[2]
    if ticket_id in tickets_db:
        tickets_db[ticket_id]['status'] = 'in_progress'
        tickets_db[ticket_id]['operator_id'] = str(query.from_user.id)
        save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)
        
        try:
            await context.bot.send_message(chat_id=int(client_user_id), text=f"✅ **Статус обновлен:** Ваша заявка №{ticket_id} принята в работу.", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Failed to send status update to client {client_user_id}: {e}")
        
        original_text = query.message.text_markdown_v2
        operator_name = query.from_user.full_name.replace('_', r'\_').replace('*', r'\*').replace('`', r'\`')
        new_text = f"{original_text}\n\n*✅ Взято в работу оператором {operator_name}*"
        
        operator_panel = InlineKeyboardMarkup([[InlineKeyboardButton("💬 Запросить информацию", callback_data=f"op_ask_{ticket_id}_{client_user_id}")], [InlineKeyboardButton("📄 Отправить на проверку", callback_data=f"op_review_{ticket_id}_{client_user_id}")], [InlineKeyboardButton("🏁 Закрыть заявку", callback_data=f"op_close_{ticket_id}_{client_user_id}")]])
        await query.edit_message_text(new_text, parse_mode='MarkdownV2', reply_markup=operator_panel)


async def operator_panel_action(query, context):
    """Действия с панели оператора (Запросить, Проверить, Закрыть)."""
    parts = query.data.split('_')
    action, ticket_id, client_user_id = parts[1], parts[2], parts[3]
    
    message_text = ""
    alert_text = ""
    
    if action == 'ask':
        message_text = f"Здравствуйте! По вашей заявке №{ticket_id} требуются уточнения. Специалист скоро напишет вам."
        alert_text = "✅ Уведомление с запросом информации отправлено!"
    elif action == 'review':
        message_text = f"📄 **Документ по заявке №{ticket_id} готов!** Мы отправили его вам на проверку."
        alert_text = "✅ Уведомление о готовности отправлено!"
    elif action == 'close':
        if ticket_id in tickets_db:
            tickets_db[ticket_id]['status'] = 'closed'
            save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)
        operator_name = query.from_user.full_name.replace('_', r'\_').replace('*', r'\*').replace('`', r'\`')
        new_text = f"{query.message.text_markdown_v2}\n\n*🏁 Заявка закрыта оператором {operator_name}*"
        await query.edit_message_text(new_text, parse_mode='MarkdownV2', reply_markup=None)
        await context.bot.send_message(chat_id=int(client_user_id), text=f"✅ Ваша заявка №{ticket_id} успешно завершена. Спасибо!")
        return

    try:
        if message_text:
            await context.bot.send_message(chat_id=int(client_user_id), text=message_text, parse_mode='Markdown')
        await query.answer(alert_text, show_alert=True)
    except Exception as e:
        await query.answer("❌ Не удалось отправить сообщение клиенту.", show_alert=True)


async def legal_menu_action(query, context):
    """Навигация по юридическому меню."""
    data = query.data
    if data == 'show_legal_menu':
        keyboard = [[InlineKeyboardButton("📄 Политика конфиденциальности", callback_data='legal_policy')], [InlineKeyboardButton("⚠️ Отказ от ответственности", callback_data='legal_disclaimer')], [InlineKeyboardButton("📑 Договор публичной оферты", callback_data='legal_oferta')], [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')]]
        await query.edit_message_text("Выберите документ:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        text = {"legal_policy": LEGAL_POLICY_TEXT, "legal_disclaimer": LEGAL_DISCLAIMER_TEXT, "legal_oferta": LEGAL_OFERTA_TEXT}.get(data, "Документ не найден.")
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К списку документов", callback_data='show_legal_menu')]]), parse_mode='Markdown')


async def services_menu_action(query, context):
    """Навигация по меню услуг."""
    data = query.data
    if data == 'show_services_menu':
        keyboard = [[InlineKeyboardButton(f"{v}", callback_data=f'service_{k}')] for k, v in CATEGORY_NAMES.items()]
        keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')])
        await query.edit_message_text("Выберите сферу:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        service_key = data.split('_')[1]
        await query.edit_message_text(SERVICE_DESCRIPTIONS[service_key], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Подать заявку по этой теме", callback_data=f'order_{service_key}')], [InlineKeyboardButton("⬅️ К списку услуг", callback_data='show_services_menu')]]), parse_mode='Markdown')


async def faq_menu_action(query, context):
    """Навигация по FAQ."""
    data = query.data
    if data == 'show_faq_menu':
        keyboard = [[InlineKeyboardButton("Как я получу и оплачу документ?", callback_data='faq_payment_and_delivery')], [InlineKeyboardButton("Сколько стоят услуги?", callback_data='faq_price')], [InlineKeyboardButton("Это просто шаблон?", callback_data='faq_template')], [InlineKeyboardButton("Сколько времени это займет?", callback_data='faq_timing')], [InlineKeyboardButton("Есть ли гарантии?", callback_data='faq_guarantee')], [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')]]
        await query.edit_message_text("Выберите вопрос:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        faq_key = data.split('_', 1)[1]
        await query.edit_message_text(FAQ_ANSWERS[faq_key], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К списку вопросов", callback_data='show_faq_menu')]]), parse_mode='Markdown')


async def order_action(query, context):
    """Начало подачи заявки."""
    user_id = str(query.from_user.id)
    category_key = query.data.split('_')[1]
    user_states[user_id] = {'category': CATEGORY_NAMES[category_key], 'state': 'ask_name'}
    save_json_data(user_states, USER_STATES_FILE, states_lock)
    await query.edit_message_text("Отлично. Прежде чем мы продолжим, пожалуйста, напишите, как к вам обращаться.")


# --- 7. ОБРАБОТЧИКИ СООБЩЕНИЙ ---

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Главный обработчик текстовых и прочих сообщений."""
    user_id = str(update.effective_user.id)
    current_state = user_states.get(user_id, {}).get('state')

    if current_state == 'in_ticket_chat':
        active_ticket_id = user_states[user_id]['active_ticket']
        ticket_data = tickets_db.get(active_ticket_id)
        if not ticket_data: return
        
        text_to_save = update.message.text or "[Файл или нетекстовое сообщение]"
        ticket_data.setdefault('chat_history', []).append({"sender": "user", "text": text_to_save, "timestamp": datetime.now().isoformat()})
        save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)

        operator_message = f"💬 Новое сообщение по заявке №{active_ticket_id}:\n\n**Клиент:** {text_to_save}"
        await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=operator_message, parse_mode="Markdown")
        await update.message.reply_text("Сообщение отправлено оператору.", quote=True)
        return

    elif current_state == 'ask_name':
        name = update.message.text
        if not name or name.startswith('/'): return
        
        ticket_id = str(get_and_increment_ticket_number())
        user_states[user_id].update({'state': 'collecting_data', 'active_ticket': ticket_id})
        save_json_data(user_states, USER_STATES_FILE, states_lock)
        
        tickets_db[ticket_id] = {"user_id": user_id, "user_name": name, "category": user_states[user_id]['category'], "status": "new", "creation_date": datetime.now().isoformat(), "chat_history": []}
        save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)

        header_text = (f"🔔 **ЗАЯВКА №{ticket_id}**\n\n**Клиент:** {name}\n**Категория:** {user_states[user_id]['category']}\n\n**ВАЖНО:** Отвечайте на **это** сообщение, чтобы общаться с клиентом.")
        await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=header_text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Взять в работу", callback_data=f"take_{ticket_id}_{user_id}")]]))

        await update.message.reply_text(f"Приятно познакомиться, {name}!\n\nВашей заявке присвоен **номер {ticket_id}**.\n\nТеперь расскажите о вашей ситуации, отправляя сообщения, фото и файлы. Когда закончите, нажмите кнопку ниже.", reply_markup=ReplyKeyboardMarkup([["✅ Завершить и отправить"]], one_time_keyboard=True, resize_keyboard=True), parse_mode='Markdown')
        return

    elif current_state == 'collecting_data':
        ticket_id = user_states[user_id]['active_ticket']
        if update.message.text == "✅ Завершить и отправить":
            await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=f"--- КОНЕЦ ПЕРВОНАЧАЛЬНОЙ ЗАЯВКИ №{ticket_id} ---")
            await update.message.reply_text(f"✅ **Отлично! Ваша заявка №{ticket_id} сформирована.**\n\nОператор изучит материалы. Вы можете следить за статусом и общаться в 'Личном кабинете'.", reply_markup=ReplyKeyboardRemove(), parse_mode='Markdown')
            del user_states[user_id]
            save_json_data(user_states, USER_STATES_FILE, states_lock)
        else:
            await context.bot.forward_message(chat_id=CHAT_ID_FOR_ALERTS, from_chat_id=user_id, message_id=update.message.message_id)
        return

    await show_main_menu(update, context)


async def reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ответы оператора в рабочем чате."""
    if str(update.message.chat_id) != str(CHAT_ID_FOR_ALERTS): return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.text:
        return
        
    replied_text = update.message.reply_to_message.text
    
    if "Заявка №" not in replied_text: return
    
    try:
        ticket_id = replied_text.split("Заявка №")[1].split("\n")[0].strip()
        ticket_data = tickets_db.get(ticket_id)
        
        if ticket_data:
            client_user_id = ticket_data['user_id']
            operator_text = update.message.text
            
            ticket_data.setdefault('chat_history', []).append({"sender": "operator", "text": operator_text, "timestamp": datetime.now().isoformat()})
            save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)
            
            await context.bot.send_message(chat_id=int(client_user_id), text=f"**Оператор по заявке №{ticket_id}:**\n{operator_text}", parse_mode="Markdown")
            await update.message.reply_text("✅ Ответ клиенту доставлен.", quote=True)
    except Exception as e:
        logger.error(f"Could not parse ticket ID or send reply: {e}")
        await update.message.reply_text("⚠️ Не удалось определить номер заявки из цитаты.", quote=True)


# --- 8. ЗАПУСК БОТА ---
def main() -> None:
    logger.info("Starting bot...")
    application = Application.builder().token(NEURO_ADVOCAT_TOKEN).build()

    # Команды
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("my_tickets", my_tickets_action))
    application.add_handler(CommandHandler("exit_chat", exit_chat_command))
    
    # Обработчик кнопок
    application.add_handler(CallbackQueryHandler(inline_button_handler))
    
    # Обработчик ответов оператора (высокий приоритет)
    application.add_handler(MessageHandler(filters.REPLY & filters.Chat(chat_id=int(CHAT_ID_FOR_ALERTS)), reply_handler))
    
    # Главный обработчик сообщений (низкий приоритет)
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    logger.info("Application starting polling...")
    application.run_polling()
    logger.info("Bot has been stopped.")

if __name__ == "__main__":
    main()

