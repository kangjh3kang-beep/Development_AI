"""`land_analysis` 과금 판정 잠금 — 성공을 증명하지 못하면 과금하지 않는다.

★왜 (2026-08-16 원장 실측):
  `routers/auto_zoning.py` 는 `result` 를 **한 번도 보지 않고** 2,000원을 청구했다.
  `billing/ledger` 실측 — `land_analysis` **18건 · 36,000원**, 사람이 낼 수 없는 간격 군집:
      2026-08-15 12:27:21 · 12:29:17              (116초)
      2026-08-02 22:12:49 · 22:13:42 · 22:15:00   ( 53초 ·  78초)
      2026-07-22 05:49:41 · 05:49:57 · 05:51:30   ( 16초 ·  93초)
  등기(`registry_issue` 4건·4,800원)와 **같은 결함 클래스**이고 금액은 7.5배다.

★픽스처 규율(CLAUDE.md): 두 모집단을 **가른다**. 각 케이스는 성공 픽스처에서 **판정 대상
  필드 하나만** 바꾼다 — 차가 0인 픽스처는 잠금이 아니다.

★배선 규율: 판정 함수만 잠그면 라우트가 그것을 **부르지 않아도** 초록이다(이 저장소에서
  실증된 함정: 순수 판정은 태우고 집행부는 스텁으로 치운다). 아래 배선 락이 그 구멍을 막는다.
"""

import re
from pathlib import Path

import pytest

from app.services.zoning.auto_zoning_service import land_analysis_charged

# 실조회 성공 — 이 픽스처에서 필드 하나씩만 바꿔 대조군을 만든다.
SUCCESS = {
    "pnu": "1168010100107360000",
    "zone_type": "일반상업지역",
    "zone_source": "vworld",
    "zone_limits": {"max_bcr": 80, "max_far": 800},
}


def test_실조회_성공은_과금한다():
    assert land_analysis_charged(SUCCESS) is True


@pytest.mark.parametrize(
    "field,value,why",
    [
        ("cached", True, "캐시 적중은 신규 분석이 아니다(등기가 이 순서로 당했다)"),
        ("pnu", None, "PNU 부재 = 필지 실조회 자체가 없었다"),
        ("pnu", "", "빈 문자열도 실조회 없음"),
        ("zone_type", None, "용도지역 미확정 = 산출물 없음"),
        ("zone_source", "keyword_inference", "추론값임을 사용자에게 고지하고 실조회가로 청구할 수 없다"),
    ],
)
def test_실패_모집단은_과금하지_않는다(field, value, why):
    """★성공 픽스처에서 **이 필드 하나만** 바꾼다 — 두 모집단의 차가 그 필드뿐이어야
    이 케이스가 그 필드의 배선을 잠근다."""
    bad = {**SUCCESS, field: value}
    assert land_analysis_charged(bad) is False, why
    # 대조: 같은 픽스처에서 그 필드만 되돌리면 True 여야 한다(차가 0이 아님을 증명).
    assert land_analysis_charged(SUCCESS) is True


def test_dict_이_아니면_과금하지_않는다():
    for junk in (None, "", [], 0, "ok"):
        assert land_analysis_charged(junk) is False


def _router_source_without_comments() -> str:
    """주석·독스트링을 걷어낸 라우터 소스.

    ★소스 검사는 주석에 뚫린다(이 저장소에서 배선 락 38개가 그렇게 관통됐다).
      줄 주석과 블록 주석/독스트링을 **둘 다** 벗긴다 — 한쪽만 벗기면 나머지로 우회된다.
    """
    p = Path(__file__).resolve().parents[1] / "routers" / "auto_zoning.py"
    src = p.read_text(encoding="utf-8")
    src = re.sub(r'"""(?:.|\n)*?"""', "", src)   # 독스트링/블록
    src = re.sub(r"'''(?:.|\n)*?'''", "", src)
    src = re.sub(r"(?m)#.*$", "", src)            # 줄 주석
    return src


def test_배선_락_판정을_거치지_않고는_청구할_수_없다():
    """★공허하지 않다: 두 단언이 **함께** 있어야 의미가 있다.

    ① 청구 호출이 실제로 존재한다(사라져서 통과하는 것이 아님을 보장)
    ② 그 청구가 `land_analysis_charged` 게이트 뒤에 있다
    """
    src = _router_source_without_comments()

    charge_calls = re.findall(r'charge_service\([^)]*"land_analysis"', src)
    assert charge_calls, "청구 호출 자체가 사라졌다 — 이 락은 청구가 있을 때만 의미가 있다"

    assert "land_analysis_charged(result)" in src, (
        "라우트가 공용 판정을 거치지 않는다 — 판정 함수만 잠그면 라우트가 그것을 "
        "부르지 않아도 초록이 된다(실증된 함정)"
    )
    # 게이트와 청구가 같은 블록에 있어야 한다(판정을 부르고 결과를 버리면 무의미).
    gated = re.search(
        r"if\s+uid\s+and\s+land_analysis_charged\(result\)\s*:(?:.|\n){0,600}?"
        r'charge_service\([^)]*"land_analysis"',
        src,
    )
    assert gated, "판정은 호출하는데 청구가 그 가드 안에 없다"


@pytest.mark.skip(
    reason="★부채(초록 안에 보이게 남김) — 동일 주소 재청구는 이 판정으로 막히지 않는다. "
    "원장 군집(16초·41초·53초 간격)은 **둘 다 성공한 실조회**라 화이트리스트를 통과한다. "
    "서버 결과 캐시 또는 (사용자·주소) 중복창이 필요하고 TTL·창 길이는 제품 결정이다."
)
def test_동일_주소_재청구를_막는다():
    raise AssertionError("미구현 — 중복창/캐시 설계 후 활성화")
