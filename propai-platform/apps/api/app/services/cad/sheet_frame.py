"""도면틀 표준(타이틀블록·시트번호·필수시트) — 기존 SVG/DXF 산출에 additive로 씌우는 순수 함수.

무엇을 푸나(쉬운 설명):
- 자동 생성된 도면들에는 '이게 어느 프로젝트의 몇 번 도면이고, 축척이 얼마이며, 언제 발행됐는지'를
  적는 표준 표제란(타이틀블록)이 없다. 심의·인허가에 제출하려면 도면마다 표준 틀이 있어야 한다.
- 이 모듈은 (1) 각 도면 코드 → 표준 시트번호(A-001 류)·시트명·필수여부 레지스트리,
  (2) 표제란을 기존 SVG/DXF에 '덧씌우는' 순수 함수(원본 무회귀 — 틀 없는 기존 경로는 그대로),
  (3) 필수시트 체크리스트를 제공한다.

★결정성/무날조: 발행일(issue_date)은 호출 시점 now()가 아니라 '명시 인자'로만 받는다(해시·IR에
  now() 금지). 표제란에 넣는 content_hash도 인자로 받은 값만 쓴다(가짜 해시 생성 0).
★무회귀: 프레임을 씌우는 함수는 입력을 변형해 '새 문자열/바이트'를 반환할 뿐, 기존 산출 경로
  (generate_full_drawing_set 등)는 이 함수를 부르지 않으면 완전히 동일하다.

신규 의존성 0: hashlib·re·io는 표준 라이브러리. ezdxf는 DXF 프레임에서만 지연 임포트(미설치 시 원본 유지).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# ══════════════════════════════════════════════════════════════════════════
# 1) 시트 레지스트리 — 도면 코드(generate_full_drawing_set 키) → 표준 시트 사양
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class SheetSpec:
    """표준 시트 1건의 사양(불변)."""

    code: str  # 내부 도면 코드(예: 'B-01' — generate_full_drawing_set 키)
    number: str  # 표준 시트번호(A-001 류 — 심의 도서 표준)
    name: str  # 시트명(한글)
    discipline: str  # 분야(건축·설비 등)
    required: bool  # 심의·인허가 필수시트 여부


# 순서 = 도서 편철 순서(매니페스트·번들 나열이 결정론이 되도록 고정).
_SHEET_REGISTRY: tuple[SheetSpec, ...] = (
    SheetSpec("B-01", "A-001", "배치도", "건축", True),
    SheetSpec("B-02-STD", "A-101", "기준층 평면도", "건축", True),
    SheetSpec("B-02-UNIT", "A-102", "단위세대 평면도", "건축", False),
    SheetSpec("B-02-UNIT-R", "A-103", "단위세대 평면도(상세)", "건축", False),
    SheetSpec("B-03", "A-201", "단면도", "건축", True),
    SheetSpec("B-04-F", "A-301", "정면도", "건축", True),
    SheetSpec("B-04-S", "A-302", "측면도", "건축", True),
    SheetSpec("B-05-RCP", "A-401", "반사천장도", "건축", False),
    SheetSpec("C-03", "A-501", "주차계획도", "건축", False),
    SheetSpec("B-06-MEP", "M-101", "설비계통도", "설비", False),
    SheetSpec("C-01", "A-901", "투시도", "건축", False),
    SheetSpec("C-02", "A-902", "일영분석도", "건축", False),
)

_REGISTRY_BY_CODE: dict[str, SheetSpec] = {s.code: s for s in _SHEET_REGISTRY}


def sheet_registry() -> tuple[SheetSpec, ...]:
    """표준 시트 레지스트리(편철 순서·불변)를 돌려준다."""
    return _SHEET_REGISTRY


def sheet_spec(code: str) -> SheetSpec | None:
    """도면 코드로 표준 시트 사양을 찾는다(미등록 코드는 None — 정직)."""
    return _REGISTRY_BY_CODE.get(str(code))


def required_sheet_codes() -> tuple[str, ...]:
    """심의·인허가 필수 도면 코드(내부 코드) 목록."""
    return tuple(s.code for s in _SHEET_REGISTRY if s.required)


def check_required_sheets(present_codes) -> tuple[bool, list[dict]]:
    """필수시트 100% 충족 여부 검사 — 미충족 시 (False, 누락목록).

    present_codes: 실제로 산출된(내용 있는) 도면 코드 집합/리스트.
    반환: (ok, missing) — missing 은 [{code, number, name}] (누락된 필수시트만, 편철 순서).

    ★무음 부분산출 금지: 호출부(번들 컴파일러)는 ok=False 면 산출을 거부하고 이 목록을 반환한다.
    """
    present = {str(c) for c in (present_codes or [])}
    missing: list[dict] = []
    for spec in _SHEET_REGISTRY:
        if spec.required and spec.code not in present:
            missing.append({"code": spec.code, "number": spec.number, "name": spec.name})
    return (len(missing) == 0, missing)


# ══════════════════════════════════════════════════════════════════════════
# 2) 타이틀블록(표제란) — 시트 1건의 표제 정보
# ══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class TitleBlock:
    """도면 표제란(타이틀블록) 값(불변) — SVG/DXF 프레임에 공용으로 쓴다."""

    project_name: str
    sheet_number: str
    sheet_name: str
    scale: str  # 예: '1:100'·'N.T.S.'(축척 미표기)
    issue_date: str  # 발행일(YYYY-MM-DD 등) — 명시 인자. 미상이면 ''(정직 공란·now() 금지)
    content_hash: str  # 도면 콘텐츠 sha256(짧게 표기·인자로 받은 값만)
    revision: str = "-"


def _sha256_text(s: str) -> str:
    """문자열의 sha256 지문(16진수 64자)."""
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


def build_title_block(
    code: str,
    *,
    project_name: str,
    scale: str = "N.T.S.",
    issue_date: str = "",
    content_hash: str | None = None,
    revision: str = "-",
) -> TitleBlock:
    """도면 코드 + 프로젝트 메타로 표제란을 조립한다(레지스트리 번호·이름 사용).

    - 미등록 코드는 number=code·name='' 로 정직 폴백(가짜 번호 생성 금지).
    - content_hash 는 명시 인자만 사용(None 이면 ''). 이 함수는 콘텐츠를 해시하지 않는다
      (해시 대상은 호출부가 결정 — 프레임 전 원본 SVG/DXF 등).
    """
    spec = sheet_spec(code)
    number = spec.number if spec else str(code)
    name = spec.name if spec else ""
    return TitleBlock(
        project_name=str(project_name or ""),
        sheet_number=number,
        sheet_name=name,
        scale=str(scale or "N.T.S."),
        issue_date=str(issue_date or ""),
        content_hash=str(content_hash or ""),
        revision=str(revision or "-"),
    )


# ══════════════════════════════════════════════════════════════════════════
# 3) SVG 프레임 — viewBox 하단에 표제란 밴드를 additive로 추가(원본 내용 무가림)
# ══════════════════════════════════════════════════════════════════════════

_VIEWBOX_RE = re.compile(
    r'viewBox="\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+'
    r'(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*"'
)
_WIDTH_RE = re.compile(r'\bwidth="(\d+(?:\.\d+)?)(?:px)?"')
_HEIGHT_RE = re.compile(r'\bheight="(\d+(?:\.\d+)?)(?:px)?"')


def _xml_escape(s: str) -> str:
    """SVG/XML 텍스트 주입 안전 — 특수문자 이스케이프(정직표기 값 그대로 표시)."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _titleblock_svg_group(tb: TitleBlock, minx: float, band_y: float, w: float, band_h: float) -> str:
    """표제란을 그리는 SVG <g> 조각(순수 문자열 — svgwrite 불요)."""
    cells: list[tuple[str, str]] = [
        ("프로젝트", tb.project_name or "-"),
        ("도면명", tb.sheet_name or "-"),
        ("도면번호", tb.sheet_number or "-"),
        ("축척", tb.scale or "-"),
        ("발행일", tb.issue_date or "-"),
        ("검증해시", (tb.content_hash or "")[:12] or "-"),
    ]
    n = len(cells)
    cell_w = w / n
    label_fs = max(6.0, band_h * 0.20)
    value_fs = max(7.0, band_h * 0.30)
    parts: list[str] = ['<g class="propai-titleblock" font-family="sans-serif">']
    # 밴드 배경(흰색)·외곽선
    parts.append(
        f'<rect x="{minx:.2f}" y="{band_y:.2f}" width="{w:.2f}" height="{band_h:.2f}" '
        f'fill="#ffffff" stroke="#2d3436" stroke-width="1"/>'
    )
    for i, (label, value) in enumerate(cells):
        cx = minx + i * cell_w
        # 셀 구분선(첫 셀 앞은 외곽선이 대신)
        if i > 0:
            parts.append(
                f'<line x1="{cx:.2f}" y1="{band_y:.2f}" x2="{cx:.2f}" '
                f'y2="{band_y + band_h:.2f}" stroke="#2d3436" stroke-width="0.5"/>'
            )
        tx = cx + cell_w * 0.06
        parts.append(
            f'<text x="{tx:.2f}" y="{band_y + band_h * 0.38:.2f}" '
            f'font-size="{label_fs:.1f}px" fill="#636e72">{_xml_escape(label)}</text>'
        )
        parts.append(
            f'<text x="{tx:.2f}" y="{band_y + band_h * 0.82:.2f}" '
            f'font-size="{value_fs:.1f}px" fill="#2d3436">{_xml_escape(value)}</text>'
        )
    parts.append("</g>")
    return "".join(parts)


