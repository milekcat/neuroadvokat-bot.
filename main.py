import os
import logging
from datetime import datetime
from threading import Lock
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

# --- Настройка логирования ---
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# --- НАСТРОЙКА (С НОВЫМ ИМЕНЕМ ПЕРЕМЕННОЙ) ---
NEURO_ADVOCAT_TOKEN = os.environ.get('NEURO_ADVOCAT_TOKEN')
CHAT_ID_FOR_ALERTS = os.environ.get('CHAT_ID_FOR_ALERTS')
TELEGRAM_CHANNEL_URL = os.environ.get('TELEGRAM_CHANNEL_URL')

# Проверяем, что ключевые переменные существуют.
if not NEURO_ADVOCAT_TOKEN or not CHAT_ID_FOR_ALERTS:
    logger.critical("FATAL ERROR: A required environment variable was NOT found.")
    logger.critical("Please ensure 'NEURO_ADVOCAT_TOKEN' and 'CHAT_ID_FOR_ALERTS' are set correctly in Railway.")
    exit(1)

# --- СИСТЕМА НУМЕРАЦИИ ЗАЯВОК ---
TICKET_COUNTER_FILE = "ticket_counter.txt"
counter_lock = Lock()

def get_and_increment_ticket_number():
    with counter_lock:
        try:
            with open(TICKET_COUNTER_FILE, 'r') as f:
                number = int(f.read().strip())
        except (FileNotFoundError, ValueError):
            number = 1023
        next_number = number + 1
        with open(TICKET_COUNTER_FILE, 'w') as f:
            f.write(str(next_number))
        return next_number

# --- ТЕКСТЫ И КОНСТАНТЫ ---
SERVICE_DESCRIPTIONS = {
    "civil": (
        "⚖️ **Гражданское право: Защита в повседневной жизни**\n\n"
        "Для каждого, кто столкнулся с несправедливостью: продали бракованный товар, некачественно сделали ремонт, "
        "химчистка испортила вещь, страховая занижает выплату по ДТП, соседи затопили квартиру.\n\n"
        "**Мы готовим:**\n"
        "• **Претензии:** грамотный досудебный шаг, который часто решает проблему без суда.\n"
        "• **Исковые заявления:** о возврате денег, взыскании неустойки, возмещении ущерба и морального вреда.\n"
        "• **Заявления на судебный приказ:** для быстрого взыскания бесспорных долгов."
    ),
    "family": (
        "👨‍👩‍👧‍👦 **Семейное право: Деликатная помощь**\n\n"
        "Для тех, кто хочет зафиксировать договоренности юридически, минимизируя конфликты.\n\n"
        "**Мы готовим:**\n"
        "• **Исковые заявления о взыскании алиментов:** как в % от дохода, так и в твердой денежной сумме (если доход «серый»).\n"
        "• **Заявления о расторжении брака** (если нет спора о детях и имуществе).\n"
        "• **Проекты соглашений об уплате алиментов:** для добровольного нотариального заверения."
    ),
    "housing": (
        "🏠 **Жилищное право: Ваш дом — ваша крепость**\n\n"
        "Для собственников и арендаторов, которые борются с бездействием УК, решают споры с соседями или хотят безопасно провести сделку.\n\n"
        "**Мы готовим:**\n"
        "• **Жалобы:** в Управляющую компанию, Жилищную инспекцию, Роспотребнадзор.\n"
        "• **Исковые заявления:** об определении порядка пользования квартирой, о нечинении препятствий.\n"
        "• **Проекты договоров:** купли-продажи, дарения, аренды (найма) с учетом ваших интересов."
    ),
    "military": (
        "🛡️ **Военное право и соцобеспечение: Поддержка для защитников**\n\n"
        "Для военнослужащих (включая участников СВО), ветеранов и их семей, столкнувшихся с бюрократией.\n\n"
        "**Мы готовим:**\n"
        "• **Запросы и рапорты:** в военкоматы, в/ч, ЕРЦ МО РФ для уточнения статуса, выплат, наград.\n"
        "• **Заявления:** на установление фактов, имеющих юридическое значение (например, участия в боевых действиях).\n"
        "• **Административные иски:** для обжалования отказов в назначении выплат и статусов."
    ),
    "admin": (
        "🏢 **Административное право: Борьба с бюрократией**\n\n"
        "Для граждан, столкнувшихся с незаконными действиями чиновников или получивших несправедливый штраф.\n\n"
        "**Мы готовим:**\n"
        "• **Жалобы:** на действия/бездействие должностных лиц в прокуратуру или вышестоящие органы.\n"
        "• **Заявления:** в Роспотребнадзор, Трудовую инспекцию.\n"
        "• **Ходатайства и жалобы:** по делам об административных правонарушениях (например, для отмены штрафа ГИБДД)."
    ),
    "business": (
        "💼 **Для малого бизнеса и самозанятых: Юридический щит**\n\n"
        "Для фрилансеров и небольших компаний, которым нужны надежные документы, но юрист в штате невыгоден.\n\n"
        "**Мы готовим:**\n"
        "• **Проекты договоров:** оказания услуг, подряда, поставки с защитой ваших интересов (например, с условием об оплате).\n"
        "• **Претензии:** к контрагентам-должникам для взыскания оплаты.\n"
        "• **Акты выполненных работ** и другие сопроводительные документы."
    )
}
FAQ_ANSWERS = {
    "price": "Стоимость подготовки любого документа — **3500 ₽**.\n\nЭто фиксированная цена, в которую уже включен анализ вашей ситуации, работа ИИ и финальная проверка юристом.",
    "payment_and_delivery": (
        "Процесс построен на **полной прозрачности и оплате за результат**:\n\n"
        "1️⃣ После того как наш специалист («Дирижер») уточнит все детали, мы готовим документ.\n\n"
        "2️⃣ Вы получаете **PDF-версию с водяными знаками** для финальной проверки. Вы можете прочитать все от корки до корки и убедиться в качестве.\n\n"
        "3️⃣ Если нужны правки — вы сообщаете о них оператору, и мы их вносим.\n\n"
        "4️⃣ **Только после вашего финального 'ОК'**, вы производите оплату любым удобным способом (карта, СБП).\n\n"
        "5️⃣ Моментально после оплаты вы получаете **финальный файл в формате .docx (Word)**, готовый к печати и использованию."
    ),
    "template": "Это **не шаблон**.\n\nКаждый документ создается ИИ на основе актуального законодательства и судебной практики, а затем **обязательно** проверяется, исправляется и доводится до совершенства живым юристом-«Дирижером».",
    "timing": "Обычно от **3 до 24 часов** с момента, как специалист получит от вас всю необходимую информацию.",
    "guarantee": "Ни один юрист не может дать 100% гарантию выигрыша. Мы **гарантируем**, что подготовленный нами документ будет юридически грамотным, убедительным и составленным с учетом ваших интересов."
}
CATEGORY_NAMES = {"civil": "Гражданское право", "family": "Семейное право", "housing": "Жилищное право", "military": "Военное право", "admin": "Административное право", "business": "Малый бизнес"}

