#!/usr/bin/env bash
# 멀티세션 협업 헬퍼 — 공유 보드(브랜치 무관) 조회/클레임/해제/노트.
# 정책: coordination/PROTOCOL.md · WORKTREES.md. 보드: ~/My_Projects/.coordination/BOARD.md
# 사용: scripts/coord.sh {status | claim <영역> | release <영역> | note <내용>}
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
BOARD_DIR="${COORD_DIR:-$(cd "$ROOT/.." && pwd)/.coordination}"
BOARD="$BOARD_DIR/BOARD.md"
BRANCH="$(git branch --show-current 2>/dev/null || echo '?')"
mkdir -p "$BOARD_DIR"

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
    echo "=== 미해제 CLAIM(편집 중인 공유영역) ==="
    # [CLAIM] 중 같은 영역의 [RELEASE]가 뒤에 없는 것만 — 간이 추출
    grep -nE '\[(CLAIM|RELEASE)\]' "$BOARD" || echo "(없음)"
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
    echo "사용: coord.sh {status | claim <영역> | release <영역> | note <내용>}" >&2
    exit 1
    ;;
esac
