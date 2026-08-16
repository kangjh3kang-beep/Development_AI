"""`_scan_guard` 자체 시험 — **가드가 실제로 막는지**를 이 세션의 실제 사고로 재현한다.

★"대조군을 강제한다"는 주장은 그 자체가 검증 대상이다. 그래서 오늘 실제로 난 위양성을
  **입력으로 재현**해, 가드가 그것을 잡는지 본다. 잡지 못하면 이 모듈은 장식이다.
"""
from __future__ import annotations

import re

import pytest

from tests._scan_guard import ScannerDeadError, assert_absent, code_lines, scan


def test_양성대조가_0이면_위반0을_믿지_않는다() -> None:
    """★사고 재현 #4 — 404 페이지 청크를 긁어 **대조군까지 0** 이었는데 "하드코딩 0건"으로 읽을 뻔했다."""
    empty_target = "이 안에는 아무것도 없다"
    with pytest.raises(ScannerDeadError, match="검사기가 죽었다"):
        assert_absent(
            empty_target,
            pattern=r"하드코딩된문구",
            positive_control=r"반드시_있어야_하는_것",
            reason="있으면 안 되는 문구",
        )


def test_음성대조가_잡히면_패턴이_아무거나_집는_것이다() -> None:
    noisy = "정상내용 zzz-absent-sentinel-do-not-add 정상내용"
    with pytest.raises(ScannerDeadError, match="음성대조"):
        assert_absent(
            noisy,
            pattern=r"없어야하는것",
            positive_control=r"정상내용",
            reason="…",
        )


def test_부분문자열_위양성은_호출자가_경계를_주면_잡힌다() -> None:
    """★사고 재현 #3·#5 — `매도청구 가능` 이 `매도청구 가능여부` 를, `propai-v` 가 `propai-vitest` 를 집었다.

    가드는 경계를 **대신 정해 주지 않는다**(그건 도메인 지식이다). 대신 대조군을 강제해
    "검사기가 살아 있다"를 먼저 보이게 하고, 경계를 준 패턴이 실제로 갈리는지 확인 가능하게 한다.
    """
    text = "매도청구 가능여부를 제공합니다"   # 정당한 라벨 — 위반이 아니다
    # 경계 없는 패턴은 잡는다(= 위양성 재현)
    r = scan(text, pattern=r"매도청구 가능", positive_control=r"제공합니다")
    assert r.hits, "경계 없는 패턴은 정당한 라벨을 집는다 — 이게 그날의 위양성이었다"
    # 경계를 주면 안 잡힌다(= 교정)
    assert_absent(
        text,
        pattern=r"매도청구 가능(?!여부)",
        positive_control=r"제공합니다",
        reason="하드코딩 '매도청구 가능' 은 instrument 통로로 대체됐어야 한다",
    )


def test_주석은_코드가_아니다() -> None:
    """★사고 재현 #7 — **주석의 예시값**을 상수 선언으로 착각했다."""
    src = (
        "// 형식: propai-v<seq>-<sha>   예) propai-v002612-e527b6e8\n"
        'const CACHE_NAME = "propai-vdev-local";'
    )
    # 주석을 걷어내면 예시값은 사라진다
    stripped = code_lines(src)
    assert "propai-v002612" not in stripped
    assert "propai-vdev-local" in stripped
    # 그 위에서 "손 채번 형태 금지"를 단언하면 주석에 걸려 넘어지지 않는다
    assert_absent(
        stripped,
        pattern=r'const CACHE_NAME = "propai-v\d+-',
        positive_control=r"const CACHE_NAME",
        reason="캐시명은 빌드가 만든다 — 손 채번 형태가 남으면 안 된다",
    )


def test_min_positive_로_대조군_강도를_올릴_수_있다() -> None:
    text = "항목 하나만 있다"
    # 1건이면 통과하지만
    scan(text, pattern=r"없음", positive_control=r"항목", min_positive=1)
    # 규모를 아는 호출자가 하한을 올리면 죽는다(= 더 강한 대조군)
    with pytest.raises(ScannerDeadError):
        scan(text, pattern=r"없음", positive_control=r"항목", min_positive=5)


def test_정규식_객체도_받는다() -> None:
    assert_absent(
        "ABC",
        pattern=re.compile(r"XYZ"),
        positive_control=re.compile(r"ABC"),
        reason="…",
    )
