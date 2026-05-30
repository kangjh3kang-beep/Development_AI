"""전국 지자체 도시계획조례 실시간 조회 서비스.

법제처 국가법령정보 공동활용 API를 활용하여
해당 시·군·구의 도시계획조례에서 건폐율/용적률 조례값을 자동 추출.

데이터 소스:
1. 법제처 자치법규 목록 조회 API (open.law.go.kr)
   - "{시군구명} 도시계획 조례" 검색 → 조례 일련번호 획득
2. 법제처 자치법규 본문 조회 API (data.go.kr/15058294)
   - 조례 본문에서 건폐율/용적률 조항 파싱
3. 정적 캐시 DB (API 실패 시 폴백)
   - 전국 주요 시·도 기본값 보유

참고 법률:
- 국토의 계획 및 이용에 관한 법률 시행령 제84조 (건폐율)
- 국토의 계획 및 이용에 관한 법률 시행령 제85조 (용적률)
- 각 지방자치단체 도시계획 조례
"""

import re
import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── 법정 상한 (국토계획법 시행령) ──
NATIONAL_LIMITS: dict[str, dict[str, float | None]] = {
    "제1종전용주거지역": {"bcr": 50, "far": 100, "height": 10},
    "제2종전용주거지역": {"bcr": 50, "far": 150, "height": 12},
    "제1종일반주거지역": {"bcr": 60, "far": 200, "height": None},
    "제2종일반주거지역": {"bcr": 60, "far": 250, "height": None},
    "제3종일반주거지역": {"bcr": 50, "far": 300, "height": None},
    "준주거지역": {"bcr": 70, "far": 500, "height": None},
    "중심상업지역": {"bcr": 90, "far": 1500, "height": None},
    "일반상업지역": {"bcr": 80, "far": 1300, "height": None},
    "근린상업지역": {"bcr": 70, "far": 900, "height": None},
    "유통상업지역": {"bcr": 80, "far": 1100, "height": None},
    "전용공업지역": {"bcr": 70, "far": 300, "height": None},
    "일반공업지역": {"bcr": 70, "far": 350, "height": None},
    "준공업지역": {"bcr": 70, "far": 400, "height": None},
    "보전녹지지역": {"bcr": 20, "far": 80, "height": None},
    "생산녹지지역": {"bcr": 20, "far": 100, "height": None},
    "자연녹지지역": {"bcr": 20, "far": 100, "height": None},
    "보전관리지역": {"bcr": 20, "far": 80, "height": None},
    "생산관리지역": {"bcr": 20, "far": 80, "height": None},
    "계획관리지역": {"bcr": 40, "far": 100, "height": None},
    "농림지역": {"bcr": 20, "far": 80, "height": None},
    "자연환경보전지역": {"bcr": 20, "far": 80, "height": None},
}

