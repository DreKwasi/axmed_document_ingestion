import asyncio
import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import BackgroundTasks, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Config, get_config
from app.database import create_sqlite_engine, run_migrations
from app.documents import (
    ReviewValidationError,
    UploadValidationError,
    apply_review_action,
    begin_image_extraction_review,
    delete_document,
    ingest_email,
    ingest_failed_document,
    ingest_image,
    ingest_json,
    ingest_pdf,
    reextract_json_document,
    serialize_document,
)
from app.events import list_events_after, record_event, serialize_event
from app.extraction.email_processing import consume_email_extraction
from app.extraction.image_processing import consume_ocr
from app.extraction.json import (
    ChainedJsonSemanticExtractor,
    JsonSemanticExtractor,
    LangChainJsonSemanticExtractor,
    RecordedJsonSemanticExtractor,
)
from app.extraction.pdf_processing import consume_pdf_extraction
from app.logging import get_api_logger
from app.models import DocumentRecord

logger = get_api_logger()

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReviewPatch(BaseModel):
    path: str
    value: object | None = None


class ReviewCommand(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)
    expected_revision: int = Field(ge=1)
    note: str | None = Field(default=None, max_length=2_000)
    rejection_reason: str | None = Field(default=None, max_length=80)
    patches: list[ReviewPatch] = Field(default_factory=list)


def _absolute_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == "backend":
        path = Path(*path.parts[1:])
    return PROJECT_ROOT / path


