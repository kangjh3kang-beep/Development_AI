"""B01 광역교통 — **「시·도를 모른다」와 「대도시권이 아니다」를 가른다.**

## 왜 이 파일이 있나 (2026-08-27 라이브 3모집단 대조군)

같은 주소(`울산광역시 동구 화정동 637-11` — 울산은 `METRO_AREA_SIDO` 원소)에
`region` 만 바꿔 프로덕션 `/api/v2/feasibility/rough-scenario` 를 3회 호출한 실측:

    region=""      → rate=null · "지역미상 — 대도시권 아님" · confidence=null   ← 침묵 미부과
    region="울산"  → rate=0.02 · confidence="unavailable"                      ← 정직 고지
    region="동구"  → rate=null · "동구 — 대도시권 아님"    · confidence=null    ← 침묵 미부과

**대조군이 갈라 준 것**: 시·도가 **해석되면** 정직 기계
(`project_charges._collect_unavailable_notes`)에 편입돼 `degraded_notes` 까지 가지만,
**해석 실패하면** `applicable=False` 라 그 기계에 **아예 안 들어간다.**
→ 법정 부담금이 **사유 없이** 사라졌다. #874/C07 「미조회를 관측처럼 그렸다」와 같은 클래스.

## ★단언의 형태 — 전부 **파티션형**

이 파일의 모든 락은 *"이 단언이 초록일 때, **반대로 틀린 구현도** 초록인가?"* 를 통과해야 한다.
그래서 각 락이 **두 모집단**을 같은 실행에서 가른다:

  · *항상 unavailable* 을 내는 구현 → 「해석된 비대도시권」 단언이 죽인다
  · *항상 not_metro_area* 를 내는 구현 → 「미해석」 단언이 죽인다
  · *무조건 자가치유* 하는 구현 → 「강원 주소의 동구」 단언이 죽인다

한쪽만 걸면 반대 방향이 **원리적으로 탐지 불가**가 된다(이 저장소에서 하루 3회 난 결함).
"""

from __future__ import annotations

import pytest

from app.services.tax.project_charges import (
    charge_item_unavailable,
    compute_developer_stage_charges,
)
from app.services.tax.regional_tax_data import (
    _SIDO_FULL_TO_SHORT,
    KNOWN_SIDO_SHORT,
    METRO_AREA_SIDO,
    SIDO_BASIS_ADDRESS,
    SIDO_BASIS_EXPLICIT,
    SIDO_BASIS_UNRESOLVED,
    get_metro_transport_charge,
    resolve_sido_for_charges,
)

_SCB = 2_000_000  # 표준건축비 주입값(금액 경로를 태우기 위한 것 — 고시값 아님)


def _b01(**kw):
    kw.setdefault("gfa_sqm", 10_000.0)
    kw.setdefault("building_type", "apartment")
    return get_metro_transport_charge(**kw)


class TestResolverBasisPartition:
    """해석기 자체 — basis 세 갈래가 **서로 다른 입력에서** 나와야 한다."""

    def test_explicit_sido_is_explicit(self):
        assert resolve_sido_for_charges(sido_name="울산") == ("울산", SIDO_BASIS_EXPLICIT)
        assert resolve_sido_for_charges(sido_name="울산광역시") == ("울산", SIDO_BASIS_EXPLICIT)

    def test_sigungu_is_not_accepted_as_sido(self):
        """★핵심 — 「비어 있지 않음」이 아니라 「시도 표에 있음」으로 판정한다.

        `"동구"` 가 explicit 로 통과하면 자가치유 사다리가 **작동하지 않는다.**
        """
        short, basis = resolve_sido_for_charges(sido_name="동구")
        assert basis == SIDO_BASIS_UNRESOLVED
        assert short == ""

    def test_address_inference(self):
        assert resolve_sido_for_charges(address="울산광역시 동구 화정동 637-11") == (
            "울산", SIDO_BASIS_ADDRESS,
        )

    def test_unresolved_when_nothing_usable(self):
        assert resolve_sido_for_charges() == ("", SIDO_BASIS_UNRESOLVED)
        assert resolve_sido_for_charges(sido_name="동구", address="주소미상") == (
            "", SIDO_BASIS_UNRESOLVED,
        )

    def test_full_name_wins_over_substring_false_positive(self):
        """★위양성 가드 — `"경기도 광주시"` 는 **경기**다(대도시권 `광주` 아님).

        축약키만 부분일치로 훑으면 `"광주"` 가 걸려 **경기도 부지가 광주광역시로** 판정된다.
        완전명을 먼저 보는 순서가 이것을 막는다 — 그 순서를 되돌리면 이 단언이 죽는다.
        """
        assert resolve_sido_for_charges(address="경기도 광주시 오포읍 1-2")[0] == "경기"

    def test_known_sido_is_derived_not_a_hand_list(self):
        """손 목록이면 `_SIDO_FULL_TO_SHORT` 에 시도를 추가해도 따라오지 않는다."""
        assert frozenset(_SIDO_FULL_TO_SHORT.values()) == KNOWN_SIDO_SHORT
        assert set(KNOWN_SIDO_SHORT) >= METRO_AREA_SIDO  # 대도시권은 시도의 부분집합


