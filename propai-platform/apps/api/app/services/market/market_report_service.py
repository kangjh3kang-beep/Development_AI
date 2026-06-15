"""시장조사보고서 서비스 — 주변 실거래·시세·입지·수급을 통합해 심층 보고서 생성.

데이터: MolitClient(유형별 실거래 통계) + LandInfoService(용도지역·공시지가·입지) +
AI 내러티브(get_llm, best-effort). 출력: 구조화 dict / PDF(reportlab) / PPTX(python-pptx).
"""

import io
import json
import re
from datetime import datetime
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# 주소에서 시/군/구 토큰 추출. KOSIS·SGIS는 통합시(수원·성남·고양 등)를 다르게 표기한다:
#   KOSIS 인구이동/소득 표 → 시 단위 집계('수원시', 자치구 없음)
#   SGIS stage 목록        → 시+구('수원시 장안구')
# 광역/특별시 자치구는 양쪽 모두 '강남구', 일반 시/군은 '파주시'/'○○군' 그대로.
_SIGUNGU_RE = re.compile(r"([가-힣]{1,6}(?:시|군|구))")


def _extract_region_keys(address: str | None) -> tuple[str | None, str | None]:
    """주소 → (KOSIS 시군구명, SGIS 시군구명). provider별 표기 차이를 흡수한다."""
    if not address:
        return (None, None)
    toks = _SIGUNGU_RE.findall(address)
    if not toks:
        return (None, None)
    # 시도(광역/특별/특별자치시)는 제외 — 실제 시군구만.
    si = next((t for t in reversed(toks)
               if t.endswith("시") and not t.endswith(("광역시", "특별시", "특별자치시"))), None)
    gu = next((t for t in reversed(toks) if t.endswith("구")), None)
    gun = next((t for t in reversed(toks) if t.endswith("군")), None)
    if si and gu:        # 통합시 자치구(수원시 장안구): KOSIS=시, SGIS="시 구"
        return (si, f"{si} {gu}")
    if gu:               # 광역/특별시 자치구(강남구): 양쪽 동일
        return (gu, gu)
    if si:               # 일반시(파주시)
        return (si, si)
    if gun:              # 군
        return (gun, gun)
    return (None, None)

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


# ── raw_data 빌더(순수 함수·네트워크 없음) ──────────────────────────────────
# 프론트(P3)·export(P4)가 dict 를 재가공하지 않도록 표(row 배열)로 평탄화한다.
# 가짜 데이터 금지: provider 가 안 준 값은 None, 미선택 분류는 키 자체를 생략한다(아래 규칙).

def _re_per_pyeong(price_10k: float, area_m2: float) -> float | None:
    """총액(만원)·면적(㎡) → 평당가(만원/평). 값이 유효할 때만 반올림 정수."""
    if price_10k and area_m2 and price_10k > 0 and area_m2 > 0:
        return round(price_10k / (area_m2 / PYEONG_SQM))
    return None


def _build_trade_table(trade: dict[str, Any]) -> list[dict[str, Any]]:
    """stats['trade'] → 행 배열. 각 유형의 건수·총액통계·평균면적·평당가를 평탄화."""
    rows: list[dict[str, Any]] = []
    for label, s in (trade or {}).items():
        pp = (s.get("per_pyeong") or {}).get("avg")
        rows.append({
            "type": label,
            "count": s.get("count", 0),
            "avg_10k": s.get("avg", 0),
            "min_10k": s.get("min", 0),
            "max_10k": s.get("max", 0),
            "avg_area_m2": s.get("avg_area_m2", 0),
            "per_pyeong_manwon": pp if pp else None,
        })
    return rows


def _build_rent_table(rent: dict[str, Any]) -> list[dict[str, Any]]:
    """stats['rent'] → 행 배열. 보증금 통계(있는 필드만)."""
    rows: list[dict[str, Any]] = []
    for label, s in (rent or {}).items():
        rows.append({
            "type": label,
            "count": s.get("count", 0),
            "avg_10k": s.get("avg", 0),
            "min_10k": s.get("min", 0),
            "max_10k": s.get("max", 0),
        })
    return rows


