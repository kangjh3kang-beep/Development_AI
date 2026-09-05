#!/usr/bin/env bash
# 워크트리를 제거해도 안전한지 판정한다.
#
# ★왜 스크립트인가 — 이 판정은 산문으로 적으면 「원리적으로 만족 불가한 조건」이 된다.
#   2026-09-05 실측: 인계서가 정리 조건을 「고유 커밋 0」(= origin/main..HEAD 가 비었나)로 적었는데,
#   이 저장소는 **스쿼시 머지**라 머지된 브랜치도 그 범위가 영원히 비지 않는다
#   (#966 MERGED 인데 14건 · #975 MERGED 인데 2건). 그 조건을 읽은 사람은 둘 중 하나를 한다:
#   ①영영 못 지운다  ②조건을 무시하고 지운다 — ②가 유실 사고다.
#
# ★틀린 축 둘(같은 실측에서 걸렀다 — 다시 쓰지 마라):
#   ✘ git diff origin/main HEAD  … 판별력 0. 머지된 브랜치도 대량 deletions 를 낸다.
#                                   그건 「미머지」가 아니라 「main 보다 뒤처짐」을 재는 것이다.
#   ✘ tip != PR headRefOid       … 방향이 둘이다(뒤에 커밋이 있다 / 뒤처졌다). 한쪽만 읽으면 오보한다.
#
# ◎ 올바른 축 — 셋을 모두 만족해야 안전하다:
#   1) PR 이 MERGED (또는 --no-pr 로 PR 축을 면제하고 사유를 남긴다)
#   2) 로컬에만 있는 커밋 0  = git rev-list --count <비교대상>..HEAD
#      ★비교대상은 origin/main 이 아니라 **PR headRefOid**(없으면 origin/<브랜치>)다.
#   3) 작업트리가 깨끗 = git status --porcelain 이 비어 있음(미추적 포함)
#
# 사용: scripts/worktree_safe_to_remove.sh <워크트리경로> [--no-pr <사유>]
# 종료코드: 0=안전  1=제거 금지(유실 위험)  2=판정 불가(조회 실패 — 「안전」으로 읽지 마라)
set -uo pipefail

WT="${1:-}"
if [ -z "$WT" ]; then
  echo "사용법: $0 <워크트리경로> [--no-pr <사유>]" >&2
  exit 2
fi
NOPR=""
if [ "${2:-}" = "--no-pr" ]; then
  NOPR="${3:-}"
  [ -n "$NOPR" ] || { echo "★--no-pr 에는 사유가 필요하다(면제를 익명으로 남기지 않는다)." >&2; exit 2; }
fi

[ -d "$WT" ] || { echo "판정 불가: 경로가 없다 — $WT" >&2; exit 2; }
git -C "$WT" rev-parse --git-dir >/dev/null 2>&1 || { echo "판정 불가: git 워크트리가 아니다 — $WT" >&2; exit 2; }

BRANCH="$(git -C "$WT" branch --show-current)"
# ★빈 문자열 폴백은 값을 본다 — `|| echo` 는 detached 에서 exit 0 + 빈 출력이라 발동하지 않는다.
[ -n "$BRANCH" ] || BRANCH='(detached)'
LOCAL="$(git -C "$WT" rev-parse HEAD 2>/dev/null)"
[ -n "$LOCAL" ] || { echo "판정 불가: HEAD 를 못 읽는다" >&2; exit 2; }

echo "워크트리 : $WT"
echo "브랜치   : $BRANCH"
echo "로컬 tip : ${LOCAL:0:12}"

VERDICT_SAFE=1   # 0 이 되면 안전
FAIL=""

# --- 축1: PR 상태 ---
BASEREF=""
if [ -n "$NOPR" ]; then
  echo "축1 PR   : 면제 — 사유: $NOPR"
