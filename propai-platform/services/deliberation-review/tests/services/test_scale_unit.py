"""AT-6 — 축척 전 chain 실패 시 진행 거부."""
import pytest

from app.contracts.enums import ScaleSource
from app.core.errors import PreflightRefused
from app.services.preflight.scale_unit import ScaleUnitResolver

NO_DIM: dict = {}  # 치수/축척표기/사용자입력/공부 전무


def test_scale_unresolved_refuses():
    with pytest.raises(PreflightRefused):
        ScaleUnitResolver().resolve(drawing=NO_DIM)


def test_scale_notation_parsed():
    r = ScaleUnitResolver().resolve(drawing={"scale_text": "1:100"})
    assert r.scale_denominator == 100.0
    assert r.source == ScaleSource.NOTATION
