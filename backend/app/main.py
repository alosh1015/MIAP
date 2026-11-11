from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import db
from app.core.config import get_settings
from app.core.crypto import validate_crypto_config
from app.core.errors import install_error_handlers
from app.modules.annotations.router import router as annotations_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.cases.router import router as cases_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.exports.router import router as exports_router
from app.modules.inference.router import router as analyses_router
from app.modules.inference.worker import runner
from app.modules.ingestion.router import router as ingestion_router
from app.modules.models.approvals import router as model_approvals_router
from app.modules.models.router import router as models_router
from app.modules.models.router import seed_models
from app.modules.patients.router import router as patients_router
from app.modules.reporting.router import router as reports_router
from app.modules.retention.router import router as retention_router
from app.modules.reviews.router import router as reviews_router
from app.modules.settings.router import router as settings_router
from app.modules.system.router import router as system_router
from app.modules.users.router import router as users_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    assert db.SessionLocal is not None
    with db.SessionLocal() as session:
        seed_models(session)
    runner.start()
    try:
        yield
    finally:
        runner.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    validate_crypto_config()
    app = FastAPI(
        title="MIAP",
        version="0.1.0",
        description="Decision-support pipeline for chest X-ray and mammogram images. Not a diagnostic device.",
        lifespan=lifespan,
    )
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Location", "X-MIAP-Meta"],
    )

    api = APIRouter(prefix="/api/v1")
    api.include_router(auth_router)
    api.include_router(dashboard_router)
    api.include_router(cases_router)
    api.include_router(annotations_router)
    api.include_router(patients_router)
    api.include_router(ingestion_router)
    api.include_router(analyses_router)
    api.include_router(reviews_router)
    api.include_router(model_approvals_router)
    api.include_router(models_router)
    api.include_router(audit_router)
    api.include_router(reports_router)
    api.include_router(settings_router)
    api.include_router(users_router)
    api.include_router(system_router)
    api.include_router(retention_router)
    api.include_router(exports_router)
    app.include_router(api)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "service": "miap", "version": "0.1.0"}

    return app


app = create_app()
