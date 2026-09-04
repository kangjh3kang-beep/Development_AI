"""토지필지 종합분석 **P1 — 선택 필지 병렬 발급·권리분석** 회귀망.

★모든 테스트는 조립된 응답 표면(`survey_selected_parcels()`의 반환 dict — cards→owners→
필드)을 직접 태운다. 내부 헬퍼(`_judge_owner` 등)만 검사하면 응답 조립 단계에서 블록이
빠지는 변이가 생존한다(이 저장소에서 실제로 겪은 형태 — CLAUDE.md 회귀망 규율 A-4).

법령 근거: 주택법 §22①2호 — 지구단위계획구역 결정고시일 기준 10년 이상 계속보유한
소유자는 매도청구 대상에서 제외된다. 기준일은 **오늘이 아니라** 결정고시일이다.
"""

from __future__ import annotations

from typing import Any

import pytest

import app.services.registry.registry_analysis_service as ras
from app.services.land_intelligence import parcel_rights_survey_service as svc

# ★보유기간 10년 요건이 **실제로 존재하는** 사업방식(주택법 계열). 이 파일의 기존 케이스는
#   전부 "보유기간 판정이 성립하는" 세계를 다루므로 이 방식으로 태운다.
#   ★2026-08-15 정정: 이 인자가 없던 시절 코드는 주택법 §22①2호의 10년 규칙을 **모든**
#     사업방식에 적용하고 사유에 "주택법 §22①2호"를 하드코딩했다(동의율 기반 사업의 법적
#     오분류). 아래 `_CONSENT_SCHEME` 대조군이 그 차이를 잠근다.
_HOUSING_SCHEME = "지구단위계획 연계"
_CONSENT_SCHEME = "가로주택정비사업"  # 소규모정비특례법 §35 — 보유기간 요건 없음


def _owner(name: str, share: str, acq_date: str | None, acq_cause: str | None) -> dict[str, Any]:
    return {
        "name": name, "share": share,
        "acquisition_date": acq_date, "acquisition_cause": acq_cause,
        "acquisition_price": None,
    }


def _ok_analysis(owners: list[dict[str, Any]]) -> dict[str, Any]:
    """RegistryAnalysisService.analyze() 성공 응답 형태(권리분석 완료)."""
    return {
        "status": "ok",
        "origin": "hyphen",
        "land": {"pnu": "1111010100100010000"},
        "ai": {
            "generated": True,
            "ownership": {
                "current_owner": ", ".join(o["name"] for o in owners),
                "owners": owners,
            },
            "provisional_registration": {"exists": False},
            "seizure": [], "mortgage": [], "other_rights": [],
            "baseline_right": "해당 없음",
            "acquired_extinguished": "기재 없음",
            "right_to_demand_sale": {"possible": "판단보류", "reason": "테스트 픽스처"},
            "rights_analysis": "테스트 픽스처 권리분석.",
            "risks": [], "safety_grade": "안전", "summary": "테스트 요약",
        },
    }


def _install_fake_registry_analysis(monkeypatch: pytest.MonkeyPatch, by_address: dict[str, Any]) -> None:
    """address별로 다른 analyze() 결과(또는 예외)를 내는 가짜 서비스를 심는다.

    ★`app.services.registry.registry_analysis_service.RegistryAnalysisService`를 패치한다
    (실제 라우터 테스트 `test_registry_issue_charging.py`와 동일한 지점) — 이 서비스가
    함수 본문 안에서 `from ... import RegistryAnalysisService`로 매 호출마다 재-임포트하므로,
    호출 시점에 패치된 값이 그대로 쓰인다.
    """

    class _Svc:
        async def analyze(self, **kw: Any) -> dict[str, Any]:
            addr = kw.get("address")
            result = by_address.get(addr)
            if result is None:
                raise KeyError(f"픽스처에 없는 주소: {addr}")
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(ras, "RegistryAnalysisService", _Svc)


# ── 제약2: 기준일 미입력이면 보유기간 판정을 하지 않는다 ──────────────────

