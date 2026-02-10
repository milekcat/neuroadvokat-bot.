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

# --- НАСТРОЙКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ---
NEURO_ADVOCAT_TOKEN = os.environ.get('NEURO_ADVOCAT_TOKEN')
CHAT_ID_FOR_ALERTS = os.environ.get('CHAT_ID_FOR_ALERTS')
TELEGRAM_CHANNEL_URL = os.environ.get('TELEGRAM_CHANNEL_URL')

# Критически важная проверка переменных
if not NEURO_ADVOCAT_TOKEN or not CHAT_ID_FOR_ALERTS:
    logger.critical("FATAL ERROR: A required environment variable was NOT found.")
    logger.critical("Please ensure 'NEURO_ADVOCAT_TOKEN' and 'CHAT_ID_FOR_ALERTS' are set correctly.")
    exit(1)

# --- ПУТИ К ФАЙЛАМ В ПОСТОЯННОМ ХРАНИЛИЩЕ (RAILWAY VOLUME) ---
DATA_DIR = Path(os.environ.get("RAILWAY_VOLUME_MOUNT_PATH", "/app/data"))
TICKET_COUNTER_FILE = DATA_DIR / "ticket_counter.txt"
USER_STATES_FILE = DATA_DIR / "user_states.json"
MESSAGE_MAP_FILE = DATA_DIR / "message_map.json" # Файл для связи сообщений оператора и клиента

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

user_states = load_json_data(USER_STATES_FILE, states_lock)
message_map = load_json_data(MESSAGE_MAP_FILE, message_map_lock)

# --- ТЕКСТЫ И КОНСТАНТЫ (ВЗЯТЫ ИЗ ВАШЕЙ ПЕРВОЙ ВЕРСИИ) ---
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
        await update.message.reply_text("Нечего отменять. Вы уже в главном меню.", reply_markup=ReplyKeyboardRemove())
    await show_main_menu(update, context)