class TestUnknownIsNotNonMetro:
    """★이 파일의 이유 — **모름 ≠ 아님**. 두 모집단을 같은 실행에서 가른다."""

    def test_unresolved_is_withheld_not_a_determination(self):
        r = _b01(sido_name="", address="")
        assert r["amount_won"] is None, "미해석인데 금액을 0으로 **단정**하면 안 된다"
        assert r["confidence"] == "unavailable"
        assert r.get("surveyed") is False, "정직 기계가 AWAITING_INPUT 를 내려면 필요"
        assert r.get("source") != "not_metro_area", "모르는 것을 「아니다」라고 하면 안 된다"
        assert r.get("applicable") is not False, "미해석은 「미부과 확정」이 아니다"

    def test_resolved_non_metro_is_a_real_determination(self):
        """★반대 방향 — 이 단언이 「항상 unavailable」 구현을 죽인다(과잉 억제 탐지)."""
        r = _b01(sido_name="제주", standard_build_cost_won_per_sqm=_SCB)
        assert r["applicable"] is False
        assert r["amount_won"] == 0
        assert r.get("confidence") != "unavailable", "해석된 비대도시권은 보류가 아니라 확정이다"
        assert r.get("source") == "not_metro_area"

    def test_the_two_populations_actually_differ(self):
        """대조군 생존 — 두 입력이 **실제로 다른 결과**를 낸다(차가 0이면 락이 아니다)."""
        unresolved = _b01(sido_name="", address="")
        non_metro = _b01(sido_name="제주")
        assert unresolved["amount_won"] is not non_metro["amount_won"]
        assert unresolved.get("confidence") != non_metro.get("confidence")


class TestSigunguSelfHealing:
    """호출부가 **시군구**를 넘겨도 초크포인트가 주소로 복구한다 — 단, **무조건은 아니다**."""

    def test_sigungu_plus_metro_address_heals(self):
        """`region="동구"` + 울산 주소 → 대도시권으로 복구(라이브 결함의 정확한 재현)."""
        r = _b01(
            sido_name="동구", address="울산광역시 동구 화정동 637-11",
            standard_build_cost_won_per_sqm=_SCB,
        )
        assert r["applicable"] is True
        assert r["amount_won"] and r["amount_won"] > 0
        assert r.get("sido_basis") == SIDO_BASIS_ADDRESS

    def test_sigungu_plus_non_metro_address_does_not_heal_into_metro(self):
        """★반대 방향 — 「무조건 대도시권으로 치유」하는 구현을 죽인다."""
        r = _b01(
            sido_name="동구", address="강원특별자치도 양양군 강현면 1-2",
            standard_build_cost_won_per_sqm=_SCB,
        )
        assert r["applicable"] is False
        assert r["amount_won"] == 0
        assert r.get("source") == "not_metro_area"

    def test_explicit_sido_beats_address(self):
        """명시 시도가 있으면 주소 추론으로 덮어쓰지 않는다(우선순위 역전 탐지)."""
        r = _b01(
            sido_name="서울", address="강원특별자치도 양양군 강현면 1-2",
            standard_build_cost_won_per_sqm=_SCB,
        )
        assert r.get("sido_basis") == SIDO_BASIS_EXPLICIT
        assert r["applicable"] is True