@pytest.mark.asyncio
async def test_기준일_미입력시_보유기간_판정을_하지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    owners = [_owner("김철수", "단독", "2005-03-02", "매매")]
    _install_fake_registry_analysis(monkeypatch, {"서울시 A": _ok_analysis(owners)})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 A"}], district_plan_decision_date=None, scheme=_HOUSING_SCHEME
    )

    assert out["district_plan_decision_date"] is None
    assert out["summary"]["decision_date_provided"] is False
    card = out["cards"][0]
    assert card["status"] == "ok"
    owner = card["owners"][0]
    # ★보류값 계약 — 판정 자리엔 **판정만**. 사유는 코드로 온다(문구 변경에 안 깨진다).
    assert owner["sell_claim_judgment"] is None, "판정 자리에 판정이 아닌 값이 들어 있다"
    assert owner["sell_claim_judgment_absent"] == AWAITING_INPUT, (
        f"기준일 없이도 매도청구 판정을 냈다 — 오늘 날짜로 임의 계산했을 가능성: {owner}"
    )
    assert owner["holding_period_years"] is None, "기준일 없이 보유기간 숫자를 냈다(조용히 틀린 값)"
    assert owner["holding_period_basis"] is None
    assert "기준일" in owner["sell_claim_reason"]
    assert "주택법" in owner["sell_claim_reason"], "근거 법령 문구가 사라졌다"
    assert "2005-03-02" in owner["evidence"], "실제 취득일이 근거 스니펫에 실리지 않았다"
    assert "매매" in owner["evidence"], "실제 취득원인이 근거 스니펫에 실리지 않았다"


@pytest.mark.asyncio
async def test_기준일_입력시엔_보유기간이_계산된다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★대조군 — 위 테스트가 '항상 판정 보류'인 결함(공허한 통과)이 아님을 확인한다."""
    owners = [_owner("김철수", "단독", "2005-03-02", "매매")]
    _install_fake_registry_analysis(monkeypatch, {"서울시 A": _ok_analysis(owners)})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 A"}], district_plan_decision_date="2024-01-01", scheme=_HOUSING_SCHEME
    )

    assert out["summary"]["decision_date_provided"] is True
    owner = out["cards"][0]["owners"][0]
    assert owner["sell_claim_judgment"] is not None
    assert not owner.get("sell_claim_judgment_absent")
    assert owner["holding_period_years"] is not None
    assert owner["holding_period_years"] >= 10  # 2005→2024 ≈ 18.8년
    assert owner["holding_period_basis"] == "2024-01-01", "기준일이 응답에 그대로 실리지 않았다"
    assert owner["inheritance"]["status"] == "비상속", "취득원인 '매매'가 상속으로 오판별됐다"
    assert owner["inheritance"]["cause_raw"] == "매매", "판정 근거(취득원인 원문)가 응답에서 빠졌다"


# ── 제약3: 상속 판별 불가/상속 시 합산 여부 "미확인" ────────────────────

@pytest.mark.asyncio
async def test_상속_판별_불가시_미확인을_낸다(monkeypatch: pytest.MonkeyPatch) -> None:
    owners = [_owner("이영희", "단독", "2018-01-01", None)]  # 취득원인 미기재
    _install_fake_registry_analysis(monkeypatch, {"서울시 B": _ok_analysis(owners)})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 B"}], district_plan_decision_date="2024-01-01", scheme=_HOUSING_SCHEME
    )
    owner = out["cards"][0]["owners"][0]
    assert owner["inheritance"]["status"] == "판별 불가"
    assert owner["inheritance"]["cause_raw"] is None, "취득원인 미기재(None)가 응답에서 다른 값으로 바뀌었다"
    assert "미확인" in owner["inheritance_aggregation_note"], (
        f"판별 불가인데 합산 여부를 확정처럼 냈다: {owner}"
    )
    assert "기재 없음" in owner["evidence"], "취득원인 미기재가 근거 스니펫에 반영되지 않았다"
    assert out["summary"]["owners_inheritance_aggregation_unconfirmed"] == 1


@pytest.mark.asyncio
async def test_상속으로_판별돼도_합산값을_확정처럼_내지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★취득원인이 명시적으로 '상속'이어도, 피상속인 원취득일이 없으면 합산 못 한다 —
    그 사실을 숨기지 않고 '미확인'으로 낸다(합산 안 한 값을 확정처럼 내는 것 금지)."""
    owners = [_owner("박민수", "단독", "2015-06-01", "상속")]
    _install_fake_registry_analysis(monkeypatch, {"서울시 C": _ok_analysis(owners)})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 C"}], district_plan_decision_date="2024-01-01", scheme=_HOUSING_SCHEME
    )
    owner = out["cards"][0]["owners"][0]
    assert owner["inheritance"]["status"] == "상속"
    assert owner["inheritance"]["cause_raw"] == "상속"
    assert "미확인" in owner["inheritance_aggregation_note"]
    # 두 모집단이 실제로 다른 문구를 낸다(차가 0이면 잠금이 아니다).
    assert owner["inheritance_aggregation_note"] != _owner_note_for_non_inherit()


