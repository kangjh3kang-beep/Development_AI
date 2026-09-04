"""조례 기본값은 **법정상한을 넘을 수 없다** — S계층 불변식 + 대조군 건강검사.

【무엇이 뚫렸었나 — 2026-08-19 실측】
조례 파서를 고쳤더니 오산시 자연녹지 건폐율이 `bcr=30, confidence=0.95` 로 나왔다.
**원문 기본값은 제45조①16호 "자연녹지지역: 20퍼센트 이하"** 이고, 30% 는 같은 조례 안의
**조건부 완화값**이었다(제50조 성장관리방안 수립지역 / 제46조 용도지구 지정 / 주유소 등).
파서 모델이 `용도지역 → 값 하나`인데 조례의 실제 구조는 `용도지역 × 조건 → 값들`이다.

★그 30% 가 틀렸다고 안 유일한 이유는 사람이 원문을 눈으로 봤기 때문이다 — 확장되지 않는다.
자연녹지 30% 는 국계법 시행령 상한 20% 를 **넘는 불가능한 값**이므로, 기계가 잡을 수 있었다.

【파생의 축 = ORDINANCE_CACHE / NATIONAL_LIMITS 딕셔너리】
검사 대상을 손으로 적지 않고 **정본 딕셔너리에서 파생**한다. 지자체·용도지역이 추가되면
자동으로 감시망에 들어온다.
"""

from __future__ import annotations

import pytest

from apps.api.app.services.land_intelligence.ordinance_service import (
    NATIONAL_LIMITS,
    ORDINANCE_CACHE,
    enforce_national_ceiling,
)

_PAIRS = [
    (region, zone, key)
    for region, zones in ORDINANCE_CACHE.items()
    for zone, vals in zones.items()
    if zone in NATIONAL_LIMITS
    for key in ("bcr", "far")
    if vals.get(key) is not None and NATIONAL_LIMITS[zone].get(key) is not None
]


def test_전제_대조군이_살아있다():
    """★대조군 건강검사 — 26곳 캐시를 파서 검증의 기준선으로 쓰려면 그 자신이 성해야 한다.

    이 단언이 없으면 아래 파라미터라이즈가 **0건 실행**되고 조용히 통과한다.
    """
    assert len(ORDINANCE_CACHE) >= 20, f"캐시 지자체가 너무 적다: {len(ORDINANCE_CACHE)}"
    assert len(NATIONAL_LIMITS) >= 15, f"법정표가 비었다: {len(NATIONAL_LIMITS)}"
    assert len(_PAIRS) >= 100, f"대조 쌍이 너무 적다: {len(_PAIRS)} — 파생이 깨졌다"


@pytest.mark.parametrize("region,zone,key", _PAIRS)
def test_정적캐시가_법정상한을_넘지_않는다(region: str, zone: str, key: str):
    """캐시 자체가 위반하면 그것은 **대조군이 아니라 오염원**이다."""
    got = ORDINANCE_CACHE[region][zone][key]
    ceiling = NATIONAL_LIMITS[zone][key]
    assert got <= ceiling, (
        f"{region}/{zone}/{key}: 조례 {got} > 법정 {ceiling} — "
        f"조례는 국계법 §77·78에 따라 법정범위 안에서 정한다"
    )


class TestGuard:
    def test_법정초과_기본값은_기각된다(self):
        # 실제로 났던 값: 자연녹지 bcr=30 (법정 20)
        bcr, far, viol = enforce_national_ceiling("자연녹지지역", 30, 100)
        assert bcr is None, "법정초과 건폐율이 통과했다 — 오늘의 결함이 그대로다"
        assert far == 100, "위반하지 않은 항목까지 함께 버리면 정보 손실이다"
        assert viol and "30" in viol[0] and "20" in viol[0], "기각 사유가 값과 상한을 담아야 한다"

    def test_클램프하지_않는다(self):
        """법정값으로 깎아 내리면 **출처 없는 그럴듯한 숫자**가 생긴다(날조)."""
        bcr, _, _ = enforce_national_ceiling("자연녹지지역", 30, None)
        assert bcr is not NATIONAL_LIMITS["자연녹지지역"]["bcr"], "법정값으로 대체하면 날조다"
        assert bcr is None

    def test_대조군_정상값은_그대로_통과한다(self):
        """★없으면 위 단언들이 '무엇이든 기각한다'로도 통과한다."""
        bcr, far, viol = enforce_national_ceiling("자연녹지지역", 20, 100)
        assert (bcr, far) == (20, 100)
        assert viol == []

    def test_대조군_경계값은_위반이_아니다(self):
        """`>` 가 `>=` 로 바뀌면 정상 조례(상한과 동일)를 전부 기각한다 — 위양성도 결함이다."""
        nat = NATIONAL_LIMITS["제2종일반주거지역"]
        bcr, far, viol = enforce_national_ceiling("제2종일반주거지역", nat["bcr"], nat["far"])
        assert (bcr, far) == (nat["bcr"], nat["far"])
        assert viol == []

    def test_대조군_미등재_용도지역은_통과시킨다(self):
        """법정표에 없는 세분 표기(제2종일반주거지역(7층이하) 등)를 기각하면 정상값을 잃는다."""
        bcr, far, viol = enforce_national_ceiling("존재하지않는용도지역", 999, 9999)
        assert (bcr, far) == (999, 9999) and viol == []

    def test_대조군_None은_건드리지_않는다(self):
        assert enforce_national_ceiling("자연녹지지역", None, None) == (None, None, [])


# ─────────────────────────────────────────────────────────────────────────────
# ★부채를 초록 안에 보이게 남긴다(커밋 메시지에만 적으면 드러나지 않는다).
#   2026-08-19 변이감사 실측 — 아래 줄들이 **무잠금**이다(고쳤으나 검증 안 됨):
#     · `_locate_section` 헤더 정규식('안' 옵셔널)  — ordinance_service.py:808
#     · 조제목 우선 앵커(상호참조 회피)             — :813-814
#     · 법정초과 시 신뢰도 0.3 강등                 — :731-732
#   전부 `_parse_bcr_far_from_text` 안에서만 관측되는데, 그 함수는 조례 XML 원문을
#   요구한다. 라이브 법제처 호출은 테스트에 두지 않으므로 **픽스처가 있어야 잠긴다.**
#   ※ "미수정"이 아니라 "수정했으나 무잠금"이다 — 리뷰어가 안전하다고 오독하지 않도록 구분.
# ─────────────────────────────────────────────────────────────────────────────


def test_todo_파서본체_픽스처_확보():
    """오산시 조례(ID 2097518) 원문을 픽스처로 고정해 파서 본체를 잠근다.

    잠글 것(그라운드 트루스는 원문 실측으로 확보됨):
      · 제45조① 기본 건폐율 자연녹지 **20%** (현재 파서는 조건부 30% 를 집어 기각당함)
      · 제51조① 기본 용적률 자연녹지 **100%** (현재 통과)
      · 조제목 앵커가 제34조 상호참조가 아니라 **제45조**를 잡는지
      · '안' 없는 표기("용도지역에서의")에서 섹션이 잡히는지
      · 법정초과 기각 시 신뢰도가 0.3 이하로 내려가는지
    """
    import pytest as _pt
    _pt.skip("부채: 조례 원문 픽스처 미확보 — 다음 단계에서 확보 후 이 skip 을 제거한다")
