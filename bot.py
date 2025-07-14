# === Импорт библиотек ===
import asyncio
from dotenv import load_dotenv
load_dotenv()
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
import datetime
import calendar
import openpyxl # Для работы с Excel файлами
import os # Для проверки существования файла и переменных окружения
from dotenv import load_dotenv # Для загрузки переменных окружения
import logging # Для логирования

# Загружаем переменные окружения из .env файла
load_dotenv()

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"), # Логи в файл
        logging.StreamHandler() # Логи в консоль
    ]
)
logger = logging.getLogger(__name__)

# Убедитесь, что ваш db.py файл находится в той же директории
from db import (
    init_db, update_user_username, get_user_role, get_all_users_with_roles,
    set_user_role, get_tickets_by_user_id, get_tickets_by_date_range,
    create_ticket, close_ticket, SUPERADMIN_ID,
    get_ticket_by_code, get_messages_by_ticket, get_attachments_by_ticket,
    get_all_registered_users, get_all_admins_and_moderators,
    assign_ticket, unassign_ticket, update_ticket_details,
    get_stale_tickets, get_response_templates, add_response_template,
    delete_response_template, is_admin_or_moderator, is_superadmin,
    add_attachment, add_message, add_ticket_feedback
)

from languages import LANGUAGES

# Токен бота
API_TOKEN = os.getenv('API_TOKEN', 'YOUR_BOT_TOKEN_HERE') # Получаем токен из .env
# SUPERADMIN_ID = int(os.getenv('SUPERADMIN_ID', 'YOUR_SUPERADMIN_ID_HERE')) # Получаем ID супер-админа из .env
# Если SUPERADMIN_ID определен в db.py, используем его оттуда.
# Если вы хотите, чтобы SUPERADMIN_ID был из .env, убедитесь, что он там есть и раскомментируйте строку выше.

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())

# === States ===

class TicketStates(StatesGroup):
    waiting_for_ticket_text = State()
    waiting_for_priority = State()
    waiting_for_category = State()
    waiting_for_admin_reply = State()
    waiting_for_feedback_text = State()
    waiting_for_template_name = State()
    waiting_for_template_text = State()
    waiting_for_export_dates = State()
    waiting_for_edit_ticket_text = State()
    waiting_for_edit_ticket_priority = State()
    waiting_for_edit_ticket_category = State()

# === ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ===

async def get_text(user_id: int, key: str, **kwargs) -> str:
    """Возвращает текст по ключу с учетом языка пользователя."""
    state = dp.current_state(user=user_id)
    data = await state.get_data()
    lang_code = data.get('language', 'ru') # по умолчанию 'ru'
    
    if lang_code in LANGUAGES and key in LANGUAGES[lang_code]:
        return LANGUAGES[lang_code][key].format(**kwargs)
    return f"[{key}]" # Если текст не найден, возвращаем ключ в скобках

async def get_user_main_keyboard(user_id: int) -> ReplyKeyboardMarkup:
    """Возвращает основную клавиатуру для обычного пользователя."""
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    kb.add(KeyboardButton(await get_text(user_id, "new_ticket_button")))
    kb.add(KeyboardButton(await get_text(user_id, "my_tickets_button")))
    
    role = await get_user_role(user_id)
    if role in ['admin', 'moderator']:
        kb.add(KeyboardButton(await get_text(user_id, "admin_panel_button")))
    elif role == 'superadmin':
        kb.add(KeyboardButton(await get_text(user_id, "superadmin_panel_button")))
    
    kb.add(KeyboardButton(await get_text(user_id, "language_button")))
    return kb

async def get_admin_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """Возвращает основную клавиатуру для админа/модератора/супер-админа."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "view_all_tickets_button"), callback_data="admin_view_tickets"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "admin_templates"), callback_data="admin_templates"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "admin_export"), callback_data="admin_export"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "admin_stale_tickets"), callback_data="admin_stale_tickets"))
    
    if await is_superadmin(user_id):
        kb.add(InlineKeyboardButton(await get_text(user_id, "admin_manage_users"), callback_data="admin_manage_users"))
    
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="main_menu"))
    return kb

async def get_back_button(user_id: int, callback_data: str) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру с кнопкой 'Назад'."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data=callback_data))
    return kb

async def get_priority_keyboard(user_id: int, current_ticket_code: str = None) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для выбора приоритета."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_priority_low"), callback_data="set_priority:Низкий"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_priority_medium"), callback_data="set_priority:Средний"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_priority_high"), callback_data="set_priority:Высокий"))
    
    if current_ticket_code:
        kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data=f"edit_ticket_user:{current_ticket_code}"))
    else:
        kb.add(InlineKeyboardButton(await get_text(user_id, "cancel_button"), callback_data="cancel_ticket_creation"))
    return kb

async def get_category_keyboard(user_id: int, current_ticket_code: str = None) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для выбора категории."""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_category_general"), callback_data="set_category:Общий вопрос"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_category_technical"), callback_data="set_category:Техническая проблема"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_category_financial"), callback_data="set_category:Финансовый вопрос"))
    
    if current_ticket_code:
        kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data=f"edit_ticket_user:{current_ticket_code}"))
    else:
        kb.add(InlineKeyboardButton(await get_text(user_id, "cancel_button"), callback_data="cancel_ticket_creation"))
    return kb

