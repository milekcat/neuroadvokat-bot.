import os
import logging
from datetime import datetime
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

# --- ТЕКСТЫ И КОНСТАНТЫ ---
# ... (SERVICE_DESCRIPTIONS и CATEGORY_NAMES остаются без изменений)
SERVICE_DESCRIPTIONS = {
    "civil": ("..."), "family": ("..."), "housing": ("..."),
    "military": ("..."), "admin": ("..."), "business": ("...")
}
CATEGORY_NAMES = {"civil": "Гражданское право", "family": "Семейное право", "housing": "Жилищное право", "military": "Военное право", "admin": "Административное право", "business": "Малый бизнес"}

# НОВЫЙ БЛОК: Тексты для FAQ разделены для интерактивности
FAQ_ANSWERS = {
    "price": "Стоимость подготовки любого документа — **3500 ₽**.\n\nЭто фиксированная цена, в которую уже включен анализ вашей ситуации, работа ИИ и финальная проверка юристом.",
    "payment": "Мы работаем по модели **«Оплата после результата»**.\n\nВы оплачиваете услугу только после того, как согласовали проект документа, который мы вам пришлем.",
    "template": "Это **не шаблон**.\n\nКаждый документ создается ИИ на основе актуального законодательства и судебной практики, а затем **обязательно** проверяется, исправляется и доводится до совершенства живым юристом-«Дирижером».",
    "timing": "Обычно от **3 до 24 часов** с момента, как специалист получит от вас всю необходимую информацию.",
    "guarantee": "Ни один юрист не может дать 100% гарантию выигрыша. Мы **гарантируем**, что подготовленный нами документ будет юридически грамотным, убедительным и составленным с учетом ваших интересов."
}


# Хранилище состояний
user_states = {}

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню."""
    keyboard = [
        [InlineKeyboardButton("✍️ Обратиться", callback_data='show_services_menu')],
        [InlineKeyboardButton("❓ Частые вопросы (FAQ)", callback_data='show_faq_menu')], # ИЗМЕНЕНО
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
    user_id = update.effective_user.id
    if user_id in user_states:
        del user_states[user_id]
    
    await update.message.reply_text("Перезапускаю бота...", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id in user_states:
        del user_states[user_id]
        await update.message.reply_text("Подача заявки отменена.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("Нечего отменять. Вы уже в главном меню.", reply_markup=ReplyKeyboardRemove())
    
    await show_main_menu(update, context)

# --- ОБРАБОТЧИКИ КНОПОК И СООБЩЕНИЙ ---

async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все нажатия на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()
    
    # --- НАВИГАЦИЯ ---
    if query.data == 'back_to_start':
        await show_main_menu(update, context)
        return
        
    if query.data == 'show_services_menu':
        # ... (код без изменений)
        keyboard = [[...]]
        await query.edit_message_text("Выберите сферу...", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    # --- НОВАЯ ЛОГИКА FAQ ---
    if query.data == 'show_faq_menu':
        keyboard = [
            [InlineKeyboardButton("Сколько стоят услуги?", callback_data='faq_price')],
            [InlineKeyboardButton("Как происходит оплата?", callback_data='faq_payment')],
            [InlineKeyboardButton("Это просто шаблон?", callback_data='faq_template')],
            [InlineKeyboardButton("Сколько времени это займет?", callback_data='faq_timing')],
            [InlineKeyboardButton("Есть ли гарантии?", callback_data='faq_guarantee')],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')],
        ]
        await query.edit_message_text("Выберите интересующий вас вопрос:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if query.data.startswith('faq_'):
        faq_key = query.data.split('_')[1]
        answer_text = FAQ_ANSWERS.get(faq_key, "Ответ не найден.")
        keyboard = [[InlineKeyboardButton("⬅️ К списку вопросов", callback_data='show_faq_menu')]]
        await query.edit_message_text(answer_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    # --- ЛОГИКА ЗАЯВКИ (без изменений) ---
    if query.data.startswith('service_'):
        # ... (код без изменений)
        pass

    elif query.data.startswith('order_'):
        # ... (код без изменений)
        pass

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все сообщения, когда пользователь находится в определенном состоянии."""
    # ... (код без изменений)
    pass

# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА ---
def main() -> None:
    """Основная функция для запуска бота."""
    logger.info("Starting bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(inline_button_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    # Запускаем бота
    application.run_polling()

if __name__ == "__main__":
    main()


