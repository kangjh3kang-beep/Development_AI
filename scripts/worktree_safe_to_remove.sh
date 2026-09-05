#!/usr/bin/env bash
# 워크트리를 제거해도 **무언가를 잃는가**를 판정한다.
#
# ★질문을 바로 잡는 것이 이 도구의 핵심이다.
#   처음에는 「머지됐나」를 물었는데, 실제로 답해야 하는 것은 **「제거하면 잃는가」** 다.
#   `git worktree remove` 가 지우는 것은 ①워크트리 디렉토리의 파일 ②그 워크트리 전용 HEAD 다.
#   **`refs/heads/<브랜치>` 는 지우지 않는다** — 그래서 브랜치가 붙어 있으면 커밋은 살아남는다.
#
# ── 걸러 낸 틀린 축들 (전부 실측으로 죽였다 · 다시 쓰지 마라) ──────────────────
#  ✘ `origin/main..HEAD` 가 비었나        … 현재 기본이 스쿼시 머지라 머지돼도 안 빈다
#                                            (#966 MERGED 인데 14 · #975 MERGED 인데 2)
#  ✘ `git diff origin/main HEAD`          … 판별력 0. 워크트리 445개 전수: MERGED 429·OPEN 4·
#                                            CLOSED 12 전부 대량 deletions, deletions=0 은 **0개**
#  ✘ `tip != PR headRefOid`               … 방향이 둘(뒤에 커밋 / 뒤처짐)이라 한쪽만 읽으면 오보
#  ✘ `git cherry origin/main HEAD`        … ★**스쿼시를 견디지 못한다.** 2차 적대 리뷰 실측:
#       PR #966(MERGED) → '+' **13** · PR #975(MERGED) → '+' **2**.
#       patch-id 는 N개 커밋의 스쿼시 결과와 각 원본이 서로 다르다. 견디는 것은 커밋 1개짜리뿐.
#       이 축을 쓰면 원격에 멀쩡히 있는 워크트리 14개가 **영구 UNSAFE** 가 된다.
#
# ── ◎ 쓰는 축 ────────────────────────────────────────────────────────────────
#  축2 **도달성** — 제거해도 살아남는 ref(`refs/heads` + `refs/remotes`)에서 HEAD 에 닿는가.
#       스쿼시와 무관하고, 「무엇을 잃는가」를 직접 답한다.
#  축3 **파일**   — 제거하면 사라지는 파일이 있는가.
#       ★★`git status --porcelain` 은 **ignored 를 안 본다**. 그런데 remove 는 `--force` 없이도
#         그것을 지운다(실측: `.env` 넣고 remove → EXIT=0 · 소실). 전수 500 중 **422개가 그 사각지대**.
#         → `--ignored` 로 보되 **재생 가능/불가를 가른다**(전부 막으면 위양성이 결함 · §A-6).
#  축1 **PR**     — 작업이 main 에 반영됐나(정보 축). 도달성과 별개 질문이다.
#  축4 **잠금·메인** — git 이 거부할 대상에 제거를 권하지 않는다.
#
# ★fail-closed: 조회기가 죽으면 「안전」이 아니라 **판정 불가(exit 2)** 를 낸다.
#   조회의 rc 와 출력을 **분리해서** 읽는다 — `grep -c` 는 실패해도 0 을 찍으므로
#   그것만 보면 **죽은 조회기가 SAFE 로 읽힌다**(2차 리뷰가 변이로 실증한 결함).
#
# 사용: scripts/worktree_safe_to_remove.sh <워크트리경로> [--no-pr <사유>]
# 종료코드: 0=안전  1=제거 금지  2=판정 불가
# ★기계 판독은 stdout 의 `::VERDICT=` 줄로 (SAFE / UNSAFE / UNDECIDED).
set -uo pipefail

WT="${1:-}"; NOPR=""
FAIL=""

emit() { echo "::VERDICT=$1"; }
undecided() {
  # ★MINOR-1 봉합: 앞 축이 이미 확정한 위험을 버리지 않는다.
  #   종전에는 축3 이 .env 를 찾아 놓고 축1 에서 exit 2 로 나가 UNDECIDED 가 됐다.
  if [ -n "$FAIL" ]; then
    echo "✘ 판정 불가이지만 **이미 확정된 위험이 있다**:$FAIL" >&2
    emit UNSAFE; exit 1
  fi
  echo "$1" >&2; emit UNDECIDED; exit 2
}

if [ -z "$WT" ]; then
  echo "사용법: $0 <워크트리경로> [--no-pr <사유>]" >&2; emit UNDECIDED; exit 2
