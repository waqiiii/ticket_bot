# ============================================
#  BOT.PY – Telegram Ticket Bot (Full version)
#  Author: Sirojiddin Baxromov
#  Date: 2025-07-14
# ============================================

"""
📝 DESCRIPTION:

Этот файл содержит:
- Инициализацию бота и базы
- Все handler-ы (callback_query, message)
- FSM состояния
- Логику управления заявками, пользователями, экспортом, шаблонами
- TODO пометки для дальнейшей разработки

🛠️ MAIN HANDLERS:

1. @dp.callback_query_handler – все inline кнопки
2. @dp.message_handler – ввод сообщений пользователями
3. FSM – состояния редактирования, экспорта
4. Startup – запуск бота с init_db()
"""

# --- IMPORTS ---

import os
import datetime
import logging
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage

# --- DB & UTILITIES IMPORTS ---
from db import (
    init_db, is_admin_or_moderator, is_superadmin,
    get_response_templates, delete_response_template, add_message,
    get_ticket_by_code, set_user_role, get_all_registered_users,
    get_all_admins_and_moderators, assign_ticket, unassign_ticket,
    update_ticket_details, get_tickets_by_date_range, generate_tickets_excel,
    get_stale_tickets
)
from states import TicketStates
from keyboards import (
    get_user_main_keyboard, get_admin_main_keyboard, get_ticket_detail_keyboard,
    get_back_button, get_priority_keyboard, get_category_keyboard
)
from languages import LANGUAGES

# --- INIT BOT ---

API_TOKEN = "7688958145:AAGIEcgy5t-6scoO5tFRDw3i62o6j3EJOKI"
SUPERADMIN_ID = int(os.getenv("SUPERADMIN_ID", "7963375756"))

bot = Bot(token=API_TOKEN, parse_mode=types.ParseMode.HTML)
dp = Dispatcher(bot, storage=MemoryStorage())

# --- LOGGER CONFIG ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
#             CALLBACK QUERY HANDLERS
# ============================================

# --- Delete Template Confirm ---
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

# --- Execute Delete Template ---
@dp.callback_query_handler(lambda c: c.data.startswith("execute_delete_template:"), state="*")
async def execute_delete_template(c: types.CallbackQuery):
    user_id = c.from_user.id
    template_id = int(c.data.split(":")[1])
    
    await delete_response_template(template_id)
    await c.message.edit_text(await get_text(user_id, "template_deleted_success"), reply_markup=await get_admin_main_keyboard(user_id))
    await c.answer()

# --- Send Template to Ticket ---
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

# --- Select Template to Send ---
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

# --- Admin Export (init) ---
@dp.callback_query_handler(lambda c: c.data == "admin_export", state="*")
async def admin_export_menu(c: types.CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    if not await is_admin_or_moderator(user_id):
        await c.answer(await get_text(user_id, "no_access"))
        return
    
    # Init export filters
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

# ================================
# TODO:
# - Реализовать get_export_summary_keyboard()
# - Реализовать get_user_role()
# - Проверить LANGUAGES dict на все ключи
# - Добавить обработку ошибок при get_chat()
# - Вынести API_TOKEN и SUPERADMIN_ID в .env
# ================================

# --- STARTUP ---
async def on_startup(dp):
    await init_db()
    logger.info("База данных инициализирована.")
    logger.info(f"Бот запущен. Супер-админ ID: {SUPERADMIN_ID}")

if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup, skip_updates=True)
