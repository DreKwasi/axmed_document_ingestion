"""Evaluation runner and scoring engine for golden benchmark datasets."""

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.extraction.commercial import apply_commercial_rules
from app.extraction.email_parser import parse_email
from app.extraction.email_reconciliation import reconcile_email_price_uoms
from app.extraction.json import JsonSemanticExtractor, profile_json, validate_source_facts
from app.extraction.ocr_client import request_ocr
from app.extraction.pdf_parser import parse_native_pdf
from app.models import EvaluationCaseRecord, EvaluationResultRecord, EvaluationRunRecord
from app.security.redaction import redact_for_model

# --- Section 1: Fixture Path Resolution & Case Seeding ---


def _dataset_fixture_path(golden_dataset_path: Path, fixture: str) -> Path:
    """Resolve fixture file path relative to the golden dataset JSON file."""
    fixture_path = Path(fixture)
    return fixture_path if fixture_path.is_absolute() else golden_dataset_path.parent / fixture_path


def seed_evaluation_cases(session: Session, golden_dataset_path: Path) -> None:
    """Load benchmark evaluation cases from golden_dataset.json into the database."""
    dataset = json.loads(golden_dataset_path.read_text())
    for case in dataset["cases"]:
        expected = case.get("expected")
        expected_output_fixture = case.get("expected_output_fixture")
        if expected_output_fixture:
            expected = json.loads(_dataset_fixture_path(golden_dataset_path, expected_output_fixture).read_text())
        existing = session.get(EvaluationCaseRecord, case["id"])
        if existing:
            continue
        session.add(
            EvaluationCaseRecord(
                id=case["id"],
                title=case["title"],
                rubric_json=json.dumps(dataset["rubric"]),
                input_fixture=case["input_fixture"],
                expected_json=json.dumps(expected or {}),
            )
        )
    session.commit()


# --- Section 2: Recorded Offline Evaluation Runner ---


def run_recorded_evaluation(
    session: Session,
    *,
    project_root: Path,
    golden_dataset_path: Path,
    extractor: JsonSemanticExtractor,
) -> EvaluationRunRecord:
    """Execute recorded offline evaluation against golden dataset JSON fixtures."""
    dataset = json.loads(golden_dataset_path.read_text())
    run = EvaluationRunRecord(
        rubric_version=dataset["rubric_version"],
        execution_mode="recorded",
        summary_json="{}",
    )
    session.add(run)
    session.flush()
    results = []
    not_run = 0
    for case in dataset["cases"]:
        if case.get("execution"):
            skipped_scores = {"canonical_fidelity": 0.0, "source_grounding": 0.0, "safety_and_uncertainty": 0.0}
            session.add(
                EvaluationResultRecord(
                    run_id=run.id,
                    case_id=case["id"],
                    status="not_run",
                    scores_json=json.dumps(skipped_scores),
                    error_analysis_json=json.dumps([f"This case requires {case['execution']} evaluation mode."]),
                )
            )
            results.append(skipped_scores)
            not_run += 1
            continue
        fixture_path = _dataset_fixture_path(golden_dataset_path, case["input_fixture"])
        payload = json.loads(fixture_path.read_text())
        source_system = str(
            payload.get("source_system") or (payload.get("meta") or {}).get("source_system") or "unknown"
        )
        started = perf_counter()
        proposal = extractor.extract(payload, profile_json(payload), source_document=str(fixture_path))
        expected = case["expected"]
        errors: list[str] = []
        if proposal is None:
            errors.append("No recorded JSON semantic extraction was available.")
            extraction_calls = 0
            line_item_count = 0
            input_tokens = 0
            output_tokens = 0
            estimated_cost_usd = "0"
            duration_ms = max(1, int((perf_counter() - started) * 1000))
        else:
            facts, invalid_paths = validate_source_facts(payload, proposal.extraction.source_facts)
            extraction_calls = 1
            input_tokens = proposal.input_tokens or 0
            output_tokens = proposal.output_tokens or 0
            estimated_cost_usd = (
                "0" if proposal.estimated_cost_usd is None else str(proposal.estimated_cost_usd)
            )
            quotation = proposal.extraction.quotation
            duration_ms = max(1, int((perf_counter() - started) * 1000))
            line_item_count = len(quotation.line_items)
            if invalid_paths:
                errors.append("Recorded extraction contained invalid source references.")
            if not facts:
                errors.append("Recorded extraction did not recover source-grounded facts.")
            if quotation.quotation_reference != expected["quotation_reference"]:
                errors.append("Quotation reference did not match golden data.")
            if line_item_count != expected["line_item_count"]:
                errors.append("Line item count did not match golden data.")
            if source_system != expected["source_system"]:
                errors.append("Source system did not match golden data.")
        scores: dict[str, Any] = {
            "canonical_fidelity": 1.0 if not errors else 0.0,
            "source_grounding": 1.0 if not errors else 0.0,
            "safety_and_uncertainty": 1.0,
            "semantic_extraction_calls": extraction_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "duration_ms": duration_ms,
        }
        status = "passed" if not errors else "failed"
        result = EvaluationResultRecord(
            run_id=run.id,
            case_id=case["id"],
            status=status,
            scores_json=json.dumps(scores),
            error_analysis_json=json.dumps(errors),
        )
        session.add(result)
        results.append(scores)
    run.summary_json = json.dumps(
        {
            "case_count": len(results),
            "passed": sum(score["canonical_fidelity"] == 1.0 for score in results),
            "not_run": not_run,
            "rubrics": dataset["rubric"],
        }
    )
    session.commit()
    return run


