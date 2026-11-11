"""Numbered SQL migrations for the SQLite store.

The runner exists because ``Base.metadata.create_all`` cannot add columns to an
existing database. Files in ``migrations/`` are applied in numeric order inside
one transaction each; the applied version and the file's SHA-256 are recorded in
``schema_migrations``. A changed file that was already applied is refused rather
than silently ignored.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.core.config import get_settings
from app.core.ids import utcnow_iso

SCHEMA_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    checksum TEXT NOT NULL
)
"""


class MigrationError(RuntimeError):
    """Raised when migrations cannot be applied safely."""


@dataclass(frozen=True)
class Migration:
    version: int
    path: Path

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.path.read_bytes()).hexdigest()


def _discover(directory: Path) -> list[Migration]:
    found: list[Migration] = []
    if not directory.is_dir():
        raise MigrationError(f"Migration directory is missing: {directory}")
    for path in sorted(directory.glob("*.sql")):
        prefix = path.stem.split("_", 1)[0]
        if prefix.isdigit():
            found.append(Migration(version=int(prefix), path=path))
    versions = [migration.version for migration in found]
    if len(set(versions)) != len(versions):
        raise MigrationError("Duplicate migration versions found")
    return found


def _statements(sql: str):
    """Yield complete SQLite statements, ignoring full-line ``--`` comments."""
    buffer = ""
    for line in sql.splitlines(keepends=True):
        if not buffer and line.lstrip().startswith("--"):
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            statement = buffer.strip()
            buffer = ""
            if statement:
                yield statement
    if buffer.strip():
        raise MigrationError("Migration file ends with an incomplete statement")


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path), timeout=30, isolation_level=None)
    connection.execute("PRAGMA busy_timeout=30000")
    return connection


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _applied(connection: sqlite3.Connection) -> dict[int, str]:
    return {
        int(version): checksum
        for version, checksum in connection.execute(
            "SELECT version, checksum FROM schema_migrations ORDER BY version"
        )
    }


def _apply_one(connection: sqlite3.Connection, migration: Migration, checksum: str) -> None:
    sql = migration.path.read_text(encoding="utf-8")
    connection.execute("PRAGMA foreign_keys=OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        try:
            for statement in _statements(sql):
                connection.execute(statement)
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise MigrationError(
                    f"Migration {migration.path.name} leaves {len(violations)} foreign-key violations"
                )
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at, checksum) VALUES (?, ?, ?)",
                (migration.version, utcnow_iso(), checksum),
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.execute("PRAGMA foreign_keys=ON")


def pending_migrations(db_path: Path | None = None) -> list[Migration]:
    """List migrations that would run. Read-only: never stamps the database."""
    target = db_path or get_settings().database_path
    directory = get_settings().migrations_dir
    migrations = _discover(directory)
    if not target.exists():
        return migrations
    connection = _connect(target)
    try:
        applied = _applied(connection) if _table_exists(connection, "schema_migrations") else {}
        if not applied and _table_exists(connection, "users"):
            # Existing MVP database: v1 is already represented by its schema.
            applied = {migrations[0].version: migrations[0].checksum}
        return [migration for migration in migrations if migration.version not in applied]
    finally:
        connection.close()


def apply_migrations(db_path: Path | None = None) -> list[int]:
    """Apply pending migrations and return the versions executed this run."""
    target = db_path or get_settings().database_path
    migrations = _discover(get_settings().migrations_dir)
    connection = _connect(target)
    executed: list[int] = []
    try:
        connection.execute(SCHEMA_TABLE)
        applied = _applied(connection)
        legacy = not applied and _table_exists(connection, "users")
        if legacy:
            first = migrations[0]
            connection.execute(
                "INSERT INTO schema_migrations (version, applied_at, checksum) VALUES (?, ?, ?)",
                (first.version, utcnow_iso(), first.checksum),
            )
            applied = {first.version: first.checksum}

        for migration in migrations:
            checksum = migration.checksum
            if migration.version in applied:
                if applied[migration.version] != checksum:
                    raise MigrationError(
                        f"Migration {migration.path.name} was modified after it was applied"
                    )
                continue
            _apply_one(connection, migration, checksum)
            executed.append(migration.version)
    finally:
        connection.close()
    return executed
