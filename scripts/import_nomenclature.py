#!/usr/bin/env python3
"""Import nomenclature Excel files into the TOIR PostgreSQL database."""

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError, SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

BATCH_SIZE = 100

DEPARTMENTS = [
    ("Участок ПТОВ", "#0ea5e9"),
    ("Участок ПТОЛ", "#3b82f6"),
    ("Электровозное депо", "#8b5cf6"),
    ("Участок ВРП", "#22c55e"),
]

FILE_TO_DEPARTMENT = {
    "ПТОВ.xlsx": "Участок ПТОВ",
    "ПТОЛ ТО-2.xlsx": "Участок ПТОЛ",
    "ЭЛ_ДЕПО.xlsx": "Электровозное депо",
    "ВРП.xlsx": "Участок ВРП",
}


def get_base_dir() -> Path:
    script_dir = Path(__file__).resolve().parent
    folder_file = script_dir / "excel_folder.txt"
    if folder_file.exists():
        folder = folder_file.read_text(encoding="utf-8").strip()
        if folder:
            return Path(folder)
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    return Path(os.environ.get("EXCEL_BASE_DIR", r"C:\Users\User\Desktop\Отчёты ТОИР"))


def clean_cell(value: Any) -> str:
    if isinstance(value, pd.Series):
        value = value.iloc[0] if len(value) > 0 else None
    if pd.isna(value):
        return ""
    value = re.sub(r",+", ",", str(value).strip())
    return re.sub(r"^,|,$", "", value).strip()


def first_non_empty_row_index(frame: pd.DataFrame) -> int:
    for index in range(len(frame)):
        row = frame.iloc[index].astype(str).str.strip()
        if (row != "").any():
            return index
    return len(frame)


def infer_name_code_columns(frame: pd.DataFrame) -> tuple[Any | None, Any | None]:
    columns = [column for column in frame.columns if isinstance(column, str)]
    name_column = None
    code_column = None
    for column in columns:
        normalized = column.lower().strip()
        if any(
            label in normalized
            for label in (
                "наименование",
                "наименомание",
                "название",
                "номенклатура",
                "тмц",
            )
        ) or normalized == "name":
            name_column = column
        if any(label in normalized for label in ("код", "артикул")) or normalized in (
            "code",
            "№",
        ):
            code_column = column
    if name_column is None and code_column is not None and len(columns) >= 2:
        name_column = next(column for column in columns if column != code_column)
    if name_column is None and code_column is None and len(columns) >= 2:
        code_column, name_column = columns[0], columns[1]
    if name_column is None and columns:
        name_column = columns[0]
    if code_column is None and len(columns) >= 2:
        code_column = columns[1]
    return name_column, code_column


def load_and_clean_excel(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        print(f"  Пропуск (файл не найден): {path}")
        return []
    frame = pd.read_excel(path, header=None)
    if frame.empty:
        return []
    frame = frame.iloc[first_non_empty_row_index(frame) :].copy()
    frame.columns = [clean_cell(value) for value in frame.iloc[0]]
    frame = frame.iloc[1:].reset_index(drop=True).dropna(how="all")
    name_column, code_column = infer_name_code_columns(frame)
    if name_column is None:
        name_column = frame.columns[0]

    rows = []
    for _, row in frame.iterrows():
        name = clean_cell(row.get(name_column, ""))
        if not name:
            continue
        code = clean_cell(row.get(code_column, "")) if code_column else ""
        extra = {
            str(column): clean_cell(row.get(column, ""))
            for column in frame.columns
            if column not in (name_column, code_column)
        }
        rows.append(
            {
                "name": name,
                "code": code or None,
                "extra": {key: value for key, value in extra.items() if value},
            }
        )
    return rows


def database_url() -> URL:
    raw_url = os.environ.get("DATABASE_URL")
    if not raw_url:
        raise RuntimeError("Set DATABASE_URL in the environment before running this script.")
    parsed = make_url(raw_url)
    if parsed.get_backend_name() != "postgresql":
        raise RuntimeError("DATABASE_URL must point to PostgreSQL.")
    return parsed.set(drivername="postgresql+asyncpg")


async def import_files() -> None:
    engine = create_async_engine(database_url(), pool_pre_ping=True)
    try:
        async with engine.begin() as connection:
            department_ids: dict[str, Any] = {}
            for name, color in DEPARTMENTS:
                department_id = (
                    await connection.execute(
                        text(
                            """
                            INSERT INTO departments (name, color)
                            VALUES (:name, :color)
                            ON CONFLICT (name) DO UPDATE
                            SET color = EXCLUDED.color
                            RETURNING id
                            """
                        ),
                        {"name": name, "color": color},
                    )
                ).scalar_one()
                department_ids[name] = department_id

            base_dir = get_base_dir()
            for filename, department_name in FILE_TO_DEPARTMENT.items():
                rows = load_and_clean_excel(base_dir / filename)
                unique_rows = []
                seen_names = set()
                for row in rows:
                    if row["name"] not in seen_names:
                        seen_names.add(row["name"])
                        unique_rows.append(row)
                department_id = department_ids[department_name]
                imported = 0
                for start in range(0, len(unique_rows), BATCH_SIZE):
                    batch = unique_rows[start : start + BATCH_SIZE]
                    await connection.execute(
                        text(
                            """
                            INSERT INTO nomenclature
                                (department_id, name, code, unit, extra)
                            VALUES
                                (:department_id, :name, :code, 'шт.',
                                 CAST(:extra AS jsonb))
                            ON CONFLICT (department_id, name) DO UPDATE
                            SET code = EXCLUDED.code,
                                unit = EXCLUDED.unit,
                                extra = EXCLUDED.extra
                            """
                        ),
                        [
                            {
                                "department_id": department_id,
                                "name": row["name"],
                                "code": row["code"],
                                "extra": json.dumps(row["extra"], ensure_ascii=False),
                            }
                            for row in batch
                        ],
                    )
                    imported += len(batch)
                print(
                    f"   {filename} -> {department_name}: "
                    f"upsert {imported} ta yozuv"
                )
    finally:
        await engine.dispose()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        asyncio.run(import_files())
    except (ArgumentError, SQLAlchemyError) as error:
        print(f"Import failed ({type(error).__name__}); database details were withheld.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
