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

if not all([NEURO_ADVOCAT_TOKEN, CHAT_ID_FOR_ALERTS]):
    logger.critical("FATAL ERROR: NEURO_ADVOCAT_TOKEN or CHAT_ID_FOR_ALERTS is missing.")
    exit(1)

# --- 2. УПРАВЛЕНИЕ ДАННЫМИ (НАДЕЖНОЕ) ---
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
        try: number = int(TICKET_COUNTER_FILE.read_text().strip())
        except (FileNotFoundError, ValueError): number = 1023
        next_number = number + 1
        TICKET_COUNTER_FILE.write_text(str(next_number))
        return next_number

user_states = load_json_data(USER_STATES_FILE, states_lock)
tickets_db = load_json_data(TICKETS_DB_FILE, tickets_lock)

# --- 3. ТЕКСТЫ И КОНСТАНТЫ (ПОЛНОСТЬЮ ЗАПОЛНЕНЫ) ---
SERVICE_DESCRIPTIONS = {
    "civil": (
        "⚖️ *Гражданское право: Защита в повседневной жизни*\n\n"
        "Для каждого, кто столкнулся с несправедливостью: продали бракованный товар, некачественно сделали ремонт, "
        "химчистка испортила вещь, страховая занижает выплату по ДТП, соседи затопили квартиру."
    ),
    "family": (
        "👨‍👩‍👧‍👦 *Семейное право: Деликатная помощь*\n\n"
        "Для тех, кто хочет зафиксировать договоренности юридически, минимизируя конфликты."
    ),
    "housing": (
        "🏠 *Жилищное право: Ваш дом — ваша крепость*\n\n"
        "Для собственников и арендаторов, которые борются с бездействием УК, решают споры с соседями или хотят безопасно провести сделку."
    ),
    "military": (
        "🛡️ *Военное право и соцобеспечение: Поддержка для защитников*\n\n"
        "Для военнослужащих (включая участников СВО), ветеранов и их семей, столкнувшихся с бюрократией."
    ),
    "admin": (
        "🏢 *Административное право: Борьба с бюрократией*\n\n"
        "Для граждан, столкнувшихся с незаконными действиями чиновников или получивших несправедливый штраф."
    ),
    "business": (
        "💼 *Для малого бизнеса и самозанятых: Юридический щит*\n\n"
        "Для фрилансеров и небольших компаний, которым нужны надежные документы, но юрист в штате невыгоден."
    )
}
FAQ_ANSWERS = {
    "price": "Стоимость подготовки любого документа — *3500 ₽*.\n\nЭто фиксированная цена, в которую уже включен анализ вашей ситуации, работа ИИ и финальная проверка юристом.",
    "payment_and_delivery": (
        "Процесс построен на *полной прозрачности и оплате за результат*:\n\n"
        "1️⃣ После согласования всех деталей, мы готовим документ и присылаем вам *PDF-версию с водяными знаками* для финальной проверки.\n"
        "2️⃣ *Только после вашего 'ОК'*, вы производите оплату.\n"
        "3️⃣ Моментально после оплаты вы получаете *финальный файл в формате .docx (Word)*."
    ),
    "template": "Это *не шаблон*.\n\nКаждый документ создается ИИ на основе актуального законодательства и судебной практики, а затем *обязательно* проверяется и доводится до совершенства живым юристом-«Дирижером».",
    "timing": "Обычно от *3 до 24 часов* с момента, как специалист получит от вас всю необходимую информацию.",
    "guarantee": "Мы *гарантируем*, что подготовленный нами документ будет юридически грамотным и убедительным. Гарантировать 100% выигрыш в суде не может ни один юрист."
}
CATEGORY_NAMES = {"civil": "Гражданское право", "family": "Семейное право", "housing": "Жилищное право", "military": "Военное право", "admin": "Административное право", "business": "Малый бизнес"}
STATUS_EMOJI = {"new": "🆕", "in_progress": "⏳", "closed": "✅", "declined": "❌"}