def _owner_note_for_non_inherit() -> str:
    return "상속에 의한 취득으로 보이지 않아 피상속인 보유기간 합산 대상이 아닙니다."


@pytest.mark.asyncio
async def test_취득일이_인식되지_않으면_보유기간_대신_판정보류를_낸다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """기준일은 있어도, 등기부 취득일 표기가 인식 불가한 문자열이면(공란이 아니어도)
    보유기간을 임의로 추정하지 않고 판정을 보류한다."""
    owners = [_owner("취득일불명자", "단독", "확인불가(등기부 훼손)", "매매")]
    _install_fake_registry_analysis(monkeypatch, {"서울시 F": _ok_analysis(owners)})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 F"}], district_plan_decision_date="2024-01-01", scheme=_HOUSING_SCHEME
    )
    owner = out["cards"][0]["owners"][0]
    assert owner["sell_claim_judgment"] is None
    assert owner["sell_claim_judgment_absent"] == SOURCE_UNAVAILABLE
    assert owner["holding_period_years"] is None
    assert owner["holding_period_basis"] == "2024-01-01", (
        "취득일 인식 실패와 무관하게 기준일 자체는 응답에 남아야 한다"
    )
    assert "취득일" in owner["sell_claim_reason"] and "인식" in owner["sell_claim_reason"]


# ── 제약1: 공유필지는 소유자별로 갈린다 ──────────────────────────────────

@pytest.mark.asyncio
async def test_공유필지가_소유자별로_갈린_결과를_낸다(monkeypatch: pytest.MonkeyPatch) -> None:
    owners = [
        _owner("장기보유자", "1/2", "2005-03-02", "매매"),   # ~18.8년 → 장기보유
        _owner("최근취득자", "1/2", "2021-06-01", "매매"),   # ~2.6년 → 단기
    ]
    _install_fake_registry_analysis(monkeypatch, {"서울시 D": _ok_analysis(owners)})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 D"}], district_plan_decision_date="2024-01-01", scheme=_HOUSING_SCHEME
    )
    card = out["cards"][0]
    assert len(card["owners"]) == 2, "공유필지인데 소유자가 하나로 뭉개졌다"

    by_name = {o["owner"]: o for o in card["owners"]}
    long_term = by_name["장기보유자"]
    short_term = by_name["최근취득자"]

    assert long_term["share"] == "1/2"
    assert short_term["share"] == "1/2"
    assert long_term["sell_claim_judgment"] != short_term["sell_claim_judgment"], (
        "소유자별 판정이라면서 두 소유자가 같은 결과를 낸다 — 차가 0이면 소유자별 분리가 아니다"
    )
    assert long_term["holding_period_years"] >= 10
    assert short_term["holding_period_years"] < 10
    assert out["summary"]["owners_long_term_holders"] == 1
    assert out["summary"]["owners_total"] == 2


