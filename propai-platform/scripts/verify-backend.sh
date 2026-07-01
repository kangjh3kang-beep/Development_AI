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
if [ "$PYMAJ" -lt 3 ] || { [ "$PYMAJ" -eq 3 ] && [ "$PYMIN" -lt 12 ]; }; then
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
trap 'rm -f "$COLLECT_LOG"' EXIT INT TERM
"$VPY" -m pytest tests/ --collect-only -q >"$COLLECT_LOG" 2>&1
COLLECTED="$(grep -oE '[0-9]+ tests? collected' "$COLLECT_LOG" | tail -1 || true)"
# 예외 유형 줄만 추출(SyntaxError 부수줄 'File...'/'^' 등 제외 → 카운트 정확).
# 분류 원칙:
#   · 자체 패키지(app./tests.) 미해결 import = '코드결함'(오타·삭제된 자체 모듈)으로 포함.
#   · 3자 패키지 미설치(No module named 'X', X는 app/tests 아님) = '환경 문제'로 제외.
#   · SyntaxError·기타 = 코드오류로 포함.
CODE_ERRORS=0
DEP_LINES=""
while IFS= read -r _line; do
  [ -z "$_line" ] && continue
  if printf '%s' "$_line" | grep -qE "No module named '(app|tests)[.']"; then
    CODE_ERRORS=$((CODE_ERRORS + 1))          # 자체 모듈 미해결 = 코드결함
  elif printf '%s' "$_line" | grep -qiE "No module named|ModuleNotFound"; then
    DEP_LINES="$DEP_LINES$_line"$'\n'         # 3자 미설치 = 환경(제외)
  else
    CODE_ERRORS=$((CODE_ERRORS + 1))          # SyntaxError·기타 코드오류
  fi
done < <(grep -E '^E +[A-Za-z_.]*(Error|Exception):' "$COLLECT_LOG")
# 미설치 의존성 종류(3자만, app/tests 제외).
DEP_MISSING="$(grep -oE "No module named '[^']+'" "$COLLECT_LOG" | grep -vE "'(app|tests)[.']" | sort -u | wc -l | tr -d ' ')"
echo "  수집: ${COLLECTED:-0}, 미설치 의존성 종류: ${DEP_MISSING}, 실코드오류: ${CODE_ERRORS}"
if [ "$DEP_MISSING" -gt 0 ]; then
  echo "  · 미설치 의존성(환경) — 게이트 실패 아님:"
  grep -oE "No module named '[^']+'" "$COLLECT_LOG" | sort -u | sed 's/^/    /'
fi
if [ "$CODE_ERRORS" -gt 0 ]; then
  echo "✗ 실제 코드오류(구문/자체모듈 import) ${CODE_ERRORS}건 — 게이트 실패:"
  # 자체 모듈(app/tests) 미해결 + 3자 아닌 예외줄만 표시.
  grep -E '^E +[A-Za-z_.]*(Error|Exception):' "$COLLECT_LOG" \
    | grep -E "No module named '(app|tests)[.']|^E +(Syntax|Indentation|Import|Name|Type|Attribute)" \
    | head -10 | sed 's/^/    /'
  exit 2
fi
echo "✓ 실코드오류 0 (3자 의존성 누락은 환경 문제로 별도 집계)"

echo "── [4/4] 핵심 도메인 테스트(법령·용도지역·조례·특이필지·evidence) ─"
# 무결성 핵심 경로만 빠르게 검증(전체 5000+ 는 CI 담당).
# (이 스크립트는 errexit 미사용 — set -uo pipefail — 이므로 RC 캡처에 set +e/-e 토글 불필요.)
RC=0
"$VPY" -m pytest tests/ \
  -k "legal or zone or ordinance or special_parcel or precheck or evidence or compliance or far_tier" \
  -q -p no:cacheprovider || RC=$?
if [ "$RC" -ne 0 ]; then
  echo "✗ 핵심 도메인 테스트 실패(RC=$RC) — 게이트 실패."
  exit 3
fi
echo ""
echo "✅ 백엔드 검증환경 게이트 통과: 파이썬 $PYVER · 수집 실코드오류 0 · 핵심 도메인 테스트 green"
exit 0