async def get_ticket_detail_keyboard(user_id: int, ticket_code: str) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для детального просмотра заявки."""
    kb = InlineKeyboardMarkup(row_width=2)
    role = await get_user_role(user_id)
    ticket = await get_ticket_by_code(ticket_code)

    if not ticket:
        return kb # Если заявка не найдена, возвращаем пустую клавиатуру

    # Кнопки для пользователя, если это его заявка и она открыта
    if ticket[5] == user_id and ticket[3] == 'open': # ticket[5] - user_id, ticket[3] - status
        kb.add(InlineKeyboardButton(await get_text(user_id, "reply_button"), callback_data=f"user_reply_to_ticket:{ticket_code}"))
        if ticket[8] is None: # Если заявка не назначена
            kb.add(InlineKeyboardButton(await get_text(user_id, "edit_ticket_button"), callback_data=f"edit_ticket_user:{ticket_code}"))
        kb.add(InlineKeyboardButton(await get_text(user_id, "close_ticket_button"), callback_data=f"close_ticket_admin:{ticket_code}")) # Пользователь может закрыть свою заявку

    # Кнопки для админа/модератора
    if role in ['admin', 'moderator', 'superadmin']:
        if ticket[3] == 'open': # Если заявка открыта
            kb.add(InlineKeyboardButton(await get_text(user_id, "reply_button"), callback_data=f"reply_to_ticket:{ticket_code}"))
            kb.add(InlineKeyboardButton(await get_text(user_id, "close_ticket_button"), callback_data=f"close_ticket_admin:{ticket_code}"))
            
            if ticket[8] is None: # Если заявка не назначена
                kb.add(InlineKeyboardButton(await get_text(user_id, "assign_ticket_button"), callback_data=f"assign_ticket:{ticket_code}"))
            else: # Если заявка назначена
                assigned_user_info = await bot.get_chat(ticket[8])
                assigned_username = assigned_user_info.username if assigned_user_info.username else f"ID {ticket[8]}"
                kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_assigned", assigned=assigned_username), callback_data=f"assign_ticket:{ticket_code}"))
        
        kb.add(InlineKeyboardButton(await get_text(user_id, "send_template_button"), callback_data=f"send_template:{ticket_code}"))

    kb.add(InlineKeyboardButton(await get_text(user_id, "history_button"), callback_data=f"history_ticket:{ticket_code}"))
    
    # Кнопка "Назад" в зависимости от контекста
    if role in ['admin', 'moderator', 'superadmin']:
        kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_view_tickets"))
    else:
        kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="my_tickets_button_callback"))
    
    return kb

async def get_rating_keyboard(user_id: int, ticket_code: str) -> InlineKeyboardMarkup:
    """Возвращает клавиатуру для оценки заявки."""
    kb = InlineKeyboardMarkup(row_width=5)
    for i in range(1, 6):
        kb.insert(InlineKeyboardButton(f"⭐ {i}", callback_data=f"rate_ticket:{ticket_code}:{i}"))
    return kb

async def send_tickets_list(message_or_callback: types.Message | types.CallbackQuery, tickets: list[tuple], title: str, back_callback_data: str, is_user_context: bool = False):
    """Отправляет список заявок с пагинацией и кнопками деталей."""
    user_id = message_or_callback.from_user.id
    
    if not tickets:
        text_to_send = await get_text(user_id, "no_tickets_found")
        reply_markup = await get_back_button(user_id, back_callback_data)
        if isinstance(message_or_callback, types.CallbackQuery):
            await message_or_callback.message.edit_text(text_to_send, reply_markup=reply_markup)
        else:
            await message_or_callback.answer(text_to_send, reply_markup=reply_markup)
        return

    tickets_per_page = 5
    num_pages = (len(tickets) + tickets_per_page - 1) // tickets_per_page

    current_page = 0
    if isinstance(message_or_callback, types.CallbackQuery):
        state = dp.current_state(user=user_id)
        data = await state.get_data()
        current_page = data.get('current_tickets_page', 0)
    
    start_index = current_page * tickets_per_page
    end_index = min((current_page + 1) * tickets_per_page, len(tickets))
    
    paginated_tickets = tickets[start_index:end_index]

    ticket_list_text = f"<b>{title}</b>\n\n"
    for ticket in paginated_tickets:
        code, text, created_at, status, username, ticket_user_id, priority, category, assigned_to_id, rating, feedback_text, last_admin_reply_at = ticket
        
        # Получаем переведенные значения для статуса, приоритета, категории
        lang_code = (await dp.current_state(user=user_id).get_data()).get('language', 'ru')
        translated_status = LANGUAGES[lang_code].get(f'ticket_status_{status.lower()}', status)
        translated_priority = LANGUAGES[lang_code].get(f'ticket_priority_{priority.lower()}', priority)
        translated_category = LANGUAGES[lang_code].get(f'ticket_category_{category.lower().replace(" ", "_")}', category)

        ticket_list_text += (
            f"<b>{await get_text(user_id, 'ticket_detail_title', code=code)}</b>\n"
            f"{await get_text(user_id, 'ticket_text', text=text[:50] + '...' if len(text) > 50 else text)}\n"
            f"{await get_text(user_id, 'ticket_created_at', created=created_at)}\n"
            f"{await get_text(user_id, 'ticket_status', status=translated_status)}\n"
            f"{await get_text(user_id, 'ticket_priority', priority=translated_priority)}\n"
            f"{await get_text(user_id, 'ticket_category', category=translated_category)}\n"
        )
        if assigned_to_id:
            try:
                assigned_user_info = await bot.get_chat(assigned_to_id)
                assigned_username = assigned_user_info.username if assigned_user_info.username else f"ID {assigned_to_id}"
                ticket_list_text += f"{await get_text(user_id, 'ticket_assigned', assigned=assigned_username)}\n"
            except Exception:
                ticket_list_text += f"{await get_text(user_id, 'ticket_assigned', assigned=f'ID {assigned_to_id} (не найден)')}\n"
        else:
            ticket_list_text += f"{await get_text(user_id, 'ticket_assigned', assigned=(await get_text(user_id, 'unassigned_tickets')).lower())}\n"
        
        ticket_list_text += "\n" # Пустая строка между заявками

    kb = InlineKeyboardMarkup(row_width=3)
    if num_pages > 1:
        if current_page > 0:
            kb.insert(InlineKeyboardButton("⬅️", callback_data=f"tickets_page:{current_page - 1}:{back_callback_data}:{int(is_user_context)}"))
        kb.insert(InlineKeyboardButton(f"{current_page + 1}/{num_pages}", callback_data="ignore_pagination"))
        if current_page < num_pages - 1:
            kb.insert(InlineKeyboardButton("➡️", callback_data=f"tickets_page:{current_page + 1}:{back_callback_data}:{int(is_user_context)}"))
    
    # Кнопки деталей для каждой заявки на текущей странице
    for ticket in paginated_tickets:
        code = ticket[0]
        callback_prefix = "history_ticket_user" if is_user_context else "ticket_detail"
        kb.add(InlineKeyboardButton(f"🔍 {code}", callback_data=f"{callback_prefix}:{code}"))

    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data=back_callback_data))

    if isinstance(message_or_callback, types.CallbackQuery):
        await message_or_callback.message.edit_text(ticket_list_text, parse_mode="HTML", reply_markup=kb)
        await message_or_callback.answer()
    else:
        await message_or_callback.answer(ticket_list_text, parse_mode="HTML", reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("tickets_page:"), state="*")
async def tickets_pagination_handler(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    parts = c.data.split(":")
    new_page = int(parts[1])
    back_callback_data = parts[2]
    is_user_context = bool(int(parts[3]))

    await state.update_data(current_tickets_page=new_page)

    # Пересобираем список заявок с учетом фильтров, если они есть
    tickets = []
    if is_user_context:
        tickets = await get_tickets_by_user_id(user_id)
    else:
        data = await state.get_data()
        status = data.get('filter_status')
        priority = data.get('filter_priority')
        category = data.get('filter_category')
        assigned_to_id = data.get('filter_assigned_to_id')
        start_date = data.get('filter_start_date')
        end_date = data.get('filter_end_date')
        
        tickets = await get_tickets_by_date_range(
            start_date=start_date,
            end_date=end_date,
            status=status,
            priority=priority,
            category=category,
            assigned_to_id=assigned_to_id
        )
    
    # Формируем заголовок на основе активных фильтров для админского просмотра
    title_text = await get_text(user_id, "view_all_tickets_button")
    if not is_user_context:
        filter_summary = []
        lang_code = (await dp.current_state(user=user_id).get_data()).get('language', 'ru')
        if status: filter_summary.append(f"{LANGUAGES[lang_code]['ticket_status'].split(':')[0]}: {LANGUAGES[lang_code].get(f'ticket_status_{status}', status)}")
        if priority: filter_summary.append(f"{LANGUAGES[lang_code]['ticket_priority'].split(':')[0]}: {LANGUAGES[lang_code].get(f'ticket_priority_{priority.lower()}', priority)}")
        if category: filter_summary.append(LANGUAGES[lang_code].get(f'ticket_category_{category.lower().replace(" ", "_")}', category))
        if assigned_to_id is not None:
            if assigned_to_id == 0:
                filter_summary.append(f"{LANGUAGES[lang_code]['ticket_assigned'].split(':')[0]}: {LANGUAGES[lang_code]['unassigned_tickets']}")
            else:
                try:
                    assigned_user_info = await bot.get_chat(assigned_to_id)
                    assigned_username = assigned_user_info.username if assigned_user_info.username else f"ID {assigned_to_id}"
                    filter_summary.append(f"{LANGUAGES[lang_code]['ticket_assigned'].split(':')[0]}: @{assigned_username}")
                except Exception:
                    filter_summary.append(f"{LANGUAGES[lang_code]['ticket_assigned'].split(':')[0]}: ID {assigned_to_id} (не найден)")
        if start_date: filter_summary.append(f"{LANGUAGES[lang_code]['export_start_date'].split('(')[0].strip()}: {start_date}")
        if end_date: filter_summary.append(f"{LANGUAGES[lang_code]['export_end_date'].split('(')[0].strip()}: {end_date}")

        if filter_summary:
            title_text += "\n" + " | ".join(filter_summary)
        else:
            title_text += "\n(" + (await get_text(user_id, "export_status_all")).lower() + ")"

    await send_tickets_list(c, tickets, title_text, back_callback_data, is_user_context)


async def generate_tickets_excel(tickets: list[tuple], file_name: str):
    """Генерирует Excel файл с данными о заявках."""
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Tickets"

    # Заголовки столбцов
    headers = [
        "Код заявки", "Текст", "Дата создания", "Статус", "Username пользователя",
        "ID пользователя", "Приоритет", "Категория", "Назначено ID", "Рейтинг",
        "Отзыв", "Последний ответ админа"
    ]
    sheet.append(headers)

    for ticket in tickets:
        # Преобразуем tuple в list для возможности изменения
        ticket_list = list(ticket) 
        
        # Получаем username назначенного админа/модератора, если есть
        if ticket_list[8]: # assigned_to_id
            try:
                assigned_user_info = await bot.get_chat(ticket_list[8])
                assigned_username = assigned_user_info.username if assigned_user_info.username else f"ID {ticket_list[8]}"
                ticket_list[8] = assigned_username # Заменяем ID на username
            except Exception:
                ticket_list[8] = f"ID {ticket_list[8]} (не найден)"
        else:
            ticket_list[8] = "Не назначено" # Для NULL значений

        sheet.append(ticket_list)

    workbook.save(file_name)


# === Хендлеры ===

@dp.message_handler(commands=['start'], state="*")
async def cmd_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Инициализация базы данных и установка роли супер-админа, если необходимо
    await init_db()
    # Обновляем username пользователя в базе данных при каждом старте
    await update_user_username(user_id, username)

    role = await get_user_role(user_id)
    if not role: # Если пользователь новый, устанавливаем ему роль 'user'
        await set_user_role(user_id, 'user', username)
        role = 'user' # Обновляем роль для текущей сессии
        logger.info(f"Новый пользователь {user_id} (@{username}) зарегистрирован с ролью 'user'.")
    else:
        logger.info(f"Пользователь {user_id} (@{username}) с ролью '{role}' запустил бота.")

    await state.finish() # Сбрасываем все состояния
    
    welcome_text = await get_text(user_id, "start_welcome")
    await message.answer(welcome_text, reply_markup=await get_user_main_keyboard(user_id))

@dp.message_handler(lambda message: message.text == LANGUAGES['ru']['new_ticket_button'] or message.text == LANGUAGES['en']['new_ticket_button'], state="*")
async def new_ticket(message: types.Message):
    user_id = message.from_user.id
    await message.answer(await get_text(user_id, "ask_for_ticket_text"), reply_markup=await get_back_button(user_id, "cancel_ticket_creation"))
    await TicketStates.waiting_for_ticket_text.set()

@dp.message_handler(content_types=[types.ContentType.TEXT, types.ContentType.PHOTO, types.ContentType.DOCUMENT], state=TicketStates.waiting_for_ticket_text)
async def process_ticket_text_and_attachments(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text

    # Проверка, что сообщение не является командой отмены
    if text == (await get_text(user_id, "cancel_button")):
        await state.finish()
        await message.answer(await get_text(user_id, "back_to_main_user_menu"), reply_markup=await get_user_main_keyboard(user_id))
        return

    async with state.proxy() as data:
        data['ticket_text'] = text
        data['attachments'] = [] # Список для хранения file_id вложений

    # Если есть фото или документ, сохраняем их file_id
    if message.photo:
        data['attachments'].append({'file_id': message.photo[-1].file_id, 'file_type': 'photo', 'file_name': None})
    if message.document:
        data['attachments'].append({'file_id': message.document.file_id, 'file_type': 'document', 'file_name': message.document.file_name})
    
    await message.answer(await get_text(user_id, "ask_priority"), reply_markup=await get_priority_keyboard(user_id))
    await TicketStates.waiting_for_priority.set()


@dp.callback_query_handler(lambda c: c.data.startswith("set_priority:"), state=TicketStates.waiting_for_priority)
async def process_priority_selection(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    priority = c.data.split(":")[1]
    
    async with state.proxy() as data:
        data['priority'] = priority
    
    await c.message.edit_text(await get_text(user_id, "ask_category"), reply_markup=await get_category_keyboard(user_id))
    await TicketStates.waiting_for_category.set()
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("set_category:"), state=TicketStates.waiting_for_category)
async def process_category_selection(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    category = c.data.split(":")[1]
    
    async with state.proxy() as data:
        ticket_text = data.get('ticket_text')
        priority = data.get('priority')
        attachments = data.get('attachments', []) # Получаем вложения

    code, created_at, status = await create_ticket(user_id, ticket_text, priority, category)

    # Сохраняем вложения в БД
    for attachment in attachments:
        await add_attachment(code, attachment['file_id'], attachment['file_name'], attachment['file_type'])

    await c.message.edit_text(await get_text(user_id, "ticket_text_received"), reply_markup=await get_user_main_keyboard(user_id))
    await c.message.answer(
        await get_text(user_id, "ticket_created_info", code=code, created_at=created_at, status=status),
        parse_mode="Markdown"
    )
    await state.finish()
    await c.answer()


@dp.callback_query_handler(lambda c: c.data == "cancel_ticket_creation", state="*")
async def cancel_ticket_creation(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    await state.finish()
    await c.message.edit_text(await get_text(user_id, "back_to_main_user_menu"), reply_markup=await get_user_main_keyboard(user_id))
    await c.answer()


@dp.message_handler(lambda message: message.text == LANGUAGES['ru']['my_tickets_button'] or message.text == LANGUAGES['en']['my_tickets_button'], state="*")
async def my_tickets(message: types.Message):
    user_id = message.from_user.id
    tickets = await get_tickets_by_user_id(user_id)
    await send_tickets_list(message, tickets, await get_text(user_id, "your_tickets_title"), "main_menu", is_user_context=True)

@dp.callback_query_handler(lambda c: c.data == "my_tickets_button_callback", state="*")
async def my_tickets_callback(c: types.CallbackQuery):
    user_id = c.from_user.id
    tickets = await get_tickets_by_user_id(user_id)
    await send_tickets_list(c, tickets, await get_text(user_id, "your_tickets_title"), "main_menu", is_user_context=True)


@dp.callback_query_handler(lambda c: c.data.startswith("history_ticket:"), state="*")
@dp.callback_query_handler(lambda c: c.data.startswith("history_ticket_user:"), state="*")
async def show_ticket_history(c: types.CallbackQuery):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]
    is_user_context = c.data.startswith("history_ticket_user:")

    ticket = await get_ticket_by_code(ticket_code)
    if not ticket:
        await c.message.answer(await get_text(user_id, "ticket_code_not_found", code=ticket_code)) # Добавьте этот ключ в languages.py
        await c.answer()
        return

    # Проверка доступа для пользователя
    if is_user_context and ticket[5] != user_id: # ticket[5] - user_id из БД
        await c.message.answer(await get_text(user_id, "not_your_ticket")) # Добавьте этот ключ в languages.py
        await c.answer()
        return

    messages = await get_messages_by_ticket(ticket_code)
    attachments = await get_attachments_by_ticket(ticket_code) # Получаем вложения

    history_text = [await get_text(user_id, "ticket_detail_title", code=ticket_code) + "\n"]
    for msg in messages:
        role, msg_text, timestamp = msg
        sender_info = ""
        # Получаем переведенную роль
        lang_code = (await dp.current_state(user=user_id).get_data()).get('language', 'ru')
        translated_role = LANGUAGES[lang_code].get(f'role_{role}', role)
        
        history_text.append(f"<b>[{timestamp} {translated_role}]:</b> {msg_text}")
    
    # Добавляем информацию о вложениях
    if attachments:
        history_text.append("\n<b>Вложения:</b>")
        for file_id, file_name, file_type in attachments:
            history_text.append(f"- {file_type.capitalize()}: {file_name if file_name else file_id}")

    await c.message.edit_text("\n".join(history_text), parse_mode="HTML", reply_markup=await get_back_button(user_id, f"ticket_detail:{ticket_code}" if not is_user_context else "my_tickets_button_callback"))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("reply_to_ticket:"), state="*")
async def reply_to_ticket_handler(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]

    ticket = await get_ticket_by_code(ticket_code)
    if not ticket or ticket[3] != 'open': # Проверяем, что заявка существует и открыта
        await c.message.answer(await get_text(user_id, "ticket_not_open_for_reply"))
        await c.answer()
        return

    await state.update_data(current_reply_ticket=ticket_code)
    await c.message.edit_text(await get_text(user_id, "reply_message_prompt", code=ticket_code), reply_markup=await get_back_button(user_id, f"ticket_detail:{ticket_code}"))
    await TicketStates.waiting_for_admin_reply.set()
    await c.answer()

@dp.message_handler(content_types=[types.ContentType.TEXT, types.ContentType.PHOTO, types.ContentType.DOCUMENT], state=TicketStates.waiting_for_admin_reply)
async def process_admin_reply(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    text = message.text

    # Проверка, что сообщение не является командой отмены
    if text == (await get_text(user_id, "back_button")):
        await state.finish()
        data = await state.get_data()
        ticket_code = data.get('current_reply_ticket')
        if ticket_code:
            # Нужно имитировать CallbackQuery для возврата к деталям заявки
            fake_callback = types.CallbackQuery(id='fake_id', from_user=message.from_user, message=message, chat_instance='fake_instance', data=f"ticket_detail:{ticket_code}")
            await show_ticket_detail(fake_callback)
        else:
            await message.answer(await get_text(user_id, "back_to_main_user_menu"), reply_markup=await get_user_main_keyboard(user_id))
        return
        
    data = await state.get_data()
    ticket_code = data.get('current_reply_ticket')
    
    if not ticket_code:
        await message.answer(await get_text(user_id, "ticket_code_not_found_in_state")) # Добавьте этот ключ в languages.py
        await state.finish()
        return

    # Получаем роль пользователя для записи в историю
    role = await get_user_role(user_id)
    if not role:
        role = 'user' # Если по какой-то причине роль не найдена, используем 'user'

    await add_message(ticket_code, user_id, role, text)

    # Если есть фото или документ, сохраняем их file_id
    if message.photo:
        await add_attachment(ticket_code, message.photo[-1].file_id, None, 'photo')
    if message.document:
        await add_attachment(ticket_code, message.document.file_id, message.document.file_name, 'document')

    # Уведомляем пользователя, который создал заявку
    ticket_info = await get_ticket_by_code(ticket_code)
    if ticket_info:
        original_user_id = ticket_info[5] # user_id создателя заявки
        try:
            # Отправляем сообщение автору заявки
            await bot.send_message(original_user_id, await get_text(original_user_id, "message_sent_to_user"))
            # Отправляем новое сообщение в историю чата, чтобы обновить
            lang_code = (await dp.current_state(user=original_user_id).get_data()).get('language', 'ru')
            translated_role = LANGUAGES[lang_code].get(f'role_{role}', role)
            await bot.send_message(original_user_id, f"<b>[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {translated_role}:</b> {text}", parse_mode="HTML")
            # Если были вложения, пересылаем их автору
            if message.photo:
                await bot.send_photo(original_user_id, message.photo[-1].file_id)
            if message.document:
                await bot.send_document(original_user_id, message.document.file_id)

        except Exception as e:
            logger.error(f"Не удалось отправить сообщение пользователю {original_user_id}: {e}")
            await message.answer(f"Не удалось уведомить пользователя о вашем ответе: {e}")

    await message.answer(await get_text(user_id, "message_sent_to_user"), reply_markup=await get_ticket_detail_keyboard(user_id, ticket_code))
    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith("user_reply_to_ticket:"), state="*")
async def user_reply_to_ticket_handler(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]

    ticket = await get_ticket_by_code(ticket_code)
    # Проверяем, что заявка существует, открыта и принадлежит текущему пользователю
    if not ticket or ticket[3] != 'open' or ticket[5] != user_id:
        await c.message.answer(await get_text(user_id, "ticket_not_open_for_reply"))
        await c.answer()
        return

    await state.update_data(current_reply_ticket=ticket_code)
    await c.message.edit_text(await get_text(user_id, "reply_message_prompt", code=ticket_code), reply_markup=await get_back_button(user_id, "my_tickets_button_callback"))
    await TicketStates.waiting_for_admin_reply.set() # Используем то же состояние, что и для админа, но для пользователя
    await c.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("close_ticket_admin:"), state="*")
async def close_ticket_admin_handler(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    ticket_code = c.data.split(":")[1]
    ticket = await get_ticket_by_code(ticket_code)
    if not ticket:
        await c.answer(await get_text(user_id, "ticket_code_not_found", code=ticket_code))
        return

    if ticket[3] == 'closed': # ticket[3] - статус
        await c.message.answer(await get_text(user_id, "ticket_already_closed", code=ticket_code)) # Добавьте этот ключ в languages.py
        await c.answer()
        return

    await close_ticket(ticket_code)
    await add_message(ticket_code, user_id, await get_user_role(user_id), await get_text(user_id, "ticket_closed_success", code=ticket_code))
    
    await c.message.edit_text(await get_text(user_id, "ticket_closed_success", code=ticket_code), reply_markup=await get_admin_main_keyboard(user_id))
    await c.answer()
    
    # Уведомляем пользователя о закрытии и просим оставить отзыв
    original_user_id = ticket[5]
    try:
        await bot.send_message(original_user_id, await get_text(original_user_id, "ticket_closed_success", code=ticket_code),
                               reply_markup=await get_rating_keyboard(original_user_id, ticket_code))
        await bot.send_message(original_user_id, await get_text(original_user_id, "feedback_prompt", code=ticket_code))
    except Exception as e:
        logger.error(f"Не удалось уведомить пользователя {original_user_id} о закрытии заявки: {e}")


@dp.callback_query_handler(lambda c: c.data.startswith("rate_ticket:"), state="*")
async def handle_ticket_rating(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    parts = c.data.split(":")
    ticket_code = parts[1]
    rating = int(parts[2])

    ticket = await get_ticket_by_code(ticket_code)
    if not ticket or ticket[5] != user_id or ticket[3] != 'closed': # Проверяем, что заявка принадлежит пользователю и закрыта
        await c.answer(await get_text(user_id, "not_your_ticket"))
        return

    await state.update_data(feedback_ticket_code=ticket_code, rating=rating)
    await c.message.edit_text(await get_text(user_id, "ask_feedback_text"), reply_markup=InlineKeyboardMarkup().add(InlineKeyboardButton(await get_text(user_id, "cancel_button"), callback_data=f"skip_feedback:{ticket_code}")))
    await TicketStates.waiting_for_feedback_text.set()
    await c.answer()

@dp.message_handler(state=TicketStates.waiting_for_feedback_text)
async def process_feedback_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    feedback_text = message.text

    data = await state.get_data()
    ticket_code = data.get('feedback_ticket_code')
    rating = data.get('rating')

    if not ticket_code or rating is None:
        await message.answer(await get_text(user_id, "feedback_data_not_found")) # Добавьте этот ключ в languages.py
        await state.finish()
        return

    # Если пользователь ввел "Отмена", пропускаем отзыв
    if feedback_text == (await get_text(user_id, "cancel_button")):
        await add_ticket_feedback(ticket_code, rating, None)
        await message.answer(await get_text(user_id, "thanks_for_feedback"), reply_markup=await get_user_main_keyboard(user_id))
        await state.finish()
        return

    await add_ticket_feedback(ticket_code, rating, feedback_text)
    await message.answer(await get_text(user_id, "thanks_for_feedback"), reply_markup=await get_user_main_keyboard(user_id))
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith("skip_feedback:"), state=TicketStates.waiting_for_feedback_text)
async def skip_feedback_text(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]

    data = await state.get_data()
    rating = data.get('rating')

    if not ticket_code or rating is None:
        await c.answer(await get_text(user_id, "feedback_data_not_found"))
        return

    await add_ticket_feedback(ticket_code, rating, None) # Передаем None для текстового отзыва
    await c.message.edit_text(await get_text(user_id, "thanks_for_feedback"), reply_markup=await get_user_main_keyboard(user_id))
    await state.finish()
    await c.answer()


@dp.message_handler(lambda message: message.text == LANGUAGES['ru']['admin_panel_button'] or message.text == LANGUAGES['en']['admin_panel_button'], state="*")
@dp.message_handler(lambda message: message.text == LANGUAGES['ru']['moderator_panel_button'] or message.text == LANGUAGES['en']['moderator_panel_button'], state="*")
@dp.message_handler(lambda message: message.text == LANGUAGES['ru']['superadmin_panel_button'] or message.text == LANGUAGES['en']['superadmin_panel_button'], state="*")
async def admin_panel(message: types.Message):
    user_id = message.from_user.id
    role = await get_user_role(user_id)
    if role in ['admin', 'moderator', 'superadmin']:
        if role == 'admin':
            title_key = "admin_menu_title"
        elif role == 'moderator':
            title_key = "moderator_menu_title"
        else: # superadmin
            title_key = "superadmin_menu_title"
        await message.answer(await get_text(user_id, title_key), reply_markup=await get_admin_main_keyboard(user_id))
    else:
        await message.answer(await get_text(user_id, "no_access"))

@dp.callback_query_handler(lambda c: c.data == "adminmenu_back", state="*")
async def admin_menu_back_handler(c: types.CallbackQuery):
    user_id = c.from_user.id
    role = await get_user_role(user_id)
    if role in ['admin', 'moderator', 'superadmin']:
        if role == 'admin':
            title_key = "admin_menu_title"
        elif role == 'moderator':
            title_key = "moderator_menu_title"
        else: # superadmin
            title_key = "superadmin_menu_title"
        await c.message.edit_text(await get_text(user_id, title_key), reply_markup=await get_admin_main_keyboard(user_id))
    else:
        await c.message.edit_text(await get_text(user_id, "no_access"))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "main_menu", state="*")
async def back_to_main_menu(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    await state.finish() # Сбрасываем все состояния
    await c.message.edit_text(await get_text(user_id, "back_to_main_user_menu"), reply_markup=await get_user_main_keyboard(user_id))
    await c.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_view_tickets", state="*")
async def admin_view_tickets(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    # Инициализация фильтров
    await state.update_data(
        filter_status=None,
        filter_priority=None,
        filter_category=None,
        filter_assigned_to_id=None,
        filter_start_date=None,
        filter_end_date=None,
        current_tickets_page=0 # Сбрасываем страницу при смене фильтров
    )
    
    await c.message.edit_text(await get_text(user_id, "select_filter"), reply_markup=await get_ticket_filters_keyboard(user_id))
    await c.answer()

async def get_ticket_filters_keyboard(user_id: int, current_filters: dict = None) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру для фильтрации заявок."""
    if current_filters is None:
        state = dp.current_state(user=user_id)
        current_filters = await state.get_data()

    kb = InlineKeyboardMarkup(row_width=2)
    
    # Статус
    status_text = current_filters.get('filter_status')
    display_status = LANGUAGES['ru'].get(f'ticket_status_{status_text.lower()}', status_text) if status_text else LANGUAGES['ru']['export_status_all']
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'ticket_status').split(':')[0]}: {display_status}", callback_data="filter_status_menu"))
    
    # Приоритет
    priority_text = current_filters.get('filter_priority')
    display_priority = LANGUAGES['ru'].get(f'ticket_priority_{priority_text.lower()}', priority_text) if priority_text else LANGUAGES['ru']['export_status_all']
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'ticket_priority').split(':')[0]}: {display_priority}", callback_data="filter_priority_menu"))

    # Категория
    category_text = current_filters.get('filter_category')
    display_category = LANGUAGES['ru'].get(f"ticket_category_{category_text.lower().replace(' ', '_')}", category_text) if category_text else LANGUAGES['ru']['export_status_all']
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'ticket_category').split(':')[0]}: {display_category}", callback_data="filter_category_menu"))

    # Назначено
    assigned_to_id = current_filters.get('filter_assigned_to_id')
    display_assigned = ""
    if assigned_to_id is None:
        display_assigned = LANGUAGES['ru']['export_status_all']
    elif assigned_to_id == 0:
        display_assigned = LANGUAGES['ru']['unassigned_tickets']
    else:
        try:
            assigned_user_info = await bot.get_chat(assigned_to_id)
            display_assigned = assigned_user_info.username if assigned_user_info.username else f"ID {assigned_to_id}"
        except Exception:
            display_assigned = f"ID {assigned_to_id} (не найден)"
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'ticket_assigned').split(':')[0]}: {display_assigned}", callback_data="filter_assigned_menu"))

    # Даты
    start_date = current_filters.get('filter_start_date', await get_text(user_id, 'export_status_all'))
    end_date = current_filters.get('filter_end_date', await get_text(user_id, 'export_status_all'))
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'export_start_date').split('(')[0].strip()}: {start_date}", callback_data="filter_date:start"))
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'export_end_date').split('(')[0].strip()}: {end_date}", callback_data="filter_date:end"))
    
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="adminmenu_back"))
    return kb

