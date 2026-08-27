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
        # ★`source` 로 판정하지 않는다 — 미해석 분기 dict 에는 `source` 키가 **아예 없어서**
        #   `!= "not_metro_area"` 가 **원리적으로 위반 불가**였다(독립 리뷰 D9-1).
        #   확정 분기와 **같은 축**에서 비교해야 락이 된다.
        assert r.get("sido_basis") == SIDO_BASIS_UNRESOLVED
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
        # ★`is not` 는 **동일성**이라 0 과 0.0 을 구별 못 한다 — 값으로 단언한다(D9-2).
        assert unresolved["amount_won"] is None
        assert non_metro["amount_won"] == 0
        assert unresolved.get("confidence") == "unavailable"
        assert non_metro.get("confidence") != "unavailable"


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


def test_integrated_recommender_path_is_live_and_covered():
    """★인계 라벨 **「dead-path 확정 — 제외」가 거짓이었다**(2차 독립 리뷰가 잡았다).

    인계서는 `integrated_recommender/orchestrator.py:286` 을 *"라우터 참조 0건 = dead-path,
    대조군으로 판정 완료"* 라고 넘겼다. **실재하는 라이브 라우트다**:

        routers/development_methods.py:267   IntegratedRecommender().recommend(...)
        main.py:914                          include_router(..., prefix="/api/v1/development-methods")

    ★**왜 0건이 나왔나** — 그 파일은 `apps/api/routers/` 에 있고 조회는 `app/routers/` 만 봤다.
      **패턴이 아니라 범위가 틀렸다**(CLAUDE.md §26 — "0건"은 부재가 아니다).
      나는 이 라벨을 §3-1 에 *"뒤집힐 수 있다"* 고 적어 두고도 **그대로 승계**했다.

    그리고 이 경로의 `region` 은 **시·도**다(`_region_from_address` = 주소 첫 토큰).
    같은 필드에 rough-scenario 는 **시군구**를 넣는다 — 그래서 *"region 은 시군구"* 라고
    찍는 처방은 **이 경로에 새 축 날조**를 만들었을 것이다. `looks_like_sido` 가 그것을 막는다.
    """
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

    inp = FeasibilityServiceV2().build_module_input(
        dev_type="M01", site_area_sqm=1_000.0, max_far_pct=250.0,
        region="경기도",  # ★이 경로가 실제로 넘기는 형태(주소 첫 토큰 = 시도)
        address="경기도 수원시 영통구 1",
    )
    assert inp.sido_name == "경기", "시·도가 주소에서 해석돼야 대도시권 판정이 산다"
    assert inp.sigungu_name == "", "시·도를 시군구 칸에 넣으면 새 축 날조다"


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
        # ★**이름까지** 단언한다 — 노드 타입만 보면 `address=region` 도 `ast.Name` 이라
        #   통과한다(독립 리뷰 M-B 가 그렇게 생존했다). **대리 변수 잠금은 잠금이 아니다.**
        assert any(isinstance(a, ast.Name) and a.id == "address" for a in args), (
            "address 에는 **주소 변수**가 가야 한다(리터럴·다른 변수 금지)"
        )

    def test_project_charges_forwards_address_downstream(self):
        """M4 의 소스측 짝 — `calculate_all_utility_stage` 로도 **변수**가 흘러야 한다."""
        import ast

        path = "app/services/tax/project_charges.py"
        args = self._kwarg_of_call(path, "calculate_all_utility_stage", "address")
        assert args, "★체인 중간에서 주소가 끊긴다"
        assert any(isinstance(a, ast.Name) and a.id == "address" for a in args)

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
        # ★**호출되는 함수 이름까지** 단언한다 — `isinstance(a, ast.Call)` 만 보면
        #   `str(region)` 도 Call 이라 **원래 결함이 그대로 통과**했다(독립 리뷰 M-A).
        assert all(
            isinstance(a, ast.Call)
            and getattr(a.func, "id", getattr(a.func, "attr", None)) == "sido_short_or_empty"
            for a in sido
        ), "sido_name 은 **공용 시도 해석기**의 반환값이어야 한다 — 시군구 변수 직결 금지"
        # ★sigungu 칸의 *내용*은 여기서 판정하지 않는다 — 노드 타입 단언은
        #   `sigungu_name=""` 같은 축 붕괴를 못 잡는다(2차 리뷰 M-J 가 그렇게 생존했다).
        #   그 판정은 **행위 락**(`TestProducersBurnedForReal`)이 한다. 여기는 존재만 본다.
        assert sigungu, "sigungu_name 칸 자체가 없으면 축이 갈리지 않는다"


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