else
  if [ "$BRANCH" = "(detached)" ]; then
    echo "축1 PR   : ★판정 불가 — detached 라 브랜치로 PR 을 찾을 수 없다" >&2
    exit 2
  fi
  PRJSON="$(gh pr list --head "$BRANCH" --state all --json number,state,headRefOid --jq '.[0]' 2>/dev/null)"
  if [ -z "$PRJSON" ] || [ "$PRJSON" = "null" ]; then
    echo "축1 PR   : ★판정 불가 — 이 브랜치의 PR 을 못 찾았다(gh 인증/네트워크/브랜치명 확인)" >&2
    exit 2
  fi
  PRNUM="$(printf '%s' "$PRJSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["number"])')"
  PRSTATE="$(printf '%s' "$PRJSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["state"])')"
  BASEREF="$(printf '%s' "$PRJSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["headRefOid"])')"
  echo "축1 PR   : #$PRNUM $PRSTATE (headRefOid ${BASEREF:0:12})"
  if [ "$PRSTATE" != "MERGED" ]; then
    FAIL="${FAIL}
  · PR #$PRNUM 이 MERGED 가 아니다($PRSTATE) — 작업이 아직 반영되지 않았다"
  fi
fi

# --- 축2: 로컬에만 있는 커밋 ---
# 비교 대상: PR headRefOid → 없으면 origin/<브랜치> → 없으면 판정 불가
CMP="$BASEREF"
if [ -z "$CMP" ] || ! git -C "$WT" cat-file -e "$CMP" 2>/dev/null; then
  git -C "$WT" fetch -q origin 2>/dev/null || true
fi
if [ -z "$CMP" ] || ! git -C "$WT" cat-file -e "$CMP" 2>/dev/null; then
  if [ "$BRANCH" != "(detached)" ] && git -C "$WT" rev-parse --verify -q "origin/$BRANCH" >/dev/null 2>&1; then
    CMP="origin/$BRANCH"
  else
    echo "축2 커밋 : ★판정 불가 — 비교 대상(PR headRefOid·origin/$BRANCH) 을 못 찾았다" >&2
    exit 2
  fi
fi
AHEAD="$(git -C "$WT" rev-list --count "$CMP..HEAD" 2>/dev/null)"
BEHIND="$(git -C "$WT" rev-list --count "HEAD..$CMP" 2>/dev/null)"
if [ -z "$AHEAD" ] || [ -z "$BEHIND" ]; then
  echo "축2 커밋 : ★판정 불가 — rev-list 가 값을 안 냈다" >&2
  exit 2
fi
echo "축2 커밋 : 로컬 고유 $AHEAD · 뒤처짐 $BEHIND  (비교대상 $CMP)"
# ★방향을 가른다 — 뒤처짐은 유실 위험이 아니다. 로컬 고유만이 위험이다.
if [ "$AHEAD" != "0" ]; then
  FAIL="${FAIL}
  · 로컬에만 있는 커밋 $AHEAD 건 — 원격 어디에도 없다면 제거 시 영구 소실"
fi

# --- 축3: 작업트리 청결(미추적 포함) ---
DIRTY="$(git -C "$WT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
UNTRACKED="$(git -C "$WT" status --porcelain 2>/dev/null | grep -c '^??' || true)"
echo "축3 트리 : 변경 $DIRTY (미추적 $UNTRACKED)"
if [ "$DIRTY" != "0" ]; then
  FAIL="${FAIL}
  · 커밋되지 않은 변경 $DIRTY 건 — 제거하면 사라진다"
  git -C "$WT" status --porcelain 2>/dev/null | head -10 | sed 's/^/      /'
fi

echo
if [ -z "$FAIL" ]; then
  echo "::VERDICT=SAFE"
  echo "◎ 제거해도 안전하다. 다음을 실행:"
  echo "    git worktree remove '$WT'"
  exit 0
else
  echo "::VERDICT=UNSAFE"
  echo "✘ 제거 금지 — 이유:$FAIL"
  exit 1
fi
