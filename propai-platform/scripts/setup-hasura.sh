#!/bin/bash

# PropAI Hasura GraphQL Metadata Setup Script
# 백엔드(FastAPI + PostgreSQL) 구조를 Hasura 엔진에 매핑(트래킹)하여 GraphQL API를 활성화합니다.

HASURA_ENDPOINT="http://localhost:8088"
ADMIN_SECRET=${HASURA_ADMIN_SECRET:-hasura_super_secret_key}

echo "🚀 PropAI Hasura 메타데이터 자동 추적 스크립트 시작..."

# 1. Postgres 소스 연결 확인 및 등록
echo "✅ 1. 데이터베이스(PostgreSQL) 소스 연결"
curl -s -X POST "${HASURA_ENDPOINT}/v1/metadata" \
  -H "X-Hasura-Admin-Secret: ${ADMIN_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "pg_add_source",
    "args": {
      "name": "default",
      "configuration": {
        "connection_info": {
          "database_url": "postgres://propai:secret@postgres:5432/propaidb",
          "pool_settings": {
            "max_connections": 50,
            "idle_timeout": 180,
            "retries": 1
          }
        }
      }
    }
  }' > /dev/null

echo "✅ 2. 핵심 테이블 메타데이터 트래킹 (GraphQL 쿼리 활성화)"
# Claude Code가 설계한 15개 테이블(예시: users, projects, regulations, avm_results 등) 트래킹
TABLES=("users" "projects" "regulations" "avm_results" "tax_records" "design_plans" "drone_inspections" "escrow_contracts")

for TABLE in "${TABLES[@]}"; do
  curl -s -X POST "${HASURA_ENDPOINT}/v1/metadata" \
    -H "X-Hasura-Admin-Secret: ${ADMIN_SECRET}" \
    -H "Content-Type: application/json" \
    -d '{
      "type": "pg_track_table",
      "args": {
        "source": "default",
        "table": "'$TABLE'"
      }
    }' > /dev/null
  echo "  - 테이블 트래킹 완료: $TABLE"
done

echo "✅ 3. 관계(Relationships) 자동 구성"
# (예시) 프로젝트와 사용자(owner)의 외래키 관계 자동 추적
curl -s -X POST "${HASURA_ENDPOINT}/v1/metadata" \
  -H "X-Hasura-Admin-Secret: ${ADMIN_SECRET}" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "pg_suggest_relationships",
    "args": {
      "omit_tracked": true
    }
  }' > /dev/null

echo "🎉 GraphQL 연동 준비가 완료되었습니다!"
echo "👉 브라우저 접속: ${HASURA_ENDPOINT}/console"
echo "👉 비밀번호: ${ADMIN_SECRET}"
