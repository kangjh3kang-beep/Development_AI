"""동적 모듈 조립기 — 개발유형 코드로 적절한 모듈 인스턴스 반환."""

from __future__ import annotations

from app.services.feasibility.modules.base_module import BaseModule
from app.services.feasibility.modules.m01_redevelopment import M01Redevelopment
from app.services.feasibility.modules.m02_reconstruction import M02Reconstruction
from app.services.feasibility.modules.m04_union_housing import M04UnionHousing
from app.services.feasibility.modules.m08_officetel import M08Officetel
from app.services.feasibility.modules.generic_module import GenericModule


# 특화 모듈 매핑
_SPECIALIZED: dict[str, type[BaseModule]] = {
    "M01": M01Redevelopment,
    "M02": M02Reconstruction,
    "M04": M04UnionHousing,
    "M08": M08Officetel,
}

# 전체 지원 코드
ALL_MODULE_CODES = [f"M{i:02d}" for i in range(1, 16)]


def get_module(development_type: str) -> BaseModule:
    """개발유형 코드 → 모듈 인스턴스 반환.

    Args:
        development_type: 'M01'~'M15'

    Returns:
        BaseModule 하위 클래스 인스턴스

    Raises:
        ValueError: 지원하지 않는 코드
    """
    if development_type not in ALL_MODULE_CODES:
        raise ValueError(f"지원하지 않는 개발유형: {development_type}. 유효값: M01~M15")

    if development_type in _SPECIALIZED:
        return _SPECIALIZED[development_type]()

    return GenericModule(development_type)


def list_modules() -> list[dict[str, str]]:
    """전체 모듈 목록 반환."""
    result = []
    for code in ALL_MODULE_CODES:
        module = get_module(code)
        result.append({
            "code": module.code,
            "name": module.name,
            "type": "specialized" if code in _SPECIALIZED else "generic",
        })
    return result
