#!/usr/bin/env bash
# PropAI 전체 시스템 구동 검증 스크립트
# 실행: bash scripts/test/verify_system.sh
set -euo pipefail

PASS=0
FAIL=0
WARN=0
RESULTS=""

log_pass() { PASS=$((PASS+1)); RESULTS+="[PASS] $1\n"; echo "[PASS] $1"; }
log_fail() { FAIL=$((FAIL+1)); RESULTS+="[FAIL] $1\n"; echo "[FAIL] $1"; }
log_warn() { WARN=$((WARN+1)); RESULTS+="[WARN] $1\n"; echo "[WARN] $1"; }

echo "========================================="
echo " PropAI 시스템 검증 시작"
echo "========================================="
echo ""

# 0. Python + venv 확인
echo "--- Phase 0: 환경 검증 ---"
cd "$(dirname "$0")/../.."
# source .venv/bin/activate 2>/dev/null || true

PYTHON_BIN=""
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="$(command -v python3)"
fi

if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" --version 2>/dev/null; then
  log_pass "Python installed: $("$PYTHON_BIN" --version 2>&1)"
  echo "Python path: $PYTHON_BIN"
  "$PYTHON_BIN" -c "import sys; print(f'Executable: {sys.executable}')"
else
  log_fail "Python not found"
fi

# 1. FastAPI 앱 임포트 검증
echo ""
echo "--- Phase 1: FastAPI 앱 로딩 ---"
if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" -c "from apps.api.main import app; print('Routes:', len(app.routes))" 2>&1; then
  log_pass "FastAPI app imports successfully"
else
  log_fail "FastAPI app import failed"
  if [ -n "$PYTHON_BIN" ]; then
    echo "--- Debugging packages.schemas.models ---"
    "$PYTHON_BIN" -c "import packages.schemas.models as m; print('DigitalTwinStatusRequest in m:', 'DigitalTwinStatusRequest' in dir(m))" || true
  fi
fi

# 2. Config 로딩 검증
echo ""
echo "--- Phase 2: Config 로딩 ---"
if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" -c "from apps.api.config import get_settings; s=get_settings(); print('App:', s.app_name, s.app_version)" 2>&1; then
  log_pass "Config loads successfully"
else
  log_fail "Config load failed"
fi

# 3. DB 모델 임포트 검증
echo ""
echo "--- Phase 3: DB 모델 임포트 ---"
if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" -c "
from apps.api.database.models import *
import apps.api.database.models as m
attrs = [a for a in dir(m) if not a.startswith('_')]
print(f'Models/attrs loaded: {len(attrs)}')
" 2>&1; then
  log_pass "DB models import OK"
else
  log_fail "DB models import failed"
fi

# 4. 서비스 레이어 임포트 검증
echo ""
echo "--- Phase 4: 서비스 레이어 임포트 ---"
SERVICES=(
  "apps.api.services.avm_service"
  "apps.api.services.regulation_service"
  "apps.api.services.design_ai_service"
  "apps.api.services.tax_ai_service"
  "apps.api.services.construction_ai_service"
  "apps.api.services.jeonse_risk_service"
  "apps.api.services.blockchain_service"
  "apps.api.services.bim_ifc_service"
  "apps.api.services.digital_twin_service"
  "apps.api.services.kdx_integration_service"
  "apps.api.services.lcc_service"
  "apps.api.services.monte_carlo_service"
  "apps.api.services.eu_taxonomy_service"
  "apps.api.services.carbon_calculation_service"
  "apps.api.services.safety_service"
  "apps.api.services.webhook_service"
  "apps.api.services.chatbot_service"
  "apps.api.services.energy_service"
  "apps.api.services.marketing_service"
  "apps.api.services.domain_agents_service"
  "apps.api.services.floor_plan_image_service"
  "apps.api.services.re100_tracker_service"
  "apps.api.services.underwriting_service"
  "apps.api.services.development_method_service"
  "apps.api.services.digital_twin_status_service"
  "apps.api.services.risk_scoring_engine"
  "apps.api.services.seumter_permit_service"
  "apps.api.services.contract_generator"
)

