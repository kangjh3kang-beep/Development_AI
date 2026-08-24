"""값에는 근거가 있어야 하고, **근거의 성격이 판정 강도를 정한다** (2026-08-23 · 형제 스윕).

## 무엇이 있었나

`#760` 이 `MAX_FLOORS = {"M10": 3}` 의 근거 없는 3층을 걷어냈다. 그런데 **같은 파일의
형제 두 표**는 그대로였다 — `MIN_LOT_AREA`(15항) · `ROAD_REQUIREMENT`(10항).
둘 다 원시 숫자였고, 둘 다 `is_blocking=True` 로 개발유형을 화면에서 죽인다
(`ComprehensiveAnalysisPanel.tsx:1154` — `부적합` 이면 행이 `opacity-50` 으로 흐려진다).

## 라이브 실측 (2026-08-23 · 168 컨테이너 `propai-v002723-06551957`)

    4,000㎡ 아파트 부지(M01)  → **부적합** · blocking `4000m² < 5000m² (최소) — 면적 부족`
    M03 도로폭 3m·접도 1m     → **"접도 제한 없음" 통과**

★**한 뿌리의 양면이다.** 표에 있으면 근거 없이 **죽이고**(과대거절),
표에 없으면 근거 없이 **살린다**(과소검출). 5,000㎡ 의 근거를 코드가 대지 못하고,
접도 1m 는 건축법 §44① 의 2m 에도 못 미친다.

## 이 파일이 잠그는 것

1. 두 표의 모든 항목이 **근거를 지닌 타입**이다(원시 숫자 재유입 차단)
2. 실무 기준(`PracticeLimit`)은 **부적합을 낼 수 없다** — `조건부` 까지
3. 법정(`LegalLimit`)은 여전히 **부적합을 낸다**(대조군 — 위 락은 아무것도 안 막는 구현에서도 초록)
4. **미등재는 "제한 없음"이 아니다** — `unknown`
5. 접도 법정선은 **연면적**을 키로 삼는다(유형 표의 부재가 규제의 부재가 아니다)
6. 라이브 두 증상이 실제로 뒤집혔는지(회귀 방지)
"""

from __future__ import annotations

import pytest

from app.services.legal.legal_limit import (
    LegalLimit,
    MissingLegalBasisError,
    PracticeLimit,
)
from app.services.zoning.development_feasibility_validator import (
    MIN_LOT_AREA,
    ROAD_FRONTAGE_STATUTE,
    ROAD_REQUIREMENT,
    ROAD_STRICT_GFA_THRESHOLD_SQM,
    ROAD_STRICT_STATUTE,
    _check_lot_area,
    _check_road,
)

# ── 1. 타입 계약 ────────────────────────────────────────────────────────────


def test_출처_없이는_실무기준을_만들_수_없다() -> None:
    """★`LegalLimit` 과 같은 규율 — 숫자만 넣는 길이 존재하지 않는다."""
    for bad in ("", "   ", None):
        with pytest.raises((MissingLegalBasisError, TypeError)):
            PracticeLimit(5000, source=bad)  # type: ignore[arg-type]


def test_출처가_있으면_만들어진다_대조군() -> None:
    """★위 락은 *무엇이든 거부하는* 타입에서도 초록이다. 정상 경로를 함께 본다."""
    ok = PracticeLimit(5000, source="플랫폼 실무기준", note="권장 최소 사업규모")
    assert ok.value == 5000
    assert not ok.unlimited
    assert ok.basis == "플랫폼 실무기준"


def test_강제력이_타입으로_갈린다() -> None:
    """★핵심 계약 — 소비처가 문자열이 아니라 **타입**을 보고 판정 강도를 정한다."""
    assert LegalLimit(2, law="건축법 §44①").enforceable is True
    assert PracticeLimit(4, source="플랫폼 실무기준").enforceable is False


# ── 2. 표가 근거를 지닌다 ───────────────────────────────────────────────────


