"""추론된 용도지역은 **종합분석 출력까지** 그 사실을 달고 간다 (2026-08-23).

## 왜 이 파일이 필요한가 — 마지막 한 홉이 비어 있었다

라이브 관측(`platform_events.zone_source_observation`)에서 **3건 중 1건**이
`keyword_inference` 였다 — PNU 를 못 얻어 **주소 문자열에서 용도지역을 추론**한 것이다.
그 값이 건폐율·용적률·개발유형·사업성을 전부 좌우한다.

    {"has_pnu": false, "inferred": true,
     "zone_type": "제2종일반주거지역", "zone_source": "keyword_inference"}

고지 사슬은 이렇게 이어진다:

    auto_zoning_service   경고를 붙인다 (ZONE_INFERENCE_WARNING)
        ↓
    land_info_service     실조회로 덮어쓰면 경고를 뗀다 / 아니면 들고 간다
        ↓
    ComprehensiveAnalysisService.analyze()   ← ★**이 홉만 잠겨 있지 않았다**
        ↓
    ComprehensiveAnalysisPanel   result.warnings 를 전량 렌더한다

`tests/test_zone_provenance.py` 는 위 두 층까지 태운다. 마지막 홉
(`analyze()` 결과 dict 의 `"warnings"` 키)은 **아무도 안 보고 있었다** —
그 한 줄이 사라지면 화면에서 경고가 조용히 없어지고, 사용자는 **지어낸 용도지역을
조회된 사실로** 읽는다. 실패 방식이 침묵이라 아무도 모른다.

## 왜 실행으로 태우는가

소스 검사(`"warnings"` 문자열 grep)는 **주석 처리·키 바꿔치기 변이에 뚫린다**
(이 저장소가 반복해 데인 형태). `analyze()` 는 외부 조회를 `collect_comprehensive`
한 곳에서 받으므로, **그 하나만 스텁하면 오프라인에서 실제로 돈다**(실측 2.7초).
그래서 스텁이 검증 대상 층을 우회하지 않는다 — 태우는 것은 진짜 `analyze()` 다.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

import pytest  # noqa: E402

from app.services.land_intelligence.comprehensive_analysis_service import (  # noqa: E402
    ComprehensiveAnalysisService,
)
from app.services.zoning.auto_zoning_service import ZONE_INFERENCE_WARNING  # noqa: E402

ADDRESS = "경기도 어딘가 123-4"


def _base(*, inferred: bool) -> dict:
    """`collect_comprehensive` 가 돌려주는 모양의 최소 페이로드.

    ★두 모집단이 **실제로 다른 값**을 내야 배선 변이가 죽는다 —
      추론(경고 있음) / 실조회(경고 없음)를 나란히 둔다.
    """
    return {
        "address": ADDRESS,
        "zone_type": "제2종일반주거지역",
        "zone_source": "keyword_inference" if inferred else "vworld_ned",
        "warnings": [ZONE_INFERENCE_WARNING] if inferred else [],
        "land_area_sqm": 1000.0,
        "pnu": None if inferred else "4111110100100230000",
        "coordinates": None,
        "zone_limits": None,
        "special_districts": [],
        "local_ordinance": None,
        "nearby_transactions": None,
        "infrastructure": None,
    }


async def _analyze(inferred: bool) -> dict:
    svc = ComprehensiveAnalysisService()

    async def _stub(_address: str, **_kw) -> dict:
        return _base(inferred=inferred)

    # ★외부 조회는 이 한 곳으로 모인다 — 여기만 막으면 `analyze()` 본체는 그대로 돈다.
    svc.land_info.collect_comprehensive = _stub  # type: ignore[method-assign]
    return await svc.analyze(
        ADDRESS, with_senior=False, include_interpretation=False
    )


@pytest.mark.asyncio
async def test_추론된_용도지역_경고가_종합분석_출력까지_살아남는다() -> None:
    """★핵심 — 이 한 홉이 끊기면 화면에서 경고가 **조용히** 사라진다."""
    result = await _analyze(inferred=True)

    # ★공허 진리 가드 — analyze() 가 실제로 돌아 결과를 만들었는지 먼저 본다.
    #   빈 dict 를 돌려주는 구현에서도 "경고가 없다"는 참이 되어 버린다.
    assert result.get("zone_type") == "제2종일반주거지역", (
        f"analyze() 가 기본 페이로드를 싣지 않았다 — 스텁이 안 먹었다: 키 {sorted(result)[:8]}"
    )

    warnings = result.get("warnings")
    assert isinstance(warnings, list), f"warnings 가 리스트가 아니다: {warnings!r}"
    assert ZONE_INFERENCE_WARNING in warnings, (
        "추론 경고가 종합분석 출력에서 사라졌다 — 화면은 지어낸 용도지역을 "
        f"조회된 사실로 보여 준다. 실제 warnings={warnings!r}"
    )


@pytest.mark.asyncio
async def test_실조회_용도지역에는_추론경고가_붙지_않는다_대조군() -> None:
    """★대조군 — 위 락은 *모든 결과에 경고를 다는* 구현에서도 초록이다.

    두 모집단이 **다른 값**을 내야 배선이 잠긴다(경고를 상수로 박는 우회를 막는다).
    """
    result = await _analyze(inferred=False)
    assert result.get("zone_type") == "제2종일반주거지역"
    assert ZONE_INFERENCE_WARNING not in (result.get("warnings") or []), (
        "실조회 용도지역인데 추론 경고가 붙었다 — 경고가 상수처럼 달리고 있다(위양성)"
    )


@pytest.mark.asyncio
async def test_경고_배열이_통째로_유실되지_않는다() -> None:
    """★`warnings` 키 자체가 사라지는 회귀를 따로 본다.

    키가 없으면 프론트(`Array.isArray(result.warnings)`)가 **조용히 렌더를 건너뛴다** —
    "경고가 없다"와 "경고 통로가 끊겼다"가 화면에서 구분되지 않는다.
    """
    result = await _analyze(inferred=True)
    assert "warnings" in result, (
        "출력에 warnings 키가 없다 — 프론트는 이 경우 아무것도 렌더하지 않고, "
        "'경고 없음'과 구분되지 않는다"
    )
