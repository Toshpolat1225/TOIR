"""Baseline schema for the local TOIR PostgreSQL database.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-06
"""

from pathlib import Path
import re

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def _split_sql(source: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    index = 0
    single_quoted = False
    double_quoted = False
    line_comment = False
    block_comment_depth = 0
    dollar_quote: str | None = None

    while index < len(source):
        if line_comment:
            char = source[index]
            current.append(char)
            index += 1
            if char == "\n":
                line_comment = False
            continue

        if block_comment_depth:
            if source.startswith("/*", index):
                current.append("/*")
                block_comment_depth += 1
                index += 2
            elif source.startswith("*/", index):
                current.append("*/")
                block_comment_depth -= 1
                index += 2
            else:
                current.append(source[index])
                index += 1
            continue

        if dollar_quote is not None:
            if source.startswith(dollar_quote, index):
                current.append(dollar_quote)
                index += len(dollar_quote)
                dollar_quote = None
            else:
                current.append(source[index])
                index += 1
            continue

        char = source[index]
        if single_quoted:
            current.append(char)
            index += 1
            if char == "'":
                if index < len(source) and source[index] == "'":
                    current.append(source[index])
                    index += 1
                else:
                    single_quoted = False
            continue

        if double_quoted:
            current.append(char)
            index += 1
            if char == '"':
                if index < len(source) and source[index] == '"':
                    current.append(source[index])
                    index += 1
                else:
                    double_quoted = False
            continue

        if source.startswith("--", index):
            current.append("--")
            line_comment = True
            index += 2
            continue

        if source.startswith("/*", index):
            current.append("/*")
            block_comment_depth = 1
            index += 2
            continue

        if char == "'":
            single_quoted = True
            current.append(char)
            index += 1
            continue

        if char == '"':
            double_quoted = True
            current.append(char)
            index += 1
            continue

        if char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z_0-9]*\$|\$\$", source[index:])
            if match is not None:
                dollar_quote = match.group(0)
                current.append(dollar_quote)
                index += len(dollar_quote)
                continue

        if char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current.clear()
            index += 1
            continue

        current.append(char)
        index += 1

    remaining = "".join(current).strip()
    if remaining:
        statements.append(remaining)
    return statements


def upgrade() -> None:
    sql_path = Path(__file__).with_name("0001_baseline.sql")
    for statement in _split_sql(sql_path.read_text(encoding="utf-8")):
        op.execute(statement)


def downgrade() -> None:
    for table in (
        "ai_insights",
        "maintenance_log",
        "maintenance_plan",
        "tmc_document_items",
        "tmc_documents",
        "work_order_items",
        "work_order_repairs",
        "work_orders",
        "work_type_templates",
        "nomenclature_norms",
        "nomenclature",
        "maintenance_intervals",
        "work_subtasks",
        "work_types",
        "wialon_settings",
        "mileage_history",
        "fixed_assets",
        "employees",
        "refresh_tokens",
        "users",
        "sections",
        "departments",
    ):
        op.drop_table(table)

    op.execute("DROP SEQUENCE IF EXISTS work_order_seq")
    op.execute("DROP FUNCTION IF EXISTS notify_change()")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at()")
