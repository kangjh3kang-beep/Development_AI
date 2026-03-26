"""참조 이미지 분석 서비스 단위 테스트.

T3-5: 기본 이미지 특징 추출, 유사도 계산, CNN 폴백을 검증한다.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from apps.api.services.reference_image_service import (
    ImageFeatures,
    ReferenceImageService,
)


# ──────────────────────────────────────────────
# 기본 특징 추출
# ──────────────────────────────────────────────


class TestExtractFeaturesBasic:
    """기본 이미지 특징 추출을 검증한다."""

    def test_기본_특징_추출(self):
        """width=1920, height=1080 이미지의 특성을 추출한다."""
        result = ReferenceImageService.extract_features_basic(1920, 1080)
        assert result.width == 1920
        assert result.height == 1080
        assert result.brightness == 0.5
        assert isinstance(result.style_tags, list)

    def test_aspect_ratio_계산(self):
        """1920/1080 = 1.78 종횡비를 검증한다."""
        result = ReferenceImageService.extract_features_basic(1920, 1080)
        assert result.aspect_ratio == pytest.approx(1.78, abs=0.01)

    def test_고해상도_태그(self):
        """width >= 3000이면 '고해상도' 태그가 부여된다."""
        result = ReferenceImageService.extract_features_basic(4000, 2000)
        assert "고해상도" in result.style_tags

    def test_파노라마_태그(self):
        """aspect_ratio > 1.5이면 '파노라마' 태그가 부여된다."""
        result = ReferenceImageService.extract_features_basic(2000, 1000)
        assert "파노라마" in result.style_tags

    def test_세로형_태그(self):
        """aspect_ratio < 0.7이면 '세로형' 태그가 부여된다."""
        result = ReferenceImageService.extract_features_basic(500, 1000)
        assert "세로형" in result.style_tags

    def test_표준비율_태그(self):
        """0.7 <= aspect_ratio <= 1.5이면 '표준비율' 태그가 부여된다."""
        result = ReferenceImageService.extract_features_basic(1000, 1000)
        assert "표준비율" in result.style_tags

    def test_height_0_처리(self):
        """height가 0이면 aspect_ratio는 0이다."""
        result = ReferenceImageService.extract_features_basic(1920, 0)
        assert result.aspect_ratio == 0


# ──────────────────────────────────────────────
# 유사도 계산
# ──────────────────────────────────────────────


class TestCalculateSimilarity:
    """유사도 계산을 검증한다."""

    def test_유사도_동일_이미지(self):
        """동일한 특성의 이미지는 유사도 1.0이다."""
        features = ReferenceImageService.extract_features_basic(1920, 1080, 0.6)
        similarity = ReferenceImageService.calculate_similarity(features, features)
        assert similarity == pytest.approx(1.0)

    def test_유사도_0_1_범위(self):
        """유사도는 0~1 범위 내에 있어야 한다."""
        features_a = ReferenceImageService.extract_features_basic(1920, 1080, 0.9)
        features_b = ReferenceImageService.extract_features_basic(500, 1000, 0.1)
        similarity = ReferenceImageService.calculate_similarity(features_a, features_b)
        assert 0 <= similarity <= 1

    def test_유사한_이미지_높은_유사도(self):
        """비슷한 특성의 이미지는 높은 유사도를 가진다."""
        features_a = ReferenceImageService.extract_features_basic(1920, 1080, 0.5)
        features_b = ReferenceImageService.extract_features_basic(1920, 1080, 0.55)
        similarity = ReferenceImageService.calculate_similarity(features_a, features_b)
        assert similarity > 0.9


# ──────────────────────────────────────────────
# CNN 폴백
# ──────────────────────────────────────────────


class TestCNNFallback:
    """CNN 특징 추출 폴백을 검증한다."""

    def test_cnn_미설치_None(self):
        """torchvision이 설치되지 않으면 None을 반환한다."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name in ("torch", "torchvision"):
                raise ImportError(f"모듈 {name} 없음")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = ReferenceImageService.extract_features_cnn("/fake/path.jpg")
            assert result is None
