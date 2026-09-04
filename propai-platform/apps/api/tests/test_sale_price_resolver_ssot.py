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
        return (29_448_234, "주변 실거래(MOLIT)", _BASIS, None, 2230)

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
            # ★표본수를 **구조적으로** 돌려준다 — 종전엔 소비처가 이 산문을 정규식으로 긁었고,
            #   생산자가 문구만 바꿔도 조용히 기본값으로 떨어졌다(적대 리뷰 MAJOR-4).
            return (30_000_000, "s", "주변 실거래(MOLIT) 동 중앙값 …", None, n)
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
        return (11_111_111, "s", _BASIS, None, 10)
    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", ok, raising=True)
    got = await mrs.MarketRevaluationService()._molit_sale_price_source(address="a")
    assert got and got["price_per_pyeong"] == 11_111_111.0

    async def zero(*, dev_type, address, sigungu5=None, building_type=None):
        return (0, "s", _BASIS, None, 10)
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


# ══════════════════════════════════════════════════════════════════════════════
# 부채 — **초록 안에 보이게** 둔다(커밋 메시지에만 적으면 안 드러난다)
# ══════════════════════════════════════════════════════════════════════════════

def test_exclusive_ratio_comes_from_the_declared_ssot() -> None:
    """★M-2 **해소** — 전용률이 정본에서 온다(평면 상수 소비처 0).

    `unit_standards` 는 **자신을 유일 정본이라 선언**하고 *"두 소비처가 서로 다른 전용률
    테이블을 각자 보유해 세대수가 30% 안팎 어긋나던 이중정의 결함"* 을 막으려 존재한다.
    `_JEONYULRYUL = 0.747` 은 정확히 그 이중정의였다(라이브 실측: 오피스텔·지산 **+35.8%**,
    단독 **−12.1%**, 아파트 **−0.4%**).

    ★★이 결함은 **앞 커밋이 활성화**시켰다 — 종전엔 `dev_type` 이 항상 M01 이라 0.747 이
      **우연히 맞았다.** `building_type` 을 실제로 넘기게 고치자 비정합이 드러났다.
    """
    import ast

    from app.services.feasibility.sale_price_resolver import _exclusive_ratio_for
    from app.services.feasibility.unit_standards import get_exclusive_ratio

    # ★평면 상수의 **실행 소비처가 0** 인가(주석·독스트링은 세지 않는다 — 파서로 본다)
    tree = ast.parse(_RESOLVER.read_text(encoding="utf-8"))
    used = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Name) and n.id == "_JEONYULRYUL"]
    assert used == [], f"평면 전용률이 아직 실행 경로에 있다: 줄 {used}"

    # ★두 모집단 — 유형이 갈리면 값도 갈려야 한다(같으면 상수와 구별 불가)
    apt, _ = _exclusive_ratio_for("M01", "apartment")
    offi, _ = _exclusive_ratio_for("M08", "officetel")
    assert offi < apt, f"오피스텔 전용률이 아파트보다 낮지 않다: {offi} vs {apt}"
    assert offi == get_exclusive_ratio("M08") == 0.55

    # ★★축은 `dev_type` 이다 — 「최소=안전측」은 **라이브 측정으로 기각**했다
    #   (apartment 가 0.75 → 0.60 이 되어 가장 흔한 경로가 −19.7%. 주상복합 값을 일반
    #    아파트에 적용하는 것이라 **보수적인 게 아니라 틀린 것**이었다).
    r, note = _exclusive_ratio_for("M01", "apartment")
    assert r == 0.75, f"dev_type 정본을 안 쓴다: {r} ({note})"

    # ★불일치는 **값을 바꾸지 않고 근거에 싣는다**(부채를 숨기지 않는다)
    r2, note2 = _exclusive_ratio_for("M01", "officetel")
    assert r2 == 0.75, "불일치인데 값을 조용히 바꿨다"
    assert "불일치" in note2, f"불일치가 표면에 안 실린다: {note2}"
    # 음성 대조군: 일치하면 그 문구가 **없다**(항상 붙이는 구현을 가른다)
    _, note3 = _exclusive_ratio_for("M08", "officetel")
    assert "불일치" not in note3, f"일치인데 불일치라 적는다: {note3}"


