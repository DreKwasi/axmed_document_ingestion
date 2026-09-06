"""Huey consumer module: run with `huey_consumer.py app.workers.tasks.huey`."""

from app.core.settings import get_settings
from app.workers.email_extraction import run_email_extraction_job
from app.workers.learning import queue_for, run_learning_job
from app.workers.ocr import run_ocr_job
from app.workers.pdf_extraction import run_pdf_extraction_job

settings = get_settings()
huey = queue_for(settings)


@huey.task(retries=2, retry_delay=5)
def consume_correction_learning(
    learning_id: str,
    database_url: str | None = None,
    task_database_path: str | None = None,
    resolver_url: str | None = None,
    resolver_token: str | None = None,
) -> None:
    run_learning_job(
        learning_id,
        database_url or settings.database_url,
        task_database_path or str(settings.task_database_path),
        resolver_url if resolver_url is not None else settings.learning_resolver_url,
        resolver_token if resolver_token is not None else settings.learning_resolver_token,
    )


def enqueue_correction_learning(
    learning_id: str,
    *,
    database_url: str,
    task_database_path: str,
    resolver_url: str | None,
    resolver_token: str | None,
) -> None:
    """Publish a committed learning record to the dedicated Huey queue."""

    consume_correction_learning(learning_id, database_url, task_database_path, resolver_url, resolver_token)


@huey.task(retries=2, retry_delay=5)
def consume_email_extraction(
    extraction_id: str,
    database_url: str | None = None,
    task_database_path: str | None = None,
    resolver_url: str | None = None,
    resolver_token: str | None = None,
    resolver_model: str | None = None,
) -> None:
    run_email_extraction_job(
        extraction_id,
        database_url or settings.database_url,
        task_database_path or str(settings.task_database_path),
        resolver_url if resolver_url is not None else settings.semantic_resolver_url,
        resolver_token if resolver_token is not None else settings.semantic_resolver_token,
        resolver_model if resolver_model is not None else settings.semantic_resolver_model,
    )


def enqueue_email_extraction(
    extraction_id: str,
    *,
    database_url: str,
    task_database_path: str,
    resolver_url: str | None,
    resolver_token: str | None,
    resolver_model: str | None,
) -> None:
    """Publish a committed email extraction record to the dedicated Huey queue."""

    consume_email_extraction(
        extraction_id,
        database_url,
        task_database_path,
        resolver_url,
        resolver_token,
        resolver_model,
    )


@huey.task(retries=2, retry_delay=5)
def consume_pdf_extraction(
    extraction_id: str,
    database_url: str | None = None,
    task_database_path: str | None = None,
    resolver_url: str | None = None,
    resolver_token: str | None = None,
    resolver_model: str | None = None,
) -> None:
    run_pdf_extraction_job(
        extraction_id,
        database_url or settings.database_url,
        task_database_path or str(settings.task_database_path),
        resolver_url if resolver_url is not None else settings.semantic_resolver_url,
        resolver_token if resolver_token is not None else settings.semantic_resolver_token,
        resolver_model if resolver_model is not None else settings.semantic_resolver_model,
    )


def enqueue_pdf_extraction(
    extraction_id: str,
    *,
    database_url: str,
    task_database_path: str,
    resolver_url: str | None,
    resolver_token: str | None,
    resolver_model: str | None,
) -> None:
    """Publish a committed PDF extraction record to the dedicated Huey queue."""

    consume_pdf_extraction(
        extraction_id,
        database_url,
        task_database_path,
        resolver_url,
        resolver_token,
        resolver_model,
    )


@huey.task(retries=2, retry_delay=5)
def consume_ocr_job(
    job_id: str,
    database_url: str | None = None,
    task_database_path: str | None = None,
    service_url: str | None = None,
    service_token: str | None = None,
) -> None:
    run_ocr_job(
        job_id,
        database_url or settings.database_url,
        task_database_path or str(settings.task_database_path),
        service_url if service_url is not None else settings.ocr_service_url,
        service_token if service_token is not None else settings.ocr_service_token,
    )


def enqueue_ocr_job(
    job_id: str,
    *,
    database_url: str,
    task_database_path: str,
    service_url: str | None,
    service_token: str | None,
) -> None:
    consume_ocr_job(job_id, database_url, task_database_path, service_url, service_token)
