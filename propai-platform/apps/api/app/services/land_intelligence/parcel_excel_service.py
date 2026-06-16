"""다필지 토지조서 엑셀 — 플랫폼 최적 양식 생성 + 업로드 파싱(주소/필지 추출).

목적: 사용자가 다필지를 일일이 검색하지 않고, 플랫폼 최적 양식 엑셀에 작성해 업로드하면
필지(주소·지번·법정동코드·PNU·면적·지목·소유구분)를 추출해 다필지 주소등록에 주입한다.

PNU 결정 우선순위(가짜 금지·정직표기):
  ① PNU열(19자리) 그대로  ② 법정동코드(bcode 10자리)+지번 조합  ③ 주소 VWorld 지오코딩(좌표·PNU)
무자료/해석불가 행은 status로 정직 표기(스킵하지 않고 사유 노출 — 사용자가 보정 가능).
의존성: openpyxl·pandas(이미 설치). 외부호출은 ③ 지오코딩만(상한·동시성 제한).
"""
from __future__ import annotations

import asyncio
import io
import re
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 양식 컬럼(순서·헤더 = 플랫폼 표준). 필수=소재지(주소). 나머지는 있으면 정확도↑.
TEMPLATE_COLUMNS = [
    ("연번", "1"),
    ("소재지(주소)", "경기도 의정부시 의정부동 224"),
    ("지번", "224"),
    ("법정동코드(bcode·10자리)", "4115010100"),
    ("PNU(필지고유번호·19자리)", ""),
    ("지목", "대"),
    ("면적(㎡)", "14959"),
    ("소유구분", "사유"),
    ("비고", ""),
]
_MAX_ROWS = 200  # 업로드 행 상한(과도 방지)
_GEOCODE_CONCURRENCY = 5

# 헤더 자동감지 — 정규화(공백/특수문자 제거·소문자) 후 후보집합 매칭.
_H_ADDR = {"소재지", "소재지주소", "주소", "지번주소", "도로명주소", "address", "소재"}
_H_JIBUN = {"지번", "번지", "지번번지", "jibun", "lot"}
_H_BCODE = {"법정동코드", "bcode", "법정동코드10자리", "법정동", "동코드", "admcd"}
_H_PNU = {"pnu", "필지고유번호", "pnu코드", "고유번호", "필지번호"}
_H_JIMOK = {"지목", "지목명", "landcategory", "jimok"}
_H_AREA = {"면적", "면적㎡", "면적m2", "토지면적", "area", "areasqm", "대지면적"}
_H_OWNER = {"소유구분", "소유", "ownertype", "소유자구분"}
_H_LABEL = {"비고", "라벨", "명칭", "메모", "note", "label"}


def _norm(h: Any) -> str:
    return re.sub(r"[\s\-_()·.,/]+", "", str(h or "")).lower()


def _detect_columns(headers: list[Any]) -> dict[str, str | None]:
    """헤더 목록 → 역할별 실제 컬럼명 매핑(첫 일치 우선)."""
    sets = {
        "address": _H_ADDR, "jibun": _H_JIBUN, "bcode": _H_BCODE, "pnu": _H_PNU,
        "jimok": _H_JIMOK, "area": _H_AREA, "owner": _H_OWNER, "label": _H_LABEL,
    }
    found: dict[str, str | None] = {k: None for k in sets}
    for h in headers:
        n = _norm(h)
        for role, candidates in sets.items():
            if found[role] is None and n in candidates:
                found[role] = h
                break
    return found


def _pnu_from_bcode(bcode: str, jibun: str) -> str | None:
    """bcode(10)+지번 → PNU(19). 구조: bcode(10)+대지구분(1:산이면2)+본번(4)+부번(4)."""
    b = re.sub(r"\D", "", str(bcode or ""))
    if len(b) < 10:
        return None
    b = b[:10]
    m = re.search(r"(산)?\s*(\d+)(?:-(\d+))?", str(jibun or ""))
    if not m:
        return None
    san = "2" if m.group(1) else "1"
    return f"{b}{san}{m.group(2).zfill(4)}{(m.group(3) or '0').zfill(4)}"


def _to_float(v: Any) -> float | None:
    try:
        f = float(re.sub(r"[,\s㎡m²]", "", str(v)))
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None


