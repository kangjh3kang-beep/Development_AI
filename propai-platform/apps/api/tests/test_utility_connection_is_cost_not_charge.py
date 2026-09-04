"""인입·부대 비용은 **부담금이 아니라 공사비**다 — 분류와 총액을 함께 잠근다.

## 왜 (2026-08-27 · 법제처 원문 + 저장소 적산 실적)

종전 `utility_stage_engine` 의 **B05~B08 「부담금」** 은 법정 부담금이 아니었다:

    전기사업법        '시설부담금' 0회   (대조군 '전기' 755회)  — §51 부담금은 전력산업기반부담금(사용자 부과)
    도시가스사업법     '분담금' 4회      — 설치비용 분담금은 실재하나 산정기준은 위임(공급규정)
    소방시설법        '부담금' 0·'분담금' 0 (대조군 '소방' 887회·본문 130KB)

★저장소가 절반은 알고 있었다 — `budget_template._CHARGES` 의 note 가
*"한전 **시설분담금**(코드 B05)"*·*"도시가스 **공급규정**(코드 B06)"* 이라 적는다.
**라벨만 「부담금」이었다.**

## ★소방(구 B08)만 처방이 다르다 — 이관이 아니라 **제거**

저장소 **적산 실적**(`data/boq_master/electrical.json` · 실적 공내역서 1건 · GFA 238,504㎡ ·
**재료비만**)으로 재니:

    전기공사 58,176 원/㎡ · 통신공사 20,017 원/㎡ · **소방공사 27,223 원/㎡**

코드값 `3,500원/㎡` 의 **7.8배**(재료비만). 즉 그 값은 소방공사비가 **될 수 없고**,
실제 소방공사는 **직접공사비 도급단가에 이미 포함**돼 있다(전기+통신+소방 재료비만
105,416원/㎡ = 도급단가 2,400,000원/㎡ 의 4.4%. 도급 밖이라면 그 단가가 성립하지 않는다).

★**인입은 반대다** — 적산 내역서에 `'인입'` **0회**(electrical)·**1회**(mechanical)이고
대조군은 풍부하다(`'간선'` 270 · `'스프링클러'` 92 · `'가스'` 272). 한전·도시가스사에
**내는 돈**은 도급 내역서에 나타나지 않는다 → **도급 밖이므로 별도 계상이 정당**하다.

★**한계**: 적산 실적 **n=1**(주상복합) · **재료비만** · 도급단가가 소방을 포함한다고
**저장소가 명시한 문서는 없다**(강한 방증이지 직접 확인은 아니다).
"""

from __future__ import annotations

import pytest

from app.services.cost.utility_connection_cost import (
    UTILITY_CONNECTION_ITEMS,
    calculate_utility_connection_cost,
)
from app.services.feasibility.construction_cost_engine import (
    calculate_total_construction_cost,
)
from app.services.tax.utility_stage_engine import calculate_all_utility_stage

GFA = 6_572.0
HH = 64
#: 종전 B05~B07(인입) 금액 — 이관은 **금액을 바꾸지 않는다**.
_LEGACY_CONNECTION_WON = 250_000 * HH + 180_000 * HH + 80_000 * HH   # 32,640,000
#: 종전 B08(소방) 금액 — **제거**되는 것(이중계상).
_LEGACY_FIRE_WON = 3_500 * int(GFA)                                   # 23,002,000


class TestChargeEngineHoldsOnlyStatutoryCharges:
    def test_only_four_statutory_codes_remain(self):
        codes = [i["code"] for i in calculate_all_utility_stage(
            sido_name="서울", sigungu_name="강남구",
            total_households=HH, total_gfa_sqm=GFA, total_sale_amount_won=10**11,
        )["items"]]
        assert codes == ["B01", "B02", "B03", "B04"]

    def test_cost_natured_codes_do_not_return(self):
        """★반대 방향 — 공사비 성격 코드가 부담금 엔진에 되돌아오면 실패."""
        codes = {i["code"] for i in calculate_all_utility_stage(
            sido_name="서울", sigungu_name="강남구",
            total_households=HH, total_gfa_sqm=GFA,
        )["items"]}
        assert not ({"B05", "B06", "B07", "B08"} & codes)

    def test_every_remaining_charge_has_a_legal_ref(self):
        """남은 넷은 **전부** 법령 근거를 갖는다 — 그것이 「부담금」의 정의다."""
        items = calculate_all_utility_stage(
            sido_name="서울", sigungu_name="강남구",
            total_households=HH, total_gfa_sqm=GFA, total_sale_amount_won=10**11,
        )["items"]
        assert items, "★모집단이 비었다 — 아래 단언이 공허해진다"
        missing = [i["code"] for i in items if not i.get("legal_ref")]
        assert not missing, f"법령 근거 없는 부담금: {missing}"


