-- F-Parcel 대량 다필지 배치 — 테이블 생성 마이그레이션
-- 적용하지 말 것(통합자가 적용). PostGIS 미사용 — geometry 는 GeoJSON 을 JSONB 로 저장.
-- 멱등: IF NOT EXISTS 로 재실행 안전.

-- gen_random_uuid() 사용을 위해 pgcrypto 확장 보장(이미 있으면 무시).
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- 1) 배치 잡 헤더
CREATE TABLE IF NOT EXISTS parcel_batch_job (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    snapshot_id     VARCHAR(64)  NOT NULL,
    idempotency_key VARCHAR(64)  UNIQUE,
    state           VARCHAR(20)  NOT NULL DEFAULT 'queued',
    region_input    JSONB        DEFAULT '{}'::jsonb,
    completeness    VARCHAR(20)  NOT NULL DEFAULT 'partial',
    counts          JSONB        DEFAULT '{}'::jsonb,
    org_id          VARCHAR(64),
    project_id      VARCHAR(64),
    created_at      TIMESTAMP    DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_parcel_batch_job_idem
    ON parcel_batch_job (idempotency_key);

-- 2) 필지별 결과
CREATE TABLE IF NOT EXISTS batch_item_result (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id     UUID NOT NULL REFERENCES parcel_batch_job(id),
    pnu        VARCHAR(32) NOT NULL,
    status     VARCHAR(20) NOT NULL,
    record_ref JSONB,
    reason     VARCHAR(500)
);

CREATE INDEX IF NOT EXISTS ix_batch_item_result_job
    ON batch_item_result (job_id);

-- 3) 집계(geometry 는 GeoJSON JSONB)
CREATE TABLE IF NOT EXISTS batch_aggregate (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id             UUID NOT NULL REFERENCES parcel_batch_job(id),
    union_boundary     JSONB,
    total_area_sqm     DOUBLE PRECISION,
    jurisdiction_flags JSONB,
    held               BOOLEAN DEFAULT TRUE
);

CREATE INDEX IF NOT EXISTS ix_batch_aggregate_job
    ON batch_aggregate (job_id);