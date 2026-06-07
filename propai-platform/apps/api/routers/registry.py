"""부동산 등기부(소유관계) 라우터 — 단건/다필지 일괄 조회·다운로드 + 토지조서."""

import asyncio
import io
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.services.registry.registry_service import RegistryService
from apps.api.auth.jwt_handler import CurrentUser, get_current_user

router = APIRouter(prefix="/registry", tags=["부동산 등기부"])

# ── 비동기 등기분석 작업 저장소(모바일 안정: 긴 동기요청 대신 제출+폴링) ──
_JOBS: dict[str, dict[str, Any]] = {}
_JOB_TTL = 3600.0


def _prune_jobs() -> None:
    now = time.time()
    for k in [k for k, v in _JOBS.items() if now - v.get("ts", 0) > _JOB_TTL]:
        _JOBS.pop(k, None)


async def _run_registry_job(job_id: str, params: dict[str, Any]) -> None:
    try:
        from app.services.registry.registry_analysis_service import RegistryAnalysisService

        res = await RegistryAnalysisService().analyze(**params)
        _JOBS[job_id] = {"status": "done", "result": res, "ts": time.time()}
    except Exception as e:  # noqa: BLE001
        _JOBS[job_id] = {"status": "error", "error": str(e)[:200], "ts": time.time()}


class RegistryBulkRequest(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list, description="[{pnu?, address?}]")
    addresses: list[str] | None = None  # 단축 입력


@router.get("/status", summary="등기부 API 연동 상태")
async def registry_status() -> dict[str, Any]:
    return RegistryService().status()


@router.get("/tilko/status", summary="틸코(Tilko) 등기 연동 상태 점검")
async def tilko_status() -> dict[str, Any]:
    """TILKO_API_KEY·IROS 자격 설정 여부 + 공개키 도달성 점검(키 입력 후 검증용)."""
    from app.services.registry import tilko_client as tk

    out = {"key_set": tk.tilko_ready(), "iros_set": tk.iros_ready(), "public_key_ok": False}
    if tk.tilko_ready():
        pub = await tk.get_public_key()
        out["public_key_ok"] = bool(pub)
        out["message"] = (
            "틸코 API키 정상(공개키 수신). IROS 자격까지 설정되면 등기 조회 가능."
            if pub else "공개키 조회 실패 — TILKO_API_KEY 확인 필요."
        )
    else:
        out["message"] = "TILKO_API_KEY 미설정(관리자 키화면 입력 필요)."
    return out


