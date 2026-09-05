"""정밀도 등급이 **하류까지 간다** — R1-b 의존 게이트 (2026-08-23).

## 무엇을 막는가 (실측)

`#770` 이 개략수지 페이로드에 정밀도 등급(E)을 붙였다. 그런데 실측하니 그 등급은
**두 경계에서 사라졌다**:

    rough_scenario_report.py   "개략수지 → 시니어 최종 사업성분석 보고서"  precision 0건
    ai/assistant_agent.py      AI 비서가 LLM 에 넘기는 수지 요약           등급 없음

앞엣것의 부제는 **"은행/투자자 제출용"** 이고 첫 화면이 `사업성 등급 F` 다.
뒤엣것은 그 숫자를 곧바로 LLM 입력으로 준다 — 등급 없이 주면
*"등급 F 이나 831.5억의 개발이익이 예상되며…"* 같은 문장이 나온다.
**전제가 갈린 채 종합을 얹으면 거짓말이 더 설득력 있어진다.**

그리고 `quality/precision.lowest()` 는 모듈 자신이 *"이 함수가 이 모듈의 존재 이유다"* 라고
써 놓았는데 **소비처가 0** 이었다(이 저장소가 반복해 데인 "정의만 하고 소비처 0").

## 이 파일이 잠그는 것

1. 세 입력(연면적·토지비·분양단가)의 **최저**를 따른다 — `lowest()` 의 첫 실사용
2. **모르면 모른다** — 하나라도 등급 미상이면 합성 결과도 None(낙관적으로 채우지 않는다)
3. 보고서 Executive Summary 가 **등급 배지 바로 옆**에서 정밀도를 고지한다
4. AI 비서 도구 출력이 등급 + **"확정치처럼 답하지 말라"는 지시**를 함께 넘긴다
5. 대조군 — 상태가 다르면 **결과도 달라야** 한다(어느 입력이든 같은 답이면 락이 공허하다)

## 변이 검증 후 남은 생존 — **설명 가능**하므로 여기 적어 둔다(점수 부풀리기 방지)

  · `elif r.get("precision") is None:` 의 키 문자열 변경 — **등가 변이**다.
    키를 바꾸면 `.get` 이 `None` 을 돌려주고 `is None` 이 참이 되어 **같은 분기**를 탄다.
  · `else "정밀도 판정 불가"` — **도달 불가 방어**(코드에도 적어 뒀다).
    `lowest` 는 입력에 `None` 이 있을 때만 `None` 을 돌려주므로 `unknown` 이 반드시 비지 않는다.
  · `elif composed is gfa_precision and gfa_basis:` 조건 무력화 — 어느 쪽으로 가도
    **유효한 근거 문구**가 나온다(연면적도 구속조건이므로 그 근거가 틀리지 않다).
  · 보고서 고지문의 긴 문자열 일부 변경 — 단언이 그 문장의 **핵심 구절**을 보므로
    다른 부분을 바꾼 변이는 살아남는다. 문장 전체를 못박으면 문구 다듬기마다 빨강이 된다.

변이 **95 kill / 6 생존**(초판 62/44 → 이 파일의 락을 보강한 결과).
"""

from __future__ import annotations

import pytest

from app.services.feasibility.rough_feasibility_orchestrator import (
    compose_scenario_precision,
)
from app.services.quality.precision import PrecisionGrade

E = PrecisionGrade.ESTIMATED
V = PrecisionGrade.VERIFIED


def _compose(**kw):
    base = dict(
        gfa_precision=E,
        gfa_basis="대지면적 3,836㎡ × 실효용적률 200% — 설계 미반영(개략)",
        land_total=1_000_000_000,
        land_price_reliable=True,
        price_pp=12_000_000,
        price_source="주변 실거래(MOLIT)",
    )
    base.update(kw)
    return compose_scenario_precision(**base)


# ── 1) 최저를 따른다 ────────────────────────────────────────────────────────
def test_세_입력의_최저를_따른다_연면적이_개략이면_전체가_개략() -> None:
    """토지비·분양단가가 확인됨(V)이어도 연면적이 개략(E)이면 산출물은 개략이다.

    ★계산이 정교해져도 등급은 오르지 않는다 — 올릴 수 있는 것은 **더 나은 입력**뿐이다.
    """
    grade, basis, inputs = _compose()
    assert grade is E
    assert inputs == {"gfa": "E", "land_cost": "V", "sale_price": "V"}
    assert "설계 미반영" in basis


