"""지역 × 개발유형별 평균 분양가(원/평) 산정 — 단일 출처(Single Source of Truth).

분양가는 *시장 시세*로 결정되어야 한다. 공사비에서 역산하면 토지비가 수입에
반영되지 않아 구조적으로 적자가 발생한다. 이 모듈은 시군구·시도 단위 시세 테이블을
제공하며, 수지분석·파이프라인·사업모델 추천이 모두 이 함수를 공유한다.

향후 실거래가(MOLIT) API 연동으로 교체 예정. 현재는 2026년 기준 보수적 시세 테이블.

분양가 출처 우선순위: 실거래가 API(향후) → 지역 시세 테이블(현재) → 공사비 기반(최후 폴백).
폴백 사용 여부는 호출부에서 메타데이터로 표기한다(할루시네이션 방지).
"""

from __future__ import annotations

# ── 시군구 세분화 평균 분양가 (만원/평) — 경기도 내 격차 반영 ──
SIGUNGU_PRICES_MAN_WON: dict[str, int] = {
    # 서울 구별
    "강남구": 5500, "서초구": 5000, "송파구": 4500, "용산구": 4000,
    "마포구": 3500, "성동구": 3200, "영등포구": 3000,
    "강동구": 3000, "동작구": 2800, "광진구": 2800,
    "노원구": 2200, "도봉구": 2000, "중랑구": 2200, "강북구": 2000,
    # 경기 시별
    "성남시": 3500, "분당": 4000, "판교": 4500,
    "수원시": 2200, "용인시": 2000, "화성시": 1800,
    "고양시": 2000, "일산": 2200,
    "의정부시": 1400, "남양주시": 1600, "구리시": 2200,
    "파주시": 1200, "양주시": 1100, "동두천시": 900,
    "안양시": 2500, "안산시": 1500, "시흥시": 1400,
    "김포시": 1600, "광명시": 2800, "하남시": 3000,
    "평택시": 1300, "오산시": 1200, "이천시": 1100,
    "부천시": 2000, "광주시": 1500,
    # 인천 구별
    "연수구": 2500, "송도": 2800, "부평구": 1600, "남동구": 1800,
    # 부산
    "해운대구": 2800, "수영구": 2500, "부산진구": 2000,
}

# ── 시도 기본값 (만원/평) ──
SIDO_PRICES_MAN_WON: dict[str, int] = {
    "서울특별시": 3000, "서울": 3000,
    "경기도": 1800, "경기": 1800,
    "인천광역시": 1800, "인천": 1800,
    "부산광역시": 2000, "부산": 2000,
    "대구광역시": 1800, "대구": 1800,
    "대전광역시": 1700, "대전": 1700,
    "광주광역시": 1500, "광주": 1500,
    "울산광역시": 1600, "울산": 1600,
    "세종특별자치시": 1800, "세종": 1800,
    "제주특별자치도": 1500, "제주": 1500,
    "강원도": 1100, "충청북도": 1200, "충청남도": 1300,
    "전라북도": 1000, "전라남도": 900,
    "경상북도": 1100, "경상남도": 1200,
}

# ── 개발유형별 분양가 보정 계수 ──
DEV_TYPE_MULTIPLIER: dict[str, float] = {
    "M01": 1.0, "M02": 1.0, "M04": 0.95, "M06": 1.0,
    "M07": 1.1, "M08": 0.8, "M09": 0.65,
    "M10": 1.1, "M11": 0.75, "M12": 1.05, "M13": 0.7,
}

_DEFAULT_BASE_MAN_WON = 1500


def resolve_regional_base_price(region: str = "", address: str = "") -> tuple[int, str]:
    """기준 분양가(만원/평)와 매칭 근거(basis)를 함께 반환 — 폴백 무신호 해소(W2-1).

    basis: "sigungu"(시군구 정밀) | "sido_region"(명시 시도) | "sido_address"(주소 시도 추론)
           | "national_default"(전국 기본 — 지역 미매칭 폴백. 호출부는 출처를
           regional_market_table로 오표기하지 말고 폴백임을 정직 표기할 것).
    """
    # 1) 시군구 세분화 매칭 (가장 정밀)
    for sigungu, price in SIGUNGU_PRICES_MAN_WON.items():
        if sigungu in address:
            return price, "sigungu"
    # 2) 명시된 시도(region) 기본값
    if region:
        price = SIDO_PRICES_MAN_WON.get(region)
        if price is not None:
            return price, "sido_region"
    # 3) 주소에서 시도 추론
    for sido, price in SIDO_PRICES_MAN_WON.items():
        if sido in address:
            return price, "sido_address"
    # 4) 전국 기본값
    return _DEFAULT_BASE_MAN_WON, "national_default"


def get_regional_base_price_man_won(region: str = "", address: str = "") -> int:
    """시군구 → 시도(region) → 주소 내 시도 추론 순으로 기준 분양가(만원/평)를 결정."""
    price, _ = resolve_regional_base_price(region=region, address=address)
    return price


def get_regional_sale_price_per_pyeong(
    dev_type: str = "", region: str = "", address: str = ""
) -> int:
    """지역 × 개발유형 평균 분양가를 원/평 단위로 반환.

    Args:
        dev_type: 개발유형 코드(M01 등). 미상이면 보정계수 1.0.
        region: 시도명. 시군구가 주소로 매칭되면 무시된다.
        address: 전체 주소 문자열(시군구 매칭에 사용).

    Returns:
        평당 분양가(원). 항상 양수.
    """
    base_man_won = get_regional_base_price_man_won(region=region, address=address)
    multiplier = DEV_TYPE_MULTIPLIER.get(dev_type, 1.0)
    return int(base_man_won * multiplier * 10000)  # 만원 → 원


def resolve_regional_sale_price_per_pyeong(
    dev_type: str = "", region: str = "", address: str = ""
) -> tuple[int, str]:
    """평당 분양가(원)와 매칭 근거(basis)를 함께 반환 — 호출부의 출처 정직 표기용(W2-1)."""
    base_man_won, basis = resolve_regional_base_price(region=region, address=address)
    multiplier = DEV_TYPE_MULTIPLIER.get(dev_type, 1.0)
    return int(base_man_won * multiplier * 10000), basis