class TestAddressInferenceIsDeterministicAndHonest:
    """★독립 리뷰가 잡은 CRITICAL — 집합 순회는 **프로세스마다 답이 달랐다**.

    `frozenset[str]` 순회 순서는 `PYTHONHASHSEED` 의존이라, 주소에 시·도 축약명이
    둘 이상 걸리면 **같은 요청이 워커마다 다른 법정 부담금**을 냈다(실측):

        "서울 종로구 세종대로 209" → seed1: 서울(4%) · seed0/2/3: 세종(2%)
        "부산 해운대구 대전로 12"  → seed0: 부산 · seed1: 대전 · seed5: 대구

    그리고 부분일치라 **없는 시·도를 지어냈다** — `"해운대구"` ⊃ `"대구"`,
    `"세종대왕면"` ⊃ `"세종"`. 그런데 `basis="sido_address"`(=관측)로 라벨링됐다.

    ★내 기존 위양성 가드는 `"경기도 광주시"`(**완전명 분기**)만 태워서
      **깨진 축약형 루프를 한 번도 실행하지 않았다.** 가드가 다른 분기를 보고 있었다.
    """

    @pytest.mark.parametrize(
        ("addr", "expected"),
        [
            ("울산광역시 동구 화정동 637-11", "울산"),
            ("경기도 광주시 오포읍 1-2", "경기"),
            ("경기 광주시 오포읍 1-2", "경기"),      # 축약형도 맨 앞이면 인정
            ("서울 종로구 세종대로 209", "서울"),     # ★"세종대로" 에 속지 않는다
            ("부산 해운대구 대전로 12", "부산"),      # ★"대전로" 에 속지 않는다
            ("전남 나주시 전북로 5", "전남"),
        ],
    )
    def test_prefix_anchored_inference(self, addr, expected):
        assert resolve_sido_for_charges(address=addr) == (expected, SIDO_BASIS_ADDRESS)

    @pytest.mark.parametrize(
        "addr",
        [
            "여주시 세종대왕면 왕대리 1",   # ★실재 행정구역 — "세종" 을 지어내면 안 된다
            "해운대구 우동 1394",          # ★"대구" 를 지어내면 안 된다
            "의정부동 224",               # 시·도 접두 없음(이 저장소에 실재하는 형태)
            "주소미상",
        ],
    )
    def test_no_sido_prefix_is_unresolved_not_invented(self, addr):
        """★반대 모집단 — 모르면 **모른다고** 한다. 지어내고 `sido_address` 라벨을 달지 않는다."""
        short, basis = resolve_sido_for_charges(address=addr)
        assert basis == SIDO_BASIS_UNRESOLVED
        assert short == ""

    def test_candidate_order_is_deterministic_not_a_set(self):
        """순회 대상이 **집합이면** 순서가 프로세스마다 바뀐다 — 자료형 자체를 잠근다."""
        from app.services.tax.regional_tax_data import _SIDO_ADDRESS_PREFIXES

        assert isinstance(_SIDO_ADDRESS_PREFIXES, tuple), (
            "set/frozenset 순회는 PYTHONHASHSEED 의존 — 같은 입력에 다른 답을 낸다"
        )
        lengths = [len(n) for n in _SIDO_ADDRESS_PREFIXES]
        assert lengths == sorted(lengths, reverse=True), "긴 이름 우선이어야 최장일치"


