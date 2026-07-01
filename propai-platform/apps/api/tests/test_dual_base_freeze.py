"""P1-7 봉쇄: 이중 DeclarativeBase 드리프트 동결(alembic 커버리지 갭 확산 방지).

배경(감사 P1-7): app/core/database.py Base(레거시)와 apps/api/database/models Base(canonical,
200+테이블)가 병존하며, 실사용 alembic(alembic.ini → database/migrations)은 canonical 만 본다 —
레거시 모델은 autogenerate 비추적. 전 서브모듈 census(2026-07-02) 결과 레거시 71테이블,
교차 이중정의 19건(스테일 정의 포함: 예 auth.User=organization_id vs 실스키마 tenant_id) —
'일괄 통합'은 중복 테이블 충돌·파괴적 autogenerate diff 위험(별도 정리 트랙 필요).

본 테스트는 그때까지의 봉쇄 게이트다:
 1) 레거시 Base 테이블 집합 동결 — 새 모델을 레거시에 추가하면 실패(신규는 canonical 로).
 2) 교차 이중정의 동결 — 새로운 테이블명 중복이 생기면 실패(가짜/파괴적 diff 예방).
 3) alembic script_location 이 canonical 트리를 가리키는지 고정(사장 트리 재지정 방지).

census 는 pkgutil 로 app/models 전 서브모듈을 명시 로드해 산출한다(다른 테스트의 직접 import
순서에 무관한 완전 집합 — 부분 로드 census 는 전체 스위트에서 거짓 실패했음).
"""
from __future__ import annotations

import contextlib
import importlib
import os
import pkgutil
import sys
from pathlib import Path

_API_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _API_DIR.parents[1]
for p in (str(_REPO_ROOT), str(_API_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

os.environ.setdefault("INTERP_REDIS_CACHE", "0")

import app.models as _legacy_pkg  # noqa: E402

# 전 서브모듈 명시 로드(완전 census). 깨진 모듈(예: feasibility — 존재하지 않는
# app.models.base 를 import하는 사장 코드)은 건너뛴다(테이블 등록 자체가 불가능한 모듈).
for _m in pkgutil.iter_modules(_legacy_pkg.__path__):
    # 깨진 사장 모듈은 어차피 테이블 등록이 불가능해 census 대상이 아님 — 건너뜀.
    with contextlib.suppress(Exception):
        importlib.import_module(f"app.models.{_m.name}")

from app.core.database import Base as LegacyBase  # noqa: E402
from apps.api.database.models import Base as CanonicalBase  # noqa: E402

# ── 동결 스냅샷(2026-07-02 전 서브모듈 census) — 갱신은 '의도적 정리 트랙'에서만 ──
LEGACY_ALLOWED = frozenset({
    "adjusted_areas", "agent_memories", "ai_recommendations", "api_keys", "audit_logs",
    "batch_aggregate", "batch_item_result", "bim_quantities", "collaborator_invites",
    "cost_calculation_sheets", "cost_work_types", "design_alternatives",
    "design_review_results", "design_stages", "development_type_tax_mappings",
    "digital_twin_realtime", "drawing_edit_histories", "drawing_layers", "drawings",
    "epd_material_carbon", "feasibility_branches", "feasibility_commits",
    "feasibility_diffs", "feasibility_rollbacks", "feasibility_shares", "feasibility_tags",
    "g2b_award_stats", "g2b_bid_analyses", "g2b_bids", "land_compensation_estimates",
    "land_parcels", "land_use_zones", "law_change_alerts", "law_changes",
    "lca_assessments", "lcc_analyses", "legal_rate_histories", "lifecycle_optimization",
    "livekit_recordings", "mass_templates", "material_unit_prices",
    "natural_disaster_risk", "optimization_results", "optimization_runs",
    "organizations", "parcel_batch_job", "parcel_groups", "permissions",
    "permit_document_sets", "portfolio_optimization", "procurement_optimization",
    "progress_billings", "project_documents", "project_members", "projects",
    "public_insight_reports", "region_tax_rates", "regions", "regulation_change_log",
    "review_comments", "role_permissions", "roles", "site_analysis_reports",
    "smart_city_data", "standard_price_updates", "tax_calculation_results", "tax_codes",
    "tax_exemptions", "user_roles", "users", "zeb_certifications",
})
# 레거시↔canonical 같은 테이블명 이중 정의(기존 부채 19건 — 스테일 diff 위험 목록).
KNOWN_CROSS_DUPLICATES = frozenset({
    "api_keys", "bim_quantities", "cost_calculation_sheets", "cost_work_types",
    "design_alternatives", "design_stages", "drawing_edit_histories", "drawing_layers",
    "drawings", "feasibility_branches", "feasibility_commits", "feasibility_tags",
    "legal_rate_histories", "material_unit_prices", "permit_document_sets",
    "progress_billings", "projects", "standard_price_updates", "users",
})


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
