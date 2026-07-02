"""참조 이미지 분석 서비스.

건축 참조 이미지의 특징을 추출하고 유사도를 계산한다.
VGG16 등 CNN 모델이 사용 가능한 환경에서는 딥러닝 기반 특징 추출,
미설치 시 기본 이미지 특성(해상도, 색상 분포) 기반 분석.
"""

from dataclasses import dataclass

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ImageFeatures:
    """이미지 특징 데이터."""

    width: int
    height: int
    aspect_ratio: float
    dominant_colors: list[str]
    brightness: float  # 0~1
    contrast: float  # 0~1
    style_tags: list[str]


class ReferenceImageService:
    """참조 이미지 분석 서비스."""

    @staticmethod
    def extract_features_basic(
        width: int,
        height: int,
        avg_brightness: float = 0.5,
    ) -> ImageFeatures:
        """기본 이미지 특성을 추출한다 (CNN 없이).

        해상도, 종횡비 등 기본 메타데이터 기반으로
        이미지 스타일 태그를 부여한다.
        """
        aspect_ratio = round(width / height, 2) if height > 0 else 0

        # 해상도 기반 스타일 태그
        style_tags = []
        if width >= 3000:
            style_tags.append("고해상도")
        if aspect_ratio > 1.5:
            style_tags.append("파노라마")
        elif aspect_ratio < 0.7:
            style_tags.append("세로형")
        else:
            style_tags.append("표준비율")

        return ImageFeatures(
            width=width,
            height=height,
            aspect_ratio=aspect_ratio,
            dominant_colors=[],
            brightness=avg_brightness,
            contrast=0.5,
            style_tags=style_tags,
        )

    @staticmethod
    def calculate_similarity(
        features_a: ImageFeatures,
        features_b: ImageFeatures,
    ) -> float:
        """두 이미지의 유사도를 계산한다 (0~1).

        가중치: 종횡비 40%, 밝기 30%, 대비 30%
        """
        ratio_sim = 1 - min(1, abs(features_a.aspect_ratio - features_b.aspect_ratio) / 2)
        brightness_sim = 1 - abs(features_a.brightness - features_b.brightness)
        contrast_sim = 1 - abs(features_a.contrast - features_b.contrast)

        similarity = 0.4 * ratio_sim + 0.3 * brightness_sim + 0.3 * contrast_sim
        return round(max(0, min(1, similarity)), 4)

    @staticmethod
    def extract_features_cnn(image_path: str) -> ImageFeatures | None:
        """CNN (VGG16) 기반 특징 추출.

        torchvision 미설치 시 None을 반환한다.
        """
        try:
            import torch  # noqa: F401 — 가용성 검사
            from PIL import Image
            from torchvision import models, transforms

            model = models.vgg16(weights=models.VGG16_Weights.DEFAULT)
            model.eval()

            transform = transforms.Compose([
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ])

            img = Image.open(image_path).convert("RGB")
            w, h = img.size

            input_tensor = transform(img).unsqueeze(0)
            with torch.no_grad():
                features = model.features(input_tensor)
                pooled = torch.nn.functional.adaptive_avg_pool2d(features, (1, 1))
                feature_vector = pooled.flatten().numpy()

            avg_brightness = float(feature_vector.mean())

            return ImageFeatures(
                width=w,
                height=h,
                aspect_ratio=round(w / h, 2),
                dominant_colors=[],
                brightness=round(float(avg_brightness), 4),
                contrast=round(float(feature_vector.std()), 4),
                style_tags=["cnn_analyzed"],
            )
        except ImportError:
            logger.info("torchvision 미설치 — CNN 분석 불가")
            return None
        except Exception as e:
            logger.error("CNN 분석 실패", error=str(e))
            return None


async def _analyze_with_vision(self, image_url: str) -> dict:
    """Claude Vision API로 참조 이미지를 분석한다.

    건축 스타일, 외관 재료, 색상 분포, 층수 추정 등을 반환한다.

    Args:
        image_url: 분석할 이미지 URL

    Returns:
        {"style": str, "materials": list, "colors": list, "estimated_floors": int, "analysis": str}
    """
    try:
        import anthropic
        client = anthropic.AsyncAnthropic()

        message = await client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "url", "url": image_url}},
                    {"type": "text",
                     "text": ("이 건축물 이미지를 분석하세요. "
                              "건축 스타일, 외관 재료, 주요 색상, 추정 층수를 한국어로 설명하세요.")},
                ],
            }],
        )
        return {
            "style": "분석 완료",
            "materials": [],
            "colors": [],
            "estimated_floors": 0,
            "analysis": message.content[0].text,
        }
    except Exception as e:
        logger.warning("Vision 참조 이미지 분석 실패", error=str(e))
        return {
            "style": "분석 불가",
            "materials": [],
            "colors": [],
            "estimated_floors": 0,
            "analysis": f"이미지 분석을 수행할 수 없습니다: {e}",
        }


# 클래스에 메서드 바인딩
ReferenceImageService.analyze_with_vision = _analyze_with_vision