class TestDerivedPopulations:
    """★파생형 — 손 목록 금지. 두 모집단 **전 원소**를 같은 규칙으로 태운다."""

    @pytest.mark.parametrize("sido", sorted(METRO_AREA_SIDO))
    def test_every_metro_sido_is_applicable(self, sido):
        r = _b01(sido_name=sido, standard_build_cost_won_per_sqm=_SCB)
        assert r["applicable"] is True, f"{sido} 는 대도시권인데 미부과 판정"
        assert r["amount_won"] and r["amount_won"] > 0

    @pytest.mark.parametrize("sido", sorted(set(KNOWN_SIDO_SHORT) - METRO_AREA_SIDO))
    def test_every_non_metro_sido_is_determined_not_withheld(self, sido):
        """★반대 모집단 — 비대도시권은 **확정 0** 이지 보류가 아니다."""
        r = _b01(sido_name=sido, standard_build_cost_won_per_sqm=_SCB)
        assert r["applicable"] is False, f"{sido} 는 비대도시권"
        assert r.get("confidence") != "unavailable", f"{sido} 를 보류로 강등하면 과잉 억제"

    def test_both_populations_are_non_empty(self):
        """공허한 참 방지 — 위 두 parametrize 가 **실제로 돌았는지**를 개수로 단언."""
        assert len(METRO_AREA_SIDO) >= 9
        assert len(set(KNOWN_SIDO_SHORT) - METRO_AREA_SIDO) >= 5


class TestHonestyMachineryIntegration:
    """★진짜 결함이 사는 층 — 미해석이 `unavailable_notes` 까지 **실제로 올라가는가**.

    함수 단위만 잠그면 **배선은 무잠금**이다(이 저장소에서 하루 3회 재발한 형태).
    """

    @staticmethod
    def _b01_item(result):
        items = result["construction"]["items"]
        return next(i for i in items if i["code"] == "B01")

    def test_unresolved_reaches_degraded_notes(self):
        out = compute_developer_stage_charges(
            sido_name="", address="", total_gfa_sqm=10_000.0, total_households=64,
        )
        item = self._b01_item(out)
        assert charge_item_unavailable(item) is True
        joined = " / ".join(out["unavailable_notes"])
        assert "광역교통" in joined, "미해석이 사용자에게 보이는 통로까지 가야 한다"

    def test_resolved_non_metro_does_not_appear(self):
        """★반대 방향 — 「전부 노트에 싣는」 구현을 죽인다(공허한 참 방지)."""
        out = compute_developer_stage_charges(
            sido_name="제주", address="제주특별자치도 서귀포시 1-2",
            total_gfa_sqm=10_000.0, total_households=64,
        )
        item = self._b01_item(out)
        assert charge_item_unavailable(item) is False
        assert "광역교통" not in " / ".join(out["unavailable_notes"])

    def test_collector_is_alive_in_both_runs(self):
        """★대조군 — 수집기가 죽어서 「0건」인 것과 구별한다.

        B03/B04(조례 미등록)는 두 실행 모두에서 반드시 뜬다. 그것이 안 뜨면
        **「광역교통이 없다」는 결론 자체가 무효**다.
        """
        for sido, addr in (("", ""), ("제주", "제주특별자치도 서귀포시 1-2")):
            out = compute_developer_stage_charges(
                sido_name=sido, address=addr, total_gfa_sqm=10_000.0, total_households=64,
            )
            joined = " / ".join(out["unavailable_notes"])
            assert "원인자부담금" in joined, f"수집기 사망 의심({sido or '미해석'})"

    def test_sigungu_call_site_heals_end_to_end(self):
        """라이브 결함의 **종단 재현** — 프론트가 보내던 값 그대로 넣어 본다."""
        out = compute_developer_stage_charges(
            sido_name="동구", address="울산광역시 동구 화정동 637-11",
            total_gfa_sqm=10_000.0, total_households=64,
        )
        item = self._b01_item(out)
        # ★**산문으로 판정하지 않는다** — 2026-08-27 실사고(오류 #124).
        #   처음엔 `"표준건축비" in reason` 으로 걸었는데, **미해석 분기의 안내문에도**
        #   *"대도시권이면 '표준건축비 × 부과율 …'이 부과된다"* 라고 내가 써 놓아서
        #   **두 분기 모두 참**이었다 — 배선을 끊는 변이(M4)가 그대로 **생존**했다.
        #   내가 방금 쓴 문구가 내 단언의 **공허한 참**을 만든 것이다.
        #   → 판정은 **구조 필드**로 한다(파서형).
        assert item["detail"].get("sido_basis") == SIDO_BASIS_ADDRESS, (
            "주소가 초크포인트까지 **실제로 전달**되어야 시군구가 치유된다 — "
            "체인 어디서든 address 가 끊기면 여기서 죽는다"
        )
        assert item["detail"].get("applicable") is True
        assert item["detail"].get("surveyed") is not False, "치유됐으면 미조회가 아니다"


