"""표본 **감쇠 사슬** — 원본 몇 건이 어디서 얼마나 깎여 화면의 N 이 됐는지 한 줄로.

## 왜

화면 감사 실측(계획서 `PLAN_analysis_premise_audit_layer_2026-08-24.md` **D9**):
지도에 실거래가 **6곳** 떴는데 원본은 **894건**이었다. 깎인 사유는 응답에 **다 들어 있었지만
여섯 군데에 흩어져** 있었다(`geocode_precut_count` · `groups_evaluated_count` ·
`coords_unresolved_count` · `radius_filtered_out_count` · 카테고리별 `precut` ·
`display_cap_impact`). 사용자는 그것을 조립할 수 없다.

★**"숫자가 없다"가 아니라 "합쳐서 말하는 자리가 없다"** 였다. 그래서 이 모듈은
**아무것도 재계산하지 않는다** — 이미 조립된 응답에서 읽어 사슬로 엮기만 한다.

## 단위 (★여기서 틀리면 그럴듯하게 맞는 거짓말이 된다)

아래 네 카운터는 **전부 그룹(group) 단위**다(소스 실측 — `nearby_map_service`):

    geocode_precut         553·583  그룹
    groups_evaluated       756·783  그룹
    coords_unresolved      758·780  그룹
    filtered_out           757·793  그룹

★같은 응답의 `geocode_failure_breakdown`·`geocode_attempted_count` 는 **질의(query) 단위**라
이 사슬에 **섞지 않는다**. 서비스 주석(≈1903행)이 바로 그 혼동을 경고하고 있다.

## 자기검산

라이브 실측(2026-08-25 · 역삼동 736 · 1000m)에서 두 갈래가 **독립적으로 일치**했다:

    카테고리별 groups_cut 합 1761  ==  최상위 geocode_precut_count 1761
    카테고리별 groups_before 합 2350  ==  precut 1761 + evaluated 554 + unresolved 35

그래서 `reconciles=False` 면 **숫자를 조용히 맞추지 않고 불일치를 신고**한다 —
맞춰 버리면 계기가 고장난 것을 "깨끗하다"로 읽게 된다.
"""

from __future__ import annotations

from typing import Any

