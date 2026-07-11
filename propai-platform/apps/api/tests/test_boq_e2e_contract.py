"""B3 BOQ 라우터 E2E 계약 테스트 — TestClient 기반 오프라인판 (B6).

simulate_boq_user.py(라이브 서버용)와 동일 시나리오를 서버 없이 검증한다.
실 레지스트리(B1: services/cost/data/boq_master/*.json)·실 엔진(B2)을 사용하며
모킹은 하지 않는다(LLM 0 · 결정론).

계약 가정(B1~B3 명세):
  - B3 라우터 엔드포인트(자체 prefix). 무상태 계산 엔드포인트는 무인증:
      GET  …boq…/summary        (master/summary — 5공종 요약)
      POST …boq…/draft          (gfa_sqm·households 파라메트릭 초안)
      POST …boq…/export         (xlsx 바이트 스트림)
      POST …boq…/apply-cost     (단가 적용 — total* 양수)
    단 …boq…/draft/from-project 는 project_id 로 프로젝트 BIM 을 조회하므로 인증+소유권 필수
    (IDOR 방지, 형제 cost.py 라우터레벨 인증과 동일 계약) — 해당 테스트에서 인증 스텁.
    경로는 app.routes에서 자동탐지하므로 prefix가 /api/v1/boq 가 아니어도 무방.
  - 스케일 규칙: gfa 드라이버 항목 qty == round규칙(qty_sample × 52000/238504).
    round 자릿수는 B2 구현 자유 — 본 테스트는 (a) qty_sample=238504 앵커 항목의
    정확값 52000, (b) gfa 비율로 스케일된 항목들의 round 후보 일치(오차 1e-6)로
    자릿수에 비의존적으로 정밀 검증한다.

기준 수치 출처(정직성): services/cost/data/boq_master/architecture.json —
의정부동 424 주상복합(실적 공내역서 1건, 연면적 238,504㎡, 건축 고유항목 961).
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# ── 시나리오 상수 ──
GFA_SQM = 52000.0
HOUSEHOLDS = 300
SAMPLE_GFA_SQM = 238504.0
GFA_RATIO = GFA_SQM / SAMPLE_GFA_SQM
ANCHOR_NAME = "임시동력+가설전기시설"  # 건축-0013 · spec=연면적기준 · qty_sample=238504
MIN_ARCH_ITEMS = 900
MIN_XLSX_BYTES = 50 * 1024

ARCH_MASTER_PATH = (Path(__file__).resolve().parents[1]
                    / "app" / "services" / "cost" / "data" / "boq_master"
                    / "architecture.json")

# draft/export/apply-cost 요청 본문 후보 — 첫 비-422 응답 채택(B2/B3 키명 변형 흡수)
# B3 정식 계약(중첩 params{gfa_sqm,...})이 최우선 — 평탄형은 레거시 변형 흡수용.
PARAM_BODIES: list[dict[str, Any]] = [
    {"params": {"gfa_sqm": GFA_SQM, "households": HOUSEHOLDS}},
    {"gfa_sqm": GFA_SQM, "households": HOUSEHOLDS},
    {"gfa_sqm": GFA_SQM, "household_count": HOUSEHOLDS},
    {"total_gfa_sqm": GFA_SQM, "households": HOUSEHOLDS},
]

_CACHE: dict[str, Any] = {}  # 모듈 내 draft 응답 캐시(순수 데이터 — 테스트 간 순서 무관)


# ──────────────────────────────────────
# 경로 탐지 · 호출 헬퍼
# ──────────────────────────────────────

def _boq_paths() -> dict[str, tuple[str, str]]:
    """마운트된 앱 라우트에서 BOQ 엔드포인트를 탐지한다. {key: (path, method)}"""
    from apps.api.main import app

    found: dict[str, tuple[str, str]] = {}
    for route in app.routes:
        path = getattr(route, "path", "") or ""
        methods = set(getattr(route, "methods", None) or [])
        if "boq" not in path or "{" in path:
            continue
        if path.endswith("/summary"):
            found.setdefault("summary", (path, "GET" if "GET" in methods else "POST"))
        elif path.endswith("/draft/priced"):
            found.setdefault("priced", (path, "POST"))
        elif path.endswith("/draft/from-project"):
            found.setdefault("from_project", (path, "POST"))
        elif path.endswith("/draft"):
            found.setdefault("draft", (path, "POST" if "POST" in methods else "GET"))
        elif path.endswith("/export"):
            found.setdefault("export", (path, "POST" if "POST" in methods else "GET"))
        elif path.endswith("/apply-cost"):
            found.setdefault("apply_cost", (path, "POST" if "POST" in methods else "GET"))
    return found


def _require_path(key: str) -> tuple[str, str]:
    paths = _boq_paths()
    if key not in paths:
        pytest.fail(
            f"B3 BOQ 라우터 미마운트 — '{key}' 엔드포인트(…boq…/{key.replace('_', '-')}) "
            f"를 app.routes에서 찾지 못함. 탐지된 경로: {paths or '없음'}")
    return paths[key]


def _assert_ok(resp: Any, ctx: str) -> None:
    if resp.status_code in (401, 403):
        pytest.fail(f"{ctx}: 인증 요구(HTTP {resp.status_code}) — "
                    "B3 계약(무인증, 기존 cost.py 라우터 패턴)과 불일치")
    assert resp.status_code == 200, f"{ctx}: HTTP {resp.status_code} — {resp.text[:300]}"


async def _call(client: Any, path: str, method: str,
                bodies: list[dict[str, Any]]) -> Any:
    """본문 후보를 순서대로 시도 — 400/422가 아니면 즉시 채택."""
    resp = None
    for body in bodies:
        if method == "GET":
            resp = await client.get(path, params={
                k: v for k, v in body.items() if isinstance(v, (int, float, str))})
        else:
            resp = await client.post(path, json=body)
        if resp.status_code not in (400, 422):
            return resp
    return resp


async def _ensure_draft(client: Any) -> dict[str, Any]:
    if "draft" not in _CACHE:
        path, method = _require_path("draft")
        resp = await _call(client, path, method, PARAM_BODIES)
        _assert_ok(resp, "draft")
        _CACHE["draft"] = resp.json()
    return _CACHE["draft"]


# ──────────────────────────────────────
# 응답 형태 표준화 (simulate_boq_user.py와 동일 규칙)
# ──────────────────────────────────────

def _norm_disc(raw: str) -> str:
    s = str(raw).lower()
    if "건축" in s or "arch" in s:
        return "architecture"
    if "기계" in s or "mech" in s:
        return "mechanical"
    if "전기" in s or "elec" in s:
        return "electrical"
    if "조경" in s or "land" in s:
        return "landscape"
    if "토목" in s or "civil" in s:
        return "civil"
    return s


def _discipline_names(summary: Any) -> list[str]:
    d = summary.get("disciplines") if isinstance(summary, dict) else None
    if isinstance(d, dict):
        return [str(k) for k in d]
    if isinstance(d, list):
        return [str(e.get("discipline") or e.get("name") or e.get("key")
                    or e.get("file") or "") if isinstance(e, dict) else str(e)
                for e in d]
    return []


def _items_by_discipline(draft: Any) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(draft, dict):
        return out
    disc = draft.get("disciplines")
    if isinstance(disc, dict):
        for k, v in disc.items():
            items = v.get("items") if isinstance(v, dict) else (v if isinstance(v, list) else [])
            out.setdefault(_norm_disc(k), []).extend(
                i for i in (items or []) if isinstance(i, dict))
        return out
    if isinstance(disc, list):
        for e in disc:
            if not isinstance(e, dict):
                continue
            k = e.get("discipline") or e.get("key") or e.get("name") or ""
            out.setdefault(_norm_disc(str(k)), []).extend(
                i for i in (e.get("items") or []) if isinstance(i, dict))
        return out
    items = draft.get("items")
    if isinstance(items, list):
        for i in items:
            if not isinstance(i, dict):
                continue
            k = i.get("discipline") or i.get("disc") or str(i.get("id", ""))[:2]
            out.setdefault(_norm_disc(str(k)), []).append(i)
    return out


def _qty(item: dict[str, Any]) -> float | None:
    for key in ("qty", "quantity", "qty_scaled", "scaled_qty", "qty_draft", "draft_qty"):
        v = item.get(key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("item_name") or "")


def _find_positive_total(obj: Any, depth: int = 0) -> tuple[str, float] | None:
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if (isinstance(v, (int, float)) and not isinstance(v, bool)
                    and "total" in str(k).lower() and v > 0):
                return str(k), float(v)
        for v in obj.values():
            r = _find_positive_total(v, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj[:50]:
            r = _find_positive_total(v, depth + 1)
            if r:
                return r
    return None


def _round_candidates(x: float) -> tuple[float, ...]:
    """B2 round 규칙 자릿수 비의존 후보 — 정수/1~4자리 round·floor·ceil·무반올림."""
    return (float(round(x)), round(x, 1), round(x, 2), round(x, 3), round(x, 4),
            float(math.floor(x)), float(math.ceil(x)), x)


def _load_master_arch_qty_map() -> tuple[dict[tuple[str, str, str], float],
                                         dict[str, list[float]]]:
    """건축 마스터 (name,spec,unit)→qty_sample 정밀맵 + name→[qty_sample] 폴백맵."""
    data = json.loads(ARCH_MASTER_PATH.read_text(encoding="utf-8"))
    by_key: dict[tuple[str, str, str], float] = {}
    by_name: dict[str, list[float]] = {}
    for it in data["items"]:
        qs = it.get("qty_sample")
        if not isinstance(qs, (int, float)):
            continue
        by_key[(it["name"], it.get("spec", ""), it.get("unit", ""))] = float(qs)
        by_name.setdefault(it["name"], []).append(float(qs))
    return by_key, by_name


# ──────────────────────────────────────
# 테스트
# ──────────────────────────────────────

@pytest.mark.asyncio
async def test_master_summary_5공종(client):
    """summary → 200 · 5공종(건축·기계소방·전기통신소방·조경·토목) 확인."""
    path, method = _require_path("summary")
    resp = await (client.get(path) if method == "GET" else client.post(path, json={}))
    _assert_ok(resp, "master/summary")
    names = _discipline_names(resp.json())
    normed = {_norm_disc(n) for n in names}
    assert len(names) == 5, f"공종 수 {len(names)} ≠ 5 — {names}"
    assert normed == {"architecture", "mechanical", "electrical", "landscape", "civil"}, (
        f"5공종 불일치 — {names}")


@pytest.mark.asyncio
async def test_draft_건축_항목수_및_gfa_스케일_정밀(client):
    """draft(gfa 52000·300세대) → 건축 항목 >900 + gfa 드라이버 스케일 정밀 검증.

    (a) 앵커(qty_sample=238504, 연면적기준) qty == 52000 — round 규칙 무관 정확값.
    (b) gfa 비율로 스케일된 항목들: qty == round후보(qty_sample × 52000/238504)
        중 하나와 1e-6 이내 일치(자릿수 비의존 round 규칙 검증).
    """
    draft = await _ensure_draft(client)
    arch = _items_by_discipline(draft).get("architecture", [])
    assert len(arch) > MIN_ARCH_ITEMS, (
        f"건축 초안 항목 {len(arch)}개 ≤ {MIN_ARCH_ITEMS} — "
        f"마스터 961개 대비 누락 과다(draft 응답 공종키: "
        f"{sorted(_items_by_discipline(draft))})")

    # (a) 앵커 정확값
    anchors = [i for i in arch if ANCHOR_NAME in _name(i)]
    assert anchors, f"앵커 항목 '{ANCHOR_NAME}'(건축-0013) 이 draft에 없음"
    anchor_qty = _qty(anchors[0])
    assert anchor_qty is not None, f"앵커 항목에 수량 키 없음 — keys={sorted(anchors[0])}"
    assert abs(anchor_qty - GFA_SQM) <= 1e-6, (
        f"앵커 qty={anchor_qty} ≠ {GFA_SQM} (= 238504 × {GFA_RATIO:.9f}; "
        "어떤 round 규칙으로도 정확히 52000이어야 함)")

    # (b) gfa 드라이버 항목 round 규칙 검증
    by_key, by_name = _load_master_arch_qty_map()
    checked = mismatched = 0
    mismatches: list[str] = []
    for it in arch:
        q = _qty(it)
        if q is None or q <= 0:
            continue
        key = (_name(it), str(it.get("spec") or ""), str(it.get("unit") or ""))
        qs = by_key.get(key)
        if qs is None:
            samples = by_name.get(_name(it), [])
            qs = samples[0] if len(samples) == 1 else None  # 동명 다항목은 모호 — 제외
        if qs is None or qs <= 0:
            continue
        # 드라이버 명시 선별(B2 qty_basis/driver) — 세대·조경 등 비-gfa 제외.
        # 주의: 시뮬 파라미터에서 gfa 비율(0.21803)과 세대 비율(0.21676)이 0.6%
        # 차이라 비율 휴리스틱만으로는 세대 항목이 새어 들어옴(실측) — driver 우선.
        drv = (it.get("qty_basis") or {}).get("driver") or it.get("driver")
        if drv is not None and drv != "gfa":
            continue
        if drv is None and abs(q / qs - GFA_RATIO) > 0.01 * GFA_RATIO:
            continue
        checked += 1
        expected = qs * GFA_RATIO
        if not any(abs(q - c) <= 1e-6 for c in _round_candidates(expected)):
            mismatched += 1
            if len(mismatches) < 5:
                mismatches.append(f"{_name(it)}: qty={q}, qty_sample={qs}, "
                                  f"기대 round({expected})")
    assert checked >= 20, (
        f"gfa 드라이버로 식별된 항목이 {checked}개(<20) — 스케일 로직 또는 "
        "qty 키 매칭 확인 필요")
    assert mismatched == 0, (
        f"round 규칙 불일치 {mismatched}/{checked}건 — 예: {mismatches}")


@pytest.mark.asyncio
async def test_export_xlsx_pk_시그니처_및_크기(client):
    """export → xlsx 바이트: PK\\x03\\x04 시그니처 + 50KB 초과."""
    draft = await _ensure_draft(client)
    path, method = _require_path("export")
    resp = await _call(client, path, method, PARAM_BODIES + [{"draft": draft}])
    _assert_ok(resp, "export")
    content = resp.content
    assert content[:4] == b"PK\x03\x04", (
        f"xlsx PK 시그니처 아님 — 선두 바이트 {content[:8]!r}")
    assert len(content) > MIN_XLSX_BYTES, (
        f"xlsx {len(content):,}B ≤ {MIN_XLSX_BYTES:,}B — 3,997항목 내역서로는 과소")


@pytest.mark.asyncio
async def test_apply_cost_응답키_및_총액_양수(client):
    """apply-cost → 200 · dict 응답 · total* 키 양수."""
    draft = await _ensure_draft(client)
    path, method = _require_path("apply_cost")
    # B3 정식 계약: BoqApplyCostRequest = BoqDraftRequest + project_id(필수)
    bodies = [{**b, "project_id": "sim-e2e"} for b in PARAM_BODIES]
    resp = await _call(client, path, method, bodies + [{"draft": draft}])
    _assert_ok(resp, "apply-cost")
    data = resp.json()
    assert isinstance(data, dict) and data, "apply-cost 응답이 비어있거나 dict 아님"
    total = _find_positive_total(data)
    assert total is not None, (
        "total 포함 키의 양수 값을 찾지 못함 — 최상위 키: " + str(sorted(data)))
    # 단가 출처 정직 표기 — price_source가 있으면 문자열(WP-09: "db"/"fallback" 계열).
    # provenance 등 다른 출처 키는 형태(B3 자유)를 강제하지 않는다(선택 계약).
    if "price_source" in data:
        assert isinstance(data["price_source"], str), "price_source 는 문자열이어야 함"


@pytest.mark.asyncio
async def test_priced_draft_단가결합_커버리지_금액(client):
    """POST /draft/priced → summary.pricing(커버리지) + 금액 보유 항목 + 미결합 빈칸(정직).

    실엔진·실단가 SSOT(모킹 없음). 전기 ref_mat_price/공종키 매핑으로 부분 결합되며,
    매칭 안 된 항목은 단가/금액 None 유지(가짜 단가 금지 — §1 정직성).
    """
    path, method = _require_path("priced")
    resp = await _call(client, path, method, PARAM_BODIES)
    _assert_ok(resp, "draft/priced")
    data = resp.json()
    pricing = (data.get("summary") or {}).get("pricing") or {}
    # 결정론: 커밋된 마스터(의정부424)는 전기 ref_mat_price 1,025항목을 보유하므로
    # priced_count>0 은 비-플레이키한 회귀 가드(0이면 단가결합 경로가 깨진 것).
    assert isinstance(pricing.get("priced_count"), int) and pricing["priced_count"] > 0, (
        "단가 결합 항목 0건 — 전기 ref_mat_price/공종키 매핑 확인")
    assert 0 <= pricing.get("coverage_pct", -1) <= 100  # 커버리지 범위 정합(보편 불변식)
    assert pricing.get("total_items", 0) >= pricing["priced_count"]
    assert isinstance(pricing.get("coverage_pct"), (int, float))

    items = [it for lst in _items_by_discipline(data).values() for it in lst]
    priced_items = [it for it in items if it.get("price_source")]
    assert priced_items, "price_source 보유 항목 없음"
    amounts = [it for it in priced_items
               if isinstance(it.get("amount"), (int, float)) and it["amount"] > 0]
    assert amounts, "금액(amount) 양수 항목 없음"
    # 미결합 항목은 단가·금액 None(가짜 단가 금지)
    unpriced = [it for it in items if it.get("price_source") is None]
    if unpriced:
        assert unpriced[0].get("amount") is None, "미결합 항목에 금액이 채워짐(정직성 위반)"


@pytest.mark.asyncio
async def test_from_project_bim_병합_정직_폴백(client):
    """POST /draft/from-project(BIM 미보유 프로젝트) → bim_merge 통계 + 전 항목 parametric.

    BIM 물량이 없으면 가짜 실측을 만들지 않고 parametric(추정)을 유지한다(§1 정직성).
    ★from-project 는 project_id 로 프로젝트 BIM 을 조회하므로 인증+소유권 필수(IDOR 방지) —
    e2e 앱에 get_current_user/get_db 를 스텁(비-UUID project_id → 소유권검사 db 미접근).
    """
    from types import SimpleNamespace

    from app.services.auth.auth_service import get_current_user
    from apps.api.database.session import get_db
    from apps.api.main import app

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(tenant_id="e2e", id="e2e-user")
    app.dependency_overrides[get_db] = lambda: None
    try:
        path, method = _require_path("from_project")
        bodies = [{**b, "project_id": "e2e-no-bim"} for b in PARAM_BODIES]
        resp = await _call(client, path, method, bodies)
        _assert_ok(resp, "draft/from-project")
        data = resp.json()
        bm = (data.get("summary") or {}).get("bim_merge") or {}
        assert "bim_rows_count" in bm and "by_source" in bm, "bim_merge 통계 누락"
        assert bm.get("bim_matched_count", 0) == 0  # BIM 0건 → 매칭 0
        items = [it for lst in _items_by_discipline(data).values() for it in lst]
        assert items, "항목 없음"
        srcs = {it.get("qty_source") for it in items}
        # BIM 0건 → 가짜 'bim' 출처를 만들면 안 됨(§1 정직). 'user'(사용자 실입력)는 허용.
        assert "bim" not in srcs, f"BIM 미보유인데 'bim' 출처 혼입(허위 실측): {srcs}"
        assert srcs <= {"parametric", "user"}, f"예상 밖 qty_source: {srcs}"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_db, None)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