# ── 제약5: 부분 실패 허용 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_한_필지_실패가_전체를_죽이지_않고_사유가_남는다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owners = [_owner("정상소유자", "단독", "2010-01-01", "매매")]
    _install_fake_registry_analysis(
        monkeypatch,
        {
            "실패필지": RuntimeError("CODEF 타임아웃(외부 API 오류)"),
            "정상필지": _ok_analysis(owners),
        },
    )

    out = await svc.survey_selected_parcels(
        [{"address": "실패필지"}, {"address": "정상필지"}],
        district_plan_decision_date="2024-01-01", scheme=_HOUSING_SCHEME,
    )

    assert out["parcel_count"] == 2, "실패 필지가 전체 응답에서 조용히 빠졌다"
    assert len(out["cards"]) == 2

    failed_card = next(c for c in out["cards"] if c["address"] == "실패필지")
    ok_card = next(c for c in out["cards"] if c["address"] == "정상필지")

    assert failed_card["status"] == "error"
    assert failed_card["message"], "실패 사유가 비어 있다 — 조용히 비운 것과 같다"
    assert "타임아웃" in failed_card["message"] or "오류" in failed_card["message"]
    assert failed_card["owners"] == []

    # ★부분 실패가 다른 필지의 정상 처리를 막지 않는다.
    assert ok_card["status"] == "ok"
    assert len(ok_card["owners"]) == 1
    assert out["summary"]["parcels_failed"] == 1
    assert out["summary"]["parcels_ok"] == 1


@pytest.mark.asyncio
async def test_등기부_미확보_필지도_사유를_남기고_계속된다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """예외가 아니라 `status="not_available"`(등기부 데이터 미확보)로 정상 반환되는
    경우도 조용히 빈 카드가 되지 않고 사유가 남아야 한다."""
    _install_fake_registry_analysis(
        monkeypatch,
        {"등기없음": {"status": "not_available", "origin": "none", "land": {},
                     "message": "등기부 데이터를 가져오지 못했습니다.", "ai": None}},
    )

    out = await svc.survey_selected_parcels(
        [{"address": "등기없음"}], district_plan_decision_date="2024-01-01", scheme=_HOUSING_SCHEME
    )
    card = out["cards"][0]
    assert card["status"] == "not_available"
    assert card["message"]
    assert card["owners"] == []


# ── 제약4: 근거 스니펫 없는 판정을 만들지 않는다 ─────────────────────────

@pytest.mark.asyncio
async def test_근거_스니펫_없는_판정을_만들지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    owners = [
        _owner("스니펫검증A", "1/2", "2005-03-02", "매매"),
        _owner("스니펫검증B", "1/2", None, "상속"),  # 취득일 미기재(판정 보류 경로)도 포함
    ]
    _install_fake_registry_analysis(monkeypatch, {"서울시 E": _ok_analysis(owners)})

    # 기준일 있는 케이스 + 없는 케이스 둘 다 확인 — 판정을 '안 내는' 경로도 evidence는 있어야 한다.
    with_date = await svc.survey_selected_parcels(
        [{"address": "서울시 E"}], district_plan_decision_date="2024-01-01", scheme=_HOUSING_SCHEME
    )
    without_date = await svc.survey_selected_parcels(
        [{"address": "서울시 E"}], district_plan_decision_date=None, scheme=_HOUSING_SCHEME
    )

    for out in (with_date, without_date):
        for card in out["cards"]:
            for owner in card["owners"]:
                assert owner.get("evidence"), f"근거 스니펫 없는 판정이 나왔다: {owner}"
                assert owner["owner"] in owner["evidence"], "근거 스니펫이 해당 소유자를 특정하지 않는다"

    # 취득일 미기재(스니펫검증B)는 근거 스니펫에 '기재 없음'이 그대로 드러나야 한다 —
    # 조용히 다른 문자열로 대체되면 사후 검증이 불가능해진다.
    b_evidence = next(
        o["evidence"] for o in with_date["cards"][0]["owners"] if o["owner"] == "스니펫검증B"
    )
    assert "기재 없음" in b_evidence, f"취득일 미기재가 근거 스니펫에 반영되지 않았다: {b_evidence}"


# ── P1.5 상속 보유기간 합산 (주택법 §22①2호) ────────────────────────────
# ★법령이 **합산하라**고 정하는데 합산하지 않으면, 상속 필지가 "보유 3년"으로 보여
#   **매도청구 가능으로 오분류**된다. 실무에서 그대로 사고가 된다.

from datetime import date as _date  # noqa: E402

