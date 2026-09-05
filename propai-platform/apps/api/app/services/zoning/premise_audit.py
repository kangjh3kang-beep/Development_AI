"""전제 감사 — **변형관계(metamorphic relation)** 레지스트리.

## 왜 이 층이 필요한가

이 저장소의 결함은 대개 *"각각은 정상인데 **조합**이 틀린"* 형태다. 라이브 실측(2026-08-24):

    dominant_zone   제2종일반주거지역   (면적가중)          ← 정상
    scenario.site   제2종일반주거지역   far 250 / bcr 60    ← 정상
    scenario.top3   **자연녹지지역**    far 100 / bcr 20    ← **자기 zone 과는 정합**

`top3` 의 한도는 **자기가 고른 zone 과 완벽히 일치**한다. 그래서 **단일 경로 자기검사로는
원리적으로 못 잡는다.** 잡히는 것은 **경로 사이의 관계**를 볼 때뿐이다.

## 왜 "정답"이 필요 없는가 (오라클 문제)

이 부지의 정답(적정 사업모델·실제 인허가 결과)은 시스템 밖에 있고 나중에야 안다.
그래서 "출력이 옳은가"는 물을 수 없다. 대신 **입력↔출력의 관계**를 묻는다 —
보존·단조성·경로 무관성·멱등성. 컴파일러·DB·자율주행에서 확립된 기법이다.

## 설계 원칙

- **값을 고치지 않는다.** 위반은 **말한다**(고지 + 등급 강등). 자동 교정은 어느 쪽이 옳은지
  단정하는 것이고, 그 단정이 틀리면 **더 조용한 결함**이 된다.
- **레지스트리**로 둔다 — 손으로 센 목록은 곧 상한이 된다(§A-4). 새 관계를 추가하면
  호출부 수정 없이 감시망에 들어온다.
- **자기 진단**: 검사를 하나도 못 돌렸으면 그 사실을 반환한다(공허한 초록 금지).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

# 위반 1건 = (관계 이름, 사람이 읽는 설명, 기계가 읽는 근거)
Violation = dict[str, Any]
Relation = Callable[[dict[str, Any]], Violation | None]

_REGISTRY: list[tuple[str, str, Relation]] = []


def relation(key: str, title: str):
    """변형관계를 레지스트리에 등록하는 데코레이터."""
    def deco(fn: Relation) -> Relation:
        _REGISTRY.append((key, title, fn))
        return fn
    return deco


def _f(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


# ── MR-C 경로 무관성 ─────────────────────────────────────────────────────────
@relation("path_invariance_zone", "경로 무관성 — 같은 부지를 두 경로로 보면 같은 용도지역")
def _mr_path_invariance(ctx: dict[str, Any]) -> Violation | None:
    """★오늘의 P0 를 **정답 없이** 잡은 관계.

    같은 부지에 대해 집계 경로(`dominant_zone`)와 시나리오 경로(`top3.zone_type`)가
    다른 용도지역을 말하면, 둘 중 하나는 반드시 틀렸다 — **어느 쪽인지 몰라도** 그것은 안다.
    """
    dom = ctx.get("dominant_zone")
    t3 = ((ctx.get("scenario") or {}).get("top3") or {}).get("zone_type")
    if not dom or dom == "mixed_review_required" or not t3 or dom == t3:
        return None
    return {
        "detail": (
            f"통합 우세 용도지역({dom})과 시나리오 계산 기준({t3})이 다릅니다 — "
            f"개발규모·수익성은 {t3} 기준이며 이 부지의 우세 용도와 일치하지 않습니다."
        ),
        "evidence": {"dominant_zone": dom, "scenario_zone": t3},
    }


# ── MR-D 개수 보존 ──────────────────────────────────────────────────────────
@relation("count_conservation_parcels", "개수 보존 — 계산에 쓴 필지수 == 투입 필지수")
def _mr_count_conservation(ctx: dict[str, Any]) -> Violation | None:
    got = ((ctx.get("scenario") or {}).get("top3") or {}).get("parcel_count")
    want = ctx.get("_request_parcel_count") or ctx.get("parcel_count")
    if got is None or want is None or int(got) == int(want):
        return None
    return {
        "detail": (
            f"시나리오가 {got}필지 기준으로 계산됐는데 투입은 {want}필지입니다 — "
            f"면적과 용도가 서로 다른 모집단에서 왔을 수 있습니다."
        ),
        "evidence": {"scenario_parcel_count": int(got), "requested_parcel_count": int(want)},
    }


# ── MR-A 면적 보존 ──────────────────────────────────────────────────────────
@relation("area_conservation", "면적 보존 — zone_mix 합 == per_parcel 합")
def _mr_area_conservation(ctx: dict[str, Any]) -> Violation | None:
    zm = ctx.get("zone_mix") or []
    pp = ctx.get("per_parcel") or []
    if not zm or not pp:
        return None
    a = sum(_f(z.get("area_sqm")) or 0.0 for z in zm)
    b = sum(_f(p.get("area_sqm")) or 0.0 for p in pp)
    if abs(a - b) <= max(1.0, b * 0.001):      # 1㎡ 또는 0.1% 허용(반올림)
        return None
    return {
        "detail": f"용도지역별 면적 합({a:,.0f}㎡)이 필지 면적 합({b:,.0f}㎡)과 다릅니다.",
        "evidence": {"zone_mix_sum": a, "per_parcel_sum": b},
    }


# ── MR-B 우세 정합 ──────────────────────────────────────────────────────────
@relation("dominant_argmax", "우세 정합 — dominant_zone == 면적 최대 용도지역")
def _mr_dominant_argmax(ctx: dict[str, Any]) -> Violation | None:
    dom = ctx.get("dominant_zone")
    zm = [z for z in (ctx.get("zone_mix") or []) if z.get("zone")]
    if not dom or dom == "mixed_review_required" or not zm:
        return None
    top = max(zm, key=lambda z: _f(z.get("area_sqm")) or 0.0)
    if top.get("zone") == dom:
        return None
    return {
        "detail": f"우세 용도지역이 {dom} 인데 면적 최대는 {top.get('zone')} 입니다.",
        "evidence": {"dominant_zone": dom, "argmax_zone": top.get("zone")},
    }


# ── MR-E 통합 단조성 ────────────────────────────────────────────────────────
@relation("integration_monotonic", "통합 단조성 — 통합면적 >= 최대 단일필지 면적")
def _mr_integration_monotonic(ctx: dict[str, Any]) -> Violation | None:
    pp = ctx.get("per_parcel") or []
    tot = _f((ctx.get("integrated") or {}).get("total_area_sqm"))
    if not pp or tot is None:
        return None
    mx = max((_f(p.get("area_sqm")) or 0.0) for p in pp)
    if tot + 1.0 >= mx:
        return None
    return {
        "detail": f"통합면적({tot:,.0f}㎡)이 최대 단일필지({mx:,.0f}㎡)보다 작습니다.",
        "evidence": {"total_area_sqm": tot, "max_parcel_sqm": mx},
    }


# ── MR-G 면적 출처 일치 ─────────────────────────────────────────────────────
@relation("area_source_agreement", "면적 출처 일치 — 시나리오 면적 == 통합 면적")
def _mr_area_source(ctx: dict[str, Any]) -> Violation | None:
    """면적은 통합값을 쓰면서 용도는 단일필지를 쓰는 **혼종 조합**을 잡는다."""
    t3 = (ctx.get("scenario") or {}).get("top3") or {}
    a = _f(t3.get("land_area_sqm"))
    b = _f((ctx.get("integrated") or {}).get("total_area_sqm"))
    if a is None or b is None or abs(a - b) <= max(1.0, b * 0.001):
        return None
    return {
        "detail": f"시나리오 면적({a:,.0f}㎡)이 통합 면적({b:,.0f}㎡)과 다릅니다.",
        "evidence": {"scenario_area_sqm": a, "integrated_area_sqm": b},
    }


def audit(ctx: dict[str, Any]) -> dict[str, Any]:
    """등록된 모든 변형관계를 돌려 위반 목록을 낸다.

    반환:
      violations : [{relation, title, detail, evidence}]
      checked    : **실행을 시도해 예외 없이 끝난** 관계 수
      registered : 등록된 관계 수
    ★`checked == 0` 이면 "위반 없음"이 **공허**하다 — 호출부가 그 사실을 알 수 있어야 한다.

    ## ★★`checked` 의 뜻 — 여기를 잘못 읽으면 화면이 오경보를 낸다 (2026-09-05 정정)

    ★**종전 이 줄은 거짓이었다**: *"실제로 **판정한** 관계 수(전제 부족으로 건너뛴 것은 제외)"*.
      아래 `checked += 1` 은 **무조건** 실행된다 — 빠지는 것은 **예외를 던진 관계뿐**이다.
      실측(`origin/main`):

          audit(정상ctx) → checked 6 / registered 6
          audit({})      → checked 6 / registered 6      ← **빈 입력에도 6**
          audit(쓰레기)   → checked 6 / registered 6

    ★**「건너뜀」이라는 정보는 원리적으로 존재하지 않는다.** 각 관계가 「전제 부족」과
      「위반 없음」을 **같은 `None`** 으로 반환하기 때문이다
      (`if got is None or want is None or got == want: return None` — 한 분기에 뭉쳐 있다).

    ★그러므로 **`checked < registered` 의 뜻은 「관계가 실행 중 예외로 죽었다」**이지
      「입력이 부족했다」가 아니다. 이 구분이 사용자 화면 문구를 가른다.

    ★**진짜 계약은 처음부터 테스트에 있었다** —
      `tests/test_premise_audit_registry.py` 의 *"빈 입력도 **판정은 시도**해야 한다"*.
      ***선언(독스트링)과 잠금(테스트)이 갈리면 「잠금」이 사실이다.***

    ★**값을 치렀다**: 이 줄을 믿고 화면 축을 세운 `#978` 초판이 **모든 정상 부지**에
      *"부분 판정 5/6 — 나머지는 **입력이 부족해** 건너뛰었습니다"* 라는 **오경보**를 냈다
      (숫자도 사유도 거짓이고 「깨끗함」은 도달 불가였다). 적대 리뷰가 잡았다.

    ★**「건너뜀」을 정말 세고 싶다면** 관계가 그 사실을 **신호해야** 한다(예: 전용 센티널 반환).
      그건 관계 6종과 기존 락 4개를 함께 바꾸는 **별건**이다 — 여기서 조용히 하지 않는다.
    """
    violations: list[Violation] = []
    checked = 0
    for key, title, fn in _REGISTRY:
        try:
            got = fn(ctx)
        except Exception:  # noqa: BLE001 — 관계 하나의 실패가 감사를 죽이지 않는다.
            continue
        checked += 1
        if got:
            violations.append({"relation": key, "title": title, **got})
    return {"violations": violations, "checked": checked, "registered": len(_REGISTRY)}


def registered_relations() -> list[str]:
    """등록된 관계 키(테스트가 **파생**시켜 쓰라 — 손으로 센 목록은 상한이 된다)."""
    return [k for k, _t, _f in _REGISTRY]
