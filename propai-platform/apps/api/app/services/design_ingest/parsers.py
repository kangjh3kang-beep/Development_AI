"""설계파일 파서 — 업로드 바이트를 DesignSpec으로 정규화.

지원: 엑셀(openpyxl), DXF(ezdxf). IFC는 기존 BIMIFCService 재사용(아래 참조),
PDF/이미지는 비전 LLM 경로(후속)로 위임한다. 추출 못 한 값은 None(추정 금지·정직).
파서는 예외를 던지지 않고 부분 추출 + meta.warnings로 정직 고지한다.
"""

from __future__ import annotations

import io
import re

from app.services.design_ingest.design_spec import (
    DesignSpec,
    RoomSpec,
    detect_drawing_type,
)

# 형식 판별 — 확장자 기준.
_EXT_FORMAT = {
    ".xlsx": "excel", ".xlsm": "excel", ".xls": "excel",
    ".dxf": "dxf",
    ".ifc": "ifc",
    ".pdf": "pdf",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".webp": "image",
}

# 엑셀 셀 텍스트에서 정량값을 뽑는 정규식(라벨:값) — 한국어 설계 스펙 관습.
# 영문 단독어(area/floors 등)는 비면적 문맥 숫자를 오탐하므로 제외(한국어 특정 라벨 위주),
# 라벨↔값 간격은 4자 이내로 좁혀 무관 숫자 매칭을 줄인다.
_NUM = r"([0-9][0-9,\.]*)"
_AREA_RE = re.compile(rf"(연면적|대지면적|건축면적|총면적|면적)\D{{0,4}}{_NUM}", re.I)
_FLOOR_RE = re.compile(rf"(지상\s?층수|층수)\D{{0,4}}{_NUM}", re.I)
_UNIT_RE = re.compile(rf"(세대수|세대|가구수|가구)\D{{0,4}}{_NUM}", re.I)
_PARK_RE = re.compile(rf"(주차대수|주차\s?대수|주차(?!장))\D{{0,4}}{_NUM}", re.I)


def detect_format(filename: str) -> str:
    """파일명 확장자로 형식을 판별한다. 미지원은 'unknown'."""
    name = (filename or "").lower()
    for ext, fmt in _EXT_FORMAT.items():
        if name.endswith(ext):
            return fmt
    return "unknown"


def _to_float(s: str) -> float | None:
    """문자열→float. 콤마는 천단위 형태(1,234,567(.8))일 때만 제거(자릿수 조작 방지)."""
    s = (s or "").strip()
    if "," in s:
        if not re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):
            return None  # 비정상 콤마(1,,2 등)는 거부 — 거짓값 합성 금지
        s = s.replace(",", "")
    try:
        return float(s)
    except (ValueError, AttributeError):
        return None


def parse_excel(content: bytes, filename: str = "") -> DesignSpec:
    """엑셀 → DesignSpec. 셀 전수 텍스트에서 면적/층수/세대/주차를 휴리스틱 추출."""
    import openpyxl

    spec = DesignSpec(source_format="excel", drawing_type="spec_sheet")
    try:
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        spec.meta["warnings"] = [f"엑셀 로드 실패: {str(e)[:120]}"]
        return spec

    texts: list[str] = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if cell is not None:
                    texts.append(str(cell))
    wb.close()

    blob = " ".join(texts)
    spec.raw_summary = blob[:4000]
    spec.title = (filename or "").rsplit("/", 1)[-1] or None

    if (m := _AREA_RE.search(blob)):
        spec.total_area_sqm = _to_float(m.group(2))
    if (m := _FLOOR_RE.search(blob)):
        v = _to_float(m.group(2))
        spec.floor_count = int(v) if v is not None else None
    if (m := _UNIT_RE.search(blob)):
        v = _to_float(m.group(2))
        spec.unit_count = int(v) if v is not None else None
    if (m := _PARK_RE.search(blob)):
        v = _to_float(m.group(2))
        spec.parking_count = int(v) if v is not None else None

    # 도면종류 힌트(파일명 우선, 없으면 spec_sheet 유지)
    dt = detect_drawing_type(filename, blob[:500])
    if dt != "unknown":
        spec.drawing_type = dt
    return spec