def apply_title_block_svg(svg: str, tb: TitleBlock) -> str:
    """기존 SVG 하단에 표제란 밴드를 additive로 붙인 '새 SVG 문자열'을 반환(순수 함수).

    동작(무가림): viewBox(또는 width/height)를 읽어 캔버스 높이를 band_h 만큼 늘리고, 늘린
    하단 공간에 표제란을 그린다 → 기존 도면 내용을 가리지 않는다.

    무회귀 안전판:
    - svg 가 비었거나 '<svg' 가 없거나 치수를 못 읽으면 '원본 그대로' 반환(프레임 실패는 정직 스킵).
    - 원본 문자열은 변형하지 않는다(입력→새 문자열).
    """
    if not svg or "<svg" not in svg or "</svg>" not in svg:
        return svg

    m = _VIEWBOX_RE.search(svg)
    has_viewbox = m is not None
    if m:
        minx, miny, w, h = (float(m.group(i)) for i in range(1, 5))
    else:
        mw, mh = _WIDTH_RE.search(svg), _HEIGHT_RE.search(svg)
        if not (mw and mh):
            return svg  # 치수 불명 — 정직 스킵(무회귀)
        minx, miny, w, h = 0.0, 0.0, float(mw.group(1)), float(mh.group(1))

    if w <= 0 or h <= 0:
        return svg
    band_h = max(30.0, h * 0.10)
    band_y = miny + h
    new_h = h + band_h

    out = svg
    # 캔버스 높이 확장 — viewBox 우선, 이어 height 속성(있으면).
    if has_viewbox:
        out = _VIEWBOX_RE.sub(
            f'viewBox="{minx:.2f} {miny:.2f} {w:.2f} {new_h:.2f}"', out, count=1
        )
    hm = _HEIGHT_RE.search(out)
    if hm:
        out = out[: hm.start()] + f'height="{new_h:.2f}"' + out[hm.end():]

    group = _titleblock_svg_group(tb, minx, band_y, w, band_h)
    idx = out.rfind("</svg>")
    return out[:idx] + group + out[idx:]


