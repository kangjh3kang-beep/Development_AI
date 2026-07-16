#!/usr/bin/env bash
# ============================================================================
# smoke-far-parity.sh — 배포후 실효 용적률 교차표면 라이브 스모크 (WP-U5)
#
# 용도: 배포 직후 프로덕션에서 실효FAR 버그클래스(구조상한 누락·날조 기본값 —
#   PR#333/#334/#336/#337 봉합)의 재발 여부를 실제 API 응답으로 확인한다.
#   CI 계약 테스트(tests/test_far_cross_surface_parity.py)의 라이브 상대역.
#
# ★★비용 주의: 규제분석·인허가분석 체크는 refresh:true로 저장본(캐시)을 우회해
#   '실분석'(외부 공공데이터 수집 + 연산)을 실제로 발생시킨다. 배포 검증 시에만
#   실행하고 반복 호출하지 말 것. (use_llm:false라 LLM 토큰 비용은 없음)
#
# 입력(환경변수 — ★자격증명 하드코딩 절대 금지):
#   PROPAI_API_BASE        API 베이스 URL (기본 https://api.4t8t.net)
#   PROPAI_SMOKE_EMAIL     스모크 계정 이메일 (미설정 시 인증 필요 표면은 SKIP)
#   PROPAI_SMOKE_PASSWORD  스모크 계정 비밀번호 (미설정 시 인증 필요 표면은 SKIP)
#   PROPAI_SMOKE_GREEN_ADDR 자연녹지 검증 주소
#                          (기본: 경기도 용인시 수지구 신봉동 56-16 —
#                           PR#333 라이브 그라운드트루스 자연녹지지역, 실효 80%)
#   PROPAI_SMOKE_TIMEOUT   요청당 최대 대기초 (기본 300 — refresh 실분석은 느림)
#
# 체크(각 결과 PASS/FAIL/SKIP 표 출력, FAIL 1개라도 있으면 exit 1):
#   [1] GET  /health                          → HTTP 200
#   [2] POST /api/v1/regulation/analyze       → limits.far.effective == 80  (인증 불필요)
#   [3] POST /api/v1/permits/ai-analysis      → site.max_far == 80 + far_basis 존재
#                                               (토큰 필요 — 자격증명 미설정 시 SKIP)
#
# 파싱: jq 없이 python3만 사용(서버 호환).
# ============================================================================

set -u -o pipefail

API_BASE="${PROPAI_API_BASE:-https://api.4t8t.net}"
GREEN_ADDR="${PROPAI_SMOKE_GREEN_ADDR:-경기도 용인시 수지구 신봉동 56-16}"
TIMEOUT="${PROPAI_SMOKE_TIMEOUT:-300}"
SMOKE_EMAIL="${PROPAI_SMOKE_EMAIL:-}"
SMOKE_PASSWORD="${PROPAI_SMOKE_PASSWORD:-}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

# 결과 누적 (name|status|detail)
RESULTS=()
HAS_FAIL=0

record() { # name status detail
  RESULTS+=("$1|$2|$3")
  [ "$2" = "FAIL" ] && HAS_FAIL=1
  return 0
}

# JSON 파일에서 점표기 경로 값 추출(없으면 빈 문자열) — jq 대체(python3).
json_get() { # file dotted.path
  python3 - "$1" "$2" <<'PY'
import json, sys
try:
    with open(sys.argv[1], encoding="utf-8") as f:
        obj = json.load(f)
    for key in sys.argv[2].split("."):
        if isinstance(obj, list):
            obj = obj[int(key)]
        elif isinstance(obj, dict):
            obj = obj.get(key)
        else:
            obj = None
        if obj is None:
            break
    print("" if obj is None else obj)
except Exception:
    print("")
PY
}

# 숫자 동등 비교(80 == 80.0 처리) — python3.
num_eq() { # a b
  python3 -c 'import sys
try:
    sys.exit(0 if abs(float(sys.argv[1]) - float(sys.argv[2])) < 1e-6 else 1)
except Exception:
    sys.exit(1)' "$1" "$2"
}

http() { # method url outfile [json_body] [bearer_token] → echo status code
  local method="$1" url="$2" out="$3" body="${4:-}" token="${5:-}"
  local args=(-sS -X "$method" -o "$out" -w '%{http_code}' --max-time "$TIMEOUT"
              -H 'Content-Type: application/json')
  [ -n "$token" ] && args+=(-H "Authorization: Bearer $token")
  [ -n "$body" ] && args+=(-d "$body")
  # 연결 실패 시에도 curl -w가 이미 000을 출력하므로 별도 폴백을 덧붙이지 않는다
  # (이중 000 방지). 출력이 비면 000으로 정규화하고 마지막 3자리만 취한다.
  local code
  code="$(curl "${args[@]}" "$url" 2>/dev/null)" || true
  [ -z "$code" ] && code="000"
  echo "${code: -3}"
}

