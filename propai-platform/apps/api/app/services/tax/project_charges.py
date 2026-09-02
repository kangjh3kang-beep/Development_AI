"""사업 부담금 공용 헬퍼 — B(공사)+C(분양) 단계 시행사 부담분 표준 계약.

★부담금 상시-0 봉합(전역 전파방지): 개략수지(rough) 경로가 total_tax_cost_won=0으로
아예 부담금을 계상하지 않아 학교용지·광역교통·상하수도·HUG 등이 총사업비에서 통째로
누락되던 결함의 공용 봉합 지점. 새 산식은 만들지 않고 기존 검증 엔진
(utility_stage_engine·sale_stage_engine)을 조합만 한다.

계약:
- A(취득)단계는 포함하지 않는다 — 개략수지 토지비(land_cost_engine,
  include_taxes_and_fees=True)에 이미 계상돼 있어 포함 시 이중계상.
- D(양도)단계도 포함하지 않는다 — 총사업비(사업 수행 비용) 성격이 아님.
- 시행사 부담분만 합산한다(sale 단계 total_won은 이미 시행사분만 —
  수분양자 부담 C04~C06은 buyer_borne_total_won으로 분리돼 있음).
- 산출 불가 항목(표준건축비 미고시·조례 단가 미등록 등)은 값을 지어내지 않고
  unavailable_notes로 정직 표기한다(무목업).
"""

from __future__ import annotations

from typing import Any

from app.services.tax.sale_stage_engine import calculate_all_sale_stage
from app.services.tax.utility_stage_engine import calculate_all_utility_stage
from app.utils.withheld import AWAITING_INPUT, SOURCE_UNAVAILABLE

# JSON/쿼리스트링 직렬화로 불리언이 문자열로 오는 흔한 오염 케이스의 거짓값 표기들.
_FALSY_STRINGS = frozenset({"", "0", "false", "no", "n", "off"})


def parse_bool_flag(value: Any) -> bool:
    """부담금 게이트용 불리언 안전 파서 — 문자열 "false"/"0" 오부과 방지(리뷰 P2-1).

    무타입 dict(params·overrides)에서 오는 게이트는 클라이언트 직렬화에 따라
    문자열 "false"가 올 수 있고, 원시 bool("false")=True라 부담구역이 아닌
    사업지에 C07이 부과된다. 문자열은 표기 기준으로, 그 외는 truthiness로 판정한다.
    """
    if isinstance(value, str):
        return value.strip().lower() not in _FALSY_STRINGS
    return bool(value)


def parse_tristate_flag(value: Any) -> bool | None:
    """게이트용 **3상태** 파서 — `None`(미조회) / `False`(조회했고 아님) / `True`(맞음).

    ★`parse_bool_flag` 는 **미조회를 `False` 로 뭉갠다.** 금액은 어차피 같지만(안전측 0),
      화면에 나가는 **주장이 달라진다** — *"미지정"* 은 관측이고 *"미조회"* 는 미측정이다.
      증거 규율 §1(관측/추론/미측정 표기 구분)이 요구하는 구별이다.

    `None`·미존재 키만 `None` 이다. 빈 문자열은 **입력했다가 지운 것**일 수 있으나
    구별할 수단이 없으므로 `None`(미조회)로 본다 — 안전한 쪽은 「모른다」다.
    """
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip()
        if not v:
            return None
        return v.lower() not in _FALSY_STRINGS
    return bool(value)


def charge_item_unavailable(item: dict[str, Any]) -> bool:
    """부담금 항목 하나가 **「산출 불가(정직 강등)」인가**. 표기 관례 3종을 한 자리에서 판정.

    ★**모듈 레벨 함수인 이유**: 인라인 불린식이면 **직접 태울 수 없어** 이 판정 자체가
      무잠금이 된다(이 저장소에서 같은 형태로 한 세션에 7회 무잠금이 났다).
      원장(`legacy_ledger._charge_items`)도 **같은 판정자**를 써야 두 소비처가 갈리지 않는다.

    ★`detail.confidence` 를 **먼저** 본다(엔진 다수의 정본 자리). 최상위는 C07 계열 보완이다.
    """
    if not isinstance(item, dict):
        return False
    detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
    if detail.get("amount_computable") is False:
        return True
    return "unavailable" in (detail.get("confidence"), item.get("confidence"))


def charge_absent_reason(item: dict[str, Any]) -> str | None:
    """강등 항목의 **보류 사유를 닫힌 어휘 코드로** 돌려준다(`app/utils/withheld.py` 계약).

    ★**왜 산문만으로 부족한가** — 그 모듈이 이미 답해 두었다:
      *"산문은 셀 수 없다. 셀 수 없으면 새 표면이 생겨도 감시망에 들지 않는다."*
      실제로 이 저장소는 부재 사유가 **다섯 갈래 어휘**로 흩어져 있었고, 그것을 하나로
      모으려고 `ABSENT_REASONS` 닫힌 어휘를 만들었다. 부담금도 그 통로를 탄다.

    ★**두 사유를 가른다** — 이것이 이 계약을 쓰는 진짜 이유다:
      · `AWAITING_INPUT`     — **미조회**. 사용자가 확인해 주면 값이 생긴다(C07 부담구역)
      · `SOURCE_UNAVAILABLE` — **원천 부재**. 사용자가 뭘 해도 안 생긴다(조례 미등록·미고시)
      종전에는 둘 다 `confidence="unavailable"` 한 낱말이었고, 화면은 **무엇을 하라는지**
      말할 수 없었다. 코드가 다르면 **처방도 다르게** 안내할 수 있다.

    ★`NOT_APPLICABLE`(해당 없음)은 **여기서 내지 않는다** — 그 경우 엔진은 강등이 아니라
      확정 0 을 내므로 이 함수에 도달하지 않는다. 다만 현재 `sale_stage_engine` 이
      **두 분기에 같은 센티널**을 써서 확정 쪽도 `0㎡ × 0원/㎡` 로 그려진다(별건 부채).
    """
    if not charge_item_unavailable(item):
        return None
    detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
    # `surveyed is False` = 조회 자체를 안 했다(엔진이 명시). 사용자 확인으로 해소된다.
    if detail.get("surveyed") is False:
        return AWAITING_INPUT
    return SOURCE_UNAVAILABLE