fi
if [ "${2:-}" = "--no-pr" ]; then
  NOPR="${3:-}"
  [ -n "$NOPR" ] || { echo "★--no-pr 에는 사유가 필요하다(면제를 익명으로 남기지 않는다)." >&2
                      emit UNDECIDED; exit 2; }
fi

[ -d "$WT" ] || undecided "판정 불가: 경로가 없다 — $WT"
git -C "$WT" rev-parse --git-dir >/dev/null 2>&1 || undecided "판정 불가: git 워크트리가 아니다 — $WT"

TOP="$(git -C "$WT" rev-parse --show-toplevel 2>/dev/null)"
if [ -n "$TOP" ] && [ "$(cd "$WT" && pwd -P)" != "$(cd "$TOP" && pwd -P)" ]; then
  undecided "판정 불가: 워크트리 루트가 아니라 하위 디렉토리다 — 루트는 $TOP"
fi

BRANCH="$(git -C "$WT" branch --show-current)"
# ★빈 문자열 폴백은 값을 본다 — `|| echo` 는 detached 에서 exit 0 이라 발동하지 않는다.
[ -n "$BRANCH" ] || BRANCH='(detached)'
LOCAL="$(git -C "$WT" rev-parse HEAD 2>/dev/null)" || undecided "판정 불가: HEAD 를 못 읽는다"
[ -n "$LOCAL" ] || undecided "판정 불가: HEAD 가 비었다"

echo "워크트리 : $WT"
echo "브랜치   : $BRANCH"
echo "로컬 tip : ${LOCAL:0:12}"

# ══════ 축3: 제거하면 사라지는 파일 ══════
# ★NIT-3 봉합: -z 로 받아 C-인용(`"…:Zone.Identifier"`)에 앵커가 안 먹는 문제를 없앤다.
# ★NUL 은 파일로 받는다 — bash 변수는 NUL 을 담지 못해 $( ) 가 구분자를 삼키고,
#   그러면 `read -d ''` 가 EOF 에서 실패해 **루프가 한 번도 안 돈다**(계약 락이 잡은 결함).
ST_F="$(mktemp)"; trap 'rm -f "$ST_F"' EXIT
if ! git -C "$WT" status --porcelain -z --ignored=matching >"$ST_F" 2>/dev/null; then
  undecided "축3 파일 : ★판정 불가 — git status 가 실패했다(인덱스 손상 등). 「안전」으로 읽지 마라"
fi
# ★MAJOR-3 봉합: 재생 가능 목록을 census 로 넓혔다. 종전에는 `next-env.d.ts` 하나가
#   워크트리 **79개**를 영구 차단해(막힌 108개 중 86개가 순수 재생물) 헤더가 경고한 그 위양성이 됐다.
#   ★그래도 이건 **목록**이고 목록은 곧 상한이다(§수집·판정 규율). 방향은 fail-closed 로 둔다 —
#     모르는 이름은 「재생 불가」로 분류해 **막는다**. 모르는 것을 통과시키면 그게 데이터 손실이다.
# ── 축3 분류 ────────────────────────────────────────────────────────────────
# ★★2026-09-05 3차 적대 리뷰가 **출하본 원본**에서 데이터 손실 경로를 찾았다.
#   종전 REGEN_RE 는 **경로의 어느 세그먼트든** 매치해서 `dist/`·`out/` **아래 전부**가
#   「재생 가능」을 상속했다. 실측: `dist/.env` → 재생불가 0 → SAFE → remove → **소실**.
#   ★게다가 git 은 `!! dist/` 로 **디렉토리를 접어** 보고하므로 안에 무엇이 있는지 **보이지도 않는다**.
#   헤더가 「모르면 막는다」고 적은 그 자리가 정확히 **모르면 통과**였다(§C-11 거짓 면역 주장).
#
# ◎ 세 갈래로 가른다 — 순서가 판정이다:
#   ① DEPS_RE  : 패키지·캐시 트리. **손으로 만들 수 없는 것만** 넣는다 → 통째로 재생 가능(안 들어간다)
#   ② SECRET_RE: 비밀류 basename → **DEPS 밖이면 무조건 보존**(deny-first). ①보다 뒤인 이유는
#                `.venv/**/cacert.pem` 같은 정당한 재생물까지 막으면 2차 MAJOR-3(위양성 86/108)이 되살아나기 때문.
#   ③ OUT_RE   : 빌드 산출 디렉토리. 사람이 뭘 넣었을 수 있으므로 **접힌 디렉토리는 들어가서** 본다.
#   ④ 그 외    : **보존**(fail-closed) — 이제 이 문장이 코드와 일치한다.
DEPS_RE='(^|/)(node_modules|__pycache__|\.venv|venv|site-packages|\.mypy_cache|\.pytest_cache|\.ruff_cache|\.turbo|\.next|\.gradle|target)(/|$)|\.egg-info(/|$)'
SECRET_RE='(^|/)(\.env($|\.)|id_(rsa|dsa|ecdsa|ed25519)($|\.)|.*\.(pem|key|p12|pfx|jks|keystore)$|.*credential.*|.*secret.*)'
OUT_RE='(^|/)(dist|build|out|coverage|htmlcov|test-results|playwright-report|\.open-next|\.vercel|\.wrangler)(/|$)'
MISC_REGEN_RE='(^|/)next-env\.d\.ts$|(^|/)\.DS_Store$|(^|/)\.coverage(\.|$)|:Zone\.Identifier$|\.tsbuildinfo$|\.pyc$|\.log$'

