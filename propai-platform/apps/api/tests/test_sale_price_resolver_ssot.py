"""분양단가 SSOT — **단위가 다른 두 수를 블렌딩하던 것**을 잠근다.

## 무엇이 결함이었나 (라이브 실측 2026-09-04 · 컨테이너 `propai-api-8000` 내부)

`market_revaluation_service.revalue()` 가 두 출처를 **가중 블렌딩**했다:

    regional   0.35  ← `regional_pricing` = **공급면적 기준 신축 분양가**
    molit_real 0.65  ← `_molit_avg_per_pyeong` = **전용면적 기준 기존아파트 매매가**

**단위도 상품도 다르다.** 그리고 그 값이 `project_pipeline` 에서
**지역 테이블보다 우선해** 분양가로 쓰였다(`avg_sale_price = market_reval["price_per_pyeong"]`).

같은 주소 5곳 실측 — 공용 리졸버(올바른 공급 기준) 대비:

    강남 역삼    100.8M vs 64.8M   **+56%**
    부산 해운대   22.4M vs 28.5M   **−21%**

★**부호가 일정하지 않아 조용했다** — 두 오류가 부분 상쇄된다(전용→공급 미변환은 상방 ·
시군구 평균 ↔ 동 중앙값은 지역마다 부호가 다름). **일관된 편향이었으면 더 빨리 보였다.**

## 이 파일이 잠그는 네 축

| 축 | 없으면 |
|---|---|
| **단위 계약** | 다시 전용 기준 값이 분양가 자리에 들어간다 |
| **재구현 금지** | 산식이 또 갈린다(그것이 이 결함의 원인) |
| **표본 하한 전파** | `n=1` 도 «실거래 기반» 이라 라벨링된다 |
| **재수출 계약** | 이관이 기존 호출부를 조용히 깬다 |
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1]
_RESOLVER = _API / "app" / "services" / "feasibility" / "sale_price_resolver.py"
_REVAL = _API / "app" / "services" / "feasibility" / "market_revaluation_service.py"
_ROUGH = _API / "app" / "services" / "feasibility" / "rough_feasibility_orchestrator.py"
_PIPE = _API / "app" / "services" / "pipeline" / "project_pipeline.py"


# ══════════════════════════════════════════════════════════════════════════════
# 축 1 — 단위 계약: 블렌딩되는 두 출처가 **같은 축**이어야 한다
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_molit_source_returns_the_shared_resolver_value(monkeypatch) -> None:
    """`_molit_sale_price_source` 는 공용 리졸버 값을 **그대로** 싣는다(재계산 없음).

    ★값이 조금이라도 가공되면 그 가공이 곧 **두 번째 산식**이고, 두 산식은 반드시 갈린다.
    """
    from app.services.feasibility import market_revaluation_service as mrs

    called: list[dict] = []

    async def fake_resolver(*, dev_type: str, address: str):
        called.append({"dev_type": dev_type, "address": address})
        return (29_448_234, "주변 실거래(MOLIT)", "동 중앙값 …(전용) × 전용률 × 프리미엄", None)

    import app.services.feasibility.sale_price_resolver as spr
    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", fake_resolver, raising=True)

    out = await mrs.MarketRevaluationService()._molit_sale_price_source(
        address="서울특별시 노원구 상계동 771", dev_type="M03")

    assert called == [{"dev_type": "M03", "address": "서울특별시 노원구 상계동 771"}], (
        f"공용 리졸버를 그대로 부르지 않았다: {called}")
    # ★**값 동일**을 단언한다 — «호출했다» 만 보면 결과를 가공하는 구현이 통과한다.
    assert out["price_per_pyeong"] == 29_448_234.0
    assert out["source"] == "molit_real"
    # 근거가 표면까지 실린다(진단 불가는 그 자체로 장애)
    assert "전용률" in out["note"]


@pytest.mark.asyncio
async def test_sample_floor_propagates_so_the_source_drops_out(monkeypatch) -> None:
    """★두 모집단 — 하한 통과 → 출처 실림 ↔ 하한 미달(리졸버가 None) → **출처가 빠진다**.

    이것이 없으면 `n=1` 짜리 값이 «주변 실거래(MOLIT)» 라벨을 달고 블렌딩에 들어간다.
    """
    import app.services.feasibility.sale_price_resolver as spr
    from app.services.feasibility import market_revaluation_service as mrs

    async def none_resolver(*, dev_type: str, address: str):
        return None  # 표본 하한 미달 = 리졸버의 정직한 None

    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", none_resolver, raising=True)
    assert await mrs.MarketRevaluationService()._molit_sale_price_source(
        address="어디든", dev_type="M01") is None, "표본 하한 미달인데 출처가 실렸다"

    # 음성 대조군 — 값이 있으면 실린다(«항상 None» 구현을 가른다)
    async def ok_resolver(*, dev_type: str, address: str):
        return (11_111_111, "s", "b", None)
    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", ok_resolver, raising=True)
    got = await mrs.MarketRevaluationService()._molit_sale_price_source(
        address="어디든", dev_type="M01")
    assert got and got["price_per_pyeong"] == 11_111_111.0

    # 0·음수도 실리지 않는다(경계 양방향)
    async def zero_resolver(*, dev_type: str, address: str):
        return (0, "s", "b", None)
    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", zero_resolver, raising=True)
    assert await mrs.MarketRevaluationService()._molit_sale_price_source(
        address="어디든", dev_type="M01") is None


# ══════════════════════════════════════════════════════════════════════════════
# 축 2 — 재구현 금지: 옛 산식이 **다시 소비되지 않는다**
# ══════════════════════════════════════════════════════════════════════════════

def _calls_named(tree: ast.AST, name: str) -> list[int]:
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and ((isinstance(n.func, ast.Attribute) and n.func.attr == name)
                 or (isinstance(n.func, ast.Name) and n.func.id == name))]


def test_the_mismatched_aggregator_has_zero_consumers() -> None:
    """단위가 틀린 옛 집계기(`_molit_avg_per_pyeong`)가 **다시 불리지 않는다**.

    ★판정은 문자열이 아니라 **파서**로 한다 — 이 파일과 대상 파일의 주석에 그 이름이
      여러 번 나오므로 `grep` 은 그것을 호출부로 센다(이 저장소가 반복해 데인 형태).
    """
    tree = ast.parse(_REVAL.read_text(encoding="utf-8"))
    calls = _calls_named(tree, "_molit_avg_per_pyeong")
    assert calls == [], f"단위 불일치 집계기가 다시 호출된다: 줄 {calls}"

    # ★공허진리 방지 + 조회기 생존: 새 소스는 **실제로 불린다**
    assert _calls_named(tree, "_molit_sale_price_source"), "새 출처가 호출되지 않는다 — 배선 끊김"
    # 음성 대조군: 조회기가 존재하는 호출을 실제로 집는가
    assert _calls_named(ast.parse("x._molit_avg_per_pyeong(1)\n"), "_molit_avg_per_pyeong"), "조회기 사망"


def test_the_resolver_formula_lives_in_exactly_one_module() -> None:
    """전용→공급 환산 + 신축 프리미엄 산식이 **한 곳에만** 있다.

    ★두 곳에 있으면 반드시 갈린다 — 그것이 이 PR 이 고치는 결함의 정확한 형태다.
    """
    from app.services.feasibility import rough_feasibility_orchestrator as rough
    from app.services.feasibility import sale_price_resolver as spr

    # 재수출은 **같은 객체**여야 한다(복사본이면 한쪽만 고쳐진다)
    assert rough._trade_sale_price_per_pyeong is spr._trade_sale_price_per_pyeong
    assert rough._resolve_sale_price_per_pyeong is spr._resolve_sale_price_per_pyeong
    assert rough._MIN_TRADE_SAMPLES is spr._MIN_TRADE_SAMPLES

    # 산식 상수(`_JEONYULRYUL`·`_PREMIUM`)를 끌어 쓰는 feasibility 모듈이 리졸버뿐인가
    hits = []
    for f in (_API / "app" / "services" / "feasibility").glob("*.py"):
        src = f.read_text(encoding="utf-8")
        # 실행 줄만 — 주석·독스트링의 언급은 세지 않는다
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.ImportFrom) and node.module and "pricing.suggest" in node.module:
                names = {a.name for a in node.names}
                if names & {"_JEONYULRYUL", "_PREMIUM"}:
                    hits.append(f.name)
    assert hits == ["sale_price_resolver.py"], f"환산 산식이 여러 곳에 있다: {sorted(set(hits))}"


# ══════════════════════════════════════════════════════════════════════════════
# 축 3 — 재수출 계약: 이관이 기존 호출부를 깨지 않는다
# ══════════════════════════════════════════════════════════════════════════════

def test_moved_names_are_still_importable_from_the_old_module() -> None:
    """★`ruff --fix` 가 «미사용» 으로 판단해 재수출을 **실제로 지웠었다**.

    기존 테스트가 이 이름들을 옛 모듈에서 끌어 쓴다(`tests/test_rough_feasibility_orchestrator.py`).
    재수출은 장식이 아니라 **계약**이다.
    """
    import app.services.feasibility.rough_feasibility_orchestrator as rough
    for name in ("_MIN_TRADE_SAMPLES", "_sigungu5_from_address",
                 "_trade_sale_price_per_pyeong", "_resolve_sale_price_per_pyeong",
                 "_BUILDING_TO_MOLIT_PROP"):
        assert hasattr(rough, name), f"재수출이 사라졌다: {name}"


# ══════════════════════════════════════════════════════════════════════════════
# 축 4 — `dev_type` 전달: 실거래 물건종별이 분양가 유형과 같은 축이어야 한다
# ══════════════════════════════════════════════════════════════════════════════

def test_pipeline_passes_dev_type_to_revaluation() -> None:
    """안 넘기면 기본값으로 떨어져 **유형이 다른 사업에서 축이 갈린다**."""
    tree = ast.parse(_PIPE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "revalue"):
            kw = {k.arg for k in node.keywords}
            assert "dev_type" in kw, f"revalue 호출에 dev_type 이 없다(줄 {node.lineno}): {sorted(kw)}"
            break
    else:
        pytest.fail("파이프라인에서 revalue 호출을 찾지 못했다 — 조회기 사망 또는 배선 제거")
