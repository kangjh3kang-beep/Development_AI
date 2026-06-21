"""설계 도면 인제스천 공용 계약(DesignSpec).

업로드된 설계파일(엑셀/DXF/IFC/PDF/이미지)을 파서가 공통 구조로 정규화한다.
이 구조가 검색·조합·임베딩의 단일 계약이다. 추출 못 한 값은 None으로 둔다(추정 금지·정직).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field

# 도면 분류 택소노미 — 실무 전수조사(건축법 설계도서 작성기준·분야별 도면·NCS/AIA/IFC·
# 유사플랫폼) 근거로 확장. 단일 출처: code → {ko, discipline, set, keywords}.
# ★detect 우선순위 = 이 dict의 삽입 순서. 분야별/복합 키워드(구조평면·천장도 등)를 먼저 두고,
# 일반 건축(평면/입면/단면/배치)을 뒤에 둬 'X평면도'가 floor_plan으로 오분류되지 않게 한다.
# 분야: 공통/건축/구조/전기/기계설비/급배수위생/소방/토목/조경/통신. set: 인허가/실시설계/상세.
# 기존 코드(site_plan/floor_plan/section/elevation/parking/spec_sheet/bim)는 하위호환 유지.
DRAWING_TYPE_META: dict[str, dict] = {
    # ── 공통(common) ──
    "cover": {"ko": "표지·도면목록", "discipline": "공통", "set": "공통",
              "keywords": ("표지", "표제", "도면목록", "도면리스트", "목록표",
                           "cover", "title sheet", "sheet index", "drawing list")},
    "general_notes": {"ko": "일반사항·범례·기호", "discipline": "공통", "set": "공통",
                      "keywords": ("일반사항", "범례", "기호표", "general notes", "legend", "symbols")},
    # ── 구조(structural) — 복합 키워드 먼저 ──
    "structural_plan": {"ko": "구조 평면도(골조)", "discipline": "구조", "set": "실시설계",
                        "keywords": ("구조평면", "골조", "구조도", "구조일반", "structural plan",
                                     "framing plan", "structural")},
    "foundation_plan": {"ko": "기초 평면·상세", "discipline": "구조", "set": "실시설계",
                        "keywords": ("기초도", "기초평면", "기초상세", "foundation")},
    "rebar_detail": {"ko": "배근상세·부재일람", "discipline": "구조", "set": "실시설계",
                     "keywords": ("배근", "부재일람", "철근", "rebar", "reinforcement", "member schedule")},
    # ── 설비/전기/통신/소방(MEP) ──
    "electrical_plan": {"ko": "전기 평면·계통도", "discipline": "전기", "set": "실시설계",
                        # "계통도"는 급배수/소방 등과 공용이라 제외 — 전기 고유어만(간선계통 등).
                        "keywords": ("전기", "간선계통", "간선", "조명", "콘센트", "수전",
                                     "electrical", "power", "lighting", "riser", "single line")},
    "hvac_plan": {"ko": "공조·환기(기계설비)", "discipline": "기계설비", "set": "실시설계",
                  "keywords": ("공조", "환기", "덕트", "기계설비", "냉난방", "장비배치",
                               "hvac", "ventilation", "duct", "mechanical")},
    "plumbing_plan": {"ko": "급배수·위생설비", "discipline": "급배수위생", "set": "실시설계",
                      # bare "배수"는 토목 우배수와 충돌 → "급배수" 등 고유어만.
                      "keywords": ("급배수", "급수", "위생설비", "오수관", "정화조",
                                   "plumbing", "sanitary")},
    "fire_protection_plan": {"ko": "소방·방재설비", "discipline": "소방", "set": "실시설계",
                             "keywords": ("소방", "소화", "스프링클러", "제연", "방재",
                                          "fire protection", "sprinkler", "fire fighting")},
    "telecom_plan": {"ko": "정보통신 도면", "discipline": "통신", "set": "실시설계",
                     "keywords": ("정보통신", "구내통신", "통신", "방송", "telecom", "communication")},
    # ── 토목·조경(civil/landscape) ──
    "civil_plan": {"ko": "토목 도면(토공·우배수·도로)", "discipline": "토목", "set": "실시설계",
                   "keywords": ("토목", "토공", "우수", "오수배수", "우배수", "옹벽", "굴착", "도로",
                                "civil", "earthwork", "drainage", "grading")},
    "landscape_plan": {"ko": "조경 도면(식재·포장)", "discipline": "조경", "set": "인허가",
                       "keywords": ("조경", "식재", "포장", "녹지", "landscape", "planting")},
    # ── 건축 특수/복합(architecture, 복합 키워드 — 일반 평면/단면보다 먼저) ──
    "site_section": {"ko": "대지 종·횡단면", "discipline": "건축", "set": "인허가",
                     "keywords": ("대지종횡단면", "대지단면", "종횡단면", "site section", "ground profile")},
    "site_survey": {"ko": "대지현황측량도", "discipline": "건축", "set": "인허가",
                    "keywords": ("현황측량", "측량도", "현황도", "survey", "existing condition")},
    "area_diagram": {"ko": "면적산출도(구적도)·면적표", "discipline": "건축", "set": "인허가",
                     "keywords": ("구적도", "면적산출", "면적표", "면적일람", "area calculation",
                                  "area schedule", "area table")},
    "daylight_analysis": {"ko": "일조(정북일조)분석도", "discipline": "건축", "set": "인허가",
                          "keywords": ("일조", "정북일조", "일영", "음영", "sun shadow", "daylight",
                                       "solar", "shadow study")},
    "fire_egress_plan": {"ko": "방화구획·피난계획도", "discipline": "건축", "set": "인허가",
                         "keywords": ("방화구획", "피난계획", "피난동선", "피난", "egress",
                                      "life safety", "evacuation", "compartment")},
    "accessibility_plan": {"ko": "장애인편의시설(BF)", "discipline": "건축", "set": "인허가",
                           "keywords": ("장애인편의", "편의시설", "무장애", "barrier free",
                                        "accessibility", "bf인증")},
    "ceiling_plan": {"ko": "천장도(반자도)", "discipline": "건축", "set": "실시설계",
                     "keywords": ("천장도", "반자도", "천장평면", "reflected ceiling", "rcp")},
    "interior_elevation": {"ko": "실내전개도", "discipline": "건축", "set": "실시설계",
                           "keywords": ("전개도", "실내전개", "벽전개", "interior elevation",
                                        "room elevation")},
    "finish_schedule": {"ko": "마감표(실내재료마감)", "discipline": "건축", "set": "인허가",
                        "keywords": ("마감표", "마감도", "실내재료마감", "마감일람", "finish schedule",
                                     "material schedule")},
    "window_door_schedule": {"ko": "창호도·창호일람표", "discipline": "건축", "set": "실시설계",
                             "keywords": ("창호도", "창호일람", "창호상세", "개구부일람",
                                          "door schedule", "window schedule", "fenestration")},
    "wall_section": {"ko": "주단면·벽체상세단면", "discipline": "건축", "set": "실시설계",
                     "keywords": ("주단면", "벽체단면", "외벽단면", "구성단면", "wall section")},
    "unit_plan": {"ko": "단위세대 평면도", "discipline": "건축", "set": "실시설계",
                  "keywords": ("단위세대", "세대평면", "타입평면", "평형평면", "unit plan", "dwelling unit")},
    "enlarged_plan": {"ko": "확대·부분 평면도", "discipline": "건축", "set": "실시설계",
                      "keywords": ("확대평면", "부분평면", "enlarged plan", "partial plan")},
    "circulation_diagram": {"ko": "동선 다이어그램", "discipline": "건축", "set": "실시설계",
                            "keywords": ("동선도", "동선", "circulation", "flow diagram")},
    "zoning_diagram": {"ko": "조닝·컨셉 다이어그램", "discipline": "건축", "set": "상세",
                       "keywords": ("조닝", "컨셉다이어그램", "매스다이어그램", "zoning diagram",
                                    "massing", "concept diagram")},
    "perspective": {"ko": "투시도·조감도(렌더링)", "discipline": "건축", "set": "상세",
                    "keywords": ("투시도", "조감도", "조감", "perspective", "rendering", "bird eye",
                                 "render", "isometric", "axonometric")},
    "parking": {"ko": "주차계획도", "discipline": "건축", "set": "인허가",
                "keywords": ("주차", "parking")},
    # ── 상세도(details) ──
    "stair_detail": {"ko": "계단·경사로 상세", "discipline": "건축", "set": "상세",
                     "keywords": ("계단상세", "계단", "경사로", "램프", "stair detail", "ramp")},
    "waterproof_detail": {"ko": "방수 상세", "discipline": "건축", "set": "상세",
                          "keywords": ("방수상세", "방수", "waterproof")},
    "insulation_detail": {"ko": "단열 상세", "discipline": "건축", "set": "상세",
                          "keywords": ("단열상세", "단열", "insulation", "thermal")},
    # ── 일반 건축(generic — 복합 키워드 뒤에 둬 오분류 방지) ──
    "site_plan": {"ko": "배치도", "discipline": "건축", "set": "인허가",
                  "keywords": ("배치도", "배치", "site plan", "layout plan", "plot plan")},
    "elevation": {"ko": "입면도", "discipline": "건축", "set": "인허가",
                  "keywords": ("입면도", "입면", "측면도", "측면", "elevation", "facade")},
    "section": {"ko": "단면도", "discipline": "건축", "set": "인허가",
                "keywords": ("단면도", "단면", "section")},
    "floor_plan": {"ko": "평면도", "discipline": "건축", "set": "인허가",
                   "keywords": ("평면도", "평면", "floor plan", "plan")},
    "detail": {"ko": "상세도(일반)", "discipline": "건축", "set": "상세",
               "keywords": ("부분상세", "상세도", "상세", "detail")},
    # ── BIM/모델 ──
    "bim_clash": {"ko": "간섭(충돌)검토도", "discipline": "공통", "set": "상세",
                  "keywords": ("간섭검토", "충돌검토", "clash", "coordination")},
    "bim": {"ko": "BIM·3D 모델", "discipline": "공통", "set": "상세",
            "keywords": ("ifc", "bim", "3d 모델", "model view", "gltf")},
    "spec_sheet": {"ko": "설계 스펙시트", "discipline": "공통", "set": "공통", "keywords": ()},
}

# 도면 종류 코드 — 미상은 unknown(추정 금지). (META 단일 출처에서 파생)
DRAWING_TYPES = (*DRAWING_TYPE_META.keys(), "unknown")

# 파일명 키워드 → 도면 종류(탐지 우선순위 = META 삽입 순서). 키워드 없는 코드는 제외.
_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    code: tuple(meta["keywords"]) for code, meta in DRAWING_TYPE_META.items() if meta.get("keywords")
}


def detect_drawing_type(filename: str = "", hints: str = "") -> str:
    """파일명+내용 힌트로 도면 종류를 분류한다(분야별/복합 우선). 못 맞추면 'unknown'."""
    hay = f"{filename} {hints}".lower()
    for dtype, keywords in _TYPE_KEYWORDS.items():
        if any(kw.lower() in hay for kw in keywords):
            return dtype
    return "unknown"


def drawing_type_label(code: str) -> str:
    """도면 코드 → 한국어명(없으면 코드 그대로)."""
    meta = DRAWING_TYPE_META.get(code)
    return meta["ko"] if meta else code


def drawing_types_by_discipline() -> dict[str, list[dict]]:
    """분야별 도면 택소노미(프론트 드롭다운/표시용). {분야: [{code,ko,set}, ...]}."""
    out: dict[str, list[dict]] = {}
    for code, meta in DRAWING_TYPE_META.items():
        out.setdefault(meta["discipline"], []).append(
            {"code": code, "ko": meta["ko"], "set": meta["set"]}
        )
    return out


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
            # 분야(공통/건축/구조/전기/…) — 분야별 검색 필터용(택소노미 단일출처에서 파생).
            "discipline": DRAWING_TYPE_META.get(self.drawing_type, {}).get("discipline"),
            "title": self.title,
            "total_area_sqm": self.total_area_sqm,
            "floor_count": self.floor_count,
            "unit_count": self.unit_count,
            "parking_count": self.parking_count,
            "room_count": len(self.rooms),
            "summary": self.raw_summary[:2000],
        }
