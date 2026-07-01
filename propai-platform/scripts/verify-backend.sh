#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# verify-backend.sh — 백엔드 검증환경 게이트 (감사 재발 방지)
#
# 왜 필요한가(근본원인):
#   apps/api 코드는 pyproject `requires-python = ">=3.12"`이며 파이썬 3.12 전용
#   기능(`datetime.UTC`, `enum.StrEnum`)을 쓴다. 3.11 이하로 pytest 를 돌리면
#   `ImportError: cannot import name 'UTC'` 등으로 "테스트 수집 실패"가 나는데,
#   이는 코드 결함이 아니라 '잘못된 파이썬 버전'이라는 환경 문제다. 과거 감사가
#   3.10 으로 돌려 "검증환경 실패"로 오진한 사례가 있었다. 이 스크립트는
#   ① 파이썬 3.12 를 강제하고 ② 의존성을 설치하며 ③ '의존성 누락'과 '실제
#   코드오류'를 구분해 수집오류를 판정하고 ④ 핵심 도메인 테스트를 실행한다.
#
# 사용법:
#   scripts/verify-backend.sh            # 전체 게이트(설치+수집검증+핵심테스트)
#   PY=python3.12 scripts/verify-backend.sh
#   SKIP_INSTALL=1 scripts/verify-backend.sh   # venv 재사용(설치 생략)
#
# 종료코드: 0=통과 / 1=파이썬버전 미달 / 2=수집 실코드오류 / 3=핵심테스트 실패
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

# 저장소 루트 기준 apps/api 로 이동(스크립트 위치 무관 실행).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "$SCRIPT_DIR/.." && pwd)/apps/api"
cd "$API_DIR" || { echo "✗ apps/api 디렉토리를 찾지 못함: $API_DIR"; exit 1; }

PY="${PY:-python3.12}"
VENV_DIR="${VENV_DIR:-$API_DIR/.venv-verify}"

echo "── [1/4] 파이썬 3.12+ 강제 검사 ─────────────────────────────"
# requires-python>=3.12. 미만이면 datetime.UTC/StrEnum ImportError 로 수집이
# 무조건 실패하므로, '코드오류'로 오인하기 전에 여기서 명확히 차단한다.
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "✗ '$PY' 실행 파일이 없습니다. 코드는 파이썬 >=3.12 필요(pyproject requires-python)."
  echo "  설치 후 재실행하거나 PY=<파이썬3.12경로> 로 지정하세요."
  exit 1
fi
PYVER="$("$PY" -c 'import sys; print("%d.%d"%sys.version_info[:2])')"
PYMAJ="${PYVER%%.*}"; PYMIN="${PYVER##*.}"
if [ "$PYMAJ" -ne 3 ] || [ "$PYMIN" -lt 12 ]; then
  echo "✗ 파이썬 $PYVER 감지 — 코드는 3.12+ 필요."
  echo "  3.11 이하에서는 datetime.UTC/enum.StrEnum ImportError 로 '수집 실패'가 나며,"
  echo "  이는 코드 결함이 아니라 파이썬 버전 문제입니다(감사 오진 방지)."
  exit 1
fi
echo "✓ 파이썬 $PYVER (>=3.12)"

echo "── [2/4] venv + 의존성 설치 ─────────────────────────────────"
if [ -z "${SKIP_INSTALL:-}" ]; then
  [ -d "$VENV_DIR" ] || "$PY" -m venv "$VENV_DIR"
  # shellcheck disable=SC1091
  "$VENV_DIR/bin/pip" install -q --upgrade pip >/dev/null 2>&1
  if [ -f requirements.txt ]; then
    echo "  requirements.txt 설치 중(수 분 소요 가능)..."
    "$VENV_DIR/bin/pip" install -q -r requirements.txt 2>&1 | tail -3 || {
      echo "✗ 의존성 설치 실패 — requirements.txt 확인 필요."; exit 1; }
  fi
  echo "✓ 의존성 설치 완료"
else
  echo "· SKIP_INSTALL=1 — 기존 venv 재사용"
fi
VPY="$VENV_DIR/bin/python"

# 테스트에 필요한 최소 환경변수(미설정 시 config 가 임시키 자동생성하나 경고 억제).
export JWT_SECRET_KEY="${JWT_SECRET_KEY:-verify-gate-key}"
export APP_SECRET_KEY="${APP_SECRET_KEY:-verify-gate-key}"
export PYTHONPATH="${PYTHONPATH:-.}"

echo "── [3/4] 수집 검증(의존성누락 vs 실코드오류 구분) ───────────"
# 전체 수집을 돌려 '실제 코드오류(구문/import 오류)'가 0인지 본다.
# 의존성 누락(ModuleNotFoundby: No module named 'X')은 환경 문제로 별도 집계하고
# 코드오류(SyntaxError, 코드 자체의 ImportError 등)만 게이트 실패로 취급한다.
COLLECT_LOG="$(mktemp)"
"$VPY" -m pytest tests/ --collect-only -q >"$COLLECT_LOG" 2>&1
COLLECTED="$(grep -oE '[0-9]+ tests collected' "$COLLECT_LOG" | tail -1 || true)"
# 코드오류 = 'E ' 로 시작하는 에러줄 중 'No module named' 가 아닌 것.
CODE_ERRORS="$(grep -E '^E ' "$COLLECT_LOG" | grep -viE "No module named|ModuleNotFound" | grep -viE "^E +$" | wc -l | tr -d ' ')"
DEP_MISSING="$(grep -oE "No module named '[^']+'" "$COLLECT_LOG" | sort -u | wc -l | tr -d ' ')"
echo "  수집: ${COLLECTED:-0}, 미설치 의존성 종류: ${DEP_MISSING}, 실코드오류: ${CODE_ERRORS}"
if [ "$DEP_MISSING" -gt 0 ]; then
  echo "  · 미설치 의존성(환경) — 게이트 실패 아님:"
  grep -oE "No module named '[^']+'" "$COLLECT_LOG" | sort -u | sed 's/^/    /'
fi
if [ "$CODE_ERRORS" -gt 0 ]; then
  echo "✗ 실제 코드오류(구문/코드 import) ${CODE_ERRORS}건 — 게이트 실패:"
  grep -E '^E ' "$COLLECT_LOG" | grep -viE "No module named|ModuleNotFound" | head -10 | sed 's/^/    /'
  rm -f "$COLLECT_LOG"
  exit 2
fi
echo "✓ 실코드오류 0 (의존성 누락은 환경 문제로 별도 집계)"
rm -f "$COLLECT_LOG"

echo "── [4/4] 핵심 도메인 테스트(법령·용도지역·조례·특이필지·evidence) ─"
# 무결성 핵심 경로만 빠르게 검증(전체 5000+ 는 CI 담당).
set +e
"$VPY" -m pytest tests/ \
  -k "legal or zone or ordinance or special_parcel or precheck or evidence or compliance or far_tier" \
  -q -p no:cacheprovider
RC=$?
set -e 2>/dev/null || true
if [ "$RC" -ne 0 ]; then
  echo "✗ 핵심 도메인 테스트 실패(RC=$RC) — 게이트 실패."
  exit 3
fi
echo ""
echo "✅ 백엔드 검증환경 게이트 통과: 파이썬 $PYVER · 수집 실코드오류 0 · 핵심 도메인 테스트 green"
exit 0
