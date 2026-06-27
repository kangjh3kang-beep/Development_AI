"""mass_backbone region_util — 주소→시군구 도출(프론트 lib/region.ts 미러) 단위테스트."""
from app.services.mass_backbone.region_util import dominant_region, region_from_address


def test_region_from_address_basic():
    assert region_from_address("서울특별시 강남구 역삼동 123-4") == "강남구"
    assert region_from_address("경기도 화성시 동탄대로 123") == "화성시"       # 특별/광역시 토큰 무시
    assert region_from_address("대구광역시 수성구 범어동") == "수성구"         # 광역시 산하 구
    assert region_from_address("강원특별자치도 양양군 강현면") == "양양군"


def test_region_from_address_none():
    assert region_from_address("") is None
    assert region_from_address(None) is None
    assert region_from_address("주소미상") is None   # 임의 추정 금지


def test_dominant_region_majority_and_determinism():
    # 화성시 2 vs 수원시 1 → 다수결 화성시
    addrs = ["경기도 화성시 a", "경기도 화성시 b", "경기도 수원시 c", None, "주소미상"]
    assert dominant_region(addrs) == "화성시"
    # 전부 미매칭 → None(가짜 생성 금지)
    assert dominant_region([None, "", "x"]) is None
    # 동률은 사전순(결정론)
    assert dominant_region(["서울특별시 강남구 a", "경기도 수원시 b"]) == "강남구"  # 강남구 < 수원시