echo "== PropAI 실효FAR 교차표면 라이브 스모크 =="
echo "   API_BASE=$API_BASE"
echo "   자연녹지 주소=$GREEN_ADDR"
echo ""

# ── [1] /health ─────────────────────────────────────────────────────────────
echo "[1/3] GET /health ..."
ST="$(http GET "$API_BASE/health" "$WORKDIR/health.json")"
if [ "$ST" = "200" ]; then
  record "health" "PASS" "HTTP 200"
else
  record "health" "FAIL" "HTTP $ST (기대 200)"
fi

# ── [2] 규제분석 — 자연녹지 실효 용적률 80% (인증 불필요) ────────────────────
echo "[2/3] POST /api/v1/regulation/analyze (refresh:true — ★실분석 비용 발생) ..."
REG_BODY="$(python3 -c 'import json,sys; print(json.dumps({"address": sys.argv[1], "refresh": True, "use_llm": False}, ensure_ascii=False))' "$GREEN_ADDR")"
ST="$(http POST "$API_BASE/api/v1/regulation/analyze" "$WORKDIR/reg.json" "$REG_BODY")"
if [ "$ST" = "200" ]; then
  EFF="$(json_get "$WORKDIR/reg.json" "limits.far.effective")"
  if [ -n "$EFF" ] && num_eq "$EFF" "80"; then
    record "regulation.limits.far.effective" "PASS" "effective=$EFF (구조상한 80%)"
  else
    record "regulation.limits.far.effective" "FAIL" "effective='$EFF' (기대 80 — 구조상한 누락/과대표시 의심)"
  fi
else
  record "regulation.limits.far.effective" "FAIL" "HTTP $ST (기대 200)"
fi

# ── [3] 인허가분석 — site.max_far 80% + far_basis 존재 (인증 필요) ───────────
echo "[3/3] POST /api/v1/permits/ai-analysis (인증 필요) ..."
if [ -z "$SMOKE_EMAIL" ] || [ -z "$SMOKE_PASSWORD" ]; then
  record "permits.site.max_far" "SKIP" "PROPAI_SMOKE_EMAIL/PASSWORD 미설정 — 인증 필요 표면 미검증(정직 표기)"
else
  LOGIN_BODY="$(python3 -c 'import json,sys; print(json.dumps({"email": sys.argv[1], "password": sys.argv[2]}))' "$SMOKE_EMAIL" "$SMOKE_PASSWORD")"
  ST="$(http POST "$API_BASE/api/v1/auth/login" "$WORKDIR/login.json" "$LOGIN_BODY")"
  TOKEN=""
  [ "$ST" = "200" ] && TOKEN="$(json_get "$WORKDIR/login.json" "access_token")"
  if [ -z "$TOKEN" ]; then
    record "permits.site.max_far" "FAIL" "로그인 실패 HTTP $ST — 토큰 미발급(스모크 계정 확인 필요)"
  else
    PERMIT_BODY="$(python3 -c 'import json,sys; print(json.dumps({"address": sys.argv[1], "refresh": True, "use_llm": False}, ensure_ascii=False))' "$GREEN_ADDR")"
    ST="$(http POST "$API_BASE/api/v1/permits/ai-analysis" "$WORKDIR/permit.json" "$PERMIT_BODY" "$TOKEN")"
    if [ "$ST" = "200" ]; then
      MAX_FAR="$(json_get "$WORKDIR/permit.json" "site.max_far")"
      FAR_BASIS="$(json_get "$WORKDIR/permit.json" "site.far_basis")"
      if [ -n "$MAX_FAR" ] && num_eq "$MAX_FAR" "80" && [ -n "$FAR_BASIS" ]; then
        record "permits.site.max_far" "PASS" "max_far=$MAX_FAR, far_basis='$FAR_BASIS'"
      else
        record "permits.site.max_far" "FAIL" "max_far='$MAX_FAR' far_basis='$FAR_BASIS' (기대 80 + 근거 존재)"
      fi
    elif [ "$ST" = "403" ]; then
      record "permits.site.max_far" "FAIL" "HTTP 403 — 스모크 계정에 permits:read 권한 없음"
    else
      record "permits.site.max_far" "FAIL" "HTTP $ST (기대 200)"
    fi
  fi
fi

# ── 결과 표 ──────────────────────────────────────────────────────────────────
echo ""
echo "== 결과 =="
printf '%-36s %-6s %s\n' "CHECK" "STATUS" "DETAIL"
printf '%-36s %-6s %s\n' "-----" "------" "------"
for row in "${RESULTS[@]}"; do
  IFS='|' read -r name status detail <<<"$row"
  printf '%-36s %-6s %s\n' "$name" "$status" "$detail"
done
echo ""

if [ "$HAS_FAIL" -eq 1 ]; then
  echo "결과: FAIL — 실효FAR 교차표면 스모크 실패(위 표 참조). 배포 롤백/원인조사 필요."
  exit 1
fi
echo "결과: OK — FAIL 0건 (SKIP은 미검증 표면이므로 별도 확인 권장)."
exit 0
