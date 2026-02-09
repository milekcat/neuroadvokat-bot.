import os
import logging
from datetime import datetime
from threading import Lock
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- Настройка логирования ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- НАСТРОЙКА ---
BOT_TOKEN = os.environ.get('BOT_TOKEN')
CHAT_ID_FOR_ALERTS = os.environ.get('CHAT_ID_FOR_ALERTS')
TELEGRAM_CHANNEL_URL = os.environ.get('TELEGRAM_CHANNEL_URL')

if not BOT_TOKEN or not CHAT_ID_FOR_ALERTS:
    logger.critical("FATAL ERROR: Required environment variable 'BOT_TOKEN' or 'CHAT_ID_FOR_ALERTS' was NOT found.")
    exit(1)

# --- НОВАЯ СИСТЕМА НУМЕРАЦИИ ЗАЯВОК ---
TICKET_COUNTER_FILE = "ticket_counter.txt"
counter_lock = Lock()

def get_and_increment_ticket_number():
    """Потокобезопасно читает и увеличивает номер заявки."""
    with counter_lock:
        try:
            with open(TICKET_COUNTER_FILE, 'r') as f:
                # Начинаем с 1023, чтобы первая заявка была 1024
                number = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            number = 1023
        
        next_number = number + 1
        
        with open(TICKET_COUNTER_FILE, 'w') as f:
            f.write(str(next_number))
            
        return next_number

# --- ТЕКСТЫ И КОНСТАНТЫ ---
# (SERVICE_DESCRIPTIONS, FAQ_ANSWERS, CATEGORY_NAMES - без изменений)
SERVICE_DESCRIPTIONS = { "civil": "...", "family": "...", "housing": "...", "military": "...", "admin": "...", "business": "..." }
FAQ_ANSWERS = { "price": "...", "payment": "...", "template": "...", "timing": "...", "guarantee": "..." }
CATEGORY_NAMES = {"civil": "Гражданское право", "family": "Семейное право", "housing": "Жилищное право", "military": "Военное право", "admin": "Административное право", "business": "Малый бизнес"}

# Хранилище состояний
user_states = {}

# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню."""
    keyboard = [
        [InlineKeyboardButton("✍️ Обратиться", callback_data='show_services_menu')],
        [InlineKeyboardButton("❓ Частые вопросы (FAQ)", callback_data='show_faq_menu')],
        [InlineKeyboardButton("📢 Наш канал", url=TELEGRAM_CHANNEL_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = "Здравствуйте! Я — помощник сервиса «Нейро-Адвокат».\n\nВыберите, что вас интересует:"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

# --- ОБРАБОТЧИКИ КОМАНД ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # (Код без изменений)
    pass

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # (Код без изменений)
    pass

# --- ОБРАБОТЧИКИ КНОПОК И СООБЩЕНИЙ ---

async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все нажатия на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()
    
    # --- НОВАЯ ЛОГИКА: ОБРАБОТКА КНОПОК ОПЕРАТОРА ---
    if query.data.startswith('take_'):
        parts = query.data.split('_')
        action, ticket_number, client_user_id = parts
        client_user_id = int(client_user_id)

        # Отправляем уведомление клиенту
        try:
            await context.bot.send_message(
                chat_id=client_user_id,
                text=f"✅ **Статус обновлен:** Ваша заявка №{ticket_number} принята в работу. Специалист уже изучает ваши материалы и скоро свяжется с вами.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send status update to client {client_user_id}: {e}")

        # Обновляем сообщение для оператора
        original_text = query.message.text_markdown_v2 # Получаем текст с разметкой
        operator_name = query.from_user.full_name
        new_text = f"{original_text}\n\n*✅ Взято в работу оператором {operator_name}*"
        
        await query.edit_message_text(new_text, parse_mode='MarkdownV2')
        return

    if query.data.startswith('decline_'):
        parts = query.data.split('_')
        action, ticket_number, client_user_id = parts

        original_text = query.message.text_markdown_v2
        operator_name = query.from_user.full_name
        new_text = f"{original_text}\n\n*❌ Отклонено оператором {operator_name}*"
        
        await query.edit_message_text(new_text, parse_mode='MarkdownV2')
        return

    # --- НАВИГАЦИЯ (без изменений) ---
    if query.data == 'back_to_start':
        await show_main_menu(update, context)
        return
        
    if query.data == 'show_services_menu':
        # ...
        return

    # --- FAQ (без изменений) ---
    if query.data == 'show_faq_menu':
        # ...
        return

    if query.data.startswith('faq_'):
        # ...
        return

    # --- ЛОГИКА ЗАЯВКИ (без изменений) ---
    if query.data.startswith('service_'):
        # ...
        pass
    elif query.data.startswith('order_'):
        # ...
        pass

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает сообщения в разных состояниях."""
    user_id = update.effective_user.id
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
        
        # --- ГЕНЕРАЦИЯ НОВОГО УВЕДОМЛЕНИЯ ---
        user_info = update.message.from_user
        user_link = f"tg://user?id={user_id}"
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        ticket_number = get_and_increment_ticket_number()
        user_states[user_id]['ticket_number'] = ticket_number

        # Используем MarkdownV2, он более строгий, но мощный
        header_text = (
            f"🔔 *ЗАЯВКА №{ticket_number}*\n\n"
            f"**Время:** `{timestamp}`\n"
            f"**Категория:** `{current_state_data['category']}`\n\n"
            f"**Клиент:** `{name}`\n"
            f"**Контакт:** [Написать клиенту]({user_link})\n\n"
            "--- НАЧАЛО ЗАЯВКИ ---"
        ).replace('-', r'\-') # Экранируем дефисы для MarkdownV2

        operator_keyboard = [
            [
                InlineKeyboardButton("✅ Взять в работу", callback_data=f"take_{ticket_number}_{user_id}"),
                InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{ticket_number}_{user_id}")
            ]
        ]

        await context.bot.send_message(
            chat_id=CHAT_ID_FOR_ALERTS, 
            text=header_text, 
            parse_mode='MarkdownV2',
            reply_markup=InlineKeyboardMarkup(operator_keyboard)
        )
        
        # Сообщение пользователю (без изменений)
        reply_keyboard = [[ "✅ Завершить и отправить заявку" ]]
        await update.message.reply_text(
            f"Приятно познакомиться, {name}!\n\n"
            "Вашему обращению присвоен **номер {ticket_number}**.\n\n"
            "Теперь расскажите о вашей ситуации...",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
        )

    elif state == 'collecting_data':
      