def test_토지비가_가정치면_그_사유가_근거에_남는다() -> None:
    """연면적이 설계기반(D)이어도 토지비가 가정치(E)면 전체는 E 이고, **왜**인지 말한다."""
    grade, basis, inputs = _compose(
        gfa_precision=PrecisionGrade.DESIGNED, gfa_basis="", land_price_reliable=False,
    )
    assert grade is E
    assert inputs["land_cost"] == "E"
    assert "토지비" in basis


def test_분양단가_지역시세표는_실거래가_아니므로_개략이다() -> None:
    """★source 문자열의 '추정' 이 판정 근거다 — 지역 시세표는 실거래가 아니다."""
    grade, _basis, inputs = _compose(
        gfa_precision=V, gfa_basis="",
        price_source="지역 시세 테이블(national_default·추정·비실거래)",
    )
    assert inputs["sale_price"] == "E"
    assert grade is E


# ── 2) 모르면 모른다 ────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    ("kw", "unknown_ko"),
    [
        ({"gfa_precision": None}, "연면적"),
        ({"land_total": None}, "토지비"),
        ({"price_pp": None}, "분양단가"),
        ({"price_source": "unavailable"}, "분양단가"),
    ],
)
def test_하나라도_등급을_모르면_결과도_모른다(kw, unknown_ko) -> None:
    """★낙관적으로 채우면 그것이 정밀도 위장의 시작이다.

    그리고 **어느 입력을 모르는지** 이름으로 말한다 — 모른다는 사실도 정보다.
    """
    grade, basis, _inputs = _compose(**kw)
    assert grade is None
    assert unknown_ko in basis
    assert "판정할 수 없습니다" in basis


def test_대조군_입력이_달라지면_결과도_달라진다() -> None:
    """★어느 입력이든 같은 답을 내는 판별기는 초록이어도 아무것도 잠그지 않는다."""
    all_verified = _compose(gfa_precision=V, gfa_basis="")[0]
    with_estimate = _compose()[0]
    with_unknown = _compose(land_total=None)[0]
    assert len({all_verified, with_estimate, with_unknown}) == 3


# ── 3) 보고서 경계 ──────────────────────────────────────────────────────────
def _scenario(precision: str | None, label: str, basis: str = "근거문구") -> dict:
    return {
        "address": "충청남도 천안시 동남구 모산동 123-1",
        "inputs": {"dev_type_name": "공동주택", "zone_type": "제1종일반주거지역"},
        "summary": {"grade": "F", "total_cost_won": 415_770_000_000},
        "degraded_notes": [],
        "precision": precision,
        "precision_label": label,
        "precision_basis": basis,
        "precision_inputs": {"gfa": precision, "land_cost": "V", "sale_price": "V"},
    }


def _exec_text(scenario: dict) -> str:
    from app.services.feasibility.rough_scenario_report import (
        build_rough_scenario_report_model,
    )

    model = build_rough_scenario_report_model(scenario)
    assert model.exec_summary is not None, "Executive Summary 가 없다 — 검사 대상이 없는 초록"
    parts: list[str] = []
    for b in model.exec_summary.blocks:
        parts.append(str(getattr(b, "title", "") or ""))
        parts.extend(str(x) for x in (getattr(b, "paragraphs", None) or []))
        parts.append(str(getattr(b, "label", "") or ""))
    return "\n".join(parts)


def test_보고서_요약이_등급_배지_옆에서_개략임을_고지한다() -> None:
    """★부제가 '은행/투자자 제출용' 이고 첫 화면이 '사업성 등급 F' 다.

    그 등급이 **설계 없이 만든 개략치**에서 나왔다는 사실이 같은 자리에 없으면
    읽는 사람은 확정 판정으로 받아들인다.
    """
    text = _exec_text(_scenario("E", "개략(추정)"))
    # 전제 가드 — 등급 배지가 실제로 있어야 이 단언이 의미를 갖는다.
    assert "사업성 등급 F" in text, "등급 배지가 없다 — 공허한 초록"
    assert "정밀도 고지" in text
    assert "개략(추정)" in text
    assert "확정 판단의 근거가 될 수 없습니다" in text


def test_등급을_판정할_수_없어도_침묵하지_않는다() -> None:
    """★침묵하면 읽는 사람은 확정치로 읽는다 — '모른다'도 반드시 말한다."""
    text = _exec_text(_scenario(None, "정밀도 미표기"))
    assert "정밀도 고지" in text
    assert "판정할 수 없습니다" in text
    assert "확정치로 읽지 마십시오" in text


def test_대조군_정밀도_키가_없으면_고지_블록도_없다() -> None:
    """★'무엇이든 붙이는' 블록이면 락이 공허하다 — 등급 정보가 없을 때는 붙지 않아야 한다."""
    s = _scenario("E", "개략(추정)")
    s.pop("precision_label")
    text = _exec_text(s)
    assert "사업성 등급 F" in text  # 대상은 여전히 존재
    assert "정밀도 고지" not in text


