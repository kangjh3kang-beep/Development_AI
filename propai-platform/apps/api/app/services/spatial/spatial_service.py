"""공간 쿼리 서비스."""
import math
from typing import Dict, List


class SpatialService:
    """좌표 기반 인근 프로젝트 검색."""

    @staticmethod
    def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        R = 6371.0
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    def find_nearby_projects(self, lat: float, lon: float, radius_km: float,
                             projects: list[dict]) -> list[dict]:
        results = []
        for p in projects:
            plat = p.get("lat", p.get("latitude", 0))
            plon = p.get("lon", p.get("longitude", 0))
            dist = self._haversine(lat, lon, plat, plon)
            if dist <= radius_km:
                results.append({**p, "distance_km": round(dist, 3)})
        results.sort(key=lambda x: x["distance_km"])
        return results
