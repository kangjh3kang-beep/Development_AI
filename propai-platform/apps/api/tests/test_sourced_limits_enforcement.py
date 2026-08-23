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
    assert len(MIN_LOT_AREA) >= 10, f"표가 {len(MIN_LOT_AREA)}개뿐이다 — 검증 대상이 없다"
    for code, limit in MIN_LOT_AREA.items():
        assert isinstance(limit, PracticeLimit), f"{code}: 원시 숫자가 다시 들어왔다 — {limit!r}"
        assert limit.basis.strip(), f"{code}: 출처가 비었다"


def test_접도_실무표의_모든_항목이_근거를_갖는다() -> None:
    assert len(ROAD_REQUIREMENT) >= 8, f"표가 {len(ROAD_REQUIREMENT)}개뿐이다"
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
