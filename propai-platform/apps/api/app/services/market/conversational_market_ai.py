"""
대화형 시장분석 AI — 자연어 질문으로 부동산 시장 데이터를 즉시 분석.
Deepblocks ChatDB 벤치마크.

분석 텍스트는 LLM 우선(get_llm 단일출처) — MOLIT 실데이터만 근거로 생성하며,
API 키 부재·호출 실패 시 템플릿 분석으로 폴백하고 `analysis_source`로 출처를 표기.
"""
import json
import logging
import re
from typing import Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ConversationalMarketAI:
    """자연어 부동산 시장 분석 에이전트."""

    # Predefined market analysis tools
    AVAILABLE_TOOLS = {
        "실거래가_조회": "특정 지역/기간의 아파트 실거래가를 조회합니다.",
        "시세_추이": "특정 지역의 시세 변동 추이를 분석합니다.",
        "공시지가_조회": "특정 필지의 공시지가를 조회합니다.",
        "수급_분석": "특정 지역의 공급/수요 현황을 분석합니다.",
        "인구_통계": "특정 지역의 인구 구조를 분석합니다.",
        "비교_분석": "2개 이상 지역의 시장 데이터를 비교합니다.",
    }

    async def analyze(self, query: str, context: Optional[dict] = None) -> dict:
        """자연어 질문을 분석하여 적절한 데이터를 조회하고 답변을 생성."""

        # Step 1: Parse intent from query
        intent = self._parse_intent(query)

        # Step 2: Extract parameters
        params = self._extract_params(query, context)

        # Step 3: Execute data retrieval
        data = await self._retrieve_data(intent, params)

        # Step 4: Generate analysis — LLM 우선, 실패·키 부재 시 템플릿 폴백
        analysis = None
        analysis_source = "template"
        if data.get("statistics"):
            # 통계(실데이터)가 없으면 LLM을 호출하지 않는다 — 근거 없는 생성 방지
            analysis = await self._generate_llm_analysis(query, intent, data, params)
            if analysis is not None:
                analysis_source = "llm"
        if analysis is None:
            analysis = self._generate_analysis(query, intent, data, params)

        return {
            "query": query,
            "intent": intent,
            "parameters": params,
            "data": data,
            "analysis": analysis,
            "analysis_source": analysis_source,
            "timestamp": datetime.now().isoformat(),
            "tools_used": [intent["tool"]],
        }

    def _parse_intent(self, query: str) -> dict:
        """질문에서 의도를 파악."""
        query_lower = query.lower()

        if any(kw in query_lower for kw in ["추이", "변동", "트렌드", "상승", "하락"]):
            return {"tool": "시세_추이", "type": "trend"}
        elif any(kw in query_lower for kw in ["비교", "대비", "vs"]):
            return {"tool": "비교_분석", "type": "comparison"}
        elif any(kw in query_lower for kw in ["공시", "공시지가", "표준지"]):
            return {"tool": "공시지가_조회", "type": "official_price"}
        elif any(kw in query_lower for kw in ["인구", "세대", "가구"]):
            return {"tool": "인구_통계", "type": "demographics"}
        elif any(kw in query_lower for kw in ["공급", "수요", "입주", "미분양"]):
            return {"tool": "수급_분석", "type": "supply_demand"}
        else:
            return {"tool": "실거래가_조회", "type": "transactions"}

    def _extract_params(self, query: str, context: Optional[dict]) -> dict:
        """질문에서 지역, 기간, 면적 등 파라미터를 추출."""
        params: dict = {}

        # Extract region (시/구/동)
        regions = {
            "강남": "11680", "서초": "11650", "송파": "11710",
            "마포": "11440", "용산": "11170", "성동": "11200",
            "강서": "11500", "영등포": "11560", "관악": "11620",
            "수원": "41110", "성남": "41130", "고양": "41280",
            "부산": "26000", "대구": "27000", "인천": "28000",
        }
        for name, code in regions.items():
            if name in query:
                params["region_name"] = name
                params["lawd_cd"] = code
                break

        # Extract area (면적)
        area_match = re.search(r"(\d+)\s*(?:m²|㎡|제곱미터|평)", query)
        if area_match:
            params["area_filter"] = int(area_match.group(1))

        # Extract period
        month_match = re.search(r"(\d+)\s*(?:개월|달)", query)
        if month_match:
            params["months"] = int(month_match.group(1))
        else:
            params["months"] = 6  # default 6 months

        # Use context if available — bcode/pnu 에서 LAWD_CD(시군구 5자리) 도출 포함
        if context:
            if not params.get("lawd_cd"):
                lc = context.get("lawd_cd")
                if not lc:  # 부지분석 컨텍스트는 보통 bcode(법정동10자리)/pnu(19자리)를 가진다 → 앞 5자리=시군구
                    src = str(context.get("bcode") or context.get("pnu") or "")
                    if len(src) >= 5 and src[:5].isdigit():
                        lc = src[:5]
                if lc:
                    params["lawd_cd"] = str(lc)[:5]
            if not params.get("region_name") and context.get("address"):
                params["region_name"] = context["address"]

        return params

    async def _retrieve_data(self, intent: dict, params: dict) -> dict:
        """의도에 맞는 데이터를 공공 API에서 조회."""
        from apps.api.app.services.external_api.molit_service import MOLITService

        tool = intent["tool"]
        data: dict = {"source": "국토교통부 실거래가 공개시스템", "records": []}

        if tool in ("실거래가_조회", "시세_추이"):
            lawd_cd = params.get("lawd_cd")
            if not lawd_cd:
                # 지역(시군구) 미특정 시 강남(11680) 등으로 폴백하지 않는다 — 무관 지역 데이터
                # 반환(할루시네이션)을 차단하고 정직하게 미특정을 고지한다.
                data["total_count"] = 0
                data["error"] = "지역(시군구)을 특정하지 못했습니다. 주소나 지역명을 포함해 다시 질문해 주세요."
                return data
            months = params.get("months", 6)

            molit = MOLITService()
            now = datetime.now()
            all_trades: list = []

            for m in range(months):
                target = now - timedelta(days=30 * m)
                deal_ym = target.strftime("%Y%m")
                try:
                    trades = await molit.get_apt_transactions(lawd_cd, deal_ym)
                    if trades:
                        all_trades.extend(trades)
                except Exception as e:
                    logger.warning("MOLIT 조회 실패 (%s): %s", deal_ym, e)

            # Filter by area if specified
            area_filter = params.get("area_filter")
            if area_filter and all_trades:
                all_trades = [
                    t for t in all_trades
                    if abs((t.get("area_m2") or t.get("area_sqm") or 0) - area_filter) < 10
                ]

            data["records"] = all_trades[:100]  # Limit
            data["total_count"] = len(all_trades)
            data["period"] = f"최근 {months}개월"

            if all_trades:
                prices = [
                    (t.get("price_10k_won") or t.get("price_10k") or 0)
                    for t in all_trades
                    if (t.get("price_10k_won") or t.get("price_10k") or 0) > 0
                ]
                if prices:
                    data["statistics"] = {
                        "avg_price_10k": round(sum(prices) / len(prices)),
                        "min_price_10k": min(prices),
                        "max_price_10k": max(prices),
                        "median_price_10k": sorted(prices)[len(prices) // 2],
                        "count": len(prices),
                    }

        return data

    async def _generate_llm_analysis(
        self, query: str, intent: dict, data: dict, params: dict
    ) -> Optional[dict]:
        """LLM으로 MOLIT 실거래 데이터 근거 한정 분석을 생성.

        API 키 부재(get_llm ValueError)·호출 실패·JSON 파싱 실패 시 None을
        반환하여 호출부가 템플릿 분석(_generate_analysis)으로 폴백하게 한다.
        반환 dict 키는 템플릿 분석과 동일(summary/details/chart_data/recommendations).
        """
        try:
            from app.services.ai.llm_provider import get_llm
            from langchain_core.messages import HumanMessage, SystemMessage

            llm = get_llm(timeout=30, max_tokens=1200)
        except Exception as e:
            logger.info("LLM 사용 불가 — 템플릿 분석 폴백: %s", str(e)[:80])
            return None

        # chart_data는 LLM이 아닌 실거래 레코드에서 직접 계산한다(수치 변조 방지)
        chart_data = self._generate_monthly_chart(data.get("records", []))
        evidence = {
            "region": params.get("region_name", "해당 지역"),
            "period": data.get("period", ""),
            "total_count": data.get("total_count", 0),
            "statistics_10k_won": data.get("statistics", {}),
            "monthly_avg_price_10k": chart_data,
            "intent": intent.get("type", ""),
        }

        sys_msg = (
            "당신은 부동산 시장분석 전문가다. 아래 국토교통부(MOLIT) 실거래 "
            "데이터만 근거로 한국어 JSON으로 답하라. "
            "키: summary(핵심 요약 2~3문장), details(데이터 해석 1~2문장), "
            "recommendations(실행 제안 2~3개 문자열 배열). "
            "가격 단위는 만원이다. 데이터에 없는 수치는 만들지 말 것."
        )
        usr_msg = (
            f"## 질문\n{query}\n\n"
            f"## 실거래 데이터\n{json.dumps(evidence, ensure_ascii=False)[:3500]}"
        )

        try:
            resp = await llm.ainvoke(
                [SystemMessage(content=sys_msg), HumanMessage(content=usr_msg)]
            )
            # 계측: BaseInterpreter 밖 직접 호출도 동일하게 토큰·과금 기록(best-effort)
            from app.services.ai.base_interpreter import record_llm_response_billing
            await record_llm_response_billing(llm, resp, service="market_ai")
            raw = resp.content if hasattr(resp, "content") else str(resp)
            txt = str(raw).strip()
            if txt.startswith("```"):
                txt = (
                    txt.split("```")[1].lstrip("json").strip()
                    if "```" in txt[3:]
                    else txt.strip("`")
                )
            parsed = json.loads(txt)
            summary = parsed.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                return None

            count = data.get("total_count", 0)
            return {
                "summary": summary,
                "details": parsed.get("details")
                or f"데이터 출처: 국토교통부 실거래가 공개시스템. 총 {count}건 분석.",
                "chart_data": chart_data,
                "recommendations": parsed.get("recommendations") or [],
            }
        except Exception as e:
            logger.warning("LLM 시장분석 실패 — 템플릿 폴백: %s", str(e)[:80])
            return None

    def _generate_analysis(
        self, query: str, intent: dict, data: dict, params: dict
    ) -> dict:
        """데이터 기반 분석 텍스트 생성 (템플릿 폴백 경로)."""
        region = params.get("region_name", "해당 지역")
        months = params.get("months", 6)
        stats = data.get("statistics", {})
        count = data.get("total_count", 0)

        if not stats:
            return {
                "summary": f"{region} 지역의 최근 {months}개월 거래 데이터를 찾을 수 없습니다.",
                "details": "MOLIT API 키를 확인하거나, 다른 지역/기간으로 조회해보세요.",
                "chart_data": None,
            }

        avg = stats.get("avg_price_10k", 0)
        avg_억 = round(avg / 10000, 1) if avg > 10000 else f"{avg}만"

        summary = f"{region} 지역 최근 {months}개월간 총 {count}건 거래. "
        summary += (
            f"평균 거래가 {avg_억}억원 "
            f"(최저 {stats.get('min_price_10k', 0)}만~"
            f"최고 {stats.get('max_price_10k', 0)}만)."
        )

        # Generate simple chart data (monthly averages)
        chart_data = self._generate_monthly_chart(data.get("records", []))

        return {
            "summary": summary,
            "details": f"데이터 출처: 국토교통부 실거래가 공개시스템. 총 {count}건 분석.",
            "chart_data": chart_data,
            "recommendations": [
                f"{region} 평균 시세 기준 분양가 책정 시 {avg_억}억원 수준 참고",
                f"거래 건수 {count}건으로 {'활발한' if count > 50 else '보통 수준의'} 시장 활동",
            ],
        }

    def _generate_monthly_chart(self, records: list) -> list:
        """월별 평균 가격 차트 데이터 생성."""
        monthly: dict[str, list] = {}
        for r in records:
            ym = str(r.get("deal_date") or "").replace("-", "")[:6]
            price = r.get("price_10k_won") or r.get("price_10k") or 0
            if ym and price > 0:
                if ym not in monthly:
                    monthly[ym] = []
                monthly[ym].append(price)

        chart = []
        for ym in sorted(monthly.keys()):
            prices = monthly[ym]
            chart.append({
                "month": f"{ym[:4]}.{ym[4:]}",
                "avg_price_10k": round(sum(prices) / len(prices)),
                "count": len(prices),
            })

        return chart
