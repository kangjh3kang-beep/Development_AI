"""
계산 메타데이터 — 모든 계산 결과에 데이터 출처와 신선도 정보를 첨부.
이를 통해 사용자와 시스템 모두 계산의 신뢰도를 판단할 수 있다.
"""
from datetime import datetime
from typing import Optional


class CalculationMetadata:
    """계산 결과에 첨부하는 메타데이터."""

    def __init__(self, calculation_type: str):
        self.calculation_type = calculation_type
        self.calculated_at = datetime.now()
        self.data_sources: list[dict] = []
        self.warnings: list[str] = []
        self.confidence_level: str = "high"  # high | medium | low
        self.legal_basis_date: Optional[str] = None  # 법령 기준일

    def add_source(self, name: str, source_type: str, last_updated: Optional[datetime] = None, is_live: bool = False):
        """사용된 데이터 소스 기록."""
        self.data_sources.append({
            "name": name,
            "type": source_type,  # "공공API" | "하드코딩" | "사용자입력" | "ML모델"
            "last_updated": last_updated.isoformat() if last_updated else None,
            "is_live": is_live,  # 실시간 조회 여부
        })

        # 하드코딩 데이터 사용 시 자동 경고
        if source_type == "하드코딩":
            self.warnings.append(f"'{name}'은 하드코딩 데이터입니다. 최신 법령과 차이가 있을 수 있습니다.")
            if self.confidence_level == "high":
                self.confidence_level = "medium"

    def add_warning(self, warning: str):
        self.warnings.append(warning)

    def set_legal_basis(self, basis_date: str):
        """법령 기준일 설정 (예: '2024-06-01')."""
        self.legal_basis_date = basis_date

    def to_dict(self) -> dict:
        return {
            "calculation_type": self.calculation_type,
            "calculated_at": self.calculated_at.isoformat(),
            "data_sources": self.data_sources,
            "warnings": self.warnings,
            "confidence_level": self.confidence_level,
            "legal_basis_date": self.legal_basis_date,
            "disclaimer": "본 계산 결과는 참고용이며, 실제 세금/금융 의사결정 시 전문가 확인을 권장합니다.",
        }
