"""도급단가의 **포함 범위** 서술을 코드에 결속한다 — `#913` 의 소방 제거가 여기에 달려 있다.

## 왜

`#913` 은 「소방시설부담금」 `3,500원/㎡` 을 **이중계상으로 제거**했다(총사업비 −23,002,000).
근거는 *"소방은 도급단가에 이미 포함"* 인데 **그 범위가 어디에도 적혀 있지 않았다.**

## ★★초안의 「근거 세 축」 중 **둘이 무너졌다**(독립 리뷰 · 자체 재측정으로 확인)

    ✘ QTO 의 mep_ratio/elec_ratio  → **범주 오류**. QTO 산식의 계수이지 도급단가의 계수가 아니다.
                                      `overview_estimator` 가 같은 저장소 언어로 **혼용 금지**를 적는다.
    ✘ "QTO < 도급단가"             → **판별력 0**. 설비를 빼면 배수가 4.37 → **6.51 로 커진다**.
                                      간극을 만드는 것은 설비가 아니라 QTO 미모델 공종(마감·토공·승강기).
    ◎ **적산 실적 데이터**          → **유일하게 살아남은 직접 증거**:
                                      `mechanical.json` level-1 「소화설비공사」 ·
                                      `electrical.json` level-1 「소방공사」.

**그래서 이 파일이 잠그는 것도 그만큼이다** — 「증명」이 아니라 **①살아남은 증거가 사라지지 않게**
**②서술이 산문으로 썩지 않게** **③`#913` 과 결속되게**.

★**락을 「라벨」이 아니라 「금액」에 건다** — 초안은 `work_code` 에 `"기계설비"` 문자열이 있는지만
봐서 **설비비를 0으로 만드는 변이 3종이 전부 생존**했다(0원짜리 라벨 행이면 초록).
"""

from __future__ import annotations

import json
import pathlib

import pytest

from app.services.cost.standard_quantity_estimator import (
    STANDARD_QUANTITIES,
    StandardQuantityEstimator,
)
from app.services.cost.unit_price_repository import _DIRECT_SQM_FALLBACK

_API = pathlib.Path(__file__).resolve().parents[1]
_GFA = 238_504.0
_FLOORS_ABOVE, _FLOORS_BELOW = 30, 3


def _kr_type(building_type: str) -> str:
    """★영문 키 → 한글 키. `"apartment"` 는 `STANDARD_QUANTITIES` 에 **없다.**

    초안은 `estimate(building_type="apartment")` 를 그대로 넘겼는데, 그 함수는
    `STANDARD_QUANTITIES.get(bt, STANDARD_QUANTITIES["공동주택"])` 이라 **조용히 폴백**했다.
    그래서 주석은 `mep_ratio=0.35`(아파트)를 인용하면서 계산은 **0.34**(공동주택)로 했다 —
    **두 축이 서로 다른 건물유형에서 나온 것**이다. 프로덕션 매핑을 명시적으로 쓴다.
    """
    from app.services.cost.boq_builder import _BT_KR

    return _BT_KR[building_type]


def _rows(building_type: str = "apartment"):
    return StandardQuantityEstimator().estimate(
        building_type=_kr_type(building_type), total_gfa_sqm=_GFA,
        floor_count_above=_FLOORS_ABOVE, floor_count_below=_FLOORS_BELOW,
        structure_type="RC",
    )


def _amount(r) -> float:
    return (r.get("quantity") or 0) * (
        (r.get("mat_unit") or 0) + (r.get("labor_unit") or 0) + (r.get("exp_unit") or 0)
    )


class TestBuildingTypeMappingIsExplicit:
    """★「내가 잰 것이 그것인가」 — 영문/한글 키가 조용히 갈리지 않게."""

    def test_english_key_is_not_a_quantities_key(self):
        assert "apartment" not in STANDARD_QUANTITIES, (
            "영문 키가 생겼다면 `_kr_type` 매핑을 다시 보라 — 조용히 다른 계수를 쓰게 된다"
        )

    def test_mapping_resolves_to_a_real_key(self):
        for bt in _DIRECT_SQM_FALLBACK:
            kr = _kr_type(bt)
            assert kr in STANDARD_QUANTITIES, f"{bt} → {kr} 가 계수표에 없다(폴백으로 떨어진다)"


class TestSurvivingEvidenceFireLivesInsideMepElec:
    """◎ **유일하게 살아남은 직접 증거** — 실적 내역서에서 소방이 설비 안에 있다."""

    @pytest.mark.parametrize(
        ("fname", "section_kw"), [("mechanical.json", "소화"), ("electrical.json", "소방")],
    )
    def test_fire_is_a_level1_section_of_the_mep_trade(self, fname, section_kw):
        """★**level-1 절**로 판정한다 — 파일 어딘가에 낱말이 있는 것과 **공종으로 존재**하는 것은 다르다."""
        d = json.loads((_API / "app/services/cost/data/boq_master" / fname).read_text(encoding="utf-8"))
        roots = [s["name"] for s in d["sections"] if s.get("level") == 1]
        assert roots, f"★{fname} 에 level-1 절이 없다 — 조회기 사망"
        assert any(section_kw in n for n in roots), (
            f"{fname} level-1 절에 '{section_kw}' 이 없다: {roots} — "
            "소방이 설비 밖이면 #913 의 소방 제거 근거가 무너진다"
        )

    def test_the_probe_can_fail(self):
        """★음성 대조군 — 없는 공종은 **없다고** 나와야 한다."""
        d = json.loads((_API / "app/services/cost/data/boq_master/electrical.json").read_text(encoding="utf-8"))
        roots = [s["name"] for s in d["sections"] if s.get("level") == 1]
        assert not any("존재하지않는공종zzz" in n for n in roots)


