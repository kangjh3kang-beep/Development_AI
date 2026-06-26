"""매스 백본 region 키 도출 — 주소 → 시군구(프론트 lib/region.ts와 **동일 규칙 SSOT**).

★전역전파방지/공용화: mass_templates.region은 '시군구' 라벨로 통일한다. 저장(collect)과 조회(프론트)가
  같은 규칙으로 시군구를 뽑아야 정확 일치(`WHERE region = :region`)로 매칭된다. 라벨이 어긋나면
  영원히 0매칭되는 silent dead feature가 되므로, 저장 측은 입력 라벨을 신뢰하지 않고 **수집된 건축물대장
  주소에서 직접 시군구를 도출**해 정규화한다(프론트는 site.address로 동일 도출 → 항상 일치).

⚠️ apps/web/lib/region.ts의 regionFromAddress와 **규칙을 일치시켜 유지**할 것(구>시>군·특별/광역시 제외).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

_GU = re.compile(r"([가-힣]+구)(?:\s|$|\d)")          # 구(자치구) — 경계로 동/번지 한글과 분리
_SI = re.compile(r"[가-힣]+시")                        # 시(특별/광역시 자체는 아래에서 제외)
_GUN = re.compile(r"([가-힣]+군)(?:\s|$|\d)")          # 군


def region_from_address(address: str | None) -> str | None:
    """주소 → 시군구(구>시>군). 매칭 실패는 None(임의 추정 금지). lib/region.ts와 동일 규칙."""
    s = (address or "").strip()
    if not s:
        return None
    gu = _GU.search(s)
    if gu:
        return gu.group(1)
    for tok in _SI.findall(s):
        if not tok.endswith(("특별시", "광역시")):   # 광역 단위 자체는 표본이 이질적이라 제외
            return tok
    gun = _GUN.search(s)
    if gun:
        return gun.group(1)
    return None


def dominant_region(addresses: Iterable[str | None]) -> str | None:
    """주소 목록에서 가장 빈도 높은 시군구 1개(수집 record 다수의 대표 지역). 없으면 None.

    동률이면 사전순 우선(결정론). 단일 시군구 수집을 전제하나, 혼재 시 다수결로 대표를 정한다.
    """
    counts: Counter[str] = Counter()
    for a in addresses:
        r = region_from_address(a)
        if r:
            counts[r] += 1
    if not counts:
        return None
    # (-빈도, 시군구명) 정렬로 최빈·동률 사전순(결정론).
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
