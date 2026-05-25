"""PostGIS + TimescaleDB 유틸리티."""
import math
from typing import Optional


class PostGISHelper:
    """PostGIS 공간 쿼리 래퍼 (인메모리 폴백)."""

    @staticmethod
    def st_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """두 좌표 간 거리(km) — Haversine."""
        R = 6371
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(dlon / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def st_contains(polygon_coords: list, point_lat: float, point_lon: float) -> bool:
        """점이 다각형 내부에 있는지 판별 — Ray Casting."""
        n = len(polygon_coords)
        inside = False
        j = n - 1
        for i in range(n):
            yi, xi = polygon_coords[i]
            yj, xj = polygon_coords[j]
            if ((yi > point_lon) != (yj > point_lon)) and (
                point_lat < (xj - xi) * (point_lon - yi) / (yj - yi) + xi
            ):
                inside = not inside
            j = i
        return inside

    @staticmethod
    def st_dwithin(
        lat1: float, lon1: float, lat2: float, lon2: float, distance_km: float
    ) -> bool:
        """두 점이 지정 거리 이내인지 판별."""
        return PostGISHelper.st_distance(lat1, lon1, lat2, lon2) <= distance_km

    @staticmethod
    def st_area(polygon_coords: list) -> float:
        """다각형 면적 (제곱미터, Shoelace)."""
        n = len(polygon_coords)
        if n < 3:
            return 0.0
        area = 0.0
        for i in range(n):
            j = (i + 1) % n
            area += polygon_coords[i][0] * polygon_coords[j][1]
            area -= polygon_coords[j][0] * polygon_coords[i][1]
        return abs(area) / 2.0

    @staticmethod
    def st_centroid(polygon_coords: list) -> tuple:
        """다각형 중심점."""
        n = len(polygon_coords)
        if n == 0:
            return (0.0, 0.0)
        lat_sum = sum(p[0] for p in polygon_coords)
        lon_sum = sum(p[1] for p in polygon_coords)
        return (lat_sum / n, lon_sum / n)

    @staticmethod
    def generate_point_sql(lat: float, lon: float, srid: int = 4326) -> str:
        """PostGIS POINT SQL 생성."""
        return f"ST_SetSRID(ST_MakePoint({lon}, {lat}), {srid})"

    @staticmethod
    def generate_buffer_sql(
        lat: float, lon: float, radius_m: float, srid: int = 4326
    ) -> str:
        """PostGIS 버퍼 SQL 생성."""
        return f"ST_Buffer(ST_SetSRID(ST_MakePoint({lon}, {lat}), {srid})::geography, {radius_m})"


class TimescaleHelper:
    """TimescaleDB 하이퍼테이블 헬퍼."""

    @staticmethod
    def create_hypertable_sql(
        table_name: str,
        time_column: str = "created_at",
        chunk_interval: str = "7 days",
    ) -> str:
        sq = chr(39)
        return (
            f"SELECT create_hypertable({sq}{table_name}{sq}, {sq}{time_column}{sq}, "
            f"chunk_time_interval => INTERVAL {sq}{chunk_interval}{sq}, "
            f"if_not_exists => TRUE);"
        )

    @staticmethod
    def continuous_aggregate_sql(
        view_name: str,
        table_name: str,
        time_column: str,
        interval: str,
        agg_expr: str,
    ) -> str:
        sq = chr(39)
        return (
            f"CREATE MATERIALIZED VIEW {view_name} "
            f"WITH (timescaledb.continuous) AS "
            f"SELECT time_bucket(INTERVAL {sq}{interval}{sq}, {time_column}) AS bucket, "
            f"{agg_expr} FROM {table_name} GROUP BY bucket;"
        )

    @staticmethod
    def retention_policy_sql(
        table_name: str, drop_after: str = "90 days"
    ) -> str:
        sq = chr(39)
        return f"SELECT add_retention_policy({sq}{table_name}{sq}, INTERVAL {sq}{drop_after}{sq});"

    @staticmethod
    def compression_policy_sql(
        table_name: str, compress_after: str = "30 days"
    ) -> str:
        sq = chr(39)
        return f"SELECT add_compression_policy({sq}{table_name}{sq}, INTERVAL {sq}{compress_after}{sq});"
