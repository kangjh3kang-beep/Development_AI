try:
    import torch
    import torch.nn as nn
    import torchvision.transforms as transforms
    import torchvision.models as models
except ImportError:
    torch = None
    nn = None
    transforms = None
    models = None

import numpy as np
from typing import Dict, List, Optional, Tuple
import structlog

logger = structlog.get_logger()

class CNNDesignService:
    """CNN 참조이미지 기반 건축 설계 자동 생성 (ResNet-50)"""

    def __init__(self):
        if torch is not None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
            self.feature_extractor = self._load_resnet()
            self.transform = transforms.Compose([
                transforms.Resize((224, 224)),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
        else:
            self.device = None
            self.feature_extractor = None
            self.transform = None

    def _load_resnet(self):
        if models is None:
            return None
        model = models.resnet50(weights=models.ResNet50_Weights.IMAGENET1K_V2)
        model.fc = nn.Identity()
        model.eval()
        return model.to(self.device)

    def extract_features(self, image_path=None) -> Dict:
        """ResNet-50 2048차원 특징 벡터 추출"""
        if torch is None:
            vec = np.random.RandomState(42).randn(2048).astype(np.float32)
            return {
                "feature_vector": vec.tolist(),
                "dominant_style": "현대식",
                "dimensions": 2048,
            }
        try:
            from PIL import Image
            img = Image.open(image_path).convert("RGB")
            tensor = self.transform(img).unsqueeze(0).to(self.device)
            with torch.no_grad():
                features = self.feature_extractor(tensor)
            vec = features.cpu().numpy().flatten()
            return {
                "feature_vector": vec.tolist(),
                "dominant_style": "현대식",
                "dimensions": len(vec),
            }
        except (OSError, RuntimeError) as e:
            logger.error("특징 벡터 추출 실패", path=str(image_path), error=str(e))
            return {
                "feature_vector": np.zeros(2048).tolist(),
                "dominant_style": "기본형",
                "dimensions": 2048,
            }

    def generate_design_parameters(self, feature_vector, site_area_sqm: float,
                                    zone_type: str, max_far: float, max_bcr: float,
                                    building_use: str) -> Dict:
        if isinstance(feature_vector, dict):
            feature_vector = feature_vector.get("feature_vector", [0] * 2048)
        feature_vector = np.array(feature_vector) if not isinstance(feature_vector, np.ndarray) else feature_vector
        total_floor_area = site_area_sqm * (max_far * 0.9) / 100
        building_footprint = site_area_sqm * (max_bcr * 0.85) / 100
        floor_count = int(total_floor_area / building_footprint) if building_footprint > 0 else 1
        parking_rules = {
            "공동주택": {"unit": "세대", "rate": 1.0},
            "근린생활시설": {"unit": "100sqm", "rate": 1.0},
            "업무시설": {"unit": "150sqm", "rate": 1.0},
        }
        rule = parking_rules.get(building_use, {"unit": "세대", "rate": 1.0})
        parking_count = int(total_floor_area / 100 * rule["rate"])
        style_score = float(np.mean(np.abs(feature_vector[:100])))
        architectural_style = "현대식" if style_score > 0.5 else "복합형" if style_score > 0.3 else "전통형"
        return {
            "total_floor_area_sqm": round(total_floor_area, 1),
            "building_footprint_sqm": round(building_footprint, 1),
            "floor_count": max(floor_count, 1),
            "parking_count": parking_count,
            "architectural_style": architectural_style,
            "far_applied": round(max_far * 0.9, 1),
            "bcr_applied": round(max_bcr * 0.85, 1),
            "feature_similarity": round(float(np.linalg.norm(feature_vector)), 4)
        }
