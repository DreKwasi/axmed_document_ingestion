"""Durable correction-learning worker entry point."""

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from huey import SqliteHuey
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.application.processing_events import record_event
from app.core.settings import Settings
from app.infrastructure.database import create_sqlite_engine
from app.infrastructure.models import ModelInvocationRecord, ReviewLearningRecord, SchemaMappingRecord
from app.security.redaction import redact_for_model


def queue_for(settings: Settings) -> SqliteHuey:
    settings.task_database_path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteHuey("axmed-learning", filename=str(settings.task_database_path))


def _resolver_provider(url: str) -> str:
    return urlparse(url).netloc or "configured-resolver"


def _validate_preferences(response: object) -> list[dict[str, str]]:
    if not isinstance(response, dict) or not isinstance(response.get("preferences"), list):
        raise ValueError("Resolver response must contain a preferences list.")
    preferences: list[dict[str, str]] = []
    for preference in response["preferences"]:
        if not isinstance(preference, dict):
            raise ValueError("Resolver preference must be an object.")
        canonical_path = preference.get("canonical_path")
        source_path = preference.get("source_path")
        rationale = preference.get("rationale")
        if not isinstance(canonical_path, str) or not canonical_path:
            raise ValueError("Resolver preference is missing canonical_path.")
        if not isinstance(source_path, str) or not source_path:
            raise ValueError("Resolver preference is missing source_path.")
        if rationale is not None and not isinstance(rationale, str):
            raise ValueError("Resolver preference rationale must be text.")
        saved = {"canonical_path": canonical_path, "source_path": source_path}
        if rationale:
            saved["rationale"] = rationale
        preferences.append(saved)
    return preferences


def _invoke_resolver(url: str, safe_context: dict[str, Any], token: str | None) -> list[dict[str, str]]:
    payload = json.dumps(
        {
            "operation": "correction_interpretation",
            "prompt_version": "correction-learning-v1",
            "context": safe_context,
        }
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, data=payload, headers=headers, method="POST")
    with urlopen(request, timeout=20) as response:  # noqa: S310 - operator-configured resolver URL.
        body = response.read().decode("utf-8")
    return _validate_preferences(json.loads(body))


def _upsert_invocation(
    session: Session,
    learning: ReviewLearningRecord,
    *,
    provider: str,
    model: str | None,
    status: str,
    duration_ms: int | None,
    metadata: dict[str, Any],
) -> ModelInvocationRecord:
    invocation = session.scalar(select(ModelInvocationRecord).where(ModelInvocationRecord.learning_id == learning.id))
    if invocation is None:
        invocation = ModelInvocationRecord(
            learning_id=learning.id,
            operation="correction_interpretation",
            provider=provider,
            model=model,
            prompt_version="correction-learning-v1",
            status=status,
            duration_ms=duration_ms,
            safe_metadata_json=json.dumps(metadata, sort_keys=True),
        )
        session.add(invocation)
    else:
        invocation.provider = provider
        invocation.model = model
        invocation.status = status
        invocation.duration_ms = duration_ms
        invocation.safe_metadata_json = json.dumps(metadata, sort_keys=True)
    return invocation


def consume_learning(session: Session, learning_id: str, settings: Settings) -> None:
    learning = session.get(ReviewLearningRecord, learning_id)
    if learning is None or learning.status in {"completed", "awaiting_model_configuration"}:
        return
    started = time.perf_counter()
    safe_context = redact_for_model(json.loads(learning.context_json))
    learning.status = "running"
    record_event(session, document_id=learning.document_id, learning_id=learning.id, stage="learning_started")
    if not settings.learning_resolver_url:
        learning.status = "awaiting_model_configuration"
        learning.result_json = json.dumps({"corrected_fields": safe_context.get("corrected_fields", [])})
        _upsert_invocation(
            session,
            learning,
            provider="unconfigured",
            model=settings.learning_resolver_model,
            status="awaiting_configuration",
            duration_ms=int((time.perf_counter() - started) * 1000),
            metadata={"corrected_field_count": len(safe_context.get("corrected_fields", []))},
        )
        record_event(
            session,
            document_id=learning.document_id,
            learning_id=learning.id,
            stage="learning_awaiting_model_configuration",
        )
        session.commit()
        return
    _upsert_invocation(
        session,
        learning,
        provider=_resolver_provider(settings.learning_resolver_url),
        model=settings.learning_resolver_model,
        status="running",
        duration_ms=None,
        metadata={"corrected_field_count": len(safe_context.get("corrected_fields", []))},
    )
    session.commit()
    try:
        preferences = _invoke_resolver(settings.learning_resolver_url, safe_context, settings.learning_resolver_token)
    except (HTTPError, URLError, TimeoutError, ValueError, json.JSONDecodeError):
        # Huey retries this task at most twice. Leaving a durable failed state makes the
        # final exhausted attempt visible, while the next retry explicitly moves it to running.
        learning.status = "failed"
        learning.error_message = "resolver_request_failed"
        _upsert_invocation(
            session,
            learning,
            provider=_resolver_provider(settings.learning_resolver_url),
            model=settings.learning_resolver_model,
            status="failed",
            duration_ms=int((time.perf_counter() - started) * 1000),
            metadata={"corrected_field_count": len(safe_context.get("corrected_fields", []))},
        )
        record_event(session, document_id=learning.document_id, learning_id=learning.id, stage="learning_failed")
        session.commit()
        raise
    learning.status = "completed"
    learning.error_message = None
    learning.result_json = json.dumps({"preferences": preferences}, sort_keys=True)
    _upsert_invocation(
        session,
        learning,
        provider=_resolver_provider(settings.learning_resolver_url),
        model=settings.learning_resolver_model,
        status="completed",
        duration_ms=int((time.perf_counter() - started) * 1000),
        metadata={"preference_count": len(preferences)},
    )
    # Never mutate a trusted mapping in place. The next matching document receives this
    # as resolver context and needs confirmation before a revised proposal becomes trusted.
    mapping = session.scalar(
        select(SchemaMappingRecord).where(
            SchemaMappingRecord.source_system == learning.source_system,
            SchemaMappingRecord.schema_fingerprint == learning.schema_fingerprint,
        )
    )
    if mapping is not None and mapping.trust_state == "trusted":
        mapping.trust_state = "proposed"
    record_event(
        session,
        document_id=learning.document_id,
        learning_id=learning.id,
        stage="learning_completed",
        metadata={"preference_count": len(preferences)},
    )
    session.commit()


def run_learning_job(
    learning_id: str,
    database_url: str,
    task_database_path: str,
    resolver_url: str | None = None,
    resolver_token: str | None = None,
) -> None:
    settings = Settings(
        database_url=database_url,
        task_database_path=Path(task_database_path),
        learning_resolver_url=resolver_url,
        learning_resolver_token=resolver_token,
    )
    engine = create_sqlite_engine(settings.database_url)
    with sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)() as session:
        consume_learning(session, learning_id, settings)
