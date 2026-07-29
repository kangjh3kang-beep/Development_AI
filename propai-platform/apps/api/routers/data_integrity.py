"""
데이터 무결성 API — 시스템의 데이터 신뢰도를 실시간 모니터링.
"""
from fastapi import APIRouter

from apps.api.app.services.data_validation.public_data_registry import PublicDataRegistry

router = APIRouter(prefix="/data-integrity", tags=["데이터 무결성"])


@router.get("/status")
async def get_data_status():
    """전체 데이터 소스 상태 조회."""
    registry = PublicDataRegistry.get_instance()
    all_status = registry.get_all_status()
    stale = registry.get_stale_sources()
    hardcoded_warnings = registry.get_hardcoded_warnings()

    healthy_count = sum(1 for s in all_status if s["is_healthy"])
    total_count = len(all_status)

    return {
        "overall_health": "healthy" if healthy_count == total_count else "degraded",
        "healthy_sources": healthy_count,
        "total_sources": total_count,
        "stale_sources": stale,
        "hardcoded_warnings": hardcoded_warnings,
        "sources": all_status,
    }


@router.get("/freshness/{source_name}")
async def check_freshness(source_name: str):
    """특정 데이터 소스의 신선도 확인."""
    registry = PublicDataRegistry.get_instance()
    source = registry.get_status(source_name)
    if not source:
        return {"error": f"'{source_name}' 데이터 소스를 찾을 수 없습니다."}
    return source.to_dict()


@router.post("/refresh/{source_name}")
async def trigger_refresh(source_name: str):
    """특정 데이터 소스 수동 갱신 트리거."""
    # This would trigger the ETL for the specific source
    return {"message": f"'{source_name}' 갱신이 요청되었습니다.", "status": "queued"}


@router.get("/field-audit-status")
async def get_field_audit_status():
    """자가검증(field_audit) 레이어의 등록/활성 상태 조회 — 배포 회귀 가드(진단 전용).

    배포된 백엔드에서 analyze() 주경로의 field_audit 부착이 무성(silent) 회귀했는지
    스모크로 즉시 assert하기 위한 관측전용 엔드포인트. 분석을 실행하지 않고(부작용 0)
    등록 규칙 상태만 introspect한다. 무인증 공개 — 배포후 스모크가 서버에서 curl로 확인.

    반환 예: {"enabled": true, "rules_registered": 8, "rule_ids": ["G1_PROTECTION_ZONE_RISK", ...]}.
    """
    try:
        from apps.api.app.services.verification.field_audit import runner
    except ImportError:
        from app.services.verification.field_audit import runner
    return runner.audit_status()
