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
    *, dev_type: str, address: str,
) -> tuple[int, str, str, None] | None:
    """주변 실거래(MOLIT) 직접 조회 → 분양단가(원/평, 공급면적). site_id 불필요(★HIGH-1).

    주소를 지오코딩해 시군구 5자리를 얻고, 검증된 공용 헬퍼 _trade_per_pyeong으로 동·시군구
    전용 평당가 중앙값을 구한다(재구현 0). 실거래는 '전용면적' 기준이므로, 개략수지가 쓰는
    '공급(분양가능)면적' 기준으로 환산(×전용률)하고 신축 분양 프리미엄(기준안 1.15)을 곱한다
    — sales site 연결 경로(suggest_base_price base tier)와 동일 산식으로 일치시킨다.

    표본 부족(_MIN_TRADE_SAMPLES 미만)·조회 실패면 None(호출부가 지역 시세로 폴백).
    """
    sigungu5 = await _sigungu5_from_address(address)
    if not sigungu5:
        return None
    try:
        # 검증된 실거래 헬퍼·환산상수 재사용(SSOT — 값 발산 방지).
        from app.services.sales.pricing.suggest import (
            _JEONYULRYUL,
            _PREMIUM,
            _extract_dong,
            _trade_per_pyeong,
        )

        building = _svc()._get_building_type(dev_type)
        prop_type = _BUILDING_TO_MOLIT_PROP.get(building, "apt")
        dong = _extract_dong(address)
        pp = await _trade_per_pyeong(sigungu5, dong, prop_type)
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
    price = int(round(med * _JEONYULRYUL * premium * 10000))
    basis = (
        f"주변 실거래(MOLIT) {scope} 중앙값 {med:,}만원/평(전용, 표본 {n}건·최근 8개월) × "
        f"전용률 {_JEONYULRYUL} × 신축 프리미엄 {premium} → 공급 평당가(공급면적 기준)"
    )
    return price, "주변 실거래(MOLIT)", basis, None


async def _resolve_sale_price_per_pyeong(
    *, db: Any, site_id: Any, dev_type: str, region: str, address: str,
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

            res = await suggest_base_price(db, site_id)
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
    trade = await _trade_sale_price_per_pyeong(dev_type=dev_type, address=address)
    if trade is not None:
        return trade

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




