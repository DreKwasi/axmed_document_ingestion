import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.application.documents import (
    ReviewValidationError,
    UploadValidationError,
    apply_review_action,
    confirm_mapping,
    create_batch,
    ingest_email,
    ingest_failed_document,
    ingest_image,
    ingest_json,
    ingest_pdf,
    serialize_batch,
    serialize_document,
)
from app.application.evaluations import (
    list_runs,
    run_live_pdf_evaluation,
    run_recorded_evaluation,
    seed_evaluation_cases,
)
from app.application.processing_events import list_events_after, record_event, serialize_event
from app.core.settings import Settings, get_settings
from app.domain.schema_mapping import (
    ChainedSemanticMappingProvider,
    LangChainSemanticMappingProvider,
    RecordedSemanticMappingProvider,
    SemanticMappingProvider,
)
from app.infrastructure.database import create_sqlite_engine, run_migrations
from app.infrastructure.models import (
    BatchRecord,
    DocumentRecord,
    EvaluationCaseRecord,
    EvaluationResultRecord,
    ModelInvocationRecord,
    ProcessingEventRecord,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ReviewPatch(BaseModel):
    path: str
    value: object | None = None


class ReviewCommand(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)
    expected_revision: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2_000)
    patches: list[ReviewPatch] = Field(default_factory=list)