def build_template_xlsx() -> bytes:
    """토지조서 다필지 업로드용 표준 엑셀 양식(예시행 + 안내 시트) 생성."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "토지조서"
    head_fill = PatternFill("solid", fgColor="1F4E79")
    head_font = Font(bold=True, color="FFFFFF", size=11)
    for col, (name, _ex) in enumerate(TEMPLATE_COLUMNS, start=1):
        c = ws.cell(row=1, column=col, value=name)
        c.fill = head_fill
        c.font = head_font
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[c.column_letter].width = max(12, len(name) + 4)
    # 예시 2행(작성 가이드).
    ws.append([ex for _n, ex in TEMPLATE_COLUMNS])
    ws.append(["2", "서울특별시 강남구 역삼동 737", "737", "1168010100", "", "대", "8500", "사유", "예: 본번만"])
    for r in (2, 3):
        for col in range(1, len(TEMPLATE_COLUMNS) + 1):
            ws.cell(row=r, column=col).font = Font(italic=True, color="888888")

    # 안내 시트.
    g = wb.create_sheet("작성안내")
    notes = [
        "■ PropAI 다필지 토지조서 업로드 양식",
        "",
        "1) [소재지(주소)] 는 필수입니다. 나머지는 비워도 됩니다(있으면 정확도↑).",
        "2) PNU(19자리)를 알면 그 열에 입력하세요 — 가장 정확합니다.",
        "3) PNU가 없으면 [법정동코드(10자리)] + [지번] 으로 자동 구성됩니다.",
        "4) 둘 다 없으면 [소재지(주소)] 를 좌표·필지로 자동 조회합니다(다소 느릴 수 있음).",
        "5) '산' 지번은 지번 칸에 '산12-3' 처럼 적으세요.",
        "6) 면적은 ㎡ 기준 숫자만(콤마 가능).",
        f"7) 한 번에 최대 {_MAX_ROWS}필지까지 업로드됩니다.",
        "",
        "※ 예시행(2~3행)은 삭제하고 실제 필지를 입력하세요.",
    ]
    for i, t in enumerate(notes, start=1):
        cell = g.cell(row=i, column=1, value=t)
        if i == 1:
            cell.font = Font(bold=True, size=13)
    g.column_dimensions["A"].width = 70

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class ParcelExcelService:
    """업로드 엑셀 → 필지 목록 추출."""

    async def parse(self, raw: bytes, filename: str) -> dict[str, Any]:
        import pandas as pd

        name = (filename or "").lower()
        try:
            if name.endswith(".csv"):
                df = pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False)
            else:
                df = pd.read_excel(io.BytesIO(raw), dtype=str, engine="openpyxl")
        except Exception as e:  # noqa: BLE001
            return {"error": f"엑셀/CSV를 읽지 못했습니다: {str(e)[:120]}", "parcels": []}

        df = df.fillna("")
        headers = list(df.columns)
        cols = _detect_columns(headers)
        if not cols["address"] and not cols["pnu"] and not cols["bcode"]:
            return {
                "error": "필수 컬럼을 찾지 못했습니다 — 최소 [소재지(주소)] 또는 [PNU] 또는 [법정동코드]가 필요합니다. 표준 양식을 내려받아 작성해 주세요.",
                "detected_columns": cols, "headers": headers, "parcels": [],
            }

        rows = df.to_dict("records")[:_MAX_ROWS]
        parcels: list[dict[str, Any]] = []
        need_geocode: list[int] = []  # 주소만 있는 행 인덱스(지오코딩 대상)

        def _g(row: dict, role: str) -> str:
            col = cols.get(role)
            return str(row.get(col, "")).strip() if col else ""

        for row in rows:
            address = _g(row, "address")
            jibun = _g(row, "jibun")
            bcode = re.sub(r"\D", "", _g(row, "bcode"))
            pnu_raw = re.sub(r"\D", "", _g(row, "pnu"))
            area = _to_float(_g(row, "area"))
            jimok = _g(row, "jimok") or None
            owner = _g(row, "owner") or None
            label = _g(row, "label") or None
            if not (address or pnu_raw or bcode):
                continue  # 완전 빈 행 스킵
            pnu = pnu_raw if len(pnu_raw) == 19 else (_pnu_from_bcode(bcode, jibun) if bcode else None)
            status = "ok" if pnu else ("need_geocode" if address else "failed")
            p = {
                "address": address or None, "jibun": jibun or None,
                "bcode": (bcode[:10] if len(bcode) >= 10 else None),
                "pnu": pnu, "area_sqm": area, "jimok": jimok,
                "owner_type": owner, "label": label,
                # ★자동 보강 필드(주소만 입력해도 PNU 확보 후 채워짐). 무자료=None(가짜 금지).
                "zone_type": None, "official_price_per_sqm": None,
                # 소유자·권리관계는 공공API로 확보 불가 → 등기부등본 열람/발급 필요(사용자 안내).
                "registry_needed": not owner,
                "status": status,
            }
            if status == "need_geocode":
                need_geocode.append(len(parcels))
            parcels.append(p)

        # ③ 주소만 있는 행 — VWorld 지오코딩으로 좌표·PNU 확보(법정동코드 몰라도 됨).
        if need_geocode:
            await self._geocode_fill(parcels, need_geocode)

        # ④ ★데이터 보완·보강 — PNU 확보된 필지의 빈 칸(면적·지목·용도지역·공시지가)을
        #    토지특성(NED)으로 자동 채운다. 사용자는 주소만 적으면 나머지는 시스템이 조회.
        await self._enrich_fill(parcels)

        ok = sum(1 for p in parcels if p["status"] == "ok")
        enriched = sum(1 for p in parcels if p.get("zone_type") or p.get("official_price_per_sqm"))
        return {
            "parcels": parcels,
            "total_rows": len(rows),
            "parsed_count": len(parcels),
            "resolved_count": ok,
            "enriched_count": enriched,
            "detected_columns": cols,
            "examples": parcels[:3],
            # 소유자·권리관계(근저당·지상권 등)는 공공API 미제공 → 등기부등본 열람/발급으로 확보.
            "registry_guidance": {
                "needed_count": sum(1 for p in parcels if p.get("registry_needed")),
                "route": "/land-schedule",
                "message": ("소유자·권리관계(근저당·지상권 등)는 공공데이터로 확인할 수 없습니다 — "
                            "토지조서 화면의 '등기부등본 열람/발급'으로 확보하세요."),
            },
            "note": (f"{len(parcels)}필지 인식 · PNU 확정 {ok}건 · 면적/용도/공시지가 자동보강 {enriched}건. "
                     "주소·지번만 입력해도 좌표·PNU·면적·용도지역·공시지가는 자동 수집됩니다. "
                     "소유자·권리관계는 등기부등본 열람/발급으로 확인하세요. "
                     "status=failed 행은 주소를 보완해 주세요(가짜값 없음)."),
        }

    async def _geocode_fill(self, parcels: list[dict[str, Any]], idxs: list[int]) -> None:
        try:
            from app.services.external_api.vworld_service import VWorldService
        except Exception:  # noqa: BLE001
            return
        vworld = VWorldService()
        sem = asyncio.Semaphore(_GEOCODE_CONCURRENCY)

        async def one(i: int) -> None:
            p = parcels[i]
            async with sem:
                try:
                    geo = await vworld.geocode_address(p["address"] or "")
                except Exception:  # noqa: BLE001
                    geo = None
            if geo:
                gp = geo.get("pnu") or ""
                if len(str(gp)) == 19:
                    p["pnu"] = str(gp)
                    p["bcode"] = p["bcode"] or str(gp)[:10]
                    p["status"] = "ok"
                p["lat"] = geo.get("lat")
                p["lon"] = geo.get("lon")

        await asyncio.gather(*[one(i) for i in idxs], return_exceptions=True)

    async def _enrich_fill(self, parcels: list[dict[str, Any]]) -> None:
        """PNU 확보된 필지의 빈 칸(면적·지목·용도지역·공시지가)을 NED 토지특성으로 보강.

        사용자가 주소만 입력해도 PNU만 있으면 면적/용도/공시지가를 자동 조회한다(가짜값 금지).
        이미 입력된 값(엑셀에 적어둔 면적/지목)은 보존하고 빈 칸만 채운다.
        """
        targets = [
            i for i, p in enumerate(parcels)
            if p.get("pnu") and not (p.get("area_sqm") and p.get("zone_type") and p.get("official_price_per_sqm"))
        ]
        if not targets:
            return
        try:
            from app.services.external_api.vworld_service import VWorldService
        except Exception:  # noqa: BLE001
            return
        vworld = VWorldService()
        sem = asyncio.Semaphore(_GEOCODE_CONCURRENCY)

        async def one(i: int) -> None:
            p = parcels[i]
            async with sem:
                try:
                    lc = await vworld.get_land_characteristics(p["pnu"])
                except Exception:  # noqa: BLE001
                    lc = None
            if not isinstance(lc, dict):
                return
            if not p.get("area_sqm") and lc.get("area_sqm"):
                p["area_sqm"] = round(float(lc["area_sqm"]), 1)
            if not p.get("jimok") and lc.get("land_category"):
                p["jimok"] = lc["land_category"]
            if lc.get("zone_type"):
                p["zone_type"] = lc["zone_type"]
            if lc.get("official_price_per_sqm"):
                p["official_price_per_sqm"] = int(lc["official_price_per_sqm"])

        await asyncio.gather(*[one(i) for i in targets], return_exceptions=True)
