from aiogram.dispatcher.filters.state import State, StatesGroup


class StartNewStates(StatesGroup):
    choosing_variant = State()
    waiting_for_tnved = State()
    choosing_partner = State()
    choosing_year = State()
    choosing_category = State()
    choosing_subcategory = State()
    confirmation = State()
    waiting_for_access_data = State()
    choosing_digit_settings = State()
    choosing_start_year_settings = State()
    choosing_months_settings = State()
    choosing_exclude_tnved_settings = State()
    choosing_table_size_settings = State()
    choosing_country_table_size_settings = State()
    choosing_text_size_settings = State()
    choosing_long_report_settings = State()