from app.services.land_intelligence import parcel_rights_survey_service as _svc  # noqa: E402
from apps.api.app.utils.withheld import (
    AWAITING_INPUT,
    NOT_APPLICABLE,
    SOURCE_UNAVAILABLE,
)


def _heir_owner(name: str, acq: str, cause: str) -> dict:
    return {"name": name, "share": "1/1", "acquisition_date": acq, "acquisition_cause": cause}


def test_상속이면_피상속인_취득일을_실제로_합산한다() -> None:
    """★합산 전 3년 → 합산 후 23년. 판정이 '가능'에서 '불가'로 **뒤집혀야** 한다."""
    owner = _heir_owner("김상속", "2023-01-01", "상속")
    history = [
        {"date": "2003-01-01", "cause": "매매", "owner": "김부친"},
        {"date": "2023-01-01", "cause": "상속", "owner": "김상속", "predecessor": "김부친"},
    ]
    base = _date(2026, 1, 1)

    without = _svc._judge_owner(owner, base, None, _HOUSING_SCHEME)
    with_hist = _svc._judge_owner(owner, base, history, _HOUSING_SCHEME)

    assert without["holding_period_years"] < 10, "대조군이 대조군이 아니다(합산 없이도 10년 초과)"
    assert without["sell_claim_judgment"].startswith("가능")
    # ★합산되면 20년 이상이 되어 판정이 뒤집힌다
    assert with_hist["inheritance_aggregated"] is True
    assert with_hist["holding_period_years"] > 20, f"합산되지 않았다: {with_hist}"
    assert with_hist["sell_claim_judgment"].startswith("불가"), (
        "합산했는데 매도청구 '가능'으로 남아 있다 — 상속 필지가 오분류된다"
    )


def test_합산에_성공하면_더는_미확인이라_말하지_않는다() -> None:
    """★정직 표기의 **반대 방향 오류**: 확정했는데 '미확인'이라 하면 사용자가 신뢰하지 못한다."""
    owner = _heir_owner("김상속", "2023-01-01", "상속")
    history = [
        {"date": "2003-01-01", "cause": "매매", "owner": "김부친"},
        {"date": "2023-01-01", "cause": "상속", "owner": "김상속"},
    ]
    out = _svc._judge_owner(owner, _date(2026, 1, 1), history, _HOUSING_SCHEME)
    assert "미확인" not in out["inheritance_aggregation_note"]
    assert "합산" in out["inheritance_aggregation_note"]
    assert "합산 미반영" not in out["sell_claim_reason"]


def test_이력에_피상속인이_없으면_추정하지_않는다() -> None:
    """★없는 것을 만들지 않는다 — 이력의 **최초** 등기면 앞선 소유자가 없다."""
    owner = _heir_owner("김상속", "2003-01-01", "상속")
    history = [{"date": "2003-01-01", "cause": "상속", "owner": "김상속"}]
    out = _svc._judge_owner(owner, _date(2026, 1, 1), history, _HOUSING_SCHEME)
    assert out["inheritance_aggregated"] is False
    assert "미확인" in out["inheritance_aggregation_note"]


def test_합산_근거를_함께_낸다() -> None:
    """★합산은 판정을 뒤집는다 — 근거 없이 뒤집으면 사후 검증이 불가능하다."""
    owner = _heir_owner("김상속", "2023-01-01", "상속")
    history = [
        {"date": "2003-01-01", "cause": "매매", "owner": "김부친"},
        {"date": "2023-01-01", "cause": "상속", "owner": "김상속"},
    ]
    out = _svc._judge_owner(owner, _date(2026, 1, 1), history, _HOUSING_SCHEME)
    ev = out["predecessor_evidence"]
    assert ev and ev.get("owner") == "김부친", f"합산 근거(피상속인 등기 항목)가 없다: {ev}"


