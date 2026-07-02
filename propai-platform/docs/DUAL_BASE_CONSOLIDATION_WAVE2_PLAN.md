# 이중 DeclarativeBase 전면 통합 — Wave-1 완료 · Wave-2 실행계획 (2026-07-02)

## Wave-1 (본 PR에서 완료)
- legacy(core Base) 71테이블 → 9개 legacy-only 모델 파일(35테이블)을 canonical Base 로 이동 → legacy 36테이블 잔존.
- 교차 이중정의 19테이블 불변(증가 0), configure_mappers OK, 동결 테스트 3 passed, backend 5596·root 931 passed.
- 이동: collaboration.py, esg.py, g2b_bid.py, livekit.py, mass_template.py, memory.py, parcel_batch.py, tax_regional.py, v58_extensions.py
- 잔여 blocked(파일 내 dual 테이블 보유): auth.py·feasibility_vcs.py·project.py·v61_cost.py·v61_design.py
- 주의(문서화): 이동분 중 collaboration.py 의 FK organizations 참조 대상은 레거시 잔류(auth.py) — canonical metadata 단독 autogenerate 시 해당 FK 미해석. 런타임 무영향(테이블은 DB 실존·전역 create_all 없음), Wave-2 auth.py 통합 시 해소.

## Wave-2 대상 19테이블 소비처·위험 분석

Wave-2 Dual-Table Rewire Preparation: 19 tables require organization_id→tenant_id migration + TenantMixin/TimestampMixin/SoftDeleteMixin adoption. Key findings: (1) Users (28 consumers, HIGH risk): is_active type conversion, organization_id↔tenant_id FK mismatch, oauth field addition, full_name/name reconciliation. (2) Projects (72 consumers, HIGH risk): organization_id↔tenant_id, v61 extension columns (pnu_codes/zone_type/max_bcr/far), location decomposition (POINT→lat/lng), deleted_at addition, largest refactor surface. (3) API Keys (8 consumers, HIGH risk): organization_id↔tenant_id, key_prefix/scopes/last_used_at addition. (4-19) Design + Cost tables (collectively 121 consumers across drawings/design_stages/alternatives/layers, bim_quantities/cost_*/material_*/progress_billings/legal_rate/standard_price, feasibility_*): primarily TenantMixin + updated_at (mixin-style timestamp) additions; feasibility_branches/commits/tags (1 consumer each, test-only) are lowest priority. Phased approach: Phase-2A (users/projects/api_keys core auth entities, 3 migrations, 108 consumers), Phase-2B (design tables with updated_at, 5 migrations, ~40 consumers), Phase-2C (cost tables + feasibility VCS, 9 migrations, ~60 consumers). Critical: Multi-tenant isolation audit in drawing/project/cost queries; migration strategy for organization→tenant context inference (backfill via audit log or parent FK trace); ORM wrapper dual-source acceptance during cutover to avoid cascading rewire of 200+ consumer files."

### users — consumers 28 · risk high
- drift: Organization FK mismatch (legacy: organization_id | canonical: tenant_id via TenantMixin). is_active type drift (legacy: String(10) vs canonical: bool). Column name drift: full_name vs name. Added in canonical: oauth_provider, oauth_id, role. Missing in legacy: tenant_id FK and mixin columns.
- plan: 1. Map organization_id→tenant_id; add tenant_id FK. 2. Create migration to convert is_active String→bool. 3. Handle full_name/name merge or deprecation path. 4. Add oauth fields (nullable, additive). 5. Create ORM dual-wrapper during cutover to accept both Base sources. 6. Update 28 consumers in auth/rbac/admin/api endpoints. 7. Key file: tests/test_dual_base_freeze.py, app/services/auth/auth_service.py, app/routers/auth.py.

