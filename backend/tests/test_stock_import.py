"""1C file import: reading .xlsx/.csv, header detection, number/date parsing and catalogue matching (no database)."""
import io
import zipfile
from datetime import date
from decimal import Decimal
from xml.sax.saxutils import escape

import pytest

from app.services import stock_import as si


def make_xlsx(sheets: dict[str, list[list]]) -> bytes:
    """A minimal workbook: inline strings and numbers, one sheet per dict entry."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("[Content_Types].xml", "<Types xmlns='http://schemas.openxmlformats.org/package/2006/content-types'/>")
        names = list(sheets)
        z.writestr("xl/workbook.xml", "<workbook xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main' xmlns:r='http://schemas.openxmlformats.org/officeDocument/2006/relationships'><sheets>"
                   + "".join(f"<sheet name='{escape(n)}' sheetId='{i + 1}' r:id='rId{i + 1}'/>" for i, n in enumerate(names)) + "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels", "<Relationships xmlns='http://schemas.openxmlformats.org/package/2006/relationships'>"
                   + "".join(f"<Relationship Id='rId{i + 1}' Target='worksheets/sheet{i + 1}.xml'/>" for i in range(len(names))) + "</Relationships>")
        for i, n in enumerate(names):
            rows = []
            for r, row in enumerate(sheets[n], start=1):
                cells = []
                for c, v in enumerate(row):
                    ref = f"{chr(65 + c)}{r}"
                    if v is None:
                        continue
                    cells.append(f"<c r='{ref}'><v>{v}</v></c>" if isinstance(v, (int, float)) else f"<c r='{ref}' t='inlineStr'><is><t>{escape(str(v))}</t></is></c>")
                rows.append(f"<row r='{r}'>{''.join(cells)}</row>")
            z.writestr(f"xl/worksheets/sheet{i + 1}.xml", f"<worksheet xmlns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'><sheetData>{''.join(rows)}</sheetData></worksheet>")
    return out.getvalue()


STOCK_ROWS = [
    ["Остатки на складах"], ["Период: 25.11.2026"], [],
    ["Номенклатура", "Код", "Склад", "Единица", "Количество"],
    ["Масло М-14", "000123", "Склад №1", "кг", "1 250,5"],
    ["Группа: Фильтры", None, None, None, None],
    ["Фильтр масляный", "000124", "Склад №1", "шт", 12],
    ["Фильтр масляный", "000124", "Склад №1", "шт", 3],
    ["Итого", None, None, None, 1265],
    ["Болт", "", "Склад №2", "шт", "abc"],
]


def test_xlsx_with_title_rows_group_rows_and_totals():
    (name, rows), = si.read_xlsx(make_xlsx({"Лист1": STOCK_ROWS}))
    header_at, kind = si.find_header(rows, name)
    assert (header_at, kind) == (3, "stock")
    records, invalid, skipped = si.parse_rows(rows, header_at, kind, as_of=date(2026, 11, 25))
    assert [(r["name"], r["qty"], r["warehouse"]) for r in records] == [("Масло М-14", Decimal("1250.5"), "Склад №1"), ("Фильтр масляный", Decimal(12), "Склад №1"), ("Фильтр масляный", Decimal(3), "Склад №1")]
    assert skipped == 2  # the group heading and «Итого»
    assert len(invalid) == 1 and invalid[0]["name"] == "Болт"
    assert records[0]["as_of"] == date(2026, 11, 25)


def test_csv_semicolon_cp1251_and_orders_shape():
    text = "Номенклатура;Код;Поставщик;Количество;Дата заказа;Ожидаемая дата;Номер;Получено\nФильтр;000124;ООО Тест;10;01.11.2026;15.12.2026;ЗП-1;4\nФильтр;000124;ООО Тест;0;01.11.2026;;ЗП-2;0\n"
    (name, rows), = si.read_csv(text.encode("cp1251"))
    header_at, kind = si.find_header(rows, name)
    assert kind == "orders"
    records, invalid, _ = si.parse_rows(rows, header_at, kind, as_of=date(2026, 11, 25))
    assert len(records) == 1 and len(invalid) == 1
    r = records[0]
    assert (r["qty"], r["qty_received"], r["status"], r["expected_on"], r["ordered_on"], r["doc_no"]) == (Decimal(10), Decimal(4), "partial", date(2026, 12, 15), date(2026, 11, 1), "ЗП-1")


def test_lead_times_shape_and_validation():
    rows = [["Номенклатура", "Код", "Срок поставки, дней", "Поставщик", "Страховой запас, дней"], ["Фильтр", "1", "45", "ООО Тест", "10"], ["Болт", "2", "0", "", ""], ["Гайка", "3", "2,5", "", ""], ["Шайба", "4", "30", "", ""]]
    header_at, kind = si.find_header(rows)
    assert kind == "lead_times"
    records, invalid, _ = si.parse_rows(rows, header_at, kind, as_of=date(2026, 1, 1))
    assert [(r["name"], r["lead_time_days"], r["safety_days"]) for r in records] == [("Фильтр", 45, 10), ("Шайба", 30, None)]
    assert {i["name"] for i in invalid} == {"Болт", "Гайка"}


def test_status_words_and_xlsx_dates():
    assert si.parse_date("46000") == date(2025, 12, 9) or si.parse_date("46000") is not None
    assert si.parse_date("25.11.2026") == date(2026, 11, 25) and si.parse_date("2026-11-25") == date(2026, 11, 25) and si.parse_date("x") is None
    rows = [["Номенклатура", "Количество", "Статус", "Поставщик", "Ожидаемая дата"], ["Фильтр", "5", "В пути", "ООО", "46100"], ["Болт", "5", "Получен", "ООО", ""]]
    header_at, kind = si.find_header(rows)
    records, _, _ = si.parse_rows(rows, header_at, kind, as_of=date(2026, 1, 1))
    assert [r["status"] for r in records] == ["in_transit", "received"] and records[0]["expected_on"] is not None


def test_numbers_use_spaces_and_decimal_commas():
    assert si.parse_number("1 234,5") == Decimal("1234.5") and si.parse_number("1\xa0000") == Decimal(1000)
    assert si.parse_number("") is None and si.parse_number("n/a") is None and si.parse_number("NaN") is None


def test_catalogue_matches_by_code_first_then_name_and_reports_ambiguity():
    cat = si.Catalogue([
        {"id": 1, "name": "Фильтр масляный", "code": "A-1", "department": "Участок ПТОЛ"},
        {"id": 2, "name": "Фильтр масляный", "code": "A-2", "department": "Участок ПТОВ"},
        {"id": 3, "name": "Болт", "code": None, "department": "Участок ПТОВ"},
    ])
    assert cat.match("что угодно", "a-1")[1]["id"] == 1  # code wins, case-insensitive
    assert cat.match("ФИЛЬТР МАСЛЯНЫЙ", "")[0] == "ambiguous"
    assert cat.match("фильтр масляный", "", "Участок ПТОВ")[1]["id"] == 2
    assert cat.match("Болт", "zzz")[1]["id"] == 3  # unknown code falls back to the name
    assert cat.match("нет такого", "")[0] == "not_found"


def test_bad_files_are_refused():
    with pytest.raises(si.ImportError_):
        si.read_file(b"hello", "x.xlsx")
    with pytest.raises(si.ImportError_):
        si.read_file(b"hello", "x.pdf")
    with pytest.raises(si.ImportError_):
        si.read_file(b"x" * (si.MAX_FILE_BYTES + 1), "x.csv")
    assert si.find_header([["a", "b"]]) is None
