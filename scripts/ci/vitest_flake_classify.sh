#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# vitest 실행 로그를 **FLAKE / REAL / UNKNOWN** 으로 가른다.
#
# 왜(전수 실측 2026-08-26 · 창 2026-08-12~08-26 14일):
#   `ci.yml` 런 **1,200건** 중 실패 135건. 그중 `Frontend (type-check + lint + test)` 가
#   빨간 런 **67건 전부**를 로그 원문으로 판정한 결과 —
#     FLAKE **39 (58%)** · REAL **13 (19%)** · UNKNOWN **15 (22%)**
#   FLAKE 는 전부 같은 얼굴이다: Test Files 전량 passed · Tests 전량 passed · **실패 0** ·
#   Errors 1 = `[vitest-worker]: Timeout calling "onTaskUpdate"` (실행 ~280초).
#
# ★★#842 초판은 여기에 *"진짜 결함을 잡은 적이 0회 · 100% 위양성"* 이라 적었다. **틀렸다.**
#   그때 표본은 **"최근 실패 런 7건"** 이라 두 겹으로 잘려 있었다 — ①"최근" 창
#   ②**"실패로 남은 런"**. ★**성공한 게이트는 자기 증거를 지운다**: 빨개져서 작성자가
#   푸시로 고치면 그 PR 은 **초록으로 머지**되고, *잡았기 때문에* 결함이 main 에 안 간다.
#   그건 원리적으로 그 표본에 안 들어온다. 전수로 재니 **14일간 진짜 실패 13건을 잡았다.**
#   (동료 세션이 반박했고 그 반박이 옳았다. 처방은 안 바뀐다 — 아래 ②가 그 13건을 지킨다.)
#
# ★UNKNOWN 15건의 정체: **vitest 요약이 나오기 전에** 죽은 것들이다(tsc·eslint 실패,
#   수집 실패, 크래시). 이 잡은 type-check → lint → test 순으로 도므로 앞 단계에서 죽으면
#   요약 자체가 없다. **그래서 UNKNOWN 은 재시도하지 않는다** — 재시도해도 같은 곳에서 죽는다.
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

# ② 어느 요약에든 **1 이상의** failed 가 있으면 진짜 실패다.
#  ★`[0-9]+ failed` 로 쓰면 `Tests 0 failed | 3091 passed`(= 실패 0건)를 REAL 로 읽는다.
#    선언한 의도는 **failed >= 1** 인데 구현이 "숫자 아무거나"였다 — 둘은 다른 술어다.
#    안전한 방향(재시도 안 함)이라 **위험하진 않지만 조용하다**: 그 형태가 나오는 순간
#    FLAKE 분기가 **영영 안 타면서 초록**이 된다(아무것도 안 하는 장치).
#    현재 vitest 는 0 을 생략하므로 미발현이나, **술어를 의도에 맞춘다**(동료 세션 지적).
if printf '%s\n%s\n' "$files_line" "$tests_line" | grep -qE '[1-9][0-9]* failed'; then
  echo "REAL"; exit 0
fi

# ③ 관측된 서명.
if printf '%s\n' "$plain" | grep -qF 'Timeout calling "onTaskUpdate"'; then
  echo "FLAKE"; exit 0
fi

# 전부 통과인데 서명도 없는데 실패했다면 원인이 다른 것이다 — 재시도 금지.
echo "UNKNOWN"
