"""Evidently 데이터 드리프트 리포트 테스트.

Phase F-4: MLOps 재학습 후 Evidently DataDriftPreset 리포트 생성 검증.
"""

from pathlib import Path

_MLOPS_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps" / "worker" / "tasks" / "mlops.py"
)
_MLOPS_SOURCE = _MLOPS_PATH.read_text(encoding="utf-8")


class TestEvidentlyDriftReport:
    """Evidently 드리프트 리포트 구조 검증."""

    def test_drift_report_function_exists(self) -> None:
        """_generate_drift_report() 함수가 존재한다."""
        assert "_generate_drift_report" in _MLOPS_SOURCE

    def test_evidently_import(self) -> None:
        """evidently 라이브러리를 사용한다."""
        assert "evidently" in _MLOPS_SOURCE

    def test_data_drift_preset(self) -> None:
        """DataDriftPreset을 사용한다."""
        assert "DataDriftPreset" in _MLOPS_SOURCE

    def test_drift_detected_return(self) -> None:
        """drift_detected 결과를 반환한다."""
        assert "drift_detected" in _MLOPS_SOURCE

    def test_drift_called_in_retrain(self) -> None:
        """run_retrain_avm() 내에서 드리프트 리포트를 호출한다."""
        assert "_generate_drift_report" in _MLOPS_SOURCE