def test_상속이_아니면_합산하지_않는다() -> None:
    """★매매 취득에 합산하면 **보유기간이 부풀려져** 매도청구 가능한 필지를 불가로 오분류한다."""
    owner = _heir_owner("이매수", "2023-01-01", "매매")
    history = [
        {"date": "2003-01-01", "cause": "매매", "owner": "박전소유"},
        {"date": "2023-01-01", "cause": "매매", "owner": "이매수"},
    ]
    out = _svc._judge_owner(owner, _date(2026, 1, 1), history, _HOUSING_SCHEME)
    assert out["inheritance_aggregated"] is False
    assert out["holding_period_years"] < 10, "매매인데 합산됐다 — 반대 방향 오분류"


@pytest.mark.asyncio
async def test_조립경로에서_이력이_판정까지_전달된다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★배선 락 — `_judge_owner` 를 **직접** 부르는 테스트만 두면, 조립부에서 이력 전달을
    끊어도(`_judge_owner(o, date, None)`) 전부 초록이다. **실제로 그 변이가 생존했다.**

    ★그래서 여기서는 `survey_selected_parcels`(응답 표면)로 태운다 —
      등기분석 결과의 `ownership.ownership_history` 가 최종 판정을 **뒤집는지** 확인한다.
    """
    owners = [_owner("김상속", "1/1", "2023-01-01", "상속")]
    analysis = _ok_analysis(owners)
    # 피상속인이 2003년에 취득 → 합산하면 20년 이상 → 매도청구 '불가'로 뒤집혀야 한다
    analysis["ai"]["ownership"]["ownership_history"] = [
        {"date": "2003-01-01", "cause": "매매", "owner": "김부친"},
        {"date": "2023-01-01", "cause": "상속", "owner": "김상속", "predecessor": "김부친"},
    ]
    _install_fake_registry_analysis(monkeypatch, {"서울시 H": analysis})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 H"}], district_plan_decision_date="2026-01-01", scheme=_HOUSING_SCHEME
    )
    owner_row = out["cards"][0]["owners"][0]

    assert owner_row["inheritance_aggregated"] is True, (
        "조립 경로에서 이력이 판정까지 전달되지 않았다 — 상속 필지가 오분류된다"
    )
    assert owner_row["holding_period_years"] > 20
    assert owner_row["sell_claim_judgment"].startswith("불가")
    assert (owner_row.get("predecessor_evidence") or {}).get("owner") == "김부친"


@pytest.mark.asyncio
async def test_이력이_없으면_조립경로에서도_미확인으로_남는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★대조군 — 이력이 없을 때는 합산하지 않아야 한다(위 테스트가 '항상 참'이 되지 않게)."""
    owners = [_owner("김상속", "1/1", "2023-01-01", "상속")]
    _install_fake_registry_analysis(monkeypatch, {"서울시 I": _ok_analysis(owners)})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 I"}], district_plan_decision_date="2026-01-01", scheme=_HOUSING_SCHEME
    )
    owner_row = out["cards"][0]["owners"][0]
    assert owner_row["inheritance_aggregated"] is False
    assert "미확인" in owner_row["inheritance_aggregation_note"]


# ── ★사업방식 게이트(2026-08-15 B2 수정) ────────────────────────────────
# 주택법 §22①2호의 10년 요건은 **주택법 계열에만** 있다. 소규모정비특례법 §35·도정법 §64 는
# 동의율 기반이라 보유기간 조건이 없고, 도시개발법 §22 는 매도청구가 아니라 **수용**이다.
# 종전 코드는 이 구분 없이 모든 방식에 10년 규칙을 적용했다 — 법적 오분류였다.

