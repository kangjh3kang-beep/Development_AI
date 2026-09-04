"""부담금 코드별 **과표·요율의 단위** — 표시층 SSOT.

## 왜 필요한가 (2026-08-26 적대 리뷰 차단)

항목 dict 의 키 이름이 `base_won` 이라 **전부 「원」인 것처럼 읽힌다.** 실제로는 셋이다:

    int(total_gfa_sqm)      → ㎡     (B01 · B08 · C07 · C08)
    total_households        → 세대   (B02 일부)
    ★B05~B08 은 **표에서 제거**됐다(2026-08-27) — 부담금이 아니라 공사비여서
      utility_stage_engine 에서 빠졌다. 인입 3건은 cost/utility_connection_cost 로 이관,
      소방은 직접공사비 도급단가에 이미 포함(적산 실적 실측 27,223원/㎡ vs 코드 3,500원/㎡)이라 제거.
    total_sale_amount_won   → 원     (B02 · C01~C06)

표시층이 `base_won` 을 전부 `"원(과표)"` 로 라벨링했더니 **「300원 과표 × 140,000 요율」**
같은, **존재하지 않는 주장**이 화면에 나갔다(22 대입 중 11 이 거짓).

★근본 처방은 **엔진이 단위를 함께 실어 보내는 것**이다. 그 전까지의 봉합으로 이 표를
**엔진 옆에** 둔다 — 표시층에 두면 엔진이 코드를 추가할 때 같이 안 움직인다.
★표에 없는 코드는 **`None`**(모름)이다. 추측해서 라벨을 붙이지 않는다.
"""

from __future__ import annotations

__all__ = ["CHARGE_BASE_UNITS", "base_units_for"]

#: code → (과표 단위, 요율 단위). `None` = 이 코드는 표에 없다(모름).
#: ★근거는 각 엔진의 `base_won=` 대입식이다. 코드를 추가하면 **여기도 추가**해야 하고,
#:   `tests/test_charge_base_units_contract.py` 가 누락을 실패로 신고한다.
CHARGE_BASE_UNITS: dict[str, tuple[str, str]] = {
    # 연면적 기준 — base_won = int(total_gfa_sqm)
    "B01": ("㎡", "부과율"),          # utility_stage_engine.py:89  (광역교통시설)
    "C07": ("㎡", "원/㎡"),           # sale_stage_engine.py:151    (기반시설)
    "C08": ("㎡", "원/㎡"),           # sale_stage_engine.py:166    (에너지절약)
    # 세대 기준 — base_won = total_households
    # ★2026-08-27 차원 교정 — 종전 ("세대","원/세대") 는 **법정 차원이 아니었다.**
    #   하수도법 §61+시행령 §35 는 **오수발생량(㎥/일)**, 수도법 시행령 §65① 은
    #   **수돗물 사용량**. **법 2 + 시행령 2** 에서 `'세대'` 출현 **0회**(★조례는 별개 — 울산 하수도 조례 §9② 는 세대별 정액 고시를 허용한다).
    #   ★이 선언까지 고쳐야 한다 — 표·엔진만 고치면 **화면 단위가 계속 거짓말**한다.
    # ★B03 상수도 — **과표 축을 모른다.** 수도법 시행령 §65③ 은 실비(원가계산) 합산이라
    #   `과표 × 요율` 구조가 아니다. 이 파일의 규칙(*"근거는 base_won= 대입식"*)상
    #   근거를 댈 수 없으므로 **추측하지 않고 (None, None)** 로 둔다.
    #   → 코드를 **빼지 않고** `(None, None)` 으로 **선언**한다.
    #     빼면 「등록 안 됨」과 「모른다고 판정함」이 구별되지 않고, 완전성 계약
    #     (`test_every_emitted_code_has_a_unit_entry`)도 깨진다. **모름을 명시하는 것**이
    #     이 저장소의 보류 계약(`app/utils/withheld.py`)과 같은 태도다.
    "B03": (None, None),
    # ★B04 하수도 — 오수발생량(㎥/일) × 단위단가(원/㎥/일).
    #   근거: 하수도법 §61①+시행령 §35① · 울산시 하수도 사용 조례 §24①4호 원문.
    "B04": ("㎥/일", "원/㎥/일"),
    # 금액 기준 — base_won = total_sale_amount_won
    "B02": ("원", "요율"),            # utility_stage_engine.py:131 (학교용지)
    "C01": ("원", "세율"),            # sale_stage_engine.py:48     (부가가치세)
    "C02": ("원", "요율"),            # sale_stage_engine.py:64     (분양보증수수료)
    "C03": ("원", "요율"),            # sale_stage_engine.py:78     (분양광고비)
    "C04": ("원", "세율"),            # sale_stage_engine.py:92     (취득세)
    "C05": ("원", "요율"),            # sale_stage_engine.py:106    (등기비용)
    "C06": ("원", "요율"),            # sale_stage_engine.py:122    (국민주택채권)
}


def base_units_for(code: str | None) -> tuple[str | None, str | None]:
    """코드 → (과표 단위, 요율 단위). **모르면 `(None, None)`** — 추측하지 않는다."""
    if not code:
        return (None, None)
    u = CHARGE_BASE_UNITS.get(str(code).upper())
    return u if u else (None, None)