def test_최소대지면적_표의_모든_항목이_근거를_갖는다() -> None:
    # ★공허 진리 방지 — 표가 비면 '위반 0'은 아무 의미가 없다.
    # ★★대역(`>= 10`)이 아니라 **실제 집합**에 결속한다. 변이 검증에서 한 줄(5항)을 지워도
    #   `>= 10` 이 여전히 참이라 생존했다 — 하한이 실제 개수와 같으면 잠금이 아니다.
    assert set(MIN_LOT_AREA) == {f"M{n:02d}" for n in range(1, 16)}, (
        f"표의 구성이 바뀌었다: {sorted(MIN_LOT_AREA)} — 유형을 더하거나 뺐다면 이 케이스를 갱신하라"
    )
    for code, limit in MIN_LOT_AREA.items():
        assert isinstance(limit, PracticeLimit), f"{code}: 원시 숫자가 다시 들어왔다 — {limit!r}"
        assert limit.basis.strip(), f"{code}: 출처가 비었다"


def test_접도_실무표의_모든_항목이_근거를_갖는다() -> None:
    # ★위와 같은 이유로 실제 집합에 결속한다(한 줄 삭제가 대역 하한을 빠져나갔다).
    assert set(ROAD_REQUIREMENT) == {
        "M01", "M02", "M06", "M07", "M08", "M09", "M10", "M11", "M12", "M13",
    }, f"표의 구성이 바뀌었다: {sorted(ROAD_REQUIREMENT)}"
    for code, req in ROAD_REQUIREMENT.items():
        for key in ("road_width", "frontage"):
            limit = req[key]
            assert isinstance(limit, PracticeLimit), f"{code}.{key}: 원시 숫자 — {limit!r}"
            assert limit.basis.strip(), f"{code}.{key}: 출처가 비었다"


def test_접도_법정선은_조문을_지닌다() -> None:
    assert isinstance(ROAD_FRONTAGE_STATUTE, LegalLimit)
    assert "건축법" in ROAD_FRONTAGE_STATUTE.law
    assert ROAD_FRONTAGE_STATUTE.value == 2, "건축법 §44① 의 2m 가 바뀌었다"
    for key in ("road_width", "frontage"):
        assert isinstance(ROAD_STRICT_STATUTE[key], LegalLimit)
        assert "시행령" in ROAD_STRICT_STATUTE[key].law
    # ★상수에 결속 — 대역(`> 1000`)만 보면 상수가 장식이 된다.
    assert ROAD_STRICT_GFA_THRESHOLD_SQM == 2000


# ── 3. 판정 강도 ────────────────────────────────────────────────────────────


def test_실무기준_미달은_부적합이_아니다() -> None:
    """★라이브 회귀 방지 — 4,000㎡ 아파트가 근거 없이 화면에서 죽던 것.

    5,000㎡ 는 어느 법에서도 오지 않았다. 법정 최소대지면적은 **용도지역** 기준이다
    (건축법 §57·시행령 §80 및 조례).
    """
    c = _check_lot_area("M01", 4000)
    assert c.status == "conditional", f"실무 권장치 미달이 {c.status} 로 나왔다: {c.detail}"
    assert c.is_blocking is False, "실무 기준이 개발유형을 죽이고 있다"
    assert "법정" in c.detail, "실무 기준임을 화면이 알 수 없다"


def test_법정_접도_위반은_부적합이다_대조군() -> None:
    """★위 락은 *아무것도 막지 않는* 구현에서도 초록이다. 법정선이 살아 있는지 본다."""
    c = _check_road("M03", road_width=3, road_frontage=1, total_gfa=7500)
    assert c.status == "fail", f"접도 1m 가 {c.status} 로 통과했다: {c.detail}"
    assert c.is_blocking is True
    assert "건축법" in c.detail, "부적합 사유에 근거(조문)가 없다"