@pytest.mark.asyncio
async def test_같은_필지가_사업방식에_따라_다른_판정을_낸다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★★두 모집단을 가른다 — **같은 소유자·같은 기준일**인데 사업방식만 바꾼다.
    두 결과가 같다면 `scheme` 인자는 장식이고, 게이트를 지워도 아무도 모른다."""
    owners = [_owner("장기보유자", "단독", "2005-03-02", "매매")]  # 결정고시일 기준 ~18.8년
    _install_fake_registry_analysis(
        monkeypatch, {"서울시 G": _ok_analysis(owners)}
    )

    housing = await svc.survey_selected_parcels(
        [{"address": "서울시 G"}], district_plan_decision_date="2024-01-01", scheme=_HOUSING_SCHEME
    )
    consent = await svc.survey_selected_parcels(
        [{"address": "서울시 G"}], district_plan_decision_date="2024-01-01", scheme=_CONSENT_SCHEME
    )

    h = housing["cards"][0]["owners"][0]
    c = consent["cards"][0]["owners"][0]

    assert h["sell_claim_judgment"] == "불가(장기보유 추정)"
    assert c["sell_claim_judgment"] is None
    assert c["sell_claim_judgment_absent"] == NOT_APPLICABLE
    assert h["sell_claim_judgment"] != c["sell_claim_judgment"], (
        "사업방식이 판정을 가르지 않는다 — scheme 인자가 장식이다"
    )
    # ★동의율 기반 방식에서는 보유기간을 **계산조차 하지 않는다**(있으면 오해를 부른다).
    assert c["holding_period_years"] is None, f"보유기간 요건이 없는 방식에서 연수를 냈다: {c}"
    assert h["holding_period_years"] is not None
    # ★사유는 실제 근거법령을 이름으로 밝힌다(주택법 하드코딩 금지).
    assert "소규모정비특례법" in c["sell_claim_reason"], c["sell_claim_reason"]
    assert c["governing_act"] == "소규모정비특례법"
    assert h["governing_act"] == "주택법"
    assert consent["summary"]["owners_holding_period_out_of_scope"] == 1
    assert housing["summary"]["owners_holding_period_out_of_scope"] == 0


@pytest.mark.asyncio
async def test_사업방식_미지정이면_보유기간을_계산하지_않는다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★기본값을 몰래 넣지 않는다 — 방식이 없으면 어느 법령의 요건인지 알 수 없다."""
    owners = [_owner("장기보유자", "단독", "2005-03-02", "매매")]
    _install_fake_registry_analysis(monkeypatch, {"서울시 J": _ok_analysis(owners)})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 J"}], district_plan_decision_date="2024-01-01", scheme=None
    )
    o = out["cards"][0]["owners"][0]
    assert o["sell_claim_judgment"] is None and o["sell_claim_judgment_absent"] == NOT_APPLICABLE
    assert o["holding_period_years"] is None
    assert "사업방식" in o["sell_claim_reason"]


@pytest.mark.asyncio
async def test_도시개발사업은_수단이_수용으로_실린다(monkeypatch: pytest.MonkeyPatch) -> None:
    """★도시개발법 §22 는 매도청구가 아니라 **수용**(토지보상법 준용)이다 — 절차가 다르다."""
    owners = [_owner("소유자", "단독", "2005-03-02", "매매")]
    _install_fake_registry_analysis(monkeypatch, {"서울시 K": _ok_analysis(owners)})

    out = await svc.survey_selected_parcels(
        [{"address": "서울시 K"}],
        district_plan_decision_date="2024-01-01",
        scheme="도시개발사업(도시개발법)",
    )
    assert out["instrument"] == "수용"
    assert out["governing_act"] == "도시개발법"
    assert out["cards"][0]["owners"][0]["instrument"] == "수용"


def test_역세권_활성화사업은_근거법령을_추론하지_않는다() -> None:
    """★basis 문자열에 '주택법'이 있다고 주택법으로 단정하면 안 된다 — 같은 문장이
    '사업방식에 따라 정비/소규모정비 준용'이라 적는다(문자열 추론이 틀리는 실증)."""
    from app.services.development.scenario_simulator import MAGDO_RULES

    rule = MAGDO_RULES["역세권 활성화사업"]
    assert "주택법" in rule["basis"], "전제가 깨졌다 — basis 에 주택법이 없으면 이 테스트는 공허하다"
    assert rule["governing_act"] is None, "모호한 방식에 근거법령을 단정했다"
    assert rule["requires_track_input"] is True

    out = svc._judge_owner(
        {"name": "소유자", "share": "단독", "acquisition_date": "2005-03-02",
         "acquisition_cause": "매매"},
        _date(2024, 1, 1),
        None,
        "역세권 활성화사업",
    )
    assert out["sell_claim_judgment"] is None and out["sell_claim_judgment_absent"] == NOT_APPLICABLE
    assert out["holding_period_years"] is None
