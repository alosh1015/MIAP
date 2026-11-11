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
from app.core.schema import AnalysisBatch, Case, Image, Job
from app.core.storage import read_blob
from app.modules.inference.engine import get_engine
from app.modules.preprocessing.profiles import heatmap_mapping
from app.modules.preprocessing.service import load_pixels, to_model_input
from app.modules.results.presenter import band_for, is_flagged
from app.modules.results.schemas import (
    ConfidenceSource,
    Finding,
    ModelRef,
    ResultDocument,
)
from app.modules.results.service import create_result
from app.modules.routing.service import is_degraded, resolve_model_for_image


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


def _refresh_batch(session, job: Job) -> None:
    """Roll per-job outcomes up to the batch after each terminal state."""
    if not job.batch_id:
        return
    batch = session.get(AnalysisBatch, job.batch_id)
    if batch is None:
        return
    jobs = session.execute(select(Job).where(Job.batch_id == batch.id)).scalars().all()
    batch.completed = sum(1 for item in jobs if item.state == "completed")
    batch.failed = sum(1 for item in jobs if item.state == "failed")
    batch.updated_at = utcnow_iso()
    finished = batch.completed + batch.failed
    if finished >= batch.total and batch.total > 0:
        if batch.failed == 0:
            batch.state = "completed"
        elif batch.completed == 0:
            batch.state = "failed"
        else:
            batch.state = "partial"
    elif finished > 0:
        batch.state = "running"
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

        entry, bucket = resolve_model_for_image(session, image, job.model_id, job.model_version)
        degraded = is_degraded(entry, bucket)

        data = read_blob(image.blob_digest)
        array, meta = load_pixels(image.mime, data)
        _progress(session, job, 0.25)

        profile = entry.get("preprocess_profile") or "xrv_chest_224"
        model_input, input_stats = to_model_input(
            array, photometric=meta.get("photometric", ""), profile=profile
        )
        _progress(session, job, 0.4)

        engine = get_engine(entry["model_id"], entry["version"])
        prediction = engine.predict(model_input)
        _progress(session, job, 0.7)

        top_index = int(prediction.extra.get("top_index") or 0)
        # A normal/reference class has no region to point at, and nothing is
        # highlighted when the leading finding did not reach the review band.
        flagged = is_flagged(
            {
                "label": prediction.label,
                "band": band_for(prediction.probability, 0.5),
            }
        )
        cam = (
            engine.gradcam(model_input, target_index=top_index)
            if flagged and engine.localisable(prediction.label)
            else None
        )
        mapping = heatmap_mapping(profile)
        # top_index addresses the model's class list; stores index into `findings`.
        primary_index = next(
            (
                position
                for position, finding in enumerate(prediction.findings)
                if finding["label"] == prediction.label
            ),
            0,
        )
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
        if bucket == "mammogram_density":
            warnings.append(
                "Breast density is a qualitative BI-RADS-style category, not a cancer screen."
            )
        if bucket == "bone_limb":
            warnings.append(
                "This bone model is zero-shot and has not been validated on local patients."
            )
        if bucket == "bone_hip_pelvis":
            warnings.append(
                "Experimental capability: hip and pelvis radiographs are outside the model's validated scope."
            )
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
            primary_finding_index=primary_index,
            detections=[],
            segmentation=None,
            heatmap=None,
            birads=None,
            density=prediction.extra.get("density"),
            warnings=warnings,
            provenance_id="pending",
            degraded=degraded,
            created_at=utcnow_iso(),
        )

        parameters = {
            "profile": profile,
            "input_size": int(input_stats["size"]),
            "channels": int(input_stats["channels"]),
            "normalisation": profile,
            "threshold": 0.5,
            "gradcam_layer": engine.cam_layer,
            "cam_method": engine.cam_method,
            "capability": bucket,
            "heatmap_mapping": mapping,
        }
        prompts = prediction.extra.get("prompts")
        if prompts:
            parameters["prompts"] = prompts
        create_result(
            session,
            job=job,
            image=image,
            document=document,
            cam=cam,
            primary_index=primary_index,
            parameters=parameters,
            heatmap_mapping=mapping,
        )

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
            detail={
                "model": document.model.model_dump(),
                "capability": bucket,
                "input_stats": input_stats,
            },
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
        try:
            current = session.get(Job, job_id)
            if current is not None:
                _refresh_batch(session, current)
        except Exception:  # noqa: BLE001 - batch rollup must not kill the worker
            session.rollback()
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