def test_every_blended_source_is_on_the_supply_price_basis() -> None:
    """★M-3 **해소** — 블렌딩되는 **세 출처 전부**가 같은 축(공급 기준 신축 분양가)이다.

    초판은 `molit_real` 만 고치고 **`avm` 을 빠뜨렸다** — **모집단이 3인데 2로 셌다**.
    AVM 도 MOLIT `area_m2`(전용) + `price_10k_won`(매매)로 학습하므로 **같은 단위 결함**이었다.

    ★라이브 실측(2026-09-05): 이 출처는 **휴면**이다(`_avm_source` → `None` · 모델 미등록,
      `stage=fallback`). 그래도 고쳤다 — **모델을 등록하는 순간 발화하는 지뢰**이고,
      그때는 «왜 분양가가 튀었나» 를 이 자리에서 찾기 어렵다.
    """
    src = _REVAL.read_text(encoding="utf-8")
    # ★`split("_avm_source")` 는 **호출부**를 잡는다(정의부보다 먼저 나온다) — 내 첫 판이
    #   그래서 위양성을 냈다. **정의부**를 앵커로 삼는다.
    assert "async def _avm_source" in src, "조회기 사망 — 정의부를 못 찾는다"
    # ★고정 창(`[:2500]`)을 쓰지 않는다 — 정의부 155행 ↔ 변환 226행이라 **잘렸다**.
    #   *절단된 창은 「없다」고 확신 있게 답한다.* 경계를 **다음 메서드**로 잡는다.
    body = src.split("async def _avm_source", 1)[1]
    nxt = body.find("\n    async def ")
    avm = body if nxt < 0 else body[:nxt]
    assert len(avm) > 800, f"창이 너무 짧다 — 경계를 잘못 잡았다({len(avm)}자)"
    # ★공용 변환을 **경유**하는가(세 번째 산식을 만들지 않았는가)
    assert "_exclusive_ratio_for" in avm, "avm 출처가 전용률 변환을 안 거친다"
    assert "_new_build_premium" in avm, "avm 출처가 신축 프리미엄을 안 거친다"
    # ★근거가 표면까지 실리는가
    assert "공급 평당가" in avm, "변환 사실이 note 에 안 실린다"

    # ★★프리미엄 상수의 **정의가 한 곳**인가 — 접근자를 두고도 복제하면 소용없다
    import ast
    defs = []
    for f in _api_py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "_PREMIUM" for t in n.targets):
                defs.append(f.name)
    assert defs == ["suggest.py"], f"신축 프리미엄이 여러 곳에 정의됐다: {defs}"


def test_stubs_must_tolerate_new_kwargs() -> None:
    """★**스텁 kwargs 함정** — 이 저장소에서 오늘만 **세 번** 났다.

    소비처가 인자를 늘리면 스텁이 `TypeError` 를 내는데, `revalue()` 의 `except Exception`
    이 그것을 **삼켜 출처가 조용히 빠진다.** 그러면 테스트는 **실패가 아니라 다른 것을 잰다**
    (실측: 29,000,000 기대 자리에 30,000,000 · 30,000,000 기대 자리에 28,000,000).

    → 출처 스텁은 **`**kw` 를 받아야 한다**. 소스 검사로 강제한다.
    """
    import re

    src = (_API / "tests" / "test_avm_train.py").read_text(encoding="utf-8")
    # ★축을 **정확히** 잡는다: `MarketRevaluationService` 의 **출처 메서드**를 대체하는
    #   스텁만이 대상이다. 이름 패턴으로 넓게 잡았더니 AVM **내부** 스텁
    #   (`_fake_load`·`_fake_comps`·`_fake_features`·`_fake_spatial`)까지 걸렸다 —
    #   그것들은 소비처가 아니라 **다른 계약**이다. ★위양성도 결함이다.
    targets = set(re.findall(
        r'monkeypatch\.setattr\(\s*MarketRevaluationService,\s*"(_[a-z_]+source[a-z_]*)"', src))
    assert targets, "조회기 사망 — 출처 스텁 배선을 하나도 못 찾았다"

    # ★죽은 루프를 지웠다 — `for name in sorted(targets)` 의 `name` 이 안 쓰이고
    #   `for sig in …: pass` 는 완전한 no-op 라 내부 스캔이 중복 실행됐다(4차 리뷰 Minor-1).
    bad = []
    if True:
        for m in re.finditer(r"async def (_fake_\w+)\(self([^)]*)\)", src):
            fn, params = m.group(1), m.group(2)
            wired = re.search(
                rf'monkeypatch\.setattr\(\s*MarketRevaluationService,\s*"[^"]+",\s*{fn}\b', src)
            if wired and "**kw" not in params:
                bad.append(f"{fn}({params.strip(', ')})")
    assert not bad, f"새 kwargs 를 못 받는 **출처 스텁**이 있다(조용히 출처가 빠진다): {bad}"