@dp.callback_query_handler(lambda c: c.data == "filter_status_menu", state="*")
async def filter_status_menu(c: types.CallbackQuery):
    user_id = c.from_user.id
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_status_all"), callback_data="filter_status:all"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_status_open"), callback_data="filter_status:open"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_status_closed"), callback_data="filter_status:closed"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_view_tickets"))
    await c.message.edit_text(await get_text(user_id, "select_filter_status"), reply_markup=kb) # Добавьте select_filter_status в languages.py
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "filter_priority_menu", state="*")
async def filter_priority_menu(c: types.CallbackQuery):
    user_id = c.from_user.id
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_priority_all"), callback_data="filter_priority:all"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_priority_low"), callback_data="filter_priority:Низкий"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_priority_medium"), callback_data="filter_priority:Средний"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_priority_high"), callback_data="filter_priority:Высокий"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_view_tickets"))
    await c.message.edit_text(await get_text(user_id, "select_filter_priority"), reply_markup=kb) # Добавьте select_filter_priority в languages.py
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "filter_category_menu", state="*")
async def filter_category_menu(c: types.CallbackQuery):
    user_id = c.from_user.id
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_category_all"), callback_data="filter_category:all"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_category_general"), callback_data="filter_category:Общий вопрос"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_category_technical"), callback_data="filter_category:Техническая проблема"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_category_financial"), callback_data="filter_category:Финансовый вопрос"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_view_tickets"))
    await c.message.edit_text(await get_text(user_id, "select_filter_category"), reply_markup=kb) # Добавьте select_filter_category в languages.py
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "filter_assigned_menu", state="*")
async def filter_assigned_menu(c: types.CallbackQuery):
    user_id = c.from_user.id
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_assigned_all"), callback_data="filter_assigned:all"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_assigned_unassigned"), callback_data="filter_assigned:0"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_assigned_me"), callback_data="filter_assigned:me"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_assigned_specific"), callback_data="filter_assigned:specific"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_view_tickets"))
    await c.message.edit_text(await get_text(user_id, "select_filter_assigned"), reply_markup=kb) # Добавьте select_filter_assigned в languages.py
    await c.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("filter_"), state="*")
