"""ParkingService 단위 테스트.

번호판 정규식 검증(validate_plate_number)과 상수를 테스트한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.parking_service import _PLATE_PATTERN, validate_plate_number


class TestPlatePattern:
    """_PLATE_PATTERN 정규식 테스트."""

    def test_3자리_한글_4자리(self):
        """123가4567 형식."""
        assert _PLATE_PATTERN.match("123가4567") is not None

    def test_2자리_한글_4자리(self):
        """12가3456 형식."""
        assert _PLATE_PATTERN.match("12가3456") is not None

    def test_영문_불일치(self):
        assert _PLATE_PATTERN.match("123A4567") is None

    def test_한글_2자_불일치(self):
        assert _PLATE_PATTERN.match("123가나4567") is None

    def test_숫자_부족(self):
        assert _PLATE_PATTERN.match("1가234") is None


class TestValidatePlateNumber:
    """validate_plate_number 함수 테스트."""

    def test_유효한_번호판(self):
        assert validate_plate_number("123가4567") == "123가4567"

    def test_2자리_유효(self):
        assert validate_plate_number("12나3456") == "12나3456"

    def test_공백_제거(self):
        assert validate_plate_number("123 가 4567") == "123가4567"

    def test_하이픈_제거(self):
        assert validate_plate_number("123-가-4567") == "123가4567"

    def test_점_제거(self):
        assert validate_plate_number("123.가.4567") == "123가4567"

    def test_무효한_번호판_None(self):
        assert validate_plate_number("ABCD1234") is None

    def test_빈_문자열_None(self):
        assert validate_plate_number("") is None

    def test_숫자만_None(self):
        assert validate_plate_number("1234567") is None

    def test_한글_위치_올바름(self):
        """한글이 중간에 있어야 함."""
        assert validate_plate_number("가1234567") is None

    def test_다양한_한글(self):
        assert validate_plate_number("78다1234") == "78다1234"
        assert validate_plate_number("123라5678") == "123라5678"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
