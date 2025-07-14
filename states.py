from aiogram.dispatcher.filters.state import State, StatesGroup

class TicketStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_priority = State()
    waiting_for_category = State()
    waiting_for_reply = State()
    waiting_for_feedback_rating = State()
    waiting_for_feedback_text = State()
    editing_text = State()
    editing_priority = State()
    editing_category = State()
    creating_template_name = State()
    creating_template_text = State()
