import contextlib
import io
import re
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from app.models import Base


ROOT = Path(__file__).resolve().parents[2]
LEGACY_ASSET_COLUMNS = {
    "name",
    "series",
    "depot",
    "number",
    "number_normalized",
    "org_unit_id",
    "comm_date",
}


def _schema_table_columns(sql: str) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    sql = re.sub(r"--.*?$", "", sql, flags=re.MULTILINE)
    pattern = re.compile(
        r"CREATE\s+TABLE\s+([A-Za-z_][A-Za-z_0-9]*)\s*\(",
        re.IGNORECASE,
    )
    for match in pattern.finditer(sql):
        depth = 1
        index = match.end()
        start = index
        elements: list[str] = []
        while depth and index < len(sql):
            char = sql[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            elif char == "," and depth == 1:
                elements.append(sql[start:index])
                start = index + 1
            index += 1
        elements.append(sql[start : index - 1])
        columns = set()
        for element in elements:
            column = re.match(r"\s*([A-Za-z_][A-Za-z_0-9]*)\s+", element)
            if column and column.group(1).upper() not in {
                "CONSTRAINT",
                "PRIMARY",
                "UNIQUE",
                "CHECK",
                "FOREIGN",
            }:
                columns.add(column.group(1))
        tables[match.group(1)] = columns
    return tables


def test_orm_columns_match_canonical_schema() -> None:
    schema_sql = (ROOT / "postgres" / "schema.sql").read_text(encoding="utf-8")
    schema = _schema_table_columns(schema_sql)
    mismatches = {
        table_name: {
            "missing": sorted(set(table.columns.keys()) - schema.get(table_name, set())),
            "extra": sorted(schema.get(table_name, set()) - set(table.columns.keys())),
        }
        for table_name, table in Base.metadata.tables.items()
        if set(table.columns.keys()) != schema.get(table_name, set())
    }
    details = "\n".join(
        f"{table}: missing={values['missing']}; extra={values['extra']}"
        for table, values in mismatches.items()
    )
    assert not mismatches, details
    assert not LEGACY_ASSET_COLUMNS.intersection(schema["fixed_assets"])
    assert not LEGACY_ASSET_COLUMNS.intersection(
        set(Base.metadata.tables["fixed_assets"].columns.keys())
    )
    asset_indexes = set(
        re.findall(
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+([A-Za-z_][A-Za-z_0-9]*)\s+ON\s+fixed_assets\b",
            schema_sql,
            re.IGNORECASE,
        )
    )
    assert asset_indexes == {
        index.name for index in Base.metadata.tables["fixed_assets"].indexes
    }


def test_views_and_reference_seeds_have_one_source() -> None:
    schema = (ROOT / "postgres" / "schema.sql").read_text(encoding="utf-8")
    views = set(
        re.findall(r"CREATE\s+OR\s+REPLACE\s+VIEW\s+([A-Za-z_][A-Za-z_0-9]*)", schema)
    )
    assert views == {
        "work_order_tmc_details",
        "executive_summary",
        "section_efficiency",
        "work_type_efficiency",
        "monthly_efficiency",
        "ai_insights_summary",
        "fleet_health",
        "maintenance_schedule",
    }
    assert "fa.name" not in schema
    for table in (
        "fixed_asset_types",
        "fixed_asset_statuses",
        "fixed_asset_type_translations",
        "fixed_asset_status_translations",
        "permissions",
        "role_permissions",
    ):
        assert not re.search(rf"INSERT\s+INTO\s+{table}\b", schema, re.IGNORECASE)
    assert "tank_car" in (
        ROOT / "backend" / "alembic" / "versions" / "0021_fixed_asset_types.py"
    ).read_text(encoding="utf-8")
    assert "INSERT INTO role_permissions" in (
        ROOT / "backend" / "alembic" / "versions" / "0020_p7_permission_grants.py"
    ).read_text(encoding="utf-8")


def test_alembic_head_and_offline_contract_render(monkeypatch) -> None:
    monkeypatch.setenv("POSTGRES_DB", "schema_test")
    monkeypatch.setenv("POSTGRES_USER", "schema_test")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test-only-not-a-real-password")
    monkeypatch.setenv("JWT_SECRET", "test-only-secret-value-that-is-at-least-32-bytes")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost")
    config = Config(str(ROOT / "backend" / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    with contextlib.redirect_stdout(io.StringIO()):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            command.upgrade(
                config,
                "0022_asset_number_dupes:head",
                sql=True,
            )
    rendered = output.getvalue()
    versions = ROOT / "backend" / "alembic" / "versions"
    revision_ids = []
    for path in versions.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        revision = re.search(r'^revision\s*=\s*"([^"]+)"', source, re.MULTILINE)
        if revision:
            revision_ids.append(revision.group(1))
            assert len(revision.group(1)) <= 32
    assert len({revision for revision in revision_ids}) == len(revision_ids)
    assert "0024_asset_column_contract" in revision_ids
    assert "0025_russian_only" in revision_ids
    assert all(
        f"DROP COLUMN IF EXISTS {column}" in rendered
        for column in LEGACY_ASSET_COLUMNS
    )
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1


def test_schema_and_new_migrations_have_clean_locale_characters() -> None:
    forbidden = re.compile("[ўқғҳЎҚҒҲӨөҮү]")
    paths = [
        ROOT / "postgres" / "schema.sql",
        ROOT / "backend" / "alembic" / "versions" / "0023_canonical_asset_indexes.py",
        ROOT / "backend" / "alembic" / "versions" / "0024_fixed_asset_column_contract.py",
        ROOT / "backend" / "alembic" / "versions" / "0025_russian_only_locales.py",
    ]
    for path in paths:
        assert not forbidden.search(path.read_text(encoding="utf-8")), str(path)


def test_localization_schema_accepts_only_russian() -> None:
    schema = (ROOT / "postgres" / "schema.sql").read_text(encoding="utf-8")
    assert schema.count("CHECK (locale = 'ru')") == 7
    assert "locale IN ('uz-Latn','uz-Cyrl','ru')" not in schema

    migration = (
        ROOT / "backend" / "alembic" / "versions" / "0025_russian_only_locales.py"
    ).read_text(encoding="utf-8")
    assert "DELETE FROM {table} WHERE locale <> 'ru'" in migration
    assert "op.create_check_constraint(constraint, table, \"locale = 'ru'\")" in migration