def parse_dxf(content: bytes, filename: str = "") -> DesignSpec:
    """DXF → DesignSpec. 레이어·텍스트(룸라벨)·바운딩박스를 추출."""
    import ezdxf

    spec = DesignSpec(source_format="dxf")
    spec.title = (filename or "").rsplit("/", 1)[-1] or None
    try:
        # ezdxf는 파일경로/스트림 모두 지원 — 텍스트모드 스트림으로 읽는다.
        doc = ezdxf.read(io.StringIO(content.decode("utf-8", errors="ignore")))
    except Exception as e:  # noqa: BLE001
        spec.meta["warnings"] = [f"DXF 파싱 실패: {str(e)[:120]}"]
        return spec

    msp = doc.modelspace()
    spec.layers = sorted({lyr.dxf.name for lyr in doc.layers})[:50]

    labels: list[str] = []
    for e in msp:
        dxftype = e.dxftype()
        if dxftype in ("TEXT", "MTEXT"):
            # TEXT는 dxf.text, MTEXT는 .text 속성 — getattr로 타입 안전하게 접근.
            txt = (getattr(e.dxf, "text", "") if dxftype == "TEXT" else getattr(e, "text", "")) or ""
            txt = txt.strip()
            if txt:
                labels.append(txt[:60])

    spec.rooms = [RoomSpec(name=t) for t in labels[:50]]

    # 바운딩박스 — LINE/LWPOLYLINE 등 전 엔티티 기준(insert만 보면 선기반 도면이 0×0 거짓값).
    # 좌표 산출 불가 시 dimensions는 비워 둔다(추정 금지·0 거짓값 금지).
    try:
        from ezdxf import bbox

        ext = bbox.extents(msp, fast=True)
        if ext.has_data and (ext.size.x or ext.size.y):
            spec.dimensions = {"bbox_w": round(ext.size.x, 2), "bbox_h": round(ext.size.y, 2)}
    except Exception:  # noqa: BLE001
        pass

    spec.raw_summary = (
        f"레이어: {', '.join(spec.layers[:20])}. 라벨: {', '.join(labels[:30])}"
    )[:4000]
    spec.drawing_type = detect_drawing_type(filename, " ".join(spec.layers + labels)[:500])
    return spec


def _ifc_quantity_area(entity: object) -> float:
    """엔티티에 부착된 IfcElementQuantity의 IfcQuantityArea 합(㎡). 없으면 0."""
    total = 0.0
    for d in (getattr(entity, "IsDefinedBy", None) or []):
        if d.is_a("IfcRelDefinesByProperties"):
            pset = d.RelatingPropertyDefinition
            if pset.is_a("IfcElementQuantity"):
                for q in pset.Quantities:
                    if q.is_a("IfcQuantityArea"):
                        total += q.AreaValue or 0.0
    return total


