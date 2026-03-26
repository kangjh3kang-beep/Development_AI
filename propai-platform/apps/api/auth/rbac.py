"""Casbin 기반 RBAC (역할 기반 접근 제어).

casbin_rule 테이블은 Casbin 어댑터가 자동 생성한다.
정책: sub(역할), obj(리소스), act(동작) 기반 매칭.
"""

from functools import lru_cache

import casbin
from fastapi import Depends, HTTPException, status

from apps.api.auth.jwt_handler import CurrentUser, get_current_user

# RBAC 모델 정의 (인라인)
_RBAC_MODEL = """
[request_definition]
r = sub, obj, act

[policy_definition]
p = sub, obj, act

[role_definition]
g = _, _

[policy_effect]
e = some(where (p.eft == allow))

[matchers]
m = g(r.sub, p.sub) && r.obj == p.obj && r.act == p.act
"""

# 기본 정책: 역할별 리소스 접근 권한
_DEFAULT_POLICIES = [
    # admin: 모든 리소스 접근 가능
    ("admin", "projects", "read"),
    ("admin", "projects", "write"),
    ("admin", "projects", "delete"),
    ("admin", "users", "read"),
    ("admin", "users", "write"),
    ("admin", "users", "delete"),
    ("admin", "avm", "read"),
    ("admin", "avm", "write"),
    ("admin", "design", "read"),
    ("admin", "design", "write"),
    ("admin", "regulation", "read"),
    ("admin", "regulation", "write"),
    ("admin", "finance", "read"),
    ("admin", "finance", "write"),
    ("admin", "tax", "read"),
    ("admin", "tax", "write"),
    ("admin", "drone", "read"),
    ("admin", "drone", "write"),
    ("admin", "blockchain", "read"),
    ("admin", "blockchain", "write"),
    ("admin", "reports", "read"),
    ("admin", "reports", "write"),
    # manager: 조회 + 생성/수정 (삭제 제외)
    ("manager", "projects", "read"),
    ("manager", "projects", "write"),
    ("manager", "avm", "read"),
    ("manager", "avm", "write"),
    ("manager", "design", "read"),
    ("manager", "design", "write"),
    ("manager", "regulation", "read"),
    ("manager", "regulation", "write"),
    ("manager", "finance", "read"),
    ("manager", "finance", "write"),
    ("manager", "tax", "read"),
    ("manager", "tax", "write"),
    ("manager", "drone", "read"),
    ("manager", "drone", "write"),
    ("manager", "blockchain", "read"),
    ("manager", "reports", "read"),
    ("manager", "reports", "write"),
    # analyst: 조회 + 분석 기능 사용
    ("analyst", "projects", "read"),
    ("analyst", "avm", "read"),
    ("analyst", "avm", "write"),
    ("analyst", "design", "read"),
    ("analyst", "regulation", "read"),
    ("analyst", "regulation", "write"),
    ("analyst", "finance", "read"),
    ("analyst", "finance", "write"),
    ("analyst", "tax", "read"),
    ("analyst", "tax", "write"),
    ("analyst", "drone", "read"),
    ("analyst", "reports", "read"),
    # viewer: 조회 전용
    ("viewer", "projects", "read"),
    ("viewer", "avm", "read"),
    ("viewer", "design", "read"),
    ("viewer", "regulation", "read"),
    ("viewer", "finance", "read"),
    ("viewer", "tax", "read"),
    ("viewer", "drone", "read"),
    ("viewer", "reports", "read"),
    # 웹훅
    ("admin", "webhooks", "read"),
    ("admin", "webhooks", "write"),
    ("admin", "webhooks", "delete"),
    ("manager", "webhooks", "read"),
    ("manager", "webhooks", "write"),
    # API 키
    ("admin", "api_keys", "read"),
    ("admin", "api_keys", "write"),
    ("admin", "api_keys", "delete"),
    ("admin", "notifications", "write"),
    ("manager", "notifications", "write"),
    ("admin", "esign", "read"),
    ("admin", "esign", "write"),
    ("manager", "esign", "read"),
    ("manager", "esign", "write"),
    ("analyst", "esign", "read"),
    ("admin", "dashboard", "read"),
    ("manager", "dashboard", "read"),
    ("analyst", "dashboard", "read"),
    ("viewer", "dashboard", "read"),
    ("admin", "system", "read"),
    ("manager", "system", "read"),
    ("analyst", "system", "read"),
    ("viewer", "system", "read"),
    ("admin", "ai_costs", "read"),
    ("admin", "ai_costs", "write"),
    ("manager", "ai_costs", "read"),
    ("manager", "ai_costs", "write"),
    ("analyst", "ai_costs", "read"),
    ("admin", "energy", "read"),
    ("manager", "energy", "read"),
    ("analyst", "energy", "read"),
    ("viewer", "energy", "read"),
    ("admin", "underwriting", "read"),
    ("admin", "underwriting", "write"),
    ("manager", "underwriting", "read"),
    ("manager", "underwriting", "write"),
    ("analyst", "underwriting", "read"),
    ("admin", "compliance", "read"),
    ("admin", "compliance", "write"),
    ("manager", "compliance", "read"),
    ("manager", "compliance", "write"),
    ("analyst", "compliance", "read"),
    ("admin", "leases", "read"),
    ("admin", "leases", "write"),
    ("manager", "leases", "read"),
    ("manager", "leases", "write"),
    ("analyst", "leases", "read"),
    ("admin", "esg", "read"),
    ("admin", "esg", "write"),
    ("manager", "esg", "read"),
    ("manager", "esg", "write"),
    ("analyst", "esg", "read"),
    ("viewer", "esg", "read"),
    ("admin", "climate", "read"),
    ("admin", "climate", "write"),
    ("manager", "climate", "read"),
    ("manager", "climate", "write"),
    ("analyst", "climate", "read"),
    ("viewer", "climate", "read"),
    ("admin", "marketing", "read"),
    ("admin", "marketing", "write"),
    ("manager", "marketing", "read"),
    ("manager", "marketing", "write"),
    ("analyst", "marketing", "read"),
    ("analyst", "marketing", "write"),
    ("viewer", "marketing", "read"),
    ("admin", "domain_agents", "read"),
    ("admin", "domain_agents", "write"),
    ("manager", "domain_agents", "read"),
    ("manager", "domain_agents", "write"),
    ("analyst", "domain_agents", "read"),
    ("analyst", "domain_agents", "write"),
    ("admin", "maintenance", "read"),
    ("admin", "maintenance", "write"),
    ("manager", "maintenance", "read"),
    ("manager", "maintenance", "write"),
    ("analyst", "maintenance", "read"),
    ("admin", "tenant_experience", "read"),
    ("admin", "tenant_experience", "write"),
    ("manager", "tenant_experience", "read"),
    ("manager", "tenant_experience", "write"),
    ("analyst", "tenant_experience", "read"),
    ("analyst", "tenant_experience", "write"),
    ("viewer", "tenant_experience", "read"),
    ("admin", "asset_intelligence", "read"),
    ("admin", "asset_intelligence", "write"),
    ("manager", "asset_intelligence", "read"),
    ("manager", "asset_intelligence", "write"),
    ("analyst", "asset_intelligence", "read"),
    ("analyst", "asset_intelligence", "write"),
    ("viewer", "asset_intelligence", "read"),
    ("admin", "portals", "read"),
    ("admin", "portals", "write"),
    ("manager", "portals", "read"),
    ("manager", "portals", "write"),
    ("analyst", "portals", "read"),
    ("analyst", "portals", "write"),
    ("viewer", "portals", "read"),
    ("admin", "chatbot", "read"),
    ("admin", "chatbot", "write"),
    ("manager", "chatbot", "read"),
    ("manager", "chatbot", "write"),
    ("analyst", "chatbot", "read"),
    ("analyst", "chatbot", "write"),
    ("admin", "auction", "read"),
    ("admin", "auction", "write"),
    ("manager", "auction", "read"),
    ("manager", "auction", "write"),
    ("analyst", "auction", "read"),
    ("analyst", "auction", "write"),
    ("viewer", "auction", "read"),
    ("admin", "contractors", "read"),
    ("admin", "contractors", "write"),
    ("manager", "contractors", "read"),
    ("manager", "contractors", "write"),
    ("analyst", "contractors", "read"),
    ("viewer", "contractors", "read"),
    ("admin", "kdx", "read"),
    ("admin", "kdx", "write"),
    ("manager", "kdx", "read"),
    ("manager", "kdx", "write"),
    ("analyst", "kdx", "read"),
    ("analyst", "kdx", "write"),
    ("viewer", "kdx", "read"),
    ("admin", "cost_intelligence", "read"),
    ("admin", "cost_intelligence", "write"),
    ("manager", "cost_intelligence", "read"),
    ("manager", "cost_intelligence", "write"),
    ("analyst", "cost_intelligence", "read"),
    ("analyst", "cost_intelligence", "write"),
    ("viewer", "cost_intelligence", "read"),
    ("admin", "contracts", "read"),
    ("admin", "contracts", "write"),
    ("manager", "contracts", "read"),
    ("manager", "contracts", "write"),
    ("analyst", "contracts", "read"),
    ("analyst", "contracts", "write"),
    ("viewer", "contracts", "read"),
    ("admin", "digital_twin_status", "read"),
    ("admin", "digital_twin_status", "write"),
    ("manager", "digital_twin_status", "read"),
    ("manager", "digital_twin_status", "write"),
    ("analyst", "digital_twin_status", "read"),
    ("analyst", "digital_twin_status", "write"),
    ("viewer", "digital_twin_status", "read"),
    ("admin", "risk_engine", "read"),
    ("admin", "risk_engine", "write"),
    ("manager", "risk_engine", "read"),
    ("manager", "risk_engine", "write"),
    ("analyst", "risk_engine", "read"),
    ("analyst", "risk_engine", "write"),
    ("viewer", "risk_engine", "read"),
    ("admin", "permits", "read"),
    ("admin", "permits", "write"),
    ("manager", "permits", "read"),
    ("manager", "permits", "write"),
    ("analyst", "permits", "read"),
    ("analyst", "permits", "write"),
    ("viewer", "permits", "read"),
    ("admin", "safety", "read"),
    ("admin", "safety", "write"),
    ("manager", "safety", "read"),
    ("manager", "safety", "write"),
    ("analyst", "safety", "read"),
    ("analyst", "safety", "write"),
    ("viewer", "safety", "read"),
    ("admin", "parking", "read"),
    ("admin", "parking", "write"),
    ("manager", "parking", "read"),
    ("manager", "parking", "write"),
    ("analyst", "parking", "read"),
    ("analyst", "parking", "write"),
    ("viewer", "parking", "read"),
    ("admin", "webrtc", "read"),
    ("admin", "webrtc", "write"),
    ("manager", "webrtc", "read"),
    ("manager", "webrtc", "write"),
    ("analyst", "webrtc", "read"),
    ("analyst", "webrtc", "write"),
    ("viewer", "webrtc", "read"),
    ("admin", "sre", "read"),
    ("admin", "sre", "write"),
    ("manager", "sre", "read"),
    ("manager", "sre", "write"),
    ("analyst", "sre", "read"),
    ("analyst", "sre", "write"),
    ("viewer", "sre", "read"),
]