# ── 전국 주요 시·군·구 조례 캐시 (API 실패 시 폴백) ──
# 출처: 각 지자체 도시계획조례 (2025~2026 기준)
ORDINANCE_CACHE: dict[str, dict[str, dict[str, float]]] = {
    # ── 서울특별시 ──
    "서울특별시": {
        "제1종전용주거지역": {"bcr": 50, "far": 100},
        "제2종전용주거지역": {"bcr": 40, "far": 120},
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 200},
        "제3종일반주거지역": {"bcr": 50, "far": 250},
        "준주거지역": {"bcr": 60, "far": 400},
        "중심상업지역": {"bcr": 60, "far": 1000},
        "일반상업지역": {"bcr": 60, "far": 800},
        "근린상업지역": {"bcr": 60, "far": 600},
        "유통상업지역": {"bcr": 60, "far": 600},
        "전용공업지역": {"bcr": 60, "far": 200},
        "일반공업지역": {"bcr": 60, "far": 200},
        "준공업지역": {"bcr": 60, "far": 400},
        "보전녹지지역": {"bcr": 20, "far": 50},
        "생산녹지지역": {"bcr": 20, "far": 50},
        "자연녹지지역": {"bcr": 20, "far": 50},
    },
    # ── 경기도 주요 시 ──
    # 출처: 각 시 도시계획 조례 (2025~2026 확인 기준)
    "성남시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 220},
        "제3종일반주거지역": {"bcr": 50, "far": 280},
        "준주거지역": {"bcr": 60, "far": 400},
    },
    "수원시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 250},
        "제3종일반주거지역": {"bcr": 50, "far": 300},
        "준주거지역": {"bcr": 70, "far": 500},
    },
    "용인시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 200},
        "제3종일반주거지역": {"bcr": 50, "far": 250},
    },
    "화성시": {
        "제2종일반주거지역": {"bcr": 60, "far": 250},
        "제3종일반주거지역": {"bcr": 50, "far": 300},
    },
    "고양시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 220},
        "제3종일반주거지역": {"bcr": 50, "far": 280},
    },
    # 의정부시 도시계획 조례 (2025 기준)
    # 의정부시의 경우 제2종일반주거지역 용적률이 법정상한(250%)과 동일하게 조례에 규정
    # 다만 7층 이하 제2종일반주거지역은 200%로 제한됨
    "의정부시": {
        "제1종전용주거지역": {"bcr": 50, "far": 100},
        "제2종전용주거지역": {"bcr": 50, "far": 150},
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 250},
        "제2종일반주거지역(7층이하)": {"bcr": 60, "far": 200},
        "제3종일반주거지역": {"bcr": 50, "far": 300},
        "준주거지역": {"bcr": 70, "far": 500},
        "일반상업지역": {"bcr": 80, "far": 900},
        "근린상업지역": {"bcr": 70, "far": 700},
        "준공업지역": {"bcr": 70, "far": 400},
    },
    "부천시": {"제2종일반주거지역": {"bcr": 60, "far": 200}, "준공업지역": {"bcr": 60, "far": 400}},
    "안양시": {"제2종일반주거지역": {"bcr": 60, "far": 220}},
    "안산시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "준공업지역": {"bcr": 70, "far": 400}},
    "파주시": {"제2종일반주거지역": {"bcr": 60, "far": 200}, "계획관리지역": {"bcr": 40, "far": 100}},
    "김포시": {"제2종일반주거지역": {"bcr": 60, "far": 250}},
    "광명시": {"제2종일반주거지역": {"bcr": 60, "far": 200}},
    "하남시": {"제2종일반주거지역": {"bcr": 60, "far": 200}},
    "시흥시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "준공업지역": {"bcr": 60, "far": 400}},
    "남양주시": {
        "제1종일반주거지역": {"bcr": 60, "far": 150},
        "제2종일반주거지역": {"bcr": 60, "far": 220},
        "제3종일반주거지역": {"bcr": 50, "far": 280},
        "준주거지역": {"bcr": 60, "far": 400},
    },
    "구리시": {
        "제2종일반주거지역": {"bcr": 60, "far": 220},
        "제3종일반주거지역": {"bcr": 50, "far": 280},
    },
    "양주시": {
        "제2종일반주거지역": {"bcr": 60, "far": 250},
        "제3종일반주거지역": {"bcr": 50, "far": 300},
    },
    # ── 인천광역시 ──
    "인천광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}, "준주거지역": {"bcr": 60, "far": 400}},
    # ── 부산광역시 ──
    "부산광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}, "일반상업지역": {"bcr": 80, "far": 1000}},
    # ── 대구광역시 ──
    "대구광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}},
    # ── 대전광역시 ──
    "대전광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}},
    # ── 광주광역시 ──
    "광주광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}},
    # ── 세종특별자치시 ──
    "세종특별자치시": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 300}},
    # ── 울산광역시 ──
    "울산광역시": {"제2종일반주거지역": {"bcr": 60, "far": 250}},
    # ── 제주특별자치도 ──
    "제주특별자치도": {"제2종일반주거지역": {"bcr": 60, "far": 250}, "제3종일반주거지역": {"bcr": 50, "far": 250}},
}

# 법제처 API 엔드포인트
MOLEG_ORDIN_LIST_URL = "http://www.law.go.kr/DRF/lawSearch.do"
MOLEG_ORDIN_TEXT_URL = "http://www.law.go.kr/DRF/lawService.do"


