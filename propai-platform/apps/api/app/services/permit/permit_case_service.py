"""인허가 사례 서비스 — 건축HUB 주택·건축인허가 기본개요 기반 인근 사례 조회.

PNU(19자리)에서 (시군구코드, 법정동코드)를 도출해 건축HUB 인허가 기본개요를 조회하고,
raw item을 PermitCaseRecord로 정규화한 뒤 분위수(건폐율·용적률 p25/p50/p75)·
주용도 상위 3개·최근 24개월 허가 건수를 요약한다.

원칙(정직):
- PNU 미해석·키없음·호출실패·무자료 전부 빈 응답 + note (가짜 데이터 생성 금지)
- 형변환 실패 값은 None (0 등 임의값 대입 금지)
- 표본 5건 미만이면 분위수 None + note
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from typing import Any

import structlog

from app.schemas.permit_case import (
    PermitCaseRecord,
    PermitCaseResponse,
    PermitCaseSummary,
)
from apps.api.integrations.hub_permit_client import ArchPermitClient, HubPermitClient
from apps.api.integrations.region_codes import pnu_to_bcode

logger = structlog.get_logger(__name__)

# 분위수 산출 최소 표본 수 (미만이면 None — 과대해석 방지)
_MIN_SAMPLES_FOR_PERCENTILES = 5
# "최근" 판정 기간 (24개월 ≈ 730일)
_RECENT_WINDOW_DAYS = 730


class PermitCaseService:
    """건축HUB 인허가 사례 조회·정규화·요약 서비스."""

    def __init__(
        self,
        hub_client: HubPermitClient | None = None,
        arch_client: ArchPermitClient | None = None,
    ) -> None:
        # 테스트 주입 가능. 미주입 시 호출 시점에 lazy 생성.
        self._hub_client = hub_client
        self._arch_client = arch_client

    async def get_nearby_cases(
        self, pnu: str, kind: str = "arch", limit: int = 50
    ) -> PermitCaseResponse:
        """PNU 기준 동일 법정동의 인허가 사례를 조회·정규화·요약한다.

        Args:
            pnu: 필지고유번호(최소 앞 10자리 숫자)
            kind: "arch"(건축인허가) | "hs"(주택인허가)
            limit: 반환 사례 상한
        """
        bcode = pnu_to_bcode(pnu)
        if bcode is None:
            return PermitCaseResponse(note="PNU 미해석 — 시군구·법정동 코드를 도출할 수 없습니다.")
        sigungu_cd, bjdong_cd = bcode

        try:
            if kind == "hs":
                client = self._hub_client or HubPermitClient()
                items = await client.get_basis_ouln_info(sigungu_cd, bjdong_cd)
            else:
                client = self._arch_client or ArchPermitClient()
                items = await client.get_ap_basis_ouln_info(sigungu_cd, bjdong_cd)
        except Exception as e:  # noqa: BLE001 — 키 미설정 등 클라이언트 외곽 오류도 빈결과 정직
            logger.warning("인허가 사례 조회 실패", pnu=pnu, kind=kind, error=str(e))
            return PermitCaseResponse(note="건축HUB 인허가 조회 실패 — 빈 결과를 반환합니다.")

        records = [self.normalize_item(item) for item in (items or [])]
        if limit and limit > 0:
            records = records[:limit]
        if not records:
            return PermitCaseResponse(note="조회 결과 없음 — 해당 법정동의 인허가 사례가 없습니다.")

        summary = self.summarize(records)
        note = None
        if summary.count < _MIN_SAMPLES_FOR_PERCENTILES:
            note = f"표본 {summary.count}건(<{_MIN_SAMPLES_FOR_PERCENTILES}) — 분위수 미산출."
        return PermitCaseResponse(
            cases=records,
            summary=summary,
            total=len(records),
            note=note,
        )

    # ── 정규화 ──────────────────────────────────────────────────────────

    @classmethod
    def normalize_item(cls, item: dict[str, Any]) -> PermitCaseRecord:
        """건축HUB 기본개요 raw item → PermitCaseRecord 정규화."""
        return PermitCaseRecord(
            land_area_sqm=cls._to_float(item.get("platArea")),
            building_area_sqm=cls._to_float(item.get("archArea")),
            total_floor_area_sqm=cls._to_float(item.get("totArea")),
            bcr_pct=cls._to_float(item.get("bcRat")),
            far_pct=cls._to_float(item.get("vlRat")),
            floors_above=cls._to_int(item.get("grndFlrCnt")),
            floors_below=cls._to_int(item.get("ugrndFlrCnt")),
            main_use=cls._to_str(item.get("mainPurpsCdNm")),
            permit_date=cls._to_iso_date(item.get("pmsDay")),
            construction_start_date=cls._to_iso_date(item.get("stcnsDay")),
            approval_date=cls._to_iso_date(item.get("useAprDay")),
        )

    @staticmethod
    def _to_float(value: Any) -> float | None:
        """문자/숫자 → float. 빈값·형변환 실패는 None(임의값 금지)."""
        if value is None:
            return None
        s = str(value).strip().replace(",", "")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        """문자/숫자 → int. 빈값·형변환 실패는 None."""
        if value is None:
            return None
        s = str(value).strip()
        if not s:
            return None
        try:
            return int(float(s))
        except ValueError:
            return None

    @staticmethod
    def _to_str(value: Any) -> str | None:
        """문자열 정리. 빈값은 None."""
        if value is None:
            return None
        s = str(value).strip()
        return s or None

    @staticmethod
    def _to_iso_date(value: Any) -> str | None:
        """YYYYMMDD(8자리) → ISO(YYYY-MM-DD). 빈값·형식불일치·무효일자는 None."""
        if value is None:
            return None
        s = str(value).strip()
        if len(s) != 8 or not s.isdigit():
            return None
        try:
            return datetime.strptime(s, "%Y%m%d").date().isoformat()
        except ValueError:
            return None

    # ── 요약 ────────────────────────────────────────────────────────────

    @classmethod
    def summarize(
        cls, records: list[PermitCaseRecord], now: datetime | None = None
    ) -> PermitCaseSummary:
        """사례 목록 → 분위수·주용도 top3·최근 24개월 건수 요약.

        표본(해당 지표 유효값) 5건 미만이면 분위수 None(과대해석 방지).
        """
        count = len(records)
        bcr_q = cls._percentiles([r.bcr_pct for r in records if r.bcr_pct is not None])
        far_q = cls._percentiles([r.far_pct for r in records if r.far_pct is not None])

        use_counter = Counter(r.main_use for r in records if r.main_use)
        top3 = [name for name, _cnt in use_counter.most_common(3)]

        cutoff = ((now or datetime.now()).date()) - timedelta(days=_RECENT_WINDOW_DAYS)
        recent = 0
        for r in records:
            if not r.permit_date:
                continue
            permit_d = cls._parse_iso(r.permit_date)
            if permit_d is not None and permit_d >= cutoff:
                recent += 1

        return PermitCaseSummary(
            count=count,
            bcr_p25=bcr_q[0] if bcr_q else None,
            bcr_p50=bcr_q[1] if bcr_q else None,
            bcr_p75=bcr_q[2] if bcr_q else None,
            far_p25=far_q[0] if far_q else None,
            far_p50=far_q[1] if far_q else None,
            far_p75=far_q[2] if far_q else None,
            main_use_top3=top3,
            recent_24m_count=recent,
        )

    @staticmethod
    def _percentiles(values: list[float]) -> tuple[float, float, float] | None:
        """(p25, p50, p75) 선형보간 분위수. 표본 5건 미만이면 None."""
        if len(values) < _MIN_SAMPLES_FOR_PERCENTILES:
            return None
        data = sorted(values)
        n = len(data)

        def _q(q: float) -> float:
            pos = (n - 1) * q
            lo = int(pos)
            hi = min(lo + 1, n - 1)
            frac = pos - lo
            return round(data[lo] + (data[hi] - data[lo]) * frac, 2)

        return _q(0.25), _q(0.50), _q(0.75)

    @staticmethod
    def _parse_iso(s: str) -> date | None:
        """ISO(YYYY-MM-DD) → date. 실패 시 None."""
        try:
            return date.fromisoformat(s)
        except ValueError:
            return None