# --- 4. ФУНКЦИИ ИНТЕРФЕЙСА И КОМАНДЫ ---

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("✍️ Создать обращение", callback_data='show_services_menu')],
        [InlineKeyboardButton("🗂️ Мои обращения", callback_data='my_tickets')],
        [InlineKeyboardButton("❓ Частые вопросы (FAQ)", callback_data='show_faq_menu')],
        [InlineKeyboardButton("📢 Наш канал", url=TELEGRAM_CHANNEL_URL)]
    ]
    text = (
        "*Вас приветствует «Нейро-Адвокат»*\n\n"
        "Мы — ваш личный арсенал для защиты прав. "
        "Наша система «Дирижер и Оркестр» создает мощные юридические документы, нацеленные на **результат**.\n\n"
        "▶️ *Создайте обращение*, чтобы начать.\n"
        "▶️ Используйте *«Мои обращения»*, чтобы отследить статус ваших задач."
    )
    
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
    await update.message.reply_text("Перезапуск системы...", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
        save_json_data(user_states, USER_STATES_FILE, states_lock)
        await update.message.reply_text("Действие отменено.", reply_markup=ReplyKeyboardRemove())
    else:
        await update.message.reply_text("Нечего отменять.", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)

# --- 5. ЛИЧНЫЙ КАБИНЕТ (УПРОЩЕННЫЙ И НАДЕЖНЫЙ) ---

async def my_tickets_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_tickets = {k: v for k, v in tickets_db.items() if v.get('user_id') == user_id}
    text = "🗂️ *Ваши обращения:*\n\nЗдесь отображается список всех созданных вами заявок и их текущий статус."
    keyboard = []
    if not user_tickets:
        text = "У вас пока нет ни одного обращения."
        keyboard.append([InlineKeyboardButton("✍️ Создать первое обращение", callback_data='show_services_menu')])
    else:
        for ticket_id, ticket_data in sorted(user_tickets.items(), key=lambda item: int(item[0]), reverse=True):
            status_emoji = STATUS_EMOJI.get(ticket_data.get('status', 'new'), '❓')
            category = escape_markdown(ticket_data.get('category', 'Без категории'))
            button_text = f"{status_emoji} Обращение №{ticket_id} ({category})"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=f"info_ticket_{ticket_id}")])
    
    keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')])
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await target.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
    else:
        await target.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

# --- 6. ОБРАБОТЧИКИ ДЕЙСТВИЙ ---