async def handle_ticket_filters(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    filter_type, filter_value = c.data.split(":", 1)
    
    async with state.proxy() as data:
        if filter_type == "filter_status":
            data['filter_status'] = filter_value if filter_value != 'all' else None
        elif filter_type == "filter_priority":
            data['filter_priority'] = filter_value if filter_value != 'all' else None
        elif filter_type == "filter_category":
            data['filter_category'] = filter_value if filter_value != 'all' else None
        elif filter_type == "filter_assigned":
            if filter_value == 'all':
                data['filter_assigned_to_id'] = None
            elif filter_value == 'me':
                data['filter_assigned_to_id'] = user_id
            elif filter_value == 'specific':
                # Запускаем отдельный процесс выбора пользователя для назначения
                users = await get_all_admins_and_moderators()
                if not users:
                    await c.answer(await get_text(user_id, "no_admins_or_moderators"))
                    return
                
                kb = InlineKeyboardMarkup(row_width=1)
                for u_id, username, _ in users:
                    user_display = f"@{username}" if username else f"ID {u_id}"
                    kb.add(InlineKeyboardButton(user_display, callback_data=f"filter_assign_specific:{u_id}"))
                kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_view_tickets"))
                await c.message.edit_text(await get_text(user_id, "select_admin_to_assign"), reply_markup=kb) 
                await c.answer()
                return # Выходим, чтобы не обновлять список пока
            else: # Конкретный ID
                data['filter_assigned_to_id'] = int(filter_value)
        elif filter_type == "filter_date":
            if filter_value == 'start':
                await state.set_state(TicketStates.waiting_for_export_dates)
                await state.update_data(current_date_filter_type='start_filter') # Изменено для различия
                await c.message.edit_text(await get_text(user_id, "export_start_date") + "\n" + await get_text(user_id, "export_enter_dates"), reply_markup=await get_back_button(user_id, "admin_view_tickets"))
            elif filter_value == 'end':
                await state.set_state(TicketStates.waiting_for_export_dates)
                await state.update_data(current_date_filter_type='end_filter') # Изменено для различия
                await c.message.edit_text(await get_text(user_id, "export_end_date") + "\n" + await get_text(user_id, "export_enter_dates"), reply_markup=await get_back_button(user_id, "admin_view_tickets"))
            await c.answer()
            return
    
    # После установки фильтра, получаем и отправляем список заявок
    await send_filtered_tickets(c, state)
    await c.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("filter_assign_specific:"), state="*")
