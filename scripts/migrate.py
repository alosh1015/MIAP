"""Apply or rehearse the numbered SQL migrations.

Usage:
    python scripts/migrate.py                 # apply to the configured database
    python scripts/migrate.py --status        # show applied and pending versions
    python scripts/migrate.py --dry-run       # copy the database and apply there
    python scripts/migrate.py --db path.db    # operate on another database file
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import get_settings  # noqa: E402
from app.core.migrations import apply_migrations, pending_migrations  # noqa: E402


def _status(db_path: Path) -> None:
    if not db_path.exists():
        print(f"{db_path}: database does not exist; all migrations are pending")
        for migration in pending_migrations(db_path):
            print(f"  pending {migration.version:03d} {migration.path.name}")
        return
    connection = sqlite3.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "schema_migrations" in tables:
            rows = connection.execute(
                "SELECT version, applied_at, checksum FROM schema_migrations ORDER BY version"
            ).fetchall()
        else:
            rows = []
            if "users" in tables:
                print(f"{db_path}: legacy database, will be baselined at version 1")
    finally:
        connection.close()
    for version, applied_at, checksum in rows:
        print(f"  applied {version:03d} {applied_at} {checksum[:12]}")
    for migration in pending_migrations(db_path):
        print(f"  pending {migration.version:03d} {migration.path.name}")


def main() -> int:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Apply MIAP SQL migrations")
    parser.add_argument("--db", type=Path, default=settings.database_path)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target: Path = args.db
    if args.status:
        _status(target)
        return 0

    if args.dry_run:
        if not target.exists():
            print(f"{target} does not exist; nothing to rehearse", file=sys.stderr)
            return 1
        with tempfile.TemporaryDirectory(prefix="miap-migrate-") as temporary:
            copy = Path(temporary) / target.name
            shutil.copy2(target, copy)
            # Include the WAL sidecar so the copy sees committed data.
            for suffix in ("-wal", "-shm"):
                sidecar = target.with_name(target.name + suffix)
                if sidecar.exists():
                    shutil.copy2(sidecar, copy.with_name(copy.name + suffix))
            executed = apply_migrations(copy)
            print(f"dry run on a copy: applied {executed or 'nothing'}")
            connection = sqlite3.connect(str(copy))
            try:
                problems = connection.execute("PRAGMA integrity_check").fetchone()
                print(f"integrity_check: {problems[0]}")
            finally:
                connection.close()
        return 0

    executed = apply_migrations(target)
    print(f"{target}: applied {executed or 'nothing'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
