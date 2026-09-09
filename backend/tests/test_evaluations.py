import json
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.database import create_sqlite_engine, run_migrations
from app.evaluations import (
    run_live_email_evaluation,
    run_live_ocr_evaluation,
    run_live_pdf_evaluation,
    run_recorded_evaluation,
    seed_evaluation_cases,
)
from app.extraction.contracts import CanonicalQuotation
from app.extraction.json import RecordedJsonSemanticExtractor
from app.extraction.ocr_contract import OcrLine, OcrPage, OcrResult
from app.extraction.semantic_agent import SemanticExtractionResult
from app.models import EvaluationCaseRecord, EvaluationResultRecord

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_recorded_evaluation_is_persisted_and_reports_rubric_scores(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'evaluations.db'}"
    run_migrations(database_url, PROJECT_ROOT)
    session_factory = sessionmaker(create_sqlite_engine(database_url))
    dataset_path = PROJECT_ROOT / "backend/evals/golden_dataset.json"

    with session_factory() as session:
        seed_evaluation_cases(session, dataset_path)
        run = run_recorded_evaluation(
            session,
            project_root=PROJECT_ROOT,
            golden_dataset_path=dataset_path,
            extractor=RecordedJsonSemanticExtractor(PROJECT_ROOT / "backend/evals/recorded_json_extractions"),
        )
        summary = json.loads(run.summary_json)
        results = list(session.query(EvaluationResultRecord).filter_by(run_id=run.id).all())

    passed = next(result for result in results if result.status == "passed")
    scores = json.loads(passed.scores_json)
    assert summary["passed"] == 1
    assert summary["not_run"] == 5
    assert scores["canonical_fidelity"] == 1.0
    assert scores["source_grounding"] == 1.0
    assert scores["input_tokens"] == 724
    assert scores["output_tokens"] == 418
    assert scores["estimated_cost_usd"] == "0.00214"
    assert scores["semantic_extraction_calls"] == 1
    assert scores["duration_ms"] >= 1
    assert sum(result.status == "not_run" for result in results) == 5


def test_recorded_evaluation_allows_one_source_change_to_update_multiple_canonical_fields(
    tmp_path, client_settings
):
    _, configured_settings = client_settings
    dataset_path = tmp_path / "one-recorded-case.json"
    fixture_path = PROJECT_ROOT / "backend/evals/fixtures/documents/sanova_offer_export_2026-08-03.json"
    extraction_path = PROJECT_ROOT / "backend/evals/recorded_json_extractions"
    dataset_path.write_text(
        json.dumps(
            {
                "rubric_version": "test",
                "rubric": [],
                "cases": [
                    {
                        "id": "one-recorded-case",
                        "title": "One source price with two canonical representations",
                        "input_fixture": str(fixture_path),
                        "expected": {
                            "source_system": "SanovaERP",
                            "quotation_reference": "SNV/EXP/2026/0771",
                            "line_item_count": 3,
                        },
                    }
                ],
            }
        )
    )

    engine = create_sqlite_engine(configured_settings.database_url)
    session_factory = sessionmaker(engine)
    with session_factory() as session:
        seed_evaluation_cases(session, dataset_path)
        run = run_recorded_evaluation(
            session,
            project_root=PROJECT_ROOT,
            golden_dataset_path=dataset_path,
            extractor=RecordedJsonSemanticExtractor(extraction_path),
        )
        summary = run.summary_json

    assert json.loads(summary)["passed"] == 1


def test_live_pdf_evaluation_counts_the_selected_cases_and_persists_a_failure(tmp_path, client_settings, monkeypatch):
    _, configured_settings = client_settings
    golden_dataset_path = tmp_path / "one-live-pdf-case.json"
    golden_dataset_path.write_text(
        json.dumps(
            {
                "rubric_version": "test",
                "rubric": [{"id": "canonical_fidelity"}],
                "cases": [
                    {
                        "id": "single-live-case",
                        "title": "One live PDF case",
                        "input_fixture": str(
                            PROJECT_ROOT
                            / "backend/evals/fixtures/documents/farmaceutica_andina_proforma_FA-COT-2026-118.pdf"
                        ),
                        "expected_output_fixture": str(
                            PROJECT_ROOT
                            / "backend/evals/golden_outputs/farmaceutica_andina_proforma_FA-COT-2026-118.expected.json"
                        ),
                        "execution": "live_pdf_pipeline",
                    }
                ],
            }
        )
    )

    def fake_extract(*_: object, **__: object):
        return SemanticExtractionResult(
                quotation=CanonicalQuotation(), source_facts=(), unresolved_issues=(), validation_count=1,
                model_call_count=1, termination_reason="validated",
                telemetry=({"duration_ms": 1, "provider": "test-provider", "model": "test-model"},),
        )

    import app.extraction.llm as extractor_module

    monkeypatch.setattr(extractor_module, "extract_semantics", fake_extract)
    engine = create_sqlite_engine(configured_settings.database_url)
    session_factory = sessionmaker(engine)
    settings = configured_settings.model_copy(update={"gemini_api_key": "test-key"})
    with session_factory() as session:
        session.add(
            EvaluationCaseRecord(
                id="single-live-case",
                title="One live PDF case",
                rubric_json="[]",
                input_fixture="fixture.pdf",
                expected_json="{}",
            )
        )
        session.commit()
        run = run_live_pdf_evaluation(
            session,
            project_root=PROJECT_ROOT,
            golden_dataset_path=golden_dataset_path,
            settings=settings,
        )
        assert json.loads(run.summary_json)["case_count"] == 1
        assert json.loads(run.summary_json)["passed"] == 0
        assert run.results[0].case_id == "single-live-case"
        assert run.results[0].status == "failed"
        assert json.loads(run.results[0].scores_json)["model"] == "test-model"
        assert json.loads(run.results[0].scores_json)["prompt_version"] == "semantic-agent-v1"