# ══════════════════════════════════════════════════════════════════════════════
# 축 4 — **배선**: `revalue()` → 출처 메서드 구간이 잠겨야 한다
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_revalue_wires_every_axis_into_the_molit_source(monkeypatch) -> None:
    """★함수만 잠그고 **배선을 안 잠근** 것을 고친다.

    `_molit_sale_price_source` 를 직접 부르는 락은 `revalue()` → 출처 메서드 **구간**을
    태우지 않는다. 실제로 그 구간에서 `building_type=None` 으로 바꾸는 변이가 **생존**했다
    (적대 리뷰 M3). 이 저장소가 반복해 데인 형태 그대로다 —
    *"변이를 함수 안에만 넣으면 배선은 무잠금"*.
    """
    from app.services.feasibility import market_revaluation_service as mrs

    seen: dict = {}

    async def fake_source(self, *, address, dev_type="M01", lawd_cd=None, building_type=None):
        seen.update(address=address, dev_type=dev_type,
                    lawd_cd=lawd_cd, building_type=building_type)
        return {"source": "molit_real", "label": "L", "price_per_pyeong": 30_000_000.0,
                "confidence": 80, "weight": 0.65, "count": 100, "note": "n"}

    monkeypatch.setattr(mrs.MarketRevaluationService, "_molit_sale_price_source",
                        fake_source, raising=True)

    async def no_avm(self, *, address, lawd_cd):
        return None
    monkeypatch.setattr(mrs.MarketRevaluationService, "_avm_source", no_avm, raising=True)

    await mrs.MarketRevaluationService().revalue(
        address="서울특별시 노원구 상계동 771", building_type="officetel",
        lawd_cd="11350", land_area_sqm=1000.0, dev_type="M08")

    # ★네 축이 **전부** 도달하는가. 하나라도 None 이면 그 축은 죽은 배선이다.
    assert seen == {"address": "서울특별시 노원구 상계동 771", "dev_type": "M08",
                    "lawd_cd": "11350", "building_type": "officetel"}, seen


@pytest.mark.asyncio
async def test_source_weights_are_the_declared_contract(monkeypatch) -> None:
    """★가중치는 **계약**이다 — 조용히 바뀌면 블렌딩 결과가 통째로 달라진다.

    `weight` 를 0.01 로 바꾸는 변이가 **생존**했다(적대 리뷰 M2): 어떤 락도 이 값을
    안 봤다. `regional` 0.35 / `molit_real` 0.65 는 «실거래가 가장 강한 시장신호» 라는
    **설계 선언**이고, 뒤집히면 하드코딩 테이블이 결과를 지배한다.
    """
    import app.services.feasibility.sale_price_resolver as spr
    from app.services.feasibility import market_revaluation_service as mrs

    async def fake(*, dev_type, address, sigungu5=None, building_type=None):
        return (30_000_000, "s", _BASIS, None, 100)
    monkeypatch.setattr(spr, "_trade_sale_price_per_pyeong", fake, raising=True)

    async def no_avm(self, *, address, lawd_cd):
        return None
    monkeypatch.setattr(mrs.MarketRevaluationService, "_avm_source", no_avm, raising=True)

    out = await mrs.MarketRevaluationService().revalue(
        address="서울특별시 노원구 상계동 771", lawd_cd="11350", building_type="apartment")
    w = {s["source"]: s["weight"] for s in out["sources"]}
    assert w == {"regional": 0.35, "molit_real": 0.65}, f"가중치 계약이 바뀌었다: {w}"
    # ★실거래가 지역 테이블보다 **무겁다** — 이 부등호가 설계의 요지다
    assert w["molit_real"] > w["regional"]


