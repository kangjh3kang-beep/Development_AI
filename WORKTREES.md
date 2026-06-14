# 워크트리 정책 — 세션 간 브랜치 충돌 재발 방지

> **반드시 지킬 규칙: 작업 브랜치마다 전용 git worktree를 쓴다. 공유 워크트리에서 다른 브랜치를 `git checkout` 하지 않는다.**
>
> 협업 조율(누가 무슨 영역 작업 중·클레임·핸드오프): `coordination/PROTOCOL.md` · 공유 보드 `<repo>/.git/coordination/BOARD.md`(저장소 스코프·모든 워크트리 공유) · 한눈 조회 `scripts/coord.sh status`.

## 왜 (2026-06-14 사고)
여러 Claude 세션이 **하나의 메인 워크트리(`Development_AI/`)를 공유**하면서 각자 다른 브랜치를 `git checkout` 했다. 한 세션이 `feature/trust-infra-2026-06-11` → `feature/self-growth-engine`으로 전환하자 다른 세션의 HEAD가 따라 움직였고, 그 세션의 커밋(SP2-1)이 **엉뚱한 브랜치에 얹혔다.** 같은 워크트리에서 HEAD는 하나뿐이라, 동시 작업은 반드시 충돌한다.

## 규칙
1. **브랜치 1개 = 워크트리 1개.** 작업 시작 시 자기 브랜치 전용 워크트리를 만들고 거기서만 작업한다.
2. **공유 메인 워크트리(`Development_AI/`)에서 `git checkout <feature-branch>` 금지.** 메인은 기준(main) 확인 용도로만.
3. 커밋 전 항상 `git branch --show-current`로 자기 브랜치인지 확인한다.

## git이 자동 강제하는 안전장치 (핵심)
git은 **이미 어느 워크트리에 checkout된 브랜치를 다른 워크트리에서 다시 checkout하는 것을 거부**한다
(`fatal: '<branch>' is already checked out at '<path>'`). 즉 브랜치마다 전용 워크트리를 두면,
다른 세션이 그 브랜치를 공유 워크트리에서 checkout하려 해도 git이 막는다 — **규칙이 자동으로 유지된다.**

## 사용법
```bash
# 브랜치 전용 워크트리 생성(없으면) — 형제 디렉토리 Development_AI_<slug>/ 에 만든다
scripts/new-worktree.sh feature/trust-infra-2026-06-11
# → /home/.../My_Projects/Development_AI_trust_infra 생성, 그 안에서만 작업

git worktree list   # 현재 워크트리·브랜치 확인
```

## 현재 워크트리 (2026-06-14)
| 경로 | 브랜치 | 용도 |
|---|---|---|
| `Development_AI/` | (세션별 가변) | 공유 메인 — feature 작업 금지 |
| `Development_AI_trust_infra/` | `feature/trust-infra-2026-06-11` | trust-infra(설계/CAD/BIM/협업) 전용 |
| `Development_AI_market_upgrade/` | `feature/market-intel-upgrade-2026-06-13` | market 전용 |

## 주의 — 새 워크트리 의존성
새 워크트리는 `.venv`·`node_modules`·`.next`(gitignore)가 없다. 테스트/빌드 전 1회 설치:
```bash
cd <worktree>/propai-platform/apps/api && python -m venv .venv && . .venv/bin/activate && pip install -r requirements*.txt
cd <worktree>/propai-platform/apps/web && pnpm install
```