def _absolute_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    active_settings.upload_dir = _absolute_path(active_settings.upload_dir)
    active_settings.task_database_path = _absolute_path(active_settings.task_database_path)
    active_settings.recorded_mapping_dir = _absolute_path(active_settings.recorded_mapping_dir)
    active_settings.golden_dataset_path = _absolute_path(active_settings.golden_dataset_path)
    engine = create_sqlite_engine(active_settings.database_url)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    mapping_providers: list[SemanticMappingProvider] = []
    if active_settings.resolved_gemini_api_key:
        mapping_providers.append(
            LangChainSemanticMappingProvider(
                api_key=active_settings.resolved_gemini_api_key,
                model=active_settings.resolved_gemini_model,
            )
        )
    mapping_providers.append(RecordedSemanticMappingProvider(active_settings.recorded_mapping_dir))
    provider = ChainedSemanticMappingProvider(mapping_providers) if len(mapping_providers) > 1 else mapping_providers[0]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        active_settings.upload_dir.mkdir(parents=True, exist_ok=True)
        run_migrations(active_settings.database_url, PROJECT_ROOT)
        with session_factory() as session:
            seed_evaluation_cases(session, active_settings.golden_dataset_path)
        yield

    app = FastAPI(title=active_settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    def get_request_session():
        with session_factory() as session:
            yield session

    SessionDep = Annotated[Session, Depends(get_request_session)]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "axmed-document-intelligence"}

    async def _process_upload_file(
        session: Session,
        file: UploadFile,
        batch_id: str | None = None,
        isolate_failures: bool = False,
    ) -> dict[str, Any]:
        data = b""
        try:
            data = await file.read(active_settings.max_upload_bytes + 1)
            filename = file.filename or "upload.json"
            lower = filename.lower()
            if lower.endswith(".eml"):
                document = ingest_email(
                    session,
                    filename=filename,
                    content_type=file.content_type,
                    data=data,
                    settings=active_settings,
                    batch_id=batch_id,
                )
            elif lower.endswith(".pdf"):
                document = ingest_pdf(
                    session,
                    filename=filename,
                    content_type=file.content_type,
                    data=data,
                    settings=active_settings,
                    batch_id=batch_id,
                )
            elif lower.endswith((".png", ".jpg", ".jpeg")):
                document = ingest_image(
                    session,
                    filename=filename,
                    content_type=file.content_type,
                    data=data,
                    settings=active_settings,
                    batch_id=batch_id,
                )
            elif lower.endswith(".json"):
                document = ingest_json(
                    session,
                    filename=filename,
                    content_type=file.content_type,
                    data=data,
                    settings=active_settings,
                    provider=provider,
                    batch_id=batch_id,
                )
            else:
                raise UploadValidationError(f"Unsupported file format: {filename}")

            response = serialize_document(session, document)
            if (
                document.source_system == "email"
                and active_settings.background_job_dispatch_enabled
                and response.get("email_extraction")
            ):
                try:
                    from app.workers.tasks import enqueue_email_extraction

                    enqueue_email_extraction(
                        response["email_extraction"]["id"],
                        database_url=active_settings.database_url,
                        task_database_path=str(active_settings.task_database_path),
                        resolver_url=active_settings.semantic_resolver_url,
                        resolver_token=active_settings.semantic_resolver_token,
                        resolver_model=active_settings.semantic_resolver_model,
                    )
                except Exception:
                    with session_factory() as event_session:
                        record_event(
                            event_session,
                            document_id=document.id,
                            stage="email_extraction_dispatch_failed",
                            metadata={"reason": "queue_unavailable"},
                        )
                        event_session.commit()
            if (
                document.source_system == "pdf"
                and active_settings.background_job_dispatch_enabled
                and response.get("pdf_extraction")
            ):
                try:
                    from app.workers.tasks import enqueue_pdf_extraction

                    enqueue_pdf_extraction(
                        response["pdf_extraction"]["id"],
                        database_url=active_settings.database_url,
                        task_database_path=str(active_settings.task_database_path),
                        resolver_url=active_settings.semantic_resolver_url,
                        resolver_token=active_settings.semantic_resolver_token,
                        resolver_model=active_settings.semantic_resolver_model,
                    )
                except Exception:
                    with session_factory() as event_session:
                        record_event(
                            event_session,
                            document_id=document.id,
                            stage="pdf_extraction_dispatch_failed",
                            metadata={"reason": "queue_unavailable"},
                        )
                        event_session.commit()
            if (
                document.status == "needs_ocr"
                and active_settings.background_job_dispatch_enabled
                and response.get("ocr")
            ):
                try:
                    from app.workers.tasks import enqueue_ocr_job

                    enqueue_ocr_job(
                        response["ocr"]["id"],
                        database_url=active_settings.database_url,
                        task_database_path=str(active_settings.task_database_path),
                        service_url=active_settings.ocr_service_url,
                        service_token=active_settings.ocr_service_token,
                    )
                except Exception:
                    with session_factory() as event_session:
                        record_event(
                            event_session,
                            document_id=document.id,
                            stage="ocr_dispatch_failed",
                            metadata={"reason": "queue_unavailable"},
                        )
                        event_session.commit()
            return response
        except UploadValidationError as error:
            if isolate_failures:
                failed_doc = ingest_failed_document(
                    session,
                    filename=file.filename or "upload",
                    data=data,
                    content_type=file.content_type,
                    error_message=str(error),
                    settings=active_settings,
                    batch_id=batch_id,
                )
                return serialize_document(session, failed_doc)
            raise HTTPException(status_code=422, detail=str(error)) from error
        except Exception as error:
            if isolate_failures:
                failed_doc = ingest_failed_document(
                    session,
                    filename=file.filename or "upload",
                    data=data,
                    content_type=file.content_type,
                    error_message=f"Processing failed: {error}",
                    settings=active_settings,
                    batch_id=batch_id,
                )
                return serialize_document(session, failed_doc)
            raise

    @app.post("/api/v1/documents", status_code=201)
    async def upload_document(
        session: SessionDep,
        file: UploadFile = File(...),  # noqa: B008
        batch_id: str | None = None,
    ):
        return await _process_upload_file(session, file, batch_id=batch_id, isolate_failures=False)

    @app.get("/api/v1/documents")
    def list_documents(session: SessionDep):
        documents = session.scalars(select(DocumentRecord).order_by(DocumentRecord.created_at.desc())).all()
        return [serialize_document(session, document) for document in documents]

    @app.post("/api/v1/batches", status_code=201)
    async def upload_batch(
        session: SessionDep,
        files: list[UploadFile] = File(...),  # noqa: B008
        name: str | None = None,
    ):
        if not files:
            raise HTTPException(status_code=400, detail="At least one file is required.")
        batch = create_batch(session, name=name)
        for file in files:
            await _process_upload_file(
                session=session,
                file=file,
                batch_id=batch.id,
                isolate_failures=True,
            )
        return serialize_batch(session, batch)

    @app.get("/api/v1/batches")
    def list_all_batches(session: SessionDep):
        batches = session.scalars(select(BatchRecord).order_by(BatchRecord.created_at.desc())).all()
        return [serialize_batch(session, b) for b in batches]

    @app.get("/api/v1/batches/{batch_id}")
    def get_single_batch(batch_id: str, session: SessionDep):
        batch = session.get(BatchRecord, batch_id)
        if batch is None:
            raise HTTPException(status_code=404, detail="Batch not found.")
        return serialize_batch(session, batch)

    @app.get("/api/v1/documents/{document_id}")
    def get_document(document_id: str, session: SessionDep):
        document = session.get(DocumentRecord, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        return serialize_document(session, document)

    @app.get("/api/v1/documents/{document_id}/source")
    def get_document_source(document_id: str, session: SessionDep):
        document = session.get(DocumentRecord, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        source_path = active_settings.upload_dir / document.stored_filename
        if not source_path.is_file():
            raise HTTPException(status_code=404, detail="Stored source document not found.")
        return FileResponse(source_path, media_type=document.media_type, filename=document.original_filename)

    @app.get("/api/v1/documents/{document_id}/events")
    def get_document_events(document_id: str, session: SessionDep, after_id: int = 0):
        if session.get(DocumentRecord, document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        if after_id < 0:
            raise HTTPException(status_code=422, detail="after_id must be zero or greater.")
        return [serialize_event(event) for event in list_events_after(session, document_id, after_id)]

    @app.get("/api/v1/documents/{document_id}/events/stream")
    async def stream_document_events(
        document_id: str,
        request: Request,
        session: SessionDep,
        after_id: int = 0,
    ):
        if session.get(DocumentRecord, document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        last_event_id = request.headers.get("Last-Event-ID")
        if last_event_id and after_id == 0:
            try:
                after_id = int(last_event_id)
            except ValueError as error:
                raise HTTPException(status_code=422, detail="Last-Event-ID must be an integer.") from error
        if after_id < 0:
            raise HTTPException(status_code=422, detail="after_id must be zero or greater.")

        async def event_stream():
            cursor = after_id
            while True:
                with session_factory() as event_session:
                    events = list(list_events_after(event_session, document_id, cursor))
                    for event in events:
                        cursor = event.id
                        yield f"id: {event.id}\nevent: processing\ndata: {json.dumps(serialize_event(event))}\n\n"
                if not events:
                    yield ": keepalive\n\n"
                await asyncio.sleep(active_settings.event_poll_interval_ms / 1000)

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/v1/documents/{document_id}/mapping/confirm")
    def confirm_document_mapping(document_id: str, session: SessionDep):
        try:
            document = confirm_mapping(session, document_id, active_settings)
            return serialize_document(session, document)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/v1/documents/{document_id}/reviews/{action}")
    def review_document(document_id: str, action: str, command: ReviewCommand, session: SessionDep):
        if action not in {"correct", "approve", "reject"}:
            raise HTTPException(status_code=404, detail="Unknown review action.")
        if action == "correct" and not command.patches:
            raise HTTPException(status_code=422, detail="A correction requires at least one patch.")
        try:
            document = apply_review_action(
                session, document_id, f"{action}ed" if action != "approve" else "approved", command.model_dump()
            )
            response = serialize_document(session, document)
            if action == "correct" and active_settings.background_job_dispatch_enabled and response["learning"]:
                learning_id = response["learning"][0]["id"]
                try:
                    # Import only when dispatch is enabled: test apps must not create or touch a shared queue.
                    from app.workers.tasks import enqueue_correction_learning

                    enqueue_correction_learning(
                        learning_id,
                        database_url=active_settings.database_url,
                        task_database_path=str(active_settings.task_database_path),
                        resolver_url=active_settings.learning_resolver_url,
                        resolver_token=active_settings.learning_resolver_token,
                    )
                except Exception:
                    # The decision is already durable. Keep the failed dispatch visible without leaking internals.
                    with session_factory() as event_session:
                        record_event(
                            event_session,
                            document_id=document_id,
                            learning_id=learning_id,
                            stage="learning_dispatch_failed",
                            metadata={"reason": "queue_unavailable"},
                        )
                        event_session.commit()
            return response
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ReviewValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.get("/api/v1/evaluations")
    def get_evaluations(session: SessionDep):
        cases = list(session.scalars(select(EvaluationCaseRecord).where(EvaluationCaseRecord.active.is_(True))))
        runs = list_runs(session)
        return {
            "cases": [{"id": case.id, "title": case.title, "rubric": json.loads(case.rubric_json)} for case in cases],
            "runs": [
                {
                    "id": run.id,
                    "status": run.status,
                    "created_at": run.created_at,
                    "execution_mode": run.execution_mode,
                    "summary": json.loads(run.summary_json),
                    "results": [
                        {
                            "case_id": result.case_id,
                            "status": result.status,
                            "scores": json.loads(result.scores_json),
                            "errors": json.loads(result.error_analysis_json),
                        }
                        for result in session.scalars(
                            select(EvaluationResultRecord).where(EvaluationResultRecord.run_id == run.id)
                        )
                    ],
                }
                for run in runs
            ],
        }

    @app.get("/api/v1/diagnostics")
    def get_diagnostics(session: SessionDep):
        """Return local operational facts only; document content never belongs here."""

        stage_counts = {
            stage: count
            for stage, count in session.execute(
                select(ProcessingEventRecord.stage, func.count()).group_by(ProcessingEventRecord.stage)
            )
        }
        invocations = list(
            session.scalars(select(ModelInvocationRecord).order_by(ModelInvocationRecord.created_at.desc()).limit(50))
        )
        return {
            "stage_counts": stage_counts,
            "invocations": [
                {
                    "operation": invocation.operation,
                    "provider": invocation.provider,
                    "model": invocation.model,
                    "status": invocation.status,
                    "duration_ms": invocation.duration_ms,
                    "input_tokens": invocation.input_tokens,
                    "output_tokens": invocation.output_tokens,
                    "estimated_cost_usd": invocation.estimated_cost_usd,
                    "metadata": json.loads(invocation.safe_metadata_json),
                    "created_at": invocation.created_at,
                }
                for invocation in invocations
            ],
        }

    @app.post("/api/v1/evaluations/runs", status_code=201)
    def run_evaluation(session: SessionDep):
        if active_settings.resolved_gemini_api_key:
            run = run_live_pdf_evaluation(
                session,
                project_root=PROJECT_ROOT,
                golden_dataset_path=active_settings.golden_dataset_path,
                settings=active_settings,
            )
        else:
            run = run_recorded_evaluation(
                session,
                project_root=PROJECT_ROOT,
                golden_dataset_path=active_settings.golden_dataset_path,
                provider=provider,
            )
        return {"id": run.id, "status": run.status, "summary": json.loads(run.summary_json)}

    return app


app = create_app()
