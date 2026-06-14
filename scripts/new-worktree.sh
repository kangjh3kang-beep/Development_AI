#!/usr/bin/env bash
# 브랜치 전용 git worktree 생성 — 세션 간 HEAD 충돌(같은 워크트리 브랜치 전환) 재발 방지.
# 정책: WORKTREES.md 참조. 사용: scripts/new-worktree.sh <branch> [slug]
set -euo pipefail

BRANCH="${1:?사용법: scripts/new-worktree.sh <branch> [slug]}"
# slug 미지정 시 브랜치명 끝부분을 안전 문자로 변환(feature/trust-infra-... → trust_infra_...)
SLUG="${2:-$(printf '%s' "$BRANCH" | sed 's#.*/##; s/[^A-Za-z0-9]/_/g')}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
PARENT="$(dirname "$REPO_ROOT")"
BASE="$(basename "$REPO_ROOT")"
DEST="$PARENT/${BASE}_${SLUG}"

if git worktree list --porcelain | grep -qx "worktree $DEST"; then
  echo "이미 존재: $DEST"
  exit 0
fi

# 로컬 브랜치가 없으면 원격에서 추적 생성
if ! git show-ref --verify --quiet "refs/heads/$BRANCH"; then
  if git show-ref --verify --quiet "refs/remotes/origin/$BRANCH"; then
    git worktree add "$DEST" -b "$BRANCH" "origin/$BRANCH"
  else
    echo "오류: 브랜치 '$BRANCH'가 로컬/원격에 없습니다." >&2
    exit 1
  fi
else
  # git이 이미 다른 워크트리에 checkout된 브랜치는 거부(의도된 안전장치)
  git worktree add "$DEST" "$BRANCH"
fi

echo "생성됨: $DEST  ($BRANCH)"
echo "이제 그 디렉토리에서만 작업하세요. 공유 메인 워크트리에서 feature 브랜치 checkout 금지."
echo "주의: 새 워크트리는 .venv/node_modules 없음 — 의존성 1회 설치 필요(WORKTREES.md)."
