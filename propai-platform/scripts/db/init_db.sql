-- ================================================================
-- PropAI v43.0 전체 DB 스키마 통합본 (60개 테이블)
-- 실행: psql -U propai -d propai_db -f scripts/db/init_db.sql
-- ================================================================

-- 확장 프로그램
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- ================================================================
-- 1. 멀티테넌트 기반
-- ================================================================
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR(200) NOT NULL,
    slug            VARCHAR(100) UNIQUE NOT NULL,
    plan            VARCHAR(20)  DEFAULT 'free',  -- free|pro|enterprise
    settings_json   TEXT,
    is_active       BOOLEAN DEFAULT true,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID REFERENCES tenants(tenant_id),
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255),
    name            VARCHAR(100),
    role            VARCHAR(20) DEFAULT 'user',     -- superadmin|admin|manager|user
    kakao_id        VARCHAR(100),
    phone           VARCHAR(20),
    profile_image   TEXT,
    language        VARCHAR(5) DEFAULT 'ko',
    is_active       BOOLEAN DEFAULT true,
    last_login_at   TIMESTAMP,
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_email  ON users(email);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    token_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash      VARCHAR(255) NOT NULL,
    expires_at      TIMESTAMP NOT NULL,
    revoked         BOOLEAN DEFAULT false,
    created_at      TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_refresh_tokens_user ON refresh_tokens(user_id, expires_at);

