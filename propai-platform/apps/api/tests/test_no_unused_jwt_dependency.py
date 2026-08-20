"""쓰지 않는 JWT 라이브러리가 **CVE 12건을 물고** 이미지에 있었다 — 다시 들어오지 못하게 잠근다.

## 왜 지웠나 (2026-08-20 · 라이브 실측)

`Security Scan` 을 되살리자 `PyJWT 2.9.0` 이 **취약점 12건**으로 나왔다. 그런데

| 확인 | 결과 |
|---|---|
| `import jwt` 하는 실행 코드 | **0파일** |
| 동적 참조(`import_module("jwt")` 등) | **0건** |
| 168 컨테이너에서 `pip show PyJWT` 의 `Required-by` | **없음** (아무도 요구 안 함) |
| 실제 인증이 쓰는 것 | `from jose import jwt` — **python-jose** |

즉 **아무도 쓰지 않는 라이브러리가 CVE 12건을 물고** 배포 이미지에 들어 있었다.
지우는 것이 올리는 것보다 낫다 — **없는 코드에는 취약점이 없다.**

## 이 락이 막는 것

되돌림은 조용히 일어난다. `requirements.txt` 에 한 줄이 다시 들어오거나,
누군가 `import jwt` 를 쓰면 12건이 그대로 돌아온다.

★검사는 **AST** 로 한다. 문자열 검색은 주석 처리 변이에 뚫린다(이 저장소에서 2회 실증).
★`from jose import jwt` 는 **허용**해야 한다 — 그게 실제 인증 경로다. 아래 대조군이
  그 구분이 살아 있는지 증명한다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

_API_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCAN_DIRS = ("app", "services", "database", "ml")
_SKIP = {".venv", "node_modules", "__pycache__", "tests"}


def _python_files() -> list[pathlib.Path]:
    out: list[pathlib.Path] = []
    for d in _SCAN_DIRS:
        root = _API_ROOT / d
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if any(part in _SKIP for part in p.parts):
                continue
            out.append(p)
    return out


def _imports_toplevel_jwt(tree: ast.AST) -> bool:
    """`import jwt` / `from jwt import ...` 만 잡는다. `from jose import jwt` 는 아니다."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "jwt" or alias.name.startswith("jwt."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            # node.module 이 'jwt' 여야 PyJWT 다. 'jose' 면 python-jose 로 정상이다.
            if node.module == "jwt" or (node.module or "").startswith("jwt."):
                return True
    return False


def test_PyJWT_가_requirements_에_다시_들어오지_않는다() -> None:
    req = (_API_ROOT / "requirements.txt").read_text(encoding="utf-8")
    선언 = [
        l.strip()
        for l in req.splitlines()
        if l.strip() and not l.strip().startswith("#") and l.strip().lower().startswith("pyjwt")
    ]
    assert not 선언, (
        "쓰지 않는 PyJWT 가 requirements 에 다시 들어왔다 — CVE 12건이 함께 돌아온다. "
        f"인증은 python-jose 를 쓴다: {선언!r}"
    )


def test_실행코드가_PyJWT_를_import_하지_않는다() -> None:
    files = _python_files()
    # ★공허 진리 방지 — 스캔 대상이 0개면 "위반 0"은 아무 의미가 없다.
    assert len(files) > 300, f"스캔 대상이 {len(files)}개뿐이다 — 경로가 틀렸다(이 초록은 무의미)"

    위반 = []
    for p in files:
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        if _imports_toplevel_jwt(tree):
            위반.append(str(p.relative_to(_API_ROOT)))

    assert not 위반, (
        "PyJWT(`import jwt`)를 쓰는 코드가 생겼다. 이 저장소의 인증은 "
        f"`from jose import jwt`(python-jose)를 쓴다: {위반!r}"
    )


def test_인증이_실제로_python_jose_를_쓴다_대조군() -> None:
    """★위 두 락은 *아무도 JWT 를 안 쓰는* 저장소에서도 초록이다 — 그러면 인증이
    통째로 사라져도 알아채지 못한다. 그래서 **jose 경로가 실제로 존재하는지** 본다.

    이 대조군이 깨지면 위 락들의 초록은 아무것도 보증하지 않는다.
    """
    사용처 = []
    for p in _python_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "jose":
                사용처.append(str(p.relative_to(_API_ROOT)))
                break

    assert 사용처, (
        "python-jose 를 쓰는 코드가 하나도 없다 — 인증 경로가 사라졌거나 스캔이 잘못됐다. "
        "이 상태에서는 위 PyJWT 락이 '위반 0'이어도 아무 의미가 없다"
    )


@pytest.mark.parametrize(
    ("src", "위반이어야"),
    [
        ("import jwt", True),
        ("import jwt.algorithms", True),
        ("from jwt import decode", True),
        ("from jose import jwt", False),           # ★실제 인증 경로 — 잡으면 안 된다
        ("from jose.exceptions import JWTError", False),
        ("# import jwt", False),                    # ★주석은 실행 코드가 아니다
        ('S = "import jwt"', False),                # ★문자열도 아니다
    ],
)
def test_판별기가_PyJWT_와_jose_를_가른다(src: str, 위반이어야: bool) -> None:
    """★판별기 자체를 시험한다. 이게 없으면 위 락이 *무엇이든 잡거나 아무것도 안 잡는*
    판별기를 써도 초록이다. 주석·문자열 케이스는 AST 검사가 문자열 검색보다 나은
    이유를 그대로 잠근다.
    """
    assert _imports_toplevel_jwt(ast.parse(src)) is 위반이어야
