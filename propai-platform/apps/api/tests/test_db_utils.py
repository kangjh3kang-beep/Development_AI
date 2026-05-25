"""PostGIS/TimescaleDB 유틸리티 테스트."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestPostGISHelper:
    """PostGISHelper 테스트."""

    def test_st_distance_same_point(self):
        from app.core.db_utils import PostGISHelper

        dist = PostGISHelper.st_distance(37.5665, 126.9780, 37.5665, 126.9780)
        assert dist == 0.0

    def test_st_distance_seoul_busan(self):
        from app.core.db_utils import PostGISHelper

        dist = PostGISHelper.st_distance(37.5665, 126.9780, 35.1796, 129.0756)
        assert 300 < dist < 400

    def test_st_contains_inside(self):
        from app.core.db_utils import PostGISHelper

        polygon = [(0, 0), (0, 10), (10, 10), (10, 0)]
        assert PostGISHelper.st_contains(polygon, 5, 5) is True

    def test_st_contains_outside(self):
        from app.core.db_utils import PostGISHelper

        polygon = [(0, 0), (0, 10), (10, 10), (10, 0)]
        assert PostGISHelper.st_contains(polygon, 15, 15) is False

    def test_st_dwithin_true(self):
        from app.core.db_utils import PostGISHelper

        result = PostGISHelper.st_dwithin(37.5665, 126.9780, 37.5700, 126.9800, 10)
        assert result is True

    def test_st_dwithin_false(self):
        from app.core.db_utils import PostGISHelper

        result = PostGISHelper.st_dwithin(37.5665, 126.9780, 35.1796, 129.0756, 1)
        assert result is False

    def test_st_area_triangle(self):
        from app.core.db_utils import PostGISHelper

        polygon = [(0, 0), (4, 0), (0, 3)]
        area = PostGISHelper.st_area(polygon)
        assert area == 6.0

    def test_st_area_too_few_points(self):
        from app.core.db_utils import PostGISHelper

        assert PostGISHelper.st_area([(0, 0), (1, 1)]) == 0.0

    def test_st_centroid(self):
        from app.core.db_utils import PostGISHelper

        polygon = [(0, 0), (4, 0), (4, 4), (0, 4)]
        cx, cy = PostGISHelper.st_centroid(polygon)
        assert cx == 2.0
        assert cy == 2.0

    def test_st_centroid_empty(self):
        from app.core.db_utils import PostGISHelper

        assert PostGISHelper.st_centroid([]) == (0.0, 0.0)

    def test_generate_point_sql(self):
        from app.core.db_utils import PostGISHelper

        sql = PostGISHelper.generate_point_sql(37.5, 127.0)
        assert "ST_MakePoint" in sql
        assert "4326" in sql

    def test_generate_buffer_sql(self):
        from app.core.db_utils import PostGISHelper

        sql = PostGISHelper.generate_buffer_sql(37.5, 127.0, 1000)
        assert "ST_Buffer" in sql
        assert "1000" in sql


class TestTimescaleHelper:
    """TimescaleHelper 테스트."""

    def test_create_hypertable_sql(self):
        from app.core.db_utils import TimescaleHelper

        sql = TimescaleHelper.create_hypertable_sql("metrics")
        assert "create_hypertable" in sql
        assert "metrics" in sql

    def test_retention_policy_sql(self):
        from app.core.db_utils import TimescaleHelper

        sql = TimescaleHelper.retention_policy_sql("metrics", "60 days")
        assert "add_retention_policy" in sql
        assert "60 days" in sql

    def test_compression_policy_sql(self):
        from app.core.db_utils import TimescaleHelper

        sql = TimescaleHelper.compression_policy_sql("metrics")
        assert "add_compression_policy" in sql

    def test_continuous_aggregate_sql(self):
        from app.core.db_utils import TimescaleHelper

        sql = TimescaleHelper.continuous_aggregate_sql(
            "hourly_view", "metrics", "ts", "1 hour", "avg(value)"
        )
        assert "MATERIALIZED VIEW" in sql
        assert "time_bucket" in sql
