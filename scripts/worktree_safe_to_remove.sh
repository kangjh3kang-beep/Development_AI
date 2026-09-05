#!/usr/bin/env bash
# 워크트리를 제거해도 안전한지 판정한다.
#
# ★왜 스크립트인가 — 이 판정을 산문으로 적으면 「만족 불가한 조건」이 된다.
#   2026-09-05 실측: 인계서가 정리 조건을 「고유 커밋 0」(= origin/main..HEAD 가 비었나)으로 적었는데,
#   이 저장소는 **현재 기본이 스쿼시 머지**라 머지된 브랜치도 그 범위가 비지 않는다
#   (#966 MERGED 인데 14건 · #975 MERGED 인데 2건). 그 조건을 읽은 사람은 둘 중 하나를 한다:
#   ①영영 못 지운다  ②조건을 무시하고 지운다 — ②가 유실 사고다.
#   ★단정 주의: 「영원히」는 **거짓**이다. main 이력에 부모 2개인 진짜 머지커밋이 224개 있고
#     (예: PR #255) 그 브랜치 tip 은 origin/main 의 조상이라 범위가 **빈다**.
#     현재 기본값이 스쿼시일 뿐이므로, 커밋 범위로 판정하는 축은 **그 조건에서만** 틀린다.
#
# ★틀린 축 둘(2026-09-05 실측으로 걸렀다 — 다시 쓰지 마라):
#   ✘ git diff origin/main HEAD  … 판별력 0. 적대 리뷰가 워크트리 445개 전수로 재확인했다:
#       MERGED 429개 · OPEN 4 · CLOSED 12 전부 대량 deletions, deletions=0 인 것은 **0개**.
#       그건 「미머지」가 아니라 「main 보다 뒤처짐」을 재는 것이다.
#   ✘ tip != PR headRefOid  … 방향이 둘이다(뒤에 커밋이 있다 / 뒤처졌다). 한쪽만 읽으면 오보한다.
#
# ◎ 축 셋을 모두 만족해야 안전하다:
#   1) PR 이 MERGED — 또는 --no-pr 로 면제하고 사유를 남긴다
#   2) 로컬에만 있는 커밋 0
#      · PR 이 있으면 rev-list <PR headRefOid>..HEAD
#      · PR 이 없으면 **git cherry origin/main HEAD** (patch-id 기반이라 스쿼시에 견딘다)
#   3) 제거하면 사라지는 파일이 없다
#      ★★ git status --porcelain 은 **ignored 를 안 본다**. 그런데 `git worktree remove` 는
#         --force 없이도 그것들을 지운다(실측: .env 를 넣고 remove → EXIT=0 · 파일 소실).
#         전수 실측 500 워크트리 중 **422개가 porcelain=0 인데 ignored>0** 이었다.
#         → --ignored=matching 으로 보고, **재생 가능한 것과 아닌 것을 가른다**
#           (전부 UNSAFE 로 하면 422개가 다 막혀 위양성이 결함이 된다).
#
# 사용: scripts/worktree_safe_to_remove.sh <워크트리경로> [--no-pr <사유>]
# 종료코드: 0=안전  1=제거 금지(유실 위험)  2=판정 불가(조회 실패 — 「안전」으로 읽지 마라)
# ★판정은 stdout 의 ::VERDICT= 줄로 읽어라(SAFE / UNSAFE / UNDECIDED). 안내문에는 안 쓰인다.
set -uo pipefail

WT="${1:-}"
if [ -z "$WT" ]; then
  echo "사용법: $0 <워크트리경로> [--no-pr <사유>]" >&2
  echo "::VERDICT=UNDECIDED"; exit 2
fi
NOPR=""
if [ "${2:-}" = "--no-pr" ]; then
  NOPR="${3:-}"
  [ -n "$NOPR" ] || { echo "★--no-pr 에는 사유가 필요하다(면제를 익명으로 남기지 않는다)." >&2
                      echo "::VERDICT=UNDECIDED"; exit 2; }
fi

undecided() { echo "$1" >&2; echo "::VERDICT=UNDECIDED"; exit 2; }

