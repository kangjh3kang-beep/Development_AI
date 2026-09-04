"""★부재 단언은 **그 자체로 잠금이 아니다** — 같은 실행에 양성 짝을 요구한다.

【왜 이 감사기가 있나 — 2026-08-20/21 실측】
`assert x is None` · `assert not …` · `== []` 같은 **부재 단언만** 있는 테스트는,
검증 대상 함수가 **통째로 고장 나 항상 빈 값을 내도 통과**한다. 이 저장소가 반복해서
데인 "공허한 초록"의 사촌이다.

실제로 이 세션에서 두 세션이 **독립적으로** 같은 결론에 도달했다:
· 나 — `"첨부파일" not in disclaimer` 만 단언했더니 **정상 경로 문구가 망가져도 통과**했다
  (변이가 잡았다). 음성 쪽도 **옳은 문구**를 요구하도록 고쳤다.
· 다른 세션 — 여러 줄 문구에서 한 단어만 보다가 같은 형태로 데이고 고쳤다.

★일반형: **부재 단언은 같은 실행에서 "올바른 상태가 실제로 성립함"을 함께 단언해야
비로소 잠금이 된다.** 그러지 않으면 "아무것도 안 하는 구현"이 전부 통과한다.

【이 감사기가 하는 일】
이 캠페인이 만든 테스트 파일들을 파싱해, **부재 단언만 있고 양성 단언이 하나도 없는**
테스트 함수를 찾아 실패시킨다. 한 번 고치고 끝나면 다시 쌓이므로 회귀망에 둔다.

★목록형이 아니라 **파일 목록에서 파생**한다 — 새 테스트가 그 파일에 추가되면 자동으로
감시망에 들어온다(사람이 센 목록은 곧 상한이 된다).
"""

import ast
import pathlib
import re

import pytest

# 이 캠페인이 만든 "정직 신호" 계열 스위트 — 부재 단언이 특히 많은 곳이다.
GUARDED = (
    "test_growth_management_regime_split",
    "test_scenario_unresolved_parcels",
    "test_conditional_legal_ceiling",
    "test_plan_limit_unknown",
    "test_ordinance_conditional_match",
    "test_ordinance_attachment_only",
    "test_upzoning_label_value_coherence",
)

_NEG = re.compile(r"assert\s+not\b|not in |is None|==\s*\[\]|==\s*None")

_TESTS_DIR = pathlib.Path(__file__).parent


def _assert_lines(src: str, fn: ast.FunctionDef) -> list[str]:
    lines = src.splitlines()[fn.lineno - 1 : fn.end_lineno]
    return [x.strip() for x in lines if x.strip().startswith("assert")]


def test_premise_guarded_files_exist_and_have_absence_assertions():
    """전제 — 감시 대상 파일이 실재하고 **부재 단언을 실제로 담고** 있어야 감사가 의미를 갖는다."""
    found, neg_total = 0, 0
    for name in GUARDED:
        p = _TESTS_DIR / f"{name}.py"
        assert p.exists(), f"감시 대상이 사라졌다: {name}(이름이 바뀌면 감사가 조용히 0건이 된다)"
        found += 1
        neg_total += len(_NEG.findall(p.read_text(encoding="utf-8")))
    assert found == len(GUARDED)
    assert neg_total >= 20, f"부재 단언이 {neg_total}건뿐 — 감사 대상이 없어 공허해진다"


@pytest.mark.parametrize("name", GUARDED)
def test_no_absence_only_test_functions(name: str):
    """★부재 단언만 있는 테스트 함수가 없어야 한다."""
    src = (_TESTS_DIR / f"{name}.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    offenders = []
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        if not fn.name.startswith("test_"):
            continue
        asserts = _assert_lines(src, fn)
        if not asserts:
            continue
        positives = [a for a in asserts if not _NEG.search(a)]
        if not positives:
            offenders.append(fn.name)

    assert not offenders, (
        f"{name}: 부재 단언만 있는 테스트 — {offenders}. "
        "검증 대상이 통째로 고장 나 항상 빈 값을 내도 통과한다. "
        "같은 실행에서 '올바른 상태가 실제로 성립함'을 함께 단언하라."
    )


def test_the_auditor_itself_is_not_vacuous():
    """★감사기가 실제로 잡을 수 있는지 — 합성 위반으로 확인한다(면역 거짓 주장 방지)."""
    bad = "def test_x():\n    assert foo() is None\n"
    tree = ast.parse(bad)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef))
    asserts = _assert_lines(bad, fn)
    assert asserts, "합성 샘플에서 assert 를 못 뽑았다 — 감사기가 아무것도 안 보고 있다"
    assert not [a for a in asserts if not _NEG.search(a)], "감사기가 위반을 위반으로 못 본다"

    good = "def test_y():\n    assert foo() is None\n    assert bar() == 1\n"
    tree2 = ast.parse(good)
    fn2 = next(n for n in ast.walk(tree2) if isinstance(n, ast.FunctionDef))
    asserts2 = _assert_lines(good, fn2)
    assert [a for a in asserts2 if not _NEG.search(a)], "감사기가 정상 케이스를 위반으로 신고한다(위양성)"
