"""시장조사보고서 서비스 — 주변 실거래·시세·입지·수급을 통합해 심층 보고서 생성.

데이터: MolitClient(유형별 실거래 통계) + LandInfoService(용도지역·공시지가·입지) +
AI 내러티브(get_llm, best-effort). 출력: 구조화 dict / PDF(reportlab) / PPTX(python-pptx).
"""

import io
import json
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_TRADE = [("apt", "아파트"), ("villa", "연립·다세대"), ("officetel", "오피스텔"), ("house", "단독·다가구")]
_RENT = [("apt", "아파트"), ("villa", "연립·다세대"), ("officetel", "오피스텔")]

# 면책 고지 — 모든 분석 산출물(보고서) 공통
DISCLAIMER_TEXT = (
    "본 분석결과는 참고용이며, 오류가 있을 수 있습니다. "
    "이와 관련해 사통팔땅은 어떠한 책임도 지지 않습니다. "
    "최종판단은 사용자가 최종 결정하는 것입니다."
)


PYEONG_SQM = 3.305785  # 1평 = 3.305785㎡


def _stat(values: list[float]) -> dict[str, Any]:
    vals = [v for v in values if v and v > 0]
    if not vals:
        return {"count": 0, "avg": 0, "min": 0, "max": 0}
    return {"count": len(vals), "avg": round(sum(vals) / len(vals)), "min": min(vals), "max": max(vals)}


def _per_pyeong_stat(rows: list) -> dict[str, Any]:
    """거래 행에서 평당 단가(만원/평) 통계. price_10k_won(만원) / (area_m2/3.305785)."""
    vals: list[float] = []
    for x in rows:
        p = float(x.get("price_10k_won") or 0)
        a = float(x.get("area_m2") or 0)
        if p > 0 and a > 0:
            vals.append(p / (a / PYEONG_SQM))
    s = _stat(vals)
    # 평당가는 만원 단위 정수로 반올림
    return {"count": s["count"], "avg": round(s["avg"]), "min": round(s["min"]), "max": round(s["max"])}


def _eok(man: float) -> str:
    if not man:
        return "-"
    if man >= 10000:
        return f"{man / 10000:.1f}억"
    return f"{int(man):,}만"