__all__ = ["build_sample_attenuation"]


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def build_sample_attenuation(payload: dict[str, Any]) -> dict[str, Any] | None:
    """이미 조립된 nearby-map 응답에서 감쇠 사슬을 엮는다(재계산 0).

    반환 None — 사슬을 말할 근거가 없을 때(무목업: 없는 것을 만들지 않는다).
    """
    if not isinstance(payload, dict):
        return None
    cats = payload.get("categories")
    if not isinstance(cats, dict) or not cats:
        return None

    precut = _int(payload.get("geocode_precut_count"))
    evaluated = _int(payload.get("groups_evaluated_count"))
    unresolved = _int(payload.get("coords_unresolved_count"))
    filtered = _int(payload.get("radius_filtered_out_count"))
    shown = sum(len(c.get("groups") or []) for c in cats.values() if isinstance(c, dict))

    # 원본은 **추정하지 않는다** — 카테고리별 `groups_before` 합이 권위값이다.
    source = sum(
        _int((c.get("precut") or {}).get("groups_before"))
        for c in cats.values() if isinstance(c, dict)
    )
    if source <= 0:
        return None

    # ★★2026-08-25 교정 — 라이브 검증이 **내 검산이 공허했음**을 드러냈다.
    #
    #   종전 모델: shown = (evaluated − filtered) − display_cap  이고
    #             display_cap = max(0, (evaluated − filtered) − shown)  ← **잔차**
    #   잔차로 정의하면 `reconciles` 가 **구성상 항상 참**이 된다(잔차가 음수가 될 때만 깨진다).
    #   즉 자기검산이 **모델 오류를 흡수**하고 있었다 — 내가 경고하던 바로 그 함정이다.
    #
    #   실측이 그것을 깼다(제천 모산동 123-1):
    #       source 238 · precut 0 · evaluated 182 · unresolved 56 · filtered 180 · shown **58**
    #       반경 안 = 182 − 180 = **2** 인데 표시가 **58** — 잔차가 음수라 검산이 붕괴했다.
    #   원인: **좌표 미확보 그룹이 버려지지 않고 표시 경로에 들어간다**
    #       (카테고리 실측: house_trade `located=0` 인데 `shown=19` · land_trade `shown=28`).
    #   → `unresolved` 는 **차감이 아니라 참고**다. 그리고 표시 상한은 **실제 카운터**
    #     (`capped_group_count`)를 쓴다.
    #
    #   두 모집단으로 검증했다(한쪽만 맞는 모델은 모델이 아니다):
    #       역삼동736  현행 일치(우연 — 잔차가 흡수) · 교정 **일치**
    #       제천 모산동 현행 **불일치** · 교정 **일치**
    #   ★역삼동에서 총합은 우연히 같았지만 **귀속이 틀렸다**(잔차cap 37 = 실제cap 73 − 미확보 36)
    #     — 표시 상한으로 깎인 36곳을 "좌표 미확보"라고 말하고 있었다.
    in_radius = evaluated - filtered
    display_capped = sum(
        _int(c.get("capped_group_count")) for c in cats.values() if isinstance(c, dict)
    )

    stages = [
        {"key": "precut", "label": "지오코딩 사전컷", "dropped": precut,
         "reason": "카테고리당 지오코딩 예산 상한 — 좌표 조회 자체를 시도하지 않았습니다"},
        {"key": "radius", "label": "반경 밖", "dropped": filtered,
         "reason": f"요청 반경 {_int(payload.get('radius_m'))}m 밖"},
        {"key": "display_cap", "label": "표시 상한 절단", "dropped": display_capped,
         "reason": "지도 표시 상한 — 계산에는 쓰였으나 화면에는 그리지 않았습니다"},
    ]
    # ★차감이 **아니다** — 좌표를 못 얻어 반경 판정을 못 했을 뿐, 표시에는 남는다.
    #   차감으로 세면 "제외됐다"는 거짓이 되고 사슬도 깨진다(위 실측).
    unlocated_note = None
    if unresolved > 0:
        unlocated_note = (
            f"이 중 {unresolved:,}곳은 좌표를 확보하지 못해 **반경 판정을 하지 못했습니다**"
            "(국토부 지번 마스킹 등). 제외된 것이 아니라 거리로 거르지 못한 채 표시됩니다."
        )

    # ★검산: 원본 − 각 단계 = 표시. 어긋나면 **맞추지 말고 신고**한다.
    accounted = source - sum(s["dropped"] for s in stages)
    reconciles = accounted == shown

    dropped_total = source - shown
    pct = round(dropped_total / source * 100, 1) if source else 0.0
    parts = " · ".join(f"{s['label']} {s['dropped']:,}" for s in stages if s["dropped"] > 0)
    headline = (
        f"원본 {source:,}곳 중 {shown:,}곳을 지도에 표시했습니다"
        f"({pct}% 제외 — {parts})." if parts else
        f"원본 {source:,}곳을 모두 표시했습니다."
    )

    out: dict[str, Any] = {
        "unit": "group",   # ★질의 단위 카운터와 섞지 말 것
        "unlocated_group_count": unresolved,
        "unlocated_note": unlocated_note,
        "in_radius_group_count": in_radius,
        "source_group_count": source,
        "shown_group_count": shown,
        "dropped_total": dropped_total,
        "dropped_pct": pct,
        "stages": stages,
        "headline": headline,
        "reconciles": reconciles,
    }
    if not reconciles:
        out["reconcile_mismatch"] = {
            "expected_shown": accounted, "actual_shown": shown,
            "delta": accounted - shown,
            "note": ("감쇠 사슬이 표시 수와 맞지 않습니다 — 계기가 어긋났다는 뜻이므로 "
                     "표시 수를 신뢰하되 사슬은 참고로만 보십시오."),
        }
    return out
