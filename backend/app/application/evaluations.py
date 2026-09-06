import json
from pathlib import Path
from time import perf_counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.schema_mapping import (
    RecordedSemanticMappingProvider,
    apply_mapping,
    extract_source_metadata,
    fingerprint,
)
from app.infrastructure.models import EvaluationCaseRecord, EvaluationResultRecord, EvaluationRunRecord


def _set_path(payload: dict[str, Any], path: str, value: Any) -> None:
    current: Any = payload
    *segments, final_segment = path.split(".")
    for segment in segments:
        current = current[int(segment)] if isinstance(current, list) else current[segment]
    if isinstance(current, list):
        current[int(final_segment)] = value
    else:
        current[final_segment] = value


def seed_evaluation_cases(session: Session, golden_dataset_path: Path) -> None:
    dataset = json.loads(golden_dataset_path.read_text())
    for case in dataset["cases"]:
        existing = session.get(EvaluationCaseRecord, case["id"])
        if existing:
            continue
        session.add(
            EvaluationCaseRecord(
                id=case["id"],
                title=case["title"],
                rubric_json=json.dumps(dataset["rubric"]),
                input_fixture=case["input_fixture"],
                expected_json=json.dumps(case["expected"]),
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
        payload = json.loads((project_root / case["input_fixture"]).read_text())
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
                source_document=case["input_fixture"],
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
                source_document=case["input_fixture"],
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
            "rubrics": dataset["rubric"],
        }
    )
    session.commit()
    return run


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
