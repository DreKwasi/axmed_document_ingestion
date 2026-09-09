"""Tests verifying SQLite concurrency, busy timeouts, and transaction isolation."""

import concurrent.futures
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.database import create_sqlite_engine
from app.events import record_event
from app.models import DocumentRecord, OcrJobRecord, ProcessingEventRecord


def test_sqlite_engine_pragmas(tmp_path: Path):
    """Engine must apply WAL mode, synchronous=NORMAL, and busy_timeout=60000."""
    db_path = tmp_path / "test_pragmas.db"
    engine = create_sqlite_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        journal_mode = conn.exec_driver_sql("PRAGMA journal_mode;").scalar()
        busy_timeout = conn.exec_driver_sql("PRAGMA busy_timeout;").scalar()
        synchronous = conn.exec_driver_sql("PRAGMA synchronous;").scalar()

        assert str(journal_mode).lower() == "wal"
        assert int(busy_timeout) == 60000
        assert int(synchronous) == 1  # 1 == NORMAL in SQLite


def test_concurrent_multithreaded_events_and_job_updates(tmp_path: Path):
    """Concurrent worker threads writing processing events and updating OCR jobs must not lock."""
    db_path = tmp_path / "test_concurrency.db"
    engine = create_sqlite_engine(f"sqlite:///{db_path}")

    from app.database import Base
    Base.metadata.create_all(bind=engine)

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    # Seed 5 document records and OCR jobs
    doc_ids = []
    job_ids = []
    with Session() as session:
        for i in range(5):
            doc = DocumentRecord(
                original_filename=f"quote_{i}.pdf",
                stored_filename=f"stored_{i}.pdf",
                media_type="application/pdf",
                source_system="supplier_portal",
                status="queued",
            )
            session.add(doc)
            session.flush()
            doc_ids.append(doc.id)

            job = OcrJobRecord(
                document_id=doc.id,
                status="queued",
                selected_pages_json="[1]",
            )
            session.add(job)
            session.flush()
            job_ids.append(job.id)
        session.commit()

    def worker_task(thread_id: int):
        doc_id = doc_ids[thread_id % len(doc_ids)]
        job_id = job_ids[thread_id % len(job_ids)]

        # Simulate multi-stage background extraction updates and events
        for step in range(10):
            with Session() as s:
                job = s.get(OcrJobRecord, job_id)
                if job:
                    job.status = f"running_{step}"
                record_event(
                    s,
                    document_id=doc_id,
                    stage=f"worker_{thread_id}_step_{step}",
                    metadata={"step": step, "thread": thread_id},
                )
                s.commit()

    # Run 8 concurrent workers generating 80 transactions with interleaved writes
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker_task, i) for i in range(8)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    with Session() as session:
        total_events = session.query(ProcessingEventRecord).count()
        assert total_events == 80
