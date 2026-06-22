"""코드리뷰 — security pnu 패턴 검증(외부 API에 무검증 유입 차단, 계약 경계 거부)."""
import pytest
from pydantic import ValidationError

from app.contracts.analysis import AnalysisInput


def test_pnu_pattern_rejects_invalid():
    with pytest.raises(ValidationError):
        AnalysisInput(pnu="abc")          # 비숫자 거부
    with pytest.raises(ValidationError):
        AnalysisInput(pnu="123")          # 비19자리 거부
    assert AnalysisInput(pnu="").pnu == ""             # 빈 허용(주소 도출 진입점)
    assert AnalysisInput(pnu="1" * 19).pnu == "1" * 19  # 19자리 PNU 허용