def create_app(settings: Config | None = None, json_extractor: JsonSemanticExtractor | None = None) -> FastAPI:
    active_settings = settings or get_config()
    active_settings.upload_dir = _absolute_path(active_settings.upload_dir)
    active_settings.recorded_json_extraction_dir = _absolute_path(active_settings.recorded_json_extraction_dir)
    active_settings.golden_dataset_path = _absolute_path(active_settings.golden_dataset_path)
    engine = create_sqlite_engine(active_settings.database_url)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    extractors: list[JsonSemanticExtractor] = [
        RecordedJsonSemanticExtractor(active_settings.recorded_json_extraction_dir)
    ]
    if active_settings.gemini_api_key:
        extractors.append(
            LangChainJsonSemanticExtractor(
                api_key=active_settings.gemini_api_key,
                model=active_settings.gemini_model,
                request_timeout_seconds=active_settings.gemini_request_timeout_seconds,
            )
        )
    extractor = json_extractor or (
        ChainedJsonSemanticExtractor(extractors) if len(extractors) > 1 else extractors[0]
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Uvicorn installs its logging configuration immediately before startup.
        # Bind here as well so the dedicated lifecycle handler survives that setup.
        global logger
        logger = get_api_logger()
        active_settings.upload_dir.mkdir(parents=True, exist_ok=True)
        run_migrations(active_settings.database_url, PROJECT_ROOT)
        logger.info("Axmed Document Intelligence API started")
        yield

    app = FastAPI(title=active_settings.app_name, version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.cors_origin_list,
        allow_origin_regex=r"^https://.*\.pages\.dev$",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_request_session():
        with session_factory() as session:
            yield session

    SessionDep = Annotated[Session, Depends(get_request_session)]

    def _record_background_failure(document_id: str, stage: str) -> None:
        with session_factory() as event_session:
            record_event(
                event_session,
                document_id=document_id,
                stage=stage,
                metadata={"reason": "background_processing_failed"},
            )
            event_session.commit()

    def _run_email_extraction(extraction_id: str, document_id: str) -> None:
        started_at = time.perf_counter()
        logger.info("[Doc %s] >>> Background task STARTED: Email extraction (%s)", document_id[:8], extraction_id[:8])
        try:
            with session_factory() as background_session:
                consume_email_extraction(background_session, extraction_id, active_settings)
            logger.info(
                "[Doc %s] <<< Background task COMPLETED: Email extraction in %.2fs",
                document_id[:8],
                time.perf_counter() - started_at,
            )
        except Exception as error:
            logger.error(
                "[Doc %s] !!! Background task FAILED: Email extraction (%s), error_type=%s",
                document_id[:8],
                extraction_id[:8],
                type(error).__name__,
            )
            _record_background_failure(document_id, "email_extraction_background_failed")

    def _run_pdf_extraction(extraction_id: str, document_id: str) -> None:
        started_at = time.perf_counter()
        logger.info("[Doc %s] >>> Background task STARTED: PDF extraction (%s)", document_id[:8], extraction_id[:8])
        try:
            with session_factory() as background_session:
                consume_pdf_extraction(background_session, extraction_id, active_settings)
            logger.info(
                "[Doc %s] <<< Background task COMPLETED: PDF extraction in %.2fs",
                document_id[:8],
                time.perf_counter() - started_at,
            )
        except Exception as error:
            logger.error(
                "[Doc %s] !!! Background task FAILED: PDF extraction (%s), error_type=%s",
                document_id[:8],
                extraction_id[:8],
                type(error).__name__,
            )
            _record_background_failure(document_id, "pdf_extraction_background_failed")

    def _run_ocr(job_id: str, document_id: str) -> None:
        started_at = time.perf_counter()
        logger.info("[Doc %s] >>> Background task STARTED: OCR (%s)", document_id[:8], job_id[:8])
        try:
            with session_factory() as background_session:
                consume_ocr(background_session, job_id, active_settings)
            logger.info(
                "[Doc %s] <<< Background task COMPLETED: OCR in %.2fs",
                document_id[:8],
                time.perf_counter() - started_at,
            )
        except Exception as error:
            logger.error(
                "[Doc %s] !!! Background task FAILED: OCR (%s), error_type=%s",
                document_id[:8],
                job_id[:8],
                type(error).__name__,
            )
            _record_background_failure(document_id, "ocr_background_failed")

    def _schedule_document_processing(
        background_tasks: BackgroundTasks,
        document: DocumentRecord,
        response: dict[str, Any],
    ) -> None:
        if not active_settings.background_processing_enabled:
            logger.warning("[Doc %s] Background processing disabled in settings.", document.id[:8])
            return
        if document.source_system == "email" and response.get("email_extraction"):
            ext_id = response["email_extraction"]["id"]
            logger.info("[Doc %s] Scheduling background task: email extraction (%s)", document.id[:8], ext_id[:8])
            background_tasks.add_task(_run_email_extraction, ext_id, document.id)
        elif document.source_system == "pdf" and response.get("pdf_extraction"):
            ext_id = response["pdf_extraction"]["id"]
            logger.info("[Doc %s] Scheduling background task: PDF extraction (%s)", document.id[:8], ext_id[:8])
            background_tasks.add_task(_run_pdf_extraction, ext_id, document.id)
        elif document.status == "needs_ocr" and response.get("ocr"):
            job_id = response["ocr"]["id"]
            logger.info("[Doc %s] Scheduling background task: OCR (%s)", document.id[:8], job_id[:8])
            background_tasks.add_task(_run_ocr, job_id, document.id)
        else:
            logger.info(
                "[Doc %s] Synchronous processing finished (status=%s, source=%s)",
                document.id[:8],
                document.status,
                document.source_system,
            )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "axmed-document-intelligence"}

    async def _process_upload_file(
        session: Session,
        file: UploadFile,
        background_tasks: BackgroundTasks,
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
                )
            elif lower.endswith(".pdf"):
                document = ingest_pdf(
                    session,
                    filename=filename,
                    content_type=file.content_type,
                    data=data,
                    settings=active_settings,
                )
            elif lower.endswith((".png", ".jpg", ".jpeg")):
                document = ingest_image(
                    session,
                    filename=filename,
                    content_type=file.content_type,
                    data=data,
                    settings=active_settings,
                )
            elif lower.endswith(".json"):
                document = ingest_json(
                    session,
                    filename=filename,
                    content_type=file.content_type,
                    data=data,
                    settings=active_settings,
                    extractor=extractor,
                )
            else:
                raise UploadValidationError(f"Unsupported file format: {filename}")

            response = serialize_document(session, document)
            _schedule_document_processing(background_tasks, document, response)
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
                )
                return serialize_document(session, failed_doc)
            raise

    @app.post("/api/v1/documents", status_code=201)
    async def upload_documents(
        background_tasks: BackgroundTasks,
        session: SessionDep,
        files: list[UploadFile] = File(...),  # noqa: B008
    ):
        if not files:
            raise HTTPException(status_code=400, detail="At least one file is required.")
        isolate_failures = len(files) > 1
        logger.info("Document upload received: %d file(s)", len(files))
        documents = [
            await _process_upload_file(
                session=session,
                file=file,
                background_tasks=background_tasks,
                isolate_failures=isolate_failures,
            )
            for file in files
        ]
        return documents

    @app.get("/api/v1/documents")
    def list_documents(session: SessionDep):
        documents = session.scalars(select(DocumentRecord).order_by(DocumentRecord.created_at.desc())).all()
        return [serialize_document(session, document) for document in documents]

    @app.get("/api/v1/documents/{document_id}")
    def get_document(document_id: str, session: SessionDep):
        document = session.get(DocumentRecord, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        return serialize_document(session, document)

    @app.delete("/api/v1/documents/{document_id}", status_code=204)
    def delete_uploaded_document(document_id: str, session: SessionDep):
        try:
            delete_document(session, document_id, active_settings)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        return Response(status_code=204)

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

    @app.post("/api/v1/documents/{document_id}/reextract")
    def reextract_document(document_id: str, session: SessionDep):
        try:
            document = reextract_json_document(session, document_id, active_settings, extractor)
            return serialize_document(session, document)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/v1/documents/{document_id}/image-extractions/{approach}/review")
    def open_image_extraction_for_review(document_id: str, approach: str, session: SessionDep):
        try:
            document = begin_image_extraction_review(session, document_id, approach)
            return serialize_document(session, document)
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @app.post("/api/v1/documents/{document_id}/reviews/{action}")
    def review_document(
        document_id: str,
        action: str,
        command: ReviewCommand,
        session: SessionDep,
    ):
        if action not in {"correct", "approve", "reject"}:
            raise HTTPException(status_code=404, detail="Unknown review action.")
        if action == "correct" and not command.patches:
            raise HTTPException(status_code=422, detail="A correction requires at least one patch.")
        if action == "reject" and not command.rejection_reason:
            raise HTTPException(status_code=422, detail="A rejection reason is required.")
        try:
            document = apply_review_action(
                session, document_id, f"{action}ed" if action != "approve" else "approved", command.model_dump()
            )
            response = serialize_document(session, document)
            return response
        except LookupError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
        except ReviewValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    return app


app = create_app()
