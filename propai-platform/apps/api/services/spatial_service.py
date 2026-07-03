"""PostGIS 공간 쿼리 서비스.

ST_DWithin, ST_Intersects, ST_Within 등 공간 연산을 제공한다.
geoalchemy2 / shapely 패키지 활용.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import func, select

from apps.api.config import get_settings
from apps.api.database.models.parcel import Parcel
from apps.api.database.models.project import Project

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)


class SpatialService:
    """PostGIS 기반 공간 쿼리 서비스."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    async def find_nearby_projects(
        self, lat: float, lon: float, radius_km: float = 5.0, limit: int = 20
    ) -> list[dict]:
        """특정 좌표 반경 내 프로젝트를 검색한다 (ST_DWithin).

        Args:
            lat: 위도 (WGS84)
            lon: 경도 (WGS84)
            radius_km: 검색 반경 (km)
            limit: 최대 결과 수

        Returns:
            [{"id": str, "distance_km": float, "lat": float, "lon": float}]
        """
        try:
            radius_m = radius_km * 1000
            point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)

            stmt = (
                select(
                    Project.id,
                    Project.latitude,
                    Project.longitude,
                    func.ST_Distance(
                        func.ST_Transform(Project.location, 3857),
                        func.ST_Transform(point, 3857),
                    ).label("distance_m"),
                )
                .where(
                    func.ST_DWithin(
                        Project.location,
                        point,
                        radius_m / 111320,
                    )
                )
                .order_by("distance_m")
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            rows = result.all()

            return [
                {
                    "id": str(row.id),
                    "lat": row.latitude,
                    "lon": row.longitude,
                    "distance_km": round((row.distance_m or 0) / 1000, 2),
                }
                for row in rows
            ]
        except Exception as e:
            logger.warning("공간 쿼리 실패", error=str(e))
            return []

    async def check_boundary_overlap(
        self, parcel_id: UUID, geometry_wkt: str
    ) -> dict:
        """필지 경계와 입력 geometry의 중첩 여부를 검사한다 (ST_Intersects).

        Args:
            parcel_id: 필지 ID
            geometry_wkt: WKT 형식 geometry

        Returns:
            {"overlaps": bool, "overlap_area_sqm": float}
        """
        try:
            input_geom = func.ST_GeomFromText(geometry_wkt, 4326)

            stmt = select(
                func.ST_Intersects(Parcel.boundary, input_geom).label("overlaps"),
                func.ST_Area(
                    func.ST_Transform(
                        func.ST_Intersection(Parcel.boundary, input_geom), 3857
                    )
                ).label("overlap_area_sqm"),
            ).where(Parcel.id == parcel_id)

            result = await self.db.execute(stmt)
            row = result.first()

            if row is None:
                return {"overlaps": False, "overlap_area_sqm": 0.0}

            return {
                "overlaps": bool(row.overlaps),
                "overlap_area_sqm": round(float(row.overlap_area_sqm or 0), 2),
            }
        except Exception as e:
            logger.warning("경계 중첩 검사 실패", error=str(e))
            return {"overlaps": False, "overlap_area_sqm": 0.0, "error": str(e)}

    async def get_projects_in_region(
        self, polygon_wkt: str, limit: int = 50
    ) -> list[dict]:
        """특정 영역(polygon) 안의 프로젝트를 검색한다 (ST_Within).

        Args:
            polygon_wkt: WKT 형식 POLYGON
            limit: 최대 결과 수
        """
        try:
            region = func.ST_GeomFromText(polygon_wkt, 4326)

            stmt = (
                select(Project.id, Project.latitude, Project.longitude)
                .where(func.ST_Within(Project.location, region))
                .limit(limit)
            )

            result = await self.db.execute(stmt)
            rows = result.all()

            return [
                {"id": str(row.id), "lat": row.latitude, "lon": row.longitude}
                for row in rows
            ]
        except Exception as e:
            logger.warning("영역 검색 실패", error=str(e))
            return []
