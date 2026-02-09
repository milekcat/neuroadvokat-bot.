import os
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- НАСТРОЙКА (берутся из переменных окружения) ---
try:
    BOT_TOKEN = os.environ['BOT_TOKEN']
    CHAT_ID_FOR_ALERTS = os.environ['CHAT_ID_FOR_ALERTS']
    TELEGRAM_CHANNEL_URL = os.environ['TELEGRAM_CHANNEL_URL']
except KeyError as e:
    logging.critical(f"FATAL ERROR: Environment variable {e} was NOT found. Please check your hosting variables.")
    exit()

# --- ТЕКСТЫ И КОНСТАНТЫ ---
# (Тексты оставлены без изменений)
SERVICE_DESCRIPTIONS = {
    "civil": (
        "⚖️ **Гражданское право: Защита в повседневной жизни**\n\n"
        "Для каждого, кто столкнулся с несправедливостью: продали бракованный товар, некачественно сделали ремонт, "
        "химчистка испортила вещь, страховая занижает выплату по ДТП, соседи затопили квартиру.\n\n"
        "**Мы готовим:**\n"
        "• **Претензии:** грамотный досудебный шаг, который часто решает проблему без суда.\n"
        "• **Исковые заявления:** о возврате денег, взыскании неустойки, возмещении ущерба и морального вреда.\n"
        "• **Заявления на судебный приказ:** для быстрого взыскания бесспорных долгов."
    ), "family": (
        "👨‍👩‍👧‍👦 **Семейное право: Деликатная помощь**\n\n"
        "Для тех, кто хочет зафиксировать договоренности юридически, минимизируя конфликты.\n\n"
        "**Мы готовим:**\n"
        "• **Исковые заявления о взыскании алиментов:** как в % от дохода, так и в твердой денежной сумме (если доход «серый»).\n"
        "• **Заявления о расторжении брака** (если нет спора о детях и имуществе).\n"
        "• **Проекты соглашений об уплате алиментов:** для добровольного нотариального заверения."
    ), "housing": (
        "🏠 **Жилищное право: Ваш дом — ваша крепость**\n\n"
        "Для собственников и арендаторов, которые борются с бездействием УК, решают споры с соседями или хотят безопасно провести сделку.\n\n"
        "**Мы готовим:**\n"
        "• **Жалобы:** в Управляющую компанию, Жилищную инспекцию, Роспотребнадзор.\n"
        "• **Исковые заявления:** об определении порядка пользования квартирой, о нечинении препятствий.\n"
        "• **Проекты договоров:** купли-продажи, дарения, аренды (найма) с учетом ваших интересов."
    ), "military": (
        "🛡️ **Военное право и соцобеспечение: Поддержка для защитников**\n\n"
        "Для военнослужащих (включая участников СВО), ветеранов и их семей, столкнувшихся с бюрократией.\n\n"
        "**Мы готовим:**\n"
        "• **Запросы и рапорты:** в военкоматы, в/ч, ЕРЦ МО РФ для уточнения статуса, выплат, наград.\n"
        "• **Заявления:** на установление фактов, имеющих юридическое значение (например, участия в боевых действиях).\n"
        "• **Административные иски:** для обжалования отказов в назначении выплат и статусов."
    ), "admin": (
        "🏢 **Административное право: Борьба с бюрократией**\n\n"
        "Для граждан, столкнувшихся с незаконными действиями чиновников или получивших несправедливый штраф.\n\n"
        "**Мы готовим:**\n"
        "• **Жалобы:** на действия/бездействие должностных лиц в прокуратуру или вышестоящие органы.\n"
        "• **Заявления:** в Роспотребнадзор, Трудовую инспекцию.\n"
        "• **Ходатайства и жалобы:** по делам об административных правонарушениях (например, для отмены штрафа ГИБДД)."
    ), "business": (
        "💼 **Для малого бизнеса и самозанятых: Юридический щит**\n\n"
        "Для фрилансеров и небольших компаний, которым нужны надежные документы, но юрист в штате невыгоден.\n\n"
        "**Мы готовим:**\n"
        "• **Проекты договоров:** оказания услуг, подряда, поставки с защитой ваших интересов (например, с условием об оплате).\n"
        "• **Претензии:** к контрагентам-должникам для взыскания оплаты.\n"
        "• **Акты выполненных работ** и другие сопроводительные документы."
    )
}

FAQ_TEXT = (
    "**Часто задаваемые вопросы (FAQ)**\n\n"
    "**1. Сколько стоят услуги?**\n"
    "Стоимость подготовки любого документа — 3500 ₽...\n\n" # Сокращено для краткости
    "**5. Вы даете 100% гарантию выигрыша в суде?**\n"
    "Ни один юрист или адвокат не может дать 100% гарантию. Мы гарантируем, что подготовленный нами документ будет юридически грамотным, убедительным и составленным с учетом ваших интересов."
)

CATEGORY_NAMES = {"civil": "Гражданское право", "family": "Семейное право", "housing": "Жилищное право", "military": "Военное право", "admin": "Административное право", "business": "Малый бизнес"}

# --- Настройка логирования ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Хранилище состояний
user_states = {}

# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню, редактируя сообщение или отправляя новое."""
    keyboard = [
        [InlineKeyboardButton("✍️ Обратиться", callback_data='show_services_menu')],
        [InlineKeyboardButton("❓ Частые вопросы (FAQ)", callback_data='show_faq')],
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
    """Обработчик /start. Сбрасывает состояние и показывает главное меню."""
    user_id = update.effective_user.id
    if user_id in user_states:
        del user_states[user_id]
    
    # ИСПРАВЛЕНИЕ: Отправляем сообщение, которое убирает ReplyKeyboard, если она была.
    await update.message.reply_text("Перезапускаю бота...", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик /cancel. Сбрасывает состояние и показывает главное меню."""
    user_id = update.effective_user.id
    if user_id in user_states:
        del user_states[user_id]
        await update.message.reply_text("Подача заявки отменена.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("Нечего отменять. Вы уже в главном меню.")
    
    await show_main_menu(update, context)

# --- ОБРАБОТЧИКИ КНОПОК И СООБЩЕНИЙ ---

async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает нажатия на инлайн-кнопки."""
    query = update.callback_query
    await query.answer()
    
    if query.data == 'back_to_start':
        await show_main_menu(update, context)
        return
        
    if query.data == 'show_services_menu':
        keyboard = [
            [InlineKeyboardButton(f"⚖️ {CATEGORY_NAMES['civil']}", callback_data='service_civil')],
            [InlineKeyboardButton(f"👨‍👩‍👧‍👦 {CATEGORY_NAMES['family']}", callback_data='service_family')],
            [InlineKeyboardButton(f"🏠 {CATEGORY_NAMES['housing']}", callback_data='service_housing')],
            [InlineKeyboardButton(f"🛡️ {CATEGORY_NAMES['military']}", callback_data='service_military')],
            [InlineKeyboardButton(f"🏢 {CATEGORY_NAMES['admin']}", callback_data='service_admin')],
            [InlineKeyboardButton(f"💼 {CATEGORY_NAMES['business']}", callback_data='service_business')],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')],
        ]
        await query.edit_message_text("Выберите сферу, в которой вам требуется помощь:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if query.data == 'show_faq':
        keyboard = [[InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')]]
        await query.edit_message_text(FAQ_TEXT, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    if query.data.startswith('service_'):
        service_key = query.data.split('_')[1]
        text = SERVICE_DESCRIPTIONS.get(service_key, "Описание не найдено.")
        keyboard = [
            [InlineKeyboardButton("✅ Подать заявку по этой теме", callback_data=f'order_{service_key}')],
            [InlineKeyboardButton("⬅️ К списку услуг", callback_data='show_services_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    elif query.data.startswith('order_'):
        user_id = query.from_user.id
        category_key = query.data.split('_')[1]
        category_name = CATEGORY_NAMES.get(category_key, "Неизвестная категория")
        user_states[user_id] = {'category': category_name, 'state': 'ask_name'}
        await query.edit_message_text("Отлично. Прежде чем мы продолжим, пожалуйста, напишите, как к вам обращаться.")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает все сообщения, когда пользователь находится в определенном состоянии."""
    user_id = update.effective_user.id
    current_state_data = user_states.get(user_id)

    if not current_state_data:
        await update.message.reply_text("Чтобы начать, воспользуйтесь командой /start")
        return

    state = current_state_data.get('state')

    if state == 'ask_name':
        if not update.message.text:
            await update.message.reply_text("Пожалуйста, отправьте ваше имя текстом.")
            return
            
        name = update.message.text
        user_states[user_id]['name'] = name
        user_states[user_id]['state'] = 'collecting_data'
        
        user_info = update.message.from_user
        user_link = f"tg://user?id={user_id}"
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        header_text = (
            f"🔔 **НОВАЯ ЗАЯВКА**\n\n"
            f"**Время:** `{timestamp}`\n"
            f"**От:** {name} ([{user_info.full_name}]({user_link}))\n"
            f"**Тема:** {current_state_data['category']}\n\n"
            "--- Начало сбора материалов ---"
        )
        await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=header_text, parse_mode='Markdown')
        
        reply_keyboard = [[ "✅ Завершить и отправить заявку" ]]
        await update.message.reply_text(
            f"Приятно познакомиться, {name}!\n\n"
            "Теперь расскажите о вашей ситуации. Вы можете отправить:\n"
            "• Текстовые сообщения\n"
            "• Голосовые сообщения\n"
            "• Фото или сканы документов\n\n"
            "Когда закончите, нажмите кнопку **'Завершить'** ниже. "
            "Если передумаете, используйте команду /cancel.",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
        )

    elif state == 'collecting_data':
        if update.message.text == "✅ Завершить и отправить заявку":
            footer_text = f"--- Конец заявки от {current_state_data['name']} ---"
            await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=footer_text)
            
            await update.message.reply_text(
                "✅ **Отлично! Ваша заявка полностью сформирована и передана специалисту.**\n\n"
                "«Дирижер» изучит все материалы и скоро свяжется с вами в личных сообщениях. "
                "Спасибо за обращение!",
                reply_markup=ReplyKeyboardRemove()
            )
            del user_states[user_id]
            return

        await context.bot.forward_message(
            chat_id=CHAT_ID_FOR_ALERTS,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )

# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА ---

def main() -> None:
    """Основная функция для запуска бота."""
    logger.info("Starting bot...")
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(inline_button_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    application.run_polling()
    logger.info("Bot stopped.")

if __name__ == "__main__":
    main()