### projects — consumers 72 · risk high
- drift: Organization FK mismatch (legacy: organization_id | canonical: tenant_id). Mixin gap: legacy lacks TenantMixin/SoftDeleteMixin/TimestampMixin. New v61 columns in canonical (pnu_codes, zone_type, max_bcr/far, building_type, floor_above/below, analysis_snapshot). Location decomposition (legacy: location_point Geometry POINT vs canonical: latitude/longitude/location separate). Missing deleted_at column in legacy.
- plan: 1. Highest priority (72 consumers, most pervasive entity). 2. Add v61 extension columns (nullable, backward-compat). 3. Map organization_id→tenant_id + add tenant_id FK. 4. Add deleted_at column (SoftDeleteMixin). 5. Decompose/preserve location_point (migrate to lat/lng if needed). 6. Create migration 002_projects_v2_tenant_extend.py. 7. Key files: 72+ consumers in agents/pipeline/routers/services/tests. 8. Update ORM wrapper for CRUD translation.

### api_keys — consumers 8 · risk high
- drift: Organization FK mismatch (legacy: organization_id | canonical: tenant_id). Schema: Legacy 7 cols vs Canonical 11 cols. Added in canonical: key_prefix, scopes (ARRAY), last_used_at, updated_at. All core auth columns present in legacy but mixin-style metadata missing.
- plan: 1. Map organization_id→tenant_id + add tenant_id FK. 2. Add key_prefix, scopes (ARRAY), last_used_at columns. 3. Add TenantMixin/TimestampMixin. 4. Create migration 003_api_keys_v2_tenant_extend.py. 5. Update 8 consumers: auth/auth_service.py, routers/auth.py, main.py, rbac.py. 6. Add migration to populate key_prefix from existing key_hash prefix.

### feasibility_branches — consumers 1 · risk medium
- drift: Same file (feasibility_vcs.py), both Base definitions present. Legacy: Column-based (app.core.database.Base). Canonical: Mapped-based (apps.api.database.models.base.Base + TenantMixin). Signature: L:21 C:7 indicates legacy has ~14 extra columns or different definition style (direct Base.Column vs Mapped).
- plan: 1. Low consumer urgency (1 file = test only). 2. Verify actual column usage via deep grep in app/ codebase. 3. Check if feasibility_branches is active codepath or legacy/archived. 4. If active: add tenant_id FK + TenantMixin. 5. Migration 004_feasibility_vcs_v2_tenant.py (optional/deferred). 6. Consider V-cut strategy: repoint legacy imports to canonical in Phase-2B VCS layer refactor.

### feasibility_commits — consumers 1 · risk medium
- drift: Identical to feasibility_branches (same file feasibility_vcs.py). Both Base definitions coexist; schema signature matches branches.
- plan: 1. Bundled with feasibility_branches (Phase-2B VCS refactor). 2. Same action plan as branches. 3. Low standalone priority given 1 consumer.

### feasibility_tags — consumers 1 · risk medium
- drift: Identical to feasibility_branches/commits (same file feasibility_vcs.py). Schema signature L:21 C:7 matches.
- plan: 1. Bundled with feasibility_branches/commits (Phase-2B VCS refactor). 2. Lowest standalone priority (1 consumer = test).

### drawings — consumers 28 · risk high
- drift: Both in v61_design.py (legacy app/models/ vs canonical database/models/). Legacy: Column-based, app.core.database.Base (missing tenant_id FK, no mixin). Canonical: Mapped-based + TenantMixin + TimestampMixin. Signature: L:2 indicates legacy defines id/project_id explicitly; canonical adds tenant_id FK + updated_at from mixins. 28 consumers = design hot-path (routers/drawing.py, design_v61.py, agents, tests).
- plan: 1. High priority (28 consumers across design pipeline). 2. Add tenant_id FK + TenantMixin + TimestampMixin. 3. Verify multi-tenant isolation: all 28 consumers must filter by tenant context. 4. Create migration 005_drawings_v2_tenant.py. 5. Update key files: routers/drawing.py, routers/design_v61.py, design generation agents, all design services. 6. Critical: Audit ACL/RLS in draw queries to prevent cross-tenant data leakage.

### design_stages — consumers 4 · risk medium
- drift: Same file v61_design.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2 (id/project_id explicit). Canonical: Mapped + TenantMixin.
- plan: 1. Medium priority (4 consumers). 2. Add tenant_id FK + TenantMixin. 3. Create migration 006_design_stages_v2_tenant.py. 4. Update routers/drawing.py + design services + tests.

