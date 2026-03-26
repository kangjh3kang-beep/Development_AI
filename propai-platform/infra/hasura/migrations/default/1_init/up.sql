-- PropAI v30.0 - 초기 마이그레이션
-- 참고: 실제 테이블은 Alembic(apps/api/migrations/)에서 관리
-- Hasura 마이그레이션은 Hasura 전용 메타데이터/뷰만 관리

-- GraphQL 구독용 뷰 (프로젝트 대시보드)
CREATE OR REPLACE VIEW public.project_dashboard_view AS
SELECT
    p.id,
    p.name,
    p.status,
    p.location,
    p.total_area,
    p.created_at,
    p.updated_at,
    u.full_name AS owner_name,
    (SELECT COUNT(*) FROM public.site_analyses sa WHERE sa.project_id = p.id) AS site_analysis_count,
    (SELECT COUNT(*) FROM public.avm_valuations av WHERE av.project_id = p.id) AS valuation_count,
    (SELECT COUNT(*) FROM public.permits pm WHERE pm.project_id = p.id) AS permit_count
FROM public.projects p
LEFT JOIN public.users u ON p.owner_id = u.id;

-- GraphQL 구독용 뷰 (에스크로 상태)
CREATE OR REPLACE VIEW public.escrow_status_view AS
SELECT
    et.id,
    et.project_id,
    et.tx_hash,
    et.status,
    et.amount,
    et.created_at,
    p.name AS project_name
FROM public.escrow_transactions et
LEFT JOIN public.projects p ON et.project_id = p.id;
