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


def _requirements_files() -> list[pathlib.Path]:
    """★목록형이 아니라 **파생형** — `requirements*.txt` 를 전부 찾는다.

    2026-08-21 실측 사고: 이 테스트가 `requirements.txt` **한 파일만** 봤고, `#720` 도 그
    파일에서만 PyJWT 를 지웠다. 그런데 **프로덕션이 쓰는 파일은 다른 것**이다 —
    `Dockerfile.oracle:20` 이 `apps/api/requirements.oracle.txt` 를 복사한다.
    그래서 CI 는 초록이었고 **라이브 컨테이너엔 `PyJWT 2.9.0` 이 그대로 있었다**
    (배포 후 `pip show PyJWT` 실측). **처방이 환자에게 닿지 않았다.**
    """
    return sorted(_API_ROOT.glob("requirements*.txt"))


def _dockerfile_copy_pairs(text: str) -> list[tuple[str, str]]:
    """`COPY <src…> <dst>` 를 **(출발지, 도착지)** 쌍으로 뽑는다.

    ★**역할은 도착지가 말하고, 검사 대상은 출발지다.**
      처음엔 출발지 **이름**에 `requirement` 가 들어있는지로 걸렀는데, 그러면
      `COPY apps/api/reqs-prod.txt ./requirements.txt` 처럼 **이름만 바꾼 경우가 그대로 빠져나간다**
      (변이 실측 SURVIVED — 이 PR 안에서 같은 오류를 세 번째로 재현했다).
      이름이 아니라 **그 파일이 이미지 안에서 무엇이 되는가**(도착지)로 판정한다.

    ★그리고 처음 정규식은 아예 **도착지를 출발지로 오인**했다(첫 변이 SURVIVED).
      플래그(`--chown=` 등)를 걷어내고 마지막 토큰만 도착지로 본다.
    """
    pairs: list[tuple[str, str]] = []
    for line in text.splitlines():
        l = line.strip()
        if not l.upper().startswith("COPY "):
            continue
        toks = [t for t in l.split()[1:] if not t.startswith("--")]
        if len(toks) < 2:
            continue
        dst = toks[-1]
        for src in toks[:-1]:
            pairs.append((src.rsplit("/", 1)[-1], dst.rsplit("/", 1)[-1]))
    return pairs


def _dockerfiles() -> list[pathlib.Path]:
    """★저장소의 **모든 Dockerfile** — 하나만 보면 이 테스트가 막으려는 결함을 스스로 갖는다.

    2026-08-21 실측: Dockerfile 이 **7개**이고 그중 **4개**가 requirements 를 COPY 하는데
    **두 파일로 갈린다** — `Dockerfile.oracle`→`requirements.oracle.txt`(프로덕션 API·워커·
    flower·beat 가 모두 이 이미지를 쓴다) / 나머지 3개→`requirements.txt`.
    처음 쓴 이 테스트는 `Dockerfile.oracle` **하나만** 봤다 — 고치려던 결함(한 파일만 보는
    검사)과 같은 형태였다.
    """
    root = _API_ROOT.parents[1]
    out = [
        p
        for p in root.rglob("Dockerfile*")
        if p.is_file() and "node_modules" not in str(p) and not p.name.endswith((".md", ".txt"))
    ]
    return sorted(out)


def test_전제_Dockerfile_을_실제로_찾는다() -> None:
    """★공허한 초록 방지 — 0건이면 아래 단언이 자동 통과한다."""
    names = {p.name for p in _dockerfiles()}
    assert "Dockerfile.oracle" in names, (
        f"배포 정본 Dockerfile.oracle 을 못 찾았다 — 탐색이 죽었거나 경로가 바뀌었다: {sorted(names)}"
    )
    assert len(_dockerfiles()) >= 3, f"Dockerfile 을 {len(_dockerfiles())}건만 찾았다 — 탐색이 죽었다"


def test_모든_이미지가_설치하는_requirements_가_검사망에_있다() -> None:
    """★**어떤 이미지든** 설치하는 requirements 는 검사망 안이어야 한다.

    판정 기준은 **도착지의 역할**이다 — 이미지 안에서 `requirements*.txt` 가 되는 파일이면,
    그 **출발지**가 검사망에 있어야 한다. 출발지 이름이 무엇이든 상관없다.
    새 requirements 를 만들어 어느 Dockerfile 이든 그것을 가리키면,
    그 파일이 `requirements*.txt` 패턴을 벗어나는 순간 실패한다 —
    **검사망 밖으로 나가는 것 자체가 실패**다.
    """
    검사망 = {p.name for p in _requirements_files()}
    검사한_쌍 = 0
    위반: list[str] = []
    for df in _dockerfiles():
        for src, dst in _dockerfile_copy_pairs(df.read_text(encoding="utf-8")):
            # 역할 판정: 이미지 안에서 requirements 가 되는가
            if not (dst.startswith("requirements") and dst.endswith(".txt")):
                continue
            검사한_쌍 += 1
            if src not in 검사망:
                위반.append(f"{df.name}: {src} → {dst}")
    # ★공허 진리 가드 — 그런 COPY 가 0건이면 "위반 0"은 무의미하다.
    assert 검사한_쌍 >= 1, (
        "requirements 로 설치되는 COPY 가 한 건도 안 잡혔다 — 추출기나 탐색이 죽었다. "
        f"Dockerfile={[p.name for p in _dockerfiles()]}"
    )
    assert not 위반, (
        "배포 이미지가 설치하는 파일이 검사망 밖이다 — 취약 의존성이 들어와도 아무도 못 잡는다.\n"
        f"  {위반}\n  검사망={sorted(검사망)}"
    )


def test_추출기_대조군_출발지와_도착지를_바르게_가른다() -> None:
    """★추출기의 자체 대조군 — 잡아야 할 것과 통과시켜야 할 것을 **둘 다** 단언한다."""
    assert _dockerfile_copy_pairs("COPY --chown=x:y apps/api/reqs-prod.txt ./requirements.txt") == [
        ("reqs-prod.txt", "requirements.txt")
    ], "도착지를 출발지로 오인하거나 이름으로 걸러낸다"
    assert _dockerfile_copy_pairs("COPY --chown=x:y apps/api/requirements.oracle.txt ./requirements.txt") == [
        ("requirements.oracle.txt", "requirements.txt")
    ], "정상 표기를 못 뽑는다"
    assert _dockerfile_copy_pairs("COPY . .") == [(".", ".")], "일반 COPY 를 잘못 다룬다"


def test_PyJWT_가_requirements_에_다시_들어오지_않는다() -> None:
    위반: list[str] = []
    검사한_파일 = 0
    for path in _requirements_files():
        검사한_파일 += 1
        for line in path.read_text(encoding="utf-8").splitlines():
            l = line.strip()
            if not l or l.startswith("#"):
                continue
            if l.lower().startswith("pyjwt"):
                위반.append(f"{path.name}: {l}")
    # ★공허 진리 가드 — 한 파일도 안 읽었으면 "위반 0" 은 부재의 증거가 아니다.
    assert 검사한_파일 >= 2, f"requirements 를 {검사한_파일}건만 읽었다 — 탐색이 죽었다"
    assert not 위반, (
        "쓰지 않는 PyJWT 가 requirements 에 다시 들어왔다 — CVE 12건이 함께 돌아온다. "
        f"인증은 python-jose 를 쓴다: {위반!r}"
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
