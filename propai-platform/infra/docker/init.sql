-- PostGIS 확장 활성화 (공간 정보 처리)
CREATE EXTENSION IF NOT EXISTS postgis;

-- UUID 기본 생성 모듈
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 암호화 함수 지원 모듈
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- TimescaleDB가 연결될 경우를 대비한 하이퍼테이블 지원 구조 준비
-- 하이퍼테이블은 데이터베이스 스키마(단계 3)에서 Claude Code 에이전트가 상세 생성합니다.

-- RLS (Row Level Security) 기본 정책 설정 예시 
-- (테넌트 격리 기술: 모든 core 테이블에서 app.current_tenant 세팅 사용)
-- 실제 테이블 생성은 API 마이그레이션(Alembic)에서 수행되며, 권한 부여만 초기 설정

-- 설정: 인증된 사용자의 현재 접속 테넌트ID 변수 공간 확보
-- CREATE POLICY 보안 정책 예시:
-- CREATE POLICY tenant_isolation ON projects 
--   USING (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- Casbin 어댑터가 casbin_rule 테이블을 자동 생성할 수 있도록 스키마 권한 명시 부여
GRANT CREATE ON SCHEMA public TO propai;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO propai;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO propai;
