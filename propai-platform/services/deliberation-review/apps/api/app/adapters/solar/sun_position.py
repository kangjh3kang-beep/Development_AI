"""L3-B — 태양위치 근사(결정론). 동지 정오 태양고도 + 동지 가조시간 + 그림자길이.

모델 상수(축경사/시간각)는 호출자가 파라미터로 주입(INV-20). 라이브 의존 없음.
"""
from __future__ import annotations

import math

_ZENITH_DEG = 90.0


def solar_noon_altitude(latitude_deg: float, axial_tilt_deg: float) -> float:
    """동지 정오 태양고도(deg). = 90 - |위도| - 축경사."""
    return _ZENITH_DEG - abs(latitude_deg) - axial_tilt_deg


def winter_daylight_hours(latitude_deg: float, axial_tilt_deg: float, degrees_per_hour: float) -> float:
    """동지 가조시간(h). 위도/적위(−축경사)로 시간각 산정."""
    lat = math.radians(latitude_deg)
    dec = math.radians(-axial_tilt_deg)
    cos_h = -math.tan(lat) * math.tan(dec)
    cos_h = max(-1.0, min(1.0, cos_h))
    hour_angle_deg = math.degrees(math.acos(cos_h))
    return 2.0 * hour_angle_deg / degrees_per_hour


def shadow_length(obstacle_height: float, altitude_deg: float) -> float:
    """장애물 그림자 길이(m). 태양고도 0 이하면 매우 긴 그림자(차폐)."""
    if altitude_deg <= 0:
        return math.inf
    return obstacle_height / math.tan(math.radians(altitude_deg))


def sun_altitude_azimuth(latitude_deg: float, declination_deg: float,
                         hour_angle_deg: float) -> tuple[float, float]:
    """시각별 태양 고도/방위각(deg). 방위각=북0·동90·남180·서270(시계방향). 3D 그림자 투영용.

    declination=적위(동지 -23.44), hour_angle=시간각(정오 0, 1h=15°, 오전 음/오후 양).
    """
    lat = math.radians(latitude_deg)
    dec = math.radians(declination_deg)
    ha = math.radians(hour_angle_deg)
    sin_alt = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(ha)
    sin_alt = max(-1.0, min(1.0, sin_alt))
    alt = math.degrees(math.asin(sin_alt))
    cos_alt = math.cos(math.radians(alt))
    if abs(cos_alt) < 1e-9:
        return alt, 180.0
    cos_az = (math.sin(dec) - math.sin(lat) * sin_alt) / (math.cos(lat) * cos_alt)
    cos_az = max(-1.0, min(1.0, cos_az))
    az = math.degrees(math.acos(cos_az))  # 북0 기준 0~180(정오 남쪽 180)
    if hour_angle_deg > 0:  # 오후 → 서쪽
        az = 360.0 - az
    return alt, az