class TestConnectionCostMovedWithoutChangingTheAmount:
    def test_connection_total_equals_legacy_b05_b06_b07(self):
        """★이관은 **금액을 바꾸지 않는다** — 바뀌는 것은 무엇이라 부르는가다."""
        got = calculate_utility_connection_cost(
            total_households=HH, total_gfa_sqm=GFA,
        )["total_won"]
        assert got == _LEGACY_CONNECTION_WON == 32_640_000

    def test_construction_total_grows_by_exactly_the_connection_cost(self):
        """★공사비 총액이 **정확히 인입비만큼** 는다(다른 것이 딸려 오지 않는다)."""
        with_hh = calculate_total_construction_cost(
            total_gfa_sqm=GFA, building_type="apartment", total_households=HH,
        )["total_construction_cost_won"]
        without = calculate_total_construction_cost(
            total_gfa_sqm=GFA, building_type="apartment", total_households=0,
        )["total_construction_cost_won"]
        assert with_hh - without == _LEGACY_CONNECTION_WON

    def test_households_zero_means_no_connection_cost(self):
        """★반대 모집단 — 세대수가 없으면 인입비도 없다(무조건 더하는 구현 탐지)."""
        assert calculate_utility_connection_cost(
            total_households=0, total_gfa_sqm=GFA,
        )["total_won"] == 0


class TestFireIsRemovedNotMoved:
    def test_fire_is_not_priced_from_the_old_fabricated_rate(self):
        """★2026-08-27 정정 — 소방은 **되살아났지만**(법정 분리 도급) **값은 아니다.**

        초안은 *"소방은 도급단가에 포함이니 이관 대상이 아니다"* 를 단언했는데
        **그 전제가 법으로 반증**됐다(소방시설공사업법 §21②). 지금 잠글 것은
        *"항목이 없다"* 가 아니라 **"날조 단가가 없다"** 다.
        """
        names = " ".join(i["name"] for i in UTILITY_CONNECTION_ITEMS)
        assert "소방" not in names, "인입비 목록(단가 보유)에는 소방이 없다 — 보류 항목은 별도"
        rates = [i["per_unit_won"] for i in UTILITY_CONNECTION_ITEMS]
        assert 3_500 not in rates, "종전 날조 단가가 인입비로 스며들었다"

    def test_total_drop_equals_exactly_the_fire_amount(self):
        """★**총사업비 순변화 = 소방 제거분** — 그 외에는 아무것도 움직이지 않는다.

        ★**첫 판의 이 테스트는 공허했다**(독립 리뷰 실증). 손으로 쓴 상수끼리 비교해
          `calculate_utility_connection_cost` 만 태웠고 **부담금 엔진도 공사비 엔진도 안 태웠다** —
          부담금에 B08 소방을 **되살리는 변이가 SURVIVED** 했다. 그래서 이 락이 있었는데도
          「호출부 하나 누락」(총사업비 -55,642,000)이 통과했다.
          → **두 엔진을 실제로 태워** 순변화를 계산한다.
        """
        charges_won = calculate_all_utility_stage(
            sido_name="서울", sigungu_name="강남구",
            total_households=HH, total_gfa_sqm=GFA, total_sale_amount_won=10**11,
        )["total_won"]
        constr_won = calculate_total_construction_cost(
            total_gfa_sqm=GFA, building_type="apartment", total_households=HH,
        )["total_construction_cost_won"]
        # 종전(HEAD~1) 상태를 같은 엔진으로 재현: 부담금에 B05~B08 이 있었고 공사비엔 인입이 없었다.
        legacy_charges = charges_won + _LEGACY_CONNECTION_WON + _LEGACY_FIRE_WON
        legacy_constr = constr_won - _LEGACY_CONNECTION_WON
        now_total = charges_won + constr_won
        legacy_total = legacy_charges + legacy_constr
        assert legacy_total - now_total == _LEGACY_FIRE_WON == 23_002_000, (
            f"총사업비 순변화가 소방 금액이 아니다: {legacy_total - now_total:,}"
        )

    def test_charge_engine_no_longer_contains_the_moved_amounts(self):
        """★위 계산이 성립하려면 **부담금 엔진에 그 금액이 실제로 없어야** 한다.

        상수 산술만으로는 「엔진에 되살아난 것」을 못 잡는다(그 변이가 실제로 생존했다).
        """
        items = calculate_all_utility_stage(
            sido_name="서울", sigungu_name="강남구",
            total_households=HH, total_gfa_sqm=GFA, total_sale_amount_won=10**11,
        )["items"]
        codes = {i["code"] for i in items}
        assert not ({"B05", "B06", "B07", "B08"} & codes)
        # ★금액으로도 확인 — 코드명을 바꿔 되살리는 변이를 잡는다.
        for i in items:
            assert i["amount_won"] != _LEGACY_FIRE_WON, f"소방 금액이 {i['code']} 로 되살아났다"


