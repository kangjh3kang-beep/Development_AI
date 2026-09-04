"""
공공데이터 무결성 검증 레이어.
모든 외부 데이터는 이 검증기를 통과한 후에만 시스템에 입력된다.
"""
import logging
from datetime import datetime

from pydantic import BaseModel, ValidationError, field_validator

logger = logging.getLogger(__name__)


# --- 실거래가 검증 스키마 ---
#: 유형과 무관한 **절대** 면적 상한(㎡). 이보다 크면 어떤 유형이든 원본 오류로 본다.
#: 5㎢ — 저장소 선례(`design_ingest/vision_parser._MAX_AREA_SQM = 5_000_000.0`, "초대형 단지도 포함")와 정렬.
_ABSOLUTE_MAX_AREA_SQM = 5_000_000.0

#: 유형별 면적 상한(㎡). **아파트 기준값을 토지에 적용하면 정상 거래가 대량 드롭된다.**
#:
#: ★라이브 실측(2026-08-26 · MOLIT 토지 원본 41370/202607 **114행**):
#:     면적 > 1000㎡ 인 행 = **68/114 = 60%** (범위 1,031~10,763㎡ · 중앙 1,795㎡)
#:   즉 종전 1000㎡ 상한은 **정상 토지거래의 60%를 "이상치"로 버리고 있었다.**
#:   토지는 필지 하나가 수만 ㎡ 인 것이 정상이다(같은 날 실측한 프로젝트 필지 147,074㎡).
#:
#: ★집합주택(아파트·연립·오피스텔)은 **전용면적**이라 1000㎡ 상한이 타당하다 — 그대로 둔다.
_MAX_AREA_SQM_BY_PROP_TYPE: dict[str, float] = {
    "apt": 1000.0,
    "villa": 1000.0,
    "officetel": 1000.0,
    "house": 50_000.0,        # 단독·다가구는 대지면적이라 전용면적보다 크다
    "land": _ABSOLUTE_MAX_AREA_SQM,       # 토지 — 상한을 두지 않는다(절대 상한만)
    "commercial": _ABSOLUTE_MAX_AREA_SQM,  # 상업·업무용 필지도 같다
}


def max_area_sqm_for(prop_type: str) -> float:
    """유형별 면적 상한(㎡) — 순수 함수.

    ★모르는 유형은 **집합주택 기준(가장 좁은 상한)** 으로 접는다. 넓게 여는 쪽으로 폴백하면
      오타 하나가 검증을 통째로 무력화한다(fail-safe 방향).
    """
    return _MAX_AREA_SQM_BY_PROP_TYPE.get((prop_type or "").strip().lower(), 1000.0)


class TransactionRecord(BaseModel):
    """국토부 실거래가 레코드 검증."""
    deal_date: str  # YYYYMMDD
    price_10k_won: int  # 만원 단위
    area_sqm: float
    floor: int
    building_year: int | None = None
    road_name: str | None = None

    @field_validator("price_10k_won")
    @classmethod
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError(f"거래가는 양수여야 합니다: {v}")
        if v > 500_000:  # 50억 초과 = 이상치
            logger.warning(f"이상 거래가 감지: {v}만원 (50억 초과)")
        return v

    @field_validator("area_sqm")
    @classmethod
    def validate_area(cls, v):
        # ★상한은 **유형과 무관한 절대 상한**만 여기서 본다. 유형별 상한은
        #   `validate_transactions(prop_type=...)` 가 건다 — 이 모델은 prop_type 을 모른다.
        #   종전엔 여기에 1000㎡ 가 박혀 있어 **토지 거래의 60%가 드롭**됐다(§ 아래 실측).
        if v <= 0 or v > _ABSOLUTE_MAX_AREA_SQM:
            raise ValueError(f"면적 범위 초과: {v}m²")
        return v

    @field_validator("floor")
    @classmethod
    def validate_floor(cls, v):
        if v < -5 or v > 120:  # 지하5~120층 범위
            raise ValueError(f"층수 범위 초과: {v}")
        return v


# --- 공시지가 검증 ---
class OfficialLandPrice(BaseModel):
    """공시지가 레코드 검증."""
    pnu: str  # 19자리
    price_per_sqm: int  # 원/m²
    base_year: int
    land_category: str  # 전, 답, 대, 임, 잡 등

    @field_validator("pnu")
    @classmethod
    def validate_pnu(cls, v):
        if len(v) != 19 or not v.isdigit():
            raise ValueError(f"PNU는 19자리 숫자여야 합니다: {v}")
        return v

    @field_validator("price_per_sqm")
    @classmethod
    def validate_price(cls, v):
        if v <= 0:
            raise ValueError(f"공시지가는 양수여야 합니다: {v}")
        if v > 100_000_000:  # m²당 1억 초과 = 검증 필요
            logger.warning(f"고가 공시지가: {v}원/m²")
        return v


# --- 세율 검증 ---
class TaxRateRecord(BaseModel):
    """세율 레코드 검증."""
    tax_type: str  # acquisition, transfer, comprehensive
    rate: float  # 0.0 ~ 1.0
    effective_date: str  # YYYY-MM-DD
    region_code: str | None = None
    conditions: dict | None = None

    @field_validator("rate")
    @classmethod
    def validate_rate(cls, v):
        if v < 0 or v > 1.0:
            raise ValueError(f"세율은 0~100% 범위여야 합니다: {v}")
        return v


