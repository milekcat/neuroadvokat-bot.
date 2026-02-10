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
        try: number = int(TICKET_COUNTER_FILE.read_text().strip())
        except (FileNotFoundError, ValueError): number = 1023
        next_number = number + 1
        TICKET_COUNTER_FILE.write_text(str(next_number))
        return next_number

user_states = load_json_data(USER_STATES_FILE, states_lock)
tickets_db = load_json_data(TICKETS_DB_FILE, tickets_lock)

# --- 3. ТЕКСТЫ И КОНСТАНТЫ ---
LEGAL_POLICY_TEXT = r"""... (Ваш полный текст Политики) ..."""
LEGAL_DISCLAIMER_TEXT = r"""... (Ваш полный текст Отказа от ответственности) ..."""
LEGAL_OFERTA_TEXT = r"""... (Ваш полный текст Оферты) ..."""
SERVICE_DESCRIPTIONS = {
    "civil": (
        r"⚖️ *Гражданское право: Защита в повседневной жизни*\n\n"
        r"Для каждого, кто столкнулся с несправедливостью: продали бракованный товар, некачественно сделали ремонт, "
        r"химчистка испортила вещь, страховая занижает выплату по ДТП, соседи затопили квартиру\.\n\n"
        r"*Мы готовим:*\n"
        r"• *Претензии:* грамотный досудебный шаг, который часто решает проблему без суда\.\n"
        r"• *Исковые заявления:* о возврате денег, взыскании неустойки, возмещении ущерба и морального вреда\.\n"
        r"• *Заявления на судебный приказ:* для быстрого взыскания бесспорных долгов\."
    ),
    "family": (
        r"👨‍👩‍👧‍👦 *Семейное право: Деликатная помощь*\n\n"
        r"Для тех, кто хочет зафиксировать договоренности юридически, минимизируя конфликты\.\n\n"
        r"*Мы готовим:*\n"
        r"• *Исковые заявления о взыскании алиментов:* как в % от дохода, так и в твердой денежной сумме \(если доход «серый»\)\.\n"
        r"• *Заявления о расторжении брака* \(если нет спора о детях и имуществе\)\.\n"
        r"• *Проекты соглашений об уплате алиментов:* для добровольного нотариального заверения\."
    ),
    "housing": (
        r"🏠 *Жилищное право: Ваш дом — ваша крепость*\n\n"
        r"Для собственников и арендаторов, которые борются с бездействием УК, решают споры с соседями или хотят безопасно провести сделку\.\n\n"
        r"*Мы готовим:*\n"
        r"• *Жалобы:* в Управляющую компанию, Жилищную инспекцию, Роспотребнадзор\.\n"
        r"• *Исковые заявления:* об определении порядка пользования квартирой, о нечинении препятствий\.\n"
        r"• *Проекты договоров:* купли\-продажи, дарения, аренды \(найма\) с учетом ваших интересов\."
    ),
    "military": (
        r"🛡️ *Военное право и соцобеспечение: Поддержка для защитников*\n\n"
        r"Для военнослужащих \(включая участников СВО\), ветеранов и их семей, столкнувшихся с бюрократией\.\n\n"
        r"*Мы готовим:*\n"
        r"• *Запросы и рапорты:* в военкоматы, в/ч, ЕРЦ МО РФ для уточнения статуса, выплат, наград\.\n"
        r"• *Заявления:* на установление фактов, имеющих юридическое значение \(например, участия в боевых действиях\)\.\n"
        r"• *Административные иски:* для обжалования отказов в назначении выплат и статусов\."
    ),
    "admin": (
        r"🏢 *Административное право: Борьба с бюрократией*\n\n"
        r"Для граждан, столкнувшихся с незаконными действиями чиновников или получивших несправедливый штраф\.\n\n"
        r"*Мы готовим:*\n"
        r"• *Жалобы:* на действия/бездействие должностных лиц в прокуратуру или вышестоящие органы\.\n"
        r"• *Заявления:* в Роспотребнадзор, Трудовую инспекцию\.\n"
        r"• *Ходатайства и жалобы:* по делам об административных правонарушениях \(например, для отмены штрафа ГИБДД\)\."
    ),
    "business": (
        r"💼 *Для малого бизнеса и самозанятых: Юридический щит*\n\n"
        r"Для фрилансеров и небольших компаний, которым нужны надежные документы, но юрист в штате невыгоден\.\n\n"
        r"*Мы готовим:*\n"
        r"• *Проекты договоров:* оказания услуг, подряда, поставки с защитой ваших интересов \(например, с условием об оплате\)\.\n"
        r"• *Претензии:* к контрагентам\-должникам для взыскания оплаты\.\n"
        r"• *Акты выполненных работ* и другие сопроводительные документы\."
    )
}
FAQ_ANSWERS = {
    "price": r"Стоимость подготовки любого документа — *3500 ₽*\.\n\nЭто фиксированная цена, в которую уже включен анализ вашей ситуации, работа ИИ и финальная проверка юристом\.",
    "payment_and_delivery": (
        r"Процесс построен на *полной прозрачности и оплате за результат*:\n\n"
        r"1️⃣ После того как наш специалист \(«Дирижер»\) уточнит все детали, мы готовим документ\.\n\n"
        r"2️⃣ Вы получаете *PDF\-версию с водяными знаками* для финальной проверки\. Вы можете прочитать все от корки до корки и убедиться в качестве\.\n\n"
        r"3️⃣ Если нужны правки — вы сообщаете о них оператору, и мы их вносим\.\n\n"
        r"4️⃣ *Только после вашего финального 'ОК'*, вы производите оплату любым удобным способом \(карта, СБП\)\.\n\n"
        r"5️⃣ Моментально после оплаты вы получаете *финальный файл в формате \.docx \(Word\)*, готовый к печати и использованию\."
    ),
    "template": r"Это *не шаблон*\.\n\nКаждый документ создается ИИ на основе актуального законодательства и судебной практики, а затем *обязательно* проверяется, исправляется и доводится до совершенства живым юристом-«Дирижером»\.",
    "timing": r"Обычно от *3 до 24 часов* с момента, как специалист получит от вас всю необходимую информацию\.",
    "guarantee": r"Ни один юрист не может дать 100% гарантию выигрыша\. Мы *гарантируем*, что подготовленный нами документ будет юридически грамотным, убедительным и составленным с учетом ваших интересов\."
}
CATEGORY_NAMES = {"civil": "Гражданское право", "family": "Семейное право", "housing": "Жилищное право", "military": "Военное право", "admin": "Административное право", "business": "Малый бизнес"}
STATUS_EMOJI = {"new": "🆕", "in_progress": "⏳", "closed": "✅", "declined": "❌"}
STATUS_TEXT = {"new": "Новое", "in_progress": "В работе", "closed": "Закрыто", "declined": "Отклонено"}