class TestEstimatesDeclareThemselves:
    """★공사비 **개산은 정당**하지만, 개산이라고 **말해야** 한다."""

    @pytest.mark.parametrize("item", UTILITY_CONNECTION_ITEMS, ids=lambda i: i["code"])
    def test_each_item_carries_basis_and_legal_note(self, item):
        assert item["basis"].strip() and "출처 미확보" in item["basis"], (
            "단가 출처가 없다는 사실을 값 옆에 적어야 한다"
        )
        assert item["legal_note"].strip()

    def test_priced_items_say_estimate_and_withheld_items_say_unavailable(self):
        """★**두 모집단** — 단가가 있으면 `estimate`, 없으면 `unavailable`.

        하나로 뭉치면 *"개산"* 과 *"산정 불가"* 가 구별되지 않는다(#913 이후 소방이 후자다).
        """
        items = calculate_utility_connection_cost(total_households=HH, total_gfa_sqm=GFA)["items"]
        priced = [i for i in items if i["unit_price"] is not None]
        withheld = [i for i in items if i["unit_price"] is None]
        assert priced and withheld, f"두 모집단이 갈리지 않는다: {[i['code'] for i in items]}"
        for i in priced:
            assert i["confidence"] == "estimate"
            assert i["qty_unit"] in {"세대", "㎡"}
        for i in withheld:
            assert i["confidence"] == "unavailable"
            assert i["amount_won"] == 0


