from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core import db
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.cases.router import router as cases_router
from app.modules.inference.router import router as analyses_router
from app.modules.inference.worker import runner
from app.modules.ingestion.router import router as ingestion_router
from app.modules.models.router import router as models_router
from app.modules.models.router import seed_models
from app.modules.reporting.router import router as reports_router


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
    api.include_router(cases_router)
    api.include_router(ingestion_router)
    api.include_router(analyses_router)
    api.include_router(models_router)
    api.include_router(audit_router)
    api.include_router(reports_router)
    app.include_router(api)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "service": "miap", "version": "0.1.0"}

    return app


app = create_app()
