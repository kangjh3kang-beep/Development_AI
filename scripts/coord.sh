#!/usr/bin/env bash
# 멀티세션 협업 헬퍼 — 공유 보드(브랜치 무관) 조회/클레임/해제/노트.
# 정책: coordination/PROTOCOL.md · WORKTREES.md. 보드: <repo>/.git/coordination/BOARD.md (git-common-dir·저장소 스코프)
# 사용: scripts/coord.sh {status | summary | claim <영역> | release <영역> | note <내용>}
set -euo pipefail

# 보드는 우리 저장소의 공유 git 디렉토리(git-common-dir) 안에 둔다 — 모든 워크트리가 공유하면서
# 정확히 이 저장소에만 스코프되고, git이 추적하지 않아(브랜치무관·머지충돌 0) 라이브 상태에 적합.
BOARD_DIR="${COORD_DIR:-$(cd "$(git rev-parse --git-common-dir)" && pwd)/coordination}"
BOARD="$BOARD_DIR/BOARD.md"
BRANCH="$(git branch --show-current 2>/dev/null || echo '?')"
mkdir -p "$BOARD_DIR"

# 요약에 실을 최근 건수. 보드는 계속 자라므로 값이 아니라 꼬리를 본다.
SUMMARY_N="${COORD_SUMMARY_N:-12}"

if [ ! -f "$BOARD" ]; then
  {
    echo "# 멀티세션 협업 보드 (공유 · 브랜치 무관)"
    echo
    echo "> 규약: <worktree>/coordination/PROTOCOL.md. 세션 시작 시 읽고, 공유영역 편집 전 claim."
    echo
    echo "## 자동 로그 (coord.sh — claim/release/note, 최신이 아래)"
  } > "$BOARD"
fi

stamp() { date '+%Y-%m-%d %H:%M'; }

# 계산된 요약 절 — ★보드 전문을 뱉지 않는다.
#
# ★왜 전문을 안 뱉나: `status` 는 보드를 통째로 `cat` 한다(2026-09-03 실측 10,005줄). 그런데
#   보드 **본문에 절 제목이 그대로 인용돼 있다**(같은 날 실측: 문자열 `미해제 CLAIM` 이 본문에 11회).
#   그래서 하류에서 `sed -n '/<제목>/,$p'` 로 절을 자르면 **첫 발생**에서 잘려 보드 후반이 절에
#   섞여 들어간다 — 동료 세션이 그 때문에 「NOTE 685건이 보인다」로 **틀리게** 읽었고, 마지막
#   발생으로 다시 자르고 나서야 자기 부채 3건이 **전부 0건**임을 확인했다.
#   `summary` 는 본문을 출력하지 않으므로 그 충돌이 **구조적으로** 일어날 수 없다.
print_summary() {
  echo "=== CLAIM/RELEASE 로그 — 최근 ${SUMMARY_N}건 (시간순 · 최신이 아래) ==="
  # ★제목에 「미해제」라고 쓰지 않는다 — 이 절은 **짝짓기를 하지 않는다.**
  #   종전 제목은 `미해제 CLAIM(편집 중인 공유영역)` 이었고 주석은 필터를 선언했는데 코드에는
  #   필터가 없어 RELEASE 까지 전부 덤프했다(2026-09-03 실측 1,224줄). 제목이 사실과 달랐다.
  #   ★짝짓기를 여기서 되살리지 마라: 2026-08-27 에 구현됐고 **자기 양성 대조군에 실패**했다
  #   (확실한 자기 쌍조차 못 맺음 · **RELEASE 1줄이 CLAIM 둘을 닫는** 실례). 그 파생 수치는
  #   8개 세션에 뿌려진 뒤 **철회**됐다. 계산하지 않는 것을 계산한다고 말하지 않는다.
  grep -nE '^- \[(CLAIM|RELEASE)\]' "$BOARD" | tail -n "$SUMMARY_N" | cut -c1-240 || echo "(없음)"
  echo "  ↳ 이 절은 최근 ${SUMMARY_N}건만이다. 전문: grep -nE '^- \[(CLAIM|RELEASE)\]' \"\$BOARD\""
  echo
  echo "=== 최근 NOTE — 최근 ${SUMMARY_N}건 (시간순 · 최신이 아래) ==="
  # ★NOTE 는 보드에서 **가장 많은 종류**인데(2026-09-03 실측 NOTE 1,772 · CLAIM 641 · RELEASE 547)
  #   종전 요약 절은 `\[(CLAIM|RELEASE)\]` 만 grep 해 **한 건도 안 보였다.** CLAUDE.md 는 인계 공유를
  #   `coord.sh note` 로 하라고 지시하는데 **그 공유가 요약 화면에서 사라지고 있었다.**
  # ★여러 줄 NOTE 는 **첫 줄만** 나온다 — 이어지는 줄에는 `- [NOTE]` 표지가 없기 때문이다.
  #   이것은 의도된 절단이며, 그래서 행번호와 전문 조회 방법을 함께 인쇄한다.
  grep -nE '^- \[NOTE\]' "$BOARD" | tail -n "$SUMMARY_N" | cut -c1-240 || echo "(없음)"
  echo "  ↳ 여러 줄 노트는 첫 줄만 보인다. 전문: sed -n '<행번호>,+40p' \"\$BOARD\""
}

cmd="${1:-status}"
shift || true

case "$cmd" in
  status)
    echo "=== 워크트리 / 브랜치 ==="
    git worktree list
    echo
    echo "=== 공유 보드: $BOARD ==="
    cat "$BOARD"
    echo
    print_summary
    ;;
  summary)
    # 보드 전문 없이 계산된 절만 — 하류 슬라이싱이 본문과 충돌할 수 없다(위 print_summary 주석).
    echo "=== 워크트리 / 브랜치 ==="
    git worktree list
    echo
    echo "=== 공유 보드: $BOARD ($(wc -l < "$BOARD")줄 · ★전문은 출력하지 않는다) ==="
    echo
    print_summary
    ;;
  claim)
    [ $# -ge 1 ] || { echo "사용: coord.sh claim <영역>" >&2; exit 1; }
    printf -- '- [CLAIM] %s <- %s (%s)\n' "$1" "$BRANCH" "$(stamp)" >> "$BOARD"
    echo "claimed: $1 <- $BRANCH"
    ;;
  release)
    [ $# -ge 1 ] || { echo "사용: coord.sh release <영역>" >&2; exit 1; }
    printf -- '- [RELEASE] %s <- %s (%s)\n' "$1" "$BRANCH" "$(stamp)" >> "$BOARD"
    echo "released: $1"
    ;;
  note)
    [ $# -ge 1 ] || { echo "사용: coord.sh note <내용>" >&2; exit 1; }
    printf -- '- [NOTE] %s %s: %s\n' "$(stamp)" "$BRANCH" "$*" >> "$BOARD"
    echo "noted."
    ;;
  *)
    echo "사용: coord.sh {status | summary | claim <영역> | release <영역> | note <내용>}" >&2
    exit 1
    ;;
esac