for svc in "${SERVICES[@]}"; do
  if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" -c "import $svc" 2>/dev/null; then
    log_pass "Service import: $svc"
  else
    log_fail "Service import: $svc"
  fi
done

# 5. 외부 API 클라이언트 임포트 검증
echo ""
echo "--- Phase 5: 외부 API 클라이언트 ---"
CLIENTS=(
  "apps.api.integrations.base_client"
  "apps.api.integrations.vworld_client"
  "apps.api.integrations.molit_client"
  "apps.api.integrations.kma_client"
  "apps.api.integrations.seumter_client"
  "apps.api.integrations.ecos_client"
  "apps.api.integrations.kets_client"
  "apps.api.integrations.court_client"
)
for cli in "${CLIENTS[@]}"; do
  if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" -c "import $cli" 2>/dev/null; then
    log_pass "Client import: $cli"
  else
    log_fail "Client import: $cli"
  fi
done

# 6. Auth 모듈 검증
echo ""
echo "--- Phase 6: 인증/보안 모듈 ---"
AUTH_MODULES=(
  "apps.api.auth.jwt_handler"
  "apps.api.auth.kakao_handler"
  "apps.api.auth.rbac"
  "apps.api.security.encryption"
)
for mod in "${AUTH_MODULES[@]}"; do
  if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" -c "import $mod" 2>/dev/null; then
    log_pass "Auth module: $mod"
  else
    log_fail "Auth module: $mod"
  fi
done

# 7. Orchestrator 임포트 검증
echo ""
echo "--- Phase 7: AI 에이전트 오케스트레이터 ---"
if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" -c "from apps.api.agents.propai_orchestrator import PropAIOrchestrator; print('Orchestrator OK')" 2>/dev/null; then
  log_pass "PropAI Orchestrator import"
else
  log_fail "PropAI Orchestrator import"
fi

# 8. Worker 임포트 검증
echo ""
echo "--- Phase 8: Worker/arq ---"
# set -e로 인해 서브쉘 실패 시 스크립트가 종료되는 것을 방지하기 위해 || true 사용
WORKER_IMPORT=$("$PYTHON_BIN" -c "from apps.worker.main import WorkerSettings; print('arq WorkerSettings OK')" 2>&1) || WORKER_IMPORT="IMPORT_FAILED: $WORKER_IMPORT"

if [[ $WORKER_IMPORT == *"arq WorkerSettings OK"* ]]; then
  log_pass "arq worker import"
else
  log_fail "arq worker import"
  echo "Error details: $WORKER_IMPORT"
fi

# 9. pytest 실행 (unit tests)
echo ""
echo "--- Phase 9: Unit Tests ---"
if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" -m pytest tests/unit/ -x -q --tb=short --no-header 2>&1 | tail -20; then
  log_pass "Unit tests executed"
else
  log_warn "Some unit tests failed (see log above)"
fi

# 10. Frontend 빌드 검증
echo ""
echo "--- Phase 10: Frontend (Next.js) ---"
if [ -f "apps/web/package.json" ]; then
  log_pass "Frontend package.json exists"
  if [ -d "apps/web/node_modules" ]; then
    log_pass "Frontend node_modules installed"
  else
    log_warn "Frontend node_modules missing — run 'pnpm install'"
  fi
  if [ -d "apps/web/.next" ]; then
    log_pass "Frontend .next build cache exists"
  else
    log_warn "Frontend .next missing — not built yet"
  fi
else
  log_fail "Frontend package.json missing"
fi

