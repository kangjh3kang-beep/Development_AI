#!/usr/bin/env bash
# 멀티세션 협업 헬퍼 — 공유 보드(브랜치 무관) 조회/클레임/해제/노트.
# 정책: coordination/PROTOCOL.md · WORKTREES.md. 보드: <repo>/.git/coordination/BOARD.md (git-common-dir·저장소 스코프)
# 사용: scripts/coord.sh {status | summary | claim <영역> | release <영역> | note <내용>}
set -euo pipefail

# 보드는 우리 저장소의 공유 git 디렉토리(git-common-dir) 안에 둔다 — 모든 워크트리가 공유하면서
# 정확히 이 저장소에만 스코프되고, git이 추적하지 않아(브랜치무관·머지충돌 0) 라이브 상태에 적합.
# ★★`COORD_DIR` 이 **설정됐는데 비어 있으면 거부**한다.
#   `${COORD_DIR:-…}` 의 `:-` 는 **빈 값을 미설정으로** 보아 파생 경로(=**실 공유 보드**)로 떨어진다.
#   `COORD_DIR=$OOPS_UNSET` 같은 흔한 오타가 «격리된 임시 보드에 쓰고 있다» 는 착각과 함께
#   **실 보드에 조용히 append** 된다 — 2026-09-04 적대 리뷰의 프로브가 정확히 그렇게 해서
#   공유 보드에 30줄을 오염시켰고, 그 세션은 권한 때문에 **스스로 지우지도 못했다.**
#   ★「격리하려는 의도」와 「실 보드에 쓰기」가 **같은 모양**이 되는 것이 이 결함의 핵심이다.
if [ -n "${COORD_DIR+x}" ] && [ -z "$COORD_DIR" ]; then
  echo "★COORD_DIR 이 설정됐는데 비어 있다 — 실 공유 보드로 조용히 떨어지는 것을 막는다(판정 거부)" >&2
  exit 2
fi
BOARD_DIR="${COORD_DIR:-$(cd "$(git rev-parse --git-common-dir)" && pwd)/coordination}"
BOARD="$BOARD_DIR/BOARD.md"
# ★`||` 는 **종료코드에만** 반응한다 — `git branch --show-current` 는 **detached HEAD 에서
#   exit 0 + 빈 출력**이라 그 폴백이 **발동하지 않았다**. 그러면 보드 줄의 브랜치 칸이
#   통째로 비어 **필드가 하나 밀린다**(파서가 다음 칸을 브랜치로 읽는다).
#   ★실해 범위: 이 저장소의 워크트리 32개가 detached 다(서브에이전트 워크트리 포함) —
#   거기서 쓴 노트는 전부 그 상태였다. **빈 출력도 실패로 다뤄야 한다.**
BRANCH="$(git branch --show-current 2>/dev/null)"
[ -n "$BRANCH" ] || BRANCH='?'   # detached·비저장소 둘 다 여기로 온다

# `summary` 에 실을 최근 건수.
# ★검증한다 — 비수치를 그냥 통과시키면 `tail -n abc` 가 실패하고 폴백이 그것을 **「(없음)」으로
#   뭉갠다**. 보드에 노트가 수천 건 있는데 「없음」이 나오는 것이 가장 나쁜 실패다(§26 위음성).
SUMMARY_N="${COORD_SUMMARY_N:-12}"
# ★**나쁜 것을 열거하지 않고 좋은 「모양」만 받는다.** 열거형이던 첫 판은 `00`·`000` 이 새어
#   `tail -n 0` 이 파이프를 닫아 **rc=141 · stdout·stderr 둘 다 빈** 무성 사망을 냈다(실측).
#   "목록은 곧 상한이 된다" — 모르는 표기는 자동으로 거부되는 쪽이 옳다.
case "$SUMMARY_N" in
  [1-9]|[1-9][0-9]|[1-9][0-9][0-9]) ;;
  *) echo "★COORD_SUMMARY_N 이 1~999 의 정수가 아니다: '$SUMMARY_N' — 판정 거부" >&2; exit 2 ;;
esac

stamp() { date '+%Y-%m-%d %H:%M'; }

