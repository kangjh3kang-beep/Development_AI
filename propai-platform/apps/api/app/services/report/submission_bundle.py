"""제출 번들 컴파일러 — 도면(SVG/DXF)+보고서 PDF+BOQ xlsx를 단일 zip으로 묶고,
매니페스트(파일별 sha256·생성근거 run_id/input_hash)를 zip에 동봉한다.

무엇을 푸나(쉬운 설명):
- 심의·인허가에 제출하려면 '도면 + 보고서 + 공내역서'를 한 묶음(zip)으로 내되, 각 파일이 위·변조되지
  않았음을 증명할 지문(sha256)과 '어떤 입력으로 만들었는지'(run_id·input_hash)를 함께 담아야 한다.
- 이 모듈은 (1) 필수시트 100% 충족을 강제(미충족=산출 거부+누락 목록), (2) 결정적 zip 생성(SVG-only
  번들 한정 — 아래 ★결정성 참조), (3) 매니페스트 해시 전수 대조(밀반입 파일 탐지 포함)가 가능한
  검증 헬퍼를 제공한다.

★필수시트 게이트: sheet_frame.check_required_sheets 로 판정. 미충족이면 RequiredSheetsMissingError 을
  올린다(무음 부분산출 금지 — 라우터가 422+누락목록으로 정직 거부).
★결정성(가능 범위 — 주장 범위 정직 한정): zip 내부 타임스탬프는 고정값(FIXED_ZIP_DT)·엔트리 편철
  순서 고정·압축 무순서화 → 같은 입력이면 같은 zip 바이트(동일 zlib 환경)가 나오는 것은 **SVG-only
  번들(도면 SVG만 담긴 경우)에 한정**된다. PDF(reportlab, CreationDate/문서ID 필드) · xlsx(openpyxl,
  docProps/core.xml 의 created/modified 타임스탬프)는 렌더러가 생성 시각을 자체적으로 내부 메타데이터에
  박아 넣으므로, report_pdf/boq_xlsx 를 포함한 번들은 같은 입력이라도 매 호출 zip 바이트가 달라질 수
  있다(비결정적). 이 모듈은 그 비결정성을 숨기지 않는다 — sha256 은 항상 '실제 받은 bytes'를 그대로
  해시하므로(가짜 고정값 아님), 매니페스트는 매 산출물의 진짜 해시를 정직하게 기록한다. 재현성이
  필요하면 report_pdf/boq_xlsx 를 빼고 도면 SVG만으로 번들을 구성하라.
★무날조: run_id/input_hash 등 생성근거는 '인자로 받은 값'만 기록한다(가짜 생성 0). 부재 시 정직 표기.
  발행일(issue_date)도 명시 인자만 — 이 모듈은 now()/uuid/random 을 쓰지 않는다.

신규 의존성 0: io·zipfile·json·hashlib 는 표준 라이브러리.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass

from app.services.cad.sheet_frame import (
    build_sheet_manifest,
    check_required_sheets,
    required_sheet_codes,
    sheet_spec,
)

BUNDLE_VERSION = "propai.submission_bundle/1.0"
MANIFEST_NAME = "manifest.json"

# zip 내부 파일 타임스탬프 고정값(결정성). zip 포맷 최소 허용일(1980-01-01) — now() 금지.
FIXED_ZIP_DT = (1980, 1, 1, 0, 0, 0)

# 번들 편철(zip 엔트리) 하위 폴더 규약.
_DIR_DRAWING = "drawings"
_DIR_REPORT = "report"
_DIR_BOQ = "boq"


class RequiredSheetsMissingError(Exception):
    """필수시트 미충족 — 산출을 거부한다(무음 부분산출 금지).

    missing: [{code, number, name}, ...] (누락된 필수시트 — 라우터가 그대로 반환).
    """

    def __init__(self, missing: list[dict]) -> None:
        self.missing = missing
        nums = ", ".join(str(m.get("number") or m.get("code")) for m in missing)
        super().__init__(f"필수시트 누락 {len(missing)}건: {nums}")


@dataclass
class BundlePart:
    """번들에 담을 파일 1건(이미 산출된 bytes)."""

    arcname: str  # zip 내부 경로(예: 'drawings/A-001.svg')
    data: bytes
    kind: str  # drawing_svg / drawing_dxf / report / boq / 기타
    code: str | None = None  # 도면 코드(도면 파트만)
    sheet_number: str | None = None
    sheet_name: str | None = None


def _sha256_bytes(data: bytes) -> str:
    """바이트의 sha256 지문(16진수 64자) — 바이너리(xlsx/dxf/pdf) 포함 모든 파일 공통."""
    return hashlib.sha256(data or b"").hexdigest()


def _canonical_json_bytes(obj) -> bytes:
    """정규화 JSON(키 정렬·공백 제거·한글 원문) 바이트 — 매니페스트 결정성."""
    return json.dumps(
        obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")


def _present_codes(
    drawings_svg: dict[str, str] | None, drawings_dxf: dict[str, bytes] | None
) -> set[str]:
    """내용이 있는(빈 문자열/바이트 아님) 도면 코드 집합 — 필수시트 판정 입력."""
    present: set[str] = set()
    for code, svg in (drawings_svg or {}).items():
        if svg:
            present.add(str(code))
    for code, dxf in (drawings_dxf or {}).items():
        if dxf:
            present.add(str(code))
    return present


def _drawing_arcname(number: str, code: str, ext: str) -> str:
    """도면 zip 경로 — 시트번호 기준(예: drawings/A-001.svg). 번호 미상 시 코드 폴백."""
    stem = number or code
    return f"{_DIR_DRAWING}/{stem}.{ext}"


def build_submission_bundle(
    *,
    project_id: str,
    project_name: str,
    issue_date: str = "",
    drawings_svg: dict[str, str] | None = None,
    drawings_dxf: dict[str, bytes] | None = None,
    report_pdf: bytes | None = None,
    boq_xlsx: bytes | None = None,
    provenance: dict | None = None,
    extra_parts: list[BundlePart] | None = None,
) -> tuple[bytes, dict]:
    """제출 번들 zip 을 만든다. 반환=(zip bytes, manifest dict).

    필수시트(sheet_frame.required_sheet_codes) 미충족 시 RequiredSheetsMissingError 발생(산출 거부).

    인자:
    - drawings_svg: {code: svg_string}. 프레임(표제란)은 호출부가 이미 씌운 최종 SVG 를 넘긴다.
    - drawings_dxf: {code: dxf_bytes}. 옵셔널(없으면 SVG 만).
    - report_pdf / boq_xlsx: 옵셔널 bytes(없으면 매니페스트에 present=False 로 정직 표기).
    - issue_date / provenance: 명시 인자만(now()·uuid 생성 금지). provenance 예: {run_id, input_hash,
      geometry_hash, compiler_version}.

    ★결정성 주의: report_pdf/boq_xlsx 를 포함하면 zip 바이트가 호출마다 달라질 수 있다(reportlab/
    openpyxl 내부 타임스탬프 메타데이터 — 모듈 상단 ★결정성 문단 참조). SVG(+DXF)만으로 구성하면
    바이트 재현성이 보장된다. 어느 경우든 매니페스트 sha256 은 실제 산출물을 정직하게 반영한다.
    """
    drawings_svg = drawings_svg or {}
    drawings_dxf = drawings_dxf or {}

    # 1) 필수시트 게이트 — 미충족이면 즉시 거부(무음 부분산출 금지).
    present = _present_codes(drawings_svg, drawings_dxf)
    ok, missing = check_required_sheets(present)
    if not ok:
        raise RequiredSheetsMissingError(missing)

    # 2) 파트(파일) 조립 — 편철 순서 고정(결정성): 시트 레지스트리 순 → 보고서 → BOQ → extra.
    parts: list[BundlePart] = []
    sheet_manifest = build_sheet_manifest(drawings_svg)  # SVG 기준 시트 목록(번호·이름·존재)
    # sheet_manifest 는 레지스트리 편철 순서이므로 그 순서로 파트를 만든다.
    for row in sheet_manifest:
        code = row["code"]
        number = row["number"]
        name = row["name"]
        svg = drawings_svg.get(code)
        if svg:
            parts.append(
                BundlePart(
                    arcname=_drawing_arcname(number, code, "svg"),
                    data=svg.encode("utf-8"),
                    kind="drawing_svg",
                    code=code,
                    sheet_number=number,
                    sheet_name=name,
                )
            )
        dxf = drawings_dxf.get(code)
        if dxf:
            parts.append(
                BundlePart(
                    arcname=_drawing_arcname(number, code, "dxf"),
                    data=dxf,
                    kind="drawing_dxf",
                    code=code,
                    sheet_number=number,
                    sheet_name=name,
                )
            )
    # 레지스트리에 없는(미래) DXF 코드도 누락 없이 편철.
    _svg_codes = {r["code"] for r in sheet_manifest}
    for code, dxf in drawings_dxf.items():
        if code not in _svg_codes and dxf:
            spec = sheet_spec(code)
            number = spec.number if spec else code
            parts.append(
                BundlePart(
                    arcname=_drawing_arcname(number, code, "dxf"),
                    data=dxf,
                    kind="drawing_dxf",
                    code=code,
                    sheet_number=number,
                    sheet_name=spec.name if spec else "",
                )
            )

    if report_pdf:
        parts.append(
            BundlePart(arcname=f"{_DIR_REPORT}/report.pdf", data=report_pdf, kind="report")
        )
    if boq_xlsx:
        parts.append(
            BundlePart(arcname=f"{_DIR_BOQ}/boq.xlsx", data=boq_xlsx, kind="boq")
        )
    for ep in extra_parts or []:
        parts.append(ep)

    # 3) 파일 매니페스트(파일별 sha256) — 편철 순서 유지.
    files: list[dict] = [
        {
            "arcname": p.arcname,
            "kind": p.kind,
            "code": p.code,
            "sheet_number": p.sheet_number,
            "sheet_name": p.sheet_name,
            "bytes": len(p.data),
            "sha256": _sha256_bytes(p.data),
        }
        for p in parts
    ]

    # 4) 매니페스트 본문(자기해시 제외 상태로 먼저 조립 → bundle_hash 계산 → 부착).
    manifest_core = {
        "bundle_version": BUNDLE_VERSION,
        "project_id": str(project_id),
        "project_name": str(project_name or ""),
        "issue_date": str(issue_date or ""),  # 명시 인자만(now() 금지)
        "provenance": {
            "run_id": (provenance or {}).get("run_id"),
            "input_hash": (provenance or {}).get("input_hash"),
            "geometry_hash": (provenance or {}).get("geometry_hash"),
            "compiler_version": (provenance or {}).get("compiler_version"),
        },
        "required_sheets": list(required_sheet_codes()),
        "sheets": sheet_manifest,
        "files": files,
        "file_count": len(files),
    }
    bundle_hash = _sha256_bytes(_canonical_json_bytes(manifest_core))
    manifest = {**manifest_core, "bundle_hash": bundle_hash}

    # 5) zip 작성 — 매니페스트 먼저, 이어 파트(편철 순서). 모든 엔트리 타임스탬프 고정(결정성).
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _writestr(zf, MANIFEST_NAME, _canonical_json_bytes(manifest))
        for p in parts:
            _writestr(zf, p.arcname, p.data)
    return buf.getvalue(), manifest


def _writestr(zf: zipfile.ZipFile, name: str, data: bytes) -> None:
    """고정 타임스탬프 ZipInfo 로 엔트리를 쓴다(결정성 — date_time/외부속성 고정)."""
    info = zipfile.ZipInfo(filename=name, date_time=FIXED_ZIP_DT)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16  # 파일 권한 고정(생성 환경 차이에 둔감)
    zf.writestr(info, data)


def verify_bundle(zip_bytes: bytes) -> tuple[bool, list[str]]:
    """번들 무결성 전수 대조 — 매니페스트의 파일별 sha256·bundle_hash 를 zip 실제 내용과 재계산 대조.

    양방향 대조(★리뷰 반영 — 편방향만으로는 밀반입 탐지 불가):
    - 매니페스트 → zip: 선언된 각 파일이 실제로 있고 해시가 일치하는가.
    - zip → 매니페스트: zip 안에 매니페스트가 모르는 파일(밀반입)이 끼어있지 않은가.

    반환: (ok, problems). problems 는 불일치·누락·밀반입 항목의 사람 읽는 사유 목록.
    ★게이트 헬퍼: '매니페스트 해시 전수 대조'를 이 함수 하나로 수행(테스트·라우터 공용).
    """
    problems: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = set(zf.namelist())
            if MANIFEST_NAME not in names:
                return False, [f"매니페스트({MANIFEST_NAME}) 부재"]
            manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))

            # (a) bundle_hash 재계산 대조(매니페스트 자체 위·변조 탐지).
            declared = manifest.get("bundle_hash")
            core = {k: v for k, v in manifest.items() if k != "bundle_hash"}
            recomputed = _sha256_bytes(_canonical_json_bytes(core))
            if declared != recomputed:
                problems.append("bundle_hash 불일치(매니페스트 변조 의심)")

            # (b) 파일별 sha256 전수 대조(매니페스트 → zip 방향 — 선언된 파일이 실제로 있고 해시 일치).
            for entry in manifest.get("files", []):
                arc = entry.get("arcname")
                if arc not in names:
                    problems.append(f"파일 누락: {arc}")
                    continue
                actual = _sha256_bytes(zf.read(arc))
                if actual != entry.get("sha256"):
                    problems.append(f"해시 불일치: {arc}")

            # (c) 역방향 대조(zip → 매니페스트) — 매니페스트에 없는 파일이 zip에 밀반입됐는지 확인.
            #   (b)만으로는 '선언된 파일이 맞는지'만 보고, '선언 안 된 파일이 몰래 끼어들었는지'는
            #   놓친다(무음 통과 취약점). declared에 매니페스트 자신(MANIFEST_NAME)도 포함해야
            #   매니페스트 엔트리 자체가 오탐으로 잡히지 않는다.
            declared = {e.get("arcname") for e in manifest.get("files", [])} | {MANIFEST_NAME}
            smuggled = names - declared
            for name in sorted(smuggled):
                problems.append(f"미등록 파일(밀반입 의심): {name}")
            # 전건 대조 보강 단언 — 밀반입이 없다면 zip 엔트리 수는 '매니페스트 파일 수 + manifest.json'
            # 과 정확히 같아야 한다(개수가 맞아도 이름이 다르면 위 smuggled가 이미 잡으므로, 이 검사는
            # 이름 집합 비교의 이중 확인 성격 — 실패해도 problems가 이미 채워져 있어 중복 신호 없음).
            if not smuggled and len(names) != len(manifest.get("files", [])) + 1:
                problems.append(
                    f"엔트리 수 불일치: zip={len(names)} vs 매니페스트+1={len(manifest.get('files', [])) + 1}"
                )
    except Exception as exc:  # noqa: BLE001 — 손상 zip 도 정직하게 실패로(예외 삼키지 않음)
        return False, [f"번들 열기 실패: {exc}"]
    return (len(problems) == 0, problems)
