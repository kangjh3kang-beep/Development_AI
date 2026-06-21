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


def parse_design_file(content: bytes, filename: str) -> DesignSpec:
    """형식 판별 후 적절한 파서로 위임. IFC/PDF/이미지는 정직 고지(후속 경로)."""
    fmt = detect_format(filename)
    if fmt == "excel":
        return parse_excel(content, filename)
    if fmt == "dxf":
        return parse_dxf(content, filename)
    if fmt == "ifc":
        # IFC는 기존 BIMIFCService(apps/api/services/bim_ifc_service.py, IfcOpenShell)가 QTO를 담당.
        spec = DesignSpec(source_format="ifc", drawing_type="bim")
        spec.title = (filename or "").rsplit("/", 1)[-1] or None
        spec.meta["warnings"] = ["IFC는 BIMIFCService로 처리 — 인제스천 연동 후속(Phase1)"]
        return spec
    if fmt in ("pdf", "image"):
        spec = DesignSpec(source_format=fmt)
        spec.title = (filename or "").rsplit("/", 1)[-1] or None
        spec.drawing_type = detect_drawing_type(filename)
        spec.meta["warnings"] = ["PDF/이미지는 비전 LLM 파싱 경로(후속) — 현재 메타만 추출"]
        return spec
    spec = DesignSpec(source_format="unknown")
    spec.meta["warnings"] = [f"지원하지 않는 형식: {filename}"]
    return spec