[ -d "$WT" ] || undecided "판정 불가: 경로가 없다 — $WT"
git -C "$WT" rev-parse --git-dir >/dev/null 2>&1 || undecided "판정 불가: git 워크트리가 아니다 — $WT"

# ★NIT 봉합: 하위 디렉토리를 주면 rev-parse 는 성공하지만 worktree remove 는 실패한다.
TOP="$(git -C "$WT" rev-parse --show-toplevel 2>/dev/null)"
if [ -n "$TOP" ] && [ "$(cd "$WT" && pwd -P)" != "$(cd "$TOP" && pwd -P)" ]; then
  undecided "판정 불가: 워크트리 루트가 아니라 하위 디렉토리다 — 루트는 $TOP"
fi

BRANCH="$(git -C "$WT" branch --show-current)"
# ★빈 문자열 폴백은 값을 본다 — `|| echo` 는 detached 에서 exit 0 이라 발동하지 않는다.
[ -n "$BRANCH" ] || BRANCH='(detached)'
LOCAL="$(git -C "$WT" rev-parse HEAD 2>/dev/null)"
[ -n "$LOCAL" ] || undecided "판정 불가: HEAD 를 못 읽는다"

echo "워크트리 : $WT"
echo "브랜치   : $BRANCH"
echo "로컬 tip : ${LOCAL:0:12}"

FAIL=""

# ============ 축3 을 먼저 잰다 ============
# ★MINOR 봉합: 축1이 먼저 exit 2 로 나가면 detached 워크트리는 미커밋 변경이 있어도
#   그 사실을 못 듣는다. 진단 정보를 죽이지 않도록 파일 축을 앞에 둔다.
DIRTY="$(git -C "$WT" status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
# ★재생 가능한 것과 아닌 것을 가른다 — 전자까지 막으면 위양성이 결함이 된다(§A-6).
REGEN_RE='(^|/)(node_modules|__pycache__|\.venv|venv|\.ruff_cache|\.pytest_cache|\.mypy_cache|\.next|\.turbo|dist|build|coverage|\.gradle|target)(/|$)|\.tsbuildinfo$|\.pyc$|\.log$'
IGN_ALL="$(git -C "$WT" status --porcelain --ignored=matching 2>/dev/null | grep '^!! ' | sed 's/^!! //')"
IGN_N=$(printf '%s' "$IGN_ALL" | grep -c . || true)
IGN_KEEP="$(printf '%s\n' "$IGN_ALL" | grep -vE "$REGEN_RE" | grep . || true)"
IGN_KEEP_N=$(printf '%s' "$IGN_KEEP" | grep -c . || true)
echo "축3 파일 : 추적변경 $DIRTY · 무시된항목 $IGN_N (재생불가 $IGN_KEEP_N)"
if [ "$DIRTY" != "0" ]; then
  FAIL="${FAIL}
  · 커밋되지 않은 변경 $DIRTY 건 — 제거하면 사라진다"
  git -C "$WT" status --porcelain 2>/dev/null | head -10 | sed 's/^/      /'
fi
if [ "${IGN_KEEP_N:-0}" != "0" ]; then
  FAIL="${FAIL}
  · ★무시된(ignored) 파일 중 **재생 불가**한 것 $IGN_KEEP_N 건 — git worktree remove 는
    --force 없이도 이것들을 지운다(실측 확인). .env 류는 재생성 불가일 수 있다"
  printf '%s\n' "$IGN_KEEP" | head -10 | sed 's/^/      /'
fi

# ============ 축1: PR 상태 ============
BASEREF=""
if [ -n "$NOPR" ]; then
  echo "축1 PR   : 면제 — 사유: $NOPR"
else
  if [ "$BRANCH" = "(detached)" ]; then
    undecided "축1 PR   : ★판정 불가 — detached 라 브랜치로 PR 을 찾을 수 없다. --no-pr <사유> 로 면제하라"
  fi
  # ★MINOR 봉합: `.[0]` 은 문서화되지 않은 정렬이다. 브랜치명 재사용이 실재하므로
  #   (실측 983 PR / 고유 브랜치 967 · 한 이름이 7회 재사용) createdAt 으로 명시적으로 최신을 고른다.
  PRJSON="$(gh pr list --head "$BRANCH" --state all --json number,state,headRefOid,createdAt \
            --jq 'sort_by(.createdAt)|last' 2>/dev/null)"
  if [ -z "$PRJSON" ] || [ "$PRJSON" = "null" ]; then
    undecided "축1 PR   : ★판정 불가 — 이 브랜치의 PR 을 못 찾았다. PR 없이 쓴 브랜치라면 --no-pr <사유> 를 주어라"
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

