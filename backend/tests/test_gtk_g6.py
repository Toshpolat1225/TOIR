from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


ROOT = Path(__file__).resolve().parents[2]


def _migration_config(output: StringIO) -> Config:
    config = Config(str(ROOT / "backend" / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(ROOT / "backend" / "alembic"))
    return config


def test_gtk_alembic_chain_has_one_head_and_is_contiguous():
    config = _migration_config(StringIO())
    script = ScriptDirectory.from_config(config)
    expected = [
        ("0012_wialon_units", "0011_wialon_counter_state"),
        ("0013_gtk_source", "0012_wialon_units"),
        ("0014_fixed_assets_gtk_id", "0013_gtk_source"),
        ("0015_gtk_wagon_mileage", "0014_fixed_assets_gtk_id"),
        ("0016_gtk_mirror_cleanup", "0015_gtk_wagon_mileage"),
    ]

    assert len(script.get_heads()) == 1
    for revision, previous in expected:
        migration = script.get_revision(revision)
        assert migration is not None
        assert len(migration.revision) <= 32
        assert migration.down_revision == previous


def test_gtk_migrations_render_offline_upgrade_and_downgrade_sql():
    upgrade_output = StringIO()
    downgrade_output = StringIO()
    with patch("logging.config.fileConfig"):
        command.upgrade(
            _migration_config(upgrade_output), "0016_gtk_mirror_cleanup", sql=True
        )
        command.downgrade(
            _migration_config(downgrade_output),
            "0016_gtk_mirror_cleanup:0012_wialon_units",
            sql=True,
        )

    upgrade_sql = upgrade_output.getvalue()
    assert "CREATE TABLE gtk_sync_runs" in upgrade_sql
    assert "gtk_wagon_mileage_log" in upgrade_sql

    downgrade_sql = downgrade_output.getvalue()
    assert "DROP TABLE gtk_sync_runs" in downgrade_sql
    assert "DROP TABLE gtk_wagon_mileage_log" in downgrade_sql


def test_gtk_related_sources_have_no_foreign_alphabet_characters():
    files = [
        *sorted((ROOT / "app" / "dashboard" / "os" / "gtk").rglob("*.tsx")),
        ROOT / "lib" / "api.ts",
        ROOT / "app" / "dashboard" / "os" / "page.tsx",
        *sorted((ROOT / "backend" / "app" / "routers").glob("gtk*.py")),
        *sorted((ROOT / "backend" / "app" / "services").glob("gtk*.py")),
        ROOT / "backend" / "app" / "services" / "mileage_attribution.py",
        *sorted((ROOT / "backend" / "app" / "integrations").glob("gtk*.py")),
        *sorted((ROOT / "backend" / "app" / "schemas").glob("gtk*.py")),
        *sorted((ROOT / "backend" / "app" / "repositories").glob("gtk*.py")),
        *sorted((ROOT / "backend" / "alembic" / "versions").glob("001[3-6]_*.py")),
        *sorted((ROOT / "docs").rglob("*.md")),
    ]
    forbidden = set("үөҮӨқғҳў")
    violations = []

    for path in files:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            found = forbidden.intersection(line)
            if found:
                violations.append(f"{path.relative_to(ROOT)}:{line_number}: {''.join(sorted(found))}")

    assert not violations, "\n".join(violations)


def test_dockerignore_excludes_sensitive_and_large_build_inputs():
    required = {
        ".env*",
        "gtk_snapshot.json",
        "gtk_page_*.html",
        "gtk_data_*.json",
        "*.csv",
        "*.dump",
        "node_modules",
        ".next",
        ".git",
        ".venv",
        "backend/.venv",
        "*.tsbuildinfo",
    }

    for ignore_path in (ROOT / ".dockerignore", ROOT / "backend" / ".dockerignore"):
        patterns = {
            line.strip()
            for line in ignore_path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        assert required <= patterns, f"Missing patterns in {ignore_path}"

    frontend_dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY . ." in frontend_dockerfile
