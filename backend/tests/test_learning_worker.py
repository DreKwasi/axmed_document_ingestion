import json
from urllib.error import URLError

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.settings import Settings
from app.infrastructure.database import create_sqlite_engine
from app.infrastructure.models import (
    ModelInvocationRecord,
    ProcessingEventRecord,
    ReviewLearningRecord,
    SchemaMappingRecord,
)
from app.workers.learning import consume_learning


def _confirmed_sanova(client, sanova_bytes):
    uploaded = client.post(
        "/api/v1/documents",
        files={"file": ("sanova.json", sanova_bytes, "application/json")},
    ).json()
    return client.post(f"/api/v1/documents/{uploaded['id']}/mapping/confirm").json()


class _ResolverResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def test_worker_redacts_context_persists_preferences_and_requires_remapping(client_settings, sanova_bytes, monkeypatch):
    client, base_settings = client_settings
    document = _confirmed_sanova(client, sanova_bytes)
    corrected = client.post(
        f"/api/v1/documents/{document['id']}/reviews/correct",
        json={
            "request_id": "learning-worker-1",
            "expected_revision": document["quotation"]["revision"],
            "patches": [{"path": "line_items.0.pricing.pack_price", "value": "4.00"}],
        },
    ).json()
    learning_id = corrected["learning"][0]["id"]
    engine = create_sqlite_engine(base_settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        learning = session.get(ReviewLearningRecord, learning_id)
        assert learning is not None
        learning.context_json = json.dumps(
            {"corrected_fields": [{"path": "line_items.0.pricing.pack_price"}], "note": "alex@example.com"}
        )
        session.commit()

    submitted: list[dict] = []

    def fake_urlopen(request, timeout):
        assert timeout == 20
        assert request.get_header("Authorization") == "Bearer test-secret"
        submitted.append(json.loads(request.data.decode()))
        return _ResolverResponse(
            {
                "preferences": [
                    {
                        "canonical_path": "pricing.pack_price",
                        "source_path": "commercials.price_per_pack",
                        "rationale": "Field is per pack.",
                    }
                ]
            }
        )

    monkeypatch.setattr("app.workers.learning.urlopen", fake_urlopen)
    with factory() as session:
        consume_learning(
            session,
            learning_id,
            Settings(
                database_url=base_settings.database_url,
                task_database_path=base_settings.task_database_path,
                learning_resolver_url="https://resolver.example/v1/interpret",
                learning_resolver_token="test-secret",
                learning_resolver_model="test-model",
            ),
        )

    assert submitted[0]["operation"] == "correction_interpretation"
    assert submitted[0]["context"]["note"] == "[redacted-email]"
    assert "alex@example.com" not in json.dumps(submitted)
    with factory() as session:
        learning = session.get(ReviewLearningRecord, learning_id)
        invocation = session.scalar(
            select(ModelInvocationRecord).where(ModelInvocationRecord.learning_id == learning_id)
        )
        mapping = session.scalar(select(SchemaMappingRecord))
        events = list(
            session.scalars(select(ProcessingEventRecord).where(ProcessingEventRecord.learning_id == learning_id))
        )
        assert learning is not None
        assert invocation is not None
        assert learning.status == "completed"
        assert json.loads(learning.result_json or "{}")["preferences"][0]["source_path"] == "commercials.price_per_pack"
        assert invocation.status == "completed"
        assert mapping is not None and mapping.trust_state == "proposed"
        assert [event.stage for event in events] == ["learning_queued", "learning_started", "learning_completed"]
        assert "alex@example.com" not in "".join(event.metadata_json for event in events)


def test_worker_records_a_safe_terminal_failure_for_huey_retry(client_settings, sanova_bytes, monkeypatch):
    client, base_settings = client_settings
    document = _confirmed_sanova(client, sanova_bytes)
    corrected = client.post(
        f"/api/v1/documents/{document['id']}/reviews/correct",
        json={
            "request_id": "learning-worker-failure",
            "expected_revision": document["quotation"]["revision"],
            "patches": [{"path": "line_items.0.pricing.pack_price", "value": "4.00"}],
        },
    ).json()
    learning_id = corrected["learning"][0]["id"]
    engine = create_sqlite_engine(base_settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def unavailable(*_args, **_kwargs):
        raise URLError("down")

    monkeypatch.setattr("app.workers.learning.urlopen", unavailable)

    with factory() as session:
        try:
            consume_learning(
                session,
                learning_id,
                Settings(
                    database_url=base_settings.database_url,
                    task_database_path=base_settings.task_database_path,
                    learning_resolver_url="https://resolver.example/v1/interpret",
                ),
            )
        except URLError:
            pass

    with factory() as session:
        learning = session.get(ReviewLearningRecord, learning_id)
        events = list(
            session.scalars(select(ProcessingEventRecord).where(ProcessingEventRecord.learning_id == learning_id))
        )
        assert learning is not None
        assert learning.status == "failed"
        assert learning.error_message == "resolver_request_failed"
        assert [event.stage for event in events] == ["learning_queued", "learning_started", "learning_failed"]


def test_diagnostics_exposes_only_safe_worker_facts(client_settings, sanova_bytes):
    client, base_settings = client_settings
    document = _confirmed_sanova(client, sanova_bytes)
    corrected = client.post(
        f"/api/v1/documents/{document['id']}/reviews/correct",
        json={
            "request_id": "learning-diagnostics",
            "expected_revision": document["quotation"]["revision"],
            "patches": [{"path": "line_items.0.pricing.pack_price", "value": "4.00"}],
        },
    ).json()
    engine = create_sqlite_engine(base_settings.database_url)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as session:
        consume_learning(
            session,
            corrected["learning"][0]["id"],
            Settings(database_url=base_settings.database_url, task_database_path=base_settings.task_database_path),
        )

    diagnostics = client.get("/api/v1/diagnostics").json()

    assert diagnostics["stage_counts"]["learning_queued"] == 1
    assert diagnostics["stage_counts"]["learning_awaiting_model_configuration"] == 1
    assert diagnostics["invocations"] == [
        {
            "operation": "correction_interpretation",
            "provider": "unconfigured",
            "model": None,
            "status": "awaiting_configuration",
            "duration_ms": diagnostics["invocations"][0]["duration_ms"],
            "metadata": {"corrected_field_count": 1},
            "created_at": diagnostics["invocations"][0]["created_at"],
        }
    ]