# --- 4. ФУНКЦИИ ИНТЕРФЕЙСА И КОМАНДЫ ---

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отображает главное меню."""
    keyboard = [
        [InlineKeyboardButton("✍️ Создать обращение", callback_data='show_services_menu')],
        [InlineKeyboardButton("🗂️ Мои обращения", callback_data='my_tickets')],
        [InlineKeyboardButton("❓ Частые вопросы (FAQ)", callback_data='show_faq_menu')],
        [InlineKeyboardButton("⚖️ Юридическая информация", callback_data='show_legal_menu')],
        [InlineKeyboardButton("📢 Наш канал", url=TELEGRAM_CHANNEL_URL)]
    ]
    text = r"*Здравствуйте\! Это «Нейро\-Адвокат»*\n\nИспользуйте кнопку 'Мои обращения' для доступа к вашему личному кабинету\.\n\nВыберите, что вас интересует:"
    
    target_message = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        try: await target_message.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)
        except Exception: pass
    else:
        await target_message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает команду /start, сбрасывая состояние."""
    await show_main_menu(update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отменяет текущий процесс, удаляя "мусорные" данные."""
    user_id = str(update.effective_user.id)
    state_data = user_states.get(user_id, {})
    
    if state_data.get('state') == 'collecting_data':
        ticket_id_to_delete = state_data.get('active_ticket')
        if ticket_id_to_delete:
            with tickets_lock:
                if ticket_id_to_delete in tickets_db:
                    del tickets_db[ticket_id_to_delete]
                    save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)
                    logger.info(f"Orphaned ticket {ticket_id_to_delete} was deleted due to /cancel.")
    if user_id in user_states:
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
    await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

# --- 5. ЛИЧНЫЙ КАБИНЕТ ---

async def my_tickets_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает пользователю список его обращений."""
    if update.callback_query:
        user = update.callback_query.from_user
        target_message = update.callback_query.message
        is_callback = True
    else:
        user = update.effective_user
        target_message = update.message
        is_callback = False
    
    user_id = str(user.id)
    user_tickets = {k: v for k, v in tickets_db.items() if v.get('user_id') == user_id}

    message_text = "🗂️ *Ваши обращения:*"
    if not user_tickets:
        message_text = "У вас пока нет ни одного обращения."
        keyboard = [[InlineKeyboardButton("✍️ Создать первое обращение", callback_data='show_services_menu')]]
    else:
        keyboard = []
        for ticket_id, ticket_data in sorted(user_tickets.items(), key=lambda item: int(item[0]), reverse=True):
            status_emoji = STATUS_EMOJI.get(ticket_data.get('status', 'new'), '❓')
            category = escape_markdown(ticket_data.get('category', 'Без категории'), 2)
            button_text = f"{status_emoji} Обращение №{ticket_id} ({category})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"view_ticket_{ticket_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')])
    
    if is_callback:
        await target_message.edit_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)
    else:
        await target_message.reply_text(message_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)

async def view_ticket_action(update: Update, context: ContextTypes.DEFAULT_TYPE, ticket_id: str):
    """Показывает детали обращения и историю чата."""
    user_id = str(update.callback_query.from_user.id)
    ticket_data = tickets_db.get(ticket_id)

    if not ticket_data or ticket_data.get('user_id') != user_id:
        await update.callback_query.edit_message_text("Обращение не найдено или у вас нет к нему доступа.")
        return

    chat_history = "💬 *История переписки:*\n\n"
    if not ticket_data.get('chat_history'):
        chat_history += "_Переписка пока пуста\\._"
    else:
        for msg in ticket_data['chat_history']:
            sender = "Вы" if msg['sender'] == 'user' else "Оператор"
            escaped_text = escape_markdown(msg['text'], 2)
            chat_history += f"*{sender}:* {escaped_text}\n"
    
    status_text = escape_markdown(STATUS_TEXT.get(ticket_data.get('status', 'new'), "Неизвестен"), 2)
    
    user_states[user_id] = {'state': 'in_ticket_chat', 'active_ticket': ticket_id}
    save_json_data(user_states, USER_STATES_FILE, states_lock)

    reply_text = (f"*Обращение №{ticket_id}*\n"
                  f"*Статус:* {status_text}\n\n{chat_history}\n\n"
                  "------------------\n"
                  "Вы находитесь в режиме чата по этому обращению\\. Все ваши следующие сообщения будут отправлены оператору\\.\n"
                  "Чтобы выйти, отправьте команду /exit\\_chat")
    
    await update.callback_query.edit_message_text(reply_text, parse_mode=ParseMode.MARKDOWN_V2)

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
    """Главный маршрутизатор для всех нажатий на inline-кнопки."""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'my_tickets': await my_tickets_action(query, context)
    elif data.startswith('view_ticket_'): await view_ticket_action(query, context, data.split('_')[2])
    elif data.startswith('take_'): await take_decline_ticket_action(query, context, 'take')
    elif data.startswith('decline_'): await take_decline_ticket_action(query, context, 'decline')
    elif data.startswith('op_'): await operator_panel_action(query, context)
    elif data == 'show_legal_menu' or data.startswith('legal_'): await legal_menu_action(query, context)
    elif data == 'show_services_menu' or data.startswith('service_'): await services_menu_action(query, context)
    elif data == 'show_faq_menu' or data.startswith('faq_'): await faq_menu_action(query, context)
    elif data.startswith('order_'): await order_action(query, context)
    elif data == 'back_to_start': await show_main_menu(query, context)
    else: logger.warning(f"Unhandled callback_data: {data}")

async def take_decline_ticket_action(query, context, action: str):
    """Обрабатывает взятие или отклонение обращения."""
    parts = query.data.split('_')
    ticket_id, client_user_id = parts[1], parts[2]
    
    with tickets_lock:
        ticket_data = tickets_db.get(ticket_id)
        if not ticket_data:
            await query.answer("Это обращение больше не существует!", show_alert=True)
            return

        if ticket_data['status'] != 'new':
            operator_name = escape_markdown(ticket_data.get('operator_name', 'другим оператором'), 2)
            status_text = STATUS_TEXT.get(ticket_data['status'], 'обработано')
            await query.answer(f"Это обращение уже {status_text} ({operator_name}).", show_alert=True)
            return

        operator_name_raw = query.from_user.full_name
        ticket_data['operator_id'] = str(query.from_user.id)
        ticket_data['operator_name'] = operator_name_raw
        
        if action == 'take':
            ticket_data['status'] = 'in_progress'
            notification_text = f"✅ *Статус обновлен:* Ваше обращение №{ticket_id} принято в работу."
            operator_action_text = f"*✅ Взято в работу оператором {escape_markdown(operator_name_raw, 2)}*"
            keyboard_buttons = [
                [InlineKeyboardButton("💬 Запросить информацию", callback_data=f"op_ask_{ticket_id}_{client_user_id}")],
                [InlineKeyboardButton("📄 Отправить на проверку", callback_data=f"op_review_{ticket_id}_{client_user_id}")],
                [InlineKeyboardButton("🏁 Закрыть обращение", callback_data=f"op_close_{ticket_id}_{client_user_id}")]
            ]
            new_keyboard = InlineKeyboardMarkup(keyboard_buttons)
        else: # decline
            ticket_data['status'] = 'declined'
            notification_text = f"❌ К сожалению, мы не можем взять в работу ваше обращение №{ticket_id} в данный момент."
            operator_action_text = f"*❌ Отклонено оператором {escape_markdown(operator_name_raw, 2)}*"
            new_keyboard = None
        save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)

    try:
        await context.bot.send_message(chat_id=int(client_user_id), text=notification_text, parse_mode=ParseMode.MARKDOWN_V2)
    except Exception as e:
        logger.error(f"Failed to send status update to client {client_user_id}: {e}")
        
    new_text = f"{query.message.text_markdown_v2}\n\n{operator_action_text}"
    await query.edit_message_text(new_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=new_keyboard)