def test_property_type_mapping_is_not_collapsed_to_one_value() -> None:
    """물건종별이 뭉개지면 유형 축이 죽는다 — 전부 `apt` 면 오피스텔이 아파트로 조회된다."""
    from app.services.feasibility.sale_price_resolver import _BUILDING_TO_MOLIT_PROP as M
    assert len(set(M.values())) >= 4, f"물건종별이 뭉개졌다: {M}"
    for a, b in (("apartment", "officetel"), ("apartment", "house"), ("office", "apartment")):
        assert M[a] != M[b], f"{a} 와 {b} 가 같은 물건종별로 조회된다: {M[a]}"


# ══════════════════════════════════════════════════════════════════════════════
# 축 5 — **행위 락**: 소스 문자열이 아니라 «무엇이 실제로 불리는가»
# ══════════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_injected_sigungu_never_calls_geocoding(monkeypatch) -> None:
    """★C-2 — 주입이 지오코딩을 **이긴다**(행위). 종전 락은 **소스 문자열**만 봤다.

    그래서 callee 의 우선순위 한 줄을 지우는 변이가 **전 락 초록으로 생존**했다.
    그 한 줄이 «VWorld 장애 → 분양가 −39%» 의 전부다.
    """
    import app.services.feasibility.sale_price_resolver as spr

    geo_calls: list[str] = []

    async def spy_geo(address: str):
        geo_calls.append(address)
        return "99999"

    async def fake_trade(sigungu5, dong, prop_type):
        return {"dong": {"median": 3000, "n": 50}, "sigungu": {"median": 3000, "n": 50}}

    monkeypatch.setattr(spr, "_sigungu5_from_address", spy_geo, raising=True)
    monkeypatch.setattr("app.services.sales.pricing.suggest._trade_per_pyeong",
                        fake_trade, raising=True)

    # ① 주입 있음 → 지오코딩 **0회**
    await spr._trade_sale_price_per_pyeong(dev_type="M01", address="어디든", sigungu5="11350")
    assert geo_calls == [], f"주입했는데 지오코딩을 불렀다: {geo_calls}"

    # ② ★음성 대조군 — 주입 없으면 **불린다**(«항상 0회» 구현을 가른다)
    await spr._trade_sale_price_per_pyeong(dev_type="M01", address="어디든")
    assert len(geo_calls) == 1, f"주입 없는데 지오코딩을 안 불렀다: {geo_calls}"

    # ③ ★잘못된 주입은 **폴백을 막지 않는다**(truthy 억제 회귀 방지)
    geo_calls.clear()
    for bad in ("1168", "abcde", "  ", "11a80", "１２３４５"):
        await spr._trade_sale_price_per_pyeong(dev_type="M01", address="어디든", sigungu5=bad)
    assert len(geo_calls) == 5, f"잘못된 주입이 폴백을 억제했다(통과한 값 있음): {geo_calls}"


@pytest.mark.asyncio
async def test_building_type_reaches_molit_property_type(monkeypatch) -> None:
    """★C-1 — 표시 문자열이 **물건종별까지 도달**하는가(행위).

    `_canonical_building` 을 태우는 테스트가 **0건**이었다 — 이 저장소의 「소비처 0」 그 자체다.
    그래서 `return _DISPLAY_TO_BUILDING.get(bt, "") → return bt`(원래 결함 복원) 변이가
    **1,965 테스트 전부 초록**으로 생존했다.

    ★**세 모집단**이어야 한다 — 하나만 보면 «전부 apt» 구현이 통과한다.
    """
    import app.services.feasibility.sale_price_resolver as spr

    seen: list[str] = []

    async def spy_trade(sigungu5, dong, prop_type):
        seen.append(prop_type)
        return {"dong": {"median": 3000, "n": 50}, "sigungu": {"median": 3000, "n": 50}}

    monkeypatch.setattr("app.services.sales.pricing.suggest._trade_per_pyeong",
                        spy_trade, raising=True)

    async def call(bt):
        await spr._trade_sale_price_per_pyeong(
            dev_type="M01", address="a", sigungu5="11350", building_type=bt)

    # ★프로덕션이 **실제로 내는 값**으로 태운다(영어 정규 키가 아니라)
    await call("다세대주택")
    await call("근린생활시설")
    await call("오피스텔")
    await call(None)              # dev_type(M01) 폴백
    assert seen == ["villa", "commercial", "officetel", "apt"], (
        f"표시 문자열이 물건종별까지 도달하지 않는다: {seen}")

    # ★모르는 표기는 **폴백을 막지 않는다**(빈 문자열로 정규화)
    seen.clear()
    await call("존재하지않는유형")
    assert seen == ["apt"], f"모르는 표기가 폴백을 억제했다: {seen}"


