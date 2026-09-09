import json
import logging

from app.events import serialize_event
from app.logging import get_api_logger
from app.models import ProcessingEventRecord


def test_event_stream_rejects_an_invalid_reconnect_cursor(client, sanova_bytes):
    document = client.post(
        "/api/v1/documents",
        files={"files": ("sanova.json", sanova_bytes, "application/json")},
    ).json()[0]

    response = client.get(
        f"/api/v1/documents/{document['id']}/events/stream",
        headers={"Last-Event-ID": "not-an-event"},
    )

    assert response.status_code == 422
    assert "Last-Event-ID" in response.json()["detail"]


def test_awaiting_configuration_event_is_serialized_as_waiting():
    event = ProcessingEventRecord(
        id=1,
        document_id="document-1",
        stage="pdf_extraction_awaiting_model_configuration",
        metadata_json=json.dumps({}),
    )

    assert serialize_event(event)["phase"] == "Waiting"


def test_application_logger_enables_lifecycle_records_from_child_modules():
    get_api_logger()

    application_logger = logging.getLogger("app")
    event_logger = logging.getLogger("app.events")

    assert application_logger.propagate is False
    assert application_logger.isEnabledFor(logging.INFO)
    assert event_logger.isEnabledFor(logging.INFO)
    assert [handler.get_name() for handler in application_logger.handlers].count("axmed-lifecycle") == 1


def test_lifespan_rebinds_child_logger_after_migrations(client):
    del client

    application_logger = logging.getLogger("app")
    event_logger = logging.getLogger("app.events")

    assert application_logger.disabled is False
    assert event_logger.disabled is False
    assert event_logger.isEnabledFor(logging.INFO)