### design_alternatives — consumers 5 · risk medium
- drift: Same file v61_design.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2.
- plan: 1. Medium priority (5 consumers). 2. Add tenant_id FK + TenantMixin. 3. Create migration 007_design_alternatives_v2_tenant.py. 4. Update routers/drawing.py + services.

### drawing_layers — consumers 3 · risk low
- drift: Same file v61_design.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2. 3 consumers mostly in tests.
- plan: 1. Lower priority (3 consumers, test-heavy). 2. Add tenant_id FK + TenantMixin. 3. Bundle with drawing_edit_histories in migration 008_drawing_audit_v2_tenant.py.

### drawing_edit_histories — consumers 3 · risk low
- drift: Same file v61_design.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2. 3 consumers mostly in tests.
- plan: 1. Lower priority (3 consumers, test-heavy). 2. Add tenant_id FK + TenantMixin. 3. Bundle with drawing_layers in migration 008_drawing_audit_v2_tenant.py.

### permit_document_sets — consumers 3 · risk low
- drift: Same file v61_design.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2. 3 consumers mostly in tests.
- plan: 1. Lower priority (3 consumers). 2. Add tenant_id FK + TenantMixin. 3. Create migration 009_permit_documents_v2_tenant.py (separate, design workflow dependency).

### bim_quantities — consumers 10 · risk medium
- drift: Same file v61_cost.py. Legacy: Column-based (created_at direct). Canonical: Mapped + TenantMixin + TimestampMixin (has updated_at). Signature: L:2 (id/project_id explicit). Missing: tenant_id FK, updated_at. 10 consumers in cost/BIM pipeline (boq_auto.py, cost.py, services).
- plan: 1. Medium-high priority (10 consumers, cost domain hot-path). 2. Add tenant_id FK + TenantMixin + TimestampMixin. 3. Verify cost pipeline filters by tenant (critical multi-tenant isolation). 4. Create migration 010_bim_quantities_v2_tenant.py. 5. Update cost routers + boq_auto pipeline + services.

### cost_work_types — consumers 4 · risk medium
- drift: Same file v61_cost.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2. 4 consumers in cost tables bootstrap + tests.
- plan: 1. Medium priority (4 consumers). 2. Add tenant_id FK + TenantMixin. 3. Create migration 011_cost_work_types_v2_tenant.py. 4. Update cost/cost_tables_bootstrap.py + cost services.

### cost_calculation_sheets — consumers 3 · risk low
- drift: Same file v61_cost.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2. 3 consumers mostly in tests.
- plan: 1. Lower priority (3 consumers, test-heavy). 2. Add tenant_id FK + TenantMixin. 3. Create migration 012_cost_calculation_sheets_v2_tenant.py.

### material_unit_prices — consumers 8 · risk medium
- drift: Same file v61_cost.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2. 8 consumers in cost services + bootstrap + pricing pipelines.
- plan: 1. Medium priority (8 consumers). 2. Add tenant_id FK + TenantMixin. 3. Create migration 013_material_unit_prices_v2_tenant.py. 4. Update cost/cost_tables_bootstrap.py + pricing services.

### progress_billings — consumers 6 · risk medium
- drift: Same file v61_cost.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2. 6 consumers in billing services + finance routers.
- plan: 1. Medium priority (6 consumers). 2. Add tenant_id FK + TenantMixin. 3. Create migration 014_progress_billings_v2_tenant.py. 4. Update billing_service.py + finance/billing routers.

### legal_rate_histories — consumers 3 · risk low
- drift: Same file v61_cost.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2. 3 consumers mostly in tests.
- plan: 1. Lower priority (3 consumers, test-heavy). 2. Add tenant_id FK + TenantMixin. 3. Create migration 015_legal_rate_histories_v2_tenant.py.

### standard_price_updates — consumers 3 · risk low
- drift: Same file v61_cost.py. Legacy: Column-based, missing tenant_id FK + mixin. Signature: L:2. 3 consumers mostly in tests.
- plan: 1. Lower priority (3 consumers, test-heavy). 2. Add tenant_id FK + TenantMixin. 3. Create migration 016_standard_price_updates_v2_tenant.py.