# ── 4) AI 비서 경계 — ★R3(LLM 종합) 실패를 미리 막는 지점 ────────────────────
@pytest.mark.asyncio
async def test_AI비서_도구가_등급과_지시를_함께_LLM에_넘긴다(monkeypatch) -> None:
    """★이 도구의 반환값은 곧바로 LLM 의 입력이 된다.

    등급 없이 총사업비·순이익·등급만 넘기면 LLM 은 그것을 매끄러운 문장으로 만든다 —
    *"등급 F 이나 831.5억의 개발이익이 예상되며…"*. **전제가 갈린 채 종합을 얹으면
    거짓말이 더 설득력 있어진다.**

    등급만 주는 것으로는 부족하다 — LLM 이 언급하지 않고 넘어갈 수 있으므로
    **"확정치처럼 답하지 말라"는 지시**까지 함께 넘긴다.
    """
    import app.services.feasibility.rough_feasibility_orchestrator as orch
    from app.services.ai.assistant_agent import rough_feasibility

    async def _fake(**_kw):
        return {
            "scenario_status": "actual",
            "inputs": {"dev_type_name": "공동주택", "gfa_sqm": 131858},
            "summary": {"total_cost_won": 415_770_000_000, "grade": "F"},
            "degraded_notes": [],
            "precision": "E",
            "precision_label": "개략(추정)",
            "precision_basis": "대지면적 × 실효용적률 — 설계 미반영(개략)",
        }

    monkeypatch.setattr(orch, "build_rough_scenario", _fake)
    out = await rough_feasibility.ainvoke({"address": "충청남도 천안시 동남구 모산동 123-1"})

    # 전제 가드 — 수치가 실제로 실려야 이 단언이 의미를 갖는다(대상 0개 통과 방지).
    assert "총사업비" in out and "등급: F" in out, "수지 요약이 비었다 — 공허한 초록"
    assert "[정밀도] 개략(추정)" in out
    assert "설계 미반영" in out
    # ★지시가 없으면 LLM 이 등급을 흘려보낸다.
    assert "확정치처럼 답하지 말고" in out


@pytest.mark.asyncio
async def test_대조군_등급이_없는_응답에는_정밀도_줄이_붙지_않는다(monkeypatch) -> None:
    """★'무엇이든 붙이는' 처리면 락이 공허하다 — 등급 정보가 없으면 지어내지 않는다."""
    import app.services.feasibility.rough_feasibility_orchestrator as orch
    from app.services.ai.assistant_agent import rough_feasibility

    async def _fake(**_kw):
        return {
            "scenario_status": "actual",
            "inputs": {"dev_type_name": "공동주택"},
            "summary": {"total_cost_won": 1, "grade": "F"},
            "degraded_notes": [],
        }

    monkeypatch.setattr(orch, "build_rough_scenario", _fake)
    out = await rough_feasibility.ainvoke({"address": "주소"})
    assert "등급: F" in out
    assert "[정밀도]" not in out


# ── 5) 보고서 본문 세부 — 근거·입력별 등급이 실제로 렌더된다 ────────────────
def test_보고서_고지가_근거와_입력별_등급을_함께_보여준다() -> None:
    """★합성 결과만 보여 주면 **무엇 때문에 낮아졌는지**를 읽는 사람이 알 수 없다.

    변이 검증에서 `근거:`·`입력별 정밀도:` 줄을 지워도 살아남았다 — 픽스처에 그 값을
    넣어 두고도 **단언하지 않았기 때문**이다. 넣은 값은 반드시 확인한다.
    """
    s = _scenario("E", "개략(추정)", basis="대지면적 × 실효용적률 — 설계 미반영(개략)")
    s["precision_inputs"] = {"gfa": "E", "land_cost": "V", "sale_price": None}
    text = _exec_text(s)
    assert "근거: 대지면적 × 실효용적률 — 설계 미반영(개략)" in text
    assert "입력별 정밀도:" in text
    assert "연면적 개략(추정)" in text
    assert "토지비 확인됨" in text
    # ★None 은 "미표기"로 **말한다** — 빈칸으로 두면 읽는 사람이 확인된 것으로 오해한다.
    assert "분양단가 미표기" in text


