"""Phase 0 — 법정/도메인 수치 하드코딩 정적 스캐너(INV-3).

소스 텍스트에서 '법정/도메인 키워드 이름 = 수치 리터럴' 할당을 탐지해 "name=value" 목록 반환.
허용리스트 제외. AT-9류(각 페이즈) 테스트가 src에 대해 호출하여 하드코딩 부재를 강제한다.
"""
from __future__ import annotations

import re

# 법정/도메인 수치를 시사하는 식별자 키워드(부분일치).
_LEGAL_KEYWORDS = (
    "far", "bcr", "height", "area", "limit", "ratio", "floor", "setback", "coverage",
    "threshold", "margin", "distance", "width", "depth", "span", "speed", "hours",
    "exclusion", "relax", "incentive", "tol", "pct", "percent",
)

# 의미 없는 일반 상수(인덱스·배수 등)는 과탐 제외.
_BENIGN = {"0", "1", "2", "100", "1000", "10", "1.0", "0.0", "0.5"}

_ASSIGN_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\d+(?:\.\d+)?)")


def scan_for_numeric_legal_constants(source: str, allowlist: tuple[str, ...] = ()) -> list[str]:
    """source에서 하드코딩 의심 수치 할당 목록("name=value") 반환. 없으면 []."""
    hits: list[str] = []
    for m in _ASSIGN_RE.finditer(source or ""):
        name, value = m.group(1), m.group(2)
        low = name.lower()
        if name in allowlist or value in _BENIGN:
            continue
        if any(k in low for k in _LEGAL_KEYWORDS):
            hits.append(f"{name}={value}")
    return hits


# AT-6에서 쓰는 별칭.
static_scan = scan_for_numeric_legal_constants
