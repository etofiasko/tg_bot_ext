import json
import unittest
from email.message import Message
from io import BytesIO
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.parse import quote

import report_api_client as client


class ReportAPIClientTests(unittest.TestCase):
    def setUp(self):
        self.options = {
            "groups": [{"id": 1, "name": "весь мир"}],
            "countries": [{"id": 2, "name_ru": "Китай"}],
            "categories": [{"id": 3, "name": "СХ", "parent_id": None}],
        }
        self.arguments = dict(
            region="Республика Казахстан", country_or_group="Китай",
            start_year=None, end_year=2025, digit=4, category=None,
            category_parent=None, text_size=7, table_size=25,
            country_table_size=15, tn_ved=None, month_range_raw="",
            exclude_raw="", plain=0, include_regions=0,
            change_color=1,
        )
        self.headers = Message()
        self.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        self.filename = "РК - Китай (янв-мар 2025).docx"
        self.headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(self.filename)

    def generate(self, **changes):
        with patch.object(client, "get_report_options", return_value=self.options), \
             patch.object(client, "_request", return_value=(self.headers, b"document")) as request:
            result = client.generate_report(**dict(self.arguments, **changes))
        self.assertEqual(request.call_args.args[1]["filename_style"], "short")
        return request.call_args.args[1], result

    def test_country_filters_and_filename(self):
        payload, result = self.generate(start_year=2023, month_range_raw="2,6",
                                        category="Зерно", category_parent="СХ")
        self.assertEqual(payload["report_kind"], "country")
        self.assertEqual(payload["country"], "Китай")
        self.assertEqual(payload["start_year"], 2023)
        self.assertEqual((payload["month_from"], payload["month_to"]), (2, 6))
        self.assertEqual(payload["category_root"], [3])
        self.assertEqual(payload["category"], ["Зерно"])
        self.assertNotIn("long_report", payload)
        self.assertNotIn("old_report", payload)
        self.assertIs(payload["include_regions"], False)
        self.assertEqual(payload["exclude_tn_veds"], "")
        self.assertEqual(result["filename"], self.filename)
        self.assertEqual(result["short_filename"], self.filename)
        self.assertEqual(result["content"], b"document")

    def test_group_and_single_month(self):
        payload, _ = self.generate(country_or_group="весь мир", month_range_raw="6")
        self.assertEqual(payload["report_kind"], "group")
        self.assertEqual(payload["group"], "весь мир")
        self.assertEqual((payload["month_from"], payload["month_to"]), (6, 6))
        self.assertNotIn("start_year", payload)

    def test_product_preserves_leading_zero(self):
        payload, _ = self.generate(country_or_group="весь мир", tn_ved="0101")
        self.assertEqual(payload["report_kind"], "product")
        self.assertEqual(payload["tn_ved"], "0101")
        self.assertEqual(payload["group"], "весь мир")

    def test_exclusions_preserve_exact_codes(self):
        payload, _ = self.generate(exclude_raw="8411,841111,8802400011,851771")
        self.assertEqual(payload["exclude_tn_veds"], "8411")
        payload, _ = self.generate(digit=6, exclude_raw="8411,841111,8802400011,851771")
        self.assertEqual(payload["exclude_tn_veds"], "841111,851771")
        payload, _ = self.generate(digit=10, exclude_raw="8411,8802400011")
        self.assertEqual(payload["exclude_tn_veds"], "8802400011")

    def test_plane_uses_only_plane_filters(self):
        for partner, kind in [("Китай", "country"), ("весь мир", "group")]:
            with self.subTest(partner=partner):
                payload, _ = self.generate(plain=1, country_or_group=partner)
                self.assertEqual(payload, {
                    "report_kind": "plane", "region": "Республика Казахстан",
                    "end_year": 2025, "plane_partner": f"{kind}:{partner}",
                    "plane_color": "blue", "filename_style": "short",
                })

    def test_no_data_keeps_existing_result_contract(self):
        with patch.object(client, "get_report_options", return_value=self.options), \
             patch.object(client, "_request", side_effect=client.ReportAPIError("Нет данных", "no_data")):
            self.assertEqual(client.generate_report(**self.arguments), {"status": "no_data"})

    def test_does_not_send_json_as_document(self):
        self.headers.replace_header("Content-Type", "application/json")
        with self.assertRaises(client.ReportAPIError):
            self.generate()

    def test_request_uses_token_json_and_timeout(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.headers = self.headers
        response.read.return_value = b"document"
        with patch.object(client, "urlopen", return_value=response) as urlopen:
            client._request("/api/v1/reports/", {"report_kind": "country"})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Authorization"), "Token " + client.REPORT_API_TOKEN)
        self.assertEqual(json.loads(request.data), {"report_kind": "country"})
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 180)

    def test_http_errors_and_timeout_are_not_retried(self):
        for status, body, expected_code in [
            (422, {"error": {"code": "no_data", "message": "Нет данных"}}, "no_data"),
            (401, {"detail": "Invalid token."}, None),
            (504, None, None),
        ]:
            with self.subTest(status=status):
                content = json.dumps(body).encode() if body else b"<html>Gateway timeout</html>"
                error = HTTPError("https://example.invalid", status, "error", Message(), BytesIO(content))
                with patch.object(client, "urlopen", side_effect=error) as urlopen:
                    with self.assertRaises(client.ReportAPIError) as caught:
                        client._request("/api/v1/reports/", {})
                    self.assertEqual(caught.exception.code, expected_code)
                    urlopen.assert_called_once()
        with patch.object(client, "urlopen", side_effect=TimeoutError) as urlopen:
            with self.assertRaises(client.ReportAPIError):
                client._request("/api/v1/reports/", {})
            urlopen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
