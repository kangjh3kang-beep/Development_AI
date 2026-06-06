"""용도지역별 법정 건폐율/용적률 상한 SSOT(Single Source of Truth).

근거: 국토의 계획 및 이용에 관한 법률 시행령
- 제84조(용도지역 안에서의 건폐율)
- 제85조(용도지역 안에서의 용적률)
※ 시행령은 용적률에 범위(예: 자연녹지 50~100%)를 두며, 구체 수치는 지자체 조례로 정한다.
  본 표는 '법정 상한(국토계획법 시행령 최대치)'을 SSOT로 보유한다. 조례 가감은 별도 데이터
  (local_ordinance)로 처리하며, 이 표의 값을 초과하는 임의 수치는 할루시네이션으로 간주한다.

실제 데이터 원본(ZONE_LIMITS)은 auto_zoning_service에 있고, 본 모듈은 그 표를 SSOT로
재노출하며 '용도지역명 → 법정 상한' 결정론 조회 헬퍼를 제공한다(검증기·그라운딩 공용).
"""

from __future__ import annotations

from typing import Any

# 데이터 원본(SSOT). auto_zoning_service.ZONE_LIMITS를 단일 출처로 사용.
from app.services.zoning.auto_zoning_service import ZONE_LIMITS

# 법정 출처 주석(그라운딩/배지 표기에 사용)
LEGAL_BASIS = "국토계획법 시행령 제84·85조(용도지역별 건폐율·용적률 상한)"


def normalize_zone_name(raw_zone: str | None) -> str | None:
    """용도지역명(공백/표기변형 포함)을 ZONE_LIMITS 표준 키로 정규화.

    정확 일치 → 부분 일치 순으로 매칭한다. 매칭 실패 시 None.
    """
    if not raw_zone:
        return None
    key = str(raw_zone).replace(" ", "").strip()
    if not key:
        return None
    if key in ZONE_LIMITS:
        return key
    # 부분 일치: 가장 구체적(긴) 키 우선으로 매칭하여 '주거지역' 같은 광의 매칭을 줄인다.
    for zone in sorted(ZONE_LIMITS, key=len, reverse=True):
        if zone in key or key in zone:
            return zone
    return None


def legal_limits_for(zone_type: str | None) -> dict[str, Any] | None:
    """용도지역명에 대한 법정 건폐율/용적률 상한을 반환.

    Returns:
        {"zone_type": 표준키, "max_bcr_pct": int, "max_far_pct": int,
         "max_height_m": int|None, "legal_basis": str} 또는 미매칭 시 None.
    """
    key = normalize_zone_name(zone_type)
    if key is None:
        return None
    limits = ZONE_LIMITS.get(key)
    if not limits:
        return None
    return {
        "zone_type": key,
        "max_bcr_pct": limits.get("max_bcr"),
        "max_far_pct": limits.get("max_far"),
        "max_height_m": limits.get("max_height_m"),
        "legal_basis": LEGAL_BASIS,
    }


def check_against_legal(
    zone_type: str | None,
    bcr_pct: float | None = None,
    far_pct: float | None = None,
    tolerance_pct: float = 0.5,
) -> list[dict[str, Any]]:
    """주어진 건폐율/용적률이 해당 용도지역 법정 상한을 초과하는지 결정론 판정.

    조례·완화 등 정당한 근거 없이 법정 상한을 초과한 수치는 할루시네이션(또는 무출처 완화)
    으로 간주하여 위반 이슈를 반환한다.

    Args:
        zone_type: 용도지역명(정규화 전).
        bcr_pct: 검증 대상 건폐율(%).
        far_pct: 검증 대상 용적률(%).
        tolerance_pct: 반올림 오차 허용폭(%p). 기본 0.5%p.

    Returns:
        위반 이슈 목록. 위반 없으면 빈 리스트. 용도지역 미매칭 시에도 빈 리스트
        (이 경우 법정 상한을 알 수 없어 별도 일반 범위 규칙에 위임).
    """
    limits = legal_limits_for(zone_type)
    if limits is None:
        return []
    issues: list[dict[str, Any]] = []
    max_bcr = limits["max_bcr_pct"]
    max_far = limits["max_far_pct"]
    zone = limits["zone_type"]

    if bcr_pct is not None and max_bcr is not None and bcr_pct > max_bcr + tolerance_pct:
        issues.append({
            "type": "법정한도초과",
            "claim": f"건폐율 {bcr_pct:g}%",
            "severity": "high",
            "note": (
                f"{zone} 법정 건폐율 상한은 {max_bcr}%({LEGAL_BASIS}). "
                f"제시값 {bcr_pct:g}%는 상한을 초과 — 조례·지구단위계획 등 출처 미확인 시 "
                f"할루시네이션 의심. 법정값 {max_bcr}% 적용 권고."
            ),
        })
    if far_pct is not None and max_far is not None and far_pct > max_far + tolerance_pct:
        issues.append({
            "type": "법정한도초과",
            "claim": f"용적률 {far_pct:g}%",
            "severity": "high",
            "note": (
                f"{zone} 법정 용적률 상한은 {max_far}%({LEGAL_BASIS}). "
                f"제시값 {far_pct:g}%는 상한을 초과 — 조례·지구단위계획 등 출처 미확인 시 "
                f"할루시네이션 의심. 법정값 {max_far}% 적용 권고."
            ),
        })
    return issues