def test_display_vocabulary_covers_what_the_pipeline_emits() -> None:
    """★손 목록이 상한이 되지 않게 — 생산자 어휘를 **파생**해 대조한다."""
    import re

    from app.services.feasibility.sale_price_resolver import (
        _BUILDING_TO_MOLIT_PROP,
        _DISPLAY_TO_BUILDING,
    )

    pipe = (_API / "app" / "services" / "pipeline" / "project_pipeline.py").read_text(encoding="utf-8")
    emitted = set(re.findall(r'building_type\s*=\s*"([^"]+)"', pipe))
    emitted |= set(re.findall(r'building_type\s*=\s*"[^"]*"\s*if[^\n]*else\s*"([^"]+)"', pipe))
    assert len(emitted) >= 3, f"생산자 어휘 추출 {len(emitted)}개 — 조회기가 죽었다: {emitted}"
    assert "아파트" in emitted, f"양성 대조군 실패: {emitted}"

    known = set(_DISPLAY_TO_BUILDING) | set(_BUILDING_TO_MOLIT_PROP)
    missing = emitted - known
    assert not missing, (
        f"파이프라인이 내는데 정규화 표에 없는 표기: {sorted(missing)} — "
        f"그 값은 조용히 'apt' 로 떨어진다")


def test_exclusive_ratio_note_does_not_lie_about_mismatch() -> None:
    """★M-3 — **프로덕션 입력(한국어)** 으로 태운다. 종전 락은 영어만 썼다.

    같은 함수가 한 축(`building`)은 정규화하고 **형제 축은 원값**을 써서,
    프로덕션 입력 **100% 에 거짓 「불일치」**가 붙어 **원장에 영속 기록**됐다.
    """
    from app.services.feasibility.sale_price_resolver import _exclusive_ratio_for

    # 일치인데 «불일치» 라 적지 않는다(위양성)
    for bt in ("아파트", "공동주택", "apartment", None):
        _, note = _exclusive_ratio_for("M01", bt)
        assert "불일치" not in note, f"M01+{bt!r} 은 일치인데 불일치라 적는다: {note}"

    # ★음성 대조군 — 진짜 불일치는 **적는다**(«절대 안 적는» 구현을 가른다)
    _, note = _exclusive_ratio_for("M01", "오피스텔")
    assert "불일치" in note, f"진짜 불일치를 안 적는다: {note}"


