import os
import logging
import json
import re
from datetime import datetime
from threading import Lock
from pathlib import Path
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
from telegram.helpers import escape_markdown

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

counter_lock, states_lock, tickets_lock = Lock(), Lock(), Lock()

def load_json_data(file_path, lock):
    with lock:
        if not file_path.exists(): return {}
        try:
            with open(file_path, 'r', encoding='utf-8') as f: return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError): return {}

def save_json_data(data, file_path, lock):
    with lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=4)

def get_and_increment_ticket_number():
    with counter_lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
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
LEGAL_POLICY_TEXT = """
📄 *Политика конфиденциальности*
(Вставьте сюда ваш полный текст)
"""
LEGAL_DISCLAIMER_TEXT = """
⚠️ *Отказ от ответственности (Disclaimer)*
(Вставьте сюда ваш полный текст)
"""
LEGAL_OFERTA_TEXT = """
📑 *Договор публичной оферты*
(Вставьте сюда ваш полный текст)
"""
SERVICE_DESCRIPTIONS = {
    "civil": "⚖️ *Гражданское право: Защита в повседневной жизни*...",
    "family": "👨‍👩‍👧‍👦 *Семейное право: Деликатная помощь*...",
    "housing": "🏠 *Жилищное право: Ваш дом — ваша крепость*...",
    "military": "🛡️ *Военное право и соцобеспечение: Поддержка для защитников*...",
    "admin": "🏢 *Административное право: Борьба с бюрократией*...",
    "business": "💼 *Для малого бизнеса и самозанятых: Юридический щит*..."
}
FAQ_ANSWERS = {
    "price": "Стоимость подготовки любого документа — *3500 ₽*...",
    "payment_and_delivery": "Процесс построен на *полной прозрачности*...",
    "template": "Это *не шаблон*...",
    "timing": "Обычно от *3 до 24 часов*...",
    "guarantee": "Ни один юрист не может дать 100% гарантию..."
}
CATEGORY_NAMES = {"civil": "Гражданское право", "family": "Семейное право", "housing": "Жилищное право", "military": "Военное право", "admin": "Административное право", "business": "Малый бизнес"}
STATUS_EMOJI = {"new": "🆕", "in_progress": "⏳", "closed": "✅", "declined": "❌"}
STATUS_TEXT = {"new": "Новое", "in_progress": "В работе", "closed": "Завершено", "declined": "Отклонено"}

# --- 4. ОСНОВНЫЕ ФУНКЦИИ ИНТЕРФЕЙСА ---

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✍️ Создать обращение", callback_data='show_services_menu')],
        [InlineKeyboardButton("🗂️ Мои обращения", callback_data='my_tickets')],
        [InlineKeyboardButton("❓ Частые вопросы (FAQ)", callback_data='show_faq_menu')],
        [InlineKeyboardButton("⚖️ Юридическая информация", callback_data='show_legal_menu')],
        [InlineKeyboardButton("📢 Наш канал", url=TELEGRAM_CHANNEL_URL)]
    ]
    text = (
        "*Вас приветствует «Нейро-Адвокат»*\n\n"
        "Мы не просто сервис. Мы — ваш личный арсенал для защиты прав. "
        "Каждое обращение здесь — это начало операции, где интеллект «Дирижера» направляет мощь «Оркестра» для достижения единственной цели — **вашего результата**.\n\n"
        "Используйте *«Мои обращения»* для доступа к личному кабинету и отслеживания статуса ваших задач."
    )
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
    await update.message.reply_text("Перезапуск системы...", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    state_data = user_states.get(user_id, {})
    if state_data.get('state') == 'collecting_data':
        ticket_id_to_delete = state_data.get('active_ticket')
        if ticket_id_to_delete:
            with tickets_lock:
                if ticket_id_to_delete in tickets_db:
                    del tickets_db[ticket_id_to_delete]
                    save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)
    if user_id in user_states:
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
    await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

async def exit_chat_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_states.get(user_id, {}).get('state') == 'in_ticket_chat':
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
        await update.message.reply_text("Вы вышли из режима чата.")
        await show_main_menu(update, context)

# --- 5. ЛИЧНЫЙ КАБИНЕТ И ЧАТ ---

