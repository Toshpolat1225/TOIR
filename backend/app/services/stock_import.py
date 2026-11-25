"""Import of the 1C exports: stock balances, purchase orders to suppliers, supplier lead times (.xlsx or .csv, no extra dependency).

Three file shapes, recognised by the header row (or by `kind`):
  stock       Номенклатура | Код | Склад | Единица | Количество            (1C «Остатки на складах»)
  orders      Номенклатура | Код | Поставщик | Количество | Дата заказа | Ожидаемая дата [| Номер | Получено | Статус]   (1C «Заказы поставщикам»)
  lead_times  Номенклатура | Код | Срок поставки, дней [| Поставщик | Страховой запас, дней | Мин. партия]
Rows are matched to the catalogue by code first, then by exact name (case-insensitive). Not found / ambiguous rows are reported and never written.
Title rows above the header, group rows and «Итого» rows of a 1C report are skipped. Dry run by default; `apply=True` writes.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
import zipfile
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from xml.etree import ElementTree as ET

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutil import today_local

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_ROWS = 50000
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main", "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}

ALIASES: dict[str, tuple[str, ...]] = {
    "name": ("номенклатура", "наименование", "товар", "материал", "тмц", "name"),
    "code": ("код", "артикул", "код номенклатуры", "code"),
    "warehouse": ("склад", "место хранения", "warehouse"),
    "unit": ("единица", "ед. изм.", "ед.изм.", "ед. измерения", "единица измерения", "ед", "unit"),
    "qty": ("количество", "кол-во", "остаток", "количество остаток", "конечный остаток", "qty"),
    "department": ("подразделение", "участок", "department"),
    "as_of": ("дата", "на дату", "дата остатка", "as_of"),
    "supplier": ("поставщик", "контрагент", "supplier"),
    "ordered_on": ("дата заказа", "дата размещения", "ordered_on"),
    "expected_on": ("ожидаемая дата", "дата поставки", "срок поставки (дата)", "ожидаемая дата поставки", "expected_on"),
    "doc_no": ("номер", "номер заказа", "документ", "заказ", "doc_no"),
    "qty_received": ("получено", "принято", "qty_received"),
    "status": ("статус", "состояние", "status"),
    "lead_time_days": ("срок поставки", "срок поставки, дней", "срок поставки (дней)", "срок поставки дней", "срок, дней", "lead_time_days"),
    "safety_days": ("страховой запас, дней", "страховой запас", "страховой запас (дней)", "safety_days"),
    "min_order_qty": ("мин. партия", "минимальная партия", "мин. заказ", "min_order_qty"),
    "note": ("примечание", "комментарий", "note"),
}
STATUS_WORDS = {"заказан": "ordered", "ordered": "ordered", "в пути": "in_transit", "in_transit": "in_transit", "частично": "partial", "partial": "partial",
                "получен": "received", "received": "received", "закрыт": "received", "отменен": "cancelled", "отменён": "cancelled", "cancelled": "cancelled"}


class ImportError_(ValueError):
    """A file that cannot be read (bad format / too big). The message is shown to the user."""


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s if s is not None else "").replace("\xa0", " ")).strip().lower().replace("ё", "е")


# ------------------------------------------------------------------------------------------------------------------------ reading files


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref).group(0)  # type: ignore[union-attr]
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def read_xlsx(content: bytes) -> list[tuple[str, list[list[str]]]]:
    try:
        z = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ImportError_("Файл не является .xlsx") from exc
    with z:
        names = set(z.namelist())
        if "xl/workbook.xml" not in names:
            raise ImportError_("Файл не является .xlsx")
        shared: list[str] = []
        if "xl/sharedStrings.xml" in names:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
                shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
        rels = {r.get("Id"): r.get("Target") for r in ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))}
        out: list[tuple[str, list[list[str]]]] = []
        sheets_el = ET.fromstring(z.read("xl/workbook.xml")).find("m:sheets", NS)
        for sh in (list(sheets_el) if sheets_el is not None else []):
            target = rels.get(sh.get("{%s}id" % NS["r"]), "")
            path = target.lstrip("/") if target.startswith("/") else "xl/" + target
            if path not in names:
                continue
            rows: list[list[str]] = []
            for row in ET.fromstring(z.read(path)).iter("{%s}row" % NS["m"]):
                cells: dict[int, str] = {}
                for c in row.findall("m:c", NS):
                    t = c.get("t")
                    if t == "inlineStr":
                        val = "".join(x.text or "" for x in c.iter("{%s}t" % NS["m"]))
                    else:
                        v = c.find("m:v", NS)
                        val = "" if v is None or v.text is None else v.text
                        if t == "s" and val != "":
                            val = shared[int(val)]
                    cells[_col_index(c.get("r") or "A1")] = val
                at = int(row.get("r") or len(rows) + 1)
                if at > MAX_ROWS:
                    raise ImportError_("Слишком много строк")
                while len(rows) < at - 1:  # keep the sheet's own row numbers: the report tells the user which row is wrong
                    rows.append([])
                rows.append([cells.get(i, "") for i in range(max(cells) + 1)] if cells else [])
                if len(rows) > MAX_ROWS:
                    raise ImportError_("Слишком много строк")
            out.append((sh.get("name") or "", rows))
        return out


def read_csv(content: bytes) -> list[tuple[str, list[list[str]]]]:
    for enc in ("utf-8-sig", "cp1251"):
        try:
            body = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ImportError_("Не удалось прочитать кодировку CSV (нужна UTF-8 или Windows-1251)")
    sample = body[:4096]
    delimiter = max((";", ",", "\t"), key=sample.count)
    rows = [list(r) for r in csv.reader(io.StringIO(body, newline=""), delimiter=delimiter)]
    if len(rows) > MAX_ROWS:
        raise ImportError_("Слишком много строк")
    return [("csv", rows)]


def read_file(content: bytes, filename: str) -> list[tuple[str, list[list[str]]]]:
    if len(content) > MAX_FILE_BYTES:
        raise ImportError_("Файл больше 10 МБ")
    if filename.lower().endswith(".xlsx") or content[:2] == b"PK":
        return read_xlsx(content)
    if filename.lower().endswith((".csv", ".txt")):
        return read_csv(content)
    raise ImportError_("Нужен файл .xlsx или .csv")


# ------------------------------------------------------------------------------------------------------------------------ parsing rows


def _match_columns(header: list[str], kind: str | None = None) -> dict[str, int]:
    cols: dict[str, int] = {}
    normed = [_norm(h) for h in header]
    order = ("lead_time_days", "safety_days", "min_order_qty", "expected_on", "ordered_on", "qty_received", "doc_no", "warehouse", "code", "name", "unit", "qty",
             "supplier", "status", "department", "note", "as_of")
    for field in order:
        for i, h in enumerate(normed):
            if i in cols.values() or not h:
                continue
            if h in ALIASES[field]:
                cols[field] = i
                break
    # «Дата» alone in an orders file is the order date, in a stock file the balance date
    if kind == "orders" and "ordered_on" not in cols and "as_of" in cols:
        cols["ordered_on"] = cols.pop("as_of")
    return cols


def detect_kind(header: list[str], sheet_name: str = "") -> str | None:
    cols = _match_columns(header)
    sheet = _norm(sheet_name)
    if "name" not in cols and "code" not in cols:
        return None
    if "lead_time_days" in cols:
        return "lead_times"
    if "expected_on" in cols or ("supplier" in cols and ("ordered_on" in cols or "doc_no" in cols)) or sheet.startswith("заказ"):
        return "orders" if "qty" in cols else None
    if "qty" in cols:
        return "stock"
    return None


def find_header(rows: list[list[str]], sheet_name: str = "", kind: str | None = None) -> tuple[int, str] | None:
    for i, row in enumerate(rows[:30]):
        k = kind or detect_kind(row, sheet_name)
        cols = _match_columns(row, k)
        if k and ("name" in cols or "code" in cols) and (("qty" in cols) if k != "lead_times" else ("lead_time_days" in cols)):
            return i, k
    return None


def parse_number(v: Any) -> Decimal | None:
    s = str(v if v is not None else "").replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    if s in ("", "-"):
        return None
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def parse_date(v: Any) -> date | None:
    s = str(v if v is not None else "").strip()
    if not s:
        return None
    if re.fullmatch(r"\d{4,6}(\.\d+)?", s):
        n = float(s)
        return (datetime(1899, 12, 30) + timedelta(days=int(n))).date() if 20000 < n < 80000 else None
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


SKIP_WORDS = ("итого", "всего", "total")


def parse_rows(rows: list[list[str]], header_at: int, kind: str, *, as_of: date) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    """(records, invalid rows, skipped rows). Records carry the 1-based sheet row number."""
    cols = _match_columns(rows[header_at], kind)
    records: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    skipped = 0

    def cell(row: list[str], field: str) -> str:
        i = cols.get(field)
        return str(row[i]).strip() if i is not None and i < len(row) and row[i] is not None else ""

    for idx in range(header_at + 1, len(rows)):
        row = rows[idx]
        name, code = cell(row, "name"), cell(row, "code")
        if not any(str(c).strip() for c in row) or any(_norm(name).startswith(w) for w in SKIP_WORDS):
            skipped += 1
            continue
        rec: dict[str, Any] = {"row": idx + 1, "name": name, "code": code, "department": cell(row, "department")}
        if kind == "stock":
            qty = parse_number(cell(row, "qty"))
            if qty is None and not cell(row, "qty"):
                skipped += 1  # a group heading of the 1C report: no quantity
                continue
            rec.update(warehouse=cell(row, "warehouse"), unit=cell(row, "unit") or None, qty=qty, as_of=parse_date(cell(row, "as_of")) or as_of)
            if qty is None or qty < 0:
                invalid.append({"row": idx + 1, "name": name, "code": code, "reason": "количество не число или меньше 0"})
                continue
        elif kind == "orders":
            qty = parse_number(cell(row, "qty"))
            received = parse_number(cell(row, "qty_received")) or Decimal(0)
            status_raw = _norm(cell(row, "status"))
            if qty is None or qty <= 0 or received < 0:
                invalid.append({"row": idx + 1, "name": name, "code": code, "reason": "количество заказа должно быть больше 0"})
                continue
            status = STATUS_WORDS.get(status_raw) or ("received" if received >= qty else "partial" if received > 0 else "ordered")
            rec.update(supplier=cell(row, "supplier") or None, qty=qty, qty_received=received, ordered_on=parse_date(cell(row, "ordered_on")),
                       expected_on=parse_date(cell(row, "expected_on")), doc_no=cell(row, "doc_no") or None, status=status, note=cell(row, "note") or None)
        else:  # lead_times
            lead = parse_number(cell(row, "lead_time_days"))
            if lead is None or lead <= 0 or lead != lead.to_integral_value() or lead > 3650:
                invalid.append({"row": idx + 1, "name": name, "code": code, "reason": "срок поставки должен быть целым числом дней больше 0"})
                continue
            safety = parse_number(cell(row, "safety_days"))
            moq = parse_number(cell(row, "min_order_qty"))
            if (safety is not None and (safety < 0 or safety != safety.to_integral_value())) or (moq is not None and moq <= 0):
                invalid.append({"row": idx + 1, "name": name, "code": code, "reason": "страховой запас или мин. партия неверны"})
                continue
            rec.update(supplier=cell(row, "supplier") or None, lead_time_days=int(lead), safety_days=int(safety) if safety is not None else None, min_order_qty=moq, note=cell(row, "note") or None)
        if not name and not code:
            invalid.append({"row": idx + 1, "name": "", "code": "", "reason": "нет ни названия, ни кода"})
            continue
        records.append(rec)
    return records, invalid, skipped


# ------------------------------------------------------------------------------------------------------------------------ matching


class Catalogue:
    def __init__(self, rows: list[dict[str, Any]]):
        self.by_code: dict[str, list[dict[str, Any]]] = {}
        self.by_name: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            if r.get("code"):
                self.by_code.setdefault(_norm(r["code"]), []).append(r)
            self.by_name.setdefault(_norm(r["name"]), []).append(r)

    def match(self, name: str, code: str, department: str = "") -> tuple[str, dict[str, Any] | None]:
        """('ok', row) | ('not_found', None) | ('ambiguous', None). Code first, then the exact name."""
        dep = _norm(department)
        for found in (self.by_code.get(_norm(code), []) if code else [], self.by_name.get(_norm(name), []) if name else []):
            if dep:
                found = [f for f in found if _norm(f.get("department", "")) == dep]
            if len(found) == 1:
                return "ok", found[0]
            if len(found) > 1:
                return "ambiguous", None
        return "not_found", None


async def load_catalogue(db: AsyncSession) -> Catalogue:
    rows = (await db.execute(text("SELECT n.id, n.name, n.code, n.unit, d.name AS department FROM nomenclature n JOIN departments d ON d.id = n.department_id"))).mappings().all()
    return Catalogue([dict(r) for r in rows])


# ------------------------------------------------------------------------------------------------------------------------ the import


async def import_file(db: AsyncSession, content: bytes, filename: str, *, apply: bool, as_of: date | None = None, kind: str | None = None) -> dict[str, Any]:
    """Reads every sheet of the file, matches the rows and (apply=True) writes them in one transaction."""
    as_of = as_of or today_local()
    sheets = read_file(content, filename)
    catalogue = await load_catalogue(db)
    batch_id = uuid.uuid4()
    reports: list[dict[str, Any]] = []
    for sheet_name, rows in sheets:
        found = find_header(rows, sheet_name, kind)
        if not found:
            reports.append({"sheet": sheet_name, "kind": None, "error": "не найдена строка заголовков (Номенклатура / Количество ... )"})
            continue
        header_at, k = found
        records, invalid, skipped = parse_rows(rows, header_at, k, as_of=as_of)
        matched: list[dict[str, Any]] = []
        not_found: list[dict[str, Any]] = []
        ambiguous: list[dict[str, Any]] = []
        for rec in records:
            status, cat = catalogue.match(rec["name"], rec["code"], rec["department"])
            if status == "ok" and cat is not None:
                matched.append({**rec, "nomenclature_id": cat["id"], "catalogue_unit": cat["unit"]})
            else:
                (not_found if status == "not_found" else ambiguous).append({"row": rec["row"], "name": rec["name"], "code": rec["code"]})
        written = await _apply(db, k, matched, batch_id) if apply else {"would_write": len(matched)}
        reports.append({"sheet": sheet_name, "kind": k, "rows_read": len(records) + len(invalid), "matched": len(matched), "skipped": skipped,
                        "invalid": invalid[:100], "not_found": not_found[:200], "ambiguous": ambiguous[:200],
                        "not_found_count": len(not_found), "ambiguous_count": len(ambiguous), "invalid_count": len(invalid), **written})
    if apply:
        await db.commit()
    else:
        await db.rollback()
    return {"applied": apply, "batch_id": str(batch_id) if apply else None, "as_of": as_of, "sheets": reports}


async def _apply(db: AsyncSession, kind: str, matched: list[dict[str, Any]], batch_id: uuid.UUID) -> dict[str, int]:
    if kind == "stock":
        merged: dict[tuple[Any, str, date], dict[str, Any]] = {}
        for r in matched:  # several lines of one item in one warehouse (1C batches) are summed
            key = (r["nomenclature_id"], r["warehouse"] or "", r["as_of"])
            if key in merged:
                merged[key]["qty"] += r["qty"]
            else:
                merged[key] = {**r}
        for (nid, wh, as_of), r in merged.items():
            await db.execute(text(
                "INSERT INTO stock_balances (nomenclature_id, warehouse, qty, unit, as_of, source, batch_id) VALUES (:n,:w,:q,:u,:d,'1c_import',:b) "
                "ON CONFLICT (nomenclature_id, warehouse, as_of) DO UPDATE SET qty = EXCLUDED.qty, unit = EXCLUDED.unit, source = '1c_import', batch_id = EXCLUDED.batch_id"),
                {"n": nid, "w": wh, "q": r["qty"], "u": r["unit"] or r["catalogue_unit"], "d": as_of, "b": batch_id})
        return {"written": len(merged)}
    if kind == "orders":
        inserted = updated = 0
        for r in matched:
            existing = None
            if r["doc_no"]:
                existing = (await db.execute(text("SELECT id FROM purchase_orders WHERE nomenclature_id=:n AND doc_no=:d"), {"n": r["nomenclature_id"], "d": r["doc_no"]})).scalar_one_or_none()
            params = {"n": r["nomenclature_id"], "d": r["doc_no"], "s": r["supplier"], "q": r["qty"], "rc": r["qty_received"], "o": r["ordered_on"], "e": r["expected_on"], "st": r["status"], "nt": r["note"]}
            if existing:
                await db.execute(text("UPDATE purchase_orders SET supplier=:s, qty=:q, qty_received=:rc, ordered_on=:o, expected_on=:e, status=:st, note=:nt WHERE id=:id"), {**params, "id": existing})
                updated += 1
            else:
                await db.execute(text("INSERT INTO purchase_orders (nomenclature_id, doc_no, supplier, qty, qty_received, ordered_on, expected_on, status, note) VALUES (:n,:d,:s,:q,:rc,:o,:e,:st,:nt)"), params)
                inserted += 1
        return {"inserted": inserted, "updated": updated, "written": inserted + updated}
    for r in matched:
        await db.execute(text(
            "INSERT INTO supplier_terms (nomenclature_id, supplier, lead_time_days, min_order_qty, safety_days, note) VALUES (:n,:s,:l,:m,COALESCE(:sf,14),:nt) "
            "ON CONFLICT (nomenclature_id) DO UPDATE SET supplier=COALESCE(EXCLUDED.supplier, supplier_terms.supplier), lead_time_days=EXCLUDED.lead_time_days, "
            "min_order_qty=COALESCE(EXCLUDED.min_order_qty, supplier_terms.min_order_qty), safety_days=COALESCE(:sf, supplier_terms.safety_days), "
            "note=COALESCE(EXCLUDED.note, supplier_terms.note), updated_at=now()"),
            {"n": r["nomenclature_id"], "s": r["supplier"], "l": r["lead_time_days"], "m": r["min_order_qty"], "sf": r["safety_days"], "nt": r["note"]})
    return {"written": len(matched)}
