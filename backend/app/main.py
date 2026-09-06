import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db import create_sqlite_engine, run_migrations
from app.evaluations import list_runs, run_recorded_evaluation, seed_evaluation_cases
from app.models import DocumentRecord, EvaluationCaseRecord, EvaluationResultRecord
from app.schema_mapping import RecordedSemanticMappingProvider
from app.services import (
    ReviewValidationError,
    UploadValidationError,
    apply_review_action,
    confirm_mapping,
    ingest_json,
    serialize_document,
)
from app.settings import Settings, get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


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
    active_settings.recorded_mapping_dir = _absolute_path(active_settings.recorded_mapping_dir)
    active_settings.golden_dataset_path = _absolute_path(active_settings.golden_dataset_path)
    engine = create_sqlite_engine(active_settings.database_url)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    provider = RecordedSemanticMappingProvider(active_settings.recorded_mapping_dir)

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

    @app.post("/api/v1/documents", status_code=201)
    async def upload_document(session: SessionDep, file: UploadFile = File(...)):
        try:
            data = await file.read(active_settings.max_upload_bytes + 1)
            document = ingest_json(
                session,
                filename=file.filename or "upload.json",
                content_type=file.content_type,
                data=data,
                settings=active_settings,
                provider=provider,
            )
            return serialize_document(session, document)
        except UploadValidationError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

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
            return serialize_document(session, document)
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

    @app.post("/api/v1/evaluations/runs", status_code=201)
    def run_evaluation(session: SessionDep):
        run = run_recorded_evaluation(
            session,
            project_root=PROJECT_ROOT,
            golden_dataset_path=active_settings.golden_dataset_path,
            provider=provider,
        )
        return {"id": run.id, "status": run.status, "summary": json.loads(run.summary_json)}

    return app


app = create_app()