# --- ОБРАБОТЧИКИ КНОПОК И СООБЩЕНИЙ ---

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
            logger.info(f"Operator {user_id} took ticket {ticket_number} for client {client_user_id_str}.")
        except Exception as e:
            logger.error(f"Failed to send 'take' status update to client {client_user_id_str}: {e}")
        
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

    if data.startswith('op_ask_'):
        parts = data.split('_')
        ticket_number, client_user_id_str = parts[1], parts[2]
        try:
            await context.bot.send_message(chat_id=int(client_user_id_str), text=f"Здравствуйте! По вашей заявке №{ticket_number} требуются уточнения. Специалист скоро напишет вам.", parse_mode='Markdown')
            await query.answer(text="✅ Уведомление клиенту отправлено!", show_alert=True)
        except Exception as e:
            await query.answer(text="❌ Не удалось отправить сообщение клиенту.", show_alert=True)
            logger.error(f"Failed to send 'ask_info' message for ticket {ticket_number}: {e}")
        return

    if data.startswith('op_review_'):
        parts = data.split('_')
        ticket_number, client_user_id_str = parts[1], parts[2]
        try:
            await context.bot.send_message(chat_id=int(client_user_id_str), text=f"📄 **Документ по заявке №{ticket_number} готов!**\n\nМы отправили вам на ознакомление версию с водяными знаками.", parse_mode='Markdown')
            await query.answer(text="✅ Уведомление о готовности отправлено!", show_alert=True)
        except Exception as e:
            await query.answer(text="❌ Не удалось отправить сообщение клиенту.", show_alert=True)
            logger.error(f"Failed to send 'review' message for ticket {ticket_number}: {e}")
        return

    if data.startswith('op_close_'):
        parts = data.split('_')
        ticket_number, client_user_id_str = parts[1], parts[2]
        operator_name = query.from_user.full_name.replace('_', '\_').replace('*', '\*').replace('`', '\`')
        original_text = query.message.text_markdown_v2
        new_text = f"{original_text}\n\n*🏁 Заявка закрыта оператором {operator_name}*"
        try:
            await query.edit_message_text(new_text, parse_mode='MarkdownV2', reply_markup=None)
            await context.bot.send_message(chat_id=int(client_user_id_str), text=f"✅ Ваша заявка №{ticket_number} успешно завершена. Спасибо, что выбрали нас!", parse_mode='Markdown')
            logger.info(f"Operator {user_id} closed ticket {ticket_number}.")
        except Exception as e:
            logger.error(f"Error during closing ticket {ticket_number}: {e}")
        return

    if data.startswith('decline_'):
        parts = data.split('_')
        ticket_number = parts[1]
        original_text = query.message.text_markdown_v2
        operator_name = query.from_user.full_name.replace('_', '\_').replace('*', '\*').replace('`', '\`')
        new_text = f"{original_text}\n\n*❌ Отклонено оператором {operator_name}*"
        await query.edit_message_text(new_text, parse_mode='MarkdownV2', reply_markup=None)
        return
    
    # Обработчики навигации по меню
    if data == 'back_to_start':
        if str(query.from_user.id) in user_states:
            del user_states[str(query.from_user.id)]
            save_json_data(user_states, USER_STATES_FILE, states_lock)
        await show_main_menu(update, context)
        return
        
    if data == 'show_services_menu':
        keyboard = [[InlineKeyboardButton(f"⚖️ {CATEGORY_NAMES['civil']}", callback_data='service_civil')], [InlineKeyboardButton(f"👨‍👩‍👧‍👦 {CATEGORY_NAMES['family']}", callback_data='service_family')], [InlineKeyboardButton(f"🏠 {CATEGORY_NAMES['housing']}", callback_data='service_housing')], [InlineKeyboardButton(f"🛡️ {CATEGORY_NAMES['military']}", callback_data='service_military')], [InlineKeyboardButton(f"🏢 {CATEGORY_NAMES['admin']}", callback_data='service_admin')], [InlineKeyboardButton(f"💼 {CATEGORY_NAMES['business']}", callback_data='service_business')], [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')]]
        await query.edit_message_text("Выберите сферу, в которой вам требуется помощь:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data == 'show_faq_menu':
        keyboard = [[InlineKeyboardButton("Как я получу и оплачу документ?", callback_data='faq_payment_and_delivery')], [InlineKeyboardButton("Сколько стоят услуги?", callback_data='faq_price')], [InlineKeyboardButton("Это просто шаблон?", callback_data='faq_template')], [InlineKeyboardButton("Сколько времени это займет?", callback_data='faq_timing')], [InlineKeyboardButton("Есть ли гарантии?", callback_data='faq_guarantee')], [InlineKeyboardButton("⬅️ Назад в меню", callback_data='back_to_start')]]
        await query.edit_message_text("Выберите интересующий вас вопрос:", reply_markup=InlineKeyboardMarkup(keyboard))
        return

    if data.startswith('faq_'):
        faq_key = data.split('_', 1)[1]
        answer_text = FAQ_ANSWERS.get(faq_key, "Ответ не найден.")
        keyboard = [[InlineKeyboardButton("⬅️ К списку вопросов", callback_data='show_faq_menu')]]
        await query.edit_message_text(answer_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    if data.startswith('service_'):
        service_key = data.split('_')[1]
        text = SERVICE_DESCRIPTIONS.get(service_key, "Описание не найдено.")
        keyboard = [[InlineKeyboardButton("✅ Подать заявку по этой теме", callback_data=f'order_{service_key}')], [InlineKeyboardButton("⬅️ К списку услуг", callback_data='show_services_menu')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        return

    if data.startswith('order_'):
        user_id = str(query.from_user.id)
        category_key = data.split('_')[1]
        category_name = CATEGORY_NAMES.get(category_key, "Неизвестная категория")
        user_states[user_id] = {'category': category_name, 'state': 'ask_name'}
        save_json_data(user_states, USER_STATES_FILE, states_lock)
        await query.edit_message_text("Отлично. Прежде чем мы продолжим, пожалуйста, напишите, как к вам обращаться.")
        return

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = str(update.effective_user.id)
    current_state_data = user_states.get(user_id)
    
    if not current_state_data:
        # Если пользователь не в процессе заявки, можно отправить подсказку
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
            f"**Контакт:** [Профиль клиента]({user_link})\n\n"
            "--- НАЧАЛО ЗАЯВКИ ---\n\n"
            "**ВАЖНО:** Чтобы ответить клиенту, используйте функцию **«Ответить» (Reply)** на его пересланные сообщения."
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
            logger.error(f"Failed to send ticket header for {ticket_number} to the alert chat: {e}")

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

async def reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Проверяем, что это ответ оператора в рабочем чате
    if str(update.message.chat_id) != str(CHAT_ID_FOR_ALERTS): return
    
    replied_message = update.message.reply_to_message
    if not replied_message: return

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
            await update.message.reply_text(f"⚠️ Не удалось доставить ответ клиенту. Ошибка: {e}")

# --- ОСНОВНАЯ ФУНКЦИЯ ЗАПУСКА ---
def main() -> None:
    logger.info("Starting bot...")
    
    application = Application.builder().token(NEURO_ADVOCAT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CallbackQueryHandler(inline_button_handler))
    
    # Обработчик ответов оператора (должен идти до основного message_handler)
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