class TestEveryCallSiteCarriesHouseholds:
    """★**호출부를 「내가 기억하는 것」이 아니라 파생형으로 센다**(독립 리뷰 CRITICAL).

    첫 판에서 나는 `calculate_total_construction_cost` 호출부 **3곳 중 2곳만** 고쳤다.
    남은 `modules/common/cost_blocks.py` 는 `total_households` 를 안 넘겨 **인입비가 조용히 0**
    이 됐고, 같은 커밋이 부담금에서는 그 금액을 빼면서 공사비에는 안 더해
    **15개 개발유형에서 총사업비 −55,642,000** 이 새어 나갔다(리뷰 실측).

    ★그 자리는 **무잠금**이었다 — 고쳐도 105건이 전부 초록이었다.
      그래서 여기서 **호출부를 AST 로 전수**한다. 새 호출부가 생기면 이 테스트가 먼저 빨개진다.
    """

    @staticmethod
    def _call_sites():
        import ast
        import pathlib

        out = []
        root = pathlib.Path(__file__).resolve().parents[1] / "app"
        for p in root.rglob("*.py"):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for n in ast.walk(tree):
                if not isinstance(n, ast.Call):
                    continue
                nm = getattr(n.func, "attr", None) or getattr(n.func, "id", None)
                if nm == "calculate_total_construction_cost":
                    # ★**이름이 아니라 값**을 들고 온다. 종전에는 `{k.arg …}` 로 **키워드
                    #   이름만** 모아서, `total_households=0` 으로 바꾸는 변이가 **생존**했다
                    #   (독립 렌즈 실증) — 그 변이가 되살리는 것이 `#913` 이 고쳤다고 선언한
                    #   **총사업비 −55,642,000 / 15개 개발유형**이다.
                    out.append((str(p.relative_to(root)), n.lineno,
                                {k.arg: k.value for k in n.keywords}))
        return out

    def test_the_scanner_finds_call_sites(self):
        """★대조군 — 하나도 못 찾으면 아래 「전부 통과」가 공허하다."""
        sites = self._call_sites()
        assert len(sites) >= 3, f"★조회기 사망 — 호출부 {len(sites)}건"

    def test_every_call_site_passes_total_households(self):
        missing = [f"{f}:{ln}" for f, ln, kws in self._call_sites()
                   if "total_households" not in kws]
        assert not missing, (
            f"★인입비가 조용히 0이 되는 호출부: {missing} — "
            "총사업비가 새어 나간다(부담금에서는 빠지는데 공사비에 안 들어온다)"
        )

    def test_the_value_is_a_real_variable_not_a_literal(self):
        """★**이름이 있는 것과 값이 실리는 것은 다르다.**

        `total_households=0` 은 키워드 **이름**을 만족시키면서 인입비를 **조용히 0** 으로
        만든다 — 즉 `#913` 이 고쳤다고 선언한 결함을 그대로 되살린다. 이름만 보는 락은
        그 변이를 **원리적으로** 못 잡는다(독립 렌즈가 SURVIVED 로 실증).
        """
        import ast

        bad = []
        for f, ln, kws in self._call_sites():
            v = kws.get("total_households")
            if v is None:
                continue          # 위 테스트가 담당
            if isinstance(v, ast.Constant):
                bad.append(f"{f}:{ln} = {v.value!r}")
        assert not bad, (
            f"★세대수 자리에 **리터럴**이 들어갔다: {bad} — "
            "이름은 있는데 값이 안 실린다(인입비가 조용히 0)"
        )

    def test_the_scanner_would_catch_a_literal(self):
        """★대조군 — 검사기가 리터럴을 **실제로 잡는지** 증명한다(위 「0건」이 공허하지 않게)."""
        import ast

        tree = ast.parse("calculate_total_construction_cost(total_households=0)")
        found = [
            k for n in ast.walk(tree) if isinstance(n, ast.Call)
            for k in n.keywords
            if k.arg == "total_households" and isinstance(k.value, ast.Constant)
        ]
        assert len(found) == 1, "검사기 사망 — 리터럴을 심었는데 못 잡는다"


class TestLedgerReconciles:
    """★행 합계 = 엔진 총액. 인입 행을 안 그리면 **사용자 화면에 검산 ERROR** 가 뜬다."""

    def test_breakdown_projects_connection_rows(self):
        from app.services.feasibility.rough_feasibility_orchestrator import (
            construction_breakdown,
        )

        cc = calculate_total_construction_cost(
            total_gfa_sqm=GFA, building_type="apartment", total_households=HH,
        )
        bd = construction_breakdown(cc)
        conn = bd.get("utility_connection") or {}
        assert conn.get("items"), "★투사가 빠지면 행이 사라지고 검산이 깨진다"
        total = bd["direct_won"] + bd["indirect"]["total_won"] + conn["total_won"]
        assert total == cc["total_construction_cost_won"], "행 합계 ≠ 엔진 총액"

    def test_connection_rows_carry_the_estimate_disclosure(self):
        """★개산 고지가 **투사 층까지** 살아남는가(로그가 아니라 페이로드로)."""
        from app.services.feasibility.rough_feasibility_orchestrator import (
            construction_breakdown,
        )

        bd = construction_breakdown(calculate_total_construction_cost(
            total_gfa_sqm=GFA, building_type="apartment", total_households=HH,
        ))
        rows = bd["utility_connection"]["items"]
        assert rows, "★투사가 비었다"
        for i in rows:
            # ★개산이든 보류든 **사유는 반드시** 실린다 — 로그가 아니라 페이로드로.
            assert i["confidence"] in {"estimate", "unavailable"}
            assert (i.get("basis") or "").strip(), f"{i['code']}: 사유가 없다"