async def my_tickets_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_tickets = {k: v for k, v in tickets_db.items() if v.get('user_id') == user_id}
    text = "🗂️ *Ваши обращения:*"
    keyboard = []
    if not user_tickets:
        text = "У вас пока нет ни одного обращения."
        keyboard.append([InlineKeyboardButton("✍️ Создать первое обращение", callback_data='show_services_menu')])
    else:
        for ticket_id, ticket_data in sorted(user_tickets.items(), key=lambda item: int(item[0]), reverse=True):
            status_emoji = STATUS_EMOJI.get(ticket_data.get('status', 'new'), '❓')
            category = escape_markdown(ticket_data.get('category', 'Без категории'))
            button_text = f"{status_emoji} Обращение №{ticket_id} ({category})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_ticket_{ticket_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')])
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def view_ticket_action(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id: str):
    user_id = str(update.callback_query.from_user.id)
    ticket_data = tickets_db.get(ticket_id)
    if not ticket_data or ticket_data.get('user_id') != user_id:
        await update.callback_query.answer("Обращение не найдено.", show_alert=True)
        return

    chat_history = "💬 *История переписки:*\n\n" + ("_Переписка пока пуста._" if not ticket_data.get('chat_history') else "".join(f"**{'Вы' if msg['sender'] == 'user' else 'Оператор'}:** {escape_markdown(msg['text'])}\n" for msg in ticket_data['chat_history']))
    status_text = escape_markdown(STATUS_TEXT.get(ticket_data.get('status', 'new'), "Неизвестен"))
    
    user_states[user_id] = {'state': 'in_ticket_chat', 'active_ticket': ticket_id}
    save_json_data(user_states, USER_STATES_FILE, states_lock)
    
    reply_text = f"*Обращение №{ticket_id}*\n*Статус:* {status_text}\n\n{chat_history}\n\n------------------\nВы находитесь в режиме чата. Все сообщения будут отправлены оператору.\nДля выхода используйте /exit_chat"
    await update.callback_query.edit_message_text(reply_text, parse_mode=ParseMode.MARKDOWN)

# --- 6. ОБРАБОТЧИКИ ДЕЙСТВИЙ (МАРШРУТИЗАТОР) ---

async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    actions = {
        'my_tickets': my_tickets_action,
        'show_legal_menu': legal_menu_action,
        'show_services_menu': services_menu_action,
        'show_faq_menu': faq_menu_action,
        'back_to_start': show_main_menu
    }
    
    if data in actions:
        await actions[data](update, context)
    elif data.startswith('view_ticket_'):
        await view_ticket_action(update, context, data.split('_')[2])
    elif data.startswith(('take_', 'decline_')):
        await operator_ticket_action(update, context)
    elif data.startswith('op_'):
        await operator_panel_action(update, context)
    elif data.startswith(('legal_', 'service_', 'faq_', 'order_')):
        prefix = data.split('_')[0]
        if prefix == 'legal': await legal_menu_action(update, context)
        elif prefix == 'service': await services_menu_action(update, context)
        elif prefix == 'faq': await faq_menu_action(update, context)
        elif prefix == 'order': await order_action(update, context)
    else:
        logger.warning(f"Unhandled callback_data: {data}")

# --- 7. ОБРАБОТЧИКИ СООБЩЕНИЙ ---

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    state_data = user_states.get(user_id, {})
    state = state_data.get('state')

    if state == 'in_ticket_chat':
        # ... (Код без изменений)
        pass
    elif state == 'collecting_data':
        ticket_id = state_data['active_ticket']
        if update.message.text == "✅ Завершить и отправить обращение":
            await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=f"--- КОНЕЦ ПЕРВОНАЧАЛЬНОГО СБОРА ДАННЫХ ПО ЗАЯВКЕ №{ticket_id} ---")
            await update.message.reply_text(f"✅ *Ваше обращение №{ticket_id} сформировано*.\n\nОператор изучит материалы. Отслеживайте статус и общайтесь с оператором в разделе *«Мои обращения»*.", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN)
            del user_states[user_id]
            save_json_data(user_states, USER_STATES_FILE, states_lock)
        else:
            await context.bot.forward_message(chat_id=CHAT_ID_FOR_ALERTS, from_chat_id=user_id, message_id=update.message.message_id)
        return
    else:
        await show_main_menu(update, context)

async def reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (Код без изменений)
    pass
    
# --- 8. ЗАПУСК БОТА ---

def main():
    logger.info("Starting bot version 4.0 'Triumph'...")
    application = Application.builder().token(NEURO_ADVOCAT_TOKEN).build()

    # ... (Код добавления обработчиков без изменений)
    
    application.run_polling()
    logger.info("Bot has been stopped.")

if __name__ == "__main__":
    main()