# ============ 축2: 로컬에만 있는 커밋 ============
# ★MAJOR-2 봉합: 종전에는 PR headRefOid 가 없으면 origin/<브랜치> 로만 폴백했는데,
#   PR 이 없는 브랜치는 대개 원격 브랜치도 없다(실측: PR 없는 워크트리 28개 중 18개).
#   그래서 --no-pr 탈출구가 정확히 필요한 자리에서 죽어 「영영 못 지운다」를 재생산했다.
#   → git cherry(patch-id) 로 「내용이 origin/main 에 도달했나」를 잰다. 스쿼시에 견딘다.
CMP="$BASEREF"
if [ -n "$CMP" ] && ! git -C "$WT" cat-file -e "$CMP" 2>/dev/null; then
  # ★MINOR: fetch 는 원격추적 ref 를 갱신한다(읽기 전용이 아니다). 정말 필요할 때만 부른다.
  echo "축2 커밋 : (비교 대상 ${CMP:0:12} 미보유 — fetch 한다 · 원격추적 ref 가 갱신된다)"
  git -C "$WT" fetch -q origin 2>/dev/null || true
fi

AHEAD=""; BEHIND=""; MODE=""
if [ -n "$CMP" ] && git -C "$WT" cat-file -e "$CMP" 2>/dev/null; then
  MODE="PR headRefOid"
  AHEAD="$(git -C "$WT" rev-list --count "$CMP..HEAD" 2>/dev/null)"
  BEHIND="$(git -C "$WT" rev-list --count "HEAD..$CMP" 2>/dev/null)"
elif [ "$BRANCH" != "(detached)" ] && git -C "$WT" rev-parse --verify -q "origin/$BRANCH" >/dev/null 2>&1; then
  MODE="origin/$BRANCH"
  AHEAD="$(git -C "$WT" rev-list --count "origin/$BRANCH..HEAD" 2>/dev/null)"
  BEHIND="$(git -C "$WT" rev-list --count "HEAD..origin/$BRANCH" 2>/dev/null)"
elif git -C "$WT" rev-parse --verify -q origin/main >/dev/null 2>&1; then
  # ★patch-id 폴백 — 스쿼시로 들어간 커밋은 '-' 로 표시되어 제외된다
  MODE="git cherry origin/main (patch-id · 스쿼시 내성)"
  AHEAD="$(git -C "$WT" cherry origin/main HEAD 2>/dev/null | grep -c '^+' || true)"
  BEHIND="?"
else
  undecided "축2 커밋 : ★판정 불가 — 비교 대상이 없다(PR headRefOid · origin/$BRANCH · origin/main 전부 부재)"
fi
[ -n "$AHEAD" ] || undecided "축2 커밋 : ★판정 불가 — 계수가 값을 안 냈다"
echo "축2 커밋 : 로컬 고유 $AHEAD · 뒤처짐 $BEHIND  (기준 $MODE)"
# ★방향을 가른다 — 뒤처짐은 유실 위험이 아니다. 로컬 고유만이 위험이다.
if [ "$AHEAD" != "0" ]; then
  FAIL="${FAIL}
  · 로컬에만 있는 커밋 $AHEAD 건 — 원격 어디에도 없다면 제거 시 영구 소실"
fi

# ============ 축4: 잠금 ============
# ★MINOR 봉합: 잠긴 워크트리를 SAFE 로 찍으면 실패할 명령을 권하게 된다(git 이 막아 유실은 없다).
if git -C "$WT" rev-parse --git-dir 2>/dev/null | grep -q 'worktrees/'; then
  GD="$(git -C "$WT" rev-parse --git-dir)"
  if [ -f "$GD/locked" ]; then
    FAIL="${FAIL}
  · ★이 워크트리는 잠겨 있다(git worktree lock) — 사유: $(head -c 200 "$GD/locked")"
  fi
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
