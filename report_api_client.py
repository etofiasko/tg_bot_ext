"""Получение готовых справок через API data_platform."""

import json
from email.message import Message
from pathlib import PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import DATA_PLATFORM_URL, REPORT_API_TOKEN


class ReportAPIError(RuntimeError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def _request(path, payload=None):
    request = Request(
        DATA_PLATFORM_URL + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
        headers={
            "Authorization": "Token " + REPORT_API_TOKEN,
            "Content-Type": "application/json",
        },
        method="POST" if payload is not None else "GET",
    )
    try:
        with urlopen(request, timeout=180) as response:
            if response.status != 200:
                raise ReportAPIError(f"Сервер вернул HTTP {response.status}")
            return response.headers, response.read()
    except HTTPError as error:
        details = {}
        try:
            details = json.loads(error.read())
        except (ValueError, UnicodeDecodeError):
            pass
        if not isinstance(details, dict):
            details = {}
        api_error = details.get("error")
        if not isinstance(api_error, dict):
            api_error = {}
        raise ReportAPIError(
            details.get("detail") or api_error.get("message") or f"Сервер вернул HTTP {error.code}",
            api_error.get("code"),
        ) from error
    except (TimeoutError, URLError) as error:
        raise ReportAPIError("Не удалось дождаться ответа API справок.") from error


def get_report_options():
    headers, body = _request("/api/v1/reports/options/")
    if headers.get_content_type() != "application/json":
        raise ReportAPIError("API вернул неверный формат списка фильтров.")
    options = json.loads(body)
    if not isinstance(options, dict):
        raise ReportAPIError("API вернул неверный список фильтров.")
    return options


def generate_report(*, region, country_or_group, start_year, end_year, digit,
                    category, category_parent, text_size, table_size,
                    country_table_size, tn_ved, month_range_raw, exclude_raw,
                    plain, include_regions, change_color):
    options = get_report_options()
    groups = {item["name"] for item in options["groups"]}
    countries = {item["name_ru"] for item in options["countries"]}
    if country_or_group in groups:
        partner_kind = "group"
    elif country_or_group in countries:
        partner_kind = "country"
    else:
        raise ReportAPIError("Выбранного партнёра нет в списке API.")

    payload = {"region": region, "end_year": end_year, "filename_style": "short"}
    if plain:
        payload.update(
            report_kind="plane",
            plane_partner=f"{partner_kind}:{country_or_group}",
            plane_color="blue" if change_color else "pink",
        )
    else:
        payload.update(
            report_kind="product" if tn_ved else partner_kind,
            digit=digit,
            include_regions=bool(include_regions),
            report_style="blue" if change_color else "basic",
            text_size=text_size,
            table_size=table_size,
            country_table_size=country_table_size,
            # The generator matches exact codes; the API also requires this digit length.
            exclude_tn_veds=",".join(dict.fromkeys(
                code.strip() for code in exclude_raw.split(",") if len(code.strip()) == digit
            )),
        )
        if tn_ved:
            if partner_kind != "group":
                raise ReportAPIError("Для справки по товару необходимо выбрать группу стран.")
            payload.update(group=country_or_group, tn_ved=tn_ved)
        else:
            payload[partner_kind] = country_or_group
        if start_year is not None:
            payload["start_year"] = start_year
        if month_range_raw:
            months = [int(value) for value in month_range_raw.split(",")]
            payload.update(month_from=months[0], month_to=months[-1])
        if category:
            roots = [item for item in options["categories"]
                     if item["parent_id"] is None and item["name"] == category_parent]
            if len(roots) != 1:
                raise ReportAPIError("Выбранной категории нет в списке API.")
            payload.update(category_root=[roots[0]["id"]], category=[category])

    try:
        headers, body = _request("/api/v1/reports/", payload)
    except ReportAPIError as error:
        if error.code == "no_data":
            return {"status": "no_data"}
        raise
    if headers.get_content_type() != "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        raise ReportAPIError("API не вернул документ Word.")
    if not body:
        raise ReportAPIError("API вернул пустой документ.")
    disposition = Message()
    disposition["Content-Disposition"] = headers.get("Content-Disposition", "")
    filename = disposition.get_filename() or "Справка.docx"
    filename = PurePosixPath(filename.replace("\\", "/")).name or "Справка.docx"
    return {"status": "ok", "content": body, "filename": filename, "short_filename": filename}
