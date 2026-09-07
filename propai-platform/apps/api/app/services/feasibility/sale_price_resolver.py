"""분양단가(원/평, **공급면적 기준**) 결정 — 전 경로 공용 SSOT.

★**왜 별도 모듈인가**: 이 산식이 `rough_feasibility_orchestrator` 안에 사적으로 있어서,
  같은 일을 하는 다른 경로가 **각자 다른 산식**을 갖게 됐다. 라이브 실측(2026-09-04,
  같은 주소 5곳)에서 두 구현이 **0.79~1.56 배로 어긋났고, 방향이 지역마다 뒤집혔다** —
  한쪽이 일관되게 높은 것이 아니라 **축이 다섯 개 달랐다**:

    기간 8↔3개월 · 범위 동↔시군구 · 집계 **중앙값↔평균** · 해제거래 필터 유무 ·
    ★★**기준: 「공급 분양가」(전용률×프리미엄 변환) ↔ 「전용 매매가 그대로」**

  마지막 것이 결정적이다. `market_revaluation_service` 가 **공급 기준 신축 분양가**
  (`regional_pricing`)와 **전용 기준 기존아파트 매매가**를 **가중 블렌딩**하고 있었고,
  그 값이 `project_pipeline` 에서 **지역 테이블보다 우선해** 분양가로 쓰였다.
  (강남 +56% · 해운대 −21%. ★두 오류가 부분 상쇄돼 **부호가 일정하지 않았고, 그래서 조용했다.**)

★**여기 있는 것이 정본이다.** 새 소비처는 이 모듈을 부르고, **자기 산식을 만들지 않는다.**

★단위 계약: 반환값은 **원/평 · 공급(분양가능)면적 기준 · 신축 분양가**다.
  실거래는 **전용면적 기준 매매가**이므로 `×전용률 × 신축프리미엄` 으로 환산한다.
  이 계약을 어기면 소비처가 다른 단위끼리 섞는다 — 그것이 위 결함이었다.
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ★지연 임포트 — `feasibility_service_v2` 는 무겁고, `regional_pricing` 은 순환을 피한다.
#   모듈 최상단에서 끌면 이 SSOT 를 부르는 쪽마다 그 무게가 따라온다.
def _svc() -> Any:
    from app.services.feasibility.feasibility_service_v2 import FeasibilityServiceV2
    global _SERVICE
    try:
        return _SERVICE
    except NameError:
        _SERVICE = FeasibilityServiceV2()
        return _SERVICE


_BUILDING_TO_MOLIT_PROP: dict[str, str] = {
    "apartment": "apt",
    "officetel": "officetel",
    "office": "commercial",     # 업무시설 = 비주거용(상업) 실거래
    "house": "house",           # 단독·다가구
    "townhouse": "villa",       # 연립·다세대(타운하우스)
}

def _exclusive_ratio_for(dev_type: str, building_type: str | None) -> tuple[float, str]:
    """전용률(전용/공급) — **정본은 `unit_standards`** 다. 평면 상수를 쓰지 않는다.

    ★왜: `unit_standards` 는 **자신을 유일 정본이라 선언**하고 *"두 소비처가 서로 다른
      전용률 테이블을 각자 보유해 세대수가 30% 안팎 어긋나던 이중정의 결함(구 «40 vs 323»
      버그 클래스)"* 을 막으려 존재한다. `_JEONYULRYUL = 0.747` 평면 상수는 **정확히 그
      이중정의**였다 — 정본 대비 오피스텔·지산 **+35.8%**, 단독 **−12.1%**
      (라이브 실측 2026-09-05 · 정본 15유형 전수).

    ★★이 결함은 **내 앞 커밋이 활성화시켰다.** 종전 파이프라인은 `dev_type` 이 **항상 M01**
      이라 0.747 ≈ 0.75 로 **우연히 맞았다**(괴리 −0.4%). `building_type` 을 실제로 넘기게
      고치자 «물건종별은 유형을 따르는데 전용률은 아파트 고정» 인 비정합이 드러났다.
      **개선이 잠자던 결함을 깨웠다.**

    ## ★축은 `dev_type` 이다 — `building_type` 으로 정하지 않는다

    정본은 `dev_type`(M01~M15) 축이고, `building_type` 은 **여러 dev_type 이 공유**한다
    (apartment ← M01 0.75 · M03 0.65 · M05 0.70 · M07 0.60). 그래서 전용률을 유일하게
    정하지 못한다.

    ★**「최소=안전측」을 썼다가 라이브 측정으로 기각했다**: apartment 가 0.75 → **0.60** 이
      되어 **가장 흔한 경로가 −19.7%**(노원 29.4M → 23.7M). 주상복합(M07) 값을 일반
      아파트에 적용하는 것이라 **보수적인 게 아니라 틀린 것**이다.
      *안전측은 값을 모를 때의 규약이지, **아는 값을 버리는 근거가 아니다.***

    → `dev_type` 의 정본값을 쓴다. `building_type` 이 그와 **어긋나면** 값을 바꾸지 않고
      **근거 문자열에 그 사실을 적는다**(부채를 숨기지 않는다 — 진짜 처방은 호출부가
      `dev_type` 을 갖는 것이고, 파이프라인은 아직 못 갖는다).
    """
    from app.services.feasibility.unit_standards import get_exclusive_ratio

    ratio = get_exclusive_ratio(dev_type)
    # ★★**같은 함수 안에서 한 축은 정규화하고 형제 축은 원값을 썼다.**
    #   `building` 은 `_canonical_building()` 을 거치는데 여기는 안 거쳐서,
    #   프로덕션 입력(**한국어**)이 영어 정규 키와 비교돼 **100% 「불일치」**로 찍혔다.
    #   실측: `('M01','아파트')` → 실제로는 **일치**인데 불일치라 적었다.
    #   그 문자열은 `basis` → `note` → `sources` → 원장(`market_revaluation`)으로 **영속 기록**된다.
    #   ★*위양성도 결함이다* 를 이 PR 에서 세 번 인용하고 같은 함수 안에서 어겼다.
    bt = _canonical_building(building_type)
    note = f"전용률 {ratio}(정본·유형 {dev_type})"
    raw = (building_type or "").strip()
    if raw and not bt:
        # ★★**「모르는 표기」와 「안 넘김」이 종전엔 바이트 단위로 같은 산출물**을 냈다.
        #   그 값은 조용히 버려지고 `prop_type` 이 `apt` 로 떨어지는데 **근거에 흔적이 없다**
        #   — 판매시설·업무시설 프로젝트가 아파트 실거래로 값이 매겨져도 원장을 보고
        #   되짚을 수 없었다(§유료 규율 4: *실패는 전용 필드로 자기를 구별한다*).
        #   ★역설이었다: 「불일치」는 **인식된** 유형에만 붙고, **정보를 실제로 버린**
        #     경우엔 아무것도 안 붙었다.
        note += f" ★건물유형 '{raw}' 를 알지 못해 **유형 축으로 폴백**(표기 미등록)"
    elif bt and bt != _safe_building_type(_svc(), dev_type):
        # ★값을 바꾸지 않는다 — 대신 **불일치를 표면까지** 싣는다.
        note += f" ★건물유형 {bt} 와 불일치 — 전용률은 유형 축을 따른다(호출부가 dev_type 미보유)"
    return ratio, note


# ── 축 경계: 전용 평당가 → **공급 평당가** ─────────────────────────────────────
#
# ★★2026-09-07 사용자 확인 — ***"모든 분양가의 표기는 공급면적 기준이다."***
#   정본 데이터로도 확증했다: 청약홈 모델 행은 `price_man` 을 **`supply_area_m2`** 와
#   같은 행에 싣는다(`house_ty`(전용)와 짝지어지지 않는다).
#
# ★그런데 이 저장소의 평당가 필드는 **단위는 이름에 담고 기준면적은 안 담는다**
#   (실측: `per_pyeong_10k`·`per_pyeong_won`·`sale_price_per_pyeong_man` … 15종,
#   축을 이름에 담은 것 **0종**). 그래서 전용값과 공급값이 **같은 모양**이라 섞여도
#   아무것도 막지 못한다. 전면 개명은 소비처가 너무 많아 회귀 위험이 크다.
#   → **개명 대신 경계를 좁힌다.** 전용→공급 환산은 이 함수 **하나만** 한다.
#
# ★실해: 전용 기준 평당가를 공급 평형에 곱하면 착시가 정확히 이 크기로 난다 —
#     전용평당 2,436만 × **공급** 34평 = 8.28억   (실거래는 6.13~7.28억)
#   사용자가 신고한 «8억» 이 이 자리에서 나올 수 있다.

# 비교사례 물건종별 → **사례의** 관례 전용률(전용/공급).
#
# ★★2026-09-07 근본 정정 — 종전에는 **대상의 `dev_type` 전용률**을 곱했다. 그런데
#   비교사례는 **아파트 분양권**이고 대상은 주상복합(M07 0.60) 이라, *"아파트가 거래된
#   전용 평당가를, 우리 주상복합 전용률로 나눈 공급면적에 매긴다"* 는 뜻이 된다.
#   감정평가 논리는 반대다 — **사례의 기준으로 시장가를 뽑고**, 대상 차이는 **별도 보정**이다.
#
# ★값의 정본은 **이 저장소 자신**이다: `suggest._REF_SUPPLY_SQM = 112.4`("84타입 표준
#   공급면적") → 84/112.4 = **0.747**, 공급 **34.0평**. 사용자 확인(*"전용 84㎡는 공급
#   34평형"*)과 일치하고, 빌리브센트하이 실측 공급평당 1,803만원과 **+0.9%**로 맞는다.
#
# ★★**아파트 계열만 넣는다.** 오피스텔·단독·상업의 관례 전용률은 **재보지 않았다** —
#   지어내면 그 숫자가 다음 사람에게 근거처럼 읽힌다. 미등록 종별은 **현행 동작을 그대로
#   유지**(대상 `dev_type` 정본)하고, 그 사실을 근거에 적는다.
# 국민평형 전용면적(㎡) — 관례 전용률의 분자. `_REF_SUPPLY_SQM`(112.4)이 분모다.
_STANDARD_EXCLUSIVE_SQM = 84.0


def _apt_comparable_ratio() -> float:
    """아파트 계열 사례 관례 전용률 — **리터럴을 쓰지 않고 표준 공급면적에서 파생**한다.

    ★`0.747` 을 여기 또 적으면 이 저장소의 **다섯 번째 사본**이 된다(실측: `_JEONYULRYUL`
      0.747 · `area-notation` 0.75 · `PricingBandPanel` 0.747 …). 사본은 **값이 갈릴 때
      조용하다** — 프론트 안에서만 0.75/0.747 두 값이 돌아 84㎡ 기준 공급면적이
      112.0㎡(33.88평) ↔ 112.4㎡(34.02평) 로 갈렸다.
    → 「84타입 표준 공급면적」 하나만 정본으로 두고 **나눠서 얻는다.**
    """
    from app.services.sales.pricing.suggest import _REF_SUPPLY_SQM
    return round(_STANDARD_EXCLUSIVE_SQM / _REF_SUPPLY_SQM, 3)


_COMPARABLE_SUPPLY_RATIO: dict[str, float] = {
    "apt": _apt_comparable_ratio(),
    "apt_presale": _apt_comparable_ratio(),
}


def _to_supply_per_pyeong_won(
    exclusive_per_pyeong_man: float,
    *,
    dev_type: str,
    building_type: str | None,
    prop_type: str,
    premium: float = 1.0,
) -> tuple[int, str]:
    """전용 기준 평당가(만원) → **공급 기준 평당가(원)**.

    Returns:
        (원/평(공급), 근거 조각) — 근거 조각에는 **반드시 「공급면적 기준」이 들어간다.**
        호출부가 그 문구를 각자 쓰면 한 곳이 빠지고, 빠진 그 곳이 오독을 만든다.

    ★`premium` 은 신축 프리미엄. 분양권 전매는 **이미 신축가**라 1.0 이다.
    """
    subj_ratio, subj_note = _exclusive_ratio_for(dev_type, building_type)
    comp_ratio = _COMPARABLE_SUPPLY_RATIO.get(prop_type)
    if comp_ratio is not None:
        ratio = comp_ratio
        note = f"사례 전용률 {comp_ratio}(물건종별 {prop_type} 관례)"
        # ★대상 유형이 다르면 **값을 바꾸지 않고 그 사실을 싣는다.** 얼마나 보정해야
        #   하는지는 재보지 않았다 — 사용자가 판단할 재료만 준다(무날조).
        if abs(subj_ratio - comp_ratio) > 0.02:
            note += (
                f" ※대상 유형 {dev_type} 의 정본 전용률은 {subj_ratio} 로 사례와 다르다"
                " — 유형 차이 보정은 **하지 않았다**(보정계수 미측정)"
            )
    else:
        ratio = subj_ratio
        note = f"{subj_note} ※{prop_type} 의 사례 관례 전용률 미등록 — 대상 유형 축 사용"
    won = int(round(exclusive_per_pyeong_man * ratio * premium * 10000))
    if premium != 1.0:
        note += f" × 신축 프리미엄 {premium}"
    # ★이 문구는 계약이다 — 잠금이 이 문자열의 **존재**가 아니라 **모든 경로 통과**를 본다.
    note += " → **공급면적 기준** 평당가"
    return won, note


def _safe_building_type(svc: Any, dev_type: str) -> str:
    try:
        return svc._get_building_type(dev_type)
    except Exception:  # noqa: BLE001
        return ""


#: 화면 표기(한국어) → 정규 키. ★파이프라인은 **표시 문자열**을 `building_type` 으로 넘긴다
#: (`project_pipeline.py:1611-1620`: "아파트"·"공동주택"·"근린생활시설"·"다세대주택").
#: 그런데 `_BUILDING_TO_MOLIT_PROP` 키는 **영어 정규 키**다 — 전부 미스한다.
#: ★★그리고 한국어 문자열이 **truthy** 라 `_get_building_type(dev_type)` 폴백까지 **억제**했다:
#:   **인자를 넘기는 것이 안 넘기는 것보다 나빴다**(실측: `building_type='공동주택', dev_type='M09'`
#:   → `prop_type='apt'` / `building_type=None, dev_type='M09'` → `prop_type='commercial'`).
#: ★내 앞 커밋의 주석은 이 축이 *"실제로 쓰인다"* 고 **단정했다** — 재 보지 않고 쓴 거짓이다.
_DISPLAY_TO_BUILDING: dict[str, str] = {
    "아파트": "apartment",
    "공동주택": "apartment",
    "다세대주택": "townhouse",
    "연립주택": "townhouse",
    "오피스텔": "officetel",
    "근린생활시설": "office",
    "업무시설": "office",
    "단독주택": "house",
}


def _canonical_building(building_type: str | None) -> str:
    """표시 문자열이든 정규 키든 **정규 키로** 돌린다. 못 알아보면 `""`(폴백을 막지 않는다).

    ★`""` 를 돌리는 것이 핵심이다 — 모르는 값을 그대로 통과시키면 그것이 truthy 라
      `dev_type` 폴백을 **억제**하고, 결과적으로 **넘길수록 나빠진다.**
    """
    bt = (building_type or "").strip()
    if not bt:
        return ""
    if bt in _BUILDING_TO_MOLIT_PROP:
        return bt
    return _DISPLAY_TO_BUILDING.get(bt, "")


def _new_build_premium() -> float:
    """신축 분양 프리미엄(기존 재고 매매가 → 신축 분양가). **정의는 `pricing.suggest` 하나다.**

    ★접근자를 두는 이유: 다른 모듈이 `1.15` 를 다시 적으면 그것이 **두 번째 산식**이 되고,
      이 PR 이 고치는 결함이 정확히 그 형태다. 상수를 복제하지 말고 **이 함수를 불러라.**
    """
    from app.services.sales.pricing.suggest import _PREMIUM
    return float(_PREMIUM["base"])


#: 실거래 표본 하한. 미만이면 실거래를 **쓰지 않고** 지역 시세로 폴백한다.
#: ★n=1 도 중앙값을 내므로, 하한이 없으면 「실거래 기반」이라는 라벨이 날조가 된다.
_MIN_TRADE_SAMPLES = 5

async def _sigungu5_from_address(address: str) -> str | None:
    """주소 → VWorld 지오코딩 → PNU → 시군구 5자리(법정동시군구코드). 실패 시 None(가짜 코드 금지).

    ★HIGH-1: 주변 실거래(MOLIT) 조회는 site_id/db 없이 시군구 5자리 코드만 있으면 된다.
    현장(sales site) 연결이 없어도 이 함수로 시군구를 스스로 확보해 실거래를 1순위로 쓴다.
    """
    if not address:
        return None
    try:
        from app.services.external_api.vworld_service import VWorldService
        from apps.api.integrations.region_codes import pnu_to_bcode

        geo = await VWorldService().geocode_address(address)
        pnu = (geo or {}).get("pnu") or ""
        conv = pnu_to_bcode(pnu)          # (시군구 5자리, 법정동 5자리) — 아니면 None
        if conv:
            return conv[0]
        # PNU가 짧아도 앞 5자리가 숫자면 시군구 코드로 사용(자체 충족).
        if len(pnu) >= 5 and pnu[:5].isdigit():
            return pnu[:5]
    except Exception as e:  # noqa: BLE001 — 지오코딩 실패는 지역 시세로 폴백(무중단)
        logger.warning("분양단가 실거래용 지오코딩 실패 — 지역 시세 폴백: %s", str(e)[:120])
    return None


async def _trade_sale_price_per_pyeong(
    *, dev_type: str, address: str, sigungu5: str | None = None,
    building_type: str | None = None,
    cases_out: list[dict[str, Any]] | None = None,
) -> tuple[int, str, str, None, int] | None:
    """주변 실거래(MOLIT) 직접 조회 → 분양단가(원/평, 공급면적). site_id 불필요(★HIGH-1).

    주소를 지오코딩해 시군구 5자리를 얻고, 검증된 공용 헬퍼 _trade_per_pyeong으로 동·시군구
    전용 평당가 중앙값을 구한다(재구현 0). 실거래는 '전용면적' 기준이므로, 개략수지가 쓰는
    '공급(분양가능)면적' 기준으로 환산(×전용률)하고 신축 분양 프리미엄(기준안 1.15)을 곱한다
    — sales site 연결 경로(suggest_base_price base tier)와 동일 산식으로 일치시킨다.

    표본 부족(_MIN_TRADE_SAMPLES 미만)·조회 실패면 None(호출부가 지역 시세로 폴백).
    """
    # ★호출부가 이미 시군구를 알면 **지오코딩을 하지 않는다.**
    #   ★★이 인자가 없던 판이 **VWorld 장애를 분양가 붕괴로 전파**했다(적대 리뷰 C-1 실측):
    #     파이프라인은 PNU 에서 `lawd` 를 이미 갖고 있는데 그것을 안 넘겨,
    #     지오코딩이 실패하면 실거래 출처가 통째로 빠지고 **−39%**(36.05M → 22.00M) 로
    #     하드코딩 테이블에 떨어졌다. 그러면서 `sale_price_source` 는 계속 `market_blended`
    #     라고 말했다 — **블렌딩이 안 됐는데 됐다고 말하는 것**이다.
    #   → 주입이 1순위, 지오코딩은 **폴백**이다.
    # ★주입값을 **검증한다.** 형제 셋이 이미 그렇게 한다
    #   (`_avm_source`: `len==5 and isdigit` · `_molit_avg_per_pyeong`: `len < 5 → None` ·
    #    같은 파일 `_sigungu5_from_address`: `pnu[:5].isdigit()`).
    #   ★검증이 없으면 `'1168'`·`'abcde'` 같은 값이 **truthy 라 지오코딩 폴백을 억제**해
    #     회복 경로를 막는다(적대 리뷰 MAJOR-5).
    _inj = (sigungu5 or "").strip()
    # ★★`isdigit()` 만으로는 **전각을 통과시킨다**(`'１２３４５'.isdigit() is True`).
    #   이 저장소는 그 사고를 **이 파일을 감시하는 래칫에** 적어 뒀다 —
    #   *"`sigungu_cd='１２３４５'` 가 MOLIT 건축물대장 API 인자로 나갔다"*.
    #   그런데 나는 «형제 셋이 이미 검증한다» 며 **가장 약한 형제**를 근거로 댔다
    #   (정본 `is_valid_pnu` 계열은 `isascii()` 로 막는다 — §29 의 가장 비싼 형태).
    #   ★내 행위 락이 이것을 잡았다(전각을 넣었더니 폴백이 억제됐다).
    _ok = len(_inj) == 5 and _inj.isascii() and _inj.isdigit()
    sigungu5 = _inj if _ok else await _sigungu5_from_address(address)
    if not sigungu5:
        return None
    try:
        # 검증된 실거래 헬퍼·환산상수 재사용(SSOT — 값 발산 방지).
        from app.services.sales.pricing.suggest import (
            _PREMIUM,
            _extract_dong,
            _trade_per_pyeong,
        )

        # ★호출부가 **건물유형을 이미 알면** 그것을 쓴다 — `dev_type` 을 거쳐 되돌리지 않는다.
        #   파이프라인이 그 예다: `design.building_type` 은 실재하고 `development_type` 은 **없다**
        #   (적대 리뷰 M-1 — 없는 필드를 `getattr` 로 읽어 **항상 M01** 이었다).
        # ★정규화를 **경계에서** 한다. 모르는 표기는 `""` 가 되어 `dev_type` 폴백이 산다.
        building = _canonical_building(building_type) or _svc()._get_building_type(dev_type)
        prop_type = _BUILDING_TO_MOLIT_PROP.get(building, "apt")
        dong = _extract_dong(address)

        # ★★**분양가의 정본은 분양권 전매다**(2026-09-06 · 사용자 신고로 발견).
        #   기존 `apt`(매매) API 에는 **미준공 분양 단지가 원리적으로 안 들어온다** —
        #   실측: 화도읍 469건 중 「빌리브센트하이」 **0건**인데 분양권 API 로는 **17건**.
        #   그리고 값이 크게 다르다(마석우리 · 12개월):
        #       분양권      전용 2,491 / 공급 1,868 만원/평
        #       매매(혼합)  전용 1,391 / 공급 1,044             → **-44%**
        #   ★사용자가 «주변 신축 분양이 평당 2,000에 육박하는데 왜 1,200인가» 로 신고했고,
        #     근본 원인은 **연식 보정이 아니라 데이터원**이었다.
        #   ★분양권은 이미 **신축 가격**이므로 신축 프리미엄을 **곱하지 않는다**(이중 계상).
        pre = None
        if prop_type == "apt":
            try:
                # ★사례를 **같은 수집 루프에서** 함께 받는다(재수집 0회 — `comparables.py` 가
                #   명문으로 요구하는 규율). 목록화·선택은 이 사례를 소비한다.
                pre = await _trade_per_pyeong(
                    sigungu5, dong, "apt_presale", collect_cases=cases_out is not None)
            except TypeError as e:
                # ★★**시그니처 불일치를 「조회 실패」로 위장하지 않는다.**
                #   내 테스트 스텁이 `collect_cases` 를 안 받아 `TypeError` 가 났고,
                #   그것이 `except Exception` 에 삼켜져 **분양권 경로가 조용히 죽고**
                #   매매로 폴백했다(값이 −44% 인 채로). 락 4건이 잡았지만, 실서비스에서는
                #   **아무도 모른 채 낮은 값이 나갔을 것**이다.
                #   → 프로그래밍 오류는 **error 로 크게** 남긴다(무중단은 유지).
                logger.error(
                    "분양권 조회 시그니처 불일치 — **배선 오류**이지 조회 실패가 아니다: %s",
                    str(e)[:140])
                pre = None
            except Exception as e:  # noqa: BLE001 — 조회 실패는 매매로 폴백(무중단)
                logger.warning("분양권 전매 조회 실패 — 매매로 폴백: %s: %s",
                               type(e).__name__, str(e)[:100])
                pre = None
        if pre:
            pd_med, pd_n = pre["dong"]["median"], pre["dong"]["n"]
            ps_med, ps_n = pre["sigungu"]["median"], pre["sigungu"]["n"]
            # ★상위 대역은 **중앙값과 같은 범위(scope)** 에서 와야 한다 — 동 중앙값에
            #   시군구 상위값을 붙이면 두 모집단이 섞여 근거가 거짓이 된다.
            if pd_med and pd_n >= _MIN_TRADE_SAMPLES:
                p_scope, p_med, p_n = "동", int(pd_med), int(pd_n)
                p_upper_key = "dong_upper"
            elif ps_med and ps_n >= _MIN_TRADE_SAMPLES:
                p_scope, p_med, p_n = "시군구", int(ps_med), int(ps_n)
                p_upper_key = "sigungu_upper"
            else:
                p_scope = None
                p_upper_key = None
            if p_scope:
                price, ratio_note = _to_supply_per_pyeong_won(
                    p_med, dev_type=dev_type, building_type=building_type,
                    prop_type="apt_presale")
                # ★★2026-09-07 사용자 신고 — *"분양가와 실거래가가 다르고 실거래가는
                #   8억이 넘는다"*. 라이브 원문을 열어 **이 앵커가 무엇인지**를 재고 근거에
                #   싣는다. 종전 문장은 값만 말해서, 읽는 사람이 **「현재 시세」로 오독**했다
                #   (내가 먼저 오독했다 — 표본의 한 점을 시세로 승격시켰다).
                #   실측(빌리브센트하이 7건·화도읍): 신고 6.13~7.28억 · 조회 최신월 **0건**.
                _dg = (pre.get("diagnostics") or {}) if isinstance(pre, dict) else {}
                _upper = (pre.get(p_upper_key) or {}) if p_upper_key else {}
                _notes = []
                if _dg.get("cancelled_excluded_n"):
                    _notes.append(f"해제거래 {_dg['cancelled_excluded_n']}건 제외")
                if _dg.get("direct_deal_n"):
                    # 제외하지 **않았다** — 밝히기만 한다(측정된 편향 +0.1%로 근거 부족).
                    _notes.append(f"직거래 {_dg['direct_deal_n']}건 포함")
                if _dg.get("latest_ym") and not _dg.get("latest_ym_rows"):
                    _notes.append(
                        f"★{_dg['latest_ym']} 신고 0건 — 신고 지연(약 30일)으로 "
                        "최신 시세가 아직 반영되지 않았을 수 있다")
                if _upper.get("p75"):
                    _notes.append(
                        f"같은 표본 상위 25% {_upper['p75']:,}만원/평"
                        + (f"·최고 {_upper['max']:,}만원/평" if _upper.get("max") else "")
                        + "(전용) — 신규 분양은 시장 상위 대역을 겨냥한다")
                basis = (
                    f"분양권 전매(MOLIT) {p_scope} 중앙값 {p_med:,}만원/평"
                    f"(전용, 표본 {p_n}건·최근 12개월) × {ratio_note}"
                    "(신축 프리미엄 미적용 — 분양권은 이미 신축가·물건종별 apt_presale)"
                    # ★이 앵커가 **무엇인지** 말한다 — 호가가 아니라 «신고된 실거래»이고,
                    #   중앙값이라 상위 대역이 보이지 않는다.
                    " ※실거래 **신고** 기준(호가 아님)"
                    + ("" if not _notes else " · " + " · ".join(_notes))
                )
                # ★채택한 경로의 사례만 내보낸다 — 폴백으로 내려가면 그 사례는 근거가 아니다.
                if cases_out is not None:
                    cases_out.extend(pre.get("cases") or [])
                return price, "분양권 전매(MOLIT)", basis, None, p_n

        pp = await _trade_per_pyeong(sigungu5, dong, prop_type)

        # ★★**2-b 단: 최근 건축년도(신축) 실거래**(2026-09-06 · 사용자 결정).
        #   «청약홈/분양권 → 없으면 가장 최근 건축년도 실거래»의 그 단이다.
        #   ★신축 분양가의 비교 대상은 신축이다. 혼합 표본을 쓰면 구축이 끌어내린다 —
        #     실측(화도읍 469건 전용 만원/평): 전체 1,391 ↔ 신축(≤10년) **1,846** = **+33%**
        #     (21~30년 구축이 **202건 최다**라 중앙값을 지배한다).
        #   ★신축 표본에도 **신축 프리미엄은 적용한다** — 매매가에서 분양가로 가는
        #     환산이지 «구축→신축» 보정이 아니기 때문이다(분양권 단과 다른 이유).
        r_d, r_s = pp.get("recent_dong") or {}, pp.get("recent_sigungu") or {}
        if r_d.get("median") and (r_d.get("n") or 0) >= _MIN_TRADE_SAMPLES:
            r_scope, r_med, r_n = "동", int(r_d["median"]), int(r_d["n"])
        elif r_s.get("median") and (r_s.get("n") or 0) >= _MIN_TRADE_SAMPLES:
            r_scope, r_med, r_n = "시군구", int(r_s["median"]), int(r_s["n"])
        else:
            r_scope = None
        if r_scope:
            yrs = pp.get("recent_build_years")
            premium = _PREMIUM["base"]
            price, ratio_note = _to_supply_per_pyeong_won(
                r_med, dev_type=dev_type, building_type=building_type,
                prop_type=prop_type, premium=premium)
            basis = (
                f"신축 실거래(MOLIT · 준공 {yrs}년 이내) {r_scope} 중앙값 {r_med:,}만원/평"
                f"(전용, 표본 {r_n}건·최근 8개월) × {ratio_note}"
                f"(물건종별 {prop_type})"
            )
            return price, "신축 실거래(MOLIT)", basis, None, r_n
    except Exception as e:  # noqa: BLE001 — 실거래 조회 실패는 지역 시세로 폴백(무중단)
        logger.warning("주변 실거래(MOLIT) 분양단가 조회 실패 — 지역 시세 폴백: %s", str(e)[:120])
        return None

    d_med, d_n = pp["dong"]["median"], pp["dong"]["n"]
    s_med, s_n = pp["sigungu"]["median"], pp["sigungu"]["n"]
    # 동(정밀) 우선, 표본 부족 시 시군구. 둘 다 미달이면 None(소표본 미신뢰 — 무목업).
    if d_med and d_n >= _MIN_TRADE_SAMPLES:
        scope, med, n = "동", int(d_med), int(d_n)
    elif s_med and s_n >= _MIN_TRADE_SAMPLES:
        scope, med, n = "시군구", int(s_med), int(s_n)
    else:
        return None

    premium = _PREMIUM["base"]
    # 전용 평당가(만원) → 공급 평당가(원/평) × 신축 프리미엄.
    price, ratio_note = _to_supply_per_pyeong_won(
        med, dev_type=dev_type, building_type=building_type,
        prop_type=prop_type, premium=premium)
    basis = (
        f"주변 실거래(MOLIT) {scope} 중앙값 {med:,}만원/평(전용, 표본 {n}건·최근 8개월) × "
        f"{ratio_note}(물건종별 {prop_type})"
    )
    # ★표본수를 **구조적으로** 돌려준다. 종전엔 소비처가 `basis` **산문에서 정규식으로
    #   긁었고**(`표본\s*([0-9,]+)\s*건`), 여기서 문구를 조금만 바꾸면 소비처가 조용히
    #   기본값으로 떨어져 신뢰도가 55 에 고정됐다(적대 리뷰 MAJOR-4 · 변이 SURVIVED).
    #   *판정은 파서로, 산문이 아니라.*
    return price, "주변 실거래(MOLIT)", basis, None, n


async def _resolve_sale_price_per_pyeong(
    *, db: Any, site_id: Any, dev_type: str, region: str, address: str,
    precision_out: dict[str, Any] | None = None,
) -> tuple[int | None, str, str, str | None]:
    """분양단가(원/평, 공급면적 기준) 결정 — 실거래 1순위, 지역 시세표는 '추정' 폴백.

    우선순위:
      1) sales site 연결(db+site_id) 있으면 suggest_base_price(신뢰루프) — 현장 확정 우선.
      2) 주변 실거래(MOLIT) 직접 조회 — site_id 없이도 주소 지오코딩으로 확보(★HIGH-1 핵심).
      3) 지역×유형 시세 테이블 폴백 — 이때만 '(추정·비실거래)' 명시 + degraded note.

    Returns: (price_won_per_pyeong|None, source, basis, degraded_note|None)
    """
    # 1순위: 주변 실거래(MOLIT) 앵커 + 신뢰루프 — sales site 연결(db+site_id) 있을 때만.
    if db is not None and site_id is not None:
        try:
            from app.services.sales.pricing.suggest import suggest_base_price

            # ★`collect_cases` 는 **opt-in** 이다(기본 False = 반환 shape 불변).
            #   호출부가 `precision_out` 을 주면 켜서 **같은 수집 루프에서** 원시 사례를 얻는다.
            #   ★★**`suggest_base_price` 를 재호출하지 않는다** — 코드가 그 사고를 명문으로
            #     적어 뒀다: *"종전엔 market_precision 조립이 별도로 재수집해 MOLIT 8개월
            #     조회가 중복 발생했다"*. 조립기도 «재호출하지 않는다(무이중화)» 를 계약으로 건다.
            want_precision = precision_out is not None
            res = await suggest_base_price(db, site_id, collect_cases=want_precision)
            if want_precision and isinstance(res, dict):
                try:
                    from app.services.market_precision.price_suggestion import (
                        assemble_market_precision,
                    )

                    precision_out.update(await assemble_market_precision(res))
                except Exception as e:  # noqa: BLE001 — 정밀화 실패가 분양가를 막지 않는다
                    logger.warning("market_precision 조립 실패(분양가는 계속): %s", str(e)[:120])
                    precision_out["unavailable_reason"] = f"{type(e).__name__}: {str(e)[:80]}"
            if isinstance(res, dict) and res.get("data_source") == "live":
                tiers = res.get("tiers") or []
                # '기준(base)' 프리미엄 tier 채택(없으면 중앙 tier).
                base_tier = next((t for t in tiers if t.get("tier") == "base"), None)
                if base_tier is None and tiers:
                    base_tier = tiers[len(tiers) // 2]
                pp10k = (base_tier or {}).get("per_pyeong_10k")
                if pp10k:
                    price = int(round(float(pp10k) * 10000))  # 만원/평 → 원/평
                    conf = (res.get("trust") or {}).get("confidence")
                    conf_txt = f"(신뢰도 {conf:.0%})" if isinstance(conf, (int, float)) else ""
                    return (
                        price,
                        "주변 실거래(MOLIT)+신뢰루프",
                        f"주변 실거래 시세×신축 프리미엄 기준 분양단가{conf_txt} · 공급면적 기준",
                        None,
                    )
        except Exception as e:  # noqa: BLE001 — 실거래 조회 실패는 다음 순위로 폴백(무중단)
            logger.warning("suggest_base_price 실패 — 주변 실거래 직접조회로 폴백: %s", str(e)[:120])

    # 2순위: 주변 실거래(MOLIT) 직접 조회 — site_id 없이 주소→시군구로 확보(★HIGH-1).
    # ★사례를 원할 때만(=precision 소비처가 있을 때만) 수집한다 — 없으면 비용 0.
    #   ★★이 인자를 안 넘기면 `cases_out` 통로가 **소비처 0** 으로 남는다.
    #     사례를 만들고도 밖으로 안 내보내는 것은 «만들었는데 안 불린다» 그 자체다.
    _cases: list[dict[str, Any]] | None = [] if precision_out is not None else None
    trade = await _trade_sale_price_per_pyeong(
        dev_type=dev_type, address=address, cases_out=_cases)
    if trade is not None:
        # ★이 리졸버의 **외부 계약은 4-튜플 그대로**다(rough 호출부 무회귀).
        #   표본수는 `_molit_sale_price_source` 만 쓰므로 여기서 벗겨 낸다.
        #   ★시그니처를 바꾸며 **이 호출부를 안 고쳤다** — 형제·호출부를 파생으로
        #     세지 않고 «바꾼 함수만» 본 결과다(이 저장소가 반복해 데인 형태).
        price, src, basis, deg, _n = trade
        # ★사례를 **채택된 경로일 때만** 정밀화 출력에 싣는다(목록화·선택의 입력).
        if precision_out is not None and _cases:
            precision_out["presale_cases"] = _cases
            precision_out["presale_case_count"] = len(_cases)
        return price, src, basis, deg

    # 3순위(폴백): 지역×유형 시세 테이블(수지·추천 공용 SSOT) — 실거래 아님(추정치).
    try:
        from app.services.feasibility import regional_pricing

        price, basis_key = regional_pricing.resolve_regional_sale_price_per_pyeong(
            dev_type=dev_type, region=region, address=address,
        )
    except Exception as e:  # noqa: BLE001 — 시세 테이블 실패는 분양단가 미확보(정직 null)
        logger.warning("지역 시세 테이블 조회 실패: %s", str(e)[:120])
        return None, "unavailable", "분양단가 미확보", "분양단가: 실거래·지역시세 모두 실패 — 미산출(무목업)"

    # ★HIGH-1: 지역 시세표는 실거래가 아니다. 전국 기본값뿐 아니라 시군구/시도 매칭도
    #   모두 '분양단가 실거래 미확보 — 지역 시세표 추정'을 degraded에 남기고, source에도
    #   '(추정·비실거래)'를 명시해 초록(실거래) 배지로 오표기되지 않게 한다.
    note = "분양단가: 실거래 미확보 — 지역 시세표 추정(참고용, 실제 시세로 재산정 필요)"
    if basis_key == "national_default":
        note = "분양단가: 실거래·지역시세 미매칭 — 전국 기본값 추정 폴백(참고용, 실제 시세로 재산정 필요)"
    return (
        int(price),
        f"지역 시세 테이블({basis_key}·추정·비실거래)",
        "지역×유형 시장표준 시세(원/평, 공급면적) — 주변 실거래 미확보 시 추정 폴백",
        note,
    )




