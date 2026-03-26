"""DigitalTwinService 단위 테스트.

IsolationForest 기반 IoT 이상 감지의 상수, 동기 함수를 검증한다.
sklearn이 설치된 환경에서만 _fit_and_predict 테스트 실행.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.digital_twin_service import (
    _MIN_DATA_POINTS_FOR_FIT,
    _RECOMMENDED_DATA_POINTS,
)


class TestConstants:
    """모듈 수준 상수 테스트."""

    def test_최소_데이터_포인트_100(self):
        assert _MIN_DATA_POINTS_FOR_FIT == 100

    def test_권장_데이터_포인트_1440(self):
        assert _RECOMMENDED_DATA_POINTS == 1440

    def test_최소값_권장값_미만(self):
        assert _MIN_DATA_POINTS_FOR_FIT < _RECOMMENDED_DATA_POINTS


class TestFitAndPredict:
    """_fit_and_predict 동기 함수 테스트 (sklearn 필요)."""

    @pytest.fixture(autouse=True)
    def _skip_if_no_sklearn(self):
        pytest.importorskip("sklearn")
        pytest.importorskip("numpy")

    def test_정상_데이터_예측(self):
        import numpy as np

        from apps.api.services.digital_twin_service import _fit_and_predict

        rng = np.random.RandomState(42)
        # 정상 데이터 200개 (평균 50, 분산 적음)
        historical = rng.normal(loc=50, scale=2, size=(200, 3)).tolist()
        current = [50.0, 50.0, 50.0]

        score, is_anomaly = _fit_and_predict(historical, current)
        assert isinstance(score, float)
        assert isinstance(is_anomaly, bool)

    def test_이상_데이터_감지(self):
        import numpy as np

        from apps.api.services.digital_twin_service import _fit_and_predict

        rng = np.random.RandomState(42)
        historical = rng.normal(loc=50, scale=2, size=(200, 3)).tolist()
        # 극단적 이상치
        current = [200.0, 200.0, 200.0]

        score, is_anomaly = _fit_and_predict(historical, current)
        assert is_anomaly is True
        assert score < 0

    def test_정상_데이터_비이상(self):
        import numpy as np

        from apps.api.services.digital_twin_service import _fit_and_predict

        rng = np.random.RandomState(42)
        historical = rng.normal(loc=50, scale=2, size=(200, 3)).tolist()
        current = [50.1, 49.9, 50.0]

        score, is_anomaly = _fit_and_predict(historical, current)
        assert is_anomaly is False
        assert score > 0

    def test_반환형_튜플(self):
        import numpy as np

        from apps.api.services.digital_twin_service import _fit_and_predict

        rng = np.random.RandomState(42)
        historical = rng.normal(loc=0, scale=1, size=(150, 2)).tolist()
        current = [0.0, 0.0]

        result = _fit_and_predict(historical, current)
        assert isinstance(result, tuple)
        assert len(result) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
