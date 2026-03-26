"""CoVe O2: SDXL 평면도 방 개수 일치율 벤치마크.

기준: 일치율 ≥ 85%
실행: pytest tests/benchmarks/bench_sdxl.py -v
"""

import pytest

pytestmark = pytest.mark.benchmark

ROOM_SPECS = [
    {"rooms": 3, "description": "3룸 아파트 평면도"},
    {"rooms": 4, "description": "4룸 오피스텔 평면도"},
    {"rooms": 2, "description": "원룸+거실 소형 평면도"},
    {"rooms": 5, "description": "5룸 대형 주택 평면도"},
]

MATCH_THRESHOLD = 0.85


class TestSDXLRoomCount:
    """SDXL 생성 평면도 방 개수 검증."""

    @pytest.mark.skip(reason="Replicate API 키 + 이미지 분석 모델 필요")
    @pytest.mark.parametrize("spec", ROOM_SPECS, ids=[s["description"] for s in ROOM_SPECS])
    def test_room_count_matches(self, spec: dict) -> None:
        """생성된 평면도의 방 개수가 요청과 일치한다."""
        # TODO: FloorPlanImageService → Replicate SDXL → 이미지 분석 → 방 개수
        pass