def test_paid_resolver_is_never_called_inside_a_loop() -> None:
    """★계획서 §5 가 **선언한** 락 — «요청당 1회» 는 오늘의 사실이지 구조적 보장이 아니다.

    지연 측정(§I)이 «호출부 10곳 전부 루프 깊이 0 = 요청당 최대 1회» 를 근거로
    «빠른 시드에 넣어도 된다» 고 판정했다. **다필지·배치 경로가 생기면 그 전제가 깨진다.**

    ★이 락이 없으면 계획서가 선언한 불변식이 **무잠금으로 머지**된다
      (CLAUDE.md §계획 게이트 C: *"§5 항목이 빈 계획서는 반려"*).

    ## ★★한계 — **직접 호출부만 본다**(닫지 못한 것을 닫았다고 하지 않는다)

    래퍼 한 겹이면 통과한다. 실측(4차 적대 리뷰):

        for a in addrs: out.append(await _one_resolve(a, dev_type))   ← **SURVIVED**
        (`_one_resolve` 가 리졸버를 부르는 얇은 래퍼)

    ★그리고 **그 형태가 다필지·배치를 쓰는 가장 자연스러운 모양**이다.
      즉 이 락은 «구조적 보장» 이 아니라 **직접 호출부에 대한 보장**이다.
      호출 그래프를 따라가려면 모듈 간 별칭·동적 호출까지 봐야 해서 이 PR 범위를 넘는다
      — **아래 `it.todo` 상당 항목으로 초록 안에 드러낸다.**
    """
    TARGETS = {
        "_resolve_sale_price_per_pyeong", "_trade_sale_price_per_pyeong",
        "revalue", "get_regional_sale_price_per_pyeong",
        "resolve_regional_sale_price_per_pyeong", "_molit_sale_price_source",
    }
    # ★★선언과 판정이 갈려 있었다: 이 튜플은 **아무 데서도 안 쓰이고**(ruff F841 →
    #   **CI 의 Backend(pytest) 가 통째로 빨개져 pytest 가 한 줄도 안 돌았다**),
    #   실제 판정은 아래에서 **다른 집합**을 하드코딩했다. 게다가 `ast.comprehension` 은
    #   컴프리헨션 노드가 아니라 **그 안의 `for` 절**이라 값 자체가 틀렸다.
    #   *«선언은 자기를 검증하지 않는다»* 를 이 PR 이 세 번 인용하고 그 처방 안에서 재발시켰다.
    #   → 선언을 **실제 판정에 쓴다**(한 곳에서만 정의).
    STMT_LOOPS = (ast.For, ast.AsyncFor, ast.While)
    COMP_LOOPS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
    bad: list[str] = []
    seen = 0

    for f in _api_py_files():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        # 각 노드의 **조상 루프 깊이**를 센다
        stack: list[str] = []

        def walk(node: ast.AST) -> None:
            nonlocal seen
            is_loop = isinstance(node, STMT_LOOPS)
            has_comp = isinstance(node, COMP_LOOPS)
            if is_loop or has_comp:
                stack.append(type(node).__name__)
            if isinstance(node, ast.Call):
                nm = (node.func.attr if isinstance(node.func, ast.Attribute)
                      else getattr(node.func, "id", None))
                if nm in TARGETS:
                    seen += 1
                    if stack:
                        bad.append(f"{f.name}:{node.lineno} {nm} (루프 {'/'.join(stack)})")
            for c in ast.iter_child_nodes(node):
                walk(c)
            if is_loop or has_comp:
                stack.pop()

        walk(tree)

    # ★공허진리 방지 — 호출부를 하나도 못 찾으면 이 락은 무엇이든 통과한다
    assert seen >= 5, f"유료 리졸버 호출부 {seen}곳 — 조회기가 죽었다"
    assert not bad, (
        f"유료 리졸버가 **루프 안**에서 호출된다(요청당 N회 = 과금 N배): {bad}\n"
        "→ 다필지·배치가 필요하면 리졸버 밖에서 한 번 부르고 결과를 재사용하라.")


@pytest.mark.xfail(strict=True, reason=(
    "★부채 — 루프 금지 락이 **직접 호출부만** 본다. 얇은 래퍼를 거쳐 루프 안에서 부르면 "
    "통과한다(4차 적대 리뷰 실측). 계획서 §5 는 이 락을 «다필지·배치 경로가 생기면 "
    "빨개진다» 로 선언했는데, **배치를 쓰는 가장 자연스러운 형태가 바로 그 래퍼**다. "
    "닫으려면 호출 그래프 1홉을 따라가야 하고 그건 이 PR 범위를 넘는다 — "
    "**닫지 못한 것을 닫았다고 하지 않으려고** 초록 안에 드러낸다."))
def test_debt_loop_lock_does_not_follow_wrappers() -> None:
    """래퍼 경유 호출도 루프 금지 락이 잡는가 — **지금은 못 잡는다**."""
    import ast as _ast

    src = _RESOLVER.read_text(encoding="utf-8")
    tree = _ast.parse(src)
    # 이 파일 안에서 «리졸버를 부르는 함수»를 1홉 따라가는 로직이 락에 있는가
    lock = (_API / "tests" / "test_sale_price_resolver_ssot.py").read_text(encoding="utf-8")
    assert "호출 그래프" in lock and "1홉" in lock.split("부채")[0], "1홉 추적이 구현됐다면 이 부채는 닫힌다"
    assert tree is not None