class TestMepIsModelledWithRealMoney:
    """★락을 **금액**에 건다 — 라벨만 보면 0원짜리 행이 통과한다(변이 3종 생존 실증)."""

    def test_mep_and_elec_rows_carry_nonzero_amounts(self):
        rows = _rows()
        assert rows, "★QTO 산출이 비었다"
        by = {str(r.get("work_code", "")): _amount(r) for r in rows}
        mep = [v for k, v in by.items() if "기계설비" in k]
        elec = [v for k, v in by.items() if "전기설비" in k]
        assert mep and elec, f"설비 행이 없다: {sorted(by)}"
        assert min(mep) > 0 and min(elec) > 0, (
            f"설비 행의 **금액이 0** 이다(라벨만 남았다): 기계={mep} 전기={elec}"
        )

    def test_mep_share_is_material_not_token(self):
        """설비가 **의미 있는 몫**이어야 한다 — 1원짜리 행으로 위 단언을 만족시키지 못하게."""
        rows = _rows()
        total = sum(_amount(r) for r in rows)
        mep = sum(_amount(r) for r in rows if "설비" in str(r.get("work_code", "")))
        assert total > 0
        assert 0.10 <= mep / total <= 0.60, f"설비 비중이 비정상: {mep / total:.1%}"


class TestScopeStatementIsStructurallyIntact:
    """★서술이 **구조**로 남아 있는가 — 토큰 존재로 판정하면 절을 통째로 지워도 통과한다."""

    @staticmethod
    def _sections() -> tuple[str, str]:
        src = (_API / "app/services/cost/unit_price_repository.py").read_text(encoding="utf-8")
        assert "**포함(의도)**:" in src and "**제외(의도)**:" in src, (
            "포함/제외를 **둘 다** 적어야 한다 — 한쪽만 적으면 반대쪽이 무제한이 된다"
        )
        inc_at = src.index("**포함(의도)**:")
        exc_at = src.index("**제외(의도)**:")
        assert inc_at < exc_at
        # ★창을 **구조에서 파생**시킨다. 고정 길이(초안 900자)는 인접 절을 침범해
        #   **무관한 문서 수정을 틀린 사유로** 막았다(위양성도 결함이다).
        after = src[exc_at:]
        stop = after.index("\n#:\n") if "\n#:\n" in after else len(after)
        return src[inc_at:exc_at], after[:stop]

    def test_included_and_excluded_do_not_contradict(self):
        included, excluded = self._sections()
        for token in ("기계설비", "전기설비"):
            assert token in included, f"'{token}' 이 **포함** 절에서 사라졌다"
            assert token not in excluded, f"'{token}' 이 **제외** 절에도 있다(모순)"
        # ★인입비와 **소방**은 도급 밖이다 — 소방은 **법정 분리 도급**(§21②).
        for token in ("인입 분담금", "소방시설공사"):
            assert token in excluded, f"'{token}' 이 **제외** 절에 없다"
            assert token not in included, f"'{token}' 이 포함으로 넘어갔다 — 이중계상"

    def test_the_window_does_not_swallow_neighbours(self):
        """★대조군 — 제외 절 창이 **근거 절까지** 먹으면 위 단언이 거짓 사유로 실패한다."""
        _, excluded = self._sections()
        assert "기각 —" not in excluded, "제외 절 창이 인접(근거) 절을 침범했다"
        assert len(excluded) < 600, f"제외 절 창이 너무 넓다: {len(excluded)}자"

    def test_the_correction_and_its_law_stay_recorded(self):
        """★**정정과 그 법적 근거를 기록**한다 — 다음 사람이 같은 길을 다시 가지 않게.

        `#916` 은 소방을 이 단가 **안**에 두었고 `#913` 은 그 전제로 소방을 **제거**했다.
        **법이 정반대**다(소방시설공사업법 §21② 분리 도급 의무). 그 정정이 사라지면
        같은 오판이 재발한다.
        """
        src = (_API / "app/services/cost/unit_price_repository.py").read_text(encoding="utf-8")
        for token in ("소방시설공사업법", "§21", "분리하여 도급", "내역서 편성 ≠ 도급 편성"):
            assert token in src, f"소방 분리도급 정정에서 '{token}' 이 사라졌다"
        assert "미측정" in src, "남은 한계 표기가 사라졌다"


class TestBoundToPr913:
    def test_fire_is_not_reintroduced_as_a_charge(self):
        from app.services.tax.utility_stage_engine import calculate_all_utility_stage

        items = calculate_all_utility_stage(
            sido_name="서울", sigungu_name="강남구",
            total_households=64, total_gfa_sqm=6_572.0,
        )["items"]
        assert len(items) >= 4, f"★모집단이 {len(items)}건 — 아래 단언이 공허해진다"
        assert "B08" not in {i["code"] for i in items}, (
            "소방이 부담금으로 되살아났다 — 도급단가 포함 범위와 이중계상이 된다"
        )
