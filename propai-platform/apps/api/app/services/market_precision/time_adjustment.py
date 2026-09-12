"""TimeAdjustment — 거래 시점 → 현재 시점 보정(R-ONE 실데이터 opt-in, 외삽 금지).

★스파이크 확정: ``app.services.land_intelligence.reb_statistics_service.housing_time_adjust``가
이미 R-ONE 주택매매가격지수 실데이터 경로를 보유한다(``RONE_HOUSING_STATBL_ID`` 환경변수
설정 시에만 조회 — 미설정/조회실패는 None). 이 모듈은 그 함수를 재구현하지 않고 그대로
호출하며, None을 받으면 임의 계수를 만들지 않고 UNKNOWN + "미보정" 정직 표기로 반환한다
(``app.services.cost.unit_price_repository``의 opt-in escalate_to_current와 동일 관례 —
보정은 부착만 하고 원본 가격을 자동으로 변형하지 않는다).

★R1 M-3 봉합(OBSERVED 경로 정직성 비대칭 해소): R-ONE 실계수가 가용해도(``status=OBSERVED``)
이 모듈은 그 계수를 표시 가격(ComparableCase/PriceSuggestion)에 실제로 적용하지 않는다 —
근거로만 부착한다. 종전엔 이 사실이 UNKNOWN 경로의 assumption에만 있고 OBSERVED 경로에는
없어, "실계수가 있으니 이미 반영됐다"는 오인 소지가 있었다. 두 경로 모두 동일하게
"계수는 근거 표기용, 표시 가격은 미보정 원본"임을 assumption에 명시한다.
"""
from __future__ import annotations

from app.services.land_intelligence.reb_statistics_service import housing_time_adjust
from app.services.market_precision.contracts import TimeAdjustment
from app.services.provenance.fact_status import FactStatus


def _sido_of_address(address: str) -> str:
    """요청 주소의 시·도(정본 해석기 경유) — scope 대조용."""
    from app.services.land_intelligence.land_price_index import _sido_of

    return _sido_of(address)

_UNCONFIGURED_LIMITATION = (
    "R-ONE 주택매매가격지수 통계표ID(RONE_HOUSING_STATBL_ID) 미설정 또는 조회 실패 — "
    "시점보정 계수를 산출/외삽하지 않고 미보정 원본 그대로 사용합니다(정직 표기, 가짜 계수 금지)."
)


async def resolve_time_adjustment(address: str = "") -> TimeAdjustment:
    """주소 기준 시점보정계수를 조회한다. 미가용 시 UNKNOWN(임의 계수 금지)."""
    result = await housing_time_adjust(address)
    if not result:
        return TimeAdjustment(
            status=FactStatus.UNKNOWN,
            factor=None,
            source="미보정",
            basis="시점보정 실데이터 미가용(R-ONE 통계표 미설정 또는 조회 실패).",
            assumption="비교사례 거래가는 시점보정 없이 원본(거래 시점 가격) 그대로 사용됩니다.",
            limitation=_UNCONFIGURED_LIMITATION,
        )
    # ★★독립 리뷰 R2 HIGH-C: 이 모듈은 독스트링에 *"임의 계수를 만들지 않고 UNKNOWN + 「미보정」
    #   정직 표기 … 가짜 계수 금지"* 라고 선언해 놓고, **존재하지 않는 지역도 OBSERVED** 로 승격시켰다
    #   (**픽스처 기준** 관측: `zzz없는지역` → status=OBSERVED · factor=1.0243 · source='R-ONE').
    #   ★★출처 표기 정정(독립 리뷰 R4 MEDIUM-3 · 2026-09-08): 위 값은 **테스트 픽스처**에서 잰
    #     것이지 라이브가 아니다. 종전에는 그냥 «실측» 이라고만 적어, 같은 파일을 읽는 사람이
    #     **라이브 관측으로 오독**하게 돼 있었다(§증거규율 2 — 인과 주장에는 증거 토큰).
    #   ★그리고 라이브에서는 이 경로가 **아예 값을 내지 않는다**(2026-09-08 실측):
    #     이 함수는 `housing_time_adjust` 를 부르는데, 그 표(주택매매가격지수 `A_2024_00615`)의
    #     `distinct_ITM_NM` 은 **`['지수']` 1종**이고 시계열 추출기는 `"변동" not in itm` 으로
    #     그 행을 **전부 걸러 낸다** ⇒ 시계열 `[]` → 누적계수 `None` → 여기서 UNKNOWN «미보정».
    #     즉 **base·branch 모두** 라이브에서 UNKNOWN 이다(이 PR 이 만든 회귀가 아니다).
    #     지수형 표는 ∏(1+r) 이 아니라 `index[t1]/index[t0]` 로 계산해야 한다 — **별건**이라
    #     이 PR 에서 고치지 않고, `tests/test_sido_resolution_fail_open.py` 의 **strict xfail** 로
    #     초록 안에 드러나게 남긴다(커밋 메시지에만 적으면 안 보인다).
    #   그리고 `limitation` 이 «이 주소의 광역시도 대표치» 라고 **단정**했다.
    #   ⇒ 요청 지역의 값이 아니면 **관측이 아니다**. scope 를 읽어 가른다.
    scope = result.get("scope")
    requested = _sido_of_address(address)
    # ★**부재와 모순을 가른다**(독립 리뷰 R2 + 기존 회귀가드가 갈라 준 지점):
    #   · `scope` 가 **없다** → 생산자가 범위를 알려주지 않았다. 우리가 **모순을 지어내지 않는다**
    #     (기존 계약 유지 = OBSERVED). 우리 생산자는 항상 싣는다 — 아래 락이 그것을 강제한다.
    #   · `scope` 가 **있고 요청 지역과 다르다** → 이 주소의 값이 **아니다**. 관측이 아니다.
    #   ★처음엔 «부재도 강등» 으로 짰다가 기존 회귀가드
    #     (`test_rone_가용시_observed_실계수`)가 빨개져 알았다 — **그 테스트가 옳았다.**
    is_substitute = bool(scope) and scope != requested
    if is_substitute:
        return TimeAdjustment(
            status=FactStatus.UNKNOWN,
            factor=result.get("factor"),
            source=result.get("source") or "R-ONE",
            basis=result.get("basis") or "주택매매가격지수 누적 변동",
            assumption=(
                "이 계수는 근거 표기용입니다 — 표시 가격은 이 계수를 적용하지 않은 미보정 원본입니다."
            ),
            limitation=(
                f"★이 주소의 시·도 값이 **아닙니다** — {scope or '미상'} 범위 값으로 대체됐습니다"
                "(요청 지역 시계열 부재). 이 주소의 변동을 관측한 것이 아니므로 근거로 인용하지 마십시오."
            ),
        )
    return TimeAdjustment(
        status=FactStatus.OBSERVED,
        factor=result.get("factor"),
        source=result.get("source") or "R-ONE",
        basis=result.get("basis") or "주택매매가격지수 누적 변동",
        assumption=(
            "이 계수는 근거 표기용입니다 — 표시 가격(비교사례·분양가 제안)은 이 계수를 "
            "적용하지 않은 미보정 원본 그대로입니다(자동 시점보정 미실시)."
        ),
        limitation="R-ONE 통계는 광역시도 단위 대표치입니다 — 개별 단지 변동과 다를 수 있습니다(외삽 한계).",
    )


__all__ = ["resolve_time_adjustment"]