@pytest.mark.xfail(
    reason=(
        "★부채(미측정) — `integrated_recommender/orchestrator.py:286` 의 region 축을 "
        "**재측정하지 않고** dead-path 로 제외했다(인계 라벨 승계). 이 계획의 다른 라벨 셋은 "
        "재측정해서 둘이 뒤집혔으므로 이것도 뒤집힐 수 있다. 재측정 후 이 xfail 을 제거하거나 "
        "진짜 락으로 바꾼다."
    ),
    strict=True,
)
def test_orchestrator_dead_path_remeasured():
    raise AssertionError("미재측정 — 초록 안에 부채를 드러내 둔다")


class TestWiringIsLocked:
    """★배선 락 — **함수만 잠그면 배선은 무잠금**이다.

    이 파일 첫 판에서 변이 3종(`M3`·`M4`·`M5`)이 **전부 생존**했다. 함수 단위 락 34건이
    초록인 채로 **주소 전달을 끊어도**, **precheck 축 교정을 되돌려도** 아무도 안 죽었다.
    (`scripts/mutate_manual.sh` 로 실측 — 손 판단이 아니라 도구가 짚었다)

    ★**판정은 파서로 한다(`ast`), 정규식이 아니다.** 소스 문자열 검사는 주석·독스트링에
      뚫린다 — 그리고 이 PR 자체가 그 함정을 밟았다(오류 #124: **내가 쓴 안내문**이
      `"표준건축비" in reason` 을 **두 분기 모두 참**으로 만들어 M4 를 살렸다).

    ★이 락들은 **호출 인자의 존재**를 본다. 진짜 경로를 태우는 락
      (`TestHonestyMachineryIntegration`)이 우선이고, 여기는 그것이 닿지 못하는
      상위 배선(오케스트레이터·precheck)을 덮는 **보완**이다.
    """

    @staticmethod
    def _kwarg_of_call(path: str, func_name: str, kwarg: str):
        """`func_name(...)` 호출에서 `kwarg=` 로 넘긴 **인자 노드**들을 모은다(AST)."""
        import ast
        import pathlib

        tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", None)
            if name != func_name:
                continue
            for kw in node.keywords:
                if kw.arg == kwarg:
                    found.append(kw.value)
        return found

    def test_orchestrator_passes_real_address_not_a_literal(self):
        """M3 — 오케스트레이터가 `compute_developer_stage_charges` 에 **주소를 넘기는가**.

        ★한쪽만 걸지 않는다: *"`address` 키가 있다"* 만 보면 `address=""` 로 되돌리는
          변이가 통과한다. **리터럴이 아니라 이름(변수)** 이어야 한다고 단언한다.
        """
        import ast

        path = "app/services/feasibility/rough_feasibility_orchestrator.py"
        args = self._kwarg_of_call(path, "compute_developer_stage_charges", "address")
        assert args, "★배선 없음 — 주소를 안 넘기면 시군구 자가치유가 죽는다"
        assert any(isinstance(a, ast.Name) for a in args), (
            "address 가 리터럴(예: \"\")이면 배선이 끊긴 것과 같다"
        )

    def test_project_charges_forwards_address_downstream(self):
        """M4 의 소스측 짝 — `calculate_all_utility_stage` 로도 **변수**가 흘러야 한다."""
        import ast

        path = "app/services/tax/project_charges.py"
        args = self._kwarg_of_call(path, "calculate_all_utility_stage", "address")
        assert args, "★체인 중간에서 주소가 끊긴다"
        assert any(isinstance(a, ast.Name) for a in args)

    def test_precheck_does_not_put_sigungu_into_sido(self):
        """M5 — `sido_name=` 에 **시군구 변수를 직결**하지 않는다.

        두 모집단: `sido_name` 은 **해석기 호출**이어야 하고(Call), `sigungu_name` 은
        **시군구 변수**여야 한다(Name). 한쪽만 보면 둘을 맞바꾼 구현이 통과한다.
        """
        import ast

        path = "app/services/precheck/precheck_service.py"
        sido = self._kwarg_of_call(path, "ModuleInput", "sido_name")
        sigungu = self._kwarg_of_call(path, "ModuleInput", "sigungu_name")
        assert sido and sigungu, "★대조군 사망 — ModuleInput 호출을 못 찾았다(파서 점검)"
        assert all(isinstance(a, ast.Call) for a in sido), (
            "sido_name 은 주소 해석기의 **반환값**이어야 한다 — 시군구 변수 직결 금지"
        )
        assert any(isinstance(a, ast.Name) for a in sigungu), (
            "sigungu_name 이 비어 있으면 축이 여전히 붕괴한 것이다"
        )


