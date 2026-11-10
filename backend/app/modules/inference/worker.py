from __future__ import annotations

import asyncio
import json
import traceback
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import select

from app.core.audit import append_audit
from app.core.config import get_settings
from app.core import db
from app.core.errors import AppError
from app.core.ids import utcnow_iso
from app.core.schema import Case, Image, Job
from app.core.storage import read_blob
from app.modules.inference.engine import get_engine
from app.modules.preprocessing.service import load_pixels, to_model_input
from app.modules.results.schemas import (
    ConfidenceSource,
    Finding,
    ModelRef,
    ResultDocument,
)
from app.modules.results.service import create_result
from app.modules.routing.service import capability_for


def _progress(session, job: Job, value: float) -> None:
    job.progress = value
    job.updated_at = utcnow_iso()
    session.commit()


def _fail(session, job: Job, code: str, detail: str) -> None:
    job.state = "failed"
    job.error_code = code
    job.error_detail = detail[:1000]
    job.updated_at = utcnow_iso()
    append_audit(
        session,
        actor_id=job.requested_by,
        action="job.failed",
        resource_type="job",
        resource_id=job.id,
        detail={"code": code},
    )
    session.commit()


def run_job(job_id: str) -> None:
    if db.SessionLocal is None:
        return
    session = db.SessionLocal()
    try:
        job = session.get(Job, job_id)
        if job is None or job.state not in {"queued", "validated", "created"}:
            return

        job.state = "running"
        job.attempts += 1
        job.progress = 0.05
        job.updated_at = utcnow_iso()
        append_audit(
            session,
            actor_id=job.requested_by,
            action="job.started",
            resource_type="job",
            resource_id=job.id,
            detail={"attempt": job.attempts},
        )
        session.commit()

        image = session.get(Image, job.image_id) if job.image_id else None
        case = session.get(Case, job.case_id)
        if image is None or case is None:
            raise AppError(422, "job_input_missing", "Job input image or case no longer exists")

        if image.modality != "xray":
            raise AppError(
                409,
                "analysis_not_supported",
                "Analysis is not available for this modality",
                "Mammogram AI analysis is out of scope for this MVP cycle; four-view viewing is supported.",
            )
        capability = capability_for(image.body_part or "unrecognised")
        if not capability["supported"]:
            raise AppError(
                409,
                "analysis_not_supported",
                "Analysis is not available for this body region",
                f"Region: {image.body_part}. Supported in this cycle: chest X-ray.",
            )

        data = read_blob(image.blob_digest)
        array, meta = load_pixels(image.mime, data)
        _progress(session, job, 0.25)

        model_input, input_stats = to_model_input(array, photometric=meta.get("photometric", ""))
        _progress(session, job, 0.4)

        engine = get_engine(job.model_id or "chest_densenet121")
        prediction = engine.predict(model_input)
        _progress(session, job, 0.7)

        cam = engine.gradcam(model_input, target_index=prediction.extra.get("top_index"))
        _progress(session, job, 0.85)

        validation = json.loads(image.validation_json or "{}")
        modality_block = validation.get("modality") or {"value": image.modality, "method": "stored", "confidence": 0.5}
        region_block = validation.get("region_or_view") or {
            "value": image.body_part,
            "method": "stored",
            "confidence": 0.5,
        }

        warnings = [
            "Decision support only. This output is not a diagnosis.",
            "The heatmap shows where the model looked, not proof of a finding.",
            f"Model: {engine.model_id} {engine.version}.",
        ]
        if engine.demo:
            warnings.append("Demo model: this output carries no clinical meaning.")
        warnings.extend(validation.get("warnings", []))

        document = ResultDocument(
            case_id=job.case_id,
            image_id=image.id,
            modality=ConfidenceSource(**modality_block),
            region_or_view=ConfidenceSource(**region_block),
            model=ModelRef(
                name=engine.model_id,
                version=engine.version,
                digest=engine.digest,
                demo=engine.demo,
            ),
            classification={"label": prediction.label, "probability": prediction.probability},
            findings=[Finding(**finding) for finding in prediction.findings],
            detections=[],
            segmentation=None,
            heatmap=None,
            birads=None,
            density=None,
            warnings=warnings,
            provenance_id="pending",
            degraded=False,
            created_at=utcnow_iso(),
        )

        create_result(session, job=job, image=image, document=document, cam=cam)

        job.state = "completed"
        job.progress = 1.0
        job.error_code = None
        job.error_detail = None
        job.updated_at = utcnow_iso()
        append_audit(
            session,
            actor_id=job.requested_by,
            action="job.completed",
            resource_type="job",
            resource_id=job.id,
            detail={"model": document.model.model_dump(), "input_stats": input_stats},
        )
        session.commit()
    except AppError as exc:
        session.rollback()
        job = session.get(Job, job_id)
        if job is not None:
            _fail(session, job, exc.code, exc.detail or exc.title)
    except Exception as exc:  # noqa: BLE001 - surfaced through job.error_detail
        traceback.print_exc()
        session.rollback()
        job = session.get(Job, job_id)
        if job is not None:
            _fail(session, job, "analysis_failed", f"{type(exc).__name__}: {exc}")
    finally:
        session.close()


class JobRunner:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[str] | None = None
        self.executor: ThreadPoolExecutor | None = None
        self.task: asyncio.Task | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.queue = asyncio.Queue()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="miap-worker")
        self.task = self.loop.create_task(self._consume())
        self._recover()

    def _recover(self) -> None:
        if db.SessionLocal is None or self.queue is None:
            return
        requeue: list[str] = []
        with db.SessionLocal() as session:
            jobs = session.execute(select(Job).where(Job.state.in_(("queued", "running")))).scalars().all()
            for job in jobs:
                if job.state == "running":
                    if job.attempts >= 2:
                        job.state = "failed"
                        job.error_code = "interrupted"
                        job.error_detail = "The worker stopped twice while this job was running."
                    else:
                        job.state = "queued"
                        append_audit(
                            session,
                            actor_id=job.requested_by,
                            action="job.requeued",
                            resource_type="job",
                            resource_id=job.id,
                            detail={"attempts": job.attempts},
                        )
                if job.state == "queued":
                    requeue.append(job.id)
            session.commit()
        for job_id in requeue:
            self.queue.put_nowait(job_id)

    async def _consume(self) -> None:
        assert self.queue is not None
        while True:
            job_id = await self.queue.get()
            try:
                assert self.executor is not None and self.loop is not None
                await self.loop.run_in_executor(self.executor, run_job, job_id)
            except Exception:  # noqa: BLE001 - worker must survive one bad job
                traceback.print_exc()
            finally:
                self.queue.task_done()

    def submit(self, job_id: str) -> None:
        if self.queue is None:
            raise RuntimeError("Job runner is not started")
        self.queue.put_nowait(job_id)

    def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=True)


runner = JobRunner()
