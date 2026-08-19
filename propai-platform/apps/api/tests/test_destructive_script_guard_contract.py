"""**데이터를 파괴하는 스크립트는 프로덕션 가드를 가져야 한다** — 파생형 락.

★왜 (2026-08-20):
    `scripts/db_reset_and_migrate.sh` 가 `docker compose … down -v`(**볼륨 삭제**)를
    **가드 없이** 실행하고 있었다. 실측으로 드러난 상태:

        · 158·168 **프로덕션 양쪽에 실재** — 두 서버 모두 저장소를 `git reset --hard` 로
          통째로 받으므로 배포될 때마다 함께 올라간다.
        · 저장소 전역 **호출처 0건**(대조군 생존) — 아무도 이 경로를 테스트하지 않는다.
        · 이름은 일상적인데(`db_reset_and_migrate`) 동작은 파괴적이다.
          마이그레이션 방법을 찾던 사람·에이전트가 집어 들기 딱 좋다.

★**파생형이다 — 목록형이 아니다.**
    파일 이름을 손으로 적지 않고, 저장소의 **모든 `.sh` 를 훑어** 파괴적 명령을 찾는다.
    새 스크립트가 들어와도 자동으로 감시망에 들어온다(사람이 센 목록은 그 순간이 상한이다 —
    이 저장소는 "목록 5 vs 실제 11" 로 이미 데였다).

★**범위를 데이터 파괴로 좁힌다.**
    빌드 산출물 정리(`rm -rf contracts/artifacts`)나 임시 디렉터리 정리
    (`trap 'rm -rf "$WORKDIR"' EXIT`)까지 잡으면 **정상 코드를 막는다** —
    가드의 위양성도 결함이다(CLAUDE.md §회귀망 A.6). 되돌릴 수 없는 **데이터**만 본다.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]

# 되돌릴 수 없는 **데이터** 파괴만. 산출물·임시파일 정리는 대상이 아니다.
_DESTRUCTIVE_RX = re.compile(
    r"(?:docker\s+compose[^\n]*\s(?:-v\b|--volumes\b)"      # 볼륨 삭제
    r"|docker\s+volume\s+(?:rm|prune)\b"
    r"|DROP\s+DATABASE\b"
    r"|TRUNCATE\s+TABLE\b)",
    re.IGNORECASE,
)

# 가드로 인정하는 표식. 하나라도 있으면 "사람이 막을 생각을 했다"로 본다.
#   ★`read -p` 는 **인정하지 않는다** — 비대화 셸(CI·`</dev/null`)에서 그냥 통과한다.
_GUARD_RX = re.compile(
    r"(?:DB_RESET_CONFIRM|_CONFIRM\b|is_production|docker\s+ps[^\n]*grep[^\n]*propai|exit\s+1[01]\b)"
)


def _shell_files() -> list[Path]:
    out: list[Path] = []
    for p in _REPO.rglob("*.sh"):
        s = str(p)
        if "/node_modules/" in s or "/.git/" in s or "/worktrees/" in s:
            continue
        out.append(p)
    return sorted(out)


def _code_only(text: str) -> str:
    """주석 줄을 걷어낸다 — 주석 속 예시를 실제 명령으로 오인하면 위양성이 난다."""
    return "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#"))


def test_전제_셸_스크립트를_실제로_찾는다() -> None:
    """★공허한 초록 방지 — 파일을 못 찾으면 아래 단언이 **0건 실행**되고 조용히 통과한다."""
    files = _shell_files()
    assert len(files) >= 5, f"셸 스크립트를 {len(files)}건밖에 못 찾았다 — 탐색이 죽었다"
    names = {p.name for p in files}
    assert "db_reset_and_migrate.sh" in names, (
        "알려진 대상이 탐색에 안 잡힌다 — 경로 규칙이 바뀌었으면 이 테스트도 고칠 것"
    )


def test_파괴적_명령_탐지기가_살아_있다() -> None:
    """★양성 대조군 — 탐지기가 알려진 사례를 실제로 잡는지 먼저 확인한다.

    이게 없으면 "위반 0" 이 *"파괴적 스크립트가 없다"* 인지 *"정규식이 죽었다"* 인지 갈리지 않는다.
    """
    target = _REPO / "propai-platform" / "scripts" / "db_reset_and_migrate.sh"
    assert target.exists(), f"{target} 가 없다 — 대조군이 사라졌다"
    assert _DESTRUCTIVE_RX.search(_code_only(target.read_text(encoding="utf-8"))), (
        "알려진 파괴적 명령(`down -v`)을 탐지기가 못 잡는다 — 이 상태의 '위반 0'은 무의미하다"
    )
    # ★음성 대조군: 산출물 정리는 잡히면 안 된다(위양성 = 정상 코드 차단).
    for benign in [
        'rm -rf /repo/contracts/artifacts',
        "trap 'rm -rf \"$WORKDIR\"' EXIT",
        "docker compose -f infra/docker-compose.yml up -d postgres",
    ]:
        assert not _DESTRUCTIVE_RX.search(benign), f"정상 표기를 위반으로 신고한다: {benign!r}"


def test_데이터를_파괴하는_스크립트는_가드를_가진다() -> None:
    """가드 없는 파괴적 스크립트가 있으면 실패한다.

    ★프로덕션 서버는 저장소를 `git reset --hard` 로 통째로 받는다 — 즉 저장소에 들어온
      스크립트는 **자동으로 실서버에 배포된다.** "로컬 전용"이라는 의도는 파일에 적혀 있을 뿐
      실행을 막지 못한다.
    """
    violations: list[str] = []
    checked = 0
    for path in _shell_files():
        code = _code_only(path.read_text(encoding="utf-8", errors="replace"))
        hit = _DESTRUCTIVE_RX.search(code)
        if not hit:
            continue
        checked += 1
        if not _GUARD_RX.search(code):
            rel = path.relative_to(_REPO)
            violations.append(f"{rel} — {hit.group(0).strip()!r}")

    assert checked >= 1, (
        "파괴적 명령을 가진 스크립트가 **한 건도** 안 잡혔다 — 탐지기나 탐색이 죽었다. "
        "이 상태의 '위반 0'은 부재의 증거가 아니다."
    )
    assert not violations, (
        "데이터를 되돌릴 수 없게 파괴하는 스크립트에 **프로덕션 가드가 없다**.\n  "
        + "\n  ".join(violations)
        + "\n  → ①프로덕션 컨테이너 실행 중이면 중단 ②명시적 확인(환경변수) 요구."
        "\n  ★`read -p` 는 가드가 아니다 — 비대화 셸에서 그냥 통과한다."
    )