class TestHealingAlsoFixesTheRate:
    """★#885 와의 합성 — 축 해석이 **부과율까지** 바로잡는다(금액이 움직인다).

    #885 가 부과율을 `수도권 4% · 그 외 대도시권 2%` 로 법령 교정하면서 판정을
    `sido_name` 에서 **파생**시켰다. 이 PR 이 `sido_name` 을 **해석된 시도**로 바꾸므로,
    호출부가 시군구를 넘기던 경로는 이제 **요율까지** 옳아진다.

    ★**이 PR 단독으로는 금액이 안 움직인다**(표준건축비 미주입이라 전부 0)는 서술은
      `#885` **이전** 기준이었다. 합성 후에는 표준건축비가 주입되는 순간
      **수도권 시군구 경로가 2% → 4% 로 2배** 바뀐다 — 그래서 여기서 잠근다.
    """

    @staticmethod
    def _rate(**kw):
        return get_metro_transport_charge(
            gfa_sqm=10_000.0, building_type="apartment",
            standard_build_cost_won_per_sqm=2_000_000, **kw,
        )

    def test_capital_area_sigungu_heals_to_4pct(self):
        """`"강남구"` + 서울 주소 → **수도권 4%**(종전엔 시군구라 판정 실패 → 2%)."""
        r = self._rate(sido_name="강남구", address="서울특별시 강남구 역삼동 1-2")
        assert r["rate"] == 0.04
        assert r["amount_won"] == 800_000_000

    def test_non_capital_metro_sigungu_heals_to_2pct(self):
        """★반대 모집단 — `"동구"` + 울산 주소 → **2%**. 무조건 4% 가 아니다."""
        r = self._rate(sido_name="동구", address="울산광역시 동구 화정동 637-11")
        assert r["rate"] == 0.02
        assert r["amount_won"] == 400_000_000

    def test_the_two_rates_actually_differ(self):
        """대조군 — 두 모집단이 **실제로 갈린다**(차가 0이면 이 락은 장식이다)."""
        cap = self._rate(sido_name="강남구", address="서울특별시 강남구 역삼동 1-2")
        non = self._rate(sido_name="동구", address="울산광역시 동구 화정동 637-11")
        assert cap["rate"] != non["rate"]
        assert cap["amount_won"] == non["amount_won"] * 2
