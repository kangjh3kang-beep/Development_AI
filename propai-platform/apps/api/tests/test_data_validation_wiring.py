"""Fix #2(감사 HIGH): 외부데이터 수집 검증 배선.

validate_transactions가 TransactionRecord 스키마 위반행을 드롭하고, recent_prices가 있으면
AnomalyDetector(IQR)로 이상치를 플래그하는지 검증. 순수 함수(pydantic만 의존)."""
from app.services.data_validation.validator import validate_transactions


def test_drops_schema_invalid_rows():
    rows = [
        {"deal_date": "2026년 6월 1일", "price_10k_won": 50000, "area_m2": 84.0, "floor": 10},  # valid
        {"deal_date": "2026년 6월 2일", "price_10k_won": 0, "area_m2": 84.0, "floor": 10},       # price<=0
        {"deal_date": "2026년 6월 3일", "price_10k_won": 50000, "area_m2": 0.0, "floor": 10},    # area<=0
        {"deal_date": "2026년 6월 4일", "price_10k_won": 50000, "area_m2": 84.0, "floor": 999},  # floor>120
    ]
    accepted, report = validate_transactions(rows)
    assert report["accepted"] == 1
    assert report["dropped"] == 3
    assert accepted[0]["price_10k_won"] == 50000


def test_flags_price_anomaly_with_recent():
    # 40억(400000만원)/84m² ≈ 47.6M원/m² vs 최근 ~5.95M원/m² → IQR 이상치
    rows = [{"deal_date": "2026년 6월 1일", "price_10k_won": 400000, "area_m2": 84.0, "floor": 10}]
    recent = [5_500_000, 5_700_000, 5_800_000, 5_900_000, 6_000_000,
              6_100_000, 6_200_000, 6_300_000, 6_400_000, 6_500_000]
    accepted, report = validate_transactions(rows, region="서울", recent_prices=recent)
    assert len(accepted) == 1
    assert accepted[0]["is_anomaly"] is True
    assert report["anomalies"] == 1


def test_no_anomaly_when_in_range():
    rows = [{"deal_date": "2026년 6월 1일", "price_10k_won": 50000, "area_m2": 84.0, "floor": 10}]
    recent = [5_500_000, 5_700_000, 5_800_000, 5_900_000, 6_000_000,
              6_100_000, 6_200_000, 6_300_000, 6_400_000, 6_500_000]
    accepted, report = validate_transactions(rows, region="서울", recent_prices=recent)
    assert accepted[0]["is_anomaly"] is False
    assert report["anomalies"] == 0


def test_empty_rows():
    accepted, report = validate_transactions([])
    assert accepted == []
    assert report["accepted"] == 0