# Хранилище состояний
user_states = {}

# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ---

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✍️ Обратиться", callback_data='show_services_menu')],
        [InlineKeyboardButton("❓ Частые вопросы (FAQ)", callback_data='show_faq_menu')],
        [InlineKeyboardButton("📢 Наш канал", url=TELEGRAM_CHANNEL_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    text = (
        "Здравствуйте! Это **«Нейро-Адвокат»**.\n\n"
        "Мы создаем юридические документы нового поколения, объединяя опыт юриста-«Дирижера» и мощь ИИ-«Оркестра». "
        "Наша цель — не участие, а **результат**, закрепленный в документе.\n\n"
        "Выберите, что вас интересует:"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

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
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith('take_'):
        parts = query.data.split('_')
        ticket_number, client_user_id = parts[1], int(parts[2])
        try:
            await context.bot.send_message(
                chat_id=client_user_id,
                text=f"✅ **Статус обновлен:** Ваша заявка №{ticket_number} принята в работу. Специалист уже изучает ваши материалы и скоро свяжется с вами.",
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send status update to client {client_user_id}: {e}")
        original_text = query.message.text_markdown_v2
        operator_name = query.from_user.full_name
        new_text = f"{original_text}\n\n*✅ Взято в работу оператором {operator_name}*"
        await query.edit_message_text(new_text, parse_mode='MarkdownV2', reply_markup=None)
        return

    if query.data.startswith('decline_'):
        parts = query.data.split('_')
        ticket_number = parts[1]
        original_text = query.message.text_markdown_v2
        operator_name = query.from_user.full_name
        new_text = f"{original_text}\n\n*❌ Отклонено оператором {operator_name}*"
        await query.edit_message_text(new_text, parse_mode='MarkdownV2', reply_markup=None)
        return
        
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

    if query.data == 'show_faq_menu':
        keyboard = [
            [InlineKeyboardButton("Как я получу и оплачу документ?", callback_data='faq_payment_and_delivery')],
            [InlineKeyboardButton("Сколько стоят услуги?", callback_data='faq_price')],
            [InlineKeyboardButton("Это просто шаблон?", callback_data='faq_template')],
            [InlineKeyboardButton("Сколько времени это займет?", callback_data='faq_timing')],
            [InlineKeyboardButton("Есть ли гарантии?", callback_data='faq_guarantee')],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')],
        ]
        await query.edit_message_text("Выберите интересующий вас вопрос:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if query.data.startswith('faq_'):
        faq_key = query.data.split('_', 1)[1]
        answer_text = FAQ_ANSWERS.get(faq_key, "Ответ не найден.")
        keyboard = [[InlineKeyboardButton("⬅️ К списку вопросов", callback_data='show_faq_menu')]]
        await query.edit_message_text(answer_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    if query.data.startswith('service_'):
        service_key = query.data.split('_')[1]
        text = SERVICE_DESCRIPTIONS.get(service_key, "Описание не найдено.")
        keyboard = [
            [InlineKeyboardButton("✅ Подать заявку по этой теме", callback_data=f'order_{service_key}')],
            [InlineKeyboardButton("⬅️ К списку услуг", callback_data='show_services_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        return

    if query.data.startswith('order_'):
        user_id = query.from_user.id
        category_key = query.data.split('_')[1]
        category_name = CATEGORY_NAMES.get(category_key, "Неизвестная категория")
        user_states[user_id] = {'category': category_name, 'state': 'ask_name'}
        await query.edit_message_text("Отлично. Прежде чем мы продолжим, пожалуйста, напишите, как к вам обращаться.")
        return

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
        
        user_info = update.message.from_user
        user_link = f"tg://user?id={user_id}"
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        ticket_number = get_and_increment_ticket_number()
        user_states[user_id]['ticket_number'] = ticket_number

        header_text = (
            f"🔔 *ЗАЯВКА №{ticket_number}*\n\n"
            f"**Время:** `{timestamp}`\n"
            f"**Категория:** `{current_state_data['category']}`\n\n"
            f"**Клиент:** `{name}`\n"
            f"**Контакт:** [Написать клиенту]({user_link})\n\n"
            "\\-\\-\\- НАЧАЛО ЗАЯВКИ \\-\\-\\-"
        )

        operator_keyboar
