from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# Пример главного меню пользователя


from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_user_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton('📩 Новая заявка'),
        KeyboardButton('🎫 Мои заявки')
    )
    return keyboard

def get_admin_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(
        KeyboardButton('📋 Все заявки'),
        KeyboardButton('⚙️ Панель администратора'),
        KeyboardButton('🌐 Язык')
    )
    return keyboard

def get_ticket_detail_keyboard(ticket_code):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton(f'💬 Ответить', callback_data=f'reply_{ticket_code}'),
        InlineKeyboardButton(f'✏️ Редактировать', callback_data=f'edit_{ticket_code}'),
        InlineKeyboardButton(f'🔒 Закрыть', callback_data=f'close_{ticket_code}')
    )
    return keyboard

def get_back_button(callback: str = "back_to_main"):
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton("🔙 Назад", callback_data=callback)
    )
    return keyboard

def get_priority_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton('🔵 Низкий', callback_data='priority_low'),
        InlineKeyboardButton('🟠 Средний', callback_data='priority_medium'),
        InlineKeyboardButton('🔴 Высокий', callback_data='priority_high')
    )
    return keyboard


def get_category_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(
        InlineKeyboardButton('📂 Общий вопрос', callback_data='category_general'),
        InlineKeyboardButton('🛠 Техническая проблема', callback_data='category_technical'),
        InlineKeyboardButton('💰 Финансовый вопрос', callback_data='category_financial')
    )
    return keyboard