async def inline_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == 'show_services_menu':
        keyboard = [[InlineKeyboardButton(name, callback_data=f'service_{key}')] for key, name in CATEGORY_NAMES.items()]
        keyboard.append([InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')])
        await query.edit_message_text("Выберите сферу, в которой вам требуется помощь:", reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif data.startswith('service_'):
        service_key = data.split('_')[1]
        text = SERVICE_DESCRIPTIONS.get(service_key, "Описание не найдено.")
        keyboard = [
            [InlineKeyboardButton("✅ Создать обращение по этой теме", callback_data=f'order_{service_key}')],
            [InlineKeyboardButton("⬅️ К списку услуг", callback_data='show_services_menu')]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data.startswith('order_'):
        user_id = str(query.from_user.id)
        category_key = data.split('_')[1]
        user_states[user_id] = {'category': CATEGORY_NAMES[category_key], 'state': 'ask_name'}
        save_json_data(user_states, USER_STATES_FILE, states_lock) # <-- СОХРАНЯЕМ НАМЕРЕНИЕ
        await query.edit_message_text("Отлично. Прежде чем мы продолжим, пожалуйста, напишите, как к вам обращаться.")

    elif data == 'show_faq_menu':
        keyboard = [
            [InlineKeyboardButton("Как я получу и оплачу документ?", callback_data='faq_payment_and_delivery')],
            [InlineKeyboardButton("Сколько стоят услуги?", callback_data='faq_price')],
            [InlineKeyboardButton("Это просто шаблон?", callback_data='faq_template')],
            [InlineKeyboardButton("Сколько времени это займет?", callback_data='faq_timing')],
            [InlineKeyboardButton("Есть ли гарантии?", callback_data='faq_guarantee')],
            [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')]
        ]
        await query.edit_message_text("Выберите интересующий вас вопрос:", reply_markup=InlineKeyboardMarkup(keyboard))
        
    elif data.startswith('faq_'):
        faq_key = data.split('_', 1)[1]
        answer_text = FAQ_ANSWERS.get(faq_key, "Ответ не найден.")
        keyboard = [[InlineKeyboardButton("⬅️ К списку вопросов", callback_data='show_faq_menu')]]
        await query.edit_message_text(answer_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)

    elif data == 'my_tickets':
        await my_tickets_action(update, context)

    elif data.startswith('info_ticket_'):
        await query.answer("Подробная информация и чат по обращению будут доступны в следующих версиях.", show_alert=True)

    elif data == 'back_to_start':
        await show_main_menu(update, context)

    elif data.startswith('take_') or data.startswith('decline_'):
        action, ticket_id, client_user_id = data.split('_')
        original_text = query.message.text
        operator_name = query.from_user.full_name
        
        status_text = "✅ Взято в работу" if action == 'take' else "❌ Отклонено"
        new_text = f"{original_text}\n\n**{status_text} оператором {operator_name}**"
        
        await query.edit_message_text(new_text, parse_mode=ParseMode.MARKDOWN, reply_markup=None)
        
        # Обновляем статус в базе данных
        with tickets_lock:
            if ticket_id in tickets_db:
                new_status = 'in_progress' if action == 'take' else 'declined'
                tickets_db[ticket_id]['status'] = new_status
                save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)

        if action == 'take':
            try:
                await context.bot.send_message(
                    chat_id=int(client_user_id),
                    text=f"✅ *Статус обновлен:* Ваша заявка №{ticket_id} принята в работу. Специалист уже изучает ваши материалы и скоро свяжется с вами.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                logger.error(f"Failed to send status update to client {client_user_id}: {e}")

# --- 7. ГЛАВНЫЙ ОБРАБОТЧИК СООБЩЕНИЙ ---

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = str(user.id)
    state_data = user_states.get(user_id)

    if not state_data or 'state' not in state_data:
        await show_main_menu(update, context)
        return

    state = state_data['state']

    if state == 'ask_name':
        if not update.message.text or update.message.text.startswith('/'):
            await update.message.reply_text("Пожалуйста, отправьте ваше имя текстом.")
            return
            
        user_states[user_id]['name'] = update.message.text
        user_states[user_id]['state'] = 'collecting_data'
        save_json_data(user_states, USER_STATES_FILE, states_lock) # <-- СОХРАНЯЕМ
        
        name = user_states[user_id]['name']
        ticket_id = str(get_and_increment_ticket_number())
        user_states[user_id]['ticket_number'] = ticket_id
        save_json_data(user_states, USER_STATES_FILE, states_lock) # <-- СОХРАНЯЕМ СНОВА
        
        with tickets_lock:
            tickets_db[ticket_id] = { "user_id": user_id, "user_name": name, "category": state_data['category'], "status": "new", "creation_date": datetime.now().isoformat() }
            save_json_data(tickets_db, TICKETS_DB_FILE, tickets_lock)

        user_link = f"tg://user?id={user_id}"
        timestamp = datetime.now().strftime('%d.%m.%Y %H:%M')
        
        header_text = (
            f"🔔 **ЗАЯВКА №{ticket_id}**\n\n"
            f"**Время:** `{timestamp}`\n"
            f"**Категория:** `{state_data['category']}`\n\n"
            f"**Клиент:** `{escape_markdown(name)}`\n"
            f"**Контакт:** [Написать клиенту]({user_link})\n\n"
            "--- НАЧАЛО ЗАЯВКИ ---"
        )
        
        operator_keyboard = [[
            InlineKeyboardButton("✅ Взять в работу", callback_data=f"take_{ticket_id}_{user_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"decline_{ticket_id}_{user_id}")
        ]]
        
        await context.bot.send_message(
            chat_id=CHAT_ID_FOR_ALERTS, 
            text=header_text, 
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(operator_keyboard)
        )
        
        reply_keyboard = [["✅ Завершить отправку материалов"]]
        await update.message.reply_text(
            f"Приятно познакомиться, {escape_markdown(name)}!\n\n"
            f"Вашему обращению присвоен **номер {ticket_id}**.\n\n"
            "Теперь расскажите о вашей ситуации, отправляя текст, фото, документы или голосовые сообщения. Когда закончите, нажмите кнопку ниже.",
            reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
            parse_mode=ParseMode.MARKDOWN
        )

    elif state == 'collecting_data':
        ticket_id = state_data.get('ticket_number', 'N/A')
        if update.message.text == "✅ Завершить отправку материалов":
            footer_text = f"--- КОНЕЦ ЗАЯВКИ №{ticket_id} ---"
            await context.bot.send_message(chat_id=CHAT_ID_FOR_ALERTS, text=footer_text)
            
            await update.message.reply_text(
                f"✅ *Отлично! Ваша заявка №{ticket_id} полностью сформирована и передана оператору.*\n\n"
                "«Дирижер» изучит все материалы. Отслеживайте статус вашего обращения в разделе *«Мои обращения»*.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode=ParseMode.MARKDOWN
            )
            del user_states[user_id]
            save_json_data(user_states, USER_STATES_FILE, states_lock)
            return
        
        await context.bot.forward_message(
            chat_id=CHAT_ID_FOR_ALERTS,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )

# --- 8. ЗАПУСК БОТА ---
def main() -> None:
    logger.info("Starting bot version 5.0 'Triumph Core'...")
    application = Application.builder().token(NEURO_ADVOCAT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(inline_button_handler))
    application.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, message_handler))

    logger.info("Application starting polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