async def filter_assign_specific_handler(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    assigned_id = int(c.data.split(":")[1])
    async with state.proxy() as data:
        data['filter_assigned_to_id'] = assigned_id
    
    await c.message.edit_text(await get_text(user_id, "select_filter"), reply_markup=await get_ticket_filters_keyboard(user_id)) # Возвращаемся к меню фильтров
    await send_filtered_tickets(c, state) # И сразу показываем отфильтрованные заявки
    await c.answer()


@dp.message_handler(state=TicketStates.waiting_for_export_dates)
async def process_export_dates(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    date_str = message.text.strip()
    
    data = await state.get_data()
    current_date_filter_type = data.get('current_date_filter_type')

    if date_str.lower() == (await get_text(user_id, "back_button")).lower(): # Если пользователь отменил
        await state.finish()
        if current_date_filter_type and "export" in current_date_filter_type:
            # Имитируем CallbackQuery для возврата в меню экспорта
            fake_callback = types.CallbackQuery(id='fake_id', from_user=message.from_user, message=message, chat_instance='fake_instance', data="admin_export")
            await admin_export_menu(fake_callback, state)
        else:
            # Имитируем CallbackQuery для возврата в меню фильтров
            fake_callback = types.CallbackQuery(id='fake_id', from_user=message.from_user, message=message, chat_instance='fake_instance', data="admin_view_tickets")
            await admin_view_tickets(fake_callback, state)
        return

    try:
        if date_str: # Может быть пустым, если пользователь хочет удалить фильтр даты
            datetime.datetime.strptime(date_str, "%Y-%m-%d") # Проверка формата
        
        async with state.proxy() as data:
            if current_date_filter_type == 'start_filter':
                data['filter_start_date'] = date_str if date_str else None
            elif current_date_filter_type == 'end_filter':
                data['filter_end_date'] = date_str if date_str else None
            elif current_date_filter_type == 'start_export':
                data['export_start_date'] = date_str if date_str else None
            elif current_date_filter_type == 'end_export':
                data['export_end_date'] = date_str if date_str else None
            
            # Очищаем состояние после получения даты
            del data['current_date_filter_type']
        
        if current_date_filter_type and "export" in current_date_filter_type:
            await message.answer(await get_text(user_id, "export_options_title"), reply_markup=await get_export_summary_keyboard(user_id, data))
        else:
            await message.answer(await get_text(user_id, "select_filter"), reply_markup=await get_ticket_filters_keyboard(user_id))
            # После установки фильтра, получаем и отправляем список заявок
            await send_filtered_tickets(message, state) # Передаем message для корректного ответа
        
        await state.set_state(None) # Выходим из состояния ожидания даты

    except ValueError:
        await message.answer(await get_text(user_id, "invalid_date_format"))
        # Остаемся в состоянии, чтобы пользователь мог ввести дату заново


async def send_filtered_tickets(message_or_callback: types.Message | types.CallbackQuery, state: FSMContext):
    user_id = message_or_callback.from_user.id
    data = await state.get_data()
    
    status = data.get('filter_status')
    priority = data.get('filter_priority')
    category = data.get('filter_category')
    assigned_to_id = data.get('filter_assigned_to_id')
    start_date = data.get('filter_start_date')
    end_date = data.get('filter_end_date')

    tickets = await get_tickets_by_date_range(
        start_date=start_date,
        end_date=end_date,
        status=status,
        priority=priority,
        category=category,
        assigned_to_id=assigned_to_id
    )
    
    # Формируем заголовок на основе активных фильтров
    filter_summary = []
    lang_code = (await dp.current_state(user=user_id).get_data()).get('language', 'ru')
    
    if status: filter_summary.append(f"{LANGUAGES[lang_code]['ticket_status'].split(':')[0]}: {LANGUAGES[lang_code].get(f'ticket_status_{status.lower()}', status)}")
    if priority: filter_summary.append(f"{LANGUAGES[lang_code]['ticket_priority'].split(':')[0]}: {LANGUAGES[lang_code].get(f'ticket_priority_{priority.lower()}', priority)}")
    # Corrected line 909: Using double quotes for the f-string
    if category:
        category_key = f"ticket_category_{category.lower().replace(' ', '_')}"
        category_value = LANGUAGES[lang_code].get(category_key, category)
        filter_summary.append(f"{LANGUAGES[lang_code]['ticket_category'].split(':')[0]}: {category_value}")
    if assigned_to_id is not None:
        if assigned_to_id == 0:
            filter_summary.append(f"{LANGUAGES[lang_code]['ticket_assigned'].split(':')[0]}: {LANGUAGES[lang_code]['unassigned_tickets']}")
        else:
            try:
                assigned_user_info = await bot.get_chat(assigned_to_id)
                assigned_username = assigned_user_info.username if assigned_user_info.username else f"ID {assigned_to_id}"
                filter_summary.append(f"{LANGUAGES[lang_code]['ticket_assigned'].split(':')[0]}: @{assigned_username}")
            except Exception:
                filter_summary.append(f"{LANGUAGES[lang_code]['ticket_assigned'].split(':')[0]}: ID {assigned_to_id} (не найден)")
    if start_date: filter_summary.append(f"{LANGUAGES[lang_code]['export_start_date'].split('(')[0].strip()}: {start_date}")
    if end_date: filter_summary.append(f"{LANGUAGES[lang_code]['export_end_date'].split('(')[0].strip()}: {end_date}")

    title_text = await get_text(user_id, "view_all_tickets_button")
    if filter_summary:
        title_text += "\n" + " | ".join(filter_summary)
    else:
        title_text += "\n(" + (await get_text(user_id, "export_status_all")).lower() + ")" # Указываем, что все фильтры

    await send_tickets_list(message_or_callback, tickets, title_text, "admin_view_tickets")


@dp.callback_query_handler(lambda c: c.data.startswith("ticket_detail:"), state="*")
async def show_ticket_detail(c: types.CallbackQuery):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]

    ticket = await get_ticket_by_code(ticket_code)
    if not ticket:
        await c.message.edit_text(await get_text(user_id, "ticket_details_not_found"))
        await c.answer()
        return
    
    t_code, text, created, status, username, ticket_user_id, priority, category, assigned_to_id, rating, feedback_text, last_admin_reply_at = ticket

    msg_parts = [
        await get_text(user_id, "ticket_detail_title", code=t_code),
        await get_text(user_id, "ticket_text", text=text),
        await get_text(user_id, "ticket_created_at", created=created),
        await get_text(user_id, "ticket_status", status=LANGUAGES[(await dp.current_state(user=user_id).get_data()).get('language', 'ru')].get(f'ticket_status_{status.lower()}', status)),
        await get_text(user_id, "ticket_user", user=(f"@{username}" if username else f"ID {ticket_user_id}")),
        await get_text(user_id, "ticket_priority", priority=LANGUAGES[(await dp.current_state(user=user_id).get_data()).get('language', 'ru')].get(f'ticket_priority_{priority.lower()}', priority)),
        await get_text(user_id, "ticket_category", category=LANGUAGES[(await dp.current_state(user=user_id).get_data()).get('language', 'ru')].get(f'ticket_category_{category.lower().replace(" ", "_")}', category))
    ]
    if assigned_to_id:
        try:
            assigned_user_info = await bot.get_chat(assigned_to_id)
            assigned_username = assigned_user_info.username if assigned_user_info.username else f"ID {assigned_to_id}"
            msg_parts.append(await get_text(user_id, "ticket_assigned", assigned=assigned_username))
        except Exception:
            msg_parts.append(await get_text(user_id, "ticket_assigned", assigned=f"ID {assigned_to_id} (не найден)"))
    else:
        msg_parts.append(await get_text(user_id, "ticket_assigned", assigned=(await get_text(user_id, "unassigned_tickets")).lower()))
    
    if rating is not None:
        msg_parts.append(await get_text(user_id, "ticket_rating", rating=f"{rating}/5"))
    if feedback_text:
        msg_parts.append(await get_text(user_id, "ticket_feedback", feedback=feedback_text))

    # Добавляем инфо о последнем ответе
    if last_admin_reply_at:
        msg_parts.append(await get_text(user_id, "last_reply_at", timestamp=last_admin_reply_at))
    else:
        msg_parts.append(await get_text(user_id, "no_last_reply"))

    msg = "\n".join(msg_parts)
    await c.message.edit_text(msg, parse_mode="HTML", reply_markup=await get_ticket_detail_keyboard(user_id, ticket_code))
    await c.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_templates", state="*")
async def admin_templates_menu(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(await get_text(user_id, "create_template_button"), callback_data="create_template"),
        InlineKeyboardButton(await get_text(user_id, "view_templates_button"), callback_data="view_templates"),
        InlineKeyboardButton(await get_text(user_id, "delete_template_button"), callback_data="delete_template")
    )
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="adminmenu_back"))
    await c.message.edit_text(await get_text(user_id, "response_templates_button"), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "create_template", state="*")