# ★**세션 정체를 기계로 기록한다** — 보드의 `[8f]`·`[3a]` 표기와 본문 서명은 **전부 자기신고**다.
#
#   2026-09-04 실해: 한 세션의 이름으로 서명된 노트를 **그 세션이 쓰지 않았고**, 통합자가
#   그 조건을 근거로 남의 PR 을 태우기 직전이었다. 그 앞에는 오귀속이 2회 더 있었다.
#   ★「절대형 서명」은 오늘 소유자 확정에 유일하게 작동한 장치였는데,
#   **그 서명 자체가 오기입되면 그 장치도 무력하다.**
#
#   ★이 필드는 **스탬프가 찍는다** — 본문에 무엇을 쓰든 바뀌지 않으므로 **위조할 수 없다.**
#   자기신고(본문 서명)와 기계기록(이 필드)을 **같은 줄에서 대조**할 수 있게 하는 것이 목적이다.
#
#   ★값이 없으면 `?` 다 — **지어내지 않는다**(비대화형·SDK 실행에서 비어 있을 수 있다).
#   ★이 값은 `ListAgents` 의 `[5b83da]` 류와 **다른 식별자**다. 대응표를 만들 수단이 없으므로
#     **대응을 시도하지 않는다** — 「값이 다르면 다른 세션」만 말한다. 그것만으로 위 사고는 잡힌다.
sid() {
  local raw="${CLAUDE_CODE_SESSION_ID:-}"
  if [ -z "$raw" ]; then printf '?'; else printf '%.8s' "$raw"; fi
}

# ── 보드 생성 ──
# ★`summary`/`status` 가 보드를 만들면, `COORD_DIR` 이 틀렸을 때 **빈 유령 보드를 만들어 놓고
#   자신 있게 "(없음)" 을 보고**한다 — 조회가 대상을 못 찾은 것을 "0건"으로 읽는 그 실패다.
# ★생성은 **쓰는 명령(claim/release/note)** 만 한다. 조회는 `require_board` 로 거부한다.
#   ★첫 봉합에서 나는 «COORD_DIR 을 명시했으면 거부» 로 갈랐는데, 그러면 **writer 도 막혀**
#     새 보드를 아예 만들 수 없었다(내 왕복 테스트가 그 회귀를 첫 실행에서 잡았다).
#     축은 «명시했나» 가 아니라 **«읽으러 왔나 쓰러 왔나»** 다.
ensure_board() {
  mkdir -p "$BOARD_DIR"
  [ -f "$BOARD" ] && return 0
  {
    echo "# 멀티세션 협업 보드 (공유 · 브랜치 무관)"
    echo
    echo "> 규약: <worktree>/coordination/PROTOCOL.md. 세션 시작 시 읽고, 공유영역 편집 전 claim."
    echo
    echo "## 자동 로그 (coord.sh — claim/release/note, 최신이 아래)"
  } > "$BOARD"
  # ★생성이 **성공한 뒤에** 알린다. 첫 판은 이 줄이 `> "$BOARD"` **앞**에 있어, BOARD 가
  #   디렉토리·끊긴 심링크일 때 «만들었다» 를 찍고 rc=1 로 죽었다(적대 리뷰 실측).
  # ★writer 는 보드를 만들 수 있어야 하므로(reader 는 `require_board` 가 거부) **이 경고가
  #   writer 쪽 유령 보드의 유일한 방어**다. 그래서 두 모집단으로 잠갔다
  #   (`test_new_board_creation_is_announced_but_append_is_quiet`).
  echo "★보드를 **새로 만들었다**: $BOARD (이 실행 이전 기록은 없다)" >&2
}

require_board() {
  [ -f "$BOARD" ] || { echo "★보드가 없다: $BOARD — 조회 대상 부재를 「0건」으로 읽지 않는다(판정 거부)" >&2; exit 3; }
  [ -r "$BOARD" ] || { echo "★보드를 읽을 수 없다: $BOARD — 판정 거부" >&2; exit 3; }
}

