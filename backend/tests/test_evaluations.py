import json
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from app.application.evaluations import run_live_email_evaluation, run_live_ocr_evaluation, run_live_pdf_evaluation
from app.domain.contracts import CanonicalQuotation
from app.domain.ocr_contract import OcrLine, OcrPage, OcrResult
from app.infrastructure.database import create_sqlite_engine
from app.infrastructure.models import EvaluationCaseRecord

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_recorded_evaluation_is_persisted_and_reports_rubric_scores(client):
    before = client.get("/api/v1/evaluations")
    assert before.status_code == 200
    assert before.json()["runs"] == []
    assert len(before.json()["cases"]) == 6

    created = client.post("/api/v1/evaluations/runs")

    assert created.status_code == 201
    assert created.json()["summary"]["passed"] == 1
    assert created.json()["summary"]["not_run"] == 5
    after = client.get("/api/v1/evaluations").json()
    result = after["runs"][0]["results"][0]
    assert result["status"] == "passed"
    assert result["scores"]["canonical_fidelity"] == 1.0
    assert result["scores"]["mapping_efficiency"] == 1.0
    assert result["scores"]["input_tokens"] == 724
    assert result["scores"]["output_tokens"] == 418
    assert result["scores"]["estimated_cost_usd"] == "0.00214"
    assert result["scores"]["warm_input_tokens"] == 0
    assert result["scores"]["warm_output_tokens"] == 0
    assert result["scores"]["warm_estimated_cost_usd"] == "0"
    assert result["scores"]["cold_duration_ms"] >= 1
    assert result["scores"]["warm_duration_ms"] >= 1
    assert after["runs"][0]["results"][1]["status"] == "not_run"


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

    class FakeExtractor:
        def __init__(self, *_: object):
            pass

        def extract_canonical_quotation(self, *_: object, **__: object):
            return CanonicalQuotation(), {
                "duration_ms": 1,
                "provider": "test-provider",
                "model": "test-model",
                "prompt_version": "test-prompt-v1",
            }

    import app.domain.langchain_extractor as extractor_module

    monkeypatch.setattr(extractor_module, "LangChainSemanticExtractor", FakeExtractor)
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
        assert json.loads(run.results[0].scores_json)["prompt_version"] == "test-prompt-v1"


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
    monkeypatch.setattr("app.application.evaluations.request_ocr", lambda *_args, **_kwargs: ocr_result)
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

    class FakeExtractor:
        def __init__(self, *_: object):
            pass

        def extract_canonical_quotation(self, *_: object, **__: object):
            return CanonicalQuotation(
                rfq_reference="RFQ-1",
                line_items=[{"pricing": {"quoted_price": {"amount": "0.134"}}}],
            ), {"duration_ms": 1, "model": "test-model"}

    monkeypatch.setattr("app.domain.langchain_extractor.LangChainSemanticExtractor", FakeExtractor)
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
