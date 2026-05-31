"""나라장터(G2B) 입찰/낙찰 비즈니스 서비스.

입찰 데이터 수집, AI 키워드 필터링, 낙찰가율 통계, 사업성 분석 연동을 처리한다.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.g2b_bid import G2BAwardStat, G2BBid
from app.schemas.g2b_bid import (
    G2BAwardStatsResponse,
    G2BAwardStatResponse,
    G2BBidFilter,
    G2BBidListResponse,
    G2BBidResponse,
    G2BDashboardStats,
)

logger = logging.getLogger(__name__)

# ── 부동산개발 관련 키워드 사전 ──

INCLUDE_KEYWORDS: list[str] = [
    # ── 정비사업/개발 ──
    "재개발", "재건축", "리모델링", "도시정비", "주택정비", "도시재생",
    "정비사업", "정비구역", "가로주택", "소규모재건축", "주거환경개선",
    "지역주택", "지주택", "재정비촉진", "뉴타운", "역세권개발",
    "도시개발", "택지개발", "지구단위", "도시계획", "기반시설",
    # ── 건축/주거 유형 ──
    "신축", "증축", "개축", "대수선", "건축", "건립", "건설",
    "아파트", "공동주택", "오피스텔", "도시형생활주택", "다세대",
    "다가구", "연립주택", "빌라", "주상복합", "타운하우스",
    "단독주택", "전원주택", "행복주택", "국민임대", "영구임대",
    "매입임대", "전세임대", "임대주택", "분양주택", "주택",
    "기숙사", "생활관", "관사", "사택", "숙소",
    # ── 비주거 건축물 ──
    "상업시설", "근린생활", "판매시설", "업무시설", "사옥", "청사",
    "물류센터", "물류창고", "창고", "공장", "지식산업센터", "데이터센터",
    "복합단지", "복합시설", "주차장", "주차타워", "체육관", "문화시설",
    "강당", "연구소", "연구시설",
    # ── 공종/공사 일반 ──
    "공사", "시공", "토목", "건축공사", "종합공사", "전문공사",
    "철거", "해체", "구조물", "기초", "지정", "파일", "항타",
    "골조", "마감", "방수", "단열", "창호", "커튼월", "외벽",
    "도배", "도장", "타일", "석공", "조적", "미장", "수장",
    "지붕", "판넬", "샌드위치패널", "강구조", "철골", "철근콘크리트",
    "콘크리트", "철근", "레미콘", "거푸집", "비계", "가설",
    "지반", "터파기", "흙막이", "토공", "굴착", "발파", "보강토",
    "옹벽", "포장", "도로", "교량", "상하수도", "관로", "하수",
    "정화조", "우수", "오수", "준설",
    # ── 설비/전기/통신/소방 ──
    "전기", "전기공사", "수배전", "변전", "발전", "태양광", "신재생",
    "설비", "기계설비", "위생설비", "냉난방", "공조", "보일러",
    "급배수", "덕트", "배관", "소방", "소방시설", "스프링클러",
    "정보통신", "통신공사", "네트워크", "정보화", "CCTV", "관제",
    "승강기", "엘리베이터", "에스컬레이터", "리프트",
    # ── 조경/외구/환경 ──
    "조경", "조경공사", "수목", "식재", "정원", "공원", "녹지",
    "환경", "환경공사", "방음", "방진", "토양", "폐기물",
    # ── 인테리어/실내 ──
    "인테리어", "실내건축", "내장", "가구", "집기", "사인",
    # ── 설계/감리/측량/엔지니어링 ──
    "설계", "건축설계", "실시설계", "기본설계", "설계용역", "턴키",
    "감리", "건설사업관리", "CM", "측량", "지적", "안전진단",
    "구조안전", "정밀안전", "내진", "정비계획", "타당성", "기본계획",
    "엔지니어링", "구조계산", "지질조사", "지반조사", "교통영향",
    "환경영향", "경관", "도시설계",
    # ── 자재/조달 (식자재 등 오탐 방지: 단독 '자재' 제외, 복합어만) ──
    "건설자재", "건축자재", "골재", "시멘트", "아스콘",
    "강관", "강판", "PHC", "PC패널", "PC공", "단열재", "방수재", "도료",
    "관급자재", "관급",
    # ── 유지보수/운영 ──
    "보수", "보강", "유지관리", "유지보수", "개보수", "환경개선",
    "노후", "그린리모델링", "에너지효율", "제로에너지",
    # ── 분양/사업 ──
    "분양", "임대", "단지", "주거", "택지", "준공", "공동주택지",
]

# 발주기관 단독으로 부동산개발 입찰로 인정하는 "개발 전담" 기관.
# 교육청·대학교·시설관리공단처럼 비건설 입찰(급식·비품·용역)도 많은 범용기관은 제외 —
# 이들이 발주한 건은 공고명에 건설 키워드가 있을 때만 INCLUDE_KEYWORDS/FACILITY로 포착.
INCLUDE_ORG_KEYWORDS: list[str] = [
    # 중앙 (건설 전담)
    "국토교통부", "건설교통", "행정중심복합도시",
    # 부동산개발 공기업
    "LH", "토지주택", "한국토지주택", "주택도시보증", "HUG", "한국부동산원",
    "한국도로공사", "도로공사", "철도공단", "국가철도", "수자원공사",
    "한국수자원", "농어촌공사", "한국농어촌",
    # 지방 도시·개발·주택공사 (부동산개발 전담)
    "도시공사", "도시개발공사", "주택공사", "도시주택공사",
    "경기주택도시", "경기도시", "인천도시", "부산도시", "대구도시",
    "광주도시", "대전도시", "울산도시", "강원개발공사", "충북개발공사",
    "전남개발공사", "경북개발공사", "제주개발공사", "세종도시", "용인도시",
    "화성도시", "안산도시", "남양주도시",
    # 정비사업 조합 (재개발·재건축)
    "재개발조합", "재건축조합", "정비사업조합", "주택재개발", "주택재건축",
]

CATEGORY_MAP: dict[str, list[str]] = {
    "재개발·재건축": [
        "재개발", "재건축", "정비사업", "주택정비", "도시정비", "도시재생",
        "가로주택", "소규모재건축", "지역주택", "재정비촉진", "뉴타운",
        "주거환경개선", "도시개발", "택지개발",
    ],
    "건축설계": [
        "건축설계", "실시설계", "기본설계", "설계용역", "설계", "턴키",
        "구조계산", "도시설계", "경관",
    ],
    "건축시공": [
        "신축", "증축", "개축", "대수선", "건설", "시공", "공사", "건축공사",
        "종합공사", "골조", "마감", "철거", "해체", "강구조", "철골",
        "철근콘크리트", "구조물",
    ],
    "토목·조경": [
        "토목", "조경", "지반", "터파기", "흙막이", "토공", "굴착", "옹벽",
        "포장", "도로", "교량", "상하수도", "관로", "수목", "식재", "공원",
        "조경공사",
    ],
    "설비·전기": [
        "전기", "전기공사", "수배전", "태양광", "신재생", "설비", "기계설비",
        "냉난방", "공조", "급배수", "소방", "소방시설", "스프링클러",
        "정보통신", "통신공사", "승강기", "엘리베이터", "방수", "단열",
    ],
    "건설자재": [
        "건설자재", "건축자재", "콘크리트", "철근", "레미콘", "골재",
        "시멘트", "아스콘", "창호", "커튼월", "외벽", "단열재", "방수재",
        "관급자재", "관급", "PHC",
    ],
    "감리·측량": [
        "감리", "건설사업관리", "CM", "측량", "지적", "안전진단", "구조안전",
        "정밀안전", "내진", "엔지니어링", "지질조사", "지반조사",
        "교통영향", "환경영향", "타당성",
    ],
    "인테리어·실내건축": [
        "인테리어", "실내건축", "내장", "가구", "집기", "사인", "도배",
        "도장", "타일",
    ],
    "유지보수·리모델링": [
        "리모델링", "그린리모델링", "보수", "보강", "유지관리", "유지보수",
        "개보수", "환경개선", "노후", "에너지효율", "제로에너지",
    ],
    "물류·산업시설": [
        "물류센터", "물류창고", "창고", "공장", "지식산업센터", "데이터센터",
    ],
}


def _classify_tags(text: str) -> list[str]:
    """공고명에서 AI 분류 태그를 추출한다."""
    tags: list[str] = []
    text_lower = text.lower()
    for tag, keywords in CATEGORY_MAP.items():
        for kw in keywords:
            if kw in text_lower:
                tags.append(tag)
                break
    return tags


# 시설명 키워드 — 발주기관명에 흔히 포함돼(예: "○○초등학교") 오탐을 유발하므로
# 공고명(title)에서만 검사한다. "학교 신축공사"는 잡되 "학교가 발주한 급식"은 제외.
FACILITY_KEYWORDS: list[str] = [
    "학교", "초등학교", "중학교", "고등학교", "병원", "의료원", "보건소",
    "도서관", "어린이집", "유치원", "요양시설", "요양원", "복지관", "주민센터",
    "체육관", "수영장", "문화시설", "박물관", "미술관", "공연장",
]


def _is_relevant_bid(title: str, org_name: str = "") -> bool:
    """부동산개발/건설 관련 입찰인지 키워드 기반으로 판단한다.

    - INCLUDE_KEYWORDS: 공사/공종/자재 등 → 공고명에서만 검사(기관명 오탐 방지).
    - FACILITY_KEYWORDS: 학교/병원 등 시설명 → 공고명에 있고 "공사/신축/설계" 등
      건설 행위 키워드가 동반될 때만 인정(시설이 발주한 비건설 입찰 제외).
    - INCLUDE_ORG_KEYWORDS: LH/도시공사 등 → 기관명에서 검사(발주처 기반).
    """
    # 1) 공고명에 건설/공종/자재 키워드 직접 매칭
    for kw in INCLUDE_KEYWORDS:
        if kw in title:
            return True
    # 2) 시설명 + 건설행위 동반 시 인정
    if any(f in title for f in FACILITY_KEYWORDS):
        if any(act in title for act in ("공사", "신축", "증축", "개축", "건립",
                                        "건설", "설계", "리모델링", "보수", "시공",
                                        "개보수", "보강", "조성")):
            return True
    # 3) 발주기관이 부동산개발 전문기관(LH·도시공사 등)
    for kw in INCLUDE_ORG_KEYWORDS:
        if kw in org_name:
            return True
    return False


def _parse_g2b_datetime(raw: Any) -> Optional[datetime]:
    """G2B API 응답의 날짜 문자열을 datetime으로 변환한다."""
    if not raw:
        return None
    s = str(raw).strip()
    for fmt in ("%Y%m%d%H%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y%m%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _safe_int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    try:
        return int(float(str(raw).replace(",", "")))
    except (ValueError, TypeError):
        return None


def _safe_float(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    try:
        return float(str(raw).replace(",", ""))
    except (ValueError, TypeError):
        return None


_SIDO_PATTERN = re.compile(
    r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
)


def _extract_region(raw_item: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    """공고 데이터에서 시/도, 시/군/구를 추출한다.

    공사현장지역(cnstrtsiteRgnNm)을 우선 사용하되, 전국 입찰은 모든 시/도가
    나열되므로(매칭 3개 초과) '전국'으로 처리한다.
    """
    # 공사현장지역을 우선하되, 비어 있으면 수요기관/공고기관명에서 지역을 보강 추출한다
    # (다수 공사 입찰은 cnstrtsiteRgnNm가 비어 있고 기관명에 "대구광역시 달서구" 식으로 지역 포함).
    place = str(
        raw_item.get("cnstrtsiteRgnNm", "")
        or raw_item.get("rgnLmtBidLocplcJdgmBssNm", "")
        or raw_item.get("dminsttNm", "")
        or raw_item.get("ntceInsttNm", "")
        or ""
    )
    if not place:
        return None, None
    matches = _SIDO_PATTERN.findall(place)
    if not matches:
        return None, None
    if len(set(matches)) > 3:
        return "전국", None
    return matches[0], None


class G2BBidService:
    """나라장터 입찰/낙찰 비즈니스 로직."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ──────────────────────────────────────────
    # 데이터 수집 및 저장
    # ──────────────────────────────────────────

    async def upsert_bid_notices(self, raw_items: list[dict[str, Any]]) -> int:
        """수집된 입찰 공고 데이터를 DB에 저장/갱신한다. 부동산 관련 건만 필터링."""
        saved = 0
        # 같은 배치에 동일 bid_notice_no가 중복 등장(공고 정정/페이지 겹침)할 수 있어
        # 아직 flush 전인 신규 레코드를 추적해 UniqueViolation을 방지한다.
        pending: dict[str, G2BBid] = {}
        for item in raw_items:
            title = str(item.get("bidNtceNm", "") or item.get("pblancNm", "") or "")
            org = str(item.get("ntceInsttNm", "") or item.get("dminsttNm", "") or "")

            if not _is_relevant_bid(title, org):
                continue

            notice_no = str(item.get("bidNtceNo", "") or item.get("bfSpecRgstNo", "") or "")
            if not notice_no:
                continue

            bid = pending.get(notice_no)
            if bid is None:
                existing = await self.db.execute(
                    select(G2BBid).where(G2BBid.bid_notice_no == notice_no)
                )
                bid = existing.scalar_one_or_none()

            bid_type = str(item.get("_bid_type", "공사"))
            tags = _classify_tags(title)
            sido, sigungu = _extract_region(item)

            from app.integrations.g2b_client import G2BClient

            if bid is None:
                bid = G2BBid(
                    bid_notice_no=notice_no,
                    bid_notice_nm=title,
                    bid_notice_ord=str(item.get("bidNtceOrd", "") or ""),
                    bid_type=bid_type,
                    category_tags=tags,
                    org_name=org,
                    org_type=self._classify_org_type(org),
                    demand_org_name=str(item.get("dminsttNm", "") or ""),
                    estimated_price=_safe_int(item.get("presmptPrce")),
                    budget_amount=_safe_int(item.get("bdgtAmt")),
                    bid_begin_dt=_parse_g2b_datetime(item.get("bidBeginDt")),
                    bid_close_dt=_parse_g2b_datetime(item.get("bidClseDt")),
                    open_dt=_parse_g2b_datetime(item.get("opengDt")),
                    notice_dt=_parse_g2b_datetime(item.get("bidNtceDt")),
                    region_sido=sido,
                    region_sigungu=sigungu,
                    delivery_place=str(item.get("cnstrtsiteRgnNm", "") or ""),
                    bid_method=str(item.get("bidMethdNm", "") or ""),
                    contract_method=str(item.get("cntrctCnclsMthdNm", "") or ""),
                    qualification=str(item.get("rgnLmtBidLocplcJdgmBssNm", "") or ""),
                    g2b_url=str(item.get("bidNtceDtlUrl", "") or "")
                    or G2BClient.build_g2b_detail_url(notice_no),
                    raw_data=item,
                )
                self.db.add(bid)
                pending[notice_no] = bid
                saved += 1
            else:
                bid.bid_close_dt = _parse_g2b_datetime(item.get("bidClseDt")) or bid.bid_close_dt
                bid.category_tags = tags or bid.category_tags
                bid.updated_at = datetime.utcnow()
                pending[notice_no] = bid

        await self.db.commit()
        logger.info("G2B 입찰 공고 %d건 저장/갱신 완료", saved)
        return saved

    async def update_award_results(self, raw_items: list[dict[str, Any]]) -> int:
        """낙찰 결과로 기존 입찰 공고 레코드를 갱신한다.

        getScsbidListSttus* 는 공고당 낙찰자 1행을 반환하며, 각 행에 낙찰자
        (bidwinnrNm)·낙찰가율(sucsfbidRate)·낙찰금액(sucsfbidAmt)·참가업체수
        (prtcptCnum)가 모두 채워져 있다(라이브 검증: 300행=300공고, 1:1).
        동일 공고가 중복 등장하면 마지막 행 값으로 수렴(멱등).
        """
        updated = 0
        seen: set[str] = set()
        for item in raw_items:
            notice_no = str(item.get("bidNtceNo", "") or "")
            if not notice_no:
                continue

            existing = await self.db.execute(
                select(G2BBid).where(G2BBid.bid_notice_no == notice_no)
            )
            bid = existing.scalar_one_or_none()
            if bid is None:
                continue

            bid.award_price = _safe_int(item.get("sucsfbidAmt"))
            bid.award_rate = _safe_float(item.get("sucsfbidRate"))
            bid.award_company = str(item.get("bidwinnrNm", "") or "")
            bid.award_dt = _parse_g2b_datetime(
                item.get("rlOpengDt") or item.get("fnlSucsfDate")
            )
            bid.bid_count = _safe_int(item.get("prtcptCnum"))
            bid.status = "awarded"
            bid.updated_at = datetime.utcnow()
            if notice_no not in seen:
                seen.add(notice_no)
                updated += 1

        await self.db.commit()
        logger.info("G2B 낙찰 결과 %d건 갱신 완료", updated)
        return updated

    # ──────────────────────────────────────────
    # 조회
    # ──────────────────────────────────────────

    async def list_bids(self, f: G2BBidFilter) -> G2BBidListResponse:
        """입찰 공고 목록을 필터링하여 반환한다."""
        query = select(G2BBid)
        conditions = []

        if f.keyword:
            conditions.append(G2BBid.bid_notice_nm.ilike(f"%{f.keyword}%"))
        if f.bid_type:
            conditions.append(G2BBid.bid_type == f.bid_type)
        if f.region_sido:
            conditions.append(G2BBid.region_sido == f.region_sido)
        if f.region_sigungu:
            conditions.append(G2BBid.region_sigungu == f.region_sigungu)
        if f.status:
            conditions.append(G2BBid.status == f.status)
        if f.category_tag:
            conditions.append(G2BBid.category_tags.any(f.category_tag))
        if f.min_price is not None:
            conditions.append(G2BBid.estimated_price >= f.min_price)
        if f.max_price is not None:
            conditions.append(G2BBid.estimated_price <= f.max_price)
        if f.org_type:
            conditions.append(G2BBid.org_type == f.org_type)
        if f.date_from:
            conditions.append(G2BBid.notice_dt >= f.date_from)
        if f.date_to:
            conditions.append(G2BBid.notice_dt <= f.date_to)

        if conditions:
            query = query.where(and_(*conditions))

        # 총 건수
        count_q = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_q)).scalar() or 0

        # 페이지네이션 + 정렬
        query = query.order_by(G2BBid.notice_dt.desc().nullslast())
        offset = (f.page - 1) * f.page_size
        query = query.offset(offset).limit(f.page_size)

        result = await self.db.execute(query)
        bids = result.scalars().all()

        return G2BBidListResponse(
            items=[G2BBidResponse.model_validate(b) for b in bids],
            total=total,
            page=f.page,
            page_size=f.page_size,
            total_pages=max(1, (total + f.page_size - 1) // f.page_size),
        )

    async def get_bid(self, bid_id: UUID) -> Optional[G2BBid]:
        """입찰 공고 단건 조회."""
        result = await self.db.execute(select(G2BBid).where(G2BBid.id == bid_id))
        return result.scalar_one_or_none()

    async def get_dashboard_stats(self) -> G2BDashboardStats:
        """대시보드 요약 통계를 반환한다."""
        now = datetime.utcnow()
        soon = now + timedelta(hours=48)

        total_active = (await self.db.execute(
            select(func.count()).where(G2BBid.status == "active")
        )).scalar() or 0

        closing_soon = (await self.db.execute(
            select(func.count()).where(
                and_(G2BBid.status == "active", G2BBid.bid_close_dt <= soon, G2BBid.bid_close_dt > now)
            )
        )).scalar() or 0

        thirty_days_ago = now - timedelta(days=30)
        avg_rate_result = await self.db.execute(
            select(func.avg(G2BBid.award_rate)).where(
                and_(G2BBid.award_dt >= thirty_days_ago, G2BBid.award_rate.isnot(None))
            )
        )
        avg_award_rate = avg_rate_result.scalar()

        ai_recommended = (await self.db.execute(
            select(func.count()).where(
                and_(G2BBid.status == "active", G2BBid.ai_risk_score.isnot(None), G2BBid.ai_risk_score <= 50)
            )
        )).scalar() or 0

        total_value = (await self.db.execute(
            select(func.sum(G2BBid.estimated_price)).where(G2BBid.status == "active")
        )).scalar()

        return G2BDashboardStats(
            total_active=total_active,
            closing_soon=closing_soon,
            avg_award_rate=float(avg_award_rate) if avg_award_rate else None,
            ai_recommended_count=ai_recommended,
            total_estimated_value=int(total_value) if total_value else None,
        )

    async def get_award_stats(
        self, bid_type: Optional[str] = None, region_sido: Optional[str] = None
    ) -> G2BAwardStatsResponse:
        """낙찰가율 통계를 조회한다."""
        query = select(G2BAwardStat)
        if bid_type:
            query = query.where(G2BAwardStat.bid_type == bid_type)
        if region_sido:
            query = query.where(G2BAwardStat.region_sido == region_sido)
        query = query.order_by(G2BAwardStat.stat_period.desc()).limit(120)

        result = await self.db.execute(query)
        stats = result.scalars().all()
        return G2BAwardStatsResponse(
            items=[G2BAwardStatResponse.model_validate(s) for s in stats],
            total=len(stats),
        )

    # ──────────────────────────────────────────
    # 유틸리티
    # ──────────────────────────────────────────

    @staticmethod
    def _classify_org_type(org_name: str) -> str:
        """발주기관명으로 기관 유형을 분류한다."""
        if any(kw in org_name for kw in ["시청", "군청", "구청", "도청", "특별시", "광역시", "특별자치"]):
            return "지자체"
        if any(kw in org_name for kw in ["LH", "SH", "GH", "공사", "공단", "진흥원", "센터"]):
            return "공기업"
        if any(kw in org_name for kw in ["부", "처", "청", "위원회", "원", "교육"]):
            return "중앙행정기관"
        return "기타공공기관"