# ══════════════════════════════════════════════════════════════════════════
# 4) DXF 프레임 — ezdxf 로 표제란 엔티티 추가(미설치·파싱실패 시 원본 유지)
# ══════════════════════════════════════════════════════════════════════════


def apply_title_block_dxf(dxf_bytes: bytes, tb: TitleBlock) -> bytes:
    """기존 DXF 하단(음의 Y 영역)에 표제란 텍스트·외곽선을 additive로 추가한 '새 DXF bytes' 반환.

    무회귀 안전판: ezdxf 미설치·바이트 파싱 실패·쓰기 실패 등 어떤 예외든 '원본 그대로' 반환한다
    (프레임은 부가물이지 필수가 아니므로 원본 도면을 절대 깨지 않는다).
    """
    if not dxf_bytes:
        return dxf_bytes
    try:
        import io  # noqa: PLC0415 — 사용 시점 임포트

        import ezdxf  # noqa: PLC0415

        doc = ezdxf.read(io.StringIO(dxf_bytes.decode("utf-8", errors="replace")))
        msp = doc.modelspace()

        # 표제란은 도면 아래(음의 Y)에 배치 — 기존 형상과 겹치지 않게(무가림).
        rows = [
            f"PROJECT: {tb.project_name}",
            f"SHEET  : {tb.sheet_number}  {tb.sheet_name}",
            f"SCALE  : {tb.scale}   DATE: {tb.issue_date or '-'}",
            f"HASH   : {(tb.content_hash or '')[:16] or '-'}   REV: {tb.revision}",
        ]
        y0 = -6.0
        line_h = 1.2
        box_h = line_h * (len(rows) + 0.5)
        box_w = 40.0
        # 외곽 상자
        msp.add_lwpolyline(
            [(0, y0), (box_w, y0), (box_w, y0 - box_h), (0, y0 - box_h), (0, y0)],
            close=True,
            dxfattribs={"layer": "TITLEBLOCK"},
        )
        for i, txt in enumerate(rows):
            msp.add_text(
                txt, dxfattribs={"layer": "TITLEBLOCK", "height": 0.6}
            ).set_placement((0.5, y0 - line_h * (i + 1)))

        buf = io.StringIO()
        doc.write(buf)
        return buf.getvalue().encode("utf-8")
    except Exception:  # noqa: BLE001 — 프레임 실패는 원본 유지(무회귀·정직)
        return dxf_bytes