def test_실무_권장_접도_미달은_조건부까지다() -> None:
    """법정선(2m)은 넘고 권장치(4m)에 못 미치는 구간 — 위법이 아니다."""
    c = _check_road("M10", road_width=3, road_frontage=2, total_gfa=300)
    assert c.status == "conditional", f"{c.status}: {c.detail}"
    assert c.is_blocking is False
    assert "권장" in c.detail


# ── 4. 미등재는 '제한 없음'이 아니다 ────────────────────────────────────────


def test_최소면적_미등재는_제한없음으로_위장하지_않는다() -> None:
    c = _check_lot_area("M99", 1000)
    assert c.status == "unknown", f"미등재 유형이 {c.status} 로 나왔다: {c.detail}"
    assert "미확인" in c.detail


def test_접도_실무표_미등재라도_법정선은_적용된다() -> None:
    """★라이브 회귀 방지 — 표에 없는 유형(M03)이 접도 1m 로 통과하던 것.

    법정 접도 규정은 **연면적**을 키로 삼으므로 유형 표의 부재가 규제의 부재가 아니다.
    """
    # 표에 없는 유형이지만 법정선 미달 → 부적합
    bad = _check_road("M03", road_width=5, road_frontage=1, total_gfa=500)
    assert bad.status == "fail", f"미등재 유형의 접도 1m 가 {bad.status}: {bad.detail}"
    assert "건축법 §44①" in bad.detail

    # 표에 없고 법정선은 충족 → 통과하되 **미등재 사실을 드러낸다**
    ok = _check_road("M03", road_width=5, road_frontage=3, total_gfa=1000)
    assert ok.status == "pass"
    assert "미등재" in ok.detail, "실무 권장치가 없다는 사실이 침묵됐다"


def test_연면적_문턱이_실제로_판정을_가른다() -> None:
    """★두 모집단이 **다른 값**을 내야 배선이 잠긴다 — 문턱 위·아래를 함께 본다."""
    over = _check_road("M01", road_width=5, road_frontage=4, total_gfa=ROAD_STRICT_GFA_THRESHOLD_SQM)
    under = _check_road("M01", road_width=5, road_frontage=4, total_gfa=ROAD_STRICT_GFA_THRESHOLD_SQM - 1)
    assert over.status == "fail", f"문턱 이상인데 강화규정이 안 걸렸다: {over.detail}"
    assert "시행령" in over.detail
    assert under.status != "fail", f"문턱 미만인데 부적합이 됐다: {under.detail}"


def test_접도_데이터_미확인은_그대로_unknown() -> None:
    """회귀 방지 — 데이터가 없을 때 법정 판정을 지어내지 않는다."""
    c = _check_road("M01", road_width=None, road_frontage=None, total_gfa=8000)
    assert c.status == "unknown"


# ── 5. 변이 검증이 드러낸 구멍 (2026-08-23 · 생존 17건 트리아지) ─────────────
#
# 아래는 **설명할 수 없는 생존**을 잠근 것이다. 변이 도구가 지운·바꾼 자리마다
# "그래도 초록"이면 그 줄은 아무도 안 보고 있다는 뜻이다.


def test_실무기준_문자열_표현이_출처를_드러낸다() -> None:
    """★`LegalLimit.__str__` 은 잠겨 있는데 `PracticeLimit.__str__` 은 아니었다(비대칭).

    화면·로그가 이 문자열을 그대로 싣는다 — 출처가 빠지면 관행값이 법정값처럼 읽힌다.
    """
    got = str(PracticeLimit(4, source="플랫폼 실무기준", note="권장 도로폭"))
    assert "4" in got and "플랫폼 실무기준" in got and "권장 도로폭" in got, got
    # 값이 없을 때는 '제한 없음'(법정 표현)이 아니라 '기준 없음'이어야 한다.
    assert "기준 없음" in str(PracticeLimit(None, source="플랫폼 실무기준"))