# --- Section 3: Live PDF Extraction Pipeline Evaluation ---


def run_live_pdf_evaluation(
    session: Session,
    *,
    project_root: Path,
    golden_dataset_path: Path,
    settings: Config,
) -> EvaluationRunRecord:
    """Run source PDFs through the production extraction stages and score reviewed fields."""
    if not settings.gemini_api_key:
        raise ValueError("Live PDF evaluation requires configured Gemini credentials.")
    dataset = json.loads(golden_dataset_path.read_text())
    run = EvaluationRunRecord(
        rubric_version=dataset["rubric_version"], execution_mode="live_pdf_pipeline", summary_json="{}"
    )
    session.add(run)
    session.flush()
    passed = 0
    live_cases = [case for case in dataset["cases"] if case.get("execution") == "live_pdf_pipeline"]
    for case in live_cases:
        expected = json.loads(_dataset_fixture_path(golden_dataset_path, case["expected_output_fixture"]).read_text())
        fixture_path = _dataset_fixture_path(golden_dataset_path, case["input_fixture"])
        parsed = parse_native_pdf(fixture_path.read_bytes())
        context = redact_for_model(
            {
                "source_document": fixture_path.name,
                "pages": [
                    {
                        "page_number": page.page_number,
                        "liteparse": page.raw_representation,
                        "text": page.text,
                    }
                    for page in parsed.pages
                ],
            }
        )
        started = perf_counter()
        from app.extraction.llm import LangChainSemanticExtractor

        extractor = LangChainSemanticExtractor(
            settings.gemini_api_key,
            settings.gemini_model,
            settings.gemini_request_timeout_seconds,
        )
        actual, telemetry = extractor.extract_canonical_quotation(context, source_type="pdf")
        actual_payload = apply_commercial_rules(actual).model_dump(mode="json")
        errors = _subset_mismatches(expected, actual_payload)
        status = "passed" if not errors else "failed"
        passed += status == "passed"
        session.add(
            EvaluationResultRecord(
                run_id=run.id,
                case_id=case["id"],
                status=status,
                scores_json=json.dumps(
                    {
                        "canonical_fidelity": 1.0 if not errors else 0.0,
                        "duration_ms": telemetry.get("duration_ms", int((perf_counter() - started) * 1000)),
                        "provider": telemetry.get("provider"),
                        "model": telemetry.get("model"),
                        "prompt_version": telemetry.get("prompt_version"),
                        "environment": settings.environment,
                    }
                ),
                error_analysis_json=json.dumps(errors),
            )
        )
    run.summary_json = json.dumps(
        {"case_count": len(live_cases), "passed": passed, "rubrics": dataset["rubric"]}
    )
    session.commit()
    return run


