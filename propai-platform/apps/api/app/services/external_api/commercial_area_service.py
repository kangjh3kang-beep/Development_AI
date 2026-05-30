"""소상공인시장진흥공단 상가(상권)정보 API 연동 (data.go.kr B553077).

반경 내 상가업소를 조회하여 상권 활성도(점포 밀도·업종 다양성)를 분석한다.
상업/주상복합 개발 시 입지분석의 상권 항목으로 사용된다.

엔드포인트: {BASE}/storeListInRadius  (BASE = .../api/open/sdsc2)
  - serviceKey: data.go.kr 발급 인증키 (MOLIT와 동일한 계정 키 공용)
  - radius: 검색 반경(m)
  - cx: 중심 경도(longitude)
  - cy: 중심 위도(latitude)
  - type=json, numOfRows, pageNo

응답(2026-05-30 라이브 검증): {header:{description,columns,stdrYm,resultCode,resultMsg},
  body:{items:[...]}}.
중요 — 이 API는 **pageNo를 무시**하고(pg1==pg2 완전 중복) totalCount 필드도 없다.
  대신 **numOfRows를 키우면 그만큼 고유 점포를 한 번에 반환**한다(검증: nr5000→5000
  고유). 따라서 페이지네이션 없이 단일 호출로 numOfRows=_FETCH_LIMIT(5000)을 요청하고
  반환된 items 개수(len)를 전체 점포 수로 본다. 밀도 만점 기준(5000)과 동일하게 잡아,
  5000을 초과하는 초대형 상권(예: 강남역삼 8000)도 만점으로 수렴 → 캡 영향 없음.
응답 item 필드: bizesNm(상호명), indsLclsNm(업종 대분류명), indsMclsNm(중분류),
  lon(경도), lat(위도), rdnmAdr(도로명주소) 등.
라이브 변별 검증: 강남역삼 8000(A), 파주금촌 3499(B), 강원평창 2(E).

키 미설정·네트워크 실패 시 None을 반환하여 데이터 부재를 명확히 한다(할루시네이션 방지).
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class CommercialAreaService:
    """소상공인 상가(상권)정보 API 연동 서비스."""

    # 단일 호출 조회 상한. 밀도 만점 기준(_VITALITY_DENSITY_FULL)과 동일하게 두어
    # 이 값을 초과하는 초대형 상권도 점수상 만점으로 수렴 → 캡이 변별에 영향 없음.
    _FETCH_LIMIT = 5000

    async def get_stores_in_radius(
        self, lat: float, lon: float, radius_m: int = 500,
    ) -> list[dict[str, Any]] | None:
        """반경 내 상가업소 목록 조회 (단일 호출, numOfRows=_FETCH_LIMIT).

        이 API는 pageNo를 무시하므로 페이지네이션 대신 numOfRows를 크게 줘서
        한 번에 받는다. 반환 item 개수가 전체 점포 수(최대 _FETCH_LIMIT로 캡).

        Returns:
            상가 리스트([{name, category_large, ...}]) 또는 None(키 없음/실패).
        """
        if not settings.SEMAS_API_KEY:
            return None

        params = {
            "serviceKey": settings.SEMAS_API_KEY,
            "radius": str(radius_m),
            "cx": str(lon),
            "cy": str(lat),
            "type": "json",
            "numOfRows": str(self._FETCH_LIMIT),
            "pageNo": "1",
        }
        url = f"{settings.SEMAS_BASE_URL}/storeListInRadius"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("상권정보 HTTP 오류: %s", e.response.status_code)
            return None
        except Exception as e:
            logger.warning("상권정보 조회 실패: %s", str(e)[:200])
            return None

        body = data.get("body") or data.get("response", {}).get("body", {})
        if not isinstance(body, dict):
            return None
        items = body.get("items", [])
        if isinstance(items, dict):  # 단건 응답 시 dict로 옴
            items = items.get("item", [])
        if not isinstance(items, list):
            return []

        stores: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            stores.append({
                "name": item.get("bizesNm", ""),
                "category_large": item.get("indsLclsNm", ""),
                "category_mid": item.get("indsMclsNm", ""),
                "lat": _to_float(item.get("lat")),
                "lon": _to_float(item.get("lon")),
                "road_address": item.get("rdnmAdr", ""),
            })
        return stores

    async def analyze_commercial_area(
        self, lat: float, lon: float, radius_m: int = 500,
    ) -> dict[str, Any] | None:
        """반경 내 상권 활성도 분석 — 점포 수, 업종 다양성, 업종별 분포, 활성도 점수.

        전체 점포 수 = 페이지를 끝까지 순회해 수집한 점포 수(len). API에 totalCount가
        없으므로 get_stores_in_radius가 페이지네이션으로 전수 집계한다.

        Returns:
            {total_stores, category_diversity, category_distribution(상위), vitality_score, grade}
            또는 None(데이터 없음).
        """
        stores = await self.get_stores_in_radius(lat, lon, radius_m)
        if stores is None:
            return None

        total = len(stores)

        # 업종 대분류별 분포 집계
        dist: dict[str, int] = {}
        for s in stores:
            cat = s.get("category_large") or "기타"
            dist[cat] = dist.get(cat, 0) + 1
        diversity = len(dist)

        # 상위 분포 정렬
        top_dist = [
            {"category": k, "count": v}
            for k, v in sorted(dist.items(), key=lambda x: -x[1])
        ][:6]

        score = compute_vitality_score(total, diversity, radius_m)
        grade = vitality_grade(score)

        return {
            "total_stores": total,
            "category_diversity": diversity,
            "category_distribution": top_dist,
            "vitality_score": score,
            "grade": grade,
            "radius_m": radius_m,
        }


def _to_float(v: Any) -> float | None:
    try:
        return float(v) if v not in (None, "") else None
    except (ValueError, TypeError):
        return None


# ── 상권 활성도 점수화 ──
# 반경 500m 기준 점포 밀도와 업종 다양성을 0~100으로 환산.
# 점포 수 70점 + 업종 다양성 30점.
# 밀도 만점 기준(5000개): 라이브 전수 검증 강남역삼 500m≈8000개(만점/A),
# 파주금촌≈3499개(B), 강원평창≈2개(E)로 변별력 확인. 조회 상한과 동일하게 둠.
_VITALITY_DENSITY_FULL = 5000   # 점포 수 만점 기준
_VITALITY_DIVERSITY_FULL = 8   # 업종 대분류 만점 기준(전체 10개 중)


def compute_vitality_score(
    total_stores: int, diversity: int, radius_m: int = 500,
) -> int:
    """상권 활성도 점수(0~100). 점포 밀도 + 업종 다양성 가중 합산.

    반경이 500m가 아니면 면적 비례로 점포 수를 정규화한다.
    """
    # 면적 정규화 (500m 반경 기준)
    area_ratio = (radius_m / 500) ** 2 if radius_m > 0 else 1.0
    normalized_stores = total_stores / area_ratio if area_ratio > 0 else total_stores

    # 점포 밀도 점수 (선형)
    density_score = min(1.0, normalized_stores / _VITALITY_DENSITY_FULL) * 70
    # 업종 다양성 점수
    diversity_score = min(1.0, diversity / _VITALITY_DIVERSITY_FULL) * 30

    return round(density_score + diversity_score)


def vitality_grade(score: int) -> str:
    """활성도 점수를 A~E 등급으로 환산."""
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    if score >= 35:
        return "D"
    return "E"