async def create_template_start(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return
    
    await c.message.edit_text(await get_text(user_id, "ask_template_name"), reply_markup=await get_back_button(user_id, "admin_templates"))
    await TicketStates.waiting_for_template_name.set()
    await c.answer()

@dp.message_handler(state=TicketStates.waiting_for_template_name)
async def process_template_name(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    template_name = message.text.strip()
    
    if template_name == (await get_text(user_id, "back_button")):
        await state.finish()
        # Имитируем CallbackQuery для возврата в меню шаблонов
        fake_callback = types.CallbackQuery(id='fake_id', from_user=message.from_user, message=message, chat_instance='fake_instance', data="admin_templates")
        await admin_templates_menu(fake_callback)
        return

    async with state.proxy() as data:
        data['new_template_name'] = template_name
    
    await message.answer(await get_text(user_id, "ask_template_text"), reply_markup=await get_back_button(user_id, "admin_templates"))
    await TicketStates.waiting_for_template_text.set()

@dp.message_handler(state=TicketStates.waiting_for_template_text)
async def process_template_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    template_text = message.text
    
    if template_text == (await get_text(user_id, "back_button")):
        await state.finish()
        # Имитируем CallbackQuery для возврата в меню шаблонов
        fake_callback = types.CallbackQuery(id='fake_id', from_user=message.from_user, message=message, chat_instance='fake_instance', data="admin_templates")
        await admin_templates_menu(fake_callback)
        return

    data = await state.get_data()
    template_name = data.get('new_template_name')
    
    success = await add_response_template(template_name, template_text)
    
    if success:
        await message.answer(await get_text(user_id, "template_added_success", name=template_name), reply_markup=await get_admin_main_keyboard(user_id))
    else:
        await message.answer(await get_text(user_id, "template_name_exists"), reply_markup=await get_admin_main_keyboard(user_id))
    
    await state.finish()

@dp.callback_query_handler(lambda c: c.data == "view_templates", state="*")
async def view_templates(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return
    
    templates = await get_response_templates()
    if not templates:
        await c.message.edit_text(await get_text(user_id, "no_templates"), reply_markup=await get_back_button(user_id, "admin_templates"))
        await c.answer()
        return
    
    template_list_text = await get_text(user_id, "templates_list_title") + "\n\n"
    for t_id, name, text in templates:
        template_list_text += f"<b>{name}</b>:\n{text}\n\n"
    
    await c.message.edit_text(template_list_text, parse_mode="HTML", reply_markup=await get_back_button(user_id, "admin_templates"))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "delete_template", state="*")
async def delete_template_start(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return
    
    templates = await get_response_templates()
    if not templates:
        await c.message.edit_text(await get_text(user_id, "no_templates"), reply_markup=await get_back_button(user_id, "admin_templates"))
        await c.answer()
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for t_id, name, _ in templates:
        kb.add(InlineKeyboardButton(name, callback_data=f"confirm_delete_template:{t_id}"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_templates"))
    
    await c.message.edit_text(await get_text(user_id, "select_template_to_delete"), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("confirm_delete_template:"), state="*")
async def confirm_delete_template(c: types.CallbackQuery):
    user_id = c.from_user.id
    template_id = int(c.data.split(":")[1])
    
    templates = await get_response_templates()
    template_name = next((t[1] for t in templates if t[0] == template_id), None)
    
    if template_name:
        kb = InlineKeyboardMarkup(row_width=2)
        kb.add(
            InlineKeyboardButton(await get_text(user_id, "yes_button"), callback_data=f"execute_delete_template:{template_id}"),
            InlineKeyboardButton(await get_text(user_id, "no_button"), callback_data="admin_templates")
        )
        await c.message.edit_text(await get_text(user_id, "confirm_delete_template", name=template_name), reply_markup=kb)
    else:
        await c.message.edit_text(await get_text(user_id, "template_not_found"), reply_markup=await get_back_button(user_id, "admin_templates"))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("execute_delete_template:"), state="*")
async def execute_delete_template(c: types.CallbackQuery):
    user_id = c.from_user.id
    template_id = int(c.data.split(":")[1])
    
    await delete_response_template(template_id)
    await c.message.edit_text(await get_text(user_id, "template_deleted_success"), reply_markup=await get_admin_main_keyboard(user_id))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("send_template:"), state="*")
async def send_template_to_ticket(c: types.CallbackQuery):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]

    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    templates = await get_response_templates()
    if not templates:
        await c.answer(await get_text(user_id, "no_templates"))
        return
    
    kb = InlineKeyboardMarkup(row_width=1)
    for t_id, name, _ in templates:
        kb.add(InlineKeyboardButton(name, callback_data=f"select_template_to_send:{ticket_code}:{t_id}"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data=f"ticket_detail:{ticket_code}"))
    
    await c.message.edit_text(await get_text(user_id, "templates_list_title"), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("select_template_to_send:"), state="*")
async def execute_send_template(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    parts = c.data.split(":")
    ticket_code = parts[1]
    template_id = int(parts[2])

    ticket = await get_ticket_by_code(ticket_code)
    if not ticket or ticket[3] != 'open':
        await c.message.answer(await get_text(user_id, "ticket_not_open_for_reply"))
        await c.answer()
        return

    templates = await get_response_templates()
    template_text = next((t[2] for t in templates if t[0] == template_id), None)
    
    if template_text:
        role = await get_user_role(user_id)
        await add_message(ticket_code, user_id, role, template_text)

        original_user_id = ticket[5]
        try:
            lang_code = (await dp.current_state(user=original_user_id).get_data()).get('language', 'ru')
            translated_role = LANGUAGES[lang_code].get(f'role_{role}', role)
            await bot.send_message(original_user_id, f"<b>[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {translated_role}:</b> {template_text}", parse_mode="HTML")
            await bot.send_message(user_id, await get_text(user_id, "message_sent_to_user"), reply_markup=await get_ticket_detail_keyboard(user_id, ticket_code))
        except Exception as e:
            logger.error(f"Не удалось отправить шаблон пользователю {original_user_id}: {e}")
            await c.message.answer(f"Не удалось уведомить пользователя о вашем ответе: {e}", reply_markup=await get_ticket_detail_keyboard(user_id, ticket_code))
    else:
        await c.message.answer(await get_text(user_id, "template_not_found"), reply_markup=await get_ticket_detail_keyboard(user_id, ticket_code))

    await c.answer()
    await state.finish()


@dp.callback_query_handler(lambda c: c.data == "admin_export", state="*")
async def admin_export_menu(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return
    
    # Инициализация фильтров для экспорта
    await state.update_data(
        export_status=None,
        export_priority=None,
        export_category=None,
        export_assigned_to_id=None,
        export_start_date=None,
        export_end_date=None
    )
    
    await c.message.edit_text(await get_text(user_id, "export_options_title"), reply_markup=await get_export_summary_keyboard(user_id, await state.get_data()))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("export_"), state="*")
async def handle_export_filters(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    filter_type, filter_value = c.data.split(":", 1)
    
    async with state.proxy() as data:
        if filter_type == "export_status":
            data['export_status'] = filter_value if filter_value != 'all' else None
        elif filter_type == "export_priority":
            data['export_priority'] = filter_value if filter_value != 'all' else None
        elif filter_type == "export_category":
            data['export_category'] = filter_value if filter_value != 'all' else None
        elif filter_type == "export_assigned":
            if filter_value == 'all':
                data['export_assigned_to_id'] = None
            elif filter_value == 'me':
                data['export_assigned_to_id'] = user_id
            elif filter_value == 'specific':
                # Запускаем отдельный процесс выбора пользователя для назначения
                users = await get_all_admins_and_moderators()
                if not users:
                    await c.answer(await get_text(user_id, "no_admins_or_moderators"))
                    return
                
                kb = InlineKeyboardMarkup(row_width=1)
                for u_id, username, _ in users:
                    user_display = f"@{username}" if username else f"ID {u_id}"
                    kb.add(InlineKeyboardButton(user_display, callback_data=f"export_assign_specific:{u_id}"))
                kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_export"))
                await c.message.edit_text(await get_text(user_id, "select_admin_to_assign"), reply_markup=kb)
                await c.answer()
                return
            else: # Конкретный ID
                data['export_assigned_to_id'] = int(filter_value)
        elif filter_type == "export_date":
            if filter_value == 'start':
                await state.set_state(TicketStates.waiting_for_export_dates)
                await state.update_data(current_date_filter_type='start_export')
                await c.message.edit_text(await get_text(user_id, "export_start_date") + "\n" + await get_text(user_id, "export_enter_dates"), reply_markup=await get_back_button(user_id, "admin_export"))
            elif filter_value == 'end':
                await state.set_state(TicketStates.waiting_for_export_dates)
                await state.update_data(current_date_filter_type='end_export')
                await c.message.edit_text(await get_text(user_id, "export_end_date") + "\n" + await get_text(user_id, "export_enter_dates"), reply_markup=await get_back_button(user_id, "admin_export"))
            await c.answer()
            return
    
    await c.message.edit_text(await get_text(user_id, "export_options_title"), reply_markup=await get_export_summary_keyboard(user_id, data))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("export_assign_specific:"), state="*")
async def export_assign_specific_handler(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    assigned_id = int(c.data.split(":")[1])
    async with state.proxy() as data:
        data['export_assigned_to_id'] = assigned_id
    
    await c.message.edit_text(await get_text(user_id, "export_options_title"), reply_markup=await get_export_summary_keyboard(user_id, data))
    await c.answer()


async def get_export_summary_keyboard(user_id: int, current_filters: dict) -> InlineKeyboardMarkup:
    """Генерирует клавиатуру с текущими выбранными фильтрами и кнопкой для экспорта."""
    kb = InlineKeyboardMarkup(row_width=2)
    lang_code = (await dp.current_state(user=user_id).get_data()).get('language', 'ru')
    
    # Кнопки выбора фильтров
    status_text = current_filters.get('export_status')
    display_status = LANGUAGES[lang_code].get(f'ticket_status_{status_text.lower()}', status_text) if status_text else LANGUAGES[lang_code]['export_status_all']
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'export_status_all')} ({display_status})", callback_data="export_status_menu"))

    priority_text = current_filters.get('export_priority')
    display_priority = LANGUAGES[lang_code].get(f'ticket_priority_{priority_text.lower()}', priority_text) if priority_text else LANGUAGES[lang_code]['export_status_all']
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'export_priority_all')} ({display_priority})", callback_data="export_priority_menu"))

    category_text = current_filters.get('export_category')
    display_category = LANGUAGES[lang_code].get(f'ticket_category_{category_text.lower().replace(' ', '_')}', category_text) if category_text else LANGUAGES[lang_code]['export_status_all']
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'export_category_all')} ({display_category})", callback_data="export_category_menu"))

    assigned_to_id = current_filters.get('export_assigned_to_id')
    display_assigned = ""
    if assigned_to_id is None:
        display_assigned = LANGUAGES[lang_code]['export_status_all']
    elif assigned_to_id == 0:
        display_assigned = LANGUAGES[lang_code]['unassigned_tickets']
    else:
        try:
            assigned_user_info = await bot.get_chat(assigned_to_id)
            display_assigned = assigned_user_info.username if assigned_user_info.username else f"ID {assigned_to_id}"
        except Exception:
            display_assigned = f"ID {assigned_to_id} (не найден)"
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'export_assigned_all')} ({display_assigned})", callback_data="export_assigned_menu"))

    start_date = current_filters.get('export_start_date', await get_text(user_id, 'export_status_all'))
    end_date = current_filters.get('export_end_date', await get_text(user_id, 'export_status_all'))
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'export_start_date').split('(')[0].strip()} ({start_date})", callback_data="export_date:start"))
    kb.add(InlineKeyboardButton(f"{await get_text(user_id, 'export_end_date').split('(')[0].strip()} ({end_date})", callback_data="export_date:end"))
    
    # Кнопка "Экспортировать"
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_tickets_button"), callback_data="execute_export"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="adminmenu_back"))
    return kb

