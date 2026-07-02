"""분석 대시보드 라우터 — 투자수익성/IoT/ESG 종합 지표.

프론트(InvestmentDashboard/IoTDashboard/ESGDashboard)가 기대하는 형태로 응답한다.
IoT 센서·자산 텔레메트리는 라이브 하드웨어 연동 전까지 대표 집계값을 제공하며,
ESG/투자 지표는 향후 프로젝트 컨텍스트(부지분석·수지·GRESB) 연동으로 정밀화한다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from apps.api.auth.jwt_handler import CurrentUser
from apps.api.auth.rbac import RequirePermission

router = APIRouter()


@router.get("/investment")
async def investment_analytics(
    current_user: CurrentUser = Depends(RequirePermission("analytics", "read")),
) -> dict:
    """투자수익성 종합 지표(16대 투자특성 + AVM/IRR/CapRate/NOI)."""
    _ = current_user
    return {
        "features": [
            {"feature": "입지", "score": 88, "maxScore": 100},
            {"feature": "교통", "score": 75, "maxScore": 100},
            {"feature": "학군", "score": 82, "maxScore": 100},
            {"feature": "상권", "score": 69, "maxScore": 100},
            {"feature": "자연환경", "score": 91, "maxScore": 100},
            {"feature": "개발호재", "score": 64, "maxScore": 100},
            {"feature": "인구유입", "score": 77, "maxScore": 100},
            {"feature": "임대수요", "score": 83, "maxScore": 100},
            {"feature": "공급물량", "score": 56, "maxScore": 100},
            {"feature": "법규리스크", "score": 72, "maxScore": 100},
            {"feature": "환경리스크", "score": 85, "maxScore": 100},
            {"feature": "시장성", "score": 79, "maxScore": 100},
            {"feature": "수익성", "score": 68, "maxScore": 100},
            {"feature": "안정성", "score": 90, "maxScore": 100},
            {"feature": "유동성", "score": 62, "maxScore": 100},
            {"feature": "성장성", "score": 74, "maxScore": 100},
        ],
        "avm_estimate_krw": 12_500_000_000,
        "avm_confidence": 0.87,
        "irr_percent": 14.2,
        "cap_rate_percent": 5.8,
        "noi_krw": 725_000_000,
        "monthly_trend": [
            {"month": "2025-10", "value": 11_800_000_000},
            {"month": "2025-11", "value": 11_950_000_000},
            {"month": "2025-12", "value": 12_100_000_000},
            {"month": "2026-01", "value": 12_200_000_000},
            {"month": "2026-02", "value": 12_350_000_000},
            {"month": "2026-03", "value": 12_500_000_000},
        ],
    }


@router.get("/iot")
async def iot_analytics(
    current_user: CurrentUser = Depends(RequirePermission("analytics", "read")),
) -> dict:
    """IoT 센서/예지보전 종합(센서 시계열 + 알림 + 요약)."""
    _ = current_user
    sensors: list[dict] = []
    _seed = {"temperature": (22.1, "°C"), "humidity": (55.0, "%"), "co2": (425.0, "ppm")}
    for stype, (base, unit) in _seed.items():
        for h in range(8):
            sensors.append({
                "timestamp": f"2026-03-22T0{h}:00:00Z",
                "sensor_id": f"{stype[:3]}-01",
                "sensor_type": stype,
                "value": round(base + (h - 4) * (0.3 if stype == "temperature" else 1.0), 1),
                "unit": unit,
            })
    return {
        "sensors": sensors,
        "alerts": [
            {
                "id": "alert-1", "equipment_name": "냉동기 #2", "alert_type": "vibration_anomaly",
                "severity": "critical", "predicted_failure_date": "2026-04-05", "confidence": 0.89,
                "message": "진동 패턴 이상 감지. 베어링 교체 권장.",
            },
            {
                "id": "alert-2", "equipment_name": "AHU-03", "alert_type": "filter_degradation",
                "severity": "warning", "predicted_failure_date": "2026-04-15", "confidence": 0.76,
                "message": "필터 효율 저하 추세. 2주 내 교체 필요.",
            },
            {
                "id": "alert-3", "equipment_name": "엘리베이터 #1", "alert_type": "motor_wear",
                "severity": "info", "predicted_failure_date": "2026-06-01", "confidence": 0.62,
                "message": "모터 마모도 정상 범위이나 모니터링 지속 권장.",
            },
        ],
        "sensor_summary": [
            {"type": "temperature", "count": 12, "avg_value": 22.1, "unit": "°C"},
            {"type": "humidity", "count": 8, "avg_value": 56.4, "unit": "%"},
            {"type": "co2", "count": 6, "avg_value": 433, "unit": "ppm"},
            {"type": "energy", "count": 4, "avg_value": 145.2, "unit": "kWh"},
        ],
    }


@router.get("/esg")
async def esg_analytics(
    current_user: CurrentUser = Depends(RequirePermission("analytics", "read")),
) -> dict:
    """ESG 종합 점수(GRESB 기준 + 환경/사회/지배구조 지표 + 탄소 스코프)."""
    _ = current_user
    return {
        "overall_score": 78.5,
        "gresb_rating": "4-Star",
        "metrics": [
            {"id": "e1", "label": "탄소 배출량 (Scope 1)", "value": 120, "unit": "tCO2e",
             "target": 100, "trend": "down"},
            {"id": "e2", "label": "탄소 배출량 (Scope 2)", "value": 280, "unit": "tCO2e",
             "target": 250, "trend": "down"},
            {"id": "e3", "label": "에너지 자립률", "value": 34, "unit": "%", "target": 40, "trend": "up"},
            {"id": "e4", "label": "재생에너지 비율", "value": 22, "unit": "%", "target": 30, "trend": "up"},
            {"id": "s1", "label": "안전사고율 (LTIR)", "value": 0.8, "unit": "", "target": 0.5, "trend": "down"},
            {"id": "s2", "label": "지역사회 프로그램", "value": 5, "unit": "건", "target": 4, "trend": "stable"},
            {"id": "g1", "label": "이사회 독립성", "value": 67, "unit": "%", "target": 60, "trend": "up"},
            {"id": "g2", "label": "공시 준수율", "value": 95, "unit": "%", "target": 100, "trend": "up"},
        ],
        "carbon_by_scope": [
            {"scope": "Scope 1", "tco2e": 120},
            {"scope": "Scope 2", "tco2e": 280},
            {"scope": "Scope 3", "tco2e": 450},
        ],
    }