-- ================================================================
-- 2. 프로젝트 + 필지
-- ================================================================
CREATE TABLE IF NOT EXISTS projects (
    project_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID REFERENCES tenants(tenant_id),
    user_id             UUID NOT NULL REFERENCES users(user_id),
    name                VARCHAR(200) NOT NULL,
    address             TEXT,
    geom                GEOMETRY(POINT, 4326),
    parcel_pnu          VARCHAR(20),
    land_area_m2        NUMERIC(12,2),
    building_area_m2    NUMERIC(12,2),
    gross_floor_area_m2 NUMERIC(12,2),
    floor_area_ratio    NUMERIC(6,2),
    building_coverage   NUMERIC(6,2),
    land_use            VARCHAR(50),
    building_use        VARCHAR(50),
    total_floors        INTEGER,
    basement_floors     INTEGER DEFAULT 0,
    status              VARCHAR(30) DEFAULT 'analysis',
    metadata_json       TEXT,
    created_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_projects_user    ON projects(user_id);
CREATE INDEX idx_projects_tenant  ON projects(tenant_id);
CREATE INDEX idx_projects_geom    ON projects USING GIST(geom);

CREATE TABLE IF NOT EXISTS parcels (
    pnu                 VARCHAR(20) PRIMARY KEY,
    address             TEXT,
    geom                GEOMETRY(MULTIPOLYGON, 4326),
    land_area_m2        NUMERIC(12,2),
    land_use            VARCHAR(50),
    land_category       VARCHAR(20),
    road_width_m        NUMERIC(6,1),
    floor_area_ratio    NUMERIC(6,2),
    building_coverage   NUMERIC(6,2),
    official_price_krw  BIGINT,
    height_limit_m      NUMERIC(6,1),
    fetched_at          TIMESTAMP DEFAULT NOW(),
    updated_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_parcels_geom ON parcels USING GIST(geom);

-- ================================================================
-- 3. AVM 시세
-- ================================================================
CREATE TABLE IF NOT EXISTS avm_valuations (
    valuation_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    pnu                 VARCHAR(20),
    estimated_price_krw BIGINT,
    lower_bound_krw     BIGINT,
    upper_bound_krw     BIGINT,
    confidence          NUMERIC(4,3),
    model_version       VARCHAR(50),
    features_json       TEXT,
    shap_json           TEXT,
    comparable_json     TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_avm_project ON avm_valuations(project_id, created_at DESC);

-- ================================================================
-- 4. 법규 준수
-- ================================================================
CREATE TABLE IF NOT EXISTS regulation_checks (
    check_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    check_type          VARCHAR(30),
    violations_json     TEXT,
    warnings_json       TEXT,
    applicable_laws     TEXT,
    floor_area_ratio_ok BOOLEAN,
    building_coverage_ok BOOLEAN,
    height_ok           BOOLEAN,
    ai_opinion          TEXT,
    checked_at          TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 5. AI 설계
-- ================================================================
CREATE TABLE IF NOT EXISTS designs (
    design_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    design_type         VARCHAR(30),
    prompt_summary      TEXT,
    design_content      TEXT,
    bim_ifc_url         TEXT,
    thumbnail_url       TEXT,
    floor_plan_url      TEXT,
    area_program_json   TEXT,
    is_favorite         BOOLEAN DEFAULT false,
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_designs_project ON designs(project_id, created_at DESC);

-- ================================================================
-- 6. 금융/투자 분석
-- ================================================================
CREATE TABLE IF NOT EXISTS financial_analyses (
    analysis_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    total_cost_krw      BIGINT,
    land_cost_krw       BIGINT,
    construction_cost_krw BIGINT,
    finance_cost_krw    BIGINT,
    expected_revenue_krw BIGINT,
    irr_pct             NUMERIC(6,2),
    npv_krw             BIGINT,
    payback_years       NUMERIC(5,1),
    ltv_pct             NUMERIC(5,2),
    dsr_pct             NUMERIC(5,2),
    risk_level          VARCHAR(20),
    monte_carlo_json    TEXT,
    scenario_json       TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- 투자 언더라이팅 (G81)
CREATE TABLE IF NOT EXISTS investment_underwriting (
    underwriting_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    purchase_price_krw  BIGINT,
    equity_ratio_pct    NUMERIC(5,2),
    loan_rate_pct       NUMERIC(5,2),
    hold_years          INTEGER,
    exit_cap_rate_pct   NUMERIC(5,2),
    irr_pct             NUMERIC(6,2),
    equity_multiple     NUMERIC(5,2),
    npv_krw             BIGINT,
    scenario            VARCHAR(20),
    lp_report_text      TEXT,
    data_room_url       TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 7. 세금/계약
-- ================================================================
CREATE TABLE IF NOT EXISTS tax_calculations (
    calc_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    calc_type           VARCHAR(20),    -- acquisition|transfer|holding
    purchase_price_krw  BIGINT,
    sale_price_krw      BIGINT,
    tax_amount_krw      BIGINT,
    tax_rate_pct        NUMERIC(6,2),
    deductions_json     TEXT,
    scenario_json       TEXT,
    calculated_at       TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lease_abstractions (
    lease_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    tenant_name         VARCHAR(100),
    lease_start         DATE,
    lease_end           DATE,
    monthly_rent_krw    INTEGER,
    deposit_krw         BIGINT,
    discount_rate_pct   NUMERIC(5,2) DEFAULT 4.5,
    pv_total_krw        BIGINT,
    ifrs16_json         TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 8. 시공/ESG
-- ================================================================
CREATE TABLE IF NOT EXISTS construction_logs (
    log_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    log_type            VARCHAR(30),
    bim4d_json          TEXT,
    carbon_total_kg     NUMERIC(12,2),
    epc_kwh_m2          NUMERIC(8,2),
    zeb_rate_pct        NUMERIC(5,1),
    climate_risk_json   TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ESG 보고서 (G84)
CREATE TABLE IF NOT EXISTS esg_reports (
    report_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    gresb_score         INTEGER,
    cdp_score           VARCHAR(5),
    carbon_tons_yr      NUMERIC(10,2),
    energy_kwh_m2       NUMERIC(8,2),
    water_m3_m2         NUMERIC(8,3),
    waste_recycle_pct   NUMERIC(5,1),
    narrative_json      TEXT,
    report_year         INTEGER,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- 기후 리스크 (G85)
CREATE TABLE IF NOT EXISTS climate_risk_assessments (
    assessment_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    flood_risk          INTEGER,
    heat_risk           INTEGER,
    storm_risk          INTEGER,
    drought_risk        INTEGER,
    overall_risk        INTEGER,
    insurance_json      TEXT,
    assessed_at         TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 9. 준법감시/KYC (G82)
-- ================================================================
CREATE TABLE IF NOT EXISTS compliance_checks (
    check_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    check_type          VARCHAR(30),
    status              VARCHAR(20),
    result_json         TEXT,
    checked_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kyc_documents (
    kyc_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(user_id),
    doc_type            VARCHAR(30),
    doc_url             TEXT,
    verification_status VARCHAR(20) DEFAULT 'pending',
    verified_at         TIMESTAMP,
    expires_at          TIMESTAMP,
    ai_result_json      TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aml_screenings (
    screening_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(user_id),
    screening_type      VARCHAR(30),
    risk_score          NUMERIC(4,1),
    risk_level          VARCHAR(20),
    matches_json        TEXT,
    screened_at         TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 10. 한국특화 (전세/경공매)
-- ================================================================
CREATE TABLE IF NOT EXISTS jeonse_analyses (
    analysis_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    jeonse_price_krw    BIGINT,
    market_price_krw    BIGINT,
    jeonse_ratio        NUMERIC(4,3),
    risk_grade          VARCHAR(5),
    fraud_patterns_json TEXT,
    hug_eligible        BOOLEAN,
    ai_opinion          TEXT,
    analyzed_at         TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auction_listings (
    auction_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    court_case_no       VARCHAR(50),
    property_type       VARCHAR(30),
    min_bid_krw         BIGINT,
    appraised_value_krw BIGINT,
    bid_ratio           NUMERIC(5,3),
    rights_analysis_json TEXT,
    liens_json          TEXT,
    recommendation      VARCHAR(30),
    analyzed_at         TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 11. AI 마케팅 (G86)
-- ================================================================
CREATE TABLE IF NOT EXISTS marketing_contents (
    content_id          VARCHAR(8) PRIMARY KEY,
    project_id          UUID NOT NULL,
    content_type        VARCHAR(20),
    target_audience     VARCHAR(50),
    content_text        TEXT,
    word_count          INTEGER,
    seo_keywords_json   TEXT,
    channels_json       TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_marketing_project ON marketing_contents(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS offering_memorandums (
    om_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL,
    content_text        TEXT,
    target_irr_pct      NUMERIC(6,2),
    version             INTEGER DEFAULT 1,
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 12. McKinsey 도메인 에이전트 (G87)
-- ================================================================
CREATE TABLE IF NOT EXISTS domain_agent_tasks (
    task_id             VARCHAR(8) PRIMARY KEY,
    domain              VARCHAR(20),
    trigger             TEXT,
    steps_json          TEXT,
    thoughts_json       TEXT,
    status              VARCHAR(30) DEFAULT 'pending',
    trace_json          TEXT,
    entity_id           VARCHAR(100),
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_agent_tasks_status ON domain_agent_tasks(status, created_at DESC);

CREATE TABLE IF NOT EXISTS domain_agent_approvals (
    approval_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id             VARCHAR(8) NOT NULL,
    thought_text        TEXT,
    approved_by         VARCHAR(100),
    decision            VARCHAR(20),
    notes               TEXT,
    decided_at          TIMESTAMP
);

-- ================================================================
-- 13. IoT 예측 유지보수 (G88)
-- ================================================================
CREATE TABLE IF NOT EXISTS equipment_sensors (
    sensor_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id        VARCHAR(50) NOT NULL,
    equipment_name      VARCHAR(100),
    equipment_type      VARCHAR(30),
    sensor_type         VARCHAR(30),
    value               NUMERIC(10,3),
    unit                VARCHAR(10),
    health_score        NUMERIC(5,1),
    rul_days            INTEGER,
    anomaly_level       VARCHAR(20) DEFAULT 'normal',
    read_at             TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_equipment_sensors_read_at
    ON equipment_sensors(equipment_id, read_at DESC);

CREATE TABLE IF NOT EXISTS predictive_maintenance_alerts (
    alert_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    equipment_id        VARCHAR(50),
    anomaly_level       VARCHAR(20),
    z_score             NUMERIC(6,2),
    confidence          NUMERIC(4,3),
    alert_json          TEXT,
    resolved            BOOLEAN DEFAULT false,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS work_orders (
    wo_id               VARCHAR(20) PRIMARY KEY,
    equipment_id        VARCHAR(50),
    building_id         UUID,
    title               VARCHAR(200),
    description         TEXT,
    priority            VARCHAR(20),
    estimated_hours     NUMERIC(6,1),
    estimated_cost_krw  INTEGER,
    assigned_contractor VARCHAR(100),
    status              VARCHAR(20) DEFAULT 'open',
    created_at          TIMESTAMP DEFAULT NOW(),
    completed_at        TIMESTAMP
);

-- ================================================================
-- 14. 임차인 경험 (G89)
-- ================================================================
CREATE TABLE IF NOT EXISTS tenant_tickets (
    ticket_id           VARCHAR(8) PRIMARY KEY,
    tenant_id           UUID NOT NULL,
    property_id         UUID NOT NULL,
    text                TEXT,
    category            VARCHAR(30),
    priority            VARCHAR(20),
    sentiment           VARCHAR(20),
    key_issue           VARCHAR(200),
    estimated_hours     INTEGER,
    escalation          BOOLEAN DEFAULT false,
    status              VARCHAR(20) DEFAULT 'open',
    resolved_at         TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_tenant_tickets_tid ON tenant_tickets(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS tenant_sentiment_scores (
    score_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    total_score         NUMERIC(5,1),
    satisfaction        VARCHAR(20),
    churn_risk          NUMERIC(4,3),
    breakdown_json      TEXT,
    scored_at           TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_financial_health (
    health_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID NOT NULL,
    payment_score       NUMERIC(5,1),
    delay_avg_days      NUMERIC(5,1),
    default_risk        NUMERIC(4,3),
    assessed_at         TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 15. 자산 인텔리전스 (G90)
-- ================================================================
CREATE TABLE IF NOT EXISTS asset_intelligence_snapshots (
    snapshot_id         VARCHAR(8) PRIMARY KEY,
    project_id          UUID NOT NULL,
    noi_monthly_krw     INTEGER,
    vacancy_pct         NUMERIC(5,1),
    energy_kwh_m2       NUMERIC(8,2),
    tenant_satisfaction NUMERIC(5,1),
    gresb_score         INTEGER,
    overall_health_score INTEGER,
    asset_value_krw     BIGINT,
    insights_json       TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_asset_snapshots_project
    ON asset_intelligence_snapshots(project_id, created_at DESC);

CREATE TABLE IF NOT EXISTS capex_optimization_results (
    result_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL,
    options_json        TEXT,
    best_option         VARCHAR(200),
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 16. AI 비용 제어 (G91)
-- ================================================================
CREATE TABLE IF NOT EXISTS ai_token_usage (
    usage_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name        VARCHAR(50),
    endpoint            VARCHAR(100),
    model               VARCHAR(50),
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    cache_read_tokens   INTEGER DEFAULT 0,
    cost_usd            NUMERIC(10,6),
    project_id          UUID,
    user_id             UUID,
    used_at             TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_ai_token_usage_date
    ON ai_token_usage(service_name, used_at DESC);
CREATE INDEX idx_ai_token_usage_month
    ON ai_token_usage(DATE_TRUNC('month', used_at));

CREATE TABLE IF NOT EXISTS ai_cost_budgets (
    budget_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    service_name        VARCHAR(50) NOT NULL,
    period              VARCHAR(10) NOT NULL,   -- 'daily'|'monthly'
    token_limit         INTEGER,
    cost_limit_usd      NUMERIC(10,2),
    alert_pct           INTEGER DEFAULT 80,
    active              BOOLEAN DEFAULT true,
    created_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (service_name, period)
);

-- ================================================================
-- 17. 포털 연동 (G92)
-- ================================================================
CREATE TABLE IF NOT EXISTS portal_listings (
    listing_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL,
    portal_name         VARCHAR(30),
    external_id         VARCHAR(100),
    status              VARCHAR(20) DEFAULT 'pending',
    listing_url         TEXT,
    posted_at           TIMESTAMP,
    updated_at          TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portal_performance (
    perf_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    listing_id          UUID NOT NULL,
    portal_name         VARCHAR(30),
    date_kst            DATE,
    views               INTEGER DEFAULT 0,
    inquiries           INTEGER DEFAULT 0,
    favorites           INTEGER DEFAULT 0,
    fetched_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (listing_id, date_kst)
);

-- ================================================================
-- 18. 다국어 보고서 (G93)
-- ================================================================
CREATE TABLE IF NOT EXISTS multilingual_reports (
    report_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL,
    source_type         VARCHAR(30),
    source_lang         VARCHAR(5) DEFAULT 'ko',
    target_lang         VARCHAR(5),
    translated_text     TEXT,
    currency_display    VARCHAR(10) DEFAULT 'KRW',
    created_at          TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 19. 에너지 인증 (G94+G95)
-- ================================================================
CREATE TABLE IF NOT EXISTS energy_certifications (
    cert_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID NOT NULL,
    cert_type           VARCHAR(20),
    status              VARCHAR(20) DEFAULT 'in_progress',
    score               INTEGER,
    grade               VARCHAR(10),
    cert_json           TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS kepco_rate_cache (
    rate_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    hour_kst            INTEGER,
    period_type         VARCHAR(10),
    rate_won_kwh        NUMERIC(8,2),
    date_kst            DATE,
    fetched_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE (date_kst, hour_kst)
);

-- ================================================================
-- 20. 운영/시스템
-- ================================================================
CREATE TABLE IF NOT EXISTS legal_audit_trail (
    trail_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID,
    user_id             UUID,
    action              VARCHAR(100),
    resource_type       VARCHAR(50),
    resource_id         VARCHAR(100),
    ip_address          INET,
    user_agent          TEXT,
    request_json        TEXT,
    response_status     INTEGER,
    created_at          TIMESTAMP DEFAULT NOW()
);
CREATE INDEX idx_audit_trail_tenant ON legal_audit_trail(tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS ai_usage_log (
    log_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID REFERENCES users(user_id),
    tenant_id           UUID,
    model               VARCHAR(50),
    feature             VARCHAR(50),
    input_tokens        INTEGER,
    output_tokens       INTEGER,
    latency_ms          INTEGER,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS model_performance (
    perf_id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_name          VARCHAR(100),
    model_version       VARCHAR(50),
    metric_name         VARCHAR(50),
    metric_value        NUMERIC(10,6),
    environment         VARCHAR(20),
    measured_at         TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID REFERENCES tenants(tenant_id),
    url                 TEXT NOT NULL,
    events              TEXT[],
    secret              VARCHAR(255),
    is_active           BOOLEAN DEFAULT true,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    delivery_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webhook_id          UUID REFERENCES webhooks(webhook_id),
    event_type          VARCHAR(50),
    payload_json        TEXT,
    response_status     INTEGER,
    attempt_count       INTEGER DEFAULT 0,
    delivered_at        TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_keys (
    key_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id           UUID REFERENCES tenants(tenant_id),
    key_hash            VARCHAR(255) NOT NULL,
    key_prefix          VARCHAR(8),
    name                VARCHAR(100),
    scopes              TEXT[],
    rate_limit_rpm      INTEGER DEFAULT 100,
    is_active           BOOLEAN DEFAULT true,
    last_used_at        TIMESTAMP,
    expires_at          TIMESTAMP,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS esign_requests (
    request_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          UUID REFERENCES projects(project_id),
    document_type       VARCHAR(50),
    signers_json        TEXT,
    status              VARCHAR(20) DEFAULT 'pending',
    provider            VARCHAR(20),
    provider_ref        VARCHAR(100),
    signed_url          TEXT,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contractors (
    contractor_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(100),
    specialties         TEXT[],
    phone               VARCHAR(20),
    rating              NUMERIC(3,1),
    is_available        BOOLEAN DEFAULT true,
    created_at          TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tenant_notifications (
    notif_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    building_id         UUID,
    message             TEXT,
    channel             VARCHAR(20),
    sent_at             TIMESTAMP DEFAULT NOW()
);

-- ================================================================
-- 인덱스 최적화 (성능)
-- ================================================================
CREATE INDEX IF NOT EXISTS idx_projects_status
    ON projects(tenant_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_regulation_project
    ON regulation_checks(project_id, checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_financial_project
    ON financial_analyses(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kyc_user
    ON kyc_documents(user_id, verification_status);
CREATE INDEX IF NOT EXISTS idx_portal_listings_project
    ON portal_listings(project_id, portal_name);

-- ================================================================
-- updated_at 자동 트리거
-- ================================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_tenants_updated BEFORE UPDATE ON tenants
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER trg_projects_updated BEFORE UPDATE ON projects
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ================================================================
-- 시드 데이터 (개발용)
-- ================================================================
INSERT INTO tenants (name, slug, plan) VALUES
    ('PropAI 데모 테넌트', 'demo', 'enterprise')
ON CONFLICT DO NOTHING;

INSERT INTO ai_cost_budgets (service_name, period, cost_limit_usd) VALUES
    ('marketing_ai_service',        'daily', 5.0),
    ('domain_agent_service',        'daily', 3.0),
    ('asset_intelligence_service',  'daily', 3.0),
    ('multilingual_report_service', 'daily', 5.0)
ON CONFLICT (service_name, period) DO NOTHING;

INSERT INTO contractors (name, specialties, phone, rating) VALUES
    ('한국전기', ARRAY['electrical', 'hvac'], '02-1234-5678', 4.8),
    ('서울설비', ARRAY['hvac', 'plumbing'],   '02-2345-6789', 4.5),
    ('메가건설', ARRAY['civil', 'structural'], '02-3456-7890', 4.7)
ON CONFLICT DO NOTHING;

SELECT 'PropAI v43.0 DB 초기화 완료 -- ' || COUNT(*) || '개 테이블' as result
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
