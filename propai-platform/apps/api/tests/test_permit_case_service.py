"""인허가 사례 서비스(PermitCaseService) 단위 테스트.

검증 범위 (외부 API/네트워크 없이 _get_data 모킹으로 결정론 검증):
- ① 정규화 정답값: bcRat "59.98"→59.98(float), pmsDay "20240115"→"2024-01-15"(ISO),
  빈값·형변환 실패는 None(가짜값 금지).
- ② 분위수 고정: [10,20,30,40,50] → p25=20/p50=30/p75=40 (선형보간),
  표본 5건 미만이면 None + note.
- ③ PNU 미해석: 빈 응답 + note (sigungu/bjdong 도출 불가).
- ④ dict 단일 item 배열화: _extract_items가 단일 dict item을 [dict]로 정규화.
- ⑤ 클라이언트 예외(키 미설정 등)도 빈 응답 정직 반환(graceful).
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from datetime import datetime  # noqa: E402
from unittest.mock import AsyncMock  # noqa: E402

import pytest  # noqa: E402

from app.schemas.permit_case import PermitCaseRecord  # noqa: E402
from app.services.permit.permit_case_service import PermitCaseService  # noqa: E402
from apps.api.integrations.hub_permit_client import (  # noqa: E402
    ArchPermitClient,
    HubPermitClient,
)


def _raw_item(**overrides) -> dict:
    """건축HUB 기본개요 raw item 샘플."""
    item = {
        "platArea": "300.5",
        "archArea": "150.2",
        "totArea": "600.4",
        "bcRat": "59.98",
        "vlRat": "199.9",
        "grndFlrCnt": "5",
        "ugrndFlrCnt": "1",
        "mainPurpsCdNm": "공동주택",
        "pmsDay": "20240115",
        "stcnsDay": "20240301",
        "useAprDay": "",
    }
    item.update(overrides)
    return item


# ── ① 정규화 ──────────────────────────────────────────────────────────────


class TestNormalizeItem:
    """raw item → PermitCaseRecord 정규화 테스트."""

    def test_정상값_정답_변환(self) -> None:
        """bcRat "59.98"→59.98, pmsDay "20240115"→"2024-01-15" 등 정답값 검증."""
        rec = PermitCaseService.normalize_item(_raw_item())
        assert rec.land_area_sqm == 300.5
        assert rec.building_area_sqm == 150.2
        assert rec.total_floor_area_sqm == 600.4
        assert rec.bcr_pct == 59.98
        assert rec.far_pct == 199.9
        assert rec.floors_above == 5
        assert rec.floors_below == 1
        assert rec.main_use == "공동주택"
        assert rec.permit_date == "2024-01-15"
        assert rec.construction_start_date == "2024-03-01"
        assert rec.approval_date is None  # 빈 문자열 → None (정직)

    def test_형변환_실패는_None(self) -> None:
        """숫자 아님·자릿수 불일치·무효일자는 None — 임의값 대입 금지."""
        rec = PermitCaseService.normalize_item(
            _raw_item(
                bcRat="abc",
                vlRat=None,
                platArea="",
                grndFlrCnt="층수미상",
                pmsDay="2024011",      # 7자리 → None
                stcnsDay="20241341",   # 무효 월일 → None
                mainPurpsCdNm="  ",
            )
        )
        assert rec.bcr_pct is None
        assert rec.far_pct is None
        assert rec.land_area_sqm is None
        assert rec.floors_above is None
        assert rec.permit_date is None
        assert rec.construction_start_date is None
        assert rec.main_use is None

    def test_누락_필드_전부_None(self) -> None:
        """원천에 키 자체가 없으면 모든 필드 None."""
        rec = PermitCaseService.normalize_item({})
        assert rec == PermitCaseRecord()


# ── ② 분위수·요약 ─────────────────────────────────────────────────────────


class TestSummarize:
    """분위수(선형보간)·주용도 top3·최근 24개월 건수 테스트."""

    def test_분위수_고정값(self) -> None:
        """[10,20,30,40,50] → p25=20, p50=30, p75=40."""
        assert PermitCaseService._percentiles([10, 20, 30, 40, 50]) == (20.0, 30.0, 40.0)

    def test_표본_5건_미만이면_None(self) -> None:
        assert PermitCaseService._percentiles([10, 20, 30, 40]) is None

    def test_summarize_종합(self) -> None:
        """분위수·top3·recent_24m_count를 고정 기준시각으로 검증."""
        records = [
            PermitCaseRecord(
                bcr_pct=float(b), far_pct=float(f), main_use=u, permit_date=d
            )
            for b, f, u, d in [
                (10, 100, "공동주택", "2025-01-15"),   # 최근(24개월 이내)
                (20, 200, "공동주택", "2024-12-01"),   # 최근
                (30, 300, "단독주택", "2020-01-01"),   # 과거
                (40, 400, "공동주택", None),            # 허가일 미상
                (50, 500, "제2종근린생활시설", "2019-06-30"),  # 과거
            ]
        ]
        summary = PermitCaseService.summarize(records, now=datetime(2026, 6, 12))
        assert summary.count == 5
        assert (summary.bcr_p25, summary.bcr_p50, summary.bcr_p75) == (20.0, 30.0, 40.0)
        assert (summary.far_p25, summary.far_p50, summary.far_p75) == (200.0, 300.0, 400.0)
        assert summary.main_use_top3[0] == "공동주택"
        assert len(summary.main_use_top3) == 3
        assert summary.recent_24m_count == 2

    def test_표본부족_분위수_None(self) -> None:
        records = [PermitCaseRecord(bcr_pct=59.98, far_pct=199.9)] * 3
        summary = PermitCaseService.summarize(records)
        assert summary.count == 3
        assert summary.bcr_p50 is None
        assert summary.far_p50 is None


# ── ③ PNU 미해석 ──────────────────────────────────────────────────────────


class TestPnuUnresolvable:
    """PNU 미해석 시 빈 응답 + note."""

    async def test_pnu_미해석_빈응답(self) -> None:
        resp = await PermitCaseService().get_nearby_cases("ABC-INVALID")
        assert resp.cases == []
        assert resp.total == 0
        assert resp.summary.count == 0
        assert resp.note is not None and "PNU 미해석" in resp.note
        assert resp.source == "building_hub"

    async def test_pnu_10자리_미만_빈응답(self) -> None:
        resp = await PermitCaseService().get_nearby_cases("12345")
        assert resp.cases == []
        assert resp.note is not None and "PNU 미해석" in resp.note


# ── ④ dict 단일 item 배열화 ───────────────────────────────────────────────


class TestExtractItems:
    """건축HUB 응답 파서 — 단일 dict item도 list로 정규화."""

    def test_단일_dict_item_배열화(self) -> None:
        data = {"response": {"body": {"items": {"item": {"bcRat": "59.98"}}}}}
        assert HubPermitClient._extract_items(data) == [{"bcRat": "59.98"}]

    def test_빈_body_빈리스트(self) -> None:
        assert HubPermitClient._extract_items({"response": {"body": None}}) == []
        assert HubPermitClient._extract_items({}) == []


# ── ⑤ get_nearby_cases (클라이언트 _get_data 모킹) ────────────────────────


class TestGetNearbyCases:
    """_get_data 모킹 기반 조회·정규화·요약 엔드투엔드 테스트."""

    async def test_arch_조회_정규화(self) -> None:
        """kind=arch → ArchPermitClient.getApBasisOulnInfo 경로 + 정규화 정답값."""
        client = ArchPermitClient()
        client._get_data = AsyncMock(return_value=[_raw_item(), _raw_item(bcRat="40")])
        svc = PermitCaseService(arch_client=client)

        resp = await svc.get_nearby_cases("1168010300101230045", kind="arch")

        assert resp.total == 2
        assert resp.cases[0].bcr_pct == 59.98
        assert resp.cases[0].permit_date == "2024-01-15"
        assert resp.cases[1].bcr_pct == 40.0
        assert resp.source == "building_hub"
        # 표본 5건 미만 → 분위수 None + note
        assert resp.summary.bcr_p50 is None
        assert resp.note is not None and "분위수 미산출" in resp.note
        # PNU → sigungu/bjdong 슬라이싱이 엔드포인트 호출에 반영
        endpoint, params = client._get_data.call_args.args[:2]
        assert endpoint == "getApBasisOulnInfo"
        assert params == {"sigunguCd": "11680", "bjdongCd": "10300"}

    async def test_hs_조회_경로(self) -> None:
        """kind=hs → HubPermitClient.getHpBasisOulnInfo 경로."""
        client = HubPermitClient()
        client._get_data = AsyncMock(return_value=[_raw_item()])
        svc = PermitCaseService(hub_client=client)

        resp = await svc.get_nearby_cases("1168010300101230045", kind="hs")

        assert resp.total == 1
        endpoint = client._get_data.call_args.args[0]
        assert endpoint == "getHpBasisOulnInfo"

    async def test_무자료_빈응답_note(self) -> None:
        """조회 성공·무자료 → 빈 응답 + note (가짜 데이터 금지)."""
        client = ArchPermitClient()
        client._get_data = AsyncMock(return_value=[])
        svc = PermitCaseService(arch_client=client)

        resp = await svc.get_nearby_cases("1168010300101230045")

        assert resp.cases == []
        assert resp.total == 0
        assert resp.note is not None and "조회 결과 없음" in resp.note

    async def test_클라이언트_예외도_빈응답(self) -> None:
        """클라이언트 외곽 예외(키 미설정 AttributeError 등)도 빈 응답 정직."""
        client = ArchPermitClient()
        client.get_ap_basis_ouln_info = AsyncMock(  # type: ignore[method-assign]
            side_effect=AttributeError("hub_permit_api_key")
        )
        svc = PermitCaseService(arch_client=client)

        resp = await svc.get_nearby_cases("1168010300101230045")

        assert resp.cases == []
        assert resp.note is not None and "조회 실패" in resp.note

    async def test_limit_상한_적용(self) -> None:
        client = ArchPermitClient()
        client._get_data = AsyncMock(return_value=[_raw_item() for _ in range(10)])
        svc = PermitCaseService(arch_client=client)

        resp = await svc.get_nearby_cases("1168010300101230045", limit=3)

        assert resp.total == 3
        assert len(resp.cases) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