# ── 조회기 사망과 진짜 0건을 **가른다** ──
# ★이 저장소는 정확히 이 결함 때문에 `tests/_scan_guard.py` 를 만들었고 `ScannerDeadError` 를
#   `AssertionError` 와 **다른 예외로** 던진다("뭉치면 「검사기가 죽었다」가 「깨끗하다」로 읽힌다").
#   그 규율을 이 스크립트도 지킨다: grep rc 1 = 진짜 0건 · rc>1 = 사망(시끄럽게 죽는다).
board_grep() {  # $1=ERE  → 번호 붙은 매칭 줄을 stdout 으로
  local out rc
  out="$(grep -nE "$1" "$BOARD")" && rc=0 || rc=$?
  if [ "$rc" -gt 1 ]; then
    # ★이 분기는 **도달 가능하다.** 첫 판 주석은 *"읽는 도중 I/O 오류뿐이라 재현 수단이 없다"* 고
    #   적었는데 **거짓이었다** — 적대 리뷰가 `PATH` 앞에 `exit 2` 짜리 `grep` 스텁을 놓아 3줄로
    #   재현했다. 그래서 산문이 아니라 **락으로** 잠갔다(`test_dead_scanner_branch_is_reachable`).
    #   ★교훈: *"재현할 수 없다"* 도 측정 대상이다. 못 한다고 적으면 아무도 다시 재지 않는다.
    echo "★조회기 사망(grep rc=$rc) — 「0건」과 구분한다. 결과를 신뢰하지 마라." >&2
    exit 3
  fi
  [ -n "$out" ] || { echo "(없음 — 조회기는 생존했고 실제로 0건이다)"; return 0; }
  printf '%s\n' "$out"
}

# ── 문자 단위 절단(+ 표식) ──
# ★`cut -c` 를 쓰지 않는다. GNU coreutils 의 `cut -c` 는 **바이트 기반**이라 한글을 문자 중간에서
#   잘라 **깨진 UTF-8** 을 뱉는다(실측: 240바이트 절단 시 라이브 보드 NOTE 1,780건 중 1,369건이
#   잘리고 그중 **533건이 파손**). 이 스크립트가 새로 보이게 만든 바로 그 노트가 깨지는 셈이다.
#   `awk substr` 도 구현에 따라 바이트 기반이라 같은 함정이다. → python3 으로 문자 단위로 자른다.
# ★python3 이 없으면 **자르지 않는다** — 자르다 깨뜨리느니 길게 두는 편이 낫다(fail-safe).
truncate_chars() {
  local lim="$1"
  if command -v python3 >/dev/null 2>&1; then
    python3 -c '
import sys
lim = int(sys.argv[1])
for ln in sys.stdin:
    ln = ln.rstrip("\n")
    sys.stdout.write(ln if len(ln) <= lim else ln[:lim] + " …[잘림]")
    sys.stdout.write("\n")
' "$lim"
  else
    cat
  fi
}

# ── 계산된 요약 절 — ★보드 전문을 뱉지 않는다 ──
# ★왜 전문을 안 뱉나: 보드 **본문이 절 제목을 그대로 인용**하고 있다. 그래서 하류에서
#   `sed -n '/<제목>/,$p'` 로 절을 자르면 **첫 발생**에서 잘려 엉뚱한 구간을 읽는다 — 동료 세션이
#   실제로 그 때문에 노트 건수를 틀리게 읽었다. `summary` 는 본문을 출력하지 않으므로 그 충돌이
#   **구조적으로** 일어날 수 없다.
# ★수치를 여기 박지 않는다(휘발성이다). 재측정:
#     grep -cE '^- \[NOTE\]' "$BOARD" ; grep -cE '^- \[(CLAIM|RELEASE)\]' "$BOARD"
#     grep -c '미해제 CLAIM' "$BOARD"          # 본문이 절 제목을 인용하는 횟수
print_summary() {
  echo "=== CLAIM/RELEASE 로그 — 최근 ${SUMMARY_N}건 (시간순 · 최신이 아래) ==="
  # ★제목에 「미해제」라고 쓰지 않는다 — 이 절은 **짝짓기를 하지 않는다.**
  #   짝짓기를 여기서 되살리지 마라: 2026-08-27 에 구현됐고 **자기 양성 대조군에 실패**했다
  #   (확실한 자기 쌍조차 못 맺음 · **RELEASE 1줄이 CLAIM 둘을 닫는** 실례). 그 파생 수치는
  #   여러 세션에 뿌려진 뒤 **철회**됐다. 계산하지 않는 것을 계산한다고 말하지 않는다.
  board_grep '^- \[(CLAIM|RELEASE)\]' | tail -n "$SUMMARY_N" | truncate_chars 240
  echo "  ↳ 최근 ${SUMMARY_N}건만이고 줄이 길면 잘린다. 전문: grep -nE '^- \[(CLAIM|RELEASE)\]' \"\$BOARD\""
  echo
  echo "=== 최근 NOTE — 최근 ${SUMMARY_N}건 (시간순 · 최신이 아래) ==="
  # ★NOTE 는 보드에서 가장 많은 종류인데 종전 요약 절은 `\[(CLAIM|RELEASE)\]` 만 grep 해
  #   **한 건도 안 보였다.** CLAUDE.md 는 인계 공유를 `coord.sh note` 로 하라고 지시하는데
  #   **그 공유가 요약 화면에서 사라지고 있었다.**
  # ★여러 줄 NOTE 는 **첫 줄만** 나온다 — 이어지는 줄에는 `- [NOTE]` 표지가 없기 때문이다.
  board_grep '^- \[NOTE\]' | tail -n "$SUMMARY_N" | truncate_chars 240
  echo "  ↳ 여러 줄 노트는 첫 줄만, 긴 줄은 잘린다. 전문: sed -n '<행번호>,+40p' \"\$BOARD\""
}

