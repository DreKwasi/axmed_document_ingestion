def test_recorded_evaluation_is_persisted_and_reports_rubric_scores(client):
    before = client.get("/api/v1/evaluations")
    assert before.status_code == 200
    assert before.json()["runs"] == []
    assert len(before.json()["cases"]) == 1

    created = client.post("/api/v1/evaluations/runs")

    assert created.status_code == 201
    assert created.json()["summary"]["passed"] == 1
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
