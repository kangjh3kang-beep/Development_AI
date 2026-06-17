"""P-D — 비동기 분석: eager 태스크 실행 + 비동기 API(dev eager 결과 즉시 포함)."""


def test_analyze_task_eager_runs():
    from app.tasks.analysis_tasks import analyze_task

    payload = {"pnu": "1111010100100000002", "application_date": "2026-01-01",
               "drawings": [{"sheet_id": "A-PLAN",
                             "element_hints": [{"semantic_hint": "PILOTIS", "hint_strength": 0.9, "area": 100.0}]}]}
    out = analyze_task.apply(args=[payload]).get()  # apply=동기 실행
    assert out["drawing_source"] == "HINTS"
    assert out["drawing_elements_n"] == 1
    assert out["input_hash"]


def test_analyze_async_endpoint(client):
    r = client.post("/api/v1/analyze/async", json={
        "pnu": "1111010100100000002", "application_date": "2026-01-01",
        "rules": [{"rule": {"rule_id": "height_limit", "comparator": "<=", "basis_article": "건축법 시행령"},
                   "measured": 30.0, "limit": 20.0, "confidence": 0.9}]})
    assert r.status_code == 200
    body = r.json()
    assert body["task_id"]
    assert body["eager"] is True
    # dev eager(동기 폴백) → 결과 즉시 포함
    assert body["result"]["input_hash"]
    assert body["result"]["findings"][0]["verdict"] == "NON_COMPLIANT"  # height 위반


def test_analyze_async_deterministic_with_sync():
    """비동기(eager) 결과 = 동기 결과(결정론 보존)."""
    from app.contracts.analysis import AnalysisInput
    from app.services.pipeline.analysis_pipeline import run_analysis
    from app.tasks.analysis_tasks import analyze_task

    payload = {"pnu": "1111010100100000002", "application_date": "2026-01-01",
               "issue": "FAR_DISPUTE",
               "corpus": [{"case_id": f"c{i}", "source": f"의결서-{i}", "decision_type": "CONDITIONAL",
                           "issue_labels": ["FAR_DISPUTE"], "conditions": ["공개공지 확대"]} for i in range(6)]}
    sync = run_analysis(AnalysisInput(**payload))
    async_out = analyze_task.apply(args=[payload]).get()
    assert async_out["input_hash"] == sync.input_hash
    assert async_out["precedent_source"] == "VECTOR_SEARCH"
