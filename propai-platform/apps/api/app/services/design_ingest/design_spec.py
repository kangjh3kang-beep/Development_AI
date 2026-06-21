"""설계 도면 인제스천 공용 계약(DesignSpec).

업로드된 설계파일(엑셀/DXF/IFC/PDF/이미지)을 파서가 공통 구조로 정규화한다.
이 구조가 검색·조합·임베딩의 단일 계약이다. 추출 못 한 값은 None으로 둔다(추정 금지·정직).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field

# 도면 종류 — 파일명/내용 힌트로 분류. 미상은 unknown(추정 금지).
DRAWING_TYPES = (
    "site_plan",    # 배치도
    "floor_plan",   # 평면도
    "section",      # 단면도
    "elevation",    # 입면도/측면도
    "parking",      # 주차설계
    "spec_sheet",   # 설계 스펙(엑셀 등)
    "bim",          # IFC/BIM
    "unknown",
)

# 파일명 키워드 → 도면 종류(한국어 도면 관습). 소문자/원문 양쪽 매칭.
_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "site_plan": ("배치도", "배치", "site plan", "siteplan", "site"),
    "floor_plan": ("평면도", "평면", "floor plan", "floorplan", "plan"),
    "section": ("단면도", "단면", "section"),
    "elevation": ("입면도", "입면", "측면도", "측면", "elevation", "facade"),
    "parking": ("주차", "parking"),
}


def detect_drawing_type(filename: str = "", hints: str = "") -> str:
    """파일명+내용 힌트로 도면 종류를 분류한다. 못 맞추면 'unknown'."""
    hay = f"{filename} {hints}".lower()
    for dtype, keywords in _TYPE_KEYWORDS.items():
        if any(kw.lower() in hay for kw in keywords):
            return dtype
    return "unknown"


def compute_point_id(content_hash: str, tenant_id: str | None = None) -> str:
    """content_hash(+tenant_id) → Qdrant 결정적 포인트 ID(uuid5).

    인제스트(저장)와 조회(원본 presigned)가 동일 규칙으로 ID를 재계산해 공유한다.
    tenant_id 결합으로 테넌트별 네임스페이스 분리(교차테넌트 충돌 차단·미지정 시 hash-only 호환).
    """
    seed = f"{tenant_id}:{content_hash}" if tenant_id else content_hash
    return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))


@dataclass
class RoomSpec:
    """도면에서 추출한 공간(룸) 1건."""

    name: str
    area_sqm: float | None = None


@dataclass
class DesignSpec:
    """파서 공통 산출물 — 검색/조합/임베딩의 단일 계약."""

    source_format: str               # dxf | excel | ifc | pdf | image
    drawing_type: str = "unknown"    # DRAWING_TYPES 중 하나
    title: str | None = None
    total_area_sqm: float | None = None
    floor_count: int | None = None
    unit_count: int | None = None
    parking_count: int | None = None
    rooms: list[RoomSpec] = field(default_factory=list)
    dimensions: dict = field(default_factory=dict)   # bbox 등 기하 요약
    layers: list[str] = field(default_factory=list)  # CAD 레이어명
    raw_summary: str = ""            # 임베딩/검색용 원문 요약(PII 없는 텍스트)
    meta: dict = field(default_factory=dict)

    def to_embedding_text(self) -> str:
        """임베딩/검색용 텍스트로 직렬화(존재하는 값만, 추정 금지)."""
        parts: list[str] = [f"도면종류:{self.drawing_type}", f"형식:{self.source_format}"]
        if self.title:
            parts.append(f"제목:{self.title}")
        if self.total_area_sqm is not None:
            parts.append(f"면적:{self.total_area_sqm}㎡")
        if self.floor_count is not None:
            parts.append(f"층수:{self.floor_count}")
        if self.unit_count is not None:
            parts.append(f"세대수:{self.unit_count}")
        if self.parking_count is not None:
            parts.append(f"주차:{self.parking_count}")
        if self.rooms:
            parts.append("공간:" + ", ".join(r.name for r in self.rooms[:30] if r.name))
        if self.layers:
            parts.append("레이어:" + ", ".join(self.layers[:30]))
        if self.raw_summary:
            parts.append(self.raw_summary[:4000])
        return "\n".join(parts)

    def _canonical(self) -> dict:
        """content_hash용 정규화 dict — 순서/None 안정화."""
        return {
            "source_format": self.source_format,
            "drawing_type": self.drawing_type,
            "title": self.title,
            "total_area_sqm": self.total_area_sqm,
            "floor_count": self.floor_count,
            "unit_count": self.unit_count,
            "parking_count": self.parking_count,
            "rooms": sorted([f"{r.name}:{r.area_sqm}" for r in self.rooms]),
            "layers": sorted(self.layers),
            "dimensions": self.dimensions,
        }

    def content_hash(self) -> str:
        """내용 기반 SHA-256 — 동일 내용 중복제거(멱등)용."""
        blob = json.dumps(self._canonical(), ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def point_id(self, tenant_id: str | None = None) -> str:
        """Qdrant 포인트 ID — (tenant_id:)content_hash 기반 결정적 UUID.

        tenant_id를 결합해 테넌트별 네임스페이스로 분리한다. 테넌트별 재업로드 멱등성은
        유지하면서, 타 테넌트가 동일 바이트 파일을 올려 소유표시(payload.tenant_id)를
        덮어쓰는 교차테넌트 충돌을 구조적으로 차단한다(tenant_id 미지정 시 hash-only 호환).
        """
        return compute_point_id(self.content_hash(), tenant_id)

    def to_payload(self) -> dict:
        """Qdrant 페이로드(검색 필터/표시용). PII 미포함 — 원문 바이트 저장 안 함."""
        return {
            "content_hash": self.content_hash(),
            "source_format": self.source_format,
            "drawing_type": self.drawing_type,
            "title": self.title,
            "total_area_sqm": self.total_area_sqm,
            "floor_count": self.floor_count,
            "unit_count": self.unit_count,
            "parking_count": self.parking_count,
            "room_count": len(self.rooms),
            "summary": self.raw_summary[:2000],
        }