cmd="${1:-status}"
shift || true

case "$cmd" in
  status)
    # ★★`status` 는 **조회 명령**이다. 2판은 여기서 `ensure_board` 를 불러 `COORD_DIR` 오타 시
    #   **빈 유령 보드를 만들고 rc=0 으로 "실제로 0건" 이라 단정**했다(적대 리뷰 실측).
    #   CLAUDE.md 가 세션 시작에 이 명령을 시키므로 그 위음성의 값이 가장 크다.
    require_board
    echo "=== 워크트리 / 브랜치 ==="
    git worktree list
    echo
    echo "=== 공유 보드: $BOARD ==="
    cat "$BOARD"
    echo
    # ★이 절은 **종전 그대로**다(제목·전량 출력·무절단). 문서화된 소비자가 있다 —
    #   인계서들이 "★자르지 마라 — NOTE 줄에 배포 요청이 숨는다" 라고 명시한다.
    #   그래서 `status` 는 후방호환을 유지하고, 요약은 `summary` 로 **따로** 낸다.
    echo "=== 미해제 CLAIM(편집 중인 공유영역) ==="
    echo "  ※이 절은 짝짓기를 하지 않는다 — CLAIM 과 RELEASE 를 **전부** 인쇄한다(제목과 다르다)."
    echo "  ※간결한 요약은 'coord.sh summary'."
    board_grep '\[(CLAIM|RELEASE)\]'
    echo
    # ★신설 — 종전에는 NOTE 가 여기서 **한 건도** 안 보였다. 절단하지 않는다(위 소비자 주석 참조).
    echo "=== 최근 NOTE (최근 ${SUMMARY_N}건 · 무절단) ==="
    board_grep '^- \[NOTE\]' | tail -n "$SUMMARY_N"
    ;;
  summary)
    require_board   # ★조회 명령은 보드를 만들지 않는다(유령 보드 방지)
    echo "=== 워크트리 / 브랜치 ==="
    git worktree list
    echo
    echo "=== 공유 보드: $BOARD ($(wc -l < "$BOARD")줄 · ★전문은 출력하지 않는다) ==="
    echo
    print_summary
    ;;
  claim)
    [ $# -ge 1 ] || { echo "사용: coord.sh claim <영역>" >&2; exit 1; }
    ensure_board
    printf -- '- [CLAIM] %s <- %s (%s · sid=%s)\n' "$1" "$BRANCH" "$(stamp)" "$(sid)" >> "$BOARD"
    echo "claimed: $1 <- $BRANCH"
    ;;
  release)
    [ $# -ge 1 ] || { echo "사용: coord.sh release <영역>" >&2; exit 1; }
    ensure_board
    printf -- '- [RELEASE] %s <- %s (%s · sid=%s)\n' "$1" "$BRANCH" "$(stamp)" "$(sid)" >> "$BOARD"
    echo "released: $1"
    ;;
  note)
    [ $# -ge 1 ] || { echo "사용: coord.sh note <내용>" >&2; exit 1; }
    ensure_board
    printf -- '- [NOTE] %s %s sid=%s: %s\n' "$(stamp)" "$BRANCH" "$(sid)" "$*" >> "$BOARD"
    echo "noted."
    ;;
  *)
    echo "사용: coord.sh {status | summary | claim <영역> | release <영역> | note <내용>}" >&2
    exit 1
    ;;
esac