def test_출처_누락_오류가_무엇을_요구하는지_말한다() -> None:
    """★오류 메시지는 다음 사람이 읽는 유일한 안내다 — 비어 있으면 규율이 전달되지 않는다."""
    with pytest.raises(MissingLegalBasisError) as e:
        PracticeLimit(5000, source="")
    msg = str(e.value)
    # ★두 절반을 각각 본다 — 한쪽만 보면 같은 낱말이 다른 줄에 있어 변이가 빠져나간다(실증).
    assert "출처가 없다" in msg, msg          # 무엇이 잘못됐나
    assert "어디서 온 값" in msg, msg          # 무엇을 하라는 건가
    assert "5000" in msg, msg                 # 어느 값인가


def test_법정접도_단서의_존재가_고지된다() -> None:
    """★건축법 §44① 에는 단서(예외)가 있다. 그 사실을 지우면 화면이 단정적으로 거짓말한다."""
    assert "단서" in ROAD_FRONTAGE_STATUTE.note, ROAD_FRONTAGE_STATUTE.note


def test_실무_권장_접도_미달이_법정이_아님을_밝힌다() -> None:
    """★값과 라벨은 한 쌍 — `조건부` 로 낮췄어도 이유가 안 보이면 사용자는 위법으로 읽는다."""
    c = _check_road("M10", road_width=3, road_frontage=2, total_gfa=300)
    assert "법정" in c.detail and "아님" in c.detail, c.detail


def test_권장최소_미달_사유에_기준값과_성격이_함께_실린다() -> None:
    c = _check_lot_area("M01", 4000)
    assert "권장 최소" in c.detail, c.detail
    assert "5000" in c.detail, "미달 기준값이 사라졌다 — 사용자가 얼마나 모자란지 알 수 없다"


def test_대지면적_통과_사유가_비지_않는다() -> None:
    """★통과 경로의 설명은 아무도 안 본다 — 그래서 비어도 초록이었다(변이 생존 2건)."""
    ok = _check_lot_area("M01", 6000)
    assert ok.status == "pass"
    assert "6000" in ok.detail and "5000" in ok.detail, ok.detail


def test_규범표는_전부_근거를_지닌_타입이다_전수() -> None:
    """★목록형이 아니라 **전수형** — 이 모듈에 새 규범 표가 생기면 자동으로 감시망에 든다.

    `SourcedLimit`(= `LegalLimit | PracticeLimit`)을 **실제로 소비**하는 유일한 자리이기도 하다.
    선언만 하고 아무도 안 읽으면 그것이 이 저장소가 반복해 데인 '소비처 0' 이다.
    """
    import typing

    from app.services.legal.legal_limit import SourcedLimit
    from app.services.zoning import development_feasibility_validator as V

    allowed = typing.get_args(SourcedLimit)
    assert set(allowed) == {LegalLimit, PracticeLimit}

    # 규범 판정에 쓰이는 표 — 값이 숫자면 반드시 근거를 지닌 타입이어야 한다.
    tables = {"MIN_LOT_AREA": V.MIN_LOT_AREA, "MAX_FLOORS": V.MAX_FLOORS}
    checked = 0
    for name, table in tables.items():
        assert table, f"{name} 이 비었다 — 공허한 초록"
        for code, limit in table.items():
            assert isinstance(limit, allowed), f"{name}[{code}]: 원시 값이 들어왔다 — {limit!r}"
            assert limit.basis.strip(), f"{name}[{code}]: 근거가 비었다"
            checked += 1
    for code, req in V.ROAD_REQUIREMENT.items():
        for key, limit in req.items():
            assert isinstance(limit, allowed), f"ROAD_REQUIREMENT[{code}][{key}]: {limit!r}"
            checked += 1
    # ★공허 진리 가드 — 대상 수가 무너지면 '위반 0'은 아무 뜻이 없다.
    assert checked >= 35, f"검사 대상이 {checked}개뿐이다"
