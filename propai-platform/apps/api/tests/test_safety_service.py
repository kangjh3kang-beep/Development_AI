"""SafetyService 단위 테스트.

YOLOv8 안전관리 서비스의 상수, URL 마스킹 등
외부 의존성 없이 검증 가능한 로직을 테스트한다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.safety_service import (
    _FRAME_SKIP,
    _MIN_CONFIDENCE,
    _VIOLATION_CLASSES,
    _sanitize_url,
)


class TestConstants:
    """모듈 수준 상수 테스트."""

    def test_프레임_스킵_5(self):
        assert _FRAME_SKIP == 5

    def test_최소_신뢰도_045(self):
        assert _MIN_CONFIDENCE == 0.45

    def test_위반_클래스_2개(self):
        assert len(_VIOLATION_CLASSES) == 2

    def test_helmet_off_클래스(self):
        assert _VIOLATION_CLASSES[0] == "helmet_off"

    def test_vest_off_클래스(self):
        assert _VIOLATION_CLASSES[1] == "vest_off"


class TestSanitizeUrl:
    """_sanitize_url 함수 테스트."""

    def test_RTSP_비밀번호_마스킹(self):
        url = "rtsp://admin:password123@192.168.1.100:554/stream1"
        result = _sanitize_url(url)
        assert "password123" not in result
        assert "***@" in result
        assert "192.168.1.100" in result

    def test_비밀번호_없는_URL_그대로(self):
        url = "rtsp://192.168.1.100:554/stream1"
        result = _sanitize_url(url)
        assert result == url

    def test_HTTP_URL_마스킹(self):
        url = "http://user:secret@example.com/path"
        result = _sanitize_url(url)
        assert "secret" not in result
        assert "***@" in result

    def test_복잡한_비밀번호_마스킹(self):
        url = "rtsp://admin:p@ss!word@cam.local:554/live"
        result = _sanitize_url(url)
        assert "p@ss!word" not in result

    def test_빈_URL(self):
        result = _sanitize_url("")
        assert result == ""

    def test_일반_URL_변경없음(self):
        url = "https://example.com/stream"
        result = _sanitize_url(url)
        assert result == url


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
