"""alembic 리비전 그래프에 head 가 **하나뿐인지** 잠근다.

★2026-09-06 실측 — 이 결함은 **CI 도 못 잡고 배포에서야** 드러났다:
    배포 스크립트 infra/deploy-zero-downtime.sh:234
      alembic upgrade head          ← 단수 'head'
    FAILED: Multiple head revisions are present for given argument 'head'
  `v62_9` 의 부모를 `v62_8_run_execution` 으로 뒀는데, v62_8 은 **이미 자식**
  (`042_member_account_system`)이 있어 거기 매달면 042 와 형제가 되어 **가지를 친다.**
  실제 단일 head 는 `043_mypage_coin_orders_ledger` 였다.

★배포 스크립트가 옳게 동작해 **트래픽 전환 없이 중단**됐다(라이브 손상 0).
  그래도 배포 한 사이클을 태웠다 — 그 판정을 **테스트로 앞당긴다.**
"""
from __future__ import annotations

import ast
from pathlib import Path

VERSIONS = Path(__file__).resolve().parents[1] / "database" / "migrations" / "versions"


def _graph() -> tuple[dict[str, str], dict[str, tuple[str, ...]]]:
    """revision → 파일명, revision → 부모들.

    ★`revision = "x"` 와 `revision: str = "x"` **두 형태를 모두** 읽는다.
      2026-09-06: AnnAssign 을 빠뜨려 58파일 중 41개만 읽고 «head 1개» 라는
      **거짓 초록**을 냈다. 파서가 모집단을 자르면 판정 전체가 무의미하다.
    """
    revs: dict[str, str] = {}
    downs: dict[str, tuple[str, ...]] = {}
    for p in sorted(VERSIONS.glob("*.py")):
        if p.name == "__init__.py":
            continue
        tree = ast.parse(p.read_text(encoding="utf-8"))
        rev = None
        down: object = None
        has_down = False
        for node in ast.walk(tree):
            name = value = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name, value = node.targets[0].id, node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                name, value = node.target.id, node.value
            if name not in ("revision", "down_revision"):
                continue
            try:
                val = ast.literal_eval(value)
            except Exception:  # noqa: BLE001 — 동적 값은 이 판정에 쓰지 않는다
                continue
            if name == "revision":
                rev = val
            else:
                down, has_down = val, True
        assert rev is not None, f"revision 을 못 읽었다: {p.name} — 판정 불가"
        revs[rev] = p.name
        if has_down:
            if down is None:
                downs[rev] = ()
            elif isinstance(down, (list, tuple)):
                downs[rev] = tuple(down)
            else:
                downs[rev] = (down,)
    return revs, downs


def _heads(revs, downs) -> list[str]:
    parents: set[str] = set()
    for ds in downs.values():
        parents.update(ds)
    return sorted(r for r in revs if r not in parents)


class TestAlembicGraph:
    def test_모집단이_충분히_읽혔다(self):
        """★공허 진리 가드 — 파서가 대부분을 못 읽으면 「head 1개」가 거짓으로 참이 된다."""
        revs, _ = _graph()
        files = [p for p in VERSIONS.glob("*.py") if p.name != "__init__.py"]
        assert len(revs) == len(files), f"파싱 {len(revs)} != 파일 {len(files)} — 판정 불가"
        assert len(revs) >= 50, f"리비전 {len(revs)}개 — 너무 적다, 조회기 사망 의심"

    def test_head_는_정확히_하나다(self):
        """★`alembic upgrade head`(단수)가 배포에서 쓰인다 — 둘이면 배포가 멈춘다."""
        revs, downs = _graph()
        heads = _heads(revs, downs)
        assert len(heads) == 1, "head 가 여럿이다: " + ", ".join(f"{h}({revs[h]})" for h in heads)

    def test_모든_부모가_실재한다(self):
        """★매달린 참조 — 없는 리비전을 부모로 두면 alembic 이 다른 오류로 죽는다."""
        revs, downs = _graph()
        dangling = {
            revs[r]: [d for d in ds if d not in revs] for r, ds in downs.items() if any(d not in revs for d in ds)
        }
        assert dangling == {}, f"존재하지 않는 부모: {dangling}"

    def test_순환이_없다(self):
        revs, downs = _graph()
        seen: dict[str, int] = {}

        def walk(node: str, stack: tuple[str, ...]) -> None:
            if node in stack:
                raise AssertionError(f"순환: {' → '.join((*stack, node))}")
            if seen.get(node):
                return
            seen[node] = 1
            for parent in downs.get(node, ()):  # 없는 부모는 위 테스트가 잡는다
                if parent in revs:
                    walk(parent, (*stack, node))

        for r in revs:
            walk(r, ())
