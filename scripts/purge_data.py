"""Delete all MIAP runtime data: SQLite database, blob store, derived files, reports.

    python scripts/purge_data.py            # dry run: list what would be removed
    python scripts/purge_data.py --yes      # actually delete

Stop the backend first. The script refuses to run if the data directory resolves
to the repository root or a parent of it. The audit tail hash is printed before
deletion so the final state can be recorded before the chain is destroyed.
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.core.config import get_settings  # noqa: E402


def human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def audit_tail(database: Path) -> str:
    if not database.exists():
        return "no database"
    try:
        connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
        row = connection.execute(
            "select seq, hash from audit_events order by seq desc limit 1"
        ).fetchone()
        count = connection.execute("select count(*) from audit_events").fetchone()[0]
        connection.close()
    except sqlite3.Error as exc:
        return f"could not read audit trail ({exc})"
    if row is None:
        return "audit trail is empty"
    return f"last event seq {row[0]} hash {row[1]} ({count} events)"


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge MIAP runtime data.")
    parser.add_argument("--yes", action="store_true", help="Delete without prompting")
    args = parser.parse_args()

    settings = get_settings()
    data_dir = settings.data_dir.resolve()
    if data_dir == REPO_ROOT or data_dir in REPO_ROOT.parents:
        print(f"Refusing to purge {data_dir}: it is the repository or a parent.", file=sys.stderr)
        return 2
    if not data_dir.exists():
        print(f"Nothing to purge: {data_dir} does not exist.")
        return 0

    print(f"Data directory: {data_dir}")
    print(f"Audit trail:    {audit_tail(settings.database_path)}")

    targets = [path for path in sorted(data_dir.rglob("*")) if path.is_file()]
    total = sum(path.stat().st_size for path in targets)
    print(f"Files:          {len(targets)} ({human(total)})")
    for path in targets[:20]:
        print(f"  {path.relative_to(data_dir)}  {human(path.stat().st_size)}")
    if len(targets) > 20:
        print(f"  ... and {len(targets) - 20} more")

    if not args.yes:
        print("\nDry run. Re-run with --yes to delete the database and every stored artefact.")
        return 0

    failures = []
    for child in sorted(data_dir.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
        except OSError as exc:
            failures.append(f"{child.name}: {exc}")
            continue
        print(f"removed {child.name}")

    if failures:
        print("\nSome files could not be removed (is the backend still running?):", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"\nPurged {human(total)}. Re-create demo data with scripts/seed_users.py and scripts/make_fixtures.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