def _build_trend_series(apt_trend: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """apt_trend(과거→현재 정렬됨) → {ym, per_pyeong_manwon, mom_pct} 행 배열.

    mom_pct(전월대비 증감률 %) = ((현재-직전)/직전*100) 반올림 1자리. 첫 항목은 None(직전 없음).
    직전 평당가가 0/None 이면 분모 0 방지로 None.
    """
    out: list[dict[str, Any]] = []
    prev: float | None = None
    for t in (apt_trend or []):
        cur = t.get("avg_per_pyeong")
        mom = None
        if prev and cur and prev > 0:
            mom = round((cur - prev) / prev * 100, 1)
        out.append({
            "ym": t.get("ym"),
            "per_pyeong_manwon": cur if cur else None,
            "mom_pct": mom,
        })
        if cur:
            prev = cur
    return out


def _build_population_block(demographics: dict[str, Any] | None) -> dict[str, Any] | None:
    """demographics.population/migration → 표 평탄화 블록.

    미선택 분류(population 비어 있고 data_source 없음)면 None 반환 → 호출측에서 키 생략.
    선택했으나 provider 실패면 data_source='unavailable'/'fallback' 등으로 정직 표기.
    """
    pop = (demographics or {}).get("population") or {}
    mig = (demographics or {}).get("migration") or {}
    pop_src = pop.get("data_source")
    mig_src = mig.get("data_source")
    # 둘 다 data_source 가 없으면 = 미선택(호출 자체를 안 함) → 키 생략 신호로 None.
    if pop_src is None and mig_src is None:
        return None

    # 연령분포: SGIS 는 {label: count} dict(예: {"0-9": n, ...}) → 행 배열.
    age_dist = pop.get("age_distribution") or {}
    age_rows = [{"label": k, "count": v} for k, v in age_dist.items()] if isinstance(age_dist, dict) else []

    # 가구원수 분포: {"1_person","2_person","3_person","4_over"} 비율(%) → 행 배열.
    #   SGIS 미제공이라 평균 가구원수 기반 '추정'(estimated=true) — note 로도 명시됨.
    ht = pop.get("household_types") or {}
    _ht_label = {"1_person": "1인", "2_person": "2인", "3_person": "3인", "4_over": "4인+"}
    household_rows = (
        [{"label": _ht_label.get(k, k), "ratio": v, "estimated": True} for k, v in ht.items()]
        if isinstance(ht, dict) else []
    )

    return {
        "summary": {
            "total_population": pop.get("total_population") or None,
            "household_count": pop.get("household_count") or None,
            "avg_household_size": pop.get("avg_household_size") or None,
        },
        "age_distribution": age_rows,
        "household_types": household_rows,
        "migration": {
            "total_inflow": mig.get("total_inflow") if mig_src is not None else None,
            "total_outflow": mig.get("total_outflow") if mig_src is not None else None,
            "net_migration": mig.get("net_migration") if mig_src is not None else None,
        },
        "source": "통계청 인구주택총조사 / 국내인구이동통계",
        # population 자체의 출처. 미선택(호출 안 함)이라 None 이면 정직하게 unavailable.
        "data_source": pop_src or "unavailable",
        "migration_data_source": mig_src or "unavailable",
    }


def _build_income_block(demographics: dict[str, Any] | None) -> dict[str, Any] | None:
    """demographics.macro_income → 소득 블록. 미선택(data_source 없음)이면 None(키 생략).

    KOSIS 국세청 표는 평균 총급여만 산출 가능(중위는 평균×0.85 추정). 인원/총급여 원수치는
    모델에 보존되지 않으므로 basis.persons/total_salary_10k 는 None(가짜 금지). bracket_ratio 미제공→null.
    """
    mi = (demographics or {}).get("macro_income") or {}
    src = mi.get("data_source")
    if src is None:
        return None
    avg = mi.get("avg_income_10k") or None
    med = mi.get("median_income_10k") or None
    # income_bracket_ratio 가 비어 있으면(미제공) 정직 null.
    bracket = mi.get("income_bracket_ratio") or None
    return {
        "avg_income_10k": avg,
        "median_income_10k": med,
        # 중위는 평균×0.85 결정론 추정값 — 실측 아님을 명시.
        "median_estimated": True,
        # 인원/총급여 원수치는 모델에 보존되지 않음(KosisClient 내부 계산값) → 정직 None.
        "basis": {"persons": None, "total_salary_10k": None},
        "bracket_ratio": bracket,
        "source": "국세청 근로소득",
        "data_source": src,
    }


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

        # ★MOLIT LAWD_CD 는 시군구 5자리. 10자리 법정동/bcode 가 들어오면 [:5]로 정규화하지 않으면
        #   실거래가 전부 빈 결과가 되어 trade·comparable_trade(적정분양가 앵커)가 통째로 누락된다.
        lawd_cd = (lawd_cd or "")[:5]
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
        # 항목 단위 게이팅: 프론트(P1)가 보내는 세부 선택. 없을 수도 있음(하위호환).
        #   detail = {pop_age, pop_household, pop_migration, income_avg, income_basis}
        #   detail 이 제공되면 항목 기준으로, 없으면 기존 분류 boolean(use_sgis/use_kosis)으로 폴백한다.
        #   → detail 미전달 시 기존 호출 동작 100% 무회귀.
        detail = options.get("detail") or {}

        def _want(key: str, fallback: bool) -> bool:
            """detail 에 항목이 명시되면 그 값, 없으면 fallback(분류 boolean)."""
            return bool(detail[key]) if key in detail else fallback

        # 인구규모/연령/가구원수는 SGIS 단일 호출이라 연령·가구 둘 중 하나라도 ON 이면 호출.
        want_pop = (
            (_want("pop_age", use_sgis) or _want("pop_household", use_sgis))
            if ("pop_age" in detail or "pop_household" in detail)
            else use_sgis
        )
        # 인구이동: detail.pop_migration 명시 시 그 값, 비면 기존 use_sgis/use_kosis 폴백.
        want_mig = _want("pop_migration", use_sgis or use_kosis)
        # 소득: detail.income_avg 또는 income_basis 명시 시 그 값, 비면 기존 use_kosis 폴백.
        want_inc = (
            (_want("income_avg", use_kosis) or _want("income_basis", use_kosis))
            if ("income_avg" in detail or "income_basis" in detail)
            else use_kosis
        )

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
        if want_pop or want_mig or want_inc:
            try:
                # use_mock=None: 클라이언트가 키 존재 여부로 실연동/폴백을 자동 결정한다.
                #   (과거 use_mock=True 하드코딩으로 키가 있어도 항상 Mock만 나오던 G1 결함 제거)
                #   키가 있으면 실데이터 시도→data_source='live', 없으면 폴백→'fallback'/'mock'/'unavailable'.
                # 통합시(수원/성남 등) 표기차 흡수: KOSIS=시 단위, SGIS=시+구.
                kosis_nm, sgis_nm = _extract_region_keys(address)

                # 항목 단위 게이팅: 미선택 항목은 provider 호출을 생략해 불필요한 외부 API
                #   호출을 줄인다(빈 메타 dict 반환 → 모델 기본값으로 unavailable 표기됨).
                async def fetch_mig():
                    if not want_mig:
                        return {"target_adm_cd": lawd_cd, "year": cur_year}
                    # I2: 인구이동은 SGIS 미제공 → KOSIS 「시군구별 이동자수」로 대상 시군구의
                    #     총전입·총전출·순이동(유입세)을 산출. 주소에서 시군구명을 추출해 식별한다.
                    od = await kosis.get_migration_od(lawd_cd[:5], cur_year, region_name=kosis_nm)
                    if od.get("data_source") == "live":
                        return od
                    # KOSIS 미확정/실패 시 SGIS 정직 폴백(가짜 금지).
                    return await sgis.get_migration_stats(lawd_cd, cur_year) if use_sgis else od
                async def fetch_pop():
                    if not want_pop:
                        return {"target_adm_cd": lawd_cd, "year": cur_year}
                    return await sgis.get_population_stats(
                        lawd_cd, cur_year, region_name=sgis_nm)
                async def fetch_inc():
                    if not want_inc:
                        return {"sigungu_cd": lawd_cd[:5], "year": cur_year}
                    return await kosis.get_macro_income_stats(
                        lawd_cd[:5], cur_year, region_name=kosis_nm)

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

        # ── 단일 소비원(raw_data + analysis) 구성 ──
        # 프론트(P3)·export(P4)가 dict 를 재가공하지 않도록 표(row 배열)로 평탄화한다.
        # 미선택 분류 처리 규칙(일관): population/income 블록은 '미선택(provider 호출 안 함)'이면
        #   키 자체를 생략하고, '선택했으나 provider 실패'면 키는 두되 data_source 로 정직 표기한다.
        raw_data: dict[str, Any] = {
            "real_estate": {
                "trade_table": _build_trade_table(stats["trade"]),
                "rent_table": _build_rent_table(stats["rent"]),
                "trend_series": _build_trend_series(stats.get("apt_trend") or []),
                "source": "국토교통부 실거래가",
                "data_source": "live",
            },
        }
        _pop_block = _build_population_block(demographics)
        if _pop_block is not None:  # 미선택이면 키 생략(정직)
            raw_data["population"] = _pop_block
        _inc_block = _build_income_block(demographics)
        if _inc_block is not None:  # 미선택이면 키 생략(정직)
            raw_data["income"] = _inc_block

        # analysis: 기존 산출을 묶기만(중복 계산 금지, 같은 객체 참조).
        analysis: dict[str, Any] = {
            "narrative": narrative,
            "feasibility": feasibility,
            "pricing_band": pricing_band,
            "unit_mix": unit_mix_recommendation,
            "target_persona": (narrative or {}).get("target_persona"),
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
            # ── 신규(하위호환): 단일 소비원 ──
            "raw_data": raw_data,
            "analysis": analysis,
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
