#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# vitest 를 돌리고, **관측된 플레이크 서명일 때만** 1회 재시도한다.
# 판정은 이 파일이 하지 않는다 — `vitest_flake_classify.sh` 가 한다(그쪽에 근거와 실측이 있다).
#
# ★종료코드는 **파이프 끝이 아니라 명령**의 것을 읽는다(`PIPESTATUS`).
#   이 저장소는 `pytest | tail` 이 exit 0 인데 실제로는 37 수집오류였던 전례가 있다
#   (CLAUDE.md §검증 규율 9). `tee` 를 쓰는 순간 같은 함정에 들어간다.
# ★재시도는 **1회뿐**이다. 여러 번 돌리면 "언젠가는 초록"이 되어 게이트가 무의미해진다.
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLASSIFY="$HERE/vitest_flake_classify.sh"
CMD=${VITEST_CMD:-"pnpm test:run"}
LOG=$(mktemp)
trap 'rm -f "$LOG"' EXIT

$CMD 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}
[ "$rc" = 0 ] && exit 0

verdict=$(bash "$CLASSIFY" "$LOG")
echo "─────────────────────────────────────────"
echo "★vitest 실패(rc=$rc) — 로그 판정: $verdict"

case "$verdict" in
  FLAKE)
    echo "★관측된 vitest-worker RPC 타임아웃 서명입니다(테스트 실패는 0건)."
    echo "  1회만 재시도합니다. 두 번째도 실패하면 그대로 빨강입니다."
    $CMD
    rc2=$?
    if [ "$rc2" != 0 ]; then
      echo "★재시도도 실패(rc=$rc2) — 플레이크가 아닙니다. 게이트를 유지합니다."
    fi
    exit "$rc2"
    ;;
  REAL)
    echo "★테스트가 실제로 실패했습니다 — 재시도하지 않습니다."
    exit "$rc"
    ;;
  *)
    echo "★알 수 없는 실패입니다(요약 부재 = 수집 실패·크래시 가능) — 재시도하지 않습니다."
    exit "$rc"
    ;;
esac
