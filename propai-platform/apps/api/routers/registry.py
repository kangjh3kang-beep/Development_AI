"""부동산 등기부(소유관계) 라우터 — 단건/다필지 일괄 조회·다운로드 + 토지조서."""

import asyncio
import io
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

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


def _issue_failed(result: Any) -> bool:
    """발급 결과가 실패/미설정(미발급)인지 판정 — 실패면 과금하지 않는다."""
    if not isinstance(result, dict):
        return False
    if result.get("error"):
        return True
    status = str(result.get("status", "")).lower()
    return status in ("unavailable", "error", "failed")


async def _charge_registry_issue(user_id: Any, result: Any, times: int = 1) -> None:
    """등기부등본 발급·열람 사용료(건당) 누적(best-effort). 발급 실패/미설정은 과금 제외."""
    if _issue_failed(result):
        return
    try:
        from app.core.database import async_session_factory
        from app.services.billing import billing_service

        async with async_session_factory() as _db:
            for _ in range(max(1, int(times))):
                await billing_service.charge_service(_db, user_id, "registry_issue")
    except Exception:  # noqa: BLE001
        pass


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


@router.post("/tilko/search", summary="틸코 등기물건 주소검색(주소→부동산 고유번호)")
async def tilko_search(
    req: dict[str, Any],
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """주소 → 부동산 고유번호 목록(RISUConfirmSimpleC). IROS 로그인·전자결제 불필요(Tilko API키만)."""
    from app.services.registry import tilko_client as tk
    return await tk.search_unique_no(str(req.get("address") or ""), page=str(req.get("page") or "1"))


@router.post("/tilko/realty", summary="틸코 등기부등본 조회/발급(IROS ID로그인)")
async def tilko_realty(
    req: dict[str, Any],
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """틸코로 등기부등본 조회/발급. unique_no(고유번호) 또는 address(자동 주소검색)로 부동산 지정.

    ⚠ 발급 수수료가 IROS 전자지급수단에서 차감됨(실호출).
    """
    from app.services.registry import tilko_client as tk

    # unique_no(부동산 고유번호 14자리) = Pin 필드. property_params.Pin/UniqueNo도 허용(하위호환).
    uno = str(req.get("unique_no") or req.get("pin")
              or (req.get("property_params") or {}).get("Pin")
              or (req.get("property_params") or {}).get("UniqueNo") or "").replace("-", "").strip()
    # 고유번호 미지정 + 주소 제공 시 → 주소검색으로 자동 해석(첫 결과 사용)
    if not uno and req.get("address"):
        s = await tk.search_unique_no(str(req["address"]))
        items = s.get("items") or []
        if items and items[0].get("unique_no"):
            uno = items[0]["unique_no"]
        else:
            return {"ok": False, "status": s.get("status", "need_unique_no"),
                    "message": s.get("message") or "주소로 부동산 고유번호를 찾지 못했습니다.",
                    "search": s}
    result = await tk.fetch_realty_registry(
        unique_no=uno,
        cmort_flag=str(req.get("cmort_flag", "N")),
        trade_seq_flag=str(req.get("trade_seq_flag", "N")),
        abs_cls=str(req.get("abs_cls", "11")),
        rgs_mttr_smry=str(req.get("rgs_mttr_smry", "")),
    )
    # 등기부등본 발급·열람 1건 1,200원(발급 성공 시, best-effort).
    await _charge_registry_issue(current_user.user_id, result, times=1)
    return result


@router.post("/bulk", summary="다필지 등기부 일괄 조회/다운로드")
async def registry_bulk(
    req: RegistryBulkRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> dict[str, Any]:
    """여러 필지의 등기부를 일괄 조회/발급한다(공급자 키 설정 시). 미설정 시 안내 반환."""
    items = list(req.items or [])
    if not items and req.addresses:
        items = [{"address": a} for a in req.addresses if a and a.strip()]
    result = await RegistryService().bulk(items)
    # 발급·열람 1건당 1,200원 × 필지수(발급 성공 시, best-effort).
    await _charge_registry_issue(current_user.user_id, result, times=max(1, len(items)))
    return result


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
    area_sqm: float | None = None  # 면적(집합건물 세대행은 대지지분 면적=실토지 기여분)
    exclusive_area_sqm: float | None = None  # 세대 전유면적(집합건물 세대행)
    unit_label: str = ""  # 동·호(집합건물 세대행)
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
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=14)
    ws["A1"].font = Font(size=14, bold=True)

    # 대지지분(평)·세대면적: 집합건물(공동주택·다세대·집합상가) 세대행에서 채워진다.
    PY = 3.305785  # 1평 = 3.305785㎡
    headers = ["번호", "지번/동·호", "소유자", "대지권비율/지분", "대지지분(㎡)", "대지지분(평)",
               "세대전유면적(㎡)", "소유구분",
               "매입예정가(원)", "매입가(원)", "계약확정", "토지사용동의", "지구단위동의"]
    ws.append(headers)
    hdr_fill = PatternFill("solid", fgColor="0E7490")
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=2, column=c)
        cell.fill = hdr_fill
        cell.font = Font(color="FFFFFF", bold=True)
        cell.alignment = Alignment(horizontal="center")

    tot_area = priv_area = pub_area = excl_area = 0.0
    sum_expected = sum_purchase = 0.0
    contracted_n = use_consent_n = dist_consent_n = 0
    for i, r in enumerate(req.rows, start=1):
        area = r.area_sqm or 0
        tot_area += area
        excl = r.exclusive_area_sqm or 0
        excl_area += excl
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
            i, r.jibun, r.owner, r.share,
            round(area, 2), round(area / PY, 3),  # 대지지분 ㎡ / 평
            round(excl, 2) if excl else "", r.owner_type,
            int(r.expected_price) if r.expected_price else "",
            int(r.purchase_price) if r.purchase_price else "",
            "○" if r.contracted else "", "○" if r.land_use_consent else "",
            "○" if r.district_consent else "",
        ])

    n = len(req.rows)
    pct = lambda a, b: f"{round(a / b * 100, 1)}%" if b else "-"  # noqa: E731
    ws.append([])
    summary = [
        ["총 필지/세대수", f"{n}건"],
        ["대지면적 합계(Σ대지지분=실토지면적)", f"{round(tot_area):,}㎡ ({round(tot_area / PY):,}평)"],
        ["  - 사유지", f"{round(priv_area):,}㎡"],
        ["  - 국공유지", f"{round(pub_area):,}㎡"],
        ["세대 전유면적 합계(집합건물)", f"{round(excl_area):,}㎡ ({round(excl_area / PY):,}평)" if excl_area else "-"],
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

    widths = [6, 28, 14, 14, 12, 11, 14, 10, 16, 16, 9, 12, 12]
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
    if not raw:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    # ★공용 콘텐츠 검증(WP-H 세션2 전역 스윕·fail-closed) — openpyxl 파싱 전에 압축폭탄(xlsx=zip
    # 계열)·실행/스크립트 위장·MIME 위장·경로순회를 차단한다. xlsx 전용이라 실측 계열을 zip 으로
    # 화이트리스트한다(xlsx 는 항상 PK/zip). 검증 실패는 http_status(4xx).
    from app.services.security.content_inspection import http_status_for, inspect_upload

    _verdict = inspect_upload(raw, file.filename or "", file.content_type, expected_kinds={"zip"})
    if not _verdict.allowed:
        raise HTTPException(
            status_code=http_status_for(_verdict.code),
            detail=f"업로드가 거부되었습니다: {_verdict.reason}",
        )
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
    # 모든 행을 보관(LLM 폴백용 그리드).
    all_rows: list[list[str]] = []
    for row in ws.iter_rows(values_only=True):
        cells = [("" if c is None else str(c)).strip() for c in row]
        all_rows.append(cells)
        # 헤더 탐지: 공백 제거 후 '지번' 매칭(예 '지 번'도 인식).
        if not headers:
            if any("지번" in c.replace(" ", "") for c in cells):
                headers = cells
            continue
        if not any(cells):  # 빈 행 → 데이터 끝(집계 푸터 앞에서 중단)
            break
        rd = {headers[i]: (cells[i] if i < len(cells) else "") for i in range(len(headers))}

        def pick(*keys: str, exclude: tuple[str, ...] = ()) -> str:
            for k, v in rd.items():
                if any(key in k for key in keys) and not any(e in k for e in exclude):
                    return v
            return ""

        jibun = pick("지번", "주소")
        # 집계 푸터 잔재(필지수·면적·비율·금액 등) 방어적 스킵.
        # '평'은 정상 지번(평창동·평택 등)을 오스킵하므로 제외 — ㎡/원/%로 면적·금액 푸터를 잡는다.
        if not jibun or any(t in jibun for t in ("필지", "㎡", "%", "원")):
            continue
        ot = pick("소유구분")
        owner_type = "국공유지" if ("국" in ot or "공" in ot) else ("사유지" if ot else "")
        # 면적: 신규 양식의 '대지지분(㎡)' 우선, 없으면 '면적'(단 '전유'·'평' 컬럼 제외).
        area_val = pick("대지지분", exclude=("평",)) or pick("면적", exclude=("전유", "평"))
        out.append({
            "jibun": jibun,
            "owner": pick("소유자"),
            "share": pick("지분", "대지권비율"),
            "area_sqm": _num(area_val),
            "exclusive_area_sqm": _num(pick("전유")),  # 세대 전유면적(집합건물 세대행)
            "owner_type": owner_type,
            "expected_price": _num(pick("매입예정")),
            "purchase_price": _num(pick("매입가")),
            "contracted": _bool(pick("계약")),
            "land_use_consent": _bool(pick("토지사용")),
            "district_consent": _bool(pick("지구단위")),
        })
    if out:
        return {"status": "ok", "count": len(out), "rows": out, "engine": "rule"}

    # ── LLM 폴백 ── 규칙기반이 0행(병합셀·다층헤더·집계 혼재 등 복잡 레이아웃)일 때
    # LLM이 시트 전체를 읽어 필지/소유자 행을 구조화 추출(원본 최대 복원, 무목업).
    llm_rows = await _llm_extract_land_schedule(all_rows)
    if llm_rows:
        return {"status": "ok", "count": len(llm_rows), "rows": llm_rows, "engine": "llm"}
    return {
        "status": "ok", "count": 0, "rows": [],
        "message": "지번을 인식하지 못했습니다. '지번/소재지'·소유자·면적이 포함된 토지조서인지 확인하세요.",
    }


async def _llm_extract_land_schedule(all_rows: list[list[str]]) -> list[dict[str, Any]]:
    """복잡 레이아웃 토지조서를 LLM으로 구조화 추출(병합셀 지번 상속·집계행 제외)."""
    # 그리드 텍스트화: 앞 90행, 셀 길이 제한, 빈 trailing 컬럼 제거.
    lines: list[str] = []
    for i, cells in enumerate(all_rows[:90]):
        trimmed = [c[:40] for c in cells]
        while trimmed and not trimmed[-1]:
            trimmed.pop()
        if trimmed:
            lines.append(f"R{i + 1}: " + " | ".join(trimmed))
    grid = "\n".join(lines)
    if not grid.strip():
        return []
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from app.services.ai.llm_provider import get_llm

        llm = get_llm(timeout=60, max_tokens=4000)
        sys = (
            "너는 한국 부동산 토지조서(편입토지조서) 엑셀을 정확히 구조화하는 전문가다. "
            "병합셀·다층헤더·집계행을 이해하고 각 소유자/필지 행을 추출한다. 근거 없는 값은 비운다."
        )
        human = (
            "다음은 토지조서 엑셀 셀 내용이다(R행번호: 열1 | 열2 ...). 각 데이터 행을 JSON 배열로만 "
            "출력하라(설명·코드펜스 금지).\n"
            "스키마: [{\"jibun\":\"소재지+지번 예 '사당동 219-16'\",\"owner\":\"소유자명\","
            "\"share\":\"지분 예 '1/2', 없으면 빈문자\",\"area_sqm\":편입면적㎡_숫자_또는_null,"
            "\"owner_type\":\"사유지|국공유지|빈문자\"}]\n"
            "규칙: ①병합셀로 지번이 빈 행은 바로 위 유효 지번을 상속 ②합계/소계/구성비/집계 행 제외 "
            "③헤더 행 제외 ④면적은 편입면적 우선(없으면 지적면적), 숫자만 ⑤JSON 배열만 출력.\n\n"
            f"[엑셀]\n{grid}"
        )
        resp = await llm.ainvoke(
            [SystemMessage(content=sys), HumanMessage(content=human)]
        )
        # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
        from app.services.ai.base_interpreter import record_llm_response_billing
        await record_llm_response_billing(llm, resp, service="registry")
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        import json
        import re

        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return []
        data = json.loads(m.group(0))
        rows: list[dict[str, Any]] = []
        for r in data:
            if not isinstance(r, dict):
                continue
            jb = str(r.get("jibun", "") or "").strip()
            if not jb:
                continue
            ot = str(r.get("owner_type", "") or "").strip()
            owner_type = (
                "국공유지" if ("국" in ot or "공" in ot)
                else ("사유지" if ot else "")
            )
            area = r.get("area_sqm")
            try:
                area = float(area) if area not in (None, "") else None
            except (TypeError, ValueError):
                area = None
            rows.append({
                "jibun": jb,
                "owner": str(r.get("owner", "") or "").strip(),
                "share": str(r.get("share", "") or "").strip(),
                "area_sqm": area,
                "owner_type": owner_type,
                "expected_price": None,
                "purchase_price": None,
                "contracted": False,
                "land_use_consent": False,
                "district_consent": False,
            })
        logger.info("토지조서 LLM 파싱 성공: %d행", len(rows))
        return rows
    except Exception as e:  # noqa: BLE001
        logger.warning("토지조서 LLM 파싱 실패: %s", str(e)[:160])
        return []