class TestSiblingCallSitesAreSwept:
    """★형제 스윕 — 한 곳만 고치면 근본 봉합이 아니다(CLAUDE.md 전역 전파방지).

    독립 리뷰가 잡았다: `precheck` 만 고치고 **주 엔진 경로**(`ModuleInput` 생산자)는
    같은 결함이 남아 있었다. `sido_name=region`(시군구 직결) 자리를 **파생형으로** 훑는다.
    """

    #: 시·도 칸에 값을 넣는 **생산자** 전수. 새 생산자가 생기면 여기 걸린다.
    PRODUCERS = (
        "app/services/precheck/precheck_service.py",
        "app/services/feasibility/feasibility_service_v2.py",
        "app/routers/v2_feasibility.py",
    )

    @pytest.mark.parametrize("path", PRODUCERS)
    def test_no_producer_assigns_bare_region_to_sido(self, path):
        """`sido_name=region` / `sido_name=req.region` 이 **한 건도** 남지 않아야 한다."""
        import ast
        import pathlib

        tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
        offenders = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg != "sido_name":
                    continue
                v = kw.value
                if isinstance(v, ast.Name) and v.id == "region":
                    offenders.append(f"{path}: sido_name=region")
                if isinstance(v, ast.Attribute) and v.attr == "region":
                    offenders.append(f"{path}: sido_name=*.region")
        assert not offenders, f"★축 붕괴 잔존: {offenders}"

    def test_the_scanner_can_actually_see_offenders(self):
        """★대조군 — 검사기가 **살아 있는지** 증명한다("위반 0"이 조회 실패일 수 있다).

        일부러 위반이 든 소스를 파서에 태워 **잡히는지** 본다. 이게 없으면
        위 parametrize 의 초록은 "위반이 없다"가 아니라 "못 찾는다"일 수 있다.
        """
        import ast

        bad = "ModuleInput(sido_name=region, sigungu_name='')"
        tree = ast.parse(bad)
        hits = [
            kw for node in ast.walk(tree) if isinstance(node, ast.Call)
            for kw in node.keywords
            if kw.arg == "sido_name" and isinstance(kw.value, ast.Name) and kw.value.id == "region"
        ]
        assert len(hits) == 1, "검사기 사망 — 위반을 심었는데 못 잡는다"