@dp.callback_query_handler(lambda c: c.data == "export_status_menu", state="*")
async def export_status_menu(c: types.CallbackQuery):
    user_id = c.from_user.id
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_status_all"), callback_data="export_status:all"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_status_open"), callback_data="export_status:open"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_status_closed"), callback_data="export_status:closed"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_export"))
    await c.message.edit_text(await get_text(user_id, "select_filter_status"), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "export_priority_menu", state="*")
async def export_priority_menu(c: types.CallbackQuery):
    user_id = c.from_user.id
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_priority_all"), callback_data="export_priority:all"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_priority_low"), callback_data="export_priority:Низкий"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_priority_medium"), callback_data="export_priority:Средний"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_priority_high"), callback_data="export_priority:Высокий"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_export"))
    await c.message.edit_text(await get_text(user_id, "select_filter_priority"), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "export_category_menu", state="*")
async def export_category_menu(c: types.CallbackQuery):
    user_id = c.from_user.id
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_category_all"), callback_data="export_category:all"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_category_general"), callback_data="export_category:Общий вопрос"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_category_technical"), callback_data="export_category:Техническая проблема"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "ticket_category_financial"), callback_data="export_category:Финансовый вопрос"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_export"))
    await c.message.edit_text(await get_text(user_id, "select_filter_category"), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data == "export_assigned_menu", state="*")
async def export_assigned_menu(c: types.CallbackQuery):
    user_id = c.from_user.id
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_assigned_all"), callback_data="export_assigned:all"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_assigned_unassigned"), callback_data="export_assigned:0"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_assigned_me"), callback_data="export_assigned:me"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "export_assigned_specific"), callback_data="export_assigned:specific"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_export"))
    await c.message.edit_text(await get_text(user_id, "select_filter_assigned"), reply_markup=kb)
    await c.answer()


