"""법정 한도를 **지어내지 않는다** — 날조형 기본값 재유입 방지 (2026-08-22).

## 무엇이 있었나

`or 60` · `or 200` · `or 250` 같은 최종 폴백이 **법정 건폐율·용적률을 발명**했다.
용도지역이 테이블에 없거나 한쪽 축만 결측이면, 자연녹지(법정 20/100)에
제2종일반주거급 한도(60/200~250)가 들어갔다.

이 사고는 **이미 두 번 문서화**돼 있었다.

    project_pipeline.py:721   `or 200`/`or 60` 날조 기본값으로 자연녹지에 200%를 발명했다
    far_tier_service.py:213   과거엔 이 경로가 … 200%/60%를 지어내 블렌드를 139.6%로 오염시켰다

그런데 **고친 자리의 형제를 스윕하지 않아** 같은 패턴이 6곳에 남아 있었다
(far_tier · ordinance · persona/runner · project_pipeline · v2_feasibility · design_v61).
★`far_tier_service` 의 가드는 조건이 `and` 4개라 **"전부 결측"만** 막았고,
  **부분 결측**(건폐는 확인·용적만 미확인)은 그대로 통과해 값을 지어냈다.

## 이 파일이 잠그는 것

1. 법정 한도 문맥에서 `or <숫자>` 로 값을 만드는 코드가 **다시 들어오지 않는다**
2. 판별기가 **주석·문자열이 아니라 실행 코드**만 본다(AST)
3. 판별기 자체가 정상 코드를 오신고하지 않는다(**대조군**)
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_API = pathlib.Path(__file__).resolve().parents[1]

# 법정 한도를 다루는 자리 — 여기서 숫자 폴백은 곧 '발명'이다.
_LIMIT_NAMES = ("bcr", "far", "max_bcr", "max_far", "national_bcr", "national_far",
                "legal_bcr", "legal_far", "applied_bcr", "applied_far")
# 한도로 오인될 수 있는 값들(발명이 아님).
_ALLOW_NUMS = {0, 1}


def _is_limit_context(node: ast.AST) -> bool:
    """대입 대상 이름이 한도 계열인가."""
    targets = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    for tgt in targets:
        name = getattr(tgt, "id", None) or getattr(tgt, "attr", None)
        if name and name.lower() in _LIMIT_NAMES:
            return True
    return False


def _fabricates(node: ast.AST) -> bool:
    """`... or <2자리 이상 상수>` 로 값을 만드는가."""
    for sub in ast.walk(node):
        if isinstance(sub, ast.BoolOp) and isinstance(sub.op, ast.Or):
            last = sub.values[-1]
            if isinstance(last, ast.Constant) and isinstance(last.value, (int, float)):
                if last.value not in _ALLOW_NUMS:
                    return True
    return False


def _scan(root: pathlib.Path) -> list[str]:
    out: list[str] = []
    for p in root.rglob("*.py"):
        if any(x in p.parts for x in (".venv", "__pycache__", "tests", "node_modules")):
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and _is_limit_context(node) and _fabricates(node):
                out.append(f"{p.relative_to(_API)}:{node.lineno}")
    return out


def test_법정한도를_숫자_폴백으로_발명하지_않는다() -> None:
    roots = [_API / "app" / "services", _API / "app" / "routers", _API / "services"]
    roots = [r for r in roots if r.exists()]
    # ★공허 진리 방지 — 스캔 대상이 없으면 '위반 0'은 아무 의미가 없다.
    total = sum(1 for r in roots for _ in r.rglob("*.py"))
    assert total > 200, f"스캔 대상이 {total}개뿐이다 — 경로가 틀렸다"

    위반 = [v for r in roots for v in _scan(r)]
    assert not 위반, (
        "법정 건폐율·용적률을 숫자 폴백으로 **발명**하는 코드가 다시 들어왔다. "
        "없는 값은 None 으로 정직 전파하고 소비처에서 미산출로 처리하라: " + str(위반)
    )


@pytest.mark.parametrize(
    ("src", "위반이어야"),
    [
        ("far = zone.get('far') or 200", True),
        ("national_bcr = legal or zl or 60", True),
        ("max_far: float = float(x.get('far') or 250)", True),
        # ── 아래는 발명이 아니다 ──
        ("far = zone.get('far')", False),                    # 정직 전파
        ("applied_bcr = float(ord_bcr or legal_bcr or 0)", False),  # 0 = 미산출 신호
        ("limit = int(limit or 50)", False),                 # 한도 계열 이름이 아님(조회 개수)
        ("timeout = t or 30", False),
    ],
)
def test_판별기가_발명과_정직전파를_가른다(src: str, 위반이어야: bool) -> None:
    """★판별기 자체를 시험한다 — *무엇이든 잡거나 아무것도 안 잡는* 판별기를 막는다."""
    tree = ast.parse(src)
    hit = any(
        isinstance(n, (ast.Assign, ast.AnnAssign)) and _is_limit_context(n) and _fabricates(n)
        for n in ast.walk(tree)
    )
    assert hit is 위반이어야, f"판별 오류: {src!r} → {hit}"