# 한 항목을 **보존해야 하는가**. ★쉘 관례대로 **참(0) = 보존**이다(함수 이름과 일치).
#   ★2026-09-05: 처음엔 반환값을 반대로 짜서 **다섯 모집단이 전부 뒤집혔다.**
#     한 모집단만 봤으면 «SAFE 가 나온다»로 넘어갔을 자리다 — 두 모집단 대조가 즉시 잡았다.
_keep_entry() {
  local e="$1" wt="$2"
  printf '%s' "$e" | grep -qE "$DEPS_RE" && return 1          # ① 통째로 재생물 → 보존 안 함
  printf '%s' "$e" | grep -qE "$SECRET_RE" && return 0        # ② deny-first → 보존
  if [ "${e%/}" != "$e" ]; then                               # ③ 접힌 디렉토리 → 들어가 본다
    local d="$wt/${e%/}" hit
    [ -d "$d" ] || return 0                                   # 못 보면 보존(fail-closed)
    # ★안에 비밀류가 하나라도 있으면 보존한다(전수 · head 로 자르지 않는다)
    hit=$(find "$d" -type f -print 2>/dev/null | grep -cE "$SECRET_RE" || true)
    [ "${hit:-0}" = "0" ] || return 0
    printf '%s' "$e" | grep -qE "$OUT_RE" && return 1         # 순수 빌드산출 → 보존 안 함
    return 0                                                   # 모르는 디렉토리 → 보존
  fi
  printf '%s' "$e" | grep -qE "$OUT_RE|$MISC_REGEN_RE" && return 1
  return 0                                                     # ④ 모르면 보존(fail-closed)
}
DIRTY=0; IGN_N=0; IGN_KEEP=""; IGN_KEEP_N=0
while IFS= read -r -d '' e; do
  [ -n "$e" ] || continue
  st="${e:0:2}"; p="${e:3}"
  if [ "$st" = "!!" ]; then
    IGN_N=$((IGN_N+1))
    if _keep_entry "$p" "$WT"; then
      IGN_KEEP="${IGN_KEEP}${p}
"; IGN_KEEP_N=$((IGN_KEEP_N+1))
    fi
  else
    DIRTY=$((DIRTY+1))
  fi
