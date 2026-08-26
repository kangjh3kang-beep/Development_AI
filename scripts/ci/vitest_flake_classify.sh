#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# vitest 실행 로그를 **FLAKE / REAL / UNKNOWN** 으로 가른다.
#
# 왜(실측 2026-08-26): 최근 `ci.yml` 실패 7건 중 **6건이 Frontend (type-check + lint + test)**
#   이었고, 그 6건을 **원문으로 전부 열어** 보니 완전히 동일했다 —
#     Test Files  전량 passed · Tests  전량 passed · **실패 0** ·
#     Errors 1 = `[vitest-worker]: Timeout calling "onTaskUpdate"`
#   즉 이 **필수 게이트가 최근 진짜 결함을 잡은 적이 0회**이고 100% 위양성이었다.
#   (run 32916207501 · 32916195162 · 32915342730 · 32913111495 · 32799830343 · 32808868737.
#    나머지 1건 32799088932 는 Backend 잡이라 별건.)
#
# ★위험은 재실행 비용이 아니라 **반사**다. *"또 그 플레이크겠지"* 로 재실행하는 습관이 생기면
#   **진짜 실패도 같은 반사에 묻힌다.** 그래서 게이트를 약화시키지 않고 **서명이 일치할 때만**
#   재시도한다 — 판정을 사람의 눈이 아니라 이 파일에 둔다.
#
# ★미측정: **왜** RPC 가 타임아웃되는지는 재지 않았다. vitest 3.2.4 는 이 타임아웃을
#   설정으로 노출하지 않는다. 이 스크립트는 **게이트 신뢰도 회복**이 목적이고 근본은 별건이다.
#
# 판정 규칙 — 셋을 **모두** 만족해야 FLAKE 다. 하나라도 어긋나면 재시도하지 않는다.
#   ① 요약이 **존재**한다 (`Test Files …` · `Tests …` 두 줄).
#      ★없으면 수집 실패·크래시일 수 있다 — 그건 재시도 대상이 아니라 **진짜 문제**다.
#   ② 요약에 **failed 가 0** 이다(두 줄 모두).
#   ③ `Timeout calling "onTaskUpdate"` 가 있다.
#  ★②가 핵심이다 — **진짜 실패와 이 타임아웃이 같은 실행에 함께** 나올 수 있고,
#    그때 재시도하면 진짜 결함을 묻는다. 그래서 ③만 보고 판정하지 않는다.
#
# 사용: vitest_flake_classify.sh <로그파일>   → stdout 에 FLAKE|REAL|UNKNOWN, exit 0
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

LOG="${1:?사용법: vitest_flake_classify.sh <로그파일>}"
[ -r "$LOG" ] || { echo "UNKNOWN"; exit 0; }

# ANSI 색·타임스탬프를 벗긴다(GitHub Actions 로그는 둘 다 붙는다).
plain=$(sed -e 's/\x1b\[[0-9;]*m//g' -e 's/^[0-9][0-9-]*T[0-9:.]*Z //' "$LOG")

files_line=$(printf '%s\n' "$plain" | grep -E '^[[:space:]]*Test Files[[:space:]]' | tail -1)
tests_line=$(printf '%s\n' "$plain" | grep -E '^[[:space:]]*Tests[[:space:]]'      | tail -1)

# ① 요약 부재 → 재시도하지 않는다(수집 실패·크래시일 수 있다).
if [ -z "$files_line" ] || [ -z "$tests_line" ]; then
  echo "UNKNOWN"; exit 0
fi

# ② 어느 요약에든 failed 가 있으면 **진짜 실패**다.
if printf '%s\n%s\n' "$files_line" "$tests_line" | grep -qE '[0-9]+ failed'; then
  echo "REAL"; exit 0
fi

# ③ 관측된 서명.
if printf '%s\n' "$plain" | grep -qF 'Timeout calling "onTaskUpdate"'; then
  echo "FLAKE"; exit 0
fi

# 전부 통과인데 서명도 없는데 실패했다면 원인이 다른 것이다 — 재시도 금지.
echo "UNKNOWN"
