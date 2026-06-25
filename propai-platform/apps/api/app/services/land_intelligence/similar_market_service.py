"""Stage 3 — 유사건축물 시장조사·사업성 연동.

목표 파이프라인 3단계: 건축가능항목(Stage 1)과 사업유형별로, '유사 건축물'(설계 도면
참조 라이브러리)을 찾아 시장조사하고, 용도별 재무모델(feasibility v2 사업성 엔진)로
사업성을 산출한다.

설계 원칙(DRY·무날조·무회귀):
- 사업성 엔진은 신규 작성하지 않는다 — 검증된 auto_recommend_top3(인허가 게이트·특이부지
  BLOCK 차단·실효 far 전파·senior 금융게이트·정직 토지가 신뢰 플래그)를 그대로 재사용한다.
- 빠진 조각 = '유사건축물 시장조사' 레이어. design_drawings 참조 라이브러리
  (search_drawings·시드 1,019건)에서 각 사업유형에 유사 설계 도면을 retrieval로 매칭한다.
  실데이터 — 미확보(임베딩 키 없음·Qdrant 미가용)는 정직하게 빈 목록 + skipped 사유 표기.
- 참조 라이브러리는 공유 시드 tenant 소유다. 사용자 tenant로 필터하면 시드가 빠지므로,
  참조 검색은 시드 tenant로 스코프한다(타 사용자 업로드 도면 교차노출 방지 + 시드 활용).

★무회귀: 본 모듈은 정보만 첨부한다. auto_recommend_top3 출력을 변형하지 않고 각 추천에
  similar_designs 키만 가산한다. 검색 실패는 graceful(빈 목록).
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# 설계 참조 라이브러리(시드 코퍼스) tenant. 배포 사실값이며 env로 오버라이드 가능.
# 시드 1,019건이 이 tenant 소유 — 참조 검색은 이 스코프로 한정(공유 reference·교차노출 방지).
DESIGN_REFERENCE_TENANT_ID = os.getenv(
    "DESIGN_REFERENCE_TENANT_ID", "0f662726-c8ed-48de-ad17-566e6505f183"
)

# 사업유형/개발유형명 → 유사도면 검색 키워드(임베딩 질의 보강). 결정론 매핑.
# Stage 1 product 라벨과 auto_recommend type_name(M01~M15) 양쪽을 커버한다.
_TYPE_KEYWORDS: dict[str, str] = {
    # Stage 1 buildable product 라벨
    "공동주택(아파트)": "아파트 공동주택 평면",
    "주상복합": "주상복합 타워 평면",
    "오피스텔": "오피스텔 평면",
    "업무시설(오피스)": "업무시설 오피스 평면",
    "판매시설(상업)": "상업시설 판매시설 평면",
    "숙박시설": "숙박시설 호텔 평면",
    "단독·다가구주택": "단독주택 다가구 평면",
    "근린생활시설": "근린생활시설 상가 평면",
    "지식산업센터": "지식산업센터 평면",
    "물류시설": "물류창고 평면",
    "공장": "공장 평면",
    # auto_recommend DEVELOPMENT_TYPE_NAMES(M01~M15)
    "재개발": "아파트 공동주택 평면",
    "재건축": "아파트 공동주택 평면",
    "역세권개발": "주상복합 역세권 평면",
    "지역주택조합": "아파트 공동주택 평면",
    "임대협동조합": "공동주택 임대 평면",
    "일반분양": "아파트 공동주택 평면",
    "단독주택": "단독주택 평면",
    "전원주택": "단독주택 전원주택 평면",
    "타운하우스": "타운하우스 연립 평면",
    "도시형생활주택": "도시형생활주택 원룸 평면",
    "공공임대": "공동주택 임대 평면",
    "민간리츠": "공동주택 평면",
}


def _keywords_for(label: str | None) -> str:
    """사업유형/개발유형명 → 유사도면 검색 키워드(매핑 외는 원문)."""
    key = (label or "").strip()
    return _TYPE_KEYWORDS.get(key, key or "건축물 평면")


async def find_similar_designs(
    *,
    zone_type: str | None,
    area_sqm: float | None,
    label: str | None,
    top_k: int = 4,
) -> dict[str, Any]:
    """참조 라이브러리에서 유사 설계 도면 Top-K 검색(실데이터·graceful).

    Returns: {results:[도면 dict], count, skipped_reason, query_label}.
      skipped_reason!=None 이면 임베딩/Qdrant 미가용 → 빈 목록(정직).
    """
    try:
        from app.services.design_ingest.search_service import SiteQuery, search_drawings

        q = SiteQuery(
            zone_type=zone_type,
            # 0/음수 면적은 미산정으로 보고 None(양수만 임베딩 소프트 반영).
            area_sqm=area_sqm if (area_sqm and area_sqm > 0) else None,
            keywords=_keywords_for(label),
            tenant_id=DESIGN_REFERENCE_TENANT_ID,  # 공유 참조 라이브러리 스코프
        )
        # 직접 호출 안전망 — 과대 top_k로 인한 Qdrant 부하 방어(라우터 경로는 기본 4).
        r = await search_drawings(q, top_k=max(1, min(top_k, 20)))
        return {
            "results": r.get("results", []),
            "count": r.get("count", 0),
            "skipped_reason": r.get("skipped_reason"),
            "query_label": label,
        }
    except Exception as e:  # noqa: BLE001 — 검색 실패는 빈 목록(메인 분석 무손상)
        logger.info("유사도면 검색 생략(%s): %s", label, str(e)[:120])
        return {"results": [], "count": 0, "skipped_reason": "error", "query_label": label}


async def attach_similar_designs_to_options(
    options: list[dict[str, Any]],
    *,
    zone_type: str | None,
    area_sqm: float | None,
    top_n: int = 3,
    top_k: int = 4,
) -> list[dict[str, Any]]:
    """Stage 1 buildable_options 상위 top_n개에 similar_designs를 가산(무회귀·가산만).

    각 옵션의 product 라벨 + 옵션 zone(현행/종상향 목표) + 부지면적으로 유사도면을 검색해
    option["similar_designs"]에 첨부한다. 나머지 옵션은 변형하지 않는다.
    """
    if not options:
        return options
    out: list[dict[str, Any]] = []
    for i, opt in enumerate(options):
        o = dict(opt)
        if i < top_n:
            sd = await find_similar_designs(
                zone_type=o.get("zone") or zone_type,
                area_sqm=area_sqm,
                label=o.get("product"),
                top_k=top_k,
            )
            o["similar_designs"] = sd
        out.append(o)
    return out


async def similar_market_feasibility(
    *,
    address: str,
    land_area_sqm: float | None = None,
    region: str = "서울",
    equity_won: int = 10_000_000_000,
    use_llm: bool = False,
    with_senior: bool = True,
    top_n: int = 3,
    top_k: int = 4,
) -> dict[str, Any]:
    """Stage 3 통합 — 사업성(auto_recommend_top3) + 유사건축물 시장조사(설계 참조).

    검증된 사업성 엔진(인허가 게이트·특이부지·senior 금융)을 호출해 사업유형별 Top 추천을
    받고, 상위 top_n개에 유사 설계 도면(참조 라이브러리)을 가산한다. 사업성 수치는 엔진의
    정직 정책(land_price_reliable·tentative·BLOCK)을 그대로 보존한다.

    Returns: auto_recommend_top3 출력 + recommendations[].similar_designs + stage 메타.
    """
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

    svc = FeasibilityServiceV2()
    rec = await svc.auto_recommend_top3(
        address=address,
        land_area_sqm=land_area_sqm,
        region=region,
        equity_won=equity_won,
        use_llm=use_llm,
        with_senior=with_senior,
    )

    zone_type = rec.get("zone_type")
    site_area = rec.get("land_area_sqm") or land_area_sqm
    recommendations = rec.get("recommendations") or []

    # 상위 top_n 추천에 유사 설계 도면 가산(사업성 수치는 불변·가산만).
    for i, r in enumerate(recommendations[: max(0, top_n)]):
        if not isinstance(r, dict):
            continue
        gfa = ((r.get("unit_summary") or {}).get("total_gfa_sqm")) or site_area
        sd = await find_similar_designs(
            zone_type=zone_type,
            area_sqm=gfa,
            label=r.get("type_name") or r.get("development_type"),
            top_k=top_k,
        )
        r["similar_designs"] = sd

    rec["stage"] = "similar_market_feasibility"
    rec["market_research_note"] = (
        "유사건축물 = 설계 참조 라이브러리(시드 코퍼스) 검색 결과(실데이터). 사업성 수치는 "
        "인허가가능 유형별 재무모델(feasibility v2)이며 토지가 신뢰도·특이부지 게이트·잠정치 "
        "표기를 그대로 따른다(가짜 ROI 금지)."
    )
    return rec
