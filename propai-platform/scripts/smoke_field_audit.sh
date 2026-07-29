#!/usr/bin/env bash
# ============================================================================
# smoke_field_audit.sh — 배포후 자가검증(field_audit) 활성 라이브 스모크
#
# 용도: 배포 직후 프로덕션에서 field_audit 자가검증 레이어가 **등록·활성** 상태인지
#   즉시 확인한다. 배포된 백엔드의 comprehensive analyze() 출력에 result["field_audit"]가
#   무성(silent)으로 부착되지 않던 회귀(배포-stale·env-disabled·prod-import-error)를
#   관측전용 진단 엔드포인트로 assert해, 관측전용 레이어의 무성 회귀를 배포 게이트에서 차단.
#
#   분석을 실행하지 않는 introspect 전용 엔드포인트라 비용·부작용 0 — 반복 호출 안전.
#
# 입력(환경변수):
#   PROPAI_API_BASE   API 베이스 URL (기본 https://api.4t8t.net).
#                     서버에서 로컬 확인 시 예: PROPAI_API_BASE=http://localhost:8000
#   PROPAI_SMOKE_TIMEOUT  요청 최대 대기초 (기본 15 — introspect라 빠름).
#
# assert: enabled==true AND rules_registered>0. 실패 시 non-zero exit(배포 회귀).
#   ★rules_registered>0(하드 >=8 아님): 0 = 핵심 회귀 신호(등록 전무 = analyze 규칙 0으로
#   퇴화). 규칙 수는 W3-1/W4로 증가하므로 하드 >=8 게이트는 향후 오검출을 낸다. 부분손실
#   (8→1 등)은 all-or-nothing 임포트 등록이라 비현실적이나, 필요 시 named-count 게이트로 강화 가능.
# 파싱: jq 있으면 jq, 없으면 python3 (서버 호환).
# ============================================================================

set -u -o pipefail

API_BASE="${PROPAI_API_BASE:-https://api.4t8t.net}"
TIMEOUT="${PROPAI_SMOKE_TIMEOUT:-15}"
URL="${API_BASE%/}/api/v1/data-integrity/field-audit-status"

echo "[smoke] field_audit 활성 확인: $URL"

BODY="$(curl -fsS --max-time "$TIMEOUT" "$URL")" || {
  echo "FIELD_AUDIT SMOKE 실패 — 엔드포인트 응답 없음(HTTP 오류/타임아웃): $URL" >&2
  exit 1
}

if command -v jq >/dev/null 2>&1; then
  echo "$BODY" | jq -e '.enabled==true and .rules_registered>0' >/dev/null || {
    echo "FIELD_AUDIT INACTIVE — 배포 회귀(enabled!=true 또는 rules_registered==0)" >&2
    echo "응답: $BODY" >&2
    exit 1
  }
else
  echo "$BODY" | python3 -c '
import json,sys
d=json.load(sys.stdin)
ok = (d.get("enabled") is True) and isinstance(d.get("rules_registered"),int) and d["rules_registered"]>0
if not ok:
    sys.stderr.write("FIELD_AUDIT INACTIVE — 배포 회귀(enabled!=true 또는 rules_registered==0)\n")
    sys.stderr.write("응답: %s\n" % json.dumps(d, ensure_ascii=False))
    sys.exit(1)
' || exit 1
fi

echo "[smoke] PASS — field_audit 활성: $BODY"
