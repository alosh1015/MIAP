from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.audit import verify_chain
from app.core.config import get_settings
from app.core.ids import utcnow_iso
from app.core.schema import Case, Job, ModelVersion, Result, User
from app.modules.inference.engine import get_engine
from app.modules.inference.worker import runner
from app.modules.models.router import internal_model_ids


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                continue
    return total


def _schema_version(session: Session) -> int:
    try:
        version = session.execute(text("SELECT MAX(version) FROM schema_migrations")).scalar()
    except Exception:  # noqa: BLE001
        version = None
    return int(version or 0)


def health(session: Session) -> dict:
    settings = get_settings()
    now = utcnow_iso()
    queued = session.execute(select(func.count(Job.id)).where(Job.state == "queued")).scalar() or 0
    running = session.execute(select(func.count(Job.id)).where(Job.state == "running")).scalar() or 0
    failed = session.execute(
        select(func.count(Job.id)).where(Job.state == "failed", Job.updated_at >= now[:10])
    ).scalar() or 0
    active_users = session.execute(
        select(func.count(User.id)).where(User.is_active == 1)
    ).scalar() or 0
    total_users = session.execute(select(func.count(User.id))).scalar() or 0
    total_cases = session.execute(select(func.count(Case.id))).scalar() or 0
    archived = session.execute(
        select(func.count(Case.id)).where(Case.status == "archived")
    ).scalar() or 0
    due = session.execute(
        select(func.count(Case.id)).where(
            Case.retention_until.is_not(None), Case.retention_until < now, Case.status != "archived"
        )
    ).scalar() or 0
    total_results = session.execute(select(func.count(Result.id))).scalar() or 0
    models = session.execute(select(ModelVersion).order_by(ModelVersion.model_id)).scalars().all()
    hidden_models = internal_model_ids()
    models = [model for model in models if model.model_id not in hidden_models]
    usage = shutil.disk_usage(settings.data_dir if settings.data_dir.exists() else Path.cwd())
    ok, checked, first_bad = verify_chain(session)
    db_path = settings.database_path
    return {
        "status": "ok" if ok else "degraded",
        "version": "0.1.0",
        "generated_at": now,
        "database": {
            "file": db_path.name,
            "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
            "schema_version": _schema_version(session),
        },
        "storage": {
            "data_size_bytes": _directory_size(settings.data_dir),
            "free_bytes": usage.free,
            "total_bytes": usage.total,
        },
        "queue": {"queued": queued, "running": running, "failed_today": failed},
        "worker": {"running": runner.task is not None and not runner.task.done(), "engine_cache": list(get_engine.cache_info())},
        "users": {"active": active_users, "total": total_users},
        "cases": {"total": total_cases, "archived": archived, "due_for_retention": due},
        "results": {"total": total_results},
        "models": {
            "approved": sum(1 for model in models if model.state == "approved"),
            "candidate": sum(1 for model in models if model.state == "candidate"),
            "versions": [
                {
                    "model_id": model.model_id,
                    "version": model.version,
                    "state": model.state,
                    "state_source": model.state_source,
                    "approved_at": model.approved_at,
                }
                for model in models
            ],
        },
        "audit": {"ok": ok, "checked": checked, "first_bad_seq": first_bad},
    }