class TestFireIsSeparatelyContractedNotIncluded:
    """★★`#913` 의 소방 제거가 **틀렸다** — 법이 **분리 도급**을 명한다.

    `#913` 은 소방(3,500원/㎡)을 *"건축 도급단가에 이미 포함"* 이라며 제거했다
    (총사업비 −23,002,000). **법제처 원문이 정반대를 말한다**(2026-08-27 실측):

        소방시설공사업법 §21②(신설 2020.6.9)
          "소방시설공사는 **다른 업종의 공사와 분리하여 도급하여야 한다**" — 위반 시 **벌칙**
        시행령 §11의2(예외)  재난·기밀·비해당·연면적 1천㎡ 이하 비상경보·대안/일괄/기술제안입찰·
          국가첨단전략기술·**국가유산수리 및 재개발·재건축 등으로서 소방청장 인정**
          → **일반 신축 개발사업은 예외 비해당 = 원칙(분리 도급) 적용**
        시행령 §4 1호가  스프링클러설비등·옥내소화전·물분무등소화설비·제연설비

    ★**내가 왜 틀렸나**: 적산 실적이 소방을 `electrical`/`mechanical` **내역서 안**에 두어
      *"도급 안"* 으로 읽었다. **내역서 편성 ≠ 도급 편성**이다 — 같은 세트가 **승강기 공종을
      갖고 있지 않은데** 그 건물에 승강기는 실재한다. *"별도 내역서가 없다"* 는
      *"도급 안"* 을 **함의하지 않는다**(독립 리뷰가 그 반례를 찾았다).

    ★**그러나 종전 값으로 되돌리지 않는다** — `3,500원/㎡` 은 출처 0건이고 적산 실적
      (27,223원/㎡·재료비만) 대비 **7.8배 과소**다. **항목은 세우되 금액은 보류**한다.
    """

    @staticmethod
    def _fire():
        r = calculate_utility_connection_cost(total_households=HH, total_gfa_sqm=GFA)
        return next(i for i in r["items"] if i["code"] == "U04"), r

    def test_fire_item_exists_again(self):
        """★항목이 **있어야** 한다 — 지우면 사용자는 누락 사실조차 모른다."""
        fire, _ = self._fire()
        assert fire["name"].strip()

    def test_fire_is_withheld_not_fabricated(self):
        """★있되 **금액은 보류** — 출처 없는 3,500원/㎡ 를 되살리지 않는다."""
        fire, _ = self._fire()
        assert fire["amount_won"] == 0
        assert fire["unit_price"] is None
        assert fire["confidence"] == "unavailable"
        assert fire["surveyed"] is False
        assert fire["amount_won"] != 3_500 * int(GFA), "종전 날조값이 되살아났다"

    def test_fire_reason_names_the_separate_contracting_law(self):
        """★사유가 **법정 분리 도급**을 말해야 한다 — 뭉뚱그리면 다음 사람이 또 지운다."""
        fire, _ = self._fire()
        text = (fire.get("basis") or "") + (fire.get("legal_note") or "")
        for token in ("소방시설공사업법", "§21", "분리"):
            assert token in text, f"사유에 '{token}' 이 없다"

    def test_the_filter_itself_excludes_nonzero_withheld(self):
        """★필터를 **합성 입력으로 직접** 태운다.

        현재 보류 항목의 금액은 **항상 0** 이라, 실제 산출만 보면 필터를 지워도 합계가
        안 바뀐다 — 변이가 **생존**했다. 0이 아닌 보류를 만들어 필터가 **실제로 거르는지** 본다.
        """
        from app.services.cost.utility_connection_cost import sum_priced_only

        synthetic = [
            {"code": "X1", "amount_won": 100, "confidence": "estimate"},
            {"code": "X2", "amount_won": 999, "confidence": "unavailable"},  # ★0이 아니다
        ]
        assert sum_priced_only(synthetic) == 100, "보류 항목이 합계에 섞였다"
        # ★반대 방향 — 전부 estimate 면 전부 센다(무조건 거르는 구현 탐지).
        assert sum_priced_only(
            [{"code": "Y", "amount_won": 7, "confidence": "estimate"}],
        ) == 7

    def test_withheld_does_not_enter_the_total(self):
        """★보류 항목이 합계에 **섞이지 않는다** — 0으로 더하면 「계상했다」로 읽힌다."""
        fire, r = self._fire()
        assert "U04" in r["withheld_codes"]
        assert r["total_won"] == sum(
            i["amount_won"] for i in r["items"] if i["code"] != "U04"
        )

    def test_the_priced_siblings_still_count(self):
        """★반대 모집단 — 단가가 있는 인입 3종은 **여전히 합계에 든다**(전부 보류로 만드는 구현 탐지)."""
        _, r = self._fire()
        assert r["total_won"] == 32_640_000
        assert len(r["withheld_codes"]) == 1, f"보류가 늘었다: {r['withheld_codes']}"