async def operator_panel_action(query, context):
    """Действия с панели оператора."""
    parts = query.data.split('_')
    action, ticket_id, client_user_id = parts[1], parts[2], parts[3]
    
    if action == 'close':
        with tickets_lock:
            if ticket_id in tickets_db:
                tickets_db[ticket_id]['status'] = 'closed'
                save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)
        operator_name = escape_markdown(query.from_user.full_name, 2)
        new_text = f"{query.message.text_markdown_v2}\n\n*🏁 Обращение закрыто оператором {operator_name}*"
        await query.edit_message_text(new_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=None)
        await context.bot.send_message(chat_id=int(client_user_id), text=f"✅ Ваше обращение №{ticket_id} успешно завершено. Спасибо!")
        return

    message_text = ""
    alert_text = "✅ Уведомление клиенту отправлено!"
    if action == 'ask':
        message_text = f"Здравствуйте! По вашему обращению №{ticket_id} требуются уточнения. Специалист скоро напишет вам."
    elif action == 'review':
        message_text = f"📄 *Документ по обращению №{ticket_id} готов!* Мы отправили его вам на проверку."
        
    try:
        if message_text: await context.bot.send_message(chat_id=int(client_user_id), text=message_text, parse_mode=ParseMode.MARKDOWN_V2)
        await query.answer(alert_text, show_alert=True)
    except Exception as e:
        await query.answer("❌ Не удалось отправить сообщение клиенту.", show_alert=True)

