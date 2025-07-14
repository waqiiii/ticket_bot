from aiogram import types
from aiogram.dispatcher import Dispatcher
from db import (
    add_user, get_user_role, create_ticket,
    get_user_tickets, get_open_tickets,
    assign_ticket, close_ticket
)


ADMINS = [7963375756]  

async def start_handler(message: types.Message):
    await add_user(message.from_user.id, message.from_user.username)
    await message.answer("Добро пожаловать! Используй /new_ticket чтобы создать тикет.")

async def new_ticket_handler(message: types.Message):
    args = message.get_args()
    if not args:
        await message.answer("Пожалуйста, напишите сообщение, например:\n/new_ticket У меня проблема с заказом.")
        return
    await create_ticket(message.from_user.id, args)
    await message.answer("✅ Ваш тикет создан! Мы скоро с вами свяжемся.")

async def my_tickets_handler(message: types.Message):
    tickets = await get_user_tickets(message.from_user.id)
    if not tickets:
        await message.answer("У вас нет тикетов.")
        return
    response = "🎫 Ваши тикеты:\n"
    for tid, msg, status in tickets:
        response += f"#{tid} [{status}]: {msg}\n"
    await message.answer(response)

async def list_open_tickets_handler(message: types.Message):
    role = await get_user_role(message.from_user.id)
    if role not in ["staff", "admin"]:
        await message.answer("⛔ У вас нет доступа к этой команде.")
        return

    tickets = await get_open_tickets()
    if not tickets:
        await message.answer("Нет открытых тикетов.")
        return

    for tid, uid, msg in tickets:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton(f"Взять тикет #{tid}", callback_data=f"assign_{tid}"))
        await message.answer(f"Тикет #{tid} от пользователя {uid}:\n{msg}", reply_markup=keyboard)

async def callback_handler(callback: types.CallbackQuery):
    data = callback.data
    if data.startswith("assign_"):
        ticket_id = int(data.split("_")[1])
        await assign_ticket(ticket_id, callback.from_user.id)
        await callback.message.edit_text(f"Тикет #{ticket_id} взят в работу {callback.from_user.full_name}")
    await callback.answer()

async def close_ticket_command(message: types.Message):
    role = await get_user_role(message.from_user.id)
    if role not in ["staff", "admin"]:
        await message.answer("⛔ У вас нет прав закрывать тикеты.")
        return

    args = message.get_args()
    if not args.isdigit():
        await message.answer("❌ Укажите номер тикета: /close_ticket 1")
        return

    await close_ticket(int(args))
    await message.answer(f"✅ Тикет #{args} закрыт.")

def register_handlers(dp: Dispatcher):
    dp.register_message_handler(start_handler, commands=["start"])
    dp.register_message_handler(new_ticket_handler, commands=["new_ticket"])
    dp.register_message_handler(my_tickets_handler, commands=["my_tickets"])
    dp.register_message_handler(list_open_tickets_handler, commands=["tickets"])
    dp.register_message_handler(close_ticket_command, commands=["close_ticket"])
    dp.register_callback_query_handler(callback_handler)
