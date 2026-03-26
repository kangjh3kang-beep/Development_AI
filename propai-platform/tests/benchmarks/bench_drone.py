"""CoVe O6: YOLOv8 하자 탐지 F1 벤치마크.

기준: F1 ≥ 0.80
실행: pytest tests/benchmarks/bench_drone.py -v
"""

import pytest

pytestmark = pytest.mark.benchmark

F1_THRESHOLD = 0.80


class TestDroneDefectDetection:
    """드론 하자 탐지 F1 스코어 검증."""

    @pytest.mark.skip(reason="Roboflow API 키 + 테스트 이미지셋 필요")
    def test_f1_score_above_threshold(self) -> None:
        """하자 탐지 F1 스코어가 0.80 이상인지 확인."""
        # TODO: 테스트 이미지셋에 대해 DroneIoTService로 추론
        # TP, FP, FN 집계 후 F1 = 2*P*R/(P+R) 계산
        pass

    @pytest.mark.skip(reason="Roboflow API 키 + 테스트 이미지셋 필요")
    def test_severity_classification_accuracy(self) -> None:
        """심각도 분류 정확도 검증."""
        pass