# --- Section 4: Live OCR Text Evidence Evaluation ---


def run_live_ocr_evaluation(
    session: Session,
    *,
    golden_dataset_path: Path,
    settings: Config,
) -> EvaluationRunRecord:
    """Evaluate configured OCR evidence without invoking an extraction model."""
    if not settings.ocr_service_url or not settings.ocr_service_token:
        raise ValueError("Live OCR evaluation requires configured OCR service credentials.")
    dataset = json.loads(golden_dataset_path.read_text())
    ocr_cases = [case for case in dataset["cases"] if case.get("execution") == "live_ocr_evidence"]
    run = EvaluationRunRecord(
        rubric_version=dataset["rubric_version"], execution_mode="live_ocr_evidence", summary_json="{}"
    )
    session.add(run)
    session.flush()
    passed = 0
    for case in ocr_cases:
        fixture_path = _dataset_fixture_path(golden_dataset_path, case["input_fixture"])
        expected = json.loads(_dataset_fixture_path(golden_dataset_path, case["expected_output_fixture"]).read_text())
        result = request_ocr(
            settings.ocr_service_url,
            data=fixture_path.read_bytes(),
            media_type="image/png" if fixture_path.suffix.lower() == ".png" else "image/jpeg",
            selected_original_pages=(1,),
            idempotency_key=f"evaluation:{case['id']}",
            deadline_ms=settings.ocr_request_timeout_seconds * 1000,
            token=settings.ocr_service_token,
        )
        text = "\n".join(line.text for page in result.pages for line in page.lines)
        matched, missing = _ocr_anchor_result(expected, text)
        errors = [f"Missing OCR anchor: {anchor}" for anchor in missing]
        required_matches = (
            len(expected["anchors"]) if expected.get("require_all_anchors") else expected["minimum_anchor_matches"]
        )
        status = "passed" if len(matched) >= required_matches else "failed"
        passed += status == "passed"
        session.add(
            EvaluationResultRecord(
                run_id=run.id,
                case_id=case["id"],
                status=status,
                scores_json=json.dumps(
                    {
                        "ocr_anchor_recall": len(matched) / len(expected["anchors"]),
                        "matched_anchors": len(matched),
                        "required_anchor_matches": required_matches,
                        "provider": result.provider,
                        "model": result.model,
                        "configuration_version": result.configuration_version,
                        "duration_ms": result.duration_ms,
                    }
                ),
                error_analysis_json=json.dumps(errors),
            )
        )
    run.summary_json = json.dumps({"case_count": len(ocr_cases), "passed": passed, "rubrics": dataset["rubric"]})
    session.commit()
    return run


# --- Section 5: Live Email Extraction Pipeline Evaluation ---


