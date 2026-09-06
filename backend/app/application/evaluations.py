import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.settings import Settings
from app.domain.commercial_rules import apply_commercial_rules
from app.domain.pdf_parser import parse_native_pdf
from app.domain.schema_mapping import (
    RecordedSemanticMappingProvider,
    apply_mapping,
    extract_source_metadata,
    fingerprint,
)
from app.infrastructure.models import EvaluationCaseRecord, EvaluationResultRecord, EvaluationRunRecord
from app.security.redaction import redact_for_model
from app.workers.ocr_client import request_ocr


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    current: Any = payload
    *segments, final_segment = path.split(".")
    for segment in segments:
        current = current[int(segment)] if isinstance(current, list) else current[segment]
    if isinstance(current, list):
        current[int(final_segment)] = value
    else:
        current[final_segment] = value


def _dataset_fixture_path(golden_dataset_path: Path, fixture: str) -> Path:
    fixture_path = Path(fixture)
    return fixture_path if fixture_path.is_absolute() else golden_dataset_path.parent / fixture_path


def seed_evaluation_cases(session: Session, golden_dataset_path: Path) -> None:
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


def run_recorded_evaluation(
    session: Session,
    *,
    project_root: Path,
    golden_dataset_path: Path,
    provider: RecordedSemanticMappingProvider,
) -> EvaluationRunRecord:
    dataset = json.loads(golden_dataset_path.read_text())
    run = EvaluationRunRecord(
        rubric_version=dataset["rubric_version"],
        execution_mode="recorded",
        summary_json="{}",
    )
    session.add(run)
    session.flush()
    results = []
    for case in dataset["cases"]:
        if case.get("execution"):
            scores = {"canonical_fidelity": 0.0, "mapping_efficiency": 0.0, "safety_and_uncertainty": 0.0}
            session.add(
                EvaluationResultRecord(
                    run_id=run.id,
                    case_id=case["id"],
                    status="not_run",
                    scores_json=json.dumps(scores),
                    error_analysis_json=json.dumps([f"This case requires {case['execution']} evaluation mode."]),
                )
            )
            results.append(scores)
            continue
        fixture_path = _dataset_fixture_path(golden_dataset_path, case["input_fixture"])
        payload = json.loads(fixture_path.read_text())
        source_system, _ = extract_source_metadata(payload)
        schema_fingerprint = fingerprint(payload)
        cold_started = perf_counter()
        cold_proposal = provider.propose(source_system, schema_fingerprint)
        expected = case["expected"]
        errors: list[str] = []
        if cold_proposal is None:
            errors.append("No recorded semantic mapping proposal was available.")
            cold_calls = 0
            warm_calls = 0
            line_item_count = 0
            input_tokens = 0
            output_tokens = 0
            estimated_cost_usd = "0"
            cold_duration_ms = max(1, int((perf_counter() - cold_started) * 1000))
            warm_duration_ms = 0
        else:
            # The recorded proposal represents a reviewer-confirmed mapping. Once trusted,
            # the warm path calls only the deterministic mapper; it has no provider handle.
            cold_calls = 1
            input_tokens = cold_proposal.input_tokens
            output_tokens = cold_proposal.output_tokens
            estimated_cost_usd = str(cold_proposal.estimated_cost_usd)
            quotation = apply_mapping(
                payload,
                cold_proposal.mapping,
                source_document=str(fixture_path),
                method="llm_extraction",
            )
            cold_duration_ms = max(1, int((perf_counter() - cold_started) * 1000))
            warm_payload = json.loads(json.dumps(payload))
            warm_mutation = expected["warm_mutation"]
            _set_path(warm_payload, warm_mutation["source_path"], warm_mutation["value"])
            warm_started = perf_counter()
            warm_quotation = apply_mapping(
                warm_payload,
                cold_proposal.mapping,
                source_document=str(fixture_path),
                method="deterministic_mapping",
            )
            warm_duration_ms = max(1, int((perf_counter() - warm_started) * 1000))
            warm_calls = 0
            line_item_count = len(quotation.line_items)
            if quotation.quotation_reference != expected["quotation_reference"]:
                errors.append("Quotation reference did not match golden data.")
            if line_item_count != expected["line_item_count"]:
                errors.append("Line item count did not match golden data.")
            if source_system != expected["source_system"]:
                errors.append("Source system did not match golden data.")
            cold_payload = quotation.model_dump(mode="json")
            warm_payload = warm_quotation.model_dump(mode="json")
            _set_path(
                warm_payload, warm_mutation["canonical_path"], _get_path(cold_payload, warm_mutation["canonical_path"])
            )
            _remove_operational_evidence(cold_payload)
            _remove_operational_evidence(warm_payload)
            if warm_payload != cold_payload:
                errors.append("Warm deterministic result diverged outside the changed source value.")
        scores = {
            "canonical_fidelity": 1.0 if not errors else 0.0,
            "mapping_efficiency": 1.0 if cold_calls == 1 and warm_calls == 0 else 0.0,
            "safety_and_uncertainty": 1.0,
            "cold_mapping_calls": cold_calls,
            "warm_mapping_calls": warm_calls,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost_usd": estimated_cost_usd,
            "warm_input_tokens": 0,
            "warm_output_tokens": 0,
            "warm_estimated_cost_usd": "0",
            "cold_duration_ms": cold_duration_ms,
            "warm_duration_ms": warm_duration_ms,
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
            "not_run": sum(
                score["canonical_fidelity"] == 0.0 and "cold_mapping_calls" not in score for score in results
            ),
            "rubrics": dataset["rubric"],
        }
    )
    session.commit()
    return run


def run_live_pdf_evaluation(
    session: Session,
    *,
    project_root: Path,
    golden_dataset_path: Path,
    settings: Settings,
) -> EvaluationRunRecord:
    """Run source PDFs through the production extraction stages and score reviewed fields."""

    if not settings.resolved_gemini_api_key:
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
                "pages": [{"page_number": page.page_number, "text": page.text} for page in parsed.pages],
            }
        )
        started = perf_counter()
        from app.domain.langchain_extractor import LangChainSemanticExtractor

        extractor = LangChainSemanticExtractor(settings.resolved_gemini_api_key, settings.resolved_gemini_model)
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


def run_live_ocr_evaluation(
    session: Session,
    *,
    golden_dataset_path: Path,
    settings: Settings,
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


def _ocr_anchor_result(expected: dict[str, Any], text: str) -> tuple[list[str], list[str]]:
    normalized_text = _normalize_ocr_text(text)
    matched = [anchor for anchor in expected["anchors"] if _normalize_ocr_text(anchor) in normalized_text]
    missing = [anchor for anchor in expected["anchors"] if anchor not in matched]
    return matched, missing


def _normalize_ocr_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _subset_mismatches(expected: Any, actual: Any, path: str = "") -> list[str]:
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
    try:
        return Decimal(str(expected)) == Decimal(str(actual))
    except (InvalidOperation, ValueError):
        return expected == actual


def _get_path(payload: dict[str, Any], path: str) -> Any:
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
    return list(session.scalars(select(EvaluationRunRecord).order_by(EvaluationRunRecord.created_at.desc()).limit(20)))