# ── 6) 보고서 JSON 경계 — 구조화 소비처도 등급 없이 숫자만 받지 않는다 ──────
@pytest.mark.asyncio
async def test_보고서_JSON에_정밀도_블록이_동봉된다() -> None:
    """★프론트·다른 보고서가 이 JSON 을 먹는다. 여기서 등급이 빠지면
    같은 수치가 화면에선 '개략', 보고서에선 확정으로 읽힌다."""
    from app.services.feasibility.rough_scenario_report import (
        generate_rough_scenario_report,
    )

    s = _scenario("E", "개략(추정)")
    j = await generate_rough_scenario_report(s, use_llm=False, format="json")
    assert isinstance(j, dict)
    # 전제 가드 — 보고서가 실제로 만들어졌는지 먼저 확인(대상 0개 통과 방지).
    assert j.get("summary"), "보고서 JSON 이 비었다 — 공허한 초록"
    assert j["precision"]["grade"] == "E"
    assert j["precision"]["label"] == "개략(추정)"
    assert j["precision"]["inputs"]["gfa"] == "E"


# ── 7) ★페이로드 배선 — 개략수지 응답이 실제로 등급을 싣는가(끝까지 태운다) ──
def _stub_orchestrator(monkeypatch, *, far: float | None, price_source: str):
    """`build_rough_scenario` 를 네트워크 없이 완주시키는 최소 스텁.

    ★소스 grep 으로 "precision 키가 있다"를 확인하면 **주석·문자열에 뚫린다**.
    실제로 함수를 태워 **반환 dict** 를 본다.
    """
    import app.services.feasibility.rough_feasibility_orchestrator as orch
    from app.services.feasibility.modules.base_module import ModuleInput

    land_area = 1000.0
    gfa = land_area * (far or 200.0) / 100.0
    rec = {
        "development_type": "M06",
        "type_name": "일반분양",
        "feasibility": {"total_cost_won": 1, "total_revenue_won": 1, "net_profit_won": 0},
        "unit_summary": {"total_gfa_sqm": gfa, "total_households": 1, "avg_area_pyeong": 34.0},
        "input_used": ModuleInput(
            development_type="M06", total_land_area_sqm=land_area,
            official_price_per_sqm=3_000_000, price_multiplier=1.1,
            total_gfa_sqm=gfa, total_households=1, avg_sale_price_per_pyeong=15_000_000,
            avg_area_pyeong=34.0, sale_ratio=0.95, equity_won=10_000_000_000,
        ),
        "composite_score": 80.0,
    }

    async def _fake_integrated(parcels):
        return None

    async def _fake_auto(**_kw):
        return {
            "address": "정밀도-QA", "zone_type": "제1종일반주거지역",
            "land_area_sqm": land_area, "effective_far_pct": far,
            "recommendations": [rec], "all_results": [rec],
            "land_price_reliable": True, "area_reliable": True, "scenario_status": "actual",
        }

    async def _fake_desk(**kw):
        return {"ok": True, "appraised_price_per_sqm": 5_000_000,
                "appraised_total_won": int(5_000_000 * (kw.get("area_sqm") or 0)),
                "evidence": None, "source": "NED 토지특성", "confidence": 0.8}

    async def _fake_price(*, db, site_id, dev_type, region, address, **kw):
        return 40_000_000, price_source, "테스트 분양단가", None

    def _fake_ratios(input_used):
        return 0.08, 0.04, None

    monkeypatch.setattr(orch, "build_integrated_context", _fake_integrated)
    monkeypatch.setattr(orch, "_auto_recommend", _fake_auto)
    monkeypatch.setattr(orch, "desk_appraisal", _fake_desk)
    monkeypatch.setattr(orch, "_resolve_sale_price_per_pyeong", _fake_price)
    monkeypatch.setattr(orch, "_engine_cost_ratios", _fake_ratios)
    return orch


@pytest.mark.asyncio
async def test_개략수지_응답이_합성_등급을_싣는다(monkeypatch) -> None:
    """연면적 개략(E) + 분양단가 지역시세표(추정=E) → 응답 전체가 개략(E)."""
    orch = _stub_orchestrator(
        monkeypatch, far=200.0, price_source="지역 시세 테이블(sigungu·추정·비실거래)")
    out = await orch.build_rough_scenario(address="정밀도-QA")

    assert out["inputs"]["gfa_sqm"] is not None, "GFA 미산출 — 검사 대상이 없는 초록"
    assert out["precision"] == "E"
    assert out["precision_label"] == "개략(추정)"
    assert out["precision_inputs"]["gfa"] == "E"
    assert out["precision_inputs"]["land_cost"] == "V"
    # ★지역 시세표는 실거래가 아니다 — source 의 '추정' 표식으로 판정한다.
    assert out["precision_inputs"]["sale_price"] == "E"


