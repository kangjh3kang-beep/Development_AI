"""PNU 유효성 판정은 **한 곳**이다 — 손수 길이 검사를 금지하는 파생형 래칫.

## 왜 생겼나 (2026-09-02 실측)

`app/utils/pnu.py` 는 스스로를 *"프론트 `apps/web/lib/pnu.ts` 의 **백엔드 미러**"* 라 선언하는데
`is_valid_pnu` 의 **프로덕션 소비처가 0** 이었다(자기 파일과 자기 테스트뿐).
같은 판정을 손으로 쓴 자리가 **18벌**이었고 **옳은 것은 2벌**이었다:

    단방향 10벌   `len(pnu) < 19` · `>= 19`   → ★**26자 오염값이 통과**한다
    길이만  6벌   `len(pnu) == 19`            → ★**19자 비숫자가 통과**한다
    정확     2벌   `!= 19 or not isdigit()`

★단방향은 이 저장소가 이미 배운 것의 **거울상**이다 — 회귀망 §D-19
*"경계를 걸면 양방향으로 걸어라. 상한만 걸었더니 하한이 0으로 붕괴했다"*. 여기서는 **하한만** 걸었다.

통과 직후 무엇을 하는지가 문제다 — **자르거나 외부로 보낸다**:
`sigungu_cd = pnu[:5]` · `sgg, bjd = pnu[:5], pnu[5:10]` · `vworld.get_land_info(pnu)`.
라이브 오염값 `'store-rep-용인시 수지구 신봉동 56-1'`(**26자**)은 `< 19` 가드를 통과해
`sigungu_cd = "store"` 를 만들고, 그것이 **건축물대장 API 로 나간다.**

## 이 락이 잠그는 것

1. **손수 길이 검사 0건** — `ast` 로 `len(<pnu…>) <op> 19` 를 **파생 수집**한다(손 목록 아님).
2. **★공허진리 방지** — 모집단이 0 이 되면 «위반 0» 이 참이 되므로 `is_valid_pnu` **호출부 하한**을
   함께 단언한다. 배선을 통째로 지우면 이쪽이 빨개진다.
3. **판정 자체** — 두 구멍(단방향·길이만)을 **서로 다른 입력**으로 가른다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from apps.api.app.utils.pnu import is_valid_pnu

API_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _py_files() -> list[pathlib.Path]:
    out = []
    for p in API_ROOT.rglob("*.py"):
        s = str(p)
        if "/tests/" in s or p.name.startswith("test_") or "/.venv/" in s or "/migrations/" in s:
            continue
        out.append(p)
    return out


def _hand_rolled_length_guards() -> list[tuple[str, int, str]]:
    """`len(<pnu 를 언급하는 식>) <비교> 19` 를 **파생 수집**한다."""
    hits: list[tuple[str, int, str]] = []
    for p in _py_files():
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:  # ★못 읽으면 조용히 0 으로 세지 않는다 — 시끄럽게 실패시킨다.
            pytest.fail(f"파싱 불가로 판정할 수 없다: {p}")
        for n in ast.walk(tree):
            if not (isinstance(n, ast.Compare) and isinstance(n.left, ast.Call)):
                continue
            f = n.left.func
            if not (isinstance(f, ast.Name) and f.id == "len"):
                continue
            expr = ast.unparse(n)
            if "pnu" not in expr.lower():
                continue
            if any(isinstance(c, ast.Constant) and c.value == 19 for c in n.comparators):
                hits.append((str(p.relative_to(API_ROOT)), n.lineno, expr[:90]))
    return hits


def _is_valid_pnu_call_sites() -> list[str]:
    """`is_valid_pnu(...)` 를 **호출**하는 프로덕션 파일(정의 파일 제외)."""
    out: list[str] = []
    for p in _py_files():
        if p.name == "pnu.py" and p.parent.name == "utils":
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            pytest.fail(f"파싱 불가로 판정할 수 없다: {p}")
        for n in ast.walk(tree):
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "is_valid_pnu"
            ):
                out.append(str(p.relative_to(API_ROOT)))
                break
    return out


class Test판정은한곳이다:
    def test_손수_길이검사가_남아있지_않다(self):
        hits = _hand_rolled_length_guards()
        assert hits == [], (
            "PNU 길이를 손으로 재는 자리가 남았다 — `is_valid_pnu` 를 쓸 것.\n"
            "★`< 19`·`>= 19` 는 **하한만** 걸어 26자 오염값을 통과시키고,\n"
            "  `== 19` 는 숫자를 안 봐 19자 비숫자를 통과시킨다.\n"
            + "\n".join(f"  {f}:{ln}  {e}" for f, ln, e in hits)
        )

    def test_공허진리_방지_배선이_실재한다(self):
        """★모집단이 0 이면 위 단언은 참이 된다 — 소비처 하한을 따로 못 박는다."""
        sites = _is_valid_pnu_call_sites()
        # 2026-09-02 배선 시점 실측 11파일. 아래로 내려가면 배선이 걷힌 것이다.
        assert len(sites) >= 11, (
            f"`is_valid_pnu` 소비처가 {len(sites)}개다 — 배선이 걷혔다.\n"
            "★이 하한이 없으면 위 「손수 검사 0건」이 **모집단 0** 으로도 참이 된다.\n"
            + "\n".join(f"  {s}" for s in sorted(sites))
        )

    def test_수집기가_살아있다_대조군(self):
        """★조회기 생존 — 일부러 넣은 손수 검사가 **잡히는지** 본다(없으면 위 0건이 무의미)."""
        src = "def f(pnu):\n    if len(pnu) < 19:\n        return None\n"
        tree = ast.parse(src)
        found = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Compare)
            and isinstance(n.left, ast.Call)
            and isinstance(n.left.func, ast.Name)
            and n.left.func.id == "len"
            and "pnu" in ast.unparse(n).lower()
            and any(isinstance(c, ast.Constant) and c.value == 19 for c in n.comparators)
        ]
        assert len(found) == 1, "수집기가 죽었다 — 위 「위반 0건」은 근거가 아니다"


class Test두구멍을다른입력으로가른다:
    """★단방향 구멍과 길이만 구멍은 **서로 다른 입력**으로 드러난다 — 하나로 뭉치면
    한쪽만 고쳐도 초록이다."""

    def test_구멍A_하한만_걸면_통과하던_값(self):
        # 라이브 실측 오염값 — 26자라 `len(pnu) < 19` 를 **통과**했다.
        bad = "store-rep-용인시 수지구 신봉동 56-1"
        assert len(bad) >= 19, "픽스처가 옛 단방향 가드를 통과하지 못하면 이 케이스는 공허하다"
        assert is_valid_pnu(bad) is False

    def test_구멍B_길이만_보면_통과하던_값(self):
        # 19자이지만 숫자가 아니다 — `len(pnu) == 19` 를 **통과**했다.
        bad = "413701100010467000a"
        assert len(bad) == 19, "픽스처가 옛 길이 가드를 통과하지 못하면 이 케이스는 공허하다"
        assert is_valid_pnu(bad) is False

    def test_음성대조_진짜는_통과한다(self):
        """★모두 False 를 주는 죽은 검사기와 구별한다."""
        assert is_valid_pnu("4137011000104670001") is True
        assert is_valid_pnu(" 4137011000104670001 ") is True  # 공백은 정규화된다

    def test_경계_양방향(self):
        """★§D-19 — 경계는 한 쌍이다. 18자·20자 **둘 다** 막는다."""
        assert is_valid_pnu("4" * 18) is False
        assert is_valid_pnu("4" * 20) is False
        assert is_valid_pnu("4" * 19) is True
