"""단건 /land-price/desk-appraisal 원장 요약 키 교정 앵커.

배경(잠복 결함): desk_appraisal 서비스 반환 dict 은 채택 총액을 `appraised_total_won`,
채택 근거를 `weight_note` 로 담는다. 그러나 라우터는 존재하지 않는 `final_value_won`/
`estimated_total_won`/`adopted_method`/(최상위)`method` 키를 읽어 항상 None 을 원장에 적재했다.
이 테스트는 라우터가 원장 summary 에 실제 값(appraised_total_won → final_value_won,
weight_note → adopted_method)을 싣고, project_id(additive) 를 전달함을 고정한다.

외부콜(desk_appraisal)·원장(record_user_analysis/attach_ledger_hash)은 monkeypatch 로 격리.
"""
import pytest

# desk_appraisal 반환 dict 의 실제 계약(★final_value_won/adopted_method 키는 없음 — 잠복결함 근원).
FAKE_RESULT = {
    "ok": True,
    "appraised_price_per_sqm": 3_000_000,
    "appraised_total_won": 1_500_000_000,
    "weight_note": "공시지가기준·거래사례 가중 채택",
    "area_sqm": 500.0,
    "confidence": 0.8,
    "range_per_sqm": {"low": 2_700_000, "high": 3_300_000},
    "methods": [],
    "disclaimer": "참고용 추정(감정평가 아님)",
}


def test_fake_result_lacks_old_keys():
    """회귀 앵커: 구 코드가 읽던 키들은 응답에 존재하지 않아 항상 None 이었다."""
    assert FAKE_RESULT.get("final_value_won") is None
    assert FAKE_RESULT.get("estimated_total_won") is None
    assert FAKE_RESULT.get("adopted_method") is None
    assert FAKE_RESULT.get("method") is None  # 최상위 method 키 없음(개별 methods[] 항목에만 존재)


@pytest.mark.asyncio
async def test_desk_appraisal_ledger_uses_appraised_total_and_weight_note(client, monkeypatch):
    """단건 /desk-appraisal 원장 summary = appraised_total_won → final_value_won,
    weight_note → adopted_method, project_id 전달."""
    # ★엔드포인트의 정규 모듈명은 apps.api.app.routers.land_price (main 이 그 경로로 include).
    #   dual sys.path 로 app.routers.land_price 는 별개 객체라 monkeypatch 가 새지 않게 정규명 사용.
    import app.services.ledger.analysis_ledger_service as als
    import app.services.ledger.ledger_adapters as la
    import apps.api.app.routers.land_price as lp

    captured: dict = {}

    async def fake_desk(**kwargs):
        return dict(FAKE_RESULT)

    async def fake_record(**kwargs):
        captured.update(kwargs)
        return {"ledger_hash": "deadbeef"}

    def fake_attach(result, wb):  # 원장 해시 attach 는 무손상 통과만 확인
        return result

    monkeypatch.setattr(lp, "desk_appraisal", fake_desk)
    monkeypatch.setattr(la, "record_user_analysis", fake_record)
    monkeypatch.setattr(als, "attach_ledger_hash", fake_attach)

    resp = await client.post(
        "/api/v1/land-price/desk-appraisal",
        json={"address": "서울 강남구 역삼동 1", "pnu": "1168010100", "area_sqm": 500,
              "project_id": "11111111-2222-3333-4444-555555555555"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("ok") is True

    summary = captured.get("summary") or {}
    # ★핵심: 채택 총액·근거가 실제 값으로 적재(구 결함 = None).
    assert summary.get("final_value_won") == 1_500_000_000
    assert summary.get("adopted_method") == "공시지가기준·거래사례 가중 채택"
    # additive project_id 귀속 전달.
    assert captured.get("project_id") == "11111111-2222-3333-4444-555555555555"