@lru_cache
def _get_enforcer() -> casbin.Enforcer:
    """Casbin 엔포서를 생성한다. 앱 시작 시 한 번만 호출."""
    import os
    import tempfile

    # 모델 파일을 임시 파일로 생성 (casbin은 파일 경로를 요구)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".conf", delete=False) as model_file:
        model_file.write(_RBAC_MODEL)
        model_path = model_file.name

    enforcer = casbin.Enforcer(model_path)
    os.unlink(model_path)

    # 기본 정책 로드
    for policy in _DEFAULT_POLICIES:
        enforcer.add_policy(*policy)

    return enforcer


def check_permission(role: str, resource: str, action: str) -> bool:
    """권한을 확인한다."""
    enforcer = _get_enforcer()
    return bool(enforcer.enforce(role, resource, action))


class RequirePermission:
    """FastAPI Depends로 사용하는 권한 검사 클래스.

    사용 예시:
        @router.get("/projects", dependencies=[Depends(RequirePermission("projects", "read"))])
    """

    def __init__(self, resource: str, action: str) -> None:
        self.resource = resource
        self.action = action

    async def __call__(
        self,
        current_user: CurrentUser = Depends(get_current_user),
    ) -> CurrentUser:
        if not check_permission(current_user.role, self.resource, self.action):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{self.resource}' 리소스에 대한 '{self.action}' 권한이 없습니다",
            )
        return current_user