# --- 용도지역 검증 ---
class ZoningRecord(BaseModel):
    """용도지역 정보 검증."""
    pnu: str
    zone_type: str
    max_bcr: float  # 건폐율 상한 (%)
    max_far: float  # 용적률 상한 (%)
    max_height_m: float | None = None

    @field_validator("max_bcr")
    @classmethod
    def validate_bcr(cls, v):
        if v <= 0 or v > 100:
            raise ValueError(f"건폐율은 0~100% 범위: {v}")
        return v

    @field_validator("max_far")
    @classmethod
    def validate_far(cls, v):
        if v <= 0 or v > 2000:  # 중심상업 1500% + 특례
            raise ValueError(f"용적률은 0~2000% 범위: {v}")
        return v


# --- 이상치 탐지 ---
class AnomalyDetector:
    """통계 기반 이상치 탐지."""

    @staticmethod
    def check_price_anomaly(
        price_10k: int,
        area_sqm: float,
        region: str,
        recent_prices: list[int],
    ) -> dict:
        """실거래가 이상치 탐지 (IQR 방식)."""
        if not recent_prices or len(recent_prices) < 5:
            return {"is_anomaly": False, "reason": "비교 데이터 부족"}

        price_per_sqm = price_10k * 10000 / area_sqm if area_sqm > 0 else 0
        recent_per_sqm = sorted(recent_prices)
        q1 = recent_per_sqm[len(recent_per_sqm) // 4]
        q3 = recent_per_sqm[3 * len(recent_per_sqm) // 4]
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        if price_per_sqm < lower or price_per_sqm > upper:
            return {
                "is_anomaly": True,
                "reason": f"m²당 {price_per_sqm:,.0f}원은 지역 범위({lower:,.0f}~{upper:,.0f}) 벗어남",
                "severity": "warning" if abs(price_per_sqm - (q1 + q3) / 2) < 2 * iqr else "critical",
            }
        return {"is_anomaly": False, "reason": ""}


# --- 데이터 신선도 검증 ---
class FreshnessChecker:
    """데이터 신선도(최신성) 검증."""

    FRESHNESS_RULES = {
        "transaction": 30,       # 실거래가: 30일 이내
        "official_price": 365,   # 공시지가: 1년 이내
        "zoning": 90,            # 용도지역: 90일 이내
        "tax_rate": 180,         # 세율: 6개월 이내
        "weather": 1,            # 기상: 1일 이내
        "energy_cert": 365,      # 에너지인증: 1년 이내
    }

    @classmethod
    def check(cls, data_type: str, last_updated: datetime) -> dict:
        max_age_days = cls.FRESHNESS_RULES.get(data_type, 30)
        age_days = (datetime.now() - last_updated).days
        is_fresh = age_days <= max_age_days

        return {
            "is_fresh": is_fresh,
            "age_days": age_days,
            "max_age_days": max_age_days,
            "data_type": data_type,
            "warning": None if is_fresh else f"{data_type} 데이터가 {age_days}일 전 것입니다 (기준: {max_age_days}일)",
        }


# --- 수집 파싱 배선(감사 HIGH #2) ---
def validate_transactions(
    rows: list[dict],
    region: str = "",
    recent_prices: list[int] | None = None,
    *,
    prop_type: str = "apt",
) -> tuple[list[dict], dict]:
    """외부 실거래가 원본행을 TransactionRecord 스키마로 검증·필터하고, recent_prices가 있으면
    AnomalyDetector(IQR)로 이상치를 플래그한다.

    배경(감사): 정의돼 있으나 소비처 0건이던 검증 스키마·이상치탐지를 실수집 경로(MolitClient
    ._parse_trade_items 출력)에 배선한다. 무목업 원칙 — 검증 실패행은 가짜 생성 없이 드롭만 하고
    그 사실을 report로 관측 가능하게 남긴다. molit 정규화 키(deal_date/price_10k_won/area_m2/floor/
    build_year) 및 일반 키(area_sqm/building_year)를 모두 수용한다.

    반환: (accepted_rows, report{accepted, dropped, anomalies, dropped_detail}).
    """
    accepted: list[dict] = []
    dropped_detail: list[dict] = []
    anomalies = 0
    for row in rows or []:
        try:
            rec = TransactionRecord(
                deal_date=str(row.get("deal_date", "")),
                price_10k_won=int(row.get("price_10k_won") or 0),
                area_sqm=float(row.get("area_m2") or row.get("area_sqm") or 0),
                floor=int(row.get("floor") or 0),
                building_year=(row.get("build_year") or row.get("building_year")) or None,
            )
        except (ValidationError, ValueError, TypeError) as e:
            dropped_detail.append({"row": row, "error": str(e).split("\n")[0]})
            continue
        # ★유형별 면적 상한 — 모델은 **절대 상한**만 보고, 유형 판단은 여기서 한다.
        #   (모델은 prop_type 을 모른다. 종전엔 모델에 1000㎡ 가 박혀 토지 60%가 드롭됐다.)
        _cap = max_area_sqm_for(prop_type)
        if rec.area_sqm > _cap:
            dropped_detail.append(
                {"row": row, "error": f"면적 범위 초과({prop_type}): {rec.area_sqm}m² > {_cap:.0f}m²"},
            )
            continue
        out = dict(row)
        if recent_prices and len(recent_prices) >= 5:
            a = AnomalyDetector.check_price_anomaly(
                rec.price_10k_won, rec.area_sqm, region, recent_prices
            )
            out["is_anomaly"] = bool(a.get("is_anomaly"))
            out["anomaly_reason"] = a.get("reason", "")
            if out["is_anomaly"]:
                anomalies += 1
        accepted.append(out)
    if dropped_detail:
        logger.warning(
            "실거래 검증: 드롭 %d건 / 채택 %d건 (스키마 위반 제외)",
            len(dropped_detail),
            len(accepted),
        )
    return accepted, {
        "accepted": len(accepted),
        "dropped": len(dropped_detail),
        "anomalies": anomalies,
        "dropped_detail": dropped_detail,
    }