done < "$ST_F"
echo "축3 파일 : 추적변경 $DIRTY · 무시된항목 $IGN_N (재생불가 $IGN_KEEP_N)"
[ "$DIRTY" = "0" ] || { FAIL="${FAIL}
  · 커밋되지 않은 변경 $DIRTY 건 — 제거하면 사라진다"; }
if [ "$IGN_KEEP_N" != "0" ]; then
  FAIL="${FAIL}
  · ★무시된(ignored) 파일 중 재생 불가로 분류된 것 $IGN_KEEP_N 건 — remove 는 --force 없이도 지운다"
  printf '%s' "$IGN_KEEP" | head -10 | sed 's/^/      /'
fi

# ══════ 축2: 제거해도 살아남는 ref 에서 HEAD 에 도달 가능한가 ══════
# ★MAJOR-4 봉합: 종전 문구 「원격 어디에도 없다면 영구 소실」은 25건 중 **23건에서 거짓**이었다.
#   remove 는 refs/heads 를 안 지우므로 **브랜치가 붙어 있으면 커밋은 산다.**
if ! REACH="$(git -C "$WT" for-each-ref --contains "$LOCAL" --format='%(refname)' refs/heads refs/remotes 2>/dev/null)"; then
  undecided "축2 도달성: ★판정 불가 — for-each-ref 가 실패했다. 「안전」으로 읽지 마라"
fi
REACH_N=$(printf '%s' "$REACH" | grep -c . || true)
echo "축2 도달성: 살아남는 ref 중 HEAD 를 품은 것 $REACH_N 개$( [ "$REACH_N" != "0" ] && printf ' (%s…)' "$(printf '%s' "$REACH" | head -1)" )"
if [ "$REACH_N" = "0" ]; then
  FAIL="${FAIL}
  · ★HEAD(${LOCAL:0:12})를 품은 ref 가 하나도 없다 — 이 워크트리가 유일한 소유자다.
    제거하면 그 커밋들은 gc 대상이 되어 **영구 소실**된다(브랜치 미부착: $BRANCH)"
fi

# ★축4를 축1 **앞**에 둔다(3차 리뷰 MINOR-1).
#   종전에는 축1이 먼저 exit 2 로 나가면 「잠김·메인 워크트리」라는 **확정된 사실**이
#   계산조차 되지 않아 UNDECIDED 로 나갔다. 실측: 잠긴 워크트리 + gh 조회 실패 → UNDECIDED,
#   같은 대상에 --no-pr 만 주면 → UNSAFE(잠김 사유 출력). **같은 사실, 다른 판정**이었다.
#   ★MINOR-1 봉합을 undecided() 에만 하고 **형제 축까지 안 갔다** — §D-20 적용 범위 ≠ 결함 범위.
# ══════ 축4: git 이 거부할 대상인가 ══════
GD="$(git -C "$WT" rev-parse --git-dir 2>/dev/null)"
GCD="$(git -C "$WT" rev-parse --git-common-dir 2>/dev/null)"
# ★MINOR-2 봉합: 메인 워크트리는 remove 가 fatal 이다(축4 를 넣은 근거가 여기에도 그대로 적용된다).
if [ -n "$GD" ] && [ -n "$GCD" ] && [ "$(cd "$WT" && cd "$GD" 2>/dev/null && pwd -P)" = "$(cd "$WT" && cd "$GCD" 2>/dev/null && pwd -P)" ]; then
  FAIL="${FAIL}
  · ★메인 워크트리다 — git worktree remove 가 거부한다(fatal: is a main working tree)"
fi
LOCKF=""
case "$GD" in /*) LOCKF="$GD/locked" ;; *) LOCKF="$WT/$GD/locked" ;; esac
if [ -f "$LOCKF" ]; then
  FAIL="${FAIL}
  · ★이 워크트리는 잠겨 있다(git worktree lock) — 사유: $(head -c 200 "$LOCKF")"
fi

# ══════ 축1: PR 상태 (정보 축 — 도달성과 다른 질문) ══════
if [ -n "$NOPR" ]; then
  echo "축1 PR   : 면제 — 사유: $NOPR"
else
  if [ "$BRANCH" = "(detached)" ]; then
    undecided "축1 PR   : ★판정 불가 — detached 라 브랜치로 PR 을 찾을 수 없다. --no-pr <사유> 로 면제하라"
  fi
  # ★`.[0]` 은 미문서화 정렬이다. 브랜치명 재사용 실측 983 PR / 고유 967 · 한 이름 7회.
  if ! PRJSON="$(gh pr list --head "$BRANCH" --state all --json number,state,createdAt \
                 --jq 'sort_by(.createdAt)|last' 2>/dev/null)"; then
    undecided "축1 PR   : ★판정 불가 — gh 조회가 실패했다"
  fi
  if [ -z "$PRJSON" ] || [ "$PRJSON" = "null" ]; then
    undecided "축1 PR   : ★판정 불가 — 이 브랜치의 PR 을 못 찾았다. PR 없이 쓴 브랜치면 --no-pr <사유> 를 주어라"
  fi
  PRNUM="$(printf '%s' "$PRJSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["number"])')"
  PRSTATE="$(printf '%s' "$PRJSON" | python3 -c 'import json,sys;print(json.load(sys.stdin)["state"])')"
  echo "축1 PR   : #$PRNUM $PRSTATE"
  [ "$PRSTATE" = "MERGED" ] || FAIL="${FAIL}
  · PR #$PRNUM 이 MERGED 가 아니다($PRSTATE) — 작업이 아직 main 에 반영되지 않았다"
fi


echo
if [ -z "$FAIL" ]; then
  emit SAFE
  echo "◎ 제거해도 잃는 것이 없다. 다음을 실행:"
  printf "    git worktree remove %q\n" "$WT"   # ★NIT-4: 경로에 ' 가 있어도 안전
  exit 0
else
  emit UNSAFE
  echo "✘ 제거 금지 — 이유:$FAIL"
  exit 1
fi
