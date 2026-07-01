"""P1-7 봉쇄: 이중 DeclarativeBase 드리프트 동결(alembic 커버리지 갭 확산 방지).

배경(감사 P1-7): app/core/database.py Base(레거시, app/models/* 29테이블)와
apps/api/database/models Base(canonical, 200+테이블)가 병존하며, 실사용 alembic
(alembic.ini → database/migrations)은 canonical 만 본다 — 레거시 모델은 autogenerate
비추적. 게다가 레거시엔 스테일 모델이 있어(예: auth.User=organization_id vs 실스키마
tenant_id) 양쪽에 같은 테이블명(users/projects/api_keys)이 이중 정의돼 있다 →
'일괄 통합'은 중복 테이블 충돌·파괴적 autogenerate diff 위험(별도 정리 트랙 필요).

본 테스트는 그때까지의 봉쇄 게이트다:
 1) 레거시 Base 테이블 집합 동결 — 새 모델을 레거시에 추가하면 실패(신규는 canonical 로).
 2) 교차 이중정의 동결 — 새로운 테이블명 중복이 생기면 실패(가짜/파괴적 diff 예방).
 3) alembic script_location 이 canonical 트리를 가리키는지 고정(사장 트리 재지정 방지).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _API_DIR.parents[1]
for p in (str(_REPO_ROOT), str(_API_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("INTERP_REDIS_CACHE", "0")

import app.models  # noqa: F401,E402 — 레거시 모델 등록(import 부작용으로 metadata 채움)
from app.core.database import Base as LegacyBase  # noqa: E402
from apps.api.database.models import Base as CanonicalBase  # noqa: E402

# ── 동결 스냅샷(2026-07-02 census) — 변경은 '의도적 정리 트랙'에서만 갱신할 것 ──
LEGACY_ALLOWED = frozenset({
    "agent_memories", "api_keys", "audit_logs", "design_review_results",
    "digital_twin_realtime", "epd_material_carbon", "land_compensation_estimates",
    "land_parcels", "land_use_zones", "lca_assessments", "lcc_analyses",
    "lifecycle_optimization", "mass_templates", "natural_disaster_risk",
    "organizations", "parcel_groups", "permissions", "portfolio_optimization",
    "procurement_optimization", "projects", "public_insight_reports",
    "regulation_change_log", "role_permissions", "roles", "site_analysis_reports",
    "smart_city_data", "user_roles", "users", "zeb_certifications",
})
# 스테일 레거시(auth.py 등)와 canonical 이 같은 테이블명을 이중 정의 중인 기존 부채.
KNOWN_CROSS_DUPLICATES = frozenset({"api_keys", "projects", "users"})


def test_legacy_base_frozen_no_new_models():
    current = frozenset(LegacyBase.metadata.tables)
    new = current - LEGACY_ALLOWED
    assert not new, (
        f"레거시 Base(app/core/database)에 새 모델 추가 금지 — canonical"
        f"(apps/api/database/models) Base 를 사용하라(alembic 추적 대상). 신규: {sorted(new)}"
    )


def test_no_new_cross_base_duplicate_tables():
    dup = frozenset(LegacyBase.metadata.tables) & frozenset(CanonicalBase.metadata.tables)
    new_dup = dup - KNOWN_CROSS_DUPLICATES
    assert not new_dup, (
        f"레거시↔canonical 에 같은 테이블명 이중 정의 신규 발생 — 스테일 diff/충돌 위험: {sorted(new_dup)}"
    )


def test_alembic_targets_canonical_tree():
    ini = (_API_DIR / "alembic.ini").read_text(encoding="utf-8")
    assert "script_location = database/migrations" in ini, (
        "alembic 은 canonical 트리(database/migrations)만 사용해야 한다"
    )