# 10b. Frontend quality gates
echo ""
echo "--- Phase 10b: Frontend Quality Gates ---"
if [ -d "apps/web/node_modules" ] && command -v pnpm >/dev/null 2>&1; then
  if (cd apps/web && pnpm test:run >/tmp/propai-vitest.log 2>&1); then
    log_pass "Frontend vitest passed"
  else
    log_fail "Frontend vitest failed"
    tail -40 /tmp/propai-vitest.log || true
  fi

  if (cd apps/web && pnpm type-check >/tmp/propai-typecheck.log 2>&1); then
    log_pass "Frontend type-check passed"
  else
    log_fail "Frontend type-check failed"
    tail -40 /tmp/propai-typecheck.log || true
  fi

  if (cd apps/web && pnpm lint >/tmp/propai-lint.log 2>&1); then
    log_pass "Frontend lint passed"
  else
    log_fail "Frontend lint failed"
    tail -40 /tmp/propai-lint.log || true
  fi

  if (cd apps/web && pnpm e2e:run >/tmp/propai-e2e.log 2>&1); then
    log_pass "Frontend Playwright E2E passed"
  else
    log_fail "Frontend Playwright E2E failed"
    tail -60 /tmp/propai-e2e.log || true
  fi
else
  log_warn "Frontend quality gates skipped (pnpm or node_modules missing)"
fi

# 10c. Release automation 검증
echo ""
echo "--- Phase 10c: Release Automation ---"
if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" scripts/release/validate_release_env.py --help >/dev/null 2>&1; then
  log_pass "Release env validator CLI loads"
else
  log_fail "Release env validator CLI failed"
fi

if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" scripts/release/run_release_smoke.py --help >/dev/null 2>&1; then
  log_pass "Release smoke CLI loads"
else
  log_fail "Release smoke CLI failed"
fi

if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" scripts/release/run_observability_smoke.py --help >/dev/null 2>&1; then
  log_pass "Observability smoke CLI loads"
else
  log_fail "Observability smoke CLI failed"
fi

if [ -n "$PYTHON_BIN" ] && "$PYTHON_BIN" scripts/release/validate_release_assets.py >/tmp/propai-release-assets.log 2>&1; then
  log_pass "Release asset validation passed"
else
  log_fail "Release asset validation failed"
  tail -40 /tmp/propai-release-assets.log || true
fi

if grep -q "scripts/release/validate_release_env.py" .github/workflows/deploy-staging.yml \
  && grep -q "scripts/release/run_release_smoke.py" .github/workflows/deploy-staging.yml \
  && grep -q "scripts/release/validate_release_env.py" .github/workflows/deploy-prod.yml \
  && grep -q "scripts/release/run_release_smoke.py" .github/workflows/deploy-prod.yml; then
  log_pass "Release workflows reference preflight and smoke scripts"
else
  log_fail "Release workflows missing preflight/smoke script wiring"
fi

# 11. 인프라 파일 검증
echo ""
echo "--- Phase 11: Infrastructure ---"
FILES_INFRA=(
  "infra/docker-compose.yml"
  "infra/k8s/base"
  "infra/terraform"
  "infra/monitoring"
  "infra/airflow"
  ".env.example"
  ".github"
  "docker-compose.prod.yml"
)
for f in "${FILES_INFRA[@]}"; do
  if [ -e "$f" ]; then
    log_pass "Infra: $f exists"
  else
    log_fail "Infra: $f missing"
  fi
done

# 12. Alembic 마이그레이션 확인
echo ""
echo "--- Phase 12: Alembic Migrations ---"
MIG_COUNT=$(find apps/api/database/migrations/versions -name "*.py" 2>/dev/null | wc -l)
echo "Migration files found: $MIG_COUNT"
if [ "$MIG_COUNT" -ge 1 ]; then
  log_pass "Alembic migrations present ($MIG_COUNT files)"
else
  log_fail "No Alembic migration files found"
fi

# 결과 요약
echo ""
echo "========================================="
echo " 검증 결과 요약"
echo "========================================="
echo "PASS: $PASS"
echo "FAIL: $FAIL"
echo "WARN: $WARN"
echo "TOTAL: $((PASS + FAIL + WARN))"
echo ""

if [ $FAIL -eq 0 ]; then
  echo "✅ 전체 시스템 검증 통과"
else
  echo "❌ 일부 항목 실패 — 위 로그 확인 필요"
fi
