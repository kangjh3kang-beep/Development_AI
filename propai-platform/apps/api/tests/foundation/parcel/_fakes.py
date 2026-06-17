"""F-Parcel 배치 테스트용 가짜 VWorld(라이브콜 0).

실제 VWorldService(structlog/httpx 의존)를 절대 import 하지 않고,
동일 시그니처의 FakeVWorld 를 제공한다. 모든 호출을 live_calls 로 카운트한다.
"""

from __future__ import annotations


class FakeVWorld:
    """VWorldService 호환 가짜 객체.

    고정 fake 필지 N개를 제공하고, 일부를 NOT_FOUND/AMBIGUOUS 로 만든다.
    bbox/polygon 후보, union 고정 반환, 관할 목록을 제공한다.
    """

    def __init__(
        self,
        confirmed_pnus=None,
        ambiguous_pnus=None,
        bbox_pnus=None,
        bbox_features=None,
    ) -> None:
        self.confirmed = confirmed_pnus or [
            "1111010100100010000",
            "1111010100100020000",
            "1111010100100030000",
        ]
        self.ambiguous = ambiguous_pnus or ["1111010100100040000"]
        self.bbox_pnus = bbox_pnus if bbox_pnus is not None else list(self.confirmed)
        self.bbox_features = bbox_features
        self.live_calls = 0

    async def get_land_characteristics(self, pnu: str, year: int = 2025):
        self.live_calls += 1
        if pnu in self.confirmed:
            return {
                "pnu": pnu,
                "area_sqm": 500.0,
                "land_category": "대",
                "zone_type": "제2종일반주거지역",
            }
        return None

    async def get_parcel_by_pnu(self, pnu_code: str):
        self.live_calls += 1
        if pnu_code in self.ambiguous:
            return {
                "geometry": {"type": "Polygon", "coordinates": []},
                "properties": {"pnu": pnu_code},
            }
        return None

    async def get_parcels_in_bbox(self, min_lon, min_lat, max_lon, max_lat, max_count=100):
        self.live_calls += 1
        if self.bbox_features is not None:
            return list(self.bbox_features)
        return [{"pnu": p, "jimok": "대", "geometry": None} for p in self.bbox_pnus]

    async def merge_parcels_gis_union(self, pnu_codes):
        self.live_calls += 1
        if not pnu_codes:
            return None
        return {
            "merged_geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]],
            },
            "total_area_sqm": 1500.0,
            "parcel_count": len(pnu_codes),
        }

    async def get_land_use_districts(self, pnu: str):
        self.live_calls += 1
        return [{"category": "용도지구", "name": "고도지구", "code": "UQA01"}]