"""CoVe O5: Three.js 3D 로딩 시간 벤치마크.

기준: 1,000요소 ≤ 5초
실행: pytest tests/benchmarks/bench_threejs.py -v
"""

import pytest

pytestmark = pytest.mark.benchmark


class TestThreeJSLoading:
    """Three.js geometry 로딩 성능 검증."""

    @pytest.mark.skip(reason="BIM 서비스 + 프론트엔드 필요 — Codex 공동")
    def test_loading_1000_elements(self) -> None:
        """1,000개 요소 Three.js geometry 생성이 5초 이내."""
        # TODO: BIMIFCService._generate_threejs_geometry()로 1000개 요소 생성
        # 시간 측정
        pass