class TestAxisFixNoLongerFabricatesB03B04:
    """★**이 클래스는 내가 만든 락이 날조값을 굳히고 있었다**(2026-08-27 자기정정).

    #891 에서 나는 *"축이 맞으면 등록 단가가 살아난다"* 를 락으로 걸었다 —
    `B03 > 0 and B04 > 0`. 그 「등록 단가」가 **출처 0건의 생성값**이었다:

      · 제거된 「전국폴백 날조값」 `120_000` 이 표에 그대로 있었다(`대구`·`경기_오산시`)
      · 값 분포가 **5,000원 계단** — 독립 조례 20건이 낼 분포가 아니다
      · ★**차원이 법과 다르다** — **법 2 + 시행령 2** 에서 `'세대'` 출현 **0회**(★조례는 별개 — 울산 하수도 조례 §9② 는 세대별 정액 고시를 허용한다)
        (하수도법 §61+시행령 §35 = ㎥/일 · 수도법 시행령 §65① = 사용량)
      · 울산 실제 단위단가로 재계산하면 **8~11배 과소**

    즉 내 락은 *"축을 고쳤다"* 를 잠근 게 아니라 **"날조값이 계상된다"** 를 잠갔다.
    → 단언을 뒤집는다. **축 교정의 진짜 성과는 B01(광역교통)** 이고, B03/B04 는
      **정직하게 보류**되어야 한다.
    """

    @staticmethod
    def _amounts(**kw):
        out = compute_developer_stage_charges(
            total_gfa_sqm=10_000.0, total_households=64, **kw,
        )
        return {i["code"]: i for i in out["construction"]["items"]}

    def test_b03_b04_are_withheld_regardless_of_axis(self):
        """축이 맞든 틀리든 **날조값을 계상하지 않는다**(단가 출처 미확보)."""
        for kw in (
            {"sido_name": "경기", "sigungu_name": "수원시"},   # 종전 「등록 지역」
            {"sido_name": "", "sigungu_name": ""},             # 미해석
        ):
            a = self._amounts(**kw)
            assert a["B03"]["amount_won"] == 0
            assert a["B04"]["amount_won"] == 0
            assert a["B03"]["detail"]["confidence"] == "unavailable"
            assert a["B04"]["detail"]["confidence"] == "unavailable"

    def test_axis_fix_still_pays_off_on_b01(self):
        """★대조군 — 축 교정 자체는 **여전히 유효**하다(B01 이 그 증거).

        이 단언이 없으면 *"전부 0으로 만들면 통과"* 하는 구현과 구별되지 않는다.
        """
        resolved = self._amounts(sido_name="울산", sigungu_name="")
        unresolved = self._amounts(sido_name="", sigungu_name="")
        assert resolved["B01"]["rate"] is not None, "해석되면 부과율이 나온다"
        assert unresolved["B01"]["rate"] is None, "미해석은 부과율도 없다"
        assert resolved["B01"]["detail"].get("sido_basis") == SIDO_BASIS_EXPLICIT