def test_live_ocr_evaluation_scores_anchor_evidence_without_a_model(tmp_path, client_settings, monkeypatch):
    _, configured_settings = client_settings
    fixture = tmp_path / "scan.png"
    fixture.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    expected = tmp_path / "expected.json"
    expected.write_text(json.dumps({"anchors": ["PROFORMA", "ANDINA"], "minimum_anchor_matches": 1}))
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "rubric_version": "test",
                "rubric": [],
                "cases": [
                    {
                        "id": "ocr-case",
                        "title": "OCR",
                        "input_fixture": str(fixture),
                        "expected_output_fixture": str(expected),
                        "execution": "live_ocr_evidence",
                    }
                ],
            }
        )
    )
    ocr_result = OcrResult(
        schema_version="1.0",
        provider="test-provider",
        model="test-model",
        configuration_version="test-v1",
        duration_ms=7,
        pages=[
            OcrPage(
                original_page_number=1,
                width=10,
                height=10,
                dpi=72,
                lines=[OcrLine(text="Proforma quotation", confidence=0.9, bounds=[[0, 0], [1, 0], [1, 1], [0, 1]])],
            )
        ],
    )
    monkeypatch.setattr("app.evaluations.request_ocr", lambda *_args, **_kwargs: ocr_result)
    engine = create_sqlite_engine(configured_settings.database_url)
    session_factory = sessionmaker(engine)
    settings = configured_settings.model_copy(
        update={"ocr_service_url": "https://ocr.test", "ocr_service_token": "token"}
    )
    with session_factory() as session:
        session.add(
            EvaluationCaseRecord(
                id="ocr-case", title="OCR", rubric_json="[]", input_fixture="scan.png", expected_json="{}"
            )
        )
        session.commit()
        run = run_live_ocr_evaluation(session, golden_dataset_path=dataset, settings=settings)
        scores = json.loads(run.results[0].scores_json)
        assert run.results[0].status == "passed"
        assert scores["matched_anchors"] == 1
        assert scores["model"] == "test-model"


def test_live_email_evaluation_persists_final_correction_fidelity(tmp_path, client_settings, monkeypatch):
    _, configured_settings = client_settings
    fixture = tmp_path / "correction.eml"
    fixture.write_text(
        "Subject: RFQ-1\nMessage-ID: <id>\n\nPrice: 0.128. Correction: price is 0.134."
    )
    expected = tmp_path / "expected.json"
    expected.write_text(
        json.dumps(
            {"rfq_reference": "RFQ-1", "line_items": [{"pricing": {"quoted_price": {"amount": "0.134"}}}]}
        )
    )
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "rubric_version": "test",
                "rubric": [],
                "cases": [
                    {
                        "id": "email-case",
                        "title": "Email",
                        "input_fixture": str(fixture),
                        "expected_output_fixture": str(expected),
                        "execution": "live_email_pipeline",
                    }
                ],
            }
        )
    )

    def fake_extract(*_: object, **__: object):
        return SemanticExtractionResult(
                quotation=CanonicalQuotation(
                    rfq_reference="RFQ-1",
                    line_items=[{"pricing": {"quoted_price": {"amount": "0.134"}}}],
                ),
                source_facts=(), unresolved_issues=(), validation_count=1, model_call_count=1,
                termination_reason="validated", telemetry=({"duration_ms": 1, "model": "test-model"},),
        )

    monkeypatch.setattr("app.extraction.llm.extract_semantics", fake_extract)
    engine = create_sqlite_engine(configured_settings.database_url)
    session_factory = sessionmaker(engine)
    settings = configured_settings.model_copy(update={"gemini_api_key": "test-key"})
    with session_factory() as session:
        session.add(
            EvaluationCaseRecord(
                id="email-case", title="Email", rubric_json="[]", input_fixture="email.eml", expected_json="{}"
            )
        )
        session.commit()
        run = run_live_email_evaluation(session, golden_dataset_path=dataset, settings=settings)
        assert run.results[0].status == "passed"
        assert json.loads(run.results[0].scores_json)["model"] == "test-model"
