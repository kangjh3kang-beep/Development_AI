"""PostGIS spatial query service tests."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


class TestSpatialServiceImport:
    """Import test."""

    def test_spatial_service_import(self):
        from apps.api.services.spatial_service import SpatialService
        assert SpatialService is not None

    def test_spatial_service_instantiation(self):
        from apps.api.services.spatial_service import SpatialService
        mock_db = AsyncMock()
        svc = SpatialService(db=mock_db)
        assert svc.db is mock_db


class TestFindNearbyProjects:
    """Radius search test."""

    @pytest.mark.asyncio
    async def test_find_nearby_returns_list(self):
        from apps.api.services.spatial_service import SpatialService
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("no PostGIS")
        svc = SpatialService(db=mock_db)
        result = await svc.find_nearby_projects(lat=37.5665, lon=126.978, radius_km=5.0)
        assert isinstance(result, list)
        assert result == []

    @pytest.mark.asyncio
    async def test_find_nearby_with_custom_radius(self):
        from apps.api.services.spatial_service import SpatialService
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("no PostGIS")
        svc = SpatialService(db=mock_db)
        result = await svc.find_nearby_projects(lat=37.5, lon=127.0, radius_km=10.0)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_find_nearby_with_limit(self):
        from apps.api.services.spatial_service import SpatialService
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("no PostGIS")
        svc = SpatialService(db=mock_db)
        result = await svc.find_nearby_projects(lat=37.5, lon=127.0, limit=5)
        assert isinstance(result, list)


class TestBoundaryOverlap:
    """Boundary overlap test."""

    @pytest.mark.asyncio
    async def test_overlap_returns_dict(self):
        from apps.api.services.spatial_service import SpatialService
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("no PostGIS")
        svc = SpatialService(db=mock_db)
        result = await svc.check_boundary_overlap(
            parcel_id=uuid4(), geometry_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        )
        assert isinstance(result, dict)
        assert "overlaps" in result

    @pytest.mark.asyncio
    async def test_overlap_postgis_missing_returns_error(self):
        from apps.api.services.spatial_service import SpatialService
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("PostGIS not available")
        svc = SpatialService(db=mock_db)
        result = await svc.check_boundary_overlap(
            parcel_id=uuid4(), geometry_wkt="POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        )
        assert result["overlaps"] is False
        assert "error" in result


class TestProjectsInRegion:
    """Region search test."""

    @pytest.mark.asyncio
    async def test_region_search_returns_list(self):
        from apps.api.services.spatial_service import SpatialService
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("no PostGIS")
        svc = SpatialService(db=mock_db)
        result = await svc.get_projects_in_region(
            polygon_wkt="POLYGON((126 37, 127 37, 127 38, 126 38, 126 37))"
        )
        assert isinstance(result, list)
        assert result == []

    @pytest.mark.asyncio
    async def test_region_search_empty_on_error(self):
        from apps.api.services.spatial_service import SpatialService
        mock_db = AsyncMock()
        mock_db.execute.side_effect = Exception("connection error")
        svc = SpatialService(db=mock_db)
        result = await svc.get_projects_in_region(
            polygon_wkt="POLYGON((0 0, 10 0, 10 10, 0 10, 0 0))", limit=10
        )
        assert result == []
