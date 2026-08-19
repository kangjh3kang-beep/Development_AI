"""조례의 **조건부 값**을 조문 제목으로 분류하고, 부지 조건과 매칭한다.

【무엇을 푸는가 — 이 캠페인의 원래 목표】
조례는 `용도지역 → 값 하나` 가 아니라 **`용도지역 × 조건 → 값들`** 이다. 오산시 조례에서
`자연녹지지역` 은 6개 조에 나오고 건폐율이 여러 개다(실측):

    제45조① 16호   20%  ← 기본(정답)
    제45조        30%  주유소·액화석유가스 충전소 / 30% 유원지 · 20% 공원 / 30% 학교
    제46조        30%  그 밖에 용도지구·구역 등
    제48조        80%  방화지구
    제49조        40%  기존 공장 증축
    제50조        30%  성장관리방안 수립지역

파서는 기본값을 골라내고 나머지를 `conditional` 로 보관하는 데까지 왔다. 그런데 그 값들이
**파서 함수 밖으로 나가지 못했다**(`_parse_bcr_far_from_text` 반환 계약에 키가 없었다) —
"소비처 0" 보다 한 단계 이른 상태다. 이 모듈이 그 값에 **조건 이름**을 붙여 밖으로 내보내고,
부지 조건과 맞춰 준다.

【★분류 앵커는 조제목이다 — 조각 텍스트가 아니다(실측)】
조건부 조각의 앞부분은 용도지역명 **뒤**에서 잘려 시작한다("에서는 건폐율을 30퍼센트…").
조건을 말하는 문구는 그 **앞**, 조제목에 있다: `제50조(성장관리방안 수립지역에서의 건폐율 완화)`.
그래서 가장 가까운 앞선 `제NN조(제목)` 을 앵커로 삼는다.

【★★함정 — 조건부가 곧 완화는 아니다】
오산시 `제47조(건폐율의 **강화**)` 가 실재한다. 조건부 값을 무조건 완화로 취급하면
**기본값보다 낮은 값을 상향 여지로 표시**하는 과대낙관이 된다. 방향(`direction`)을 함께 낸다.

【★적용하지 않는다 — #704 와 같은 계약】
조건 충족 여부를 우리가 확인할 수 있는 것은 **부지 designation 으로 판별되는 것뿐**이다.
건축물 용도(주유소·학교·유원지)·연혁(기존 공장) 조건은 **설계가 정해져야** 판정된다.
그래서 이 모듈은 `applied: False` 로 **후보만** 내고, 실효값은 건드리지 않는다.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.zoning.district_regime import _norm, is_growth_management_plan

# 조제목 → 조건 종류. **부지 designation 으로 판별 가능한 것**과 그렇지 않은 것을 가른다.
#   site  = 부지가 그 구역/지구에 속하는가로 판정(우리가 측정 가능)
#   use   = 건축물 용도·연혁으로 판정(설계가 정해져야 안다 — 측정 불가)
#   base  = 기본 조문(조건 아님)
_ARTICLE_RULES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    # (조제목 키워드, condition_key, kind)
    (("성장관리방안", "성장관리계획"), "growth_management_plan", "site"),
    (("방화지구",), "fire_district", "site"),
    (("용도지구", "용도구역"), "designated_district", "site"),
    (("기존 공장", "기존공장"), "existing_factory", "use"),
    (("경관지구",), "landscape_district", "site"),
)

# 조제목이 **강화**를 말하면 그 값은 상향 여지가 아니다(오산시 제47조 실재).
_STRENGTHEN_TOKENS: tuple[str, ...] = ("강화", "축소", "제한")

_ARTICLE_RE = re.compile(r"제(\d+)조(?:의\s*\d+)?\s*\(([^)]{1,60})\)")


def find_article(section: str, pos: int) -> dict[str, Any] | None:
    """`pos` 직전의 가장 가까운 `제NN조(제목)` 를 찾는다. 없으면 None."""
    last = None
    for m in _ARTICLE_RE.finditer(section, 0, max(pos, 0)):
        last = m
    if not last:
        return None
    return {"article": f"제{last.group(1)}조", "article_title": last.group(2).strip()}


def classify_article(article_title: str | None) -> tuple[str, str, str]:
    """조제목 → (condition_key, kind, direction).

    direction: 'relax'(완화 추정) | 'strengthen'(강화 — 상향 여지 아님)
    kind:      'site' | 'use' | 'unknown'
    """
    title = (article_title or "").strip()
    direction = "strengthen" if any(t in title for t in _STRENGTHEN_TOKENS) else "relax"
    for keywords, key, kind in _ARTICLE_RULES:
        if any(k in title for k in keywords):
            return key, kind, direction
    return "unclassified", "unknown", direction


def match_site_conditions(
    conditional_limits: Any, districts: Any
) -> dict[str, Any]:
    """조건부 값 × 부지 designation → 매칭 결과.

    Returns:
        `{"matched": [...], "unmatched_site": [...], "undecidable": [...], "applied": False}`

        · matched      — 부지 조건이 **실제로 충족**된 것(designation 으로 확인)
        · unmatched_site — 부지 조건이지만 이 필지는 해당 없음
        · undecidable  — 건축물 용도·연혁 조건이라 **설계 없이는 판정 불가**
        ★`applied: False` — 후보일 뿐 적용값이 아니다(#704 `conditional_ceiling` 과 같은 계약).
    """
    rows = [d for d in (districts if isinstance(districts, (list, tuple)) else [])]
    names = [_norm(d) for d in rows]
    has_growth_plan = any(is_growth_management_plan(d) for d in rows)

    out: dict[str, list[dict[str, Any]]] = {
        "matched": [], "unmatched_site": [], "undecidable": [],
    }
    for item in conditional_limits or []:
        if not isinstance(item, dict):
            continue
        key, kind = item.get("condition_key"), item.get("condition_kind")
        if item.get("direction") == "strengthen":
            # 강화 조항은 상향 여지가 아니다 — 매칭 대상에서 제외하고 그대로 알린다.
            out["undecidable"].append({**item, "why": "강화 조항 — 상향 여지가 아님"})
            continue
        if kind != "site":
            out["undecidable"].append({
                **item,
                "why": "건축물 용도·연혁 조건 — 설계가 정해져야 판정 가능",
            })
            continue
        if _site_condition_holds(key, item, names, has_growth_plan):
            out["matched"].append(item)
        else:
            out["unmatched_site"].append(item)

    return {**out, "applied": False}


def _site_condition_holds(
    key: str | None, item: dict[str, Any], names: list[str], has_growth_plan: bool
) -> bool:
    """부지 designation 으로 이 조건이 충족되는가.

    ★`성장관리방안`(조례 구 명칭)은 국토계획법 **성장관리계획구역** 지정으로 판정한다 —
      수도권 `성장관리권역` 은 `is_growth_management_plan` 이 이미 배제한다(PR #703).
    """
    if key == "growth_management_plan":
        return has_growth_plan
    if key == "fire_district":
        return any("방화지구" in n for n in names)
    if key == "landscape_district":
        return any("경관지구" in n for n in names)
    if key == "designated_district":
        # 조제목이 '그 밖에 용도지구·구역 등' 이라 어느 지구인지 조문 본문의 나열에 달렸다.
        # 나열 항목을 우리가 신뢰성 있게 못 가르므로 **충족으로 단정하지 않는다**(보수측).
        return False
    return False
