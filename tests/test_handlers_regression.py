import contextlib
import unittest
from email.message import Message
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import quote

import handlers
import report_api_client as client


class MemoryState:
    def __init__(self):
        self.data = {}

    async def get_data(self):
        return self.data.copy()

    async def update_data(self, **values):
        self.data.update(values)

    async def finish(self):
        self.data.clear()


class HandlerRegressionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.state = MemoryState()
        self.message = SimpleNamespace(
            text='', from_user=SimpleNamespace(id=123, username='tester'),
            answer=AsyncMock(), reply=AsyncMock(), answer_document=AsyncMock(),
            edit_reply_markup=AsyncMock(),
        )
        self.callback = MagicMock(spec=handlers.types.CallbackQuery)
        self.callback.message = self.message
        self.callback.from_user = self.message.from_user
        self.callback.answer = AsyncMock()
        states = SimpleNamespace(**{
            name: SimpleNamespace(set=AsyncMock())
            for name in vars(handlers.StartNewStates)
            if not name.startswith('_')
        })
        replacements = {
            'StartNewStates': states,
            'get_user_role': MagicMock(return_value='admin'),
            'register_user': MagicMock(),
            'get_partners': MagicMock(return_value=['Индия', 'весь мир']),
            'get_categories': MagicMock(return_value=['СХ']),
            'get_subcategories': MagicMock(return_value=['Зерно']),
            'tnved_exists': MagicMock(return_value=True),
            'add_download_history': AsyncMock(),
        }
        for name, value in replacements.items():
            self.stack.enter_context(patch.object(handlers, name, value))
        self.history = replacements['add_download_history']
        self.stack.enter_context(patch('builtins.print'))
        options = {
            'groups': [{'name': 'весь мир'}],
            'countries': [{'name_ru': 'Индия'}],
            'categories': [{'id': 3, 'name': 'СХ', 'parent_id': None}],
        }
        self.stack.enter_context(patch.object(client, 'get_report_options', return_value=options))
        headers = Message()
        headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        self.filename = 'РК - Индия (янв-мар 2025).docx'
        headers['Content-Disposition'] = "attachment; filename*=UTF-8''" + quote(self.filename)
        self.request = self.stack.enter_context(patch.object(client, '_request', return_value=(headers, b'document')))

    async def enter(self, handler, text):
        self.message.text = text
        await handler(self.message, self.state)

    async def begin(self, variant, partner='Индия'):
        await handlers.start_new_handler(self.message, self.state)
        self.callback.data = variant
        await handlers.start_new_variant_chosen(self.callback, self.state)
        if variant == 'product_cb':
            await self.enter(handlers.start_new_waiting_tnved, '0101')
        else:
            await self.enter(handlers.start_new_partner, partner)
        await self.enter(handlers.start_new_year, '2025')

    async def confirm(self):
        self.callback.data = 'sn_confirm'
        await handlers.start_new_confirmation(self.callback, self.state)
        self.message.answer_document.assert_awaited_once()
        filename, stream = self.message.answer_document.call_args.args[0]
        self.assertEqual(filename, self.filename)
        self.assertEqual(stream.read(), b'document')
        self.message.answer.assert_awaited_with(
            f'Ваш документ {self.filename} готов. Чтобы начать заново, нажмите /start')
        self.history.assert_awaited_once()
        self.assertEqual(self.state.data, {})
        payload = self.request.call_args.args[1]
        self.assertEqual(payload['filename_style'], 'short')
        return payload

    async def test_country_without_category_and_hidden_alias(self):
        for choice in ('Без категории', 'бЕз КаТеГоРиИ', '---', '  ---  '):
            with self.subTest(choice=choice):
                self.message.answer_document.reset_mock()
                self.history.reset_mock()
                await self.begin('country_cb', 'иНдИя')
                keyboard = self.message.answer.call_args.kwargs['reply_markup'].to_python()
                self.assertNotIn('---', str(keyboard))
                await self.enter(handlers.start_new_category, choice)
                self.assertEqual(self.state.data['subcategory'], '')
                payload = await self.confirm()
                self.assertEqual(payload['country'], 'Индия')
                self.assertNotIn('category', payload)
                self.assertNotIn('category_root', payload)
                self.assertEqual(payload['exclude_tn_veds'], '8411,8517,8802')

    async def test_group_category_and_advanced_settings(self):
        await self.begin('country_cb', 'ВЕСЬ МИР')
        await self.enter(handlers.start_new_category, 'сх')
        await self.enter(handlers.start_new_subcategory, 'зЕРНО')
        self.callback.data = 'advanced_settings'
        await handlers.start_new_confirmation(self.callback, self.state)
        for handler, text in (
            (handlers.digit_settings_handler, '6 ЗНАКОВ'),
            (handlers.start_year_settings_handler, '2023'),
            (handlers.months_settings_handler, '2, 6'),
            (handlers.exclude_tnved_settings_handler, '8802400011'),
            (handlers.table_size_settings_handler, '500'),
            (handlers.country_table_size_settings_handler, '200'),
            (handlers.text_size_settings_handler, '100'),
            (handlers.long_report_settings_handler, 'ВКЛЮЧИТЬ'),
        ):
            await self.enter(handler, text)
        payload = self.request.call_args.args[1]
        for key, value in dict(report_kind='group', group='весь мир', category_root=[3],
                               category=['Зерно'], digit=6, start_year=2023,
                               month_from=2, month_to=6, exclude_tn_veds='',
                               table_size=500, country_table_size=200, text_size=100,
                               long_report=True).items():
            self.assertEqual(payload[key], value)
        self.message.answer_document.assert_awaited_once()
        self.history.assert_awaited_once()

    async def test_product(self):
        await self.begin('product_cb')
        payload = await self.confirm()
        self.assertEqual(payload['report_kind'], 'product')
        self.assertEqual(payload['tn_ved'], '0101')
        self.assertTrue(payload['long_report'])

    async def test_plane(self):
        await self.begin('plane_cb')
        payload = await self.confirm()
        self.assertEqual(payload, dict(report_kind='plane', region='Республика Казахстан',
                                       end_year=2025, plane_partner='country:Индия', plane_color='blue',
                                       filename_style='short'))

    async def test_no_data_and_api_failure(self):
        for code in ('no_data', 'generation_failed'):
            with self.subTest(code=code):
                await self.begin('country_cb')
                await self.enter(handlers.start_new_category, '---')
                self.request.side_effect = client.ReportAPIError('Test error', code)
                self.callback.data = 'sn_confirm'
                await handlers.start_new_confirmation(self.callback, self.state)
                self.message.answer_document.assert_not_awaited()
                self.history.assert_not_awaited()
                self.assertEqual(self.state.data, {})

    async def test_limits_reject_invalid_values_without_changing_state(self):
        for handler, field, maximum in (
            (handlers.table_size_settings_handler, 'table_size', 500),
            (handlers.country_table_size_settings_handler, 'country_table_size', 200),
            (handlers.text_size_settings_handler, 'text_size', 100),
        ):
            for invalid in ('0', str(maximum + 1), 'abc'):
                await self.enter(handler, invalid)
                self.assertNotIn(field, self.state.data)

    async def test_advanced_defaults_and_show_all_codes(self):
        await self.begin('country_cb')
        await self.enter(handlers.start_new_category, 'Без категории')
        for handler in (handlers.digit_settings_handler, handlers.start_year_settings_handler,
                        handlers.months_settings_handler, handlers.exclude_tnved_settings_handler,
                        handlers.table_size_settings_handler, handlers.country_table_size_settings_handler,
                        handlers.text_size_settings_handler, handlers.long_report_settings_handler):
            await self.enter(handler, 'ПРОПУСТИТЬ')
        payload = self.request.call_args.args[1]
        for key, value in dict(digit=4, text_size=7, table_size=25, country_table_size=15,
                               long_report=False, exclude_tn_veds='8411,8517,8802').items():
            self.assertEqual(payload[key], value)
        self.assertNotIn('start_year', payload)
        self.assertNotIn('month_from', payload)
        await self.enter(handlers.exclude_tnved_settings_handler, 'отображать все знаки тн вэд')
        self.assertEqual(self.state.data['exclude_tnved'], '')

    async def test_unknown_names_are_still_rejected(self):
        for handler in (handlers.start_new_partner, handlers.start_new_category,
                        handlers.start_new_subcategory):
            self.state.data = {'category_parent': 'СХ'}
            await self.enter(handler, 'несуществующее значение')
            self.assertEqual(self.state.data, {'category_parent': 'СХ'})

    async def test_restart_and_cancel(self):
        await self.begin('country_cb')
        await self.enter(handlers.start_new_category, 'НАЧАТЬ ЗАНОВО')
        self.assertEqual(self.state.data, {'user_role': 'admin'})
        self.callback.data = 'cancel_cb'
        await handlers.start_new_variant_chosen(self.callback, self.state)
        self.assertEqual(self.state.data, {})
        self.request.assert_not_called()


if __name__ == '__main__':
    unittest.main()