@router.post("/tilko/realty", summary="틸코 등기부등본 조회/발급(IROS ID로그인)")
async def tilko_realty(
    req: dict[str, Any],
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """틸코로 등기부등본 조회/발급. req.property_params에 부동산 식별 필드(소재지/고유번호 등) 주입.

    ⚠ 발급 수수료가 IROS 전자지급수단에서 차감됨(실호출). 명세 확정된 property_params 필요.
    """
    from app.services.registry import tilko_client as tk

    return await tk.fetch_realty_registry(
        property_params=req.get("property_params") or {},
        cmort_flag=str(req.get("cmort_flag", "0")),
        trade_seq_flag=str(req.get("trade_seq_flag", "0")),
        abs_cls=str(req.get("abs_cls", "0")),
        rgs_mttr_smry=str(req.get("rgs_mttr_smry", "0")),
    )


@router.post("/bulk", summary="다필지 등기부 일괄 조회/다운로드")
async def registry_bulk(
    req: RegistryBulkRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """여러 필지의 등기부를 일괄 조회/발급한다(공급자 키 설정 시). 미설정 시 안내 반환."""
    items = list(req.items or [])
    if not items and req.addresses:
        items = [{"address": a} for a in req.addresses if a and a.strip()]
    return await RegistryService().bulk(items)


class RegistryAnalyzeRequest(BaseModel):
    address: str | None = None
    pnu: str | None = None
    registry_text: str | None = None  # 등기부등본 내용 직접 입력(연동 미설정 시)
    realty_type: str | None = None    # 0토지+건물 1집합건물 2토지 3건물(기본=env)
    dong: str | None = None           # 집합건물 동
    ho: str | None = None             # 집합건물 호
    # 부지분석에서 이미 확보한 토지정보(전달 시 백엔드 재조회 생략 → 지연 단축)
    land_hint: dict[str, Any] | None = None


@router.post("/analyze", summary="부동산 등기정보 권리분석(법무사·변호사 AI)")
async def registry_analyze(
    req: RegistryAnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """등기부(연동 조회 또는 직접 입력)를 법무사·변호사 관점에서 분석해 소유정보·소유기간·
    매입금액·보유지분·가등기·압류·근저당·매도청구 가능여부 등 권리관계를 제공한다.
    집합건물은 realty_type=1 + dong/ho로 특정 호 등기를 조회한다."""
    from app.services.registry.registry_analysis_service import RegistryAnalysisService

    result = await RegistryAnalysisService().analyze(
        address=req.address, pnu=req.pnu, registry_text=req.registry_text,
        realty_type=req.realty_type, dong=req.dong, ho=req.ho,
        land_hint=req.land_hint,
    )
    # 서비스 사용료: 등기부등본 권리분석 1건 1,200원(LLM 과금 별개, best-effort).
    try:
        from app.core.database import async_session_factory
        from app.services.billing import billing_service

        async with async_session_factory() as _db:
            charge = await billing_service.charge_service(
                _db, current_user.user_id, "registry_analysis"
            )
        if isinstance(result, dict):
            result["service_charge"] = charge
    except Exception:  # noqa: BLE001
        pass
    return result


@router.post("/analyze/jobs", summary="등기 권리분석 비동기 작업 제출(모바일 안정)")
async def registry_analyze_submit(
    req: RegistryAnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """긴 동기요청(CODEF ~50s) 대신 작업을 제출하고 즉시 job_id 반환.
    캐시 적중 시 즉시 결과 반환(작업 생략). 진행은 GET /analyze/jobs/{id}로 폴링."""
    from app.services.registry.registry_analysis_service import peek_analyze_cache

    cached = await peek_analyze_cache(
        address=req.address, pnu=req.pnu, realty_type=req.realty_type,
        dong=req.dong, ho=req.ho, registry_text=req.registry_text,
    )
    if cached is not None:
        # 캐시 적중 = 신규 분석 없음 → 과금 안 함(동일 입력 재조회 무료).
        return {"job_id": None, "status": "done", "result": cached}

    # 캐시 미적중 → 신규 권리분석 수행 예정 → 1,200원 과금(best-effort, LLM 별개).
    try:
        from app.core.database import async_session_factory
        from app.services.billing import billing_service

        async with async_session_factory() as _db:
            await billing_service.charge_service(
                _db, current_user.user_id, "registry_analysis"
            )
    except Exception:  # noqa: BLE001
        pass

    _prune_jobs()
    job_id = uuid.uuid4().hex
    _JOBS[job_id] = {"status": "pending", "ts": time.time()}
    params = dict(
        address=req.address, pnu=req.pnu, registry_text=req.registry_text,
        realty_type=req.realty_type, dong=req.dong, ho=req.ho, land_hint=req.land_hint,
    )
    asyncio.create_task(_run_registry_job(job_id, params))
    return {"job_id": job_id, "status": "pending"}


@router.get("/analyze/jobs/{job_id}", summary="등기 권리분석 작업 상태/결과 조회")
async def registry_analyze_status(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """작업 상태(pending/done/error)와 완료 시 결과를 반환."""
    j = _JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "작업을 찾을 수 없습니다(만료되었거나 잘못된 ID).")
    return {"status": j["status"], "result": j.get("result"), "error": j.get("error")}


@router.post("/cleanup", summary="등기부 PDF TTL 자동삭제(경과분 정리)")
async def registry_cleanup(days: int = 30) -> dict[str, Any]:
    """비공개 버킷의 등기부 PDF 중 days 경과분을 삭제한다(워커 cron/수동 호출용)."""
    from apps.api.services.storage_service import cleanup_registry_pdfs

    try:
        deleted = await cleanup_registry_pdfs(days=days)
        return {"status": "ok", "deleted": deleted, "days": days}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": str(e)[:200]}


# ── 토지조서 엑셀 ──

class LandRow(BaseModel):
    jibun: str = ""
    owner: str = ""
    share: str = ""
    area_sqm: float | None = None
    owner_type: str = ""
    expected_price: float | None = None
    purchase_price: float | None = None
    contracted: bool = False
    land_use_consent: bool = False
    district_consent: bool = False
    note: str = ""


class LandScheduleExcelRequest(BaseModel):
    project_name: str = "토지조서"
    rows: list[LandRow] = Field(default_factory=list)


@router.post("/land-schedule/excel", summary="토지조서 엑셀 다운로드")
async def land_schedule_excel(req: LandScheduleExcelRequest):
    """토지조서(편입토지 명세 + 집계)를 엑셀(.xlsx)로 생성한다."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "토지조서"

    title = f"토지조서 — {req.project_name}"
    ws.append([title])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=11)
    ws["A1"].font = Font(size=14, bold=True)

    headers = ["번호", "지번", "소유자", "소유지분", "면적(㎡)", "소유구분",
               "매입예정가(원)", "매입가(원)", "계약확정", "토지사용동의", "지구단위동의"]
    ws.append(headers)
    hdr_fill = PatternFill("solid", fgColor="0E7490")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=2, column=c)
        cell.fill = hdr_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center")

    tot_area = priv_area = pub_area = 0.0
    sum_expected = sum_purchase = 0.0
    contracted_n = use_consent_n = dist_consent_n = 0
    for i, r in enumerate(req.rows, start=1):
        area = r.area_sqm or 0
        tot_area += area
        if r.owner_type == "국공유지":
            pub_area += area
        elif r.owner_type == "사유지":
            priv_area += area
        sum_expected += r.expected_price or 0
        sum_purchase += r.purchase_price or 0
        contracted_n += 1 if r.contracted else 0
        use_consent_n += 1 if r.land_use_consent else 0
        dist_consent_n += 1 if r.district_consent else 0
        ws.append([
            i, r.jibun, r.owner, r.share, round(area, 1), r.owner_type,
            int(r.expected_price) if r.expected_price else "",
            int(r.purchase_price) if r.purchase_price else "",
            "○" if r.contracted else "", "○" if r.land_use_consent else "",
            "○" if r.district_consent else "",
        ])

    n = len(req.rows)
    pct = lambda a, b: f"{round(a / b * 100, 1)}%" if b else "-"  # noqa: E731
    ws.append([])
    summary = [
        ["총 필지수", f"{n}필지"],
        ["부지면적 합계", f"{round(tot_area):,}㎡ ({round(tot_area / 3.305785):,}평)"],
        ["  - 사유지", f"{round(priv_area):,}㎡"],
        ["  - 국공유지", f"{round(pub_area):,}㎡"],
        ["확보비율(계약확정)", f"{pct(contracted_n, n)} ({contracted_n}/{n})"],
        ["토지사용 동의율", f"{pct(use_consent_n, n)} ({use_consent_n}/{n})"],
        ["지구단위 동의율", f"{pct(dist_consent_n, n)} ({dist_consent_n}/{n})"],
        ["매입예정가 합계", f"{int(sum_expected):,}원"],
        ["매입가 합계(확정)", f"{int(sum_purchase):,}원"],
        ["미확보 잔여 보상비(예정-매입)", f"{int(sum_expected - sum_purchase):,}원"],
    ]
    for label, val in summary:
        ws.append([label, val])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)

    widths = [6, 26, 14, 10, 11, 10, 16, 16, 9, 12, 12]
    for idx, w in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + idx)].width = w

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="land_schedule.xlsx"'},
    )


@router.post("/land-schedule/import", summary="토지조서 엑셀 업로드(대량 지번 일괄 입력)")
async def land_schedule_import(file: UploadFile = File(...)) -> dict[str, Any]:
    """토지조서 엑셀(.xlsx)을 업로드해 행으로 파싱한다. 헤더에 '지번' 포함 행을 기준으로
    소유자/지분/면적/소유구분/매입예정가/매입가/계약/동의 컬럼을 유연 매핑한다."""
    from openpyxl import load_workbook

    raw = await file.read()
    try:
        wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": f"엑셀 읽기 실패: {str(e)[:120]}", "rows": []}
    ws = wb.active

    def _num(v: Any) -> float | None:
        if v is None:
            return None
        try:
            return float(str(v).replace(",", "").replace("원", "").strip())
        except (TypeError, ValueError):
            return None

    def _bool(v: Any) -> bool:
        s = str(v or "").strip().lower()
        return s in ("○", "o", "y", "yes", "true", "1", "예", "완료", "v")

    headers: list[str] = []
    out: list[dict[str, Any]] = []
    for row in ws.iter_rows(values_only=True):
        cells = [("" if c is None else str(c)).strip() for c in row]
        if not headers:
            if any("지번" in c for c in cells):
                headers = cells
            continue
        if not any(cells):  # 빈 행 → 데이터 끝(집계 푸터 앞에서 중단)
            break
        rd = {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}

        def pick(*keys: str) -> str:
            for k, v in rd.items():
                if any(key in k for key in keys):
                    return v
            return ""

        jibun = pick("지번", "주소")
        # 집계 푸터 잔재(필지수·면적·비율·금액 등) 방어적 스킵
        if not jibun or any(t in jibun for t in ("필지", "㎡", "%", "원", "평")):
            continue
        ot = pick("소유구분")
        owner_type = "국공유지" if ("국" in ot or "공" in ot) else ("사유지" if ot else "")
        out.append({
            "jibun": jibun,
            "owner": pick("소유자"),
            "share": pick("지분"),
            "area_sqm": _num(pick("면적")),
            "owner_type": owner_type,
            "expected_price": _num(pick("매입예정")),
            "purchase_price": _num(pick("매입가")),
            "contracted": _bool(pick("계약")),
            "land_use_consent": _bool(pick("토지사용")),
            "district_consent": _bool(pick("지구단위")),
        })
    return {"status": "ok", "count": len(out), "rows": out}