class TestProducersBurnedForReal:
    """★**생산자를 행위로 태운다** — AST 락은 철자만 거부했다(2차 독립 리뷰).

    1차 봉합의 AST 락은 `sido_name=region` 이라는 **철자 두 개**만 막았다. 그래서
    `sido_name=_sido_short_or_empty(region)`(대상만 바꾼 것)이나 `sigungu_name=""`(축을 다시
    비우는 것)은 **그대로 통과**했고, 그중 셋은 **돈을 움직였다**(B03+B04 −21.5%).

    > **함수는 잠갔는데 배선은 무잠금** — 이 PR 이 고쳤다고 선언한 그 결함이
    > **한 층 위에서 재발**했다. 그래서 이제 **생산자를 실제로 호출해** 나온
    > `ModuleInput` 의 `(sido_name, sigungu_name)` 두 칸을 **두 모집단**으로 단언한다.
    """

    @staticmethod
    def _svc():
        from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2

        return FeasibilityServiceV2()

    def test_build_module_input_splits_axes_for_sigungu_region(self):
        """`region` 이 **시군구**로 오는 호출부(rough-scenario) — 두 칸이 갈려야 한다."""
        inp = self._svc().build_module_input(
            dev_type="M01", site_area_sqm=1_000.0, max_far_pct=250.0,
            region="수원시", address="경기도 수원시 영통구 1-2",
        )
        assert inp.sido_name == "경기", "시·도는 주소에서 해석"
        assert inp.sigungu_name == "수원시", "시군구는 region 에서"

    def test_build_module_input_refuses_to_put_a_sido_into_sigungu(self):
        """★반대 모집단 — `region` 이 **시도**로 오는 호출부(integrated_recommender).

        같은 필드에 뜻이 다른 값이 온다. 시·도를 시군구 칸에 넣으면 **새 축 날조**다.
        """
        inp = self._svc().build_module_input(
            dev_type="M01", site_area_sqm=1_000.0, max_far_pct=250.0,
            region="경기도", address="경기도 수원시 영통구 1-2",
        )
        assert inp.sido_name == "경기"
        assert inp.sigungu_name == "", "시·도를 시군구 칸에 넣으면 안 된다"

    def test_build_module_input_unresolved_address_invents_nothing(self):
        """주소로 시·도를 못 얻으면 **빈 문자열**. `"서울"` 을 지어내지 않는다."""
        inp = self._svc().build_module_input(
            dev_type="M01", site_area_sqm=1_000.0, max_far_pct=250.0,
            region="", address="의정부동 224",
        )
        assert inp.sido_name == ""
        assert inp.sigungu_name == ""

    def test_the_two_populations_actually_differ(self):
        """대조군 — 두 모집단이 실제로 갈린다(차가 0이면 락이 아니다)."""
        svc = self._svc()
        a = svc.build_module_input(dev_type="M01", site_area_sqm=1_000.0, max_far_pct=250.0,
                                   region="수원시", address="경기도 수원시 영통구 1-2")
        b = svc.build_module_input(dev_type="M01", site_area_sqm=1_000.0, max_far_pct=250.0,
                                   region="경기도", address="경기도 수원시 영통구 1-2")
        assert a.sigungu_name != b.sigungu_name

    def test_precheck_producer_splits_axes(self):
        """precheck 생산자도 **같은 계약**이어야 한다(형제 일치)."""
        import asyncio

        from app.services.precheck.precheck_service import _build_band_module_input

        _svc, inp = asyncio.run(_build_band_module_input(
            best_code="M01", zone_type="제2종일반주거지역",
            legal={"sigungu": "수원시", "far_pct": 250.0, "applied_far_pct": 250.0},
            area_sqm=1_000.0, address="경기도 수원시 영통구 1-2",
            official_price_per_sqm=1_500_000.0,
        ))
        assert inp.sido_name == "경기"
        assert inp.sigungu_name == "수원시"

    def test_precheck_producer_does_not_fabricate_seoul(self):
        """★반대 모집단 — 시군구 미확인이면 **지어낸 `"서울"`** 이 축에 들어가면 안 된다."""
        import asyncio

        from app.services.precheck.precheck_service import _build_band_module_input

        _svc, inp = asyncio.run(_build_band_module_input(
            best_code="M01", zone_type="제2종일반주거지역",
            legal={"far_pct": 250.0, "applied_far_pct": 250.0},
            area_sqm=1_000.0, address="주소미상",
            official_price_per_sqm=1_500_000.0,
        ))
        assert inp.sigungu_name == "", "지어낸 폴백이 시군구 축에 새면 안 된다"
        assert inp.sido_name == ""

    def test_producer_axes_reach_the_money(self):
        """★종단 — 생산자가 낸 두 칸이 **실제 B03/B04 금액**을 만든다.

        이것이 없으면 「금액이 움직인다」는 선언이 **그것을 만드는 코드에 결속되지 않는다.**
        """
        svc = self._svc()
        good = svc.build_module_input(dev_type="M01", site_area_sqm=1_000.0, max_far_pct=250.0,
                                      region="수원시", address="경기도 수원시 영통구 1-2")
        blind = svc.build_module_input(dev_type="M01", site_area_sqm=1_000.0, max_far_pct=250.0,
                                       region="", address="의정부동 224")
        amt = lambda i: {  # noqa: E731
            x["code"]: x["rate"] for x in compute_developer_stage_charges(
                sido_name=i.sido_name, sigungu_name=i.sigungu_name,
                total_gfa_sqm=10_000.0, total_households=64,
            )["construction"]["items"]
        }
        g, b = amt(good), amt(blind)
        # ★종전 이 단언은 `g["B03"] > 0` 이었다 — **날조 단가가 계상되는 것**을 잠갔다.
        #   축 교정의 진짜 성과는 **B01 광역교통**이다(부과율이 나오는가).
        assert g["B01"] is not None, "★시·도가 해석되면 광역교통 부과율이 나온다"
        assert b["B01"] is None, "★반대 모집단 — 미해석이면 부과율도 없다"
        assert g["B03"] is None and b["B03"] is None, "단가 출처 미확보 — 양쪽 다 정직 보류"