def parse_ifc(content: bytes, filename: str = "") -> DesignSpec:
    """IFC(BIM) → DesignSpec. 층수(IfcBuildingStorey)·공간(IfcSpace)·면적(IfcElementQuantity)·
    요소종류를 추출한다(검색/조합용). 상세 물량·원가 QTO는 BIMIFCService가 담당(중복 산정 안 함).

    ifcopenshell은 파일경로 입력이라 임시파일로 기록 후 파싱한다(BIMIFCService와 동일 전제).
    파싱 실패/미가용은 예외 없이 부분 추출 + warnings로 정직 고지(추정 금지·가짜값 금지).
    """
    import contextlib
    import os
    import tempfile

    spec = DesignSpec(source_format="ifc", drawing_type="bim")
    spec.title = (filename or "").rsplit("/", 1)[-1] or None

    tmp: str | None = None
    try:
        import ifcopenshell

        with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tf:
            tf.write(content)
            tmp = tf.name
        ifc = ifcopenshell.open(tmp)  # 모델을 메모리에 로드(이후 파일 삭제 무방)

        storeys = ifc.by_type("IfcBuildingStorey")
        spaces = ifc.by_type("IfcSpace")
        spec.floor_count = len(storeys) or None  # 0이면 None(가짜값 금지)

        # 면적: ★IfcSpace의 바닥면적 합(연면적 의미 — 엑셀 total_area_sqm과 동일 축).
        #   벽·슬래브 표면적(IfcBuildingElement)은 '바닥면적'이 아니므로 합산하지 않는다(의미 혼동 방지).
        #   상세 물량(벽/슬래브 면적·체적·원가)은 BIMIFCService가 담당.
        floor_area = 0.0
        rooms: list[RoomSpec] = []
        for s in spaces[:50]:
            nm = (getattr(s, "Name", None) or "").strip()[:60]
            a = round(_ifc_quantity_area(s), 2) or None
            if nm or a:
                rooms.append(RoomSpec(name=nm or "(이름없음)", area_sqm=a))
            if a:
                floor_area += a
        spec.rooms = rooms  # IfcSpace는 세대가 아닐 수 있어 rooms로만(unit_count 추정 안 함)
        if floor_area > 0:
            spec.total_area_sqm = round(floor_area, 2)
            spec.meta["ifc_area_basis"] = "space_floor_area"  # 근거: 공간 바닥면적 합(표면적 아님)

        types = sorted({el.is_a() for el in ifc.by_type("IfcBuildingElement")})[:50]
        spec.layers = types
        spec.raw_summary = (
            f"IFC {ifc.schema} · 층 {len(storeys)} · 공간 {len(spaces)} · "
            f"요소종류 {', '.join(types[:20])}"
        )[:4000]
        dt = detect_drawing_type(filename)
        spec.drawing_type = dt if dt != "unknown" else "bim"
    except Exception as e:  # noqa: BLE001 — 파싱 실패/미가용은 정직 스텁(예외 비전파)
        spec.meta["warnings"] = [f"IFC 파싱 실패: {str(e)[:120]}"]
    finally:
        if tmp:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
    return spec


def parse_design_file(content: bytes, filename: str) -> DesignSpec:
    """형식 판별 후 적절한 파서로 위임. PDF/이미지는 비전(비동기) 경로 안내."""
    fmt = detect_format(filename)
    if fmt == "excel":
        return parse_excel(content, filename)
    if fmt == "dxf":
        return parse_dxf(content, filename)
    if fmt == "ifc":
        return parse_ifc(content, filename)
    if fmt in ("pdf", "image"):
        # PDF/이미지는 멀티모달 비전 경로 필요 → 비동기 parse_design_file_async를 쓰라는 정직 고지.
        # (동기 경로에서는 LLM 호출 불가 — 메타만 채운 스텁 반환.)
        spec = DesignSpec(source_format=fmt)
        spec.title = (filename or "").rsplit("/", 1)[-1] or None
        spec.drawing_type = detect_drawing_type(filename)
        spec.meta["warnings"] = ["PDF/이미지는 비전 LLM 경로(parse_design_file_async) 필요 — 동기경로는 메타만"]
        return spec
    spec = DesignSpec(source_format="unknown")
    spec.meta["warnings"] = [f"지원하지 않는 형식: {filename}"]
    return spec


async def parse_design_file_async(content: bytes, filename: str) -> DesignSpec:
    """비동기 진입점 — 이미지/PDF는 비전 LLM, 그 외는 동기 파서로 위임.

    인제스천(ingest_service)은 이 경로를 사용해야 스캔/렌더 도면(이미지·PDF)을
    멀티모달로 구조화할 수 있다. 비전 실패는 정직 스텁으로 강등(예외 없음).
    """
    fmt = detect_format(filename)
    if fmt in ("pdf", "image"):
        from app.services.design_ingest.vision_parser import parse_drawing_with_vision

        return await parse_drawing_with_vision(content, filename, fmt)
    if fmt == "ifc":
        # ifcopenshell 파싱은 CPU 바운드(대형 IFC) → 스레드로 오프로드(이벤트루프 비차단).
        import asyncio

        return await asyncio.to_thread(parse_design_file, content, filename)
    return parse_design_file(content, filename)
