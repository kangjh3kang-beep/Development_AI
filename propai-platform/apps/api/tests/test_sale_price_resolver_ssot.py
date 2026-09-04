"""분양단가 SSOT — **단위가 다른 두 수를 블렌딩하던 것**과, 그 봉합이 만든 결함들을 잠근다.

## 원래 결함 (라이브 실측 2026-09-04 · 컨테이너 `propai-api-8000` 내부)

`market_revaluation_service.revalue()` 가 두 출처를 **가중 블렌딩**했다:

    regional   0.35  ← `regional_pricing` = **공급면적 기준 신축 분양가**
    molit_real 0.65  ← `_molit_avg_per_pyeong` = **전용면적 기준 기존아파트 매매가**

같은 주소 5곳: 강남 **+56%** · 해운대 **−21%**.
★**부호가 일정하지 않아 조용했다** — 두 오류가 부분 상쇄된다.

## ★★그 봉합이 새 결함 셋을 만들었다(적대 리뷰가 잡았다) — 여기서 함께 잠근다

| # | 내가 만든 것 | 결과 |
|---|---|---|
| C-1 | `lawd_cd` 를 버리고 **VWorld 지오코딩 의존**을 새로 만듦 | 지오코딩 장애 시 분양가 **−39%**(36.05M → 22.00M)인데 라벨은 계속 `market_blended` |
| M-1 | `dev_type` 배선에 **없는 필드**를 `getattr` — 항상 `"M01"` | 락은 «키가 있다» 만 봐서 초록 = **장식이 락으로 위장** |
| M-4 | `confidence` 를 **고정 92** | n=5 에서 **+24pt** 부풀고, 그 값이 사용자에게 나간다 |

## 부채 (이 PR 범위 밖이지만 **초록 안에 보이게** 둔다)

- **M-2** 전용률 `_JEONYULRYUL = 0.747` 평면 상수 ↔ 선언된 정본 `unit_standards.get_exclusive_ratio(dev_type)`
  — 오피스텔·지산에서 **최대 36%** 어긋난다
- **M-3** 세 번째 출처 `avm` 이 **같은 단위 결함**을 그대로 갖는다(전용 기준 매매가)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_API = Path(__file__).resolve().parents[1]
_RESOLVER = _API / "app" / "services" / "feasibility" / "sale_price_resolver.py"
_REVAL = _API / "app" / "services" / "feasibility" / "market_revaluation_service.py"
_PIPE = _API / "app" / "services" / "pipeline" / "project_pipeline.py"

_BASIS = "주변 실거래(MOLIT) 동 중앙값 3,428만원/평(전용, 표본 2,230건·최근 8개월) × 전용률 0.747 × 신축 프리미엄 1.15 → 공급 평당가"


def _api_py_files():
    """★`glob("*.py")` 가 아니라 **재귀**다 — 리뷰가 하위 디렉토리 복제로 뚫었다."""
    return [f for f in (_API / "app").rglob("*.py") if "__pycache__" not in str(f)]


def _calls_named(tree: ast.AST, name: str) -> list[int]:
    return [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and ((isinstance(n.func, ast.Attribute) and n.func.attr == name)
                 or (isinstance(n.func, ast.Name) and n.func.id == name))]


# ══════════════════════════════════════════════════════════════════════════════
# 축 1 — 단위 계약: 블렌딩되는 두 출처가 **같은 축**이어야 한다
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_molit_source_returns_the_shared_resolver_value(monkeypatch) -> None:
    """공용 리졸버 값을 **그대로** 싣는다(재계산·가공 없음) + **인자가 전부 전달된다**."""
    import app.services.feasibility.sale_price_resolver as spr
    from app.services.feasibility import market_revaluation_service as mrs

    seen: list[dict] = []

    async def fake(*, dev_type, address, sigungu5=None, building_type=None):
        seen.append({"dev_type": dev_type, "address": address,
                     "sigungu5": sigungu5, "building_type": building_type})
        return (29_448_234, "주변 실거래(MOLIT)", _BASIS, None)

    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", fake, raising=True)
    out = await mrs.MarketRevaluationService()._molit_sale_price_source(
        address="서울특별시 노원구 상계동 771", dev_type="M03",
        lawd_cd="11350", building_type="officetel")

    # ★값 **동일** — «호출했다» 만 보면 결과를 가공하는 구현이 통과한다
    assert out["price_per_pyeong"] == 29_448_234.0
    assert out["source"] == "molit_real"
    assert "전용률" in out["note"]
    # ★★인자가 **전부** 도달하는가. 하나라도 빠지면 그 축은 죽은 배선이다.
    assert seen == [{"dev_type": "M03", "address": "서울특별시 노원구 상계동 771",
                     "sigungu5": "11350", "building_type": "officetel"}], seen


@pytest.mark.asyncio
async def test_confidence_tracks_sample_size_not_a_constant(monkeypatch) -> None:
    """★M-4 — `confidence` 는 **표본수의 함수**다. 고정값은 정직성 지표를 부풀린다.

    이 값은 `project_pipeline` 의 `sale_price_confidence`("분양가 신뢰도(%)")로
    **사용자에게 나간다.** 고정 92 는 n=5 에서 **+24pt** 부풀었다.
    """
    import app.services.feasibility.sale_price_resolver as spr
    from app.services.feasibility import market_revaluation_service as mrs

    async def make(n: int):
        async def fake(*, dev_type, address, sigungu5=None, building_type=None):
            return (30_000_000, "s", f"주변 실거래(MOLIT) 동 중앙값 …(전용, 표본 {n:,}건·최근 8개월) × 전용률 0.747", None)
        monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", fake, raising=True)
        return await mrs.MarketRevaluationService()._molit_sale_price_source(address="a")

    low, mid, high = await make(5), await make(12), await make(2230)
    # ★두 모집단이 **다른 값**을 내야 한다 — 같으면 상수와 구별되지 않는다
    assert low["confidence"] < mid["confidence"] < high["confidence"], (
        f"표본수가 신뢰도를 가르지 않는다: {low['confidence']}/{mid['confidence']}/{high['confidence']}")
    assert low["confidence"] == 55 and high["confidence"] == 92
    # 표본수가 원장에 남는다(근거 소실 방지)
    assert low["count"] == 5 and high["count"] == 2230


@pytest.mark.asyncio
async def test_sample_floor_propagates_so_the_source_drops_out(monkeypatch) -> None:
    """★두 모집단 — 하한 통과 → 실림 ↔ 리졸버 `None` → **출처가 빠진다**."""
    import app.services.feasibility.sale_price_resolver as spr
    from app.services.feasibility import market_revaluation_service as mrs

    async def none_res(*, dev_type, address, sigungu5=None, building_type=None):
        return None
    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", none_res, raising=True)
    assert await mrs.MarketRevaluationService()._molit_sale_price_source(address="a") is None

    async def ok(*, dev_type, address, sigungu5=None, building_type=None):
        return (11_111_111, "s", _BASIS, None)
    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", ok, raising=True)
    got = await mrs.MarketRevaluationService()._molit_sale_price_source(address="a")
    assert got and got["price_per_pyeong"] == 11_111_111.0

    async def zero(*, dev_type, address, sigungu5=None, building_type=None):
        return (0, "s", _BASIS, None)
    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", zero, raising=True)
    assert await mrs.MarketRevaluationService()._molit_sale_price_source(address="a") is None


# ══════════════════════════════════════════════════════════════════════════════
# 축 2 (C-1) — 출처가 빠지면 **라벨이 그 사실을 말한다**
# ══════════════════════════════════════════════════════════════════════════════

def test_blend_label_distinguishes_single_source_from_blended() -> None:
    """★«블렌딩» 이라는 말이 **실제로 섞였을 때만** 나온다.

    종전엔 출처가 `regional` 하나만 남아도 `market_blended` 였다. VWorld 장애 시
    실거래가 통째로 빠져 **−39%**(36.05M → 22.00M)로 하드코딩 테이블에 떨어지는데
    **라벨은 그대로**였다 — 실패가 자기를 구별하지 못하면 아무도 원인을 못 본다.
    """
    from app.services.feasibility.market_revaluation_service import _blend_label

    two = [{"source": "regional"}, {"source": "molit_real"}]
    one = [{"source": "regional"}]
    assert _blend_label(two, False, 1.0) == "market_blended"
    assert _blend_label(two, True, 1.0) == "avm_blended"
    # ★두 번째 모집단 — 하나뿐이면 「블렌딩」이 아니다
    assert _blend_label(one, False, 1.0) == "single_source:regional"
    assert _blend_label(one, True, 1.0) == "single_source:regional"
    # 산출 불가는 None(정직)
    assert _blend_label(two, False, 0.0) is None


def test_pipeline_uses_the_service_label_not_its_own() -> None:
    """파이프라인이 라벨을 **다시 적으면** 두 곳이 갈린다 — 실제로 갈려 있었다."""
    src = _PIPE.read_text(encoding="utf-8")
    assert 'market_reval.get("sale_price_source")' in src, (
        "파이프라인이 서비스 라벨을 안 쓴다 — 자기가 market_blended 를 하드코딩하고 있다")


def test_sigungu_injection_beats_geocoding() -> None:
    """★C-1 — 호출부가 시군구를 알면 **지오코딩을 하지 않는다**(장애 전파 차단)."""
    src = _RESOLVER.read_text(encoding="utf-8")
    tree = ast.parse(src)
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.AsyncFunctionDef) and n.name == "_trade_sale_price_per_pyeong")
    kwonly = [a.arg for a in fn.args.kwonlyargs]
    assert "sigungu5" in kwonly, f"주입 경로가 없다 — 지오코딩이 강결합이다: {kwonly}"
    assert "building_type" in kwonly, f"건물유형 주입 경로가 없다: {kwonly}"
    # 소비처가 실제로 넘기는가(배선 — 존재 아님)
    rev = _REVAL.read_text(encoding="utf-8")
    assert "sigungu5=(lawd_cd or \"\")[:5] or None" in rev, "revaluation 이 lawd_cd 를 안 넘긴다"
    assert "building_type=building_type" in rev, "revaluation 이 building_type 을 안 넘긴다"


# ══════════════════════════════════════════════════════════════════════════════
# 축 3 — 재구현 금지: 옛 산식이 **어떤 경로로도** 되살아나지 않는다
# ══════════════════════════════════════════════════════════════════════════════

def test_the_mismatched_aggregator_has_zero_consumers() -> None:
    """★**전 파일 파생** + `getattr` 우회까지. 한 파일만 파싱하면 리뷰의 변이 2종이 샌다."""
    hits: list[str] = []
    for f in _api_py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        hits += [f"{f.name}:{ln}" for ln in _calls_named(tree, "_molit_avg_per_pyeong")]
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "getattr"
                    and len(n.args) >= 2 and isinstance(n.args[1], ast.Constant)
                    and n.args[1].value == "_molit_avg_per_pyeong"):
                hits.append(f"{f.name}:{n.lineno}(getattr 우회)")
    assert hits == [], f"단위 불일치 집계기가 다시 호출된다: {hits}"

    # ★공허진리 방지: 새 출처는 **실제로** 불린다
    assert _calls_named(ast.parse(_REVAL.read_text(encoding="utf-8")),
                        "_molit_sale_price_source"), "새 출처가 호출되지 않는다 — 배선 끊김"
    # 음성 대조군
    assert _calls_named(ast.parse("x._molit_avg_per_pyeong(1)\n"), "_molit_avg_per_pyeong"), "조회기 사망"


def test_the_conversion_formula_lives_in_exactly_one_module() -> None:
    """환산 산식이 **한 곳에만** 있는가 — 리뷰가 뚫은 **세 경로**를 전부 본다.

    ①`ImportFrom` ②별칭/`Attribute` 접근 ③**리터럴 `0.747`·`1.15` 직접 사용**
    그리고 `glob` 이 아니라 **`rglob`**(하위 디렉토리 복제).
    """
    hits: set[str] = set()
    for f in _api_py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "pricing.suggest" in node.module:
                if {a.name for a in node.names} & {"_JEONYULRYUL", "_PREMIUM"}:
                    hits.add(f.name)
            if isinstance(node, ast.Attribute) and node.attr in {"_JEONYULRYUL", "_PREMIUM"}:
                hits.add(f.name)
            # ★리터럴은 **`0.747` 만** 본다. `1.15` 는 몬테카를로·에스컬레이션 등에서
            #   쓰이는 **흔한 승수**라 넣으면 정상 코드 6파일을 위반으로 신고한다
            #   (실측: 0.747 → **1파일** · 1.15 → **7파일**). **위양성도 결함이다** —
            #   가드가 정상 코드를 막으면 다음 사람이 가드를 끈다.
            #   `1.15` 는 위의 import/Attribute 축이 덮는다.
            if isinstance(node, ast.Constant) and node.value == 0.747:
                hits.add(f.name)
    allowed = {"sale_price_resolver.py", "suggest.py"}   # 정의처 + 유일 소비처
    assert not (hits - allowed), f"환산 산식이 여러 곳에 있다: {sorted(hits - allowed)}"
    assert "suggest.py" in hits, "조회기 사망 — 정의처조차 안 잡힌다"


def test_moved_names_are_still_importable_from_the_old_module() -> None:
    """재수출 계약 — ★`ruff --fix` 가 실제로 이것을 «미사용» 으로 지웠었다."""
    import app.services.feasibility.rough_feasibility_orchestrator as rough
    import app.services.feasibility.sale_price_resolver as spr
    for name in ("_MIN_TRADE_SAMPLES", "_sigungu5_from_address",
                 "_trade_sale_price_per_pyeong", "_resolve_sale_price_per_pyeong",
                 "_BUILDING_TO_MOLIT_PROP"):
        assert hasattr(rough, name), f"재수출이 사라졌다: {name}"
    # ★함수는 **같은 객체**여야 한다(`is` 가 의미 있는 축)
    assert rough._trade_sale_price_per_pyeong is spr._trade_sale_price_per_pyeong
    assert rough._resolve_sale_price_per_pyeong is spr._resolve_sale_price_per_pyeong
    # ★★상수는 `is` 로 못 잡는다(`5 is 5` 는 인터닝으로 항상 참) — **정의 지점이 하나**임을 센다
    defs = [f.name for f in _api_py_files()
            if any(isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_MIN_TRADE_SAMPLES" for t in n.targets)
                for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))))]
    assert defs == ["sale_price_resolver.py"], f"표본 하한이 여러 곳에 정의됐다: {defs}"


def test_split_property_type_mapping_is_not_collapsed() -> None:
    """물건종별 매핑이 뭉개지지 않았는가 — 전부 `apt` 가 되면 유형 축이 죽는다."""
    from app.services.feasibility.sale_price_resolver import _BUILDING_TO_MOLIT_PROP
    vals = set(_BUILDING_TO_MOLIT_PROP.values())
    assert len(vals) >= 2, f"물건종별이 한 값으로 뭉개졌다: {_BUILDING_TO_MOLIT_PROP}"
    assert _BUILDING_TO_MOLIT_PROP.get("officetel") != _BUILDING_TO_MOLIT_PROP.get("apartment")


# ══════════════════════════════════════════════════════════════════════════════
# 부채 — **초록 안에 보이게** 둔다(커밋 메시지에만 적으면 안 드러난다)
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.xfail(strict=True, reason=(
    "★M-2 부채 — 전용률이 두 벌이다. `_JEONYULRYUL = 0.747`(평면 상수)과 "
    "`unit_standards.get_exclusive_ratio(dev_type)`(선언된 정본, 유형별)이 공존하고 "
    "오피스텔·지식산업센터에서 **최대 36%** 어긋난다. 이 PR 범위 밖이라 고치지 않되 "
    "**초록 안에 보이게** 둔다. 고치면 rough 경로의 값이 바뀌므로 별도 측정이 필요하다."))
def test_debt_exclusive_ratio_has_two_sources() -> None:
    from app.services.feasibility.unit_standards import get_exclusive_ratio
    from app.services.sales.pricing.suggest import _JEONYULRYUL
    assert get_exclusive_ratio("M08") == _JEONYULRYUL


@pytest.mark.xfail(strict=True, reason=(
    "★M-3 부채 — 세 번째 출처 `avm` 이 **같은 단위 결함**을 갖는다: "
    "`predicted_won / (84.0㎡ / 평)` 은 **전용 기준 매매가**인데 공급 기준 분양가와 섞인다. "
    "이 PR 은 `molit_real` 만 고쳤다 — **모집단이 3인데 2로 셌다.** "
    "MLflow 모델 미등록이면 휴면이라 라이브 발화 여부는 **미측정**."))
def test_debt_avm_source_uses_supply_area_basis() -> None:
    src = _REVAL.read_text(encoding="utf-8")
    assert "_AVM_REF_AREA_SQM" not in src or "전용률" in src.split("_avm_source")[1][:1200]