@pytest.mark.asyncio
async def test_연면적을_못_구하면_응답_등급도_미표기다(monkeypatch) -> None:
    """★대조군 — 같은 경로가 **다른 답**을 내야 배선이 잠긴다.

    실효용적률 미확보 → GFA 미산출 → 등급 미상 → 응답 전체가 `None`.
    낙관적으로 E 를 채우면 이 단언이 죽는다.
    """
    orch = _stub_orchestrator(monkeypatch, far=None, price_source="주변 실거래(MOLIT)")
    out = await orch.build_rough_scenario(address="정밀도-QA")

    assert out["inputs"]["gfa_sqm"] is None, "GFA 가 산출됐다 — 대조군 전제가 무너졌다"
    assert out["precision"] is None
    assert out["precision_label"] == "정밀도 미표기"
    assert "연면적" in out["precision_basis"]
    assert out["precision_inputs"]["gfa"] is None
    # 분양단가는 실거래라 확인됨 — **한 입력이 모른다고 나머지를 지우지 않는다**.
    assert out["precision_inputs"]["sale_price"] == "V"


# ── 8) 변이가 드러낸 **미검사 분기**들 ──────────────────────────────────────
@pytest.mark.asyncio
async def test_AI비서_등급_미표기일_때도_지시를_넘긴다(monkeypatch) -> None:
    """★E 경로만 잠그고 None 경로를 방치했더니 그 분기가 변이에서 살아남았다.

    등급을 **판정할 수 없을 때**야말로 LLM 이 확정치처럼 말하기 쉽다.
    """
    import app.services.feasibility.rough_feasibility_orchestrator as orch
    from app.services.ai.assistant_agent import rough_feasibility

    async def _fake(**_kw):
        return {
            "scenario_status": "actual",
            "inputs": {"dev_type_name": "공동주택"},
            "summary": {"total_cost_won": 1, "grade": "F"},
            "degraded_notes": [],
            "precision": None,
            "precision_label": "정밀도 미표기",
            "precision_basis": "연면적 등급 미확보 — 산출물 전체의 정밀도를 판정할 수 없습니다",
        }

    monkeypatch.setattr(orch, "build_rough_scenario", _fake)
    out = await rough_feasibility.ainvoke({"address": "주소"})
    assert "[정밀도] 정밀도 미표기" in out
    # 근거도 함께 넘어가야 한다(무엇을 모르는지 LLM 이 말할 수 있어야 한다).
    assert "연면적 등급 미확보" in out
    assert "정밀도를 판정할 수 없다" in out
    assert "확정치처럼 답하지 말고" in out


def test_분양단가가_구속조건이면_그_사유가_근거에_남는다() -> None:
    """★입력별 등급만 확인하고 **근거 문구**를 방치했더니 그 분기가 변이에서 살아남았다."""
    grade, basis, _inputs = _compose(
        gfa_precision=V, gfa_basis="",
        price_source="지역 시세 테이블(national_default·추정·비실거래)",
    )
    assert grade is E
    assert "분양단가" in basis and "실거래 미확보" in basis


def test_모든_입력이_확인됨이면_등급도_확인됨이다() -> None:
    """★상향 경로 — 개략 입력이 하나도 없으면 결과는 V 다.

    이 경로가 없으면 "무조건 E 로 떨어뜨리는" 판별기여도 초록이 된다.
    """
    grade, basis, inputs = _compose(gfa_precision=V, gfa_basis="")
    assert grade is V
    assert inputs == {"gfa": "V", "land_cost": "V", "sale_price": "V"}
    # ★"비어 있지 않다"만 보면 문구를 아무거나 바꿔도 통과한다(변이 생존). 문구를 못박는다.
    assert basis == "입력 최저 등급을 따름"


def test_보고서_고지가_확인됨_등급도_말한다() -> None:
    """★E·None 만 잠그고 일반 경로(V/D)를 방치했더니 그 분기가 변이에서 살아남았다."""
    text = _exec_text(_scenario("V", "확인됨"))
    assert "정밀도 고지" in text
    assert "확인됨" in text


@pytest.mark.asyncio
async def test_보고서_JSON_정밀도_블록이_근거까지_담는다() -> None:
    """★블록 존재만 보고 `basis` 를 방치했더니 그 줄이 변이에서 살아남았다."""
    from app.services.feasibility.rough_scenario_report import (
        generate_rough_scenario_report,
    )

    s = _scenario("E", "개략(추정)", basis="대지면적 × 실효용적률 — 설계 미반영(개략)")
    j = await generate_rough_scenario_report(s, use_llm=False, format="json")
    assert j["precision"]["basis"] == "대지면적 × 실효용적률 — 설계 미반영(개략)"