@dp.callback_query_handler(lambda c: c.data == "execute_export", state="*")
async def execute_export_tickets(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    data = await state.get_data()
    
    status = data.get('export_status')
    priority = data.get('export_priority')
    category = data.get('export_category')
    assigned_to_id = data.get('export_assigned_to_id')
    start_date = data.get('export_start_date')
    end_date = data.get('export_end_date')

    tickets = await get_tickets_by_date_range(
        start_date=start_date,
        end_date=end_date,
        status=status,
        priority=priority,
        category=category,
        assigned_to_id=assigned_to_id
    )

    if not tickets:
        await c.answer(await get_text(user_id, "no_tickets_found"), show_alert=True)
        return

    file_name = f"tickets_export_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    await generate_tickets_excel(tickets, file_name)

    with open(file_name, 'rb') as f:
        await bot.send_document(user_id, types.InputFile(f), caption=await get_text(user_id, "export_file_generated"))
    
    os.remove(file_name) # Удаляем файл после отправки
    await c.answer()


@dp.callback_query_handler(lambda c: c.data == "admin_stale_tickets", state="*")
async def admin_stale_tickets(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return
    
    stale_tickets = await get_stale_tickets(hours=24)
    await send_tickets_list(c, stale_tickets, await get_text(user_id, "stale_tickets_title"), "adminmenu_back")
    await c.answer()

# --- Хендлеры для выбора языка ---
@dp.message_handler(lambda m: m.text in [LANGUAGES['ru']['language_button'], LANGUAGES['en']['language_button']], state="*")
async def choose_language_start(m: types.Message):
    user_id = m.from_user.id
    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton("Русский 🇷🇺", callback_data="set_language:ru"),
        InlineKeyboardButton("English 🇬🇧", callback_data="set_language:en")
    )
    await m.answer(await get_text(user_id, "choose_language"), reply_markup=kb)

@dp.callback_query_handler(lambda c: c.data.startswith("set_language:"), state="*")
async def set_language_cb(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    lang_code = c.data.split(":")[1]
    await state.update_data(language=lang_code)
    
    # Обновляем клавиатуру пользователя после смены языка
    await c.message.edit_text(await get_text(user_id, "language_set", language=lang_code), reply_markup=await get_user_main_keyboard(user_id))
    await c.answer()

# --- Управление ролями пользователей (только для суперадмина) ---
@dp.callback_query_handler(lambda c: c.data == "admin_manage_users", state="*")
async def manage_users_start(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_superadmin(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return
    
    users = await get_all_registered_users()
    if not users:
        await c.message.edit_text(await get_text(user_id, "no_users_registered"), reply_markup=await get_back_button(user_id, "adminmenu_back"))
        await c.answer()
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for u_id, username in users:
        user_display = f"@{username}" if username else f"ID {u_id}"
        kb.add(InlineKeyboardButton(user_display, callback_data=f"manage_user:{u_id}"))
    
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="adminmenu_back"))
    await c.message.edit_text(await get_text(user_id, "manage_users_title"), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("manage_user:"), state="*")
async def select_user_to_manage(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_superadmin(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    target_user_id = int(c.data.split(":")[1])
    target_user_info = await bot.get_chat(target_user_id)
    target_username = target_user_info.username if target_user_info.username else f"ID {target_user_id}"
    target_user_display = f"@{target_username}" if target_username else f"ID {target_user_id}"

    kb = InlineKeyboardMarkup(row_width=2)
    kb.add(
        InlineKeyboardButton(await get_text(user_id, "role_user"), callback_data=f"set_user_role_confirm:{target_user_id}:user"),
        InlineKeyboardButton(await get_text(user_id, "role_moderator"), callback_data=f"set_user_role_confirm:{target_user_id}:moderator"),
        InlineKeyboardButton(await get_text(user_id, "role_admin"), callback_data=f"set_user_role_confirm:{target_user_id}:admin")
    )
    # Суперадмина можно только установить, не снять через это меню
    kb.add(InlineKeyboardButton(await get_text(user_id, "role_superadmin"), callback_data=f"set_user_role_confirm:{target_user_id}:superadmin"))
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="admin_manage_users"))

    await c.message.edit_text(await get_text(user_id, "set_role_for_user", user_display=target_user_display), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("set_user_role_confirm:"), state="*")
async def execute_set_user_role(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_superadmin(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    parts = c.data.split(":")
    target_user_id = int(parts[1])
    new_role = parts[2]

    # Получаем username целевого пользователя
    target_user_info = await bot.get_chat(target_user_id)
    target_username = target_user_info.username if target_user_info.username else None
    
    await set_user_role(target_user_id, new_role, target_username)

    target_user_display = f"@{target_username}" if target_username else f"ID {target_user_id}"
    await c.message.edit_text(await get_text(user_id, "role_updated_success", user_display=target_user_display, role=new_role), reply_markup=await get_admin_main_keyboard(user_id))
    await c.answer()

# --- Хендлеры для назначения заявок ---
@dp.callback_query_handler(lambda c: c.data.startswith("assign_ticket:"), state="*")
async def assign_ticket_start(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    ticket_code = c.data.split(":")[1]
    
    admins_and_mods = await get_all_admins_and_moderators()
    if not admins_and_mods:
        await c.answer(await get_text(user_id, "no_admins_or_moderators"))
        return

    kb = InlineKeyboardMarkup(row_width=1)
    for admin_id, username, _ in admins_and_mods:
        user_display = f"@{username}" if username else f"ID {admin_id}"
        kb.add(InlineKeyboardButton(user_display, callback_data=f"execute_assign:{ticket_code}:{admin_id}"))
    
    kb.add(InlineKeyboardButton(await get_text(user_id, "unassign_ticket_button"), callback_data=f"unassign_ticket:{ticket_code}")) # Кнопка для снятия назначения
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data=f"ticket_detail:{ticket_code}"))
    
    await c.message.edit_text(await get_text(user_id, "select_admin_to_assign", code=ticket_code), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("execute_assign:"), state="*")
async def execute_assign_ticket(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    parts = c.data.split(":")
    ticket_code = parts[1]
    assigned_to_id = int(parts[2])

    await assign_ticket(ticket_code, assigned_to_id)
    
    assigned_user_info = await bot.get_chat(assigned_to_id)
    assigned_username = assigned_user_info.username if assigned_user_info.username else f"ID {assigned_to_id}"

    await c.message.edit_text(await get_text(user_id, "ticket_assigned_success", code=ticket_code, username=assigned_username), reply_markup=await get_ticket_detail_keyboard(user_id, ticket_code))
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("unassign_ticket:"), state="*")
async def execute_unassign_ticket(c: types.CallbackQuery):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return

    ticket_code = c.data.split(":")[1]
    await unassign_ticket(ticket_code)
    
    await c.message.edit_text(await get_text(user_id, "ticket_unassigned_success", code=ticket_code), reply_markup=await get_ticket_detail_keyboard(user_id, ticket_code))
    await c.answer()

# --- Хендлеры для редактирования заявок пользователем ---
@dp.callback_query_handler(lambda c: c.data.startswith("edit_ticket_user:"), state="*")
async def edit_ticket_start(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]

    ticket = await get_ticket_by_code(ticket_code)
    # Разрешаем редактировать только свои открытые и неназначенные заявки
    if not ticket or ticket[5] != user_id or ticket[3] != 'open' or ticket[8] is not None: # ticket[8] - assigned_to_id
        await c.answer(await get_text(user_id, "ticket_not_open_for_edit"))
        return

    await state.update_data(current_edit_ticket_code=ticket_code)
    
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton(await get_text(user_id, "edit_text_button"), callback_data=f"edit_ticket_text:{ticket_code}"),
        InlineKeyboardButton(await get_text(user_id, "edit_priority_button"), callback_data=f"edit_ticket_priority:{ticket_code}"),
        InlineKeyboardButton(await get_text(user_id, "edit_category_button"), callback_data=f"edit_ticket_category:{ticket_code}")
    )
    kb.add(InlineKeyboardButton(await get_text(user_id, "back_button"), callback_data="my_tickets_button_callback"))
    
    await c.message.edit_text(await get_text(user_id, "edit_ticket_menu_title", code=ticket_code), reply_markup=kb)
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("edit_ticket_text:"), state="*")
async def edit_ticket_text_prompt(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]
    await state.update_data(current_edit_ticket_code=ticket_code)
    await c.message.edit_text(await get_text(user_id, "enter_new_ticket_text"), reply_markup=await get_back_button(user_id, f"edit_ticket_user:{ticket_code}"))
    await TicketStates.waiting_for_edit_ticket_text.set()
    await c.answer()

@dp.message_handler(state=TicketStates.waiting_for_edit_ticket_text)
async def process_edit_ticket_text(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    new_text = message.text

    if new_text == (await get_text(user_id, "back_button")):
        await state.finish()
        data = await state.get_data()
        ticket_code = data.get('current_edit_ticket_code')
        # Имитируем CallbackQuery для возврата в меню редактирования
        fake_callback = types.CallbackQuery(id='fake_id', from_user=message.from_user, message=message, chat_instance='fake_instance', data=f"edit_ticket_user:{ticket_code}")
        await edit_ticket_start(fake_callback, state)
        return

    data = await state.get_data()
    ticket_code = data.get('current_edit_ticket_code')

    if not ticket_code:
        await message.answer(await get_text(user_id, "ticket_code_not_found_for_edit")) # Добавьте этот ключ в languages.py
        await state.finish()
        return

    success = await update_ticket_details(ticket_code, new_text=new_text)
    if success:
        await add_message(ticket_code, user_id, 'user', f"Пользователь изменил текст заявки на: {new_text[:50]}...")
        await message.answer(await get_text(user_id, "ticket_updated_success", code=ticket_code), reply_markup=await get_user_main_keyboard(user_id))
    else:
        await message.answer(await get_text(user_id, "no_changes_made"), reply_markup=await get_user_main_keyboard(user_id))
    
    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith("edit_ticket_priority:"), state="*")
async def edit_ticket_priority_prompt(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]
    await state.update_data(current_edit_ticket_code=ticket_code)
    await c.message.edit_text(await get_text(user_id, "select_new_priority"), reply_markup=await get_priority_keyboard(user_id, current_ticket_code=ticket_code))
    await TicketStates.waiting_for_edit_ticket_priority.set()
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("set_priority:"), state=TicketStates.waiting_for_edit_ticket_priority)
async def process_edit_ticket_priority(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    new_priority = c.data.split(":")[1]
    
    data = await state.get_data()
    ticket_code = data.get('current_edit_ticket_code')

    if not ticket_code:
        await c.answer(await get_text(user_id, "ticket_code_not_found_for_edit"))
        return

    success = await update_ticket_details(ticket_code, new_priority=new_priority)
    if success:
        await add_message(ticket_code, user_id, 'user', f"Пользователь изменил приоритет заявки на: {new_priority}")
        await c.message.edit_text(await get_text(user_id, "ticket_updated_success", code=ticket_code), reply_markup=await get_user_main_keyboard(user_id))
    else:
        await c.message.edit_text(await get_text(user_id, "no_changes_made"), reply_markup=await get_user_main_keyboard(user_id))
    
    await state.finish()
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("edit_ticket_category:"), state="*")
async def edit_ticket_category_prompt(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    ticket_code = c.data.split(":")[1]
    await state.update_data(current_edit_ticket_code=ticket_code)
    await c.message.edit_text(await get_text(user_id, "select_new_category"), reply_markup=await get_category_keyboard(user_id, current_ticket_code=ticket_code))
    await TicketStates.waiting_for_edit_ticket_category.set()
    await c.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("set_category:"), state=TicketStates.waiting_for_edit_ticket_category)
async def process_edit_ticket_category(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    new_category = c.data.split(":")[1]
    
    data = await state.get_data()
    ticket_code = data.get('current_edit_ticket_code')

    if not ticket_code:
        await c.answer(await get_text(user_id, "ticket_code_not_found_for_edit"))
        return

    success = await update_ticket_details(ticket_code, new_category=new_category)
    if success:
        await add_message(ticket_code, user_id, 'user', f"Пользователь изменил категорию заявки на: {new_category}")
        await c.message.edit_text(await get_text(user_id, "ticket_updated_success", code=ticket_code), reply_markup=await get_user_main_keyboard(user_id))
    else:
        await c.message.edit_text(await get_text(user_id, "no_changes_made"), reply_markup=await get_user_main_keyboard(user_id))
    
    await state.finish()
    await c.answer()


# --- Запуск бота ---
async def on_startup(dp):
    await init_db()
    logger.info("База данных инициализирована.")
    logger.info(f"Бот запущен. Супер-админ ID: {SUPERADMIN_ID}")
    
if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)