class OrdinanceService:
    """전국 지자체 도시계획조례 실시간 조회 서비스."""

    async def get_ordinance_limits(
        self, address: str, zone_type: str
    ) -> dict[str, Any]:
        """주소와 용도지역으로 해당 지자체 조례 건폐율/용적률을 조회.

        우선순위:
        1. 법제처 API 실시간 조회 (도시계획조례 본문 파싱)
        2. 정적 캐시 DB (주요 시군구)
        3. 법정 상한 (국토계획법 시행령)
        """
        # 주소에서 지자체 추출
        region_info = self._extract_region(address)
        sido = region_info["sido"]
        sigungu = region_info["sigungu"]

        # 법정 상한
        national = NATIONAL_LIMITS.get(zone_type, {})
        national_bcr: float = float(national.get("bcr") or 60)
        national_far: float = float(national.get("far") or 250)

        result = {
            "sido": sido,
            "sigungu": sigungu,
            "zone_type": zone_type,
            "national_bcr": national_bcr,
            "national_far": national_far,
            "ordinance_bcr": None,
            "ordinance_far": None,
            "effective_bcr": national_bcr,
            "effective_far": national_far,
            "source": "법정상한",
            "legal_basis": "국토의 계획 및 이용에 관한 법률 시행령 제84조, 제85조",
            "ordinance_name": None,
            "last_updated": None,
        }

        # 1차: 법제처 API 실시간 조회
        api_result = await self._fetch_from_moleg_api(sido or "", sigungu, zone_type)
        if api_result and api_result.get("bcr") is not None:
            ord_bcr = api_result["bcr"]
            ord_far = api_result["far"]
            result["ordinance_bcr"] = ord_bcr
            result["ordinance_far"] = ord_far
            result["effective_bcr"] = min(national_bcr, ord_bcr) if ord_bcr else national_bcr
            result["effective_far"] = min(national_far, ord_far) if ord_far else national_far
            result["source"] = "법제처API"
            result["ordinance_name"] = api_result.get("ordinance_name")
            result["last_updated"] = api_result.get("last_updated")
            result["legal_basis"] = f"{sigungu or sido} 도시계획 조례"
            return result

        # 2차: 정적 캐시 조회 (전국 주요 시군구 조례 데이터)
        cache_result = self._lookup_cache(sido or "", sigungu, zone_type)
        if cache_result:
            c_bcr = cache_result["bcr"]
            c_far = cache_result["far"]
            result["ordinance_bcr"] = c_bcr
            result["ordinance_far"] = c_far
            result["effective_bcr"] = min(national_bcr, c_bcr)
            result["effective_far"] = min(national_far, c_far)
            result["source"] = "지자체 조례"
            result["legal_basis"] = f"{sigungu or sido} 도시계획 조례"
            return result

        # 3차: 법정 상한 그대로 (해당 지자체 조례 데이터 미보유)
        logger.info(
            "조례 캐시 미보유 — 법정상한 적용: sido=%s, sigungu=%s, zone=%s, "
            "법정 건폐율=%.0f%%, 법정 용적률=%.0f%%",
            sido, sigungu, zone_type, national_bcr, national_far,
        )
        result["source"] = "법정상한"
        return result

    async def _fetch_from_moleg_api(
        self, sido: str, sigungu: str | None, zone_type: str
    ) -> dict[str, Any] | None:
        """법제처 API로 도시계획조례 실시간 조회."""
        api_key = getattr(settings, "MOLEG_API_KEY", "") or ""
        if not api_key:
            return None

        search_name = f"{sigungu or sido} 도시계획 조례" if sigungu else f"{sido} 도시계획 조례"

        try:
            # Step 1: 자치법규 목록 검색 (User-Agent 필수)
            headers = {"User-Agent": "PropAI/1.0 (https://4t8t.net)"}
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                resp = await client.get(
                    MOLEG_ORDIN_LIST_URL,
                    params={
                        "OC": api_key,
                        "target": "ordin",
                        "type": "XML",
                        "query": search_name,
                        "display": "5",
                        "sort": "date",
                    },
                )
                resp.raise_for_status()
                ordin_list_xml = resp.text

            # 조례 일련번호 추출
            ordin_id = self._parse_ordin_id(ordin_list_xml, sigungu or sido)
            if not ordin_id:
                return None

            # Step 2: 조례 본문 조회
            async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
                resp = await client.get(
                    MOLEG_ORDIN_TEXT_URL,
                    params={
                        "OC": api_key,
                        "target": "ordin",
                        "type": "XML",
                        "ID": ordin_id,
                    },
                )
                resp.raise_for_status()
                ordin_text = resp.text

            # Step 3: 본문에서 건폐율/용적률 파싱
            return self._parse_bcr_far_from_text(ordin_text, zone_type, sigungu or sido)

        except Exception as e:
            logger.warning("법제처 API 조례 조회 실패: %s %s (%s)", sido, sigungu, str(e))
            return None

    def _parse_ordin_id(self, xml_text: str, region_name: str) -> str | None:
        """XML 응답에서 도시계획조례 일련번호를 추출."""
        # 간이 XML 파싱 (lxml 의존 없이)
        pattern = r"<법령일련번호>(\d+)</법령일련번호>"
        matches = re.findall(pattern, xml_text)
        if matches:
            return matches[0]
        # 영문 키 시도
        pattern2 = r"<ordinSeq>(\d+)</ordinSeq>"
        matches2 = re.findall(pattern2, xml_text)
        return matches2[0] if matches2 else None

    def _parse_bcr_far_from_text(
        self, xml_text: str, zone_type: str, region_name: str
    ) -> dict[str, Any] | None:
        """조례 본문에서 용도지역별 건폐율/용적률 값을 추출.

        파싱 전략 (실증 검증 완료):
        1. CDATA 블록을 추출하여 전체 텍스트 구성
        2. "용도지역안에서의 건폐율" / "용도지역안에서의 용적률" 조문 위치 탐색
        3. "{용도지역} : {숫자}퍼센트" 패턴으로 전체 테이블 파싱
        4. 요청된 zone_type에 해당하는 값 반환
        """
        # CDATA 블록 추출하여 전체 텍스트 구성
        chunks = re.findall(r"CDATA\[(.*?)\]", xml_text, re.DOTALL)
        full_text = " ".join(chunks)

        if not full_text:
            return None

        bcr = None
        far = None

        # 건폐율 조문 파싱
        bcr_idx = full_text.find("용도지역안에서의 건폐율")
        if bcr_idx >= 0:
            bcr_section = full_text[bcr_idx:bcr_idx + 1000]
            items = re.findall(r"(\S+지역)\s*:\s*(\d+)퍼센트", bcr_section)
            for zone_name, pct_str in items:
                if zone_type in zone_name or zone_name in zone_type:
                    bcr = int(pct_str)
                    break

        # 용적률 조문 파싱
        far_idx = full_text.find("용도지역안에서의 용적률")
        if far_idx >= 0:
            far_section = full_text[far_idx:far_idx + 1500]
            items = re.findall(r"(\S+지역)\s*:\s*(\d+)퍼센트", far_section)
            for zone_name, pct_str in items:
                if zone_type in zone_name or zone_name in zone_type:
                    far = int(pct_str)
                    break

        if bcr is None and far is None:
            return None

        # 조례명/시행일 추출
        ordin_name_match = re.search(r"<자치법규명>.*?CDATA\[([^\]]+)\]", xml_text)
        date_match = re.search(r"<시행일자>(\d{8})</시행일자>", xml_text)

        return {
            "bcr": bcr,
            "far": far,
            "ordinance_name": ordin_name_match.group(1) if ordin_name_match else f"{region_name} 도시계획 조례",
            "last_updated": f"{date_match.group(1)[:4]}-{date_match.group(1)[4:6]}-{date_match.group(1)[6:]}" if date_match else None,
        }

    def _lookup_cache(
        self, sido: str, sigungu: str | None, zone_type: str
    ) -> dict[str, float] | None:
        """정적 캐시에서 조례값 조회."""
        # 시군구 매칭 시도
        if sigungu:
            data = ORDINANCE_CACHE.get(sigungu, {}).get(zone_type)
            if data:
                return data

        # 시도 매칭
        data = ORDINANCE_CACHE.get(sido, {}).get(zone_type)
        return data

    def _extract_region(self, address: str) -> dict[str, str | None]:
        """주소에서 시도/시군구를 추출."""
        # 광역시/특별시/도
        SIDO_LIST = [
            "서울특별시", "부산광역시", "대구광역시", "인천광역시",
            "광주광역시", "대전광역시", "울산광역시", "세종특별자치시",
            "경기도", "강원도", "충청북도", "충청남도",
            "전라북도", "전라남도", "경상북도", "경상남도", "제주특별자치도",
        ]
        SIDO_SHORT = {
            "서울": "서울특별시", "부산": "부산광역시", "대구": "대구광역시",
            "인천": "인천광역시", "광주": "광주광역시", "대전": "대전광역시",
            "울산": "울산광역시", "세종": "세종특별자치시", "경기": "경기도",
            "강원": "강원도", "충북": "충청북도", "충남": "충청남도",
            "전북": "전라북도", "전남": "전라남도", "경북": "경상북도",
            "경남": "경상남도", "제주": "제주특별자치도",
        }

        sido = None
        for s in SIDO_LIST:
            if s in address:
                sido = s
                break
        if not sido:
            for short, full in SIDO_SHORT.items():
                if short in address:
                    sido = full
                    break

        # 시군구 추출 (시/군/구 패턴)
        sigungu = None
        sigungu_match = re.search(r"(?:서울|부산|대구|인천|광주|대전|울산|경기|강원|충[북남]|전[북남]|경[북남]|제주)\S*\s+(\S+[시군구])", address)
        if sigungu_match:
            sigungu = sigungu_match.group(1)
        else:
            # 간단 패턴: "OO시", "OO군", "OO구"
            match = re.search(r"(\S{2,4}[시군구])\s", address)
            if match:
                candidate = match.group(1)
                # 광역시 자체를 시군구로 잡지 않도록
                if candidate not in SIDO_LIST and "특별" not in candidate and "광역" not in candidate:
                    sigungu = candidate

        return {"sido": sido or "미확인", "sigungu": sigungu}