def _collect_unavailable_notes(stage: dict[str, Any]) -> list[str]:
    """단계 items에서 '산출 불가(정직 강등)' 항목의 사유를 수집한다.

    엔진들의 정직 표기 관례 **3종**을 모두 인식한다:
    - detail.confidence == "unavailable" (B01 표준건축비 미고시, B03/B04 조례 미등록)
    - detail.amount_computable == False (B01 광역교통 — 금액 산출 불가 플래그)
    - **item 최상위 confidence == "unavailable"** (C07 기반시설부담금 — 부담구역 **미조회**)

    ★**왜 최상위도 봐야 하나** — 2026-08-27 라이브·로컬 실측.
      C07(`sale_stage_engine`)은 `confidence` 를 **item 최상위**에 붙이고 `detail` 에는
      `reason`·`surveyed` 만 둔다. 형제 B01/B03/B04(`utility_stage_engine`)는 **`detail` 안**에
      붙인다. 이 함수는 `detail` 만 봤으므로 **C07 의 「미조회」가 여기서 통째로 사라졌다.**

      결과: `unavailable_notes` → `degraded_notes` → 보고서 ⑦「유의」로 가는 길이 끊겨,
      **제출용 PDF 에 「기반시설부담구역 미조회」가 0회 등장**한 채 표에는
      `기반시설부담금 0원`(`0㎡ × 0 원/㎡`)이 **관측된 사실처럼** 실렸다.

    ★**형제 주석의 실측이 낡아 있었다.** `compact_charge_items` 는
      *"엔진 16종 전수 실측: 최상위 non-None **0/16**"* 이라 적고 이 함수를
      *"처음부터 옳게 읽고 있었다"* 고 보증한다. 그 측정은 **C07 3상태(#871) 이전**의 것이고
      지금은 **1/16** 이다 — 낡은 측정이 형제를 면제해 주고 있었다.
      (CLAUDE.md §자기 라벨 승계 금지 · §휘발성 값은 재측정으로)

    ★그래서 판정을 **한 자리에서** 한다 — 새 엔진이 어느 관례를 쓰든 여기만 보면 된다.
    """
    notes: list[str] = []
    for item in stage.get("items") or []:
        if not isinstance(item, dict):
            continue
        detail = item.get("detail") if isinstance(item.get("detail"), dict) else {}
        if not charge_item_unavailable(item):
            continue
        reason = detail.get("reason") or item.get("reason") or "산출 근거 미확보"
        notes.append(f"{item.get('name', item.get('code', '부담금'))}: {reason} — 합계 미반영(정직 강등)")
    return notes


def compute_developer_stage_charges(
    *,
    sido_name: str = "",
    sigungu_name: str = "",
    total_households: int = 0,
    total_sale_amount_won: int = 0,
    total_gfa_sqm: float = 0,
    building_type: str = "apartment",
    avg_area_sqm: float = 85.0,
    # ★3상태 — `None`(미조회) / `False`(조회했고 아님) / `True`(맞음).
    #   종전 `bool = False` 는 **미조회를 미지정으로 뭉개** 화면에 없는 관측 주장을 냈다.
    in_infra_charge_zone: bool | None = None,
    # ★B01 시도 해석 자가치유용 — 호출부가 시·도가 아닌 값을 넘겨도 주소로 복구한다.
    address: str = "",
) -> dict[str, Any]:
    """B(공사)+C(분양) 단계 시행사 부담금 일괄 계산 — 개략수지 총사업비 계상용.

    Returns:
        {
            'construction': {...},   # utility_stage 원본(items·total_won)
            'sale': {...},           # sale_stage 원본(items·total_won=시행사분)
            'total_won': int,        # 시행사 부담 합계(B.total + C.total)
            'unavailable_notes': [...],  # 산출 불가 항목 정직 사유(합계 미반영분)
        }
    """
    construction = calculate_all_utility_stage(
        sido_name=sido_name,
        sigungu_name=sigungu_name,
        total_households=max(0, total_households),
        total_sale_amount_won=max(0, total_sale_amount_won),
        total_gfa_sqm=max(0.0, total_gfa_sqm),
        building_type=building_type,
        address=address,
    )
    sale = calculate_all_sale_stage(
        total_sale_amount_won=max(0, total_sale_amount_won),
        total_units=max(0, total_households),
        avg_area_sqm=avg_area_sqm or 85.0,
        total_gfa_sqm=max(0.0, total_gfa_sqm),
        building_type=building_type,
        in_infra_charge_zone=in_infra_charge_zone,
    )
    notes = _collect_unavailable_notes(construction) + _collect_unavailable_notes(sale)
    return {
        "construction": construction,
        "sale": sale,
        "total_won": int(construction["total_won"]) + int(sale["total_won"]),
        "unavailable_notes": notes,
    }
