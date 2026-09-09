"""★인터프리터 때문에 건너뛰는 락은 **고치는 법을 달고 있어야** 한다(2026-09-10).

【왜 · 실측】이 저장소의 `apps/api` 라우터는 기본 `python3`(miniforge **3.10**)에서
**임포트조차 안 된다** — `datetime.UTC`(3.11+) · PEP 695 `class CRUDBase[M]:`(3.12+).
그래서 라우터 락을 `skipif` + AST 로 짜게 되는데, **AST 는 `if False:` 로 무력화된 분기와
살아 있는 분기를 구별하지 못한다.**

PR #1027 에서 그 대가를 실측했다 — 기계 변이 55건 중 **생존 20건이 그 맹점 하나**였고,
로컬 3.12 환경을 만들자 **52 kill / 생존 3** 으로 바뀌었다(그중 둘은 진짜 결함이었다).

★그리고 skip 된 락은 **CI 에서 처음 실행**된다. 실제로 CI 가 내 스텁 결함을 **두 번** 잡았다
(`tuple` 로 흉내 낸 SQLAlchemy Row · 호출-횟수로 라우팅하는 스텁).
**skip 은 「통과」가 아니라 「아직 모른다」다.**

【이 락이 하는 일】산문으로 적으면 재발 저수지에 들어간다. 그래서 **다음 인터프리터 스킵도
자동으로** 이 규율에 걸리게, 모집단을 파생시켜 검사한다 — 새 스킵을 만드는 사람은
해법을 함께 적어야 한다.

【해법 · 로컬 3.12 환경 만들기】(2026-09-10 실측 — **GDAL 불필요**)

    /usr/bin/python3.12 -m venv ~/.venvs/propai312
    ~/.venvs/propai312/bin/pip install --upgrade pip
    ~/.venvs/propai312/bin/pip install fastapi 'sqlalchemy[asyncio]' pydantic \
      pydantic-settings bcrypt 'python-jose[cryptography]' pytest pytest-asyncio \
      asyncpg httpx python-multipart email-validator geoalchemy2 structlog

    cd propai-platform/apps/api
    ~/.venvs/propai312/bin/python -m pytest tests/test_site_enter_membership_auth.py -q

★CI 는 GDAL 네이티브까지 깐다(`gdal-bin libgdal-dev`). 위 목록은 **그것 없이**
  `test_site_*`·`test_sales_*` 계열이 도는 최소 집합이다(실측: 27 passed · 68 passed).
  다른 계열은 `No module named 'X'` 를 보고 하나씩 더하면 된다.
★**변이 도구는 `sys.executable` 을 쓴다** — 도구 **자체**를 그 파이썬으로 불러야 한다:

    ~/.venvs/propai312/bin/python scripts/mutate_changed.py --max 400 --tests <경로…>

  이걸 안 하면 3.10 으로 돌아 **라우터 본문 변이가 통째로 생존**한다(실측 20건).
"""
from __future__ import annotations

import ast
import pathlib

TESTS = pathlib.Path(__file__).resolve().parent

# ★해법의 SSOT — 스킵 사유에 이 토큰이 있으면 «로컬에서 어떻게 돌리는지» 를 적은 것이다.
#   경로 하나를 못 박는다(설명이 아니라 **실행 가능한 좌표**여야 한다).
REMEDY_TOKEN = "propai312"


def _files_with_interpreter_skip() -> dict[str, str]:
    """`sys.version_info` 로 건너뛰는 파일 전수 → {파일명: 소스}."""
    found: dict[str, str] = {}
    for path in sorted(TESTS.glob("test_*.py")):
        if path.name == pathlib.Path(__file__).name:
            continue
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Attribute) and node.attr == "version_info"
                    and isinstance(node.value, ast.Name) and node.value.id == "sys"):
                found[path.name] = src
                break
    return found


def test_scanner_is_alive() -> None:
    """★공허 방지 — 조회기가 죽으면 «위반 0» 은 공짜다."""
    pop = _files_with_interpreter_skip()
    assert pop, "인터프리터 스킵이 **한 건도** 안 잡혔다 — 조회기가 죽었다"
    assert "test_site_enter_membership_auth.py" in pop, (
        "알려진 인터프리터 스킵 파일을 못 찾았다 — 축이 죽었다"
    )
    # ★특이도 — 아무 파일이나 잡으면 안 된다(이 파일 자신은 제외되고, 축과 무관한 파일도).
    assert "test_site_lookup_soft_delete_sweep.py" not in pop, (
        "조회기가 `sys.version_info` 없는 파일까지 센다 — 위양성도 결함이다"
    )


def test_every_interpreter_skip_names_how_to_run_it_locally() -> None:
    """★스킵을 보는 사람이 **곧 고치는 법**을 보게 한다.

    ★단언하는 것은 **문구가 아니라 좌표**다 — 실행 가능한 환경 이름 하나(`REMEDY_TOKEN`).
      산문을 못 박으면 다듬을 때마다 깨지는 취약한 락이 된다(저장소 §C-30).
    """
    violations = [
        name for name, src in sorted(_files_with_interpreter_skip().items())
        if REMEDY_TOKEN not in src
    ]
    assert not violations, (
        "인터프리터 때문에 건너뛰는 락이 **고치는 법을 안 달고** 있다 "
        f"(스킵 사유에 `{REMEDY_TOKEN}` 환경을 적어라): " + ", ".join(violations)
    )
