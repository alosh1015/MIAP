from __future__ import annotations

import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.core import migrations
from app.core.config import get_settings


def _schema(path: Path) -> dict[str, str]:
    connection = sqlite3.connect(str(path))
    try:
        return {
            name: sql
            for name, sql in connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type IN ('table', 'index')"
            )
        }
    finally:
        connection.close()


def test_fresh_database_applies_every_migration_once():
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "fresh.db"
        assert migrations.apply_migrations(path) == [1, 2, 3, 4, 5]
        assert migrations.apply_migrations(path) == []
        schema = _schema(path)
        for table in (
            "patients",
            "finding_reviews",
            "result_heatmaps",
            "analysis_batches",
            "model_approvals",
            "app_settings",
            "user_prefs",
        ):
            assert table in schema
        connection = sqlite3.connect(str(path))
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(cases)")}
            report_columns = {
                row[1]: row for row in connection.execute("PRAGMA table_info(reports)")
            }
            job_columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        finally:
            connection.close()
        assert "patient_id" in columns
        assert {"audience", "kind", "sha256"} <= set(report_columns)
        assert report_columns["case_id"][3] == 0
        assert "batch_id" in job_columns


def test_legacy_database_is_baselined_without_reexecuting_v1():
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "legacy.db"
        connection = sqlite3.connect(str(path))
        for statement in migrations._statements(
            (get_settings().migrations_dir / "001_init.sql").read_text(encoding="utf-8")
        ):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO users VALUES ('u_legacy', 'a@b.test', 'x', 'Legacy', 'clinician', 1, '2026-01-01T00:00:00Z')"
        )
        connection.commit()
        connection.close()

        assert migrations.apply_migrations(path) == [2, 3, 4, 5]
        connection = sqlite3.connect(str(path))
        try:
            versions = [row[0] for row in connection.execute("SELECT version FROM schema_migrations")]
            kept = connection.execute("SELECT id FROM users").fetchall()
        finally:
            connection.close()
        assert versions == [1, 2, 3, 4, 5]
        assert kept == [("u_legacy",)]


def test_modified_migration_is_refused(tmp_path, monkeypatch):
    directory = tmp_path / "migrations"
    shutil.copytree(get_settings().migrations_dir, directory)
    settings = get_settings().model_copy(update={"migrations_dir": directory})
    monkeypatch.setattr(migrations, "get_settings", lambda: settings)

    path = tmp_path / "checked.db"
    assert migrations.apply_migrations(path) == [1, 2, 3, 4, 5]

    target = directory / "002_patients_identity.sql"
    target.write_text(target.read_text(encoding="utf-8") + "\n-- edited\n", encoding="utf-8")
    with pytest.raises(migrations.MigrationError, match="002_patients_identity.sql"):
        migrations.apply_migrations(path)


def test_pending_migrations_reports_remaining_work(tmp_path, monkeypatch):
    directory = tmp_path / "migrations"
    shutil.copytree(get_settings().migrations_dir, directory)
    settings = get_settings().model_copy(update={"migrations_dir": directory})
    monkeypatch.setattr(migrations, "get_settings", lambda: settings)

    path = tmp_path / "partial.db"
    connection = sqlite3.connect(str(path))
    connection.execute(migrations.SCHEMA_TABLE)
    connection.execute(
        "INSERT INTO schema_migrations (version, applied_at, checksum) VALUES (1, 'x', ?)",
        (migrations.Migration(1, directory / "001_init.sql").checksum,),
    )
    connection.commit()
    connection.close()

    assert [migration.version for migration in migrations.pending_migrations(path)] == [2, 3, 4, 5]