async def legal_menu_action(query, context):
    """Навигация по юридическому меню."""
    data = query.data
    if data == 'show_legal_menu':
        keyboard = [[InlineKeyboardButton("📄 Политика конфиденциальности", callback_data='legal_policy')], [InlineKeyboardButton("⚠️ Отказ от ответственности", callback_data='legal_disclaimer')], [InlineKeyboardButton("📑 Договор публичной оферты", callback_data='legal_oferta')], [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')]]
        await query.edit_message_text("Выберите документ:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN_V2)
    else:
        text = {"legal_policy": LEGAL_POLICY_TEXT, "legal_disclaimer": LEGAL_DISCLAIMER_TEXT, "legal_oferta": LEGAL_OFERTA_TEXT}.get(query.data, "Документ не найден.")
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К списку документов", callback_data='show_legal_menu')]]), parse_mode=ParseMode.MARKDOWN_V2)

async def services_menu_action(query, context):
    """Навигация по меню услуг."""
    data = query.data
    if data == 'show_services_menu':
        keyboard = [[InlineKeyboardButton(name, callback_data=f'service_{key}')] for key, name in CATEGORY_NAMES.items()]
        keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')])
        await query.edit_message_text("Выберите сферу:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        service_key = data.split('_')[1]
        await query.edit_message_text(SERVICE_DESCRIPTIONS[service_key], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Создать обращение по этой теме", callback_data=f'order_{service_key}')]]), parse_mode=ParseMode.MARKDOWN_V2)

async def faq_menu_action(query, context):
    """Навигация по FAQ."""
    data = query.data
    if data == 'show_faq_menu':
        keyboard = [[InlineKeyboardButton("Как я получу и оплачу документ?", callback_data='faq_payment_and_delivery')], [InlineKeyboardButton("Сколько стоят услуги?", callback_data='faq_price')], [InlineKeyboardButton("Это просто шаблон?", callback_data='faq_template')], [InlineKeyboardButton("Сколько времени это займет?", callback_data='faq_timing')], [InlineKeyboardButton("Есть ли гарантии?", callback_data='faq_guarantee')], [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')]]
        await query.edit_message_text("Выберите вопрос:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        faq_key = data.split('_', 1)[1]
        await query.edit_message_text(FAQ_ANSWERS[faq_key], reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ К списку вопросов", callback_data='show_faq_menu')]]), parse_mode=ParseMode.MARKDOWN_V2)

async def order_action(query, context):
    """Начало создания обращения."""
    user = query.from_user
    user_id = str(user.id)
    category_key = query.data.split('_')[1]

    # Сразу переводим в состояние сбора данных
    user_states[user_id] = {'state': 'collecting_data', 'category': CATEGORY_NAMES[category_key]}
    save_json_data(user_states, USER_STATES_FILE, states_lock)

    await query.message.delete()
    await context.bot.send_message(
        chat_id=user_id,
        text=r"Отлично\! *Пожалуйста, представьтесь*, опишите вашу ситуацию и приложите все необходимые материалы \(текст, фото, документы, голосовые сообщения\)\. Когда закончите, нажмите кнопку ниже\.",
        reply_markup=ReplyKeyboardMarkup([["✅ Завершить и отправить обращение"]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode=ParseMode.MARKDOWN_V2
    )

# --- 7. ОБРАБОТЧИКИ СООБЩЕНИЙ ---

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Главный обработчик сообщений."""
    user = update.effective_user
    user_id = str(user.id)
    current_state_data = user_states.get(user_id, {})
    current_state = current_state_data.get('state')

    if current_state == 'in_ticket_chat':
        active_ticket_id = current_state_data['active_ticket']
        if active_ticket_id not in tickets_db: return
        
        text_to_save = update.message.text or "[Файл или нетекстовое сообщение]"
        with tickets_lock:
            tickets_db[active_ticket_id].setdefault('chat_history', []).append({"sender": "user", "text": text_to_save, "timestamp": datetime.now().isoformat()})
            save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)

        escaped_text = escape_markdown(text_to_save, 2)
        operator_message = f"💬 Новое сообщение по ОБРАЩЕНИЮ №{active_ticket_id}:\n\n*Клиент:* {escaped_text}"
        await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=operator_message, parse_mode=ParseMode.MARKDOWN_V2)
        await update.message.reply_text("Сообщение отправлено оператору.", quote=True)
        return

    elif current_state == 'collecting_data':
        # Если это первое сообщение в состоянии сбора данных, создаем обращение
        if 'active_ticket' not in current_state_data:
            ticket_id = str(get_and_increment_ticket_number())
            name = user.full_name or user.first_name
            category = current_state_data['category']
            
            user_states[user_id]['active_ticket'] = ticket_id
            save_json_data(user_states, USER_STATES_FILE, states_lock)
            
            with tickets_lock:
                tickets_db[ticket_id] = {"user_id": user_id, "user_name": name, "category": category, "status": "new", "creation_date": datetime.now().isoformat(), "chat_history": []}
                save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)

            header_text = (f"🔔 *ОБРАЩЕНИЕ №{ticket_id}*\n\n"
                           f"*Клиент:* {escape_markdown(name, 2)}\n"
                           f"*Категория:* {escape_markdown(category, 2)}\n\n"
                           "*ВАЖНО:* Отвечайте на *это* сообщение, чтобы общаться с клиентом.")
            await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=header_text, parse_mode=ParseMode.MARKDOWN_V2, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("✅ Взять в работу", callback_data=f"take_{ticket_id}_{user_id}"), InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{ticket_id}_{user_id}")]]))

        # Пересылаем текущее сообщение
        ticket_id = user_states[user_id]['active_ticket']
        if update.message.text == "✅ Завершить и отправить обращение":
            await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=f"--- КОНЕЦ ПЕРВОНАЧАЛЬНОГО ОБРАЩЕНИЯ №{ticket_id} ---")
            await update.message.reply_text(f"✅ *Отлично\\! Ваше обращение №{ticket_id} сформировано*\\.\n\nОператор изучит материалы\\. Вы можете следить за статусом и общаться в 'Личном кабинете'\\.", reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.MARKDOWN_V2)
            del user_states[user_id]
            save_json_data(user_states, USER_STATES_FILE, states_lock)
        else:
            await context.bot.forward_message(chat_id=CHAT_ID_FOR_ALERTS, from_chat_id=user_id, message_id=update.message.message_id)
        return

    await show_main_menu(update, context)

async def reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ответы оператора в рабочем чате."""
    if str(update.message.chat_id) != str(CHAT_ID_FOR_ALERTS) or not update.message.reply_to_message:
        return
        
    replied_text = update.message.reply_to_message.text or update.message.reply_to_message.caption
    if not replied_text:
        await update.message.reply_text("⚠️ Не удалось определить номер обращения. Отвечайте на сообщение с текстом.", quote=True)
        return
    
    match = re.search(r"ОБРАЩЕНИЕ №(\d+)", replied_text)
    if not match:
        await update.message.reply_text("⚠️ Не удалось определить номер обращения из цитаты.", quote=True)
        return

    ticket_id = match.group(1)
    if ticket_id not in tickets_db:
        await update.message.reply_text("⚠️ Обращение с таким номером не найдено в базе.", quote=True)
        return
        
    ticket_data = tickets_db[ticket_id]
    client_user_id = ticket_data['user_id']
    operator_text = update.message.text
    
    with tickets_lock:
        ticket_data.setdefault('chat_history', []).append({"sender": "operator", "text": operator_text, "timestamp": datetime.now().isoformat()})
        save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)
    
    try:
        escaped_operator_text = escape_markdown(operator_text, 2)
        await context.bot.send_message(chat_id=int(client_user_id), text=f"*Оператор по обращению №{ticket_id}:*\n{escaped_operator_text}", parse_mode=ParseMode.MARKDOWN_V2)
        await update.message.reply_text("✅ Ответ клиенту доставлен.", quote=True)
    except Exception as e:
        logger.error(f"Failed to relay reply to client {client_user_id}: {e}")

# --- 8. ЗАПУСК БОТА ---
def main() -> None:
    logger.info("Starting bot...")
    application = Application.builder().token(NEURO_ADVOCAT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("my_tickets", my_tickets_action))
    application.add_handler(CommandHandler("exit_chat", exit_chat_command))
    
    application.add_handler(CallbackQueryHandler(inline_button_handler))
    
    application.add_handler(MessageHandler(filters.REPLY & filters.Chat(chat_id=int(CHAT_ID_FOR_ALERTS)), reply_handler))
    
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    logger.info("Application starting polling...")
    application.run_polling()
    logger.info("Bot has been stopped.")

if __name__ == "__main__":
    main()
