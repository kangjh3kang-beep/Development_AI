"""토지특성(공부) 원천 → 소비 형태로 옮기는 **단일 투영**.

## 왜 공용인가 (2026-09-03 실측)

`vworld_service.get_land_characteristics` 는 **11필드**를 준다. 그런데 그것을 받는
**두 파이프가 각각 다르게 깎고 있었다**:

    batch  job_runner.resolve_pnu_status  → source·land_category·zone_type          (3)
    excel  parcel_excel_service._enrich_fill → area_sqm·zone_type·official_price… (일부)

둘 다 `road_side`(맹지 판정의 축) · `terrain_*` · `land_use_situation` 을 **버렸다.**
★한쪽만 넓히면 **두 파이프의 필드 집합이 갈라진다** — 같은 필지가 진입점에 따라 다른 내용을
갖게 되고, 나중에 합칠 때 더 비싸진다(저장소 §전역 전파방지).

★**손 목록이 아니라 파생**이다. 원천이 필드를 늘리면 여기가 자동으로 따라간다.
빼는 것만 `_DROP` 에 **사유와 함께** 적는다(fail-open 이 아니라 명시적 제외).
"""

from __future__ import annotations

from typing import Any

# 원천 키 중 옮기지 않는 것 — **이유를 함께 적는다.**
_DROP: dict[str, str] = {
    "pnu": "소비 측 레코드가 이미 pnu 를 갖는다(중복 적재 금지)",
}


def project_land_characteristics(chars: dict[str, Any] | None) -> dict[str, Any]:
    """토지특성 원천 dict → 소비용 dict(파생형).

    `None`/빈 dict 는 빈 dict 를 준다 — **0 이나 빈 문자열로 지어내지 않는다.**
    """
    if not chars:
        return {}
    return {k: v for k, v in chars.items() if k not in _DROP}


def source_keys(chars: dict[str, Any] | None) -> set[str]:
    """이 투영이 옮겨야 할 키 집합(락이 파생형으로 대조할 때 쓴다)."""
    return set(project_land_characteristics(chars))


# 토지임야목록에서 옮길 필드 — **파생이 아니라 선별**이다(원천이 15+필드라 전부 싣지 않는다).
#   ★선별한 이유를 적는다: 이 넷은 **토지작업 판단에 직접 쓰인다.**
LEDGER_PICK = {
    "regstrSeCodeNm": "대장구분(토지대장/임야대장)",
    "posesnSeCodeNm": "소유구분 — 협의매수 상대방의 종류",
    "cnrsPsnCo": "공유인수 — 많을수록 협의매수가 어렵다",
    "lastUpdtDt": "데이터기준일자 — 공부는 시점 문서다",
}


def ledger_fields(ledger: list[dict] | None) -> dict[str, Any]:
    """토지임야목록 첫 행에서 판단에 쓰는 필드만 옮긴다. 없으면 빈 dict(지어내지 않는다)."""
    if not ledger:
        return {}
    row = ledger[0]
    return {k: row[k] for k in LEDGER_PICK if row.get(k) not in (None, "")}


def is_shared_parcel(ledger: list[dict] | None) -> bool:
    """대장의 `cnrsPsnCo`(공유인 수)가 **2 이상**인가. 못 읽으면 False(부르지 않는다)."""
    if not ledger:
        return False
    try:
        return int(str(ledger[0].get("cnrsPsnCo") or "0").strip()) > 1
    except (TypeError, ValueError):
        return False


def co_owner_summary(rows: list[dict] | None) -> dict[str, Any]:
    """공유자 연명부 → **구성 요약**. 성명은 없다(개인정보 제외 API).

    ★「수」는 `ladfrlList.cnrsPsnCo` 가 이미 준다. 여기서 더하는 것은 **구성**이다 —
      전원 개인인지, 법인이 끼었는지, **국·공유가 섞였는지**. 셋은 매입 절차가 다르다.
    ★`None`(조회 못 함)과 `[]`(공유 아님)을 뭉개지 않는다.
    """
    if rows is None:
        return {}
    dist: dict[str, int] = {}
    for r in rows:
        kind = str(r.get("posesnSeCodeNm") or "").strip() or "미상"
        dist[kind] = dist.get(kind, 0) + 1
    out: dict[str, Any] = {"co_owner_count": len(rows), "co_owner_kinds": dist}
    # ★국·공유가 섞이면 협의매수가 아니라 공유재산법 절차다 — 그 신호를 **따로** 낸다.
    #   («법인 포함»과 같은 칸에 두면 절차가 다른 것이 한 칸에 묻힌다.)
    out["has_public_share"] = any(("국" in k or "공유" in k) for k in dist)
    return out