def run_live_email_evaluation(
    session: Session,
    *,
    golden_dataset_path: Path,
    settings: Config,
) -> EvaluationRunRecord:
    """Run approved email cases through parse, redaction, structured extraction, and rules."""
    if not settings.gemini_api_key:
        raise ValueError("Live email evaluation requires configured Gemini credentials.")
    dataset = json.loads(golden_dataset_path.read_text())
    email_cases = [case for case in dataset["cases"] if case.get("execution") == "live_email_pipeline"]
    run = EvaluationRunRecord(
        rubric_version=dataset["rubric_version"], execution_mode="live_email_pipeline", summary_json="{}"
    )
    session.add(run)
    session.flush()
    passed = 0
    from app.extraction.llm import LangChainSemanticExtractor

    extractor = LangChainSemanticExtractor(
        settings.gemini_api_key,
        settings.gemini_model,
        settings.gemini_request_timeout_seconds,
    )
    for case in email_cases:
        fixture_path = _dataset_fixture_path(golden_dataset_path, case["input_fixture"])
        expected = json.loads(_dataset_fixture_path(golden_dataset_path, case["expected_output_fixture"]).read_text())
        parsed = parse_email(fixture_path.read_bytes())
        context = redact_for_model(
            {
                "subject": parsed.subject,
                "message_id": parsed.message_id,
                "body_text": parsed.body_text,
                "supplier_organization": parsed.supplier_organization,
            }
        )
        started = perf_counter()
        actual, telemetry = extractor.extract_canonical_quotation(context, source_type="email")
        reconciled = reconcile_email_price_uoms(actual, parsed.body_text)
        errors = _subset_mismatches(expected, apply_commercial_rules(reconciled).model_dump(mode="json"))
        status = "passed" if not errors else "failed"
        passed += status == "passed"
        session.add(
            EvaluationResultRecord(
                run_id=run.id,
                case_id=case["id"],
                status=status,
                scores_json=json.dumps(
                    {
                        "canonical_fidelity": 1.0 if not errors else 0.0,
                        "duration_ms": telemetry.get("duration_ms", int((perf_counter() - started) * 1000)),
                        "provider": telemetry.get("provider"),
                        "model": telemetry.get("model"),
                        "prompt_version": telemetry.get("prompt_version"),
                        "environment": settings.environment,
                    }
                ),
                error_analysis_json=json.dumps(errors),
            )
        )
    run.summary_json = json.dumps({"case_count": len(email_cases), "passed": passed, "rubrics": dataset["rubric"]})
    session.commit()
    return run


# --- Section 6: Parity Comparison & Scoring Utilities ---


def _ocr_anchor_result(expected: dict[str, Any], text: str) -> tuple[list[str], list[str]]:
    """Match required textual anchors against normalized OCR transcription."""
    normalized_text = _normalize_ocr_text(text)
    matched = [anchor for anchor in expected["anchors"] if _normalize_ocr_text(anchor) in normalized_text]
    missing = [anchor for anchor in expected["anchors"] if anchor not in matched]
    return matched, missing


def _normalize_ocr_text(value: str) -> str:
    """Strip all non-alphanumeric characters for fuzzy anchor matching."""
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _subset_mismatches(expected: Any, actual: Any, path: str = "") -> list[str]:
    """Recursively identify differences where actual output diverges from expected baseline."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path or '$'} expected object."]
        return [
            mismatch
            for key, value in expected.items()
            for mismatch in _subset_mismatches(value, actual.get(key), f"{path}.{key}" if path else key)
        ]
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return [f"{path} expected {len(expected)} items."]
        return [
            mismatch
            for index, value in enumerate(expected)
            for mismatch in _subset_mismatches(value, actual[index], f"{path}[{index}]")
        ]
    if _values_match(expected, actual):
        return []
    return [f"{path} expected {expected!r}, got {actual!r}."]


def _values_match(expected: Any, actual: Any) -> bool:
    """Compare scalar values with numeric equality fallback."""
    try:
        return Decimal(str(expected)) == Decimal(str(actual))
    except (InvalidOperation, ValueError):
        return expected == actual


def _get_path(payload: dict[str, Any], path: str) -> Any:
    """Navigate a dotted path through nested dictionaries and lists."""
    current: Any = payload
    for segment in path.split("."):
        current = current[int(segment)] if isinstance(current, list) else current[segment]
    return current


def _remove_operational_evidence(value: Any) -> None:
    """Exclude method/confidence metadata when comparing business-value parity."""
    if isinstance(value, dict):
        value.pop("evidence", None)
        for child in value.values():
            _remove_operational_evidence(child)
    elif isinstance(value, list):
        for child in value:
            _remove_operational_evidence(child)


def list_runs(session: Session) -> list[EvaluationRunRecord]:
    """Fetch recent evaluation runs ordered by creation timestamp descending."""
    return list(session.scalars(select(EvaluationRunRecord).order_by(EvaluationRunRecord.created_at.desc()).limit(20)))