# ══════════════════════════════════════════════════════════════════════════
# 5) 시트 매니페스트 — FullDrawingSet 산출에 additive로 부착할 시트 목록
# ══════════════════════════════════════════════════════════════════════════


def build_sheet_manifest(drawings: dict[str, str]) -> list[dict]:
    """도면 세트(code→SVG) → 시트 매니페스트 목록(번호·이름·포맷·sha256·필수·존재).

    - 레지스트리 순서를 먼저 나열(편철 순서·결정론), 그다음 미등록 코드를 정직하게 덧붙인다.
    - present = 코드가 있고 SVG 내용이 비어있지 않음. sha256 은 SVG utf-8 바이트(없으면 None).
    """
    drawings = drawings or {}
    manifest: list[dict] = []
    seen: set[str] = set()

    def _row(spec: SheetSpec | None, code: str, svg: str | None) -> dict:
        present = bool(svg)
        return {
            "code": code,
            "number": spec.number if spec else code,
            "name": spec.name if spec else "",
            "discipline": spec.discipline if spec else "",
            "required": bool(spec.required) if spec else False,
            "format": "svg",
            "present": present,
            "sha256": _sha256_text(svg) if present else None,
        }

    for spec in _SHEET_REGISTRY:
        seen.add(spec.code)
        manifest.append(_row(spec, spec.code, drawings.get(spec.code)))
    # 레지스트리에 없는(미래 추가) 코드도 누락 없이 정직 표기.
    for code, svg in drawings.items():
        if code not in seen:
            manifest.append(_row(None, code, svg))
    return manifest
