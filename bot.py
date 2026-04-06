from aiogram import Bot, Dispatcher, executor, types
import pandas as pd 
from config import API_TOKEN
from handlers import (
    access_settings_handler,
    handle_access_data,
    download_history_handler,
    start_new_handler,
    start_new_variant_chosen,
    start_new_waiting_tnved,
    start_new_partner,
    start_new_year,
    start_new_category,
    start_new_subcategory,
    start_new_confirmation,
    digit_settings_handler,
    start_year_settings_handler,
    months_settings_handler,
    exclude_tnved_settings_handler,
    table_size_settings_handler,
    country_table_size_settings_handler,
    text_size_settings_handler,
    long_report_settings_handler)
from aiogram.types import Message
from states import StartNewStates
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from bot_db import setup_users_tables


setup_users_tables()


bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())



@dp.message_handler(commands=['access_settings'])
async def cmd_access_settings(message: Message):
    await access_settings_handler(message)

@dp.message_handler(state=StartNewStates.waiting_for_access_data)
async def process_access_settings(message: types.Message, state: FSMContext):
    await handle_access_data(message, state)

@dp.message_handler(commands=['history'])
async def cmd_history(message: types.Message):
    await download_history_handler(message)

@dp.message_handler(commands=['start'], state='*')
async def cmd_start_new(message: Message, state: FSMContext):
    await start_new_handler(message, state)

@dp.callback_query_handler(state=StartNewStates.choosing_variant)
async def cbq_start_new_variant(cbq: types.CallbackQuery, state: FSMContext):
    await start_new_variant_chosen(cbq, state)

@dp.message_handler(state=StartNewStates.waiting_for_tnved)
async def msg_start_new_tnved(message: Message, state: FSMContext):
    await start_new_waiting_tnved(message, state)

@dp.message_handler(state=StartNewStates.choosing_partner)
async def msg_start_new_partner(message: Message, state: FSMContext):
    await start_new_partner(message, state)

@dp.message_handler(state=StartNewStates.choosing_year)
async def msg_start_new_year(message: Message, state: FSMContext):
    await start_new_year(message, state)

@dp.message_handler(state=StartNewStates.choosing_category)
async def msg_start_new_category(message: Message, state: FSMContext):
    await start_new_category(message, state)

@dp.message_handler(state=StartNewStates.choosing_subcategory)
async def msg_start_new_subcategory(message: Message, state: FSMContext):
    await start_new_subcategory(message, state)

@dp.callback_query_handler(state=StartNewStates.confirmation)
async def cbq_start_new_confirmation(cbq: types.CallbackQuery, state: FSMContext):
    await start_new_confirmation(cbq, state)


@dp.message_handler(state=StartNewStates.choosing_digit_settings)
async def msg_digit_settings_handler(message: Message, state: FSMContext):
    await digit_settings_handler(message, state)
    
@dp.message_handler(state=StartNewStates.choosing_start_year_settings)
async def msg_start_year_settings_handler(message: Message, state: FSMContext):
    await start_year_settings_handler(message, state)
    
@dp.message_handler(state=StartNewStates.choosing_months_settings)
async def msg_months_settings_handler(message: Message, state: FSMContext):
    await months_settings_handler(message, state)
    
@dp.message_handler(state=StartNewStates.choosing_exclude_tnved_settings)
async def msg_exclude_tnved_settings_handler(message: Message, state: FSMContext):
    await exclude_tnved_settings_handler(message, state)
    
@dp.message_handler(state=StartNewStates.choosing_table_size_settings)
async def msg_table_size_settings_handler(message: Message, state: FSMContext):
    await table_size_settings_handler(message, state)
    
@dp.message_handler(state=StartNewStates.choosing_country_table_size_settings)
async def msg_country_table_size_settings_handler(message: Message, state: FSMContext):
    await country_table_size_settings_handler(message, state)
    
@dp.message_handler(state=StartNewStates.choosing_text_size_settings)
async def msg_text_size_settings_handler(message: Message, state: FSMContext):
    await text_size_settings_handler(message, state)
    
@dp.message_handler(state=StartNewStates.choosing_long_report_settings)
async def msg_long_report_settings_handler(message: Message, state: FSMContext):
    await long_report_settings_handler(message, state)


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