class MarketReportService:
    def __init__(self) -> None:
        from apps.api.integrations.molit_client import MolitClient

        self.molit = MolitClient()

    def _months(self, n: int = 3) -> list[str]:
        now = datetime.now()
        y, m = now.year, now.month - 1  # 현재월 신고지연 → 직전월부터
        if m == 0:
            m = 12
            y -= 1
        out = []
        for _ in range(n):
            out.append(f"{y}{m:02d}")
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return out

    async def _category_stats(self, lawd_cd: str) -> dict[str, Any]:
        import asyncio

        months = self._months(3)
        trade: dict[str, Any] = {}
        rent: dict[str, Any] = {}

        async def trade_one(pt: str, label: str):
            rows: list = []
            res = await asyncio.gather(*[self.molit.get_transactions(lawd_cd, ym, prop_type=pt, num_rows=1000) for ym in months], return_exceptions=True)
            for r in res:
                if isinstance(r, list):
                    rows.extend(r)
            prices = [float(x.get("price_10k_won") or 0) for x in rows]
            areas = [float(x.get("area_m2") or 0) for x in rows]
            return label, {
                **_stat(prices),
                "avg_area_m2": round(sum(a for a in areas if a > 0) / max(1, len([a for a in areas if a > 0])), 1) if areas else 0,
                "per_pyeong": _per_pyeong_stat(rows),  # 평당가(만원/평) — 면적 정규화 시세
            }

        async def rent_one(pt: str, label: str):
            rows: list = []
            res = await asyncio.gather(*[self.molit.get_rent_transactions(lawd_cd, ym, prop_type=pt, num_rows=1000) for ym in months], return_exceptions=True)
            for r in res:
                if isinstance(r, list):
                    rows.extend(r)
            dep = [float(x.get("deposit_10k_won") or 0) for x in rows]
            return label, {**_stat(dep), "count": len([d for d in dep if d > 0])}

        # 아파트 매매 월별 추이(시세 추이 차트용)
        async def apt_month(ym: str):
            try:
                rows = await self.molit.get_transactions(lawd_cd, ym, prop_type="apt", num_rows=1000)
            except Exception:  # noqa: BLE001
                rows = []
            prices = [float(x.get("price_10k_won") or 0) for x in rows if (x.get("price_10k_won") or 0) > 0]
            pp = _per_pyeong_stat(rows)
            return {
                "ym": ym,
                "avg": round(sum(prices) / len(prices)) if prices else 0,  # 총액 평균(만원)
                "avg_per_pyeong": pp["avg"],  # 평당가(만원/평) — 추이 기준
                "count": len(prices),
            }

        tr = await asyncio.gather(*[trade_one(pt, lb) for pt, lb in _TRADE])
        rr = await asyncio.gather(*[rent_one(pt, lb) for pt, lb in _RENT])
        trend = await asyncio.gather(*[apt_month(ym) for ym in months])
        trade = dict(tr)
        rent = dict(rr)
        # 추이는 과거→현재 순으로
        trend_sorted = sorted(trend, key=lambda t: t["ym"])
        return {"months": months, "trade": trade, "rent": rent, "apt_trend": trend_sorted}

    async def _narrative(self, ctx: dict[str, Any]) -> dict[str, Any]:
        """AI 시장 해석(요약·기회·리스크). 실패 시 구조화 폴백."""
        try:
            from app.services.ai.llm_provider import get_llm
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_llm(timeout=40, max_tokens=1500)
            sys = ("당신은 부동산 개발 및 시장분석 전문가다. 제공된 실거래·시세·입지 데이터와 인구 이동, 연령대, 평균 소득 데이터를 종합하여 "
                   "한국어 JSON으로 답하라. 키: summary(시장요약 3~4문장), opportunities(기회 2~3개 배열), "
                   "risks(리스크 2~3개 배열), price_trend(가격동향 2문장), target_persona(추천 분양 타겟 고객층 2문장). "
                   "★모든 거래시세·분양가는 반드시 평당가(만원/평) 기준으로 서술하라. 총액(억원)이 아닌 "
                   "평당 단가를 사용한다. 예: '아파트 평당 약 1,800만원'. 데이터 단위는 만원/평이다. "
                   "★target_persona에는 유입 인구의 주 연령대, 거시적 평균 소득을 고려해 가장 분양 가능성이 높은 고객의 직업군/가구형태/특화설계 제안을 포함하라.")
            usr = f"## 시장 데이터\n{json.dumps(ctx, ensure_ascii=False)[:4000]}"
            resp = await llm.ainvoke([SystemMessage(content=sys), HumanMessage(content=usr)])
            raw = resp.content if hasattr(resp, "content") else str(resp)
            txt = raw.strip()
            if txt.startswith("```"):
                txt = txt.split("```")[1].lstrip("json").strip() if "```" in txt[3:] else txt.strip("`")
            data = json.loads(txt)
            return data
        except Exception as e:  # noqa: BLE001
            logger.warning("시장 내러티브 생성 실패, 구조화 폴백", err=str(e)[:80])
            return {"summary": "수집된 실거래·시세 데이터를 기반으로 한 시장 현황입니다.", "opportunities": [], "risks": [], "price_trend": "", "target_persona": "데이터 기반 타겟팅 분석 불가"}

    async def _nearby_presale_84_price(
        self, lawd_cd: str, coords: Any,
    ) -> tuple[float | None, str]:
        """주변 신규 분양가(청약홈) → 84㎡급 대표 분양총액(만원) 중앙값. (값, 출처).

        거래사례비교 1차 보강. PresaleService.nearby(거리필터 공고) → 가까운 아파트 공고 상위 3개의
        detail(주택형별 분양총액 price_man·공급면적)에서 84㎡급(공급 100~125㎡) 분양가를 모아 중앙값.
        키 미설정/데이터 없음/타임아웃이면 (None, 'unavailable') 정직 반환(가짜값 금지).
        보고서 지연 방지를 위해 하드타임아웃 적용.
        """
        import asyncio as _aio
        try:
            from app.services.land_intelligence.presale_service import PresaleService, area_from_lawd
        except Exception:  # noqa: BLE001
            return None, "unavailable"
        _lat = coords.get("lat") if isinstance(coords, dict) else None
        _lon = (coords.get("lon") or coords.get("lng")) if isinstance(coords, dict) else None
        try:
            svc = PresaleService()
            near = await _aio.wait_for(
                svc.nearby(_lat, _lon, area_from_lawd(lawd_cd),
                           radius_m=3000, months_back=12, max_markers=8),
                timeout=12.0)
            if not near.get("available"):
                return None, "unavailable"
            picks = [it for it in (near.get("items") or []) if it.get("house_manage_no")][:3]
            if not picks:
                return None, "unavailable"
            details = await _aio.wait_for(_aio.gather(*[
                svc.detail(it.get("house_manage_no", ""), it.get("pblanc_no", ""), it.get("product", "apt"))
                for it in picks], return_exceptions=True), timeout=15.0)
            cands: list[float] = []
            for d in details:
                if not isinstance(d, dict) or not d.get("available"):
                    continue
                for m in d.get("models", []):
                    try:
                        amt = float(m.get("price_man"))
                        ar = float(m.get("supply_area_m2"))
                    except (TypeError, ValueError):
                        continue
                    # 전용 84㎡급 ≈ 공급 100~125㎡ — 실거래 84㎡ 기준가와 일관되게 비교.
                    if amt > 0 and 100.0 <= ar <= 125.0:
                        cands.append(amt)
            if not cands:
                return None, "unavailable"
            cands.sort()
            return float(cands[len(cands) // 2]), "live"  # 중앙값
        except Exception:  # noqa: BLE001 — 타임아웃·네트워크·파싱 실패 시 정직 None
            return None, "unavailable"

    async def build_report(self, address: str, lawd_cd: str, pnu: str | None = None, use_llm: bool = True, options: dict | None = None) -> dict[str, Any]:
        from app.services.land_intelligence.land_info_service import LandInfoService
        
        options = options or {}
        use_sgis = options.get("sgis", False)
        use_kosis = options.get("kosis", False)

        comp = {}
        try:
            comp = await LandInfoService().collect_comprehensive(address, pnu=pnu)
        except Exception:  # noqa: BLE001
            pass
        stats = await self._category_stats(lawd_cd)

        # ── Phase 1: 공공 인구 및 소득 데이터(SGIS, KOSIS) 연동 ──
        from apps.api.integrations.sgis_client import SgisClient
        from apps.api.integrations.kosis_client import KosisClient
        from apps.api.app.services.market.market_models import DemographicProfile, MigrationData, PopulationData, MacroIncomeData
        import asyncio
        
        sgis = SgisClient()
        kosis = KosisClient()
        cur_year = str(datetime.now().year)
        
        # 병렬로 인구이동, 연령통계, 거시소득 호출 (옵션 선택 여부에 따라 분기)
        demographics: dict[str, Any] | None = None
        if use_sgis or use_kosis:
            try:
                # use_mock=None: 클라이언트가 키 존재 여부로 실연동/폴백을 자동 결정한다.
                #   (과거 use_mock=True 하드코딩으로 키가 있어도 항상 Mock만 나오던 G1 결함 제거)
                #   키가 있으면 실데이터 시도→data_source='live', 없으면 폴백→'fallback'/'mock'/'unavailable'.
                async def fetch_mig():
                    if not use_sgis:
                        return {"target_adm_cd": lawd_cd, "year": cur_year}
                    # I2: 인구이동(OD)은 SGIS 미제공 → KOSIS 국내인구이동통계 우선 시도.
                    #     데이터 있으면 전출지별 유입 Top, 없으면 SGIS 정직 unavailable 폴백(가짜 금지).
                    od = await kosis.get_migration_od(lawd_cd[:5], cur_year)
                    if od.get("top_inflow_regions"):
                        return od
                    return await sgis.get_migration_stats(lawd_cd, cur_year)
                async def fetch_pop():
                    return await sgis.get_population_stats(lawd_cd, cur_year) if use_sgis else {"target_adm_cd": lawd_cd, "year": cur_year}
                async def fetch_inc():
                    return await kosis.get_macro_income_stats(lawd_cd[:5], cur_year) if use_kosis else {"sigungu_cd": lawd_cd[:5], "year": cur_year}

                mig, pop, inc = await asyncio.gather(
                    fetch_mig(),
                    fetch_pop(),
                    fetch_inc(),
                    return_exceptions=True
                )
                # Pydantic 모델을 사용해 어댑터 패턴으로 데이터 표준화
                profile = DemographicProfile(
                    source_phase=1,
                    migration=MigrationData(**(mig if not isinstance(mig, Exception) else {"target_adm_cd": lawd_cd, "year": cur_year})),
                    population=PopulationData(**(pop if not isinstance(pop, Exception) else {"target_adm_cd": lawd_cd, "year": cur_year})),
                    macro_income=MacroIncomeData(**(inc if not isinstance(inc, Exception) else {"sigungu_cd": lawd_cd[:5], "year": cur_year}))
                )
                demographics = profile.model_dump()
            except Exception as e:
                logger.warning("Demographic data fetch failed", error=str(e))

        comp = comp if isinstance(comp, dict) else {}
        zone = comp.get("local_ordinance") or {}
        land_use = comp.get("land_use_plan") or {}
        basic = comp.get("land_register") or comp.get("basic") or {}
        infra = comp.get("infrastructure") or {}
        coords = comp.get("coordinates")
        # 용도지역: 여러 경로에서 견고하게 추출
        zone_type = (
            zone.get("zone_type") or land_use.get("zone_type")
            or basic.get("zone_type") or comp.get("zone_type")
        )
        official_price = None
        if comp.get("official_prices"):
            official_price = (comp["official_prices"][0] or {}).get("price_per_sqm")
        # 폴백: AutoZoningService(파이프라인 용도지역 감지기)로 보강
        if not zone_type:
            try:
                from app.services.zoning.auto_zoning_service import AutoZoningService

                az = await AutoZoningService().analyze_by_address(address)
                zone_type = az.get("zone_type")
                if not official_price and az.get("official_price_per_sqm"):
                    official_price = az.get("official_price_per_sqm")
            except Exception:  # noqa: BLE001
                pass

        # 평당가(만원/평) 요약 — 모든 시세는 면적 정규화된 평당가 기준으로 서술
        pp_by_type = {
            label: (v.get("per_pyeong") or {}).get("avg")
            for label, v in stats["trade"].items()
            if (v.get("per_pyeong") or {}).get("avg")
        }
        apt_pp = ((stats["trade"].get("아파트") or {}).get("per_pyeong") or {}).get("avg")
        
        # ── Phase 3: 사업 타당성 분석 (Feasibility Engine) ──
        from app.services.market.feasibility_service import FeasibilityService
        land_area = float(basic.get("land_area") or basic.get("area_sqm") or 330.0) # 기본 100평
        # 대표 평당가는 아파트 평당가를 우선 사용, 없으면 전체 평균 사용
        valid_pp = [v for v in pp_by_type.values() if v is not None]
        target_pp = apt_pp or (sum(valid_pp)/len(valid_pp) if valid_pp else 2000)
        feasibility = FeasibilityService().analyze_feasibility(
            land_area_sqm=land_area,
            zone_type=zone_type or "",
            avg_pyeong_price_manwon=target_pp,
            official_price_per_sqm=official_price or 0
        )

        # ── M3: 적정 분양가 산정 — 거래사례비교(1차 핵심) + 지불여력(2차 검증)·결정론 ──
        # 1차: 주변 동일종목 실거래 시세(평당가)·주변 분양가. 2차: KOSIS 소득→PIR/DSR/LTV로 수요 수용성.
        # 비교 데이터 없으면 엔진이 data_source='unavailable'로 정직 반환(가짜값 금지).
        from app.services.market.pricing_band_service import compute_fair_price
        _mi = (demographics or {}).get("macro_income") or {}
        _income_10k = _mi.get("median_income_10k") or _mi.get("avg_income_10k")
        # 실거래 평당가(만원/평) — 폴백 2000 제외, 실값만 비교가로 사용.
        _real_pp = apt_pp or (sum(valid_pp) / len(valid_pp) if valid_pp else None)
        # 대표 84㎡ 1세대 실거래 기반가(만원) = 평당가 × 25.4평(=84/3.305785)
        _trade_unit_10k = round(_real_pp * (84.0 / 3.305785)) if _real_pp else None
        # 주변 신규 분양가(청약홈) — 84㎡급(공급 100~125㎡) 분양총액 중앙값. 키/데이터 없으면 None(정직).
        _presale_10k, _presale_src = await self._nearby_presale_84_price(lawd_cd, coords)
        pricing_band = compute_fair_price(
            comparable_trade_10k=_trade_unit_10k,
            nearby_presale_10k=_presale_10k,
            annual_income_10k=_income_10k,
            trade_source="live" if _real_pp else None,
            presale_source=_presale_src,
            income_source=_mi.get("data_source"),
        )

        # ── I6: 수요기반 평형 MD 추천(가구원수 분포 → 권장 전용면적 배분)·결정론 ──
        from app.services.market.unit_mix_recommender import recommend_unit_mix
        _pop = (demographics or {}).get("population") or {}
        unit_mix_recommendation = recommend_unit_mix(
            _pop.get("household_types"),
            data_source=_pop.get("data_source"),
        )

        ctx = {
            "address": address,
            "zone_type": zone_type,
            "official_price_per_sqm": official_price,
            "price_basis": "평당가(만원/평) 기준으로 서술할 것",
            "apt_avg_per_pyeong_manwon": apt_pp,
            "avg_per_pyeong_by_type_manwon": pp_by_type,
            "apt_trend_per_pyeong": [
                {"ym": t["ym"], "per_pyeong_manwon": t.get("avg_per_pyeong")}
                for t in (stats.get("apt_trend") or [])
            ],
            "rent_stats_manwon": stats["rent"],
            "subway": (infra.get("nearest_subway") or {}).get("name") if isinstance(infra, dict) else None,
            "demographics": demographics,
            "feasibility": feasibility,
        }
        narrative = await self._narrative(ctx) if use_llm else {
            "summary": "수집된 실거래·시세 데이터 기반 시장 현황입니다. (AI 분석 미포함)",
            "opportunities": [], "risks": [], "price_trend": "", "target_persona": "AI 분석 미포함"
        }

        return {
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "address": address,
            "lawd_cd": lawd_cd,
            "coordinates": coords,
            "months": stats["months"],
            "zone_type": ctx["zone_type"],
            "official_price_per_sqm": official_price,
            "trade": stats["trade"],
            "rent": stats["rent"],
            "apt_trend": stats.get("apt_trend") or [],
            "infrastructure": infra,
            "demographics": demographics,
            "narrative": narrative,
            "feasibility_analysis": feasibility,
            "pricing_band": pricing_band,
            "unit_mix_recommendation": unit_mix_recommendation,
        }

    # ── 정적 지도 이미지(OSM 타일 합성, Pillow) ──
    @staticmethod
    def static_map_png(lat: float, lon: float, radius_m: int = 1000, zoom: int = 15,
                       w: int = 720, h: int = 440) -> bytes | None:
        """대상 좌표 중심 OSM 정적 지도 PNG(중심핀 + 반경원). 실패 시 None."""
        try:
            import math
            import httpx
            from PIL import Image, ImageDraw

            n = 2 ** zoom
            xf = (lon + 180.0) / 360.0 * n
            lat_r = math.radians(lat)
            yf = (1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n
            cols = w // 256 + 2
            rows = h // 256 + 2
            x0 = int(xf) - cols // 2
            y0 = int(yf) - rows // 2
            canvas = Image.new("RGB", (cols * 256, rows * 256), (235, 235, 235))
            headers = {"User-Agent": "PropAI/1.0 (market report)"}
            with httpx.Client(timeout=8.0, headers=headers) as client:
                for cx in range(cols):
                    for cy in range(rows):
                        tx, ty = x0 + cx, y0 + cy
                        if tx < 0 or ty < 0 or tx >= n or ty >= n:
                            continue
                        try:
                            r = client.get(f"https://a.tile.openstreetmap.org/{zoom}/{tx}/{ty}.png")
                            if r.status_code == 200:
                                tile = Image.open(io.BytesIO(r.content)).convert("RGB")
                                canvas.paste(tile, (cx * 256, cy * 256))
                        except Exception:  # noqa: BLE001
                            continue
            # 중심 픽셀
            cpx = int((xf - x0) * 256)
            cpy = int((yf - y0) * 256)
            # 목표 크기로 중심 크롭
            left = max(0, cpx - w // 2)
            top = max(0, cpy - h // 2)
            img = canvas.crop((left, top, left + w, top + h))
            d = ImageDraw.Draw(img, "RGBA")
            ox, oy = cpx - left, cpy - top
            # 반경 원
            mpp = 156543.03392 * math.cos(lat_r) / n
            rpx = int(radius_m / mpp)
            d.ellipse([ox - rpx, oy - rpx, ox + rpx, oy + rpx], outline=(20, 184, 166, 220), width=3)
            d.ellipse([ox - rpx, oy - rpx, ox + rpx, oy + rpx], fill=(20, 184, 166, 30))
            # 중심 핀
            d.ellipse([ox - 9, oy - 9, ox + 9, oy + 9], fill=(239, 68, 68, 255), outline=(255, 255, 255, 255), width=3)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception as e:  # noqa: BLE001
            logger.warning("정적 지도 생성 실패", err=str(e)[:80])
            return None

    # ── PDF (reportlab) ──
    def to_pdf(self, rep: dict[str, Any]) -> bytes:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        try:
            pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
            font = "HYSMyeongJo-Medium"
        except Exception:  # noqa: BLE001
            font = "Helvetica"

        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=18 * mm, bottomMargin=18 * mm)
        ss = getSampleStyleSheet()
        h1 = ParagraphStyle("h1", parent=ss["Title"], fontName=font, fontSize=20)
        h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName=font, fontSize=13, textColor=colors.HexColor("#0e7490"))
        body = ParagraphStyle("body", parent=ss["BodyText"], fontName=font, fontSize=10, leading=16)
        story: list = []
        story.append(Paragraph("시장조사보고서", h1))
        story.append(Paragraph(f"{rep['address']} · 생성 {rep['generated_at']} · 최근 {len(rep['months'])}개월", body))
        story.append(Spacer(1, 8))

        # 대상지 지도 캡처
        coords = rep.get("coordinates") or {}
        if coords.get("lat") and coords.get("lon"):
            png = self.static_map_png(coords["lat"], coords["lon"], 1000)
            if png:
                from reportlab.platypus import Image as RLImage

                story.append(Paragraph("대상지 위치 (반경 1km)", h2))
                story.append(RLImage(io.BytesIO(png), width=165 * mm, height=101 * mm))
                story.append(Spacer(1, 8))

        nar = rep.get("narrative") or {}
        story.append(Paragraph("1. 시장 요약", h2))
        story.append(Paragraph(nar.get("summary") or "-", body))
        if rep.get("zone_type") or rep.get("official_price_per_sqm"):
            story.append(Paragraph(f"용도지역: {rep.get('zone_type') or '-'} · 공시지가(㎡): {_eok((rep.get('official_price_per_sqm') or 0)/10000) if rep.get('official_price_per_sqm') else '-'}", body))
        story.append(Spacer(1, 6))

        def stat_table(title: str, data: dict, unit_label: str):
            story.append(Paragraph(title, h2))
            rows = [["유형", "건수", "평균", "최저", "최고"]]
            for label, s in data.items():
                rows.append([label, str(s.get("count", 0)), _eok(s.get("avg", 0)), _eok(s.get("min", 0)), _eok(s.get("max", 0))])
            t = Table(rows, colWidths=[45 * mm, 25 * mm, 35 * mm, 35 * mm, 35 * mm])
            t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e7490")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))

        # 매매 시세: 평당가(만원/평) 중심 + 총액 평균 병기
        def trade_table(title: str, data: dict):
            story.append(Paragraph(title, h2))
            rows = [["유형", "건수", "평당가(만원/평)", "총액 평균", "평균면적"]]
            for label, s in data.items():
                pp = (s.get("per_pyeong") or {}).get("avg", 0)
                area = s.get("avg_area_m2", 0)
                rows.append([
                    label, str(s.get("count", 0)),
                    f"{int(pp):,}만원/평" if pp else "-",
                    _eok(s.get("avg", 0)),
                    f"{area:.1f}㎡({round(area / PYEONG_SQM)}평)" if area else "-",
                ])
            t = Table(rows, colWidths=[40 * mm, 20 * mm, 42 * mm, 35 * mm, 38 * mm])
            t.setStyle(TableStyle([
                ("FONTNAME", (0, 0), (-1, -1), font), ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e7490")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]))
            story.append(t)
            story.append(Spacer(1, 8))

        trade_table("2. 매매 시세 (유형별 · 평당가 기준)", rep.get("trade") or {})
        stat_table("3. 전월세 보증금 (유형별)", rep.get("rent") or {}, "만원")

        # 시세 추이 차트(아파트 월별 평당가)
        trend = [t for t in (rep.get("apt_trend") or []) if t.get("avg_per_pyeong") or t.get("avg")]
        if trend:
            from reportlab.graphics.shapes import Drawing
            from reportlab.graphics.charts.barcharts import VerticalBarChart

            story.append(Paragraph("4. 매매 시세 추이 (아파트 월별 평당가, 만원/평)", h2))
            d = Drawing(440, 170)
            bc = VerticalBarChart()
            bc.x = 40; bc.y = 25; bc.width = 360; bc.height = 120
            bc.data = [[int(t.get("avg_per_pyeong") or t.get("avg") or 0) for t in trend]]
            bc.categoryAxis.categoryNames = [f"{int(t['ym'][4:6])}월" for t in trend]
            bc.categoryAxis.labels.fontName = font
            bc.valueAxis.labels.fontName = font
            bc.barWidth = 14
            bc.bars[0].fillColor = colors.HexColor("#0e7490")
            bc.valueAxis.valueMin = 0
            d.add(bc)
            story.append(d)
            story.append(Spacer(1, 8))

        story.append(Paragraph("5. 기회 요인", h2))
        for o in (nar.get("opportunities") or ["-"]):
            story.append(Paragraph(f"· {o}", body))
        story.append(Spacer(1, 4))
        story.append(Paragraph("6. 리스크 요인", h2))
        for r in (nar.get("risks") or ["-"]):
            story.append(Paragraph(f"· {r}", body))
        story.append(Spacer(1, 4))
        story.append(Paragraph("7. 가격 동향", h2))
        story.append(Paragraph(nar.get("price_trend") or "-", body))

        # 면책 고지
        story.append(Spacer(1, 14))
        disc = ParagraphStyle("disc", parent=body, fontSize=7.5, textColor=colors.HexColor("#888888"), leading=11)
        story.append(Paragraph(DISCLAIMER_TEXT, disc))

        doc.build(story)
        return buf.getvalue()

    # ── PPTX (python-pptx) ──
    def to_pptx(self, rep: dict[str, Any]) -> bytes:
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor

        from pptx.enum.shapes import MSO_SHAPE

        prs = Presentation()
        prs.slide_width = Inches(13.33)
        prs.slide_height = Inches(7.5)
        accent = RGBColor(0x0E, 0x74, 0x90)
        ink = RGBColor(0x0F, 0x17, 0x2A)
        WHITE = RGBColor(0xFF, 0xFF, 0xFF)

        def _fill(shape, rgb):
            shape.fill.solid()
            shape.fill.fore_color.rgb = rgb
            shape.line.fill.background()

        def brand_footer(s):
            bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(7.1), Inches(13.33), Inches(0.4))
            _fill(bar, accent)
            tf = bar.text_frame
            tf.margin_top = Pt(2)
            tf.text = "사통팔땅 · AI 부동산 인텔리전스   |   시장조사보고서"
            tf.paragraphs[0].font.size = Pt(10)
            tf.paragraphs[0].font.color.rgb = WHITE

        def header_bar(s, title: str):
            bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(1.1))
            _fill(bar, accent)
            tf = bar.text_frame
            tf.margin_left = Inches(0.6)
            tf.word_wrap = True
            tf.text = title
            tf.paragraphs[0].font.size = Pt(26)
            tf.paragraphs[0].font.bold = True
            tf.paragraphs[0].font.color.rgb = WHITE

        def title_slide():
            s = prs.slides.add_slide(prs.slide_layouts[6])
            # 브랜드 풀블리드 배경
            bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.33), Inches(7.5))
            _fill(bg, ink)
            band = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, Inches(2.0), Inches(13.33), Inches(0.12))
            _fill(band, accent)
            brand = s.shapes.add_textbox(Inches(0.9), Inches(0.7), Inches(11), Inches(0.6)).text_frame
            brand.text = "사통팔땅  ·  AI 부동산 인텔리전스"
            brand.paragraphs[0].font.size = Pt(16); brand.paragraphs[0].font.color.rgb = accent; brand.paragraphs[0].font.bold = True
            tb = s.shapes.add_textbox(Inches(0.9), Inches(2.5), Inches(11.7), Inches(2.5)).text_frame
            tb.text = "시장조사보고서"
            tb.paragraphs[0].font.size = Pt(52); tb.paragraphs[0].font.bold = True; tb.paragraphs[0].font.color.rgb = WHITE
            p = tb.add_paragraph()
            p.text = f"{rep['address']}"
            p.font.size = Pt(22); p.font.color.rgb = WHITE
            p2 = tb.add_paragraph()
            p2.text = f"생성 {rep['generated_at']} · 최근 {len(rep['months'])}개월 · 실거래 기반"
            p2.font.size = Pt(14); p2.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)
            # 면책 고지
            disc = s.shapes.add_textbox(Inches(0.9), Inches(6.7), Inches(11.7), Inches(0.6)).text_frame
            disc.word_wrap = True
            disc.text = DISCLAIMER_TEXT
            disc.paragraphs[0].font.size = Pt(9); disc.paragraphs[0].font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

        def map_slide():
            coords = rep.get("coordinates") or {}
            if not (coords.get("lat") and coords.get("lon")):
                return
            png = self.static_map_png(coords["lat"], coords["lon"], 1000)
            if not png:
                return
            s = prs.slides.add_slide(prs.slide_layouts[6])
            header_bar(s, "대상지 위치 (반경 1km)")
            s.shapes.add_picture(io.BytesIO(png), Inches(2.6), Inches(1.4), height=Inches(5.4))
            brand_footer(s)

        def text_slide(title: str, lines: list[str]):
            s = prs.slides.add_slide(prs.slide_layouts[6])
            header_bar(s, title)
            bodytf = s.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(11.7), Inches(5.2)).text_frame
            bodytf.word_wrap = True
            for i, ln in enumerate(lines or ["-"]):
                para = bodytf.paragraphs[0] if i == 0 else bodytf.add_paragraph()
                para.text = ln
                para.font.size = Pt(16); para.font.color.rgb = ink
                para.space_after = Pt(8)
            brand_footer(s)

        def table_slide(title: str, data: dict, pp: bool = False):
            s = prs.slides.add_slide(prs.slide_layouts[6])
            header_bar(s, title)
            rows = len(data) + 1
            ncol = 4 if pp else 5
            tbl = s.shapes.add_table(rows, ncol, Inches(0.8), Inches(1.5), Inches(11.7), Inches(0.5 * rows)).table
            hdr = ["유형", "건수", "평당가(만원/평)", "총액 평균"] if pp else ["유형", "건수", "평균", "최저", "최고"]
            for c, h in enumerate(hdr):
                cell = tbl.cell(0, c)
                cell.text = h
                cell.fill.solid(); cell.fill.fore_color.rgb = accent
                cell.text_frame.paragraphs[0].font.color.rgb = WHITE
                cell.text_frame.paragraphs[0].font.bold = True
            for r, (label, st) in enumerate(data.items(), start=1):
                tbl.cell(r, 0).text = label
                tbl.cell(r, 1).text = str(st.get("count", 0))
                if pp:
                    ppv = (st.get("per_pyeong") or {}).get("avg", 0)
                    tbl.cell(r, 2).text = f"{int(ppv):,}만원/평" if ppv else "-"
                    tbl.cell(r, 3).text = _eok(st.get("avg", 0))
                else:
                    tbl.cell(r, 2).text = _eok(st.get("avg", 0))
                    tbl.cell(r, 3).text = _eok(st.get("min", 0))
                    tbl.cell(r, 4).text = _eok(st.get("max", 0))
            brand_footer(s)

        def chart_slide(title: str, trend: list[dict[str, Any]]):
            from pptx.chart.data import CategoryChartData
            from pptx.enum.chart import XL_CHART_TYPE

            s = prs.slides.add_slide(prs.slide_layouts[6])
            header_bar(s, title)
            cd = CategoryChartData()
            cd.categories = [f"{int(x['ym'][4:6])}월" for x in trend]
            cd.add_series("아파트 평당가(만원/평)", [int(x.get("avg_per_pyeong") or x.get("avg") or 0) for x in trend])
            s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.8), Inches(1.5), Inches(11.7), Inches(5), cd)
            brand_footer(s)

        nar = rep.get("narrative") or {}
        trend = [x for x in (rep.get("apt_trend") or []) if x.get("avg_per_pyeong") or x.get("avg")]
        title_slide()
        map_slide()
        text_slide("1. 시장 요약", [nar.get("summary") or "-", f"용도지역: {rep.get('zone_type') or '-'}"])
        table_slide("2. 매매 시세 (유형별 · 평당가)", rep.get("trade") or {}, pp=True)
        table_slide("3. 전월세 보증금 (유형별)", rep.get("rent") or {})
        if trend:
            chart_slide("4. 매매 시세 추이 (아파트 월별 평당가)", trend)
        text_slide("5. 기회 요인", [f"· {o}" for o in (nar.get("opportunities") or ["-"])])
        text_slide("6. 리스크 요인", [f"· {r}" for r in (nar.get("risks") or ["-"])])
        text_slide("7. 가격 동향", [nar.get("price_trend") or "-"])

        buf = io.BytesIO()
        prs.save(buf)
        return buf.getvalue()
