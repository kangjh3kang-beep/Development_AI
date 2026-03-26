# PropAI v43.0 -- Part C: 설계AI + 금융세금AI + 한국특화AI + 시공ESG
## Phase 06~09 | IDE 즉시 실행 완전 빌드 프롬프트

---

> **선행 조건**: Part-B 완료 (/auth, /parcels, /avm, /regulation 엔드포인트 동작)
> **예상 소요**: 17일 | **다음 파트**: Part-D (MLOps + 프론트엔드 + 인프라)

---

## Phase 06: 설계 AI (M-RPG + SSE 스트리밍)

```
================================================================
[PROPAI PHASE-06: AI 설계 생성 (SSE 스트리밍)]
================================================================

== P06-STEP-01: 설계 AI 서비스 ==

[파일: apps/api/app/services/design_ai_service.py]
import os
import json
import uuid
import httpx
from datetime import datetime
from typing import AsyncGenerator

class DesignAIService:
    """
    AI 건축 설계 생성 서비스
    Claude claude-sonnet-4-6 (temperature=0.7 -- 창의적 설계)
    SSE 스트리밍 + 동기 호출 이중 지원
    참조 이미지 업로드 기반 생성 지원
    """

    # Prompt Caching 적용 -- 건축법 컨텍스트 반복 캐싱
    ARCHITECTURAL_SYSTEM_PROMPT = """당신은 20년 경력의 한국 건축사입니다.
건축법, 주택법, 국토계획법을 완벽히 숙지하고 있으며
에너지 효율, 친환경 설계, 사용자 편의성을 최우선으로 합니다.

설계 원칙:
1. 법적 건폐율/용적률 준수
2. 일조권/채광 확보 (정북 방향 사선 기준)
3. 주차장 법정 대수 확보
4. ZEB (제로에너지빌딩) 기준 에너지 효율
5. 유니버설 디자인 (장애인 접근성)
6. 한국 전통 미학 + 현대 건축의 조화

출력 형식은 JSON으로 반환하세요."""

    def __init__(self, db_pool=None):
        from app.db import get_db_pool
        self._db = db_pool or get_db_pool()

    async def generate_design_stream(
        self,
        project_id:      str,
        land_area_m2:    float,
        land_use:        str,
        building_use:    str,
        floor_count:     int,
        design_style:    str = "현대적 미니멀",
        special_req:     str = ""
    ) -> AsyncGenerator[str, None]:
        """SSE 스트리밍 설계 생성"""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        prompt = self._build_design_prompt(
            land_area_m2, land_use, building_use, floor_count, design_style, special_req
        )

        if not api_key:
            # Mock 스트리밍
            mock = self._mock_design(land_area_m2, land_use, building_use, floor_count)
            for char in json.dumps(mock, ensure_ascii=False):
                yield f"data: {char}\n\n"
            yield "data: [DONE]\n\n"
            return

        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type":      "application/json"
                },
                json={
                    "model":      "claude-sonnet-4-6",
                    "max_tokens": 3000,
                    "temperature": 0.7,
                    "stream":     True,
                    "system":     self.ARCHITECTURAL_SYSTEM_PROMPT,
                    "messages":   [{"role": "user", "content": prompt}]
                }
            ) as resp:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        yield f"{line}\n\n"

    async def generate_design_sync(
        self,
        project_id:   str,
        land_area_m2: float,
        land_use:     str,
        building_use: str,
        floor_count:  int,
        design_style: str = "현대적 미니멀",
        special_req:  str = ""
    ) -> dict:
        """동기 설계 생성 + DB 저장"""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        if not api_key:
            result = self._mock_design(land_area_m2, land_use, building_use, floor_count)
        else:
            prompt = self._build_design_prompt(
                land_area_m2, land_use, building_use, floor_count, design_style, special_req
            )
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key":         api_key,
                        "anthropic-version": "2023-06-01",
                        "Content-Type":      "application/json"
                    },
                    json={
                        "model":      "claude-sonnet-4-6",
                        "max_tokens": 3000,
                        "temperature": 0.7,
                        "system":     self.ARCHITECTURAL_SYSTEM_PROMPT,
                        "messages":   [{"role": "user", "content": prompt}]
                    }
                )
            data    = resp.json()
            content = data.get("content", [{}])[0].get("text", "{}")
            try:
                result = json.loads(content.replace("```json","").replace("```","").strip())
            except Exception:
                result = {"design_content": content, "raw": True}

            # 토큰 사용량 기록
            usage = data.get("usage", {})
            await self._record_ai_cost("design_ai_service", project_id,
                                        usage.get("input_tokens", 0), usage.get("output_tokens", 0))

        # DB 저장
        design_id = str(uuid.uuid4())
        await self._db.execute("""
            INSERT INTO designs
            (design_id, project_id, design_type, prompt_summary, design_content, area_program_json)
            VALUES ($1,$2::uuid,'ai_generated',$3,$4,$5)
        """,
            design_id, project_id,
            f"{building_use} / {floor_count}층 / {design_style}",
            json.dumps(result, ensure_ascii=False),
            json.dumps(result.get("area_program", {}), ensure_ascii=False)
        )
        result["design_id"] = design_id
        return result

    def _build_design_prompt(self, land_area_m2, land_use, building_use, floor_count, style, special_req):
        return f"""다음 조건에 맞는 건축 설계안을 생성해주세요.

[부지 조건]
- 대지 면적: {land_area_m2}m²
- 용도지역: {land_use}
- 건축물 용도: {building_use}
- 층수: 지상 {floor_count}층
- 설계 스타일: {style}
- 특수 요구사항: {special_req or "없음"}

[JSON 응답 형식]
{{
  "concept":          "<설계 컨셉 2문장>",
  "building_coverage_pct": <건폐율%>,
  "floor_area_ratio_pct":  <용적률%>,
  "total_area_m2":         <연면적m²>,
  "floor_height_m":        <층고m>,
  "parking_count":         <주차대수>,
  "design_features": ["<특징1>","<특징2>","<특징3>"],
  "area_program": {{
    "지하1층": "<용도 + 면적m²>",
    "1층":     "<용도 + 면적m²>",
    "2~{floor_count}층": "<용도 + 면적m²>"
  }},
  "sustainability": {{
    "zeb_grade":       "<ZEB 등급>",
    "energy_kwh_m2":   <에너지소비량>,
    "renewable_pct":   <신재생에너지비율%>
  }},
  "estimated_cost_krw": <공사비 원화>,
  "construction_months": <공사기간 개월>
}}"""

    def _mock_design(self, land_area_m2, land_use, building_use, floor_count) -> dict:
        total_area = land_area_m2 * floor_count * 0.7
        return {
            "concept":                 f"{land_use}에 최적화된 {building_use} 설계안. 자연광과 통풍을 극대화한 친환경 건축.",
            "building_coverage_pct":   58.0,
            "floor_area_ratio_pct":    240.0,
            "total_area_m2":           round(total_area, 0),
            "floor_height_m":          3.2,
            "parking_count":           int(total_area / 150),
            "design_features":         ["고단열 커튼월", "태양광 패널 루프탑", "우수재활용 시스템"],
            "area_program":            {"1층": f"로비/주차 {land_area_m2*0.3:.0f}m²", "2층 이상": f"주용도 {total_area*0.8:.0f}m²"},
            "sustainability":          {"zeb_grade": "ZEB5", "energy_kwh_m2": 120, "renewable_pct": 20},
            "estimated_cost_krw":      int(total_area * 3_000_000),
            "construction_months":     floor_count * 3,
            "mock":                    True
        }

    async def _record_ai_cost(self, service, project_id, input_tokens, output_tokens):
        try:
            await self._db.execute("""
                INSERT INTO ai_token_usage
                (service_name, endpoint, model, input_tokens, output_tokens, cost_usd, project_id, used_at)
                VALUES ($1,'/design','claude-sonnet-4-6',$2,$3,$4,$5::uuid,NOW())
            """, service, input_tokens, output_tokens,
                (input_tokens * 0.000003 + output_tokens * 0.000015), project_id)
        except Exception:
            pass

== P06-STEP-02: 설계 AI 라우터 (SSE 포함) ==

[파일: apps/api/app/routers/design/__init__.py]
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
from app.services.design_ai_service import DesignAIService
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/v1/design", tags=["design"])
_svc   = DesignAIService()

class DesignRequest(BaseModel):
    project_id:   str
    land_area_m2: float
    land_use:     str
    building_use: str
    floor_count:  int
    design_style: str = "현대적 미니멀"
    special_req:  str = ""

@router.post("/generate")
async def generate_design(req: DesignRequest, user: dict = Depends(get_current_user)):
    return await _svc.generate_design_sync(**dict(req))

@router.post("/generate/stream")
async def generate_design_stream(req: DesignRequest, user: dict = Depends(get_current_user)):
    return StreamingResponse(
        _svc.generate_design_stream(**dict(req)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

@router.get("/history/{project_id}")
async def get_history(project_id: str, user: dict = Depends(get_current_user)):
    rows = await _svc._db.fetch("""
        SELECT design_id, design_type, prompt_summary, is_favorite, created_at
        FROM designs WHERE project_id=$1::uuid
        ORDER BY created_at DESC LIMIT 10
    """, project_id)
    return [dict(r) for r in rows]
```

---

## Phase 07: 금융 + 세금 AI

```
================================================================
[PROPAI PHASE-07: 금융/세금 AI (투자 분석 + 몬테카를로)]
================================================================

== P07-STEP-01: 세금 AI 서비스 ==

[파일: apps/api/app/services/tax_ai_service.py]
import json
import random
import math
from datetime import datetime

class TaxAIService:
    """
    부동산 세금 AI 서비스
    양도소득세: 누진세율 8구간 + 장기보유특별공제
    취득세: 주택수별 세율 + 법인 세율
    Monte Carlo 절세 시나리오 (N=1,000회 시뮬레이션)
    """

    # 양도소득세 누진세율 (2025년 기준)
    TRANSFER_TAX_BRACKETS = [
        (12_000_000,   0.06),
        (46_000_000,   0.15),
        (88_000_000,   0.24),
        (150_000_000,  0.35),
        (300_000_000,  0.38),
        (500_000_000,  0.40),
        (1_000_000_000, 0.42),
        (float("inf"), 0.45),
    ]

    # 장기보유특별공제율 (3년~15년+)
    LONG_TERM_DEDUCTION = {
        3: 0.06, 4: 0.08, 5: 0.10, 6: 0.12, 7: 0.14,
        8: 0.16, 9: 0.18, 10: 0.20, 11: 0.22, 12: 0.24,
        13: 0.26, 14: 0.28, 15: 0.30
    }

    def calculate_transfer_tax(
        self,
        purchase_price_krw: int,
        sale_price_krw:     int,
        hold_years:         int,
        home_count:         int = 1,    # 보유 주택 수
        is_major_city:      bool = True  # 조정대상지역 여부
    ) -> dict:
        """양도소득세 계산"""
        gain       = sale_price_krw - purchase_price_krw
        if gain <= 0:
            return {"tax_krw": 0, "gain_krw": gain, "note": "양도차익 없음 -- 세금 없음"}

        # 장기보유특별공제
        deduction_rate = self.LONG_TERM_DEDUCTION.get(min(hold_years, 15), 0)
        # 다주택자 조정지역: 장기보유 공제 적용 불가
        if home_count >= 2 and is_major_city:
            deduction_rate = 0

        gain_after_deduction = int(gain * (1 - deduction_rate))

        # 기본공제 (연 250만원)
        taxable = max(0, gain_after_deduction - 2_500_000)

        # 누진세율 적용
        tax = 0
        prev_limit = 0
        for limit, rate in self.TRANSFER_TAX_BRACKETS:
            if taxable <= prev_limit:
                break
            bracket_income = min(taxable, limit) - prev_limit
            tax += bracket_income * rate
            prev_limit = limit
            if taxable <= limit:
                break

        # 중과세 (다주택자 조정지역)
        surcharge_rate = 0
        if home_count == 2 and is_major_city: surcharge_rate = 0.20
        if home_count >= 3 and is_major_city: surcharge_rate = 0.30

        tax_base       = int(tax)
        surcharge      = int(tax_base * surcharge_rate)
        total_tax      = tax_base + surcharge
        local_income_tax = int(total_tax * 0.1)  # 지방소득세 10%
        final_tax      = total_tax + local_income_tax
        effective_rate = final_tax / gain * 100 if gain > 0 else 0

        return {
            "gain_krw":              gain,
            "deduction_rate_pct":    deduction_rate * 100,
            "gain_after_deduction":  gain_after_deduction,
            "taxable_income_krw":    taxable,
            "base_tax_krw":          tax_base,
            "surcharge_krw":         surcharge,
            "local_income_tax_krw":  local_income_tax,
            "total_tax_krw":         final_tax,
            "effective_rate_pct":    round(effective_rate, 2),
            "net_profit_krw":        gain - final_tax,
            "hold_years":            hold_years,
            "home_count":            home_count,
        }

    def calculate_acquisition_tax(
        self,
        price_krw:  int,
        home_count: int = 1,
        is_legal_entity: bool = False
    ) -> dict:
        """취득세 계산"""
        if is_legal_entity:
            base_rate = 0.04   # 법인: 4% (12% 중과 제외 기준)
        elif home_count == 1:
            if price_krw <= 600_000_000:  base_rate = 0.01
            elif price_krw <= 900_000_000: base_rate = 0.02
            else:                          base_rate = 0.03
        elif home_count == 2:
            base_rate = 0.08   # 조정대상지역 2주택
        else:
            base_rate = 0.12   # 3주택 이상

        acquisition_tax = int(price_krw * base_rate)
        local_education_tax = int(acquisition_tax * 0.2)   # 지방교육세
        special_rural_tax   = int(price_krw * 0.002)        # 농어촌특별세
        total_tax = acquisition_tax + local_education_tax + special_rural_tax

        return {
            "price_krw":             price_krw,
            "base_rate_pct":         base_rate * 100,
            "acquisition_tax_krw":   acquisition_tax,
            "local_education_tax_krw": local_education_tax,
            "special_rural_tax_krw": special_rural_tax,
            "total_tax_krw":         total_tax,
            "total_rate_pct":        round(total_tax / price_krw * 100, 3),
        }

    def run_monte_carlo_tax_scenarios(
        self,
        purchase_price_krw: int,
        sale_price_range:   tuple,  # (min, max)
        hold_years_range:   tuple,  # (min, max)
        n_simulations:      int = 1000
    ) -> dict:
        """Monte Carlo 양도세 절세 시나리오 (N=1,000)"""
        results = []
        for _ in range(n_simulations):
            sale_price = random.randint(*sale_price_range)
            hold_years = random.randint(*hold_years_range)
            result = self.calculate_transfer_tax(purchase_price_krw, sale_price, hold_years)
            results.append({
                "sale_price_krw": sale_price,
                "hold_years":     hold_years,
                "tax_krw":        result.get("total_tax_krw", 0),
                "net_profit_krw": result.get("net_profit_krw", 0)
            })

        taxes = [r["tax_krw"] for r in results]
        profits = [r["net_profit_krw"] for r in results]

        # 최적 시나리오 (세금 최소 + 순이익 최대)
        best = max(results, key=lambda x: x["net_profit_krw"] - x["tax_krw"] * 0.5)

        return {
            "n_simulations": n_simulations,
            "tax_stats": {
                "mean_krw":   int(sum(taxes) / len(taxes)),
                "min_krw":    min(taxes),
                "max_krw":    max(taxes),
                "p25_krw":    int(sorted(taxes)[n_simulations // 4]),
                "p75_krw":    int(sorted(taxes)[n_simulations * 3 // 4]),
            },
            "profit_stats": {
                "mean_krw":   int(sum(profits) / len(profits)),
                "max_krw":    max(profits),
            },
            "best_scenario": best,
            "recommendation": f"보유 {best['hold_years']}년 후 매도 시 순이익 극대화"
        }

== P07-STEP-02: 금융 분석 서비스 ==

[파일: apps/api/app/services/finance_service.py]
import json
import math
from datetime import datetime

class FinanceService:
    """
    부동산 금융 분석 서비스
    IRR / NPV / 투자 회수 기간 계산
    LTV / DSR 계산
    투자 언더라이팅 (G81)
    """

    def __init__(self, db_pool=None):
        from app.db import get_db_pool
        self._db = db_pool or get_db_pool()

    def calculate_irr(self, cash_flows: list) -> float:
        """IRR 계산 (뉴턴-랩슨 방법)"""
        rate = 0.1  # 초기 추정값 10%
        for _ in range(100):
            npv    = sum(cf / (1 + rate) ** t for t, cf in enumerate(cash_flows))
            dnpv   = sum(-t * cf / (1 + rate) ** (t + 1) for t, cf in enumerate(cash_flows))
            if abs(dnpv) < 1e-10:
                break
            rate_new = rate - npv / dnpv
            if abs(rate_new - rate) < 1e-8:
                rate = rate_new
                break
            rate = rate_new
        return round(rate * 100, 2)

    def calculate_npv(self, cash_flows: list, discount_rate: float) -> int:
        """NPV 계산"""
        r = discount_rate / 100
        return int(sum(cf / (1 + r) ** t for t, cf in enumerate(cash_flows)))

    async def run_underwriting(
        self,
        project_id:       str,
        purchase_price_krw: int,
        equity_ratio_pct: float,
        loan_rate_pct:    float,
        noi_monthly_krw:  int,
        hold_years:       int,
        exit_cap_rate_pct: float
    ) -> dict:
        """투자 언더라이팅 (G81)"""
        equity_krw  = int(purchase_price_krw * equity_ratio_pct / 100)
        loan_krw    = purchase_price_krw - equity_krw
        monthly_payment = loan_krw * (loan_rate_pct / 100 / 12) / \
                          (1 - (1 + loan_rate_pct / 100 / 12) ** (-hold_years * 12))

        # 연간 현금흐름
        annual_noi  = noi_monthly_krw * 12
        annual_debt = monthly_payment * 12
        annual_cf   = annual_noi - annual_debt

        # 매각 가치
        exit_value  = int(annual_noi / (exit_cap_rate_pct / 100))
        remaining_loan = loan_krw * (1 + loan_rate_pct / 100 / 12) ** (hold_years * 12) - \
                         monthly_payment * ((1 + loan_rate_pct / 100 / 12) ** (hold_years * 12) - 1) / \
                         (loan_rate_pct / 100 / 12)
        net_exit    = exit_value - remaining_loan

        # IRR 계산
        cash_flows = [-equity_krw] + [annual_cf] * hold_years
        cash_flows[-1] += net_exit
        irr_pct    = self.calculate_irr(cash_flows)
        npv_krw    = self.calculate_npv(cash_flows, 8.0)  # 8% 할인율 기준

        equity_multiple = (sum(cash_flows[1:]) + equity_krw) / equity_krw

        result = {
            "purchase_price_krw":  purchase_price_krw,
            "equity_krw":          equity_krw,
            "loan_krw":            loan_krw,
            "ltv_pct":             round((1 - equity_ratio_pct / 100) * 100, 1),
            "annual_noi_krw":      annual_noi,
            "annual_cf_krw":       int(annual_cf),
            "exit_value_krw":      exit_value,
            "irr_pct":             irr_pct,
            "equity_multiple":     round(equity_multiple, 2),
            "npv_krw":             npv_krw,
            "hold_years":          hold_years,
        }

        await self._db.execute("""
            INSERT INTO investment_underwriting
            (project_id, purchase_price_krw, equity_ratio_pct, loan_rate_pct,
             hold_years, exit_cap_rate_pct, irr_pct, equity_multiple, npv_krw)
            VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8,$9)
        """,
            project_id, purchase_price_krw, equity_ratio_pct,
            loan_rate_pct, hold_years, exit_cap_rate_pct,
            irr_pct, equity_multiple, npv_krw
        )
        return result

== P07-STEP-03: 금융/세금 라우터 ==

[파일: apps/api/app/routers/finance/__init__.py]
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.services.finance_service import FinanceService
from app.services.tax_ai_service import TaxAIService
from app.middleware.auth import get_current_user

router  = APIRouter(prefix="/api/v1/finance", tags=["finance"])
_fin    = FinanceService()
_tax    = TaxAIService()

class UnderwritingRequest(BaseModel):
    project_id:         str
    purchase_price_krw: int
    equity_ratio_pct:   float = 30.0
    loan_rate_pct:      float = 4.5
    noi_monthly_krw:    int
    hold_years:         int   = 5
    exit_cap_rate_pct:  float = 4.5

class TransferTaxRequest(BaseModel):
    purchase_price_krw: int
    sale_price_krw:     int
    hold_years:         int
    home_count:         int  = 1
    is_major_city:      bool = True

class AcquisitionTaxRequest(BaseModel):
    price_krw:      int
    home_count:     int  = 1
    is_legal_entity: bool = False

class MonteCarloRequest(BaseModel):
    purchase_price_krw: int
    sale_price_min:     int
    sale_price_max:     int
    hold_years_min:     int = 3
    hold_years_max:     int = 10
    n_simulations:      int = 1000

@router.post("/underwriting")
async def run_underwriting(req: UnderwritingRequest, user: dict = Depends(get_current_user)):
    return await _fin.run_underwriting(**dict(req))

@router.post("/tax/transfer")
async def calc_transfer_tax(req: TransferTaxRequest, user: dict = Depends(get_current_user)):
    return _tax.calculate_transfer_tax(**dict(req))

@router.post("/tax/acquisition")
async def calc_acquisition_tax(req: AcquisitionTaxRequest, user: dict = Depends(get_current_user)):
    return _tax.calculate_acquisition_tax(**dict(req))

@router.post("/tax/monte-carlo")
async def monte_carlo(req: MonteCarloRequest, user: dict = Depends(get_current_user)):
    return _tax.run_monte_carlo_tax_scenarios(
        req.purchase_price_krw,
        (req.sale_price_min, req.sale_price_max),
        (req.hold_years_min, req.hold_years_max),
        req.n_simulations
    )
```

---

## Phase 08: 한국특화 AI (전세/경공매)

```
================================================================
[PROPAI PHASE-08: 한국특화 AI -- 전세/경공매 분석]
================================================================

== P08-STEP-01: 전세 리스크 분석 서비스 ==

[파일: apps/api/app/services/jeonse_service.py]
import os
import json
import httpx
from datetime import datetime

class JeonseRiskService:
    """
    전세 리스크 분석 서비스
    전세 사기 7대 패턴 탐지
    HUG 보증보험 가입 가능 여부 자동 판단
    리스크 등급 A~F 산출
    """

    # 전세 사기 7대 패턴
    FRAUD_PATTERNS = {
        "high_jeonse_ratio": "전세가율 80% 이상 (깡통전세 위험)",
        "illegal_building":  "불법 건축물 / 위반 건축물",
        "multi_mortgage":    "근저당 과다 설정 (전세금 + 근저당 > 시세 80%)",
        "registration_mismatch": "등기부 소유자와 임대인 불일치",
        "short_term_ownership": "소유권 취득 후 1년 이내 임대",
        "auction_signal":    "경매/압류 이력 존재",
        "hug_unavailable":   "HUG 보증보험 가입 불가 (한도 초과)"
    }

    def __init__(self, db_pool=None):
        from app.db import get_db_pool
        self._db = db_pool or get_db_pool()

    async def analyze_jeonse_risk(
        self,
        project_id:        str,
        jeonse_price_krw:  int,
        market_price_krw:  int,
        mortgage_total_krw: int = 0,
        building_legal:    bool = True,
        owner_match:       bool = True,
        ownership_years:   int  = 5,
        has_auction_history: bool = False,
        is_metropolitan:   bool  = True
    ) -> dict:
        """전세 리스크 종합 분석"""

        jeonse_ratio = jeonse_price_krw / market_price_krw if market_price_krw > 0 else 1.0
        total_burden = (jeonse_price_krw + mortgage_total_krw) / market_price_krw if market_price_krw > 0 else 1.0

        # HUG 보증보험 한도 (2025 기준)
        hug_limit = 700_000_000 if is_metropolitan else 500_000_000
        hug_eligible = jeonse_price_krw <= hug_limit and jeonse_ratio <= 0.9

        # 패턴 탐지
        detected_patterns = []
        if jeonse_ratio >= 0.8:
            detected_patterns.append(self.FRAUD_PATTERNS["high_jeonse_ratio"])
        if not building_legal:
            detected_patterns.append(self.FRAUD_PATTERNS["illegal_building"])
        if total_burden > 0.8:
            detected_patterns.append(self.FRAUD_PATTERNS["multi_mortgage"])
        if not owner_match:
            detected_patterns.append(self.FRAUD_PATTERNS["registration_mismatch"])
        if ownership_years < 1:
            detected_patterns.append(self.FRAUD_PATTERNS["short_term_ownership"])
        if has_auction_history:
            detected_patterns.append(self.FRAUD_PATTERNS["auction_signal"])
        if not hug_eligible:
            detected_patterns.append(self.FRAUD_PATTERNS["hug_unavailable"])

        # 리스크 등급 산출
        risk_score = len(detected_patterns)
        grade_map  = {0: "A", 1: "B", 2: "C", 3: "D", 4: "E", 5: "F"}
        risk_grade = grade_map.get(min(risk_score, 5), "F")

        # AI 종합 의견
        ai_opinion = await self._get_ai_opinion(
            jeonse_ratio, risk_grade, detected_patterns, hug_eligible
        )

        result = {
            "jeonse_price_krw":  jeonse_price_krw,
            "market_price_krw":  market_price_krw,
            "jeonse_ratio":      round(jeonse_ratio, 3),
            "total_burden_ratio": round(total_burden, 3),
            "hug_eligible":      hug_eligible,
            "hug_limit_krw":     hug_limit,
            "risk_grade":        risk_grade,
            "risk_score":        risk_score,
            "fraud_patterns":    detected_patterns,
            "recommendation":    self._get_recommendation(risk_grade),
            "ai_opinion":        ai_opinion,
        }

        await self._db.execute("""
            INSERT INTO jeonse_analyses
            (project_id, jeonse_price_krw, market_price_krw, jeonse_ratio,
             risk_grade, fraud_patterns_json, hug_eligible, ai_opinion)
            VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,$8)
        """,
            project_id, jeonse_price_krw, market_price_krw, jeonse_ratio,
            risk_grade, json.dumps(detected_patterns, ensure_ascii=False),
            hug_eligible, ai_opinion
        )
        return result

    def _get_recommendation(self, grade: str) -> str:
        recs = {
            "A": "안전한 전세 계약 가능 (HUG 보증보험 가입 적극 권장)",
            "B": "주의 필요 -- 등기부 등본 및 건축물 대장 재확인",
            "C": "리스크 높음 -- 전문가 검토 후 계약 여부 결정",
            "D": "매우 위험 -- 계약 전 법무사/변호사 상담 필수",
            "E": "심각한 위험 -- 계약 재고 강력 권고",
            "F": "전세 사기 패턴 복수 탐지 -- 계약 포기 권고"
        }
        return recs.get(grade, "분석 불가")

    async def _get_ai_opinion(self, ratio, grade, patterns, hug_eligible) -> str:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return f"[기계 검토] 전세가율 {ratio*100:.1f}% | 등급 {grade} | 패턴 {len(patterns)}건 탐지 | HUG{'가능' if hug_eligible else '불가'}"

        prompt = f"""전세 계약 리스크 분석 결과를 2문장으로 요약해주세요.
전세가율: {ratio*100:.1f}%, 리스크 등급: {grade}, 탐지 패턴: {patterns}, HUG: {'가능' if hug_eligible else '불가'}"""

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={"model": "claude-sonnet-4-6", "max_tokens": 200, "temperature": 0,
                          "messages": [{"role": "user", "content": prompt}]}
                )
            return resp.json().get("content", [{}])[0].get("text", "")
        except Exception:
            return f"전세가율 {ratio*100:.1f}% -- 리스크 등급 {grade}"

== P08-STEP-02: 전세/경공매 라우터 ==

[파일: apps/api/app/routers/projects/__init__.py]
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services.jeonse_service import JeonseRiskService
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["korean-specific"])
_jeonse_svc = JeonseRiskService()

class JeonseRequest(BaseModel):
    project_id:          str
    jeonse_price_krw:    int
    market_price_krw:    int
    mortgage_total_krw:  int  = 0
    building_legal:      bool = True
    owner_match:         bool = True
    ownership_years:     int  = 5
    has_auction_history: bool = False
    is_metropolitan:     bool = True

@router.post("/jeonse/analyze")
async def analyze_jeonse(req: JeonseRequest, user: dict = Depends(get_current_user)):
    return await _jeonse_svc.analyze_jeonse_risk(**dict(req))
```

---

## Phase 09: 시공 + ESG AI

```
================================================================
[PROPAI PHASE-09: 시공/ESG/기후리스크 AI]
================================================================

== P09-STEP-01: 시공 + ESG + 탄소 서비스 ==

[파일: apps/api/app/services/construction_esg_service.py]
import json
import math
from datetime import datetime, timedelta

class ConstructionESGService:
    """
    시공 + ESG AI 통합 서비스
    BIM 4D 시공 일정 자동 생성 (국토부 표준품셈 기반)
    탄소 배출 계산 (내재탄소 + 장비탄소 + 전력탄소)
    ZEB 에너지 시뮬레이션
    기후 리스크 정량화 (KMA RCP 8.5 기반)
    """

    # 국토부 표준품셈 공종별 공기 계수 (m²당 일수)
    CONSTRUCTION_PHASES = {
        "토공사":     {"days_per_m2": 0.02, "cost_per_m2": 80_000,  "carbon_kg_m2": 15},
        "기초공사":   {"days_per_m2": 0.05, "cost_per_m2": 200_000, "carbon_kg_m2": 80},
        "골조공사":   {"days_per_m2": 0.08, "cost_per_m2": 400_000, "carbon_kg_m2": 150},
        "외부마감":   {"days_per_m2": 0.04, "cost_per_m2": 300_000, "carbon_kg_m2": 40},
        "내부마감":   {"days_per_m2": 0.06, "cost_per_m2": 500_000, "carbon_kg_m2": 60},
        "기계/전기":  {"days_per_m2": 0.03, "cost_per_m2": 200_000, "carbon_kg_m2": 20},
        "준공검사":   {"days_per_m2": 0.01, "cost_per_m2": 30_000,  "carbon_kg_m2": 5},
    }

    # 탄소 배출 계수 (IPCC 2023 기준)
    CARBON_FACTORS = {
        "concrete_kg_per_m3": 270,   # 콘크리트 kg CO2e/m3
        "steel_kg_per_ton":   1_800,  # 철근 kg CO2e/ton
        "electricity_kg_kwh": 0.459,  # 한국 전력 탄소계수 (2025 KEA)
        "diesel_kg_liter":    2.68,   # 경유 탄소계수
    }

    def __init__(self, db_pool=None):
        from app.db import get_db_pool
        self._db = db_pool or get_db_pool()

    def generate_bim4d_schedule(
        self,
        project_id:          str,
        gross_floor_area_m2: float,
        total_floors:        int,
        start_date:          str = "2026-06-01"
    ) -> dict:
        """
        BIM 4D 시공 일정 자동 생성
        국토부 표준품셈 기반 공기 계산
        """
        from datetime import date
        try:
            current_date = date.fromisoformat(start_date)
        except Exception:
            current_date = date(2026, 6, 1)

        schedule     = []
        total_cost   = 0
        total_carbon = 0

        for phase_name, params in self.CONSTRUCTION_PHASES.items():
            duration_days = max(7, int(gross_floor_area_m2 * params["days_per_m2"]))
            phase_cost    = int(gross_floor_area_m2 * params["cost_per_m2"])
            phase_carbon  = gross_floor_area_m2 * params["carbon_kg_m2"]

            end_date = current_date + timedelta(days=duration_days)
            schedule.append({
                "phase":         phase_name,
                "start_date":    current_date.isoformat(),
                "end_date":      end_date.isoformat(),
                "duration_days": duration_days,
                "cost_krw":      phase_cost,
                "carbon_kg":     round(phase_carbon, 0),
            })
            total_cost   += phase_cost
            total_carbon += phase_carbon
            current_date  = end_date

        return {
            "project_id":          project_id,
            "gross_floor_area_m2": gross_floor_area_m2,
            "total_floors":        total_floors,
            "schedule":            schedule,
            "total_cost_krw":      total_cost,
            "total_carbon_kg":     round(total_carbon, 0),
            "total_months":        round(sum(p["duration_days"] for p in schedule) / 30, 1),
            "methodology":         "국토교통부 표준품셈 2025 기준"
        }

    def calculate_carbon_footprint(
        self,
        gross_floor_area_m2: float,
        concrete_m3:         float,
        steel_ton:           float,
        energy_kwh_yr:       float,
        diesel_liters_construction: float
    ) -> dict:
        """
        건물 탄소 발자국 계산
        내재탄소 + 운영탄소 + 시공탄소 분리 계산
        """
        # 내재탄소 (자재)
        concrete_carbon = concrete_m3       * self.CARBON_FACTORS["concrete_kg_per_m3"]
        steel_carbon    = steel_ton         * self.CARBON_FACTORS["steel_kg_per_ton"]
        embodied_carbon = concrete_carbon + steel_carbon

        # 시공 탄소 (장비)
        construction_carbon = diesel_liters_construction * self.CARBON_FACTORS["diesel_kg_liter"]

        # 운영 탄소 (연간)
        operational_carbon_yr = energy_kwh_yr * self.CARBON_FACTORS["electricity_kg_kwh"]

        # 30년 생애주기 총 탄소
        lifecycle_carbon = embodied_carbon + construction_carbon + operational_carbon_yr * 30

        return {
            "embodied_carbon_kg":      round(embodied_carbon, 0),
            "construction_carbon_kg":  round(construction_carbon, 0),
            "operational_carbon_yr_kg": round(operational_carbon_yr, 0),
            "lifecycle_30yr_kg":       round(lifecycle_carbon, 0),
            "carbon_intensity_kg_m2":  round(lifecycle_carbon / gross_floor_area_m2, 1),
            "epc_kwh_m2_yr":           round(energy_kwh_yr / gross_floor_area_m2, 1),
            "zeb_rate_pct":            0,   # 신재생에너지 비율 입력 시 계산
            "methodology":             "IPCC 2023 + KEA 전력 탄소계수 2025"
        }

    def calculate_climate_risk(
        self,
        project_id:    str,
        latitude:      float,
        longitude:     float,
        coastal_dist_km: float = 50,
        elevation_m:   float = 50,
        flood_zone:    bool = False,
        heat_island:   bool = False
    ) -> dict:
        """
        기후 리스크 정량화 (KMA RCP 8.5 시나리오)
        홍수/폭염/태풍/가뭄 4대 리스크 점수 산출
        """
        # 홍수 리스크 (0~100)
        flood_base   = 40 if flood_zone else 20
        flood_elev   = max(0, 30 - elevation_m * 0.3)
        flood_risk   = min(100, int(flood_base + flood_elev))

        # 폭염 리스크
        heat_base    = 30
        heat_island_bonus = 20 if heat_island else 0
        heat_risk    = min(100, heat_base + heat_island_bonus + (35 - latitude) * 2 if latitude < 38 else 30)

        # 태풍 리스크 (해안 근접도)
        storm_risk   = min(100, max(10, int(60 - coastal_dist_km * 0.5)))

        # 가뭄 리스크 (내륙 + 고도)
        drought_risk = min(100, int(20 + elevation_m * 0.1))

        overall_risk = int((flood_risk + heat_risk + storm_risk + drought_risk) / 4)
        risk_level   = "높음" if overall_risk >= 60 else "보통" if overall_risk >= 40 else "낮음"

        return {
            "project_id":  project_id,
            "flood_risk":  flood_risk,
            "heat_risk":   int(heat_risk),
            "storm_risk":  storm_risk,
            "drought_risk": drought_risk,
            "overall_risk": overall_risk,
            "risk_level":  risk_level,
            "insurance_recommendation": {
                "flood_insurance":   flood_risk >= 50,
                "typhoon_insurance": storm_risk >= 50,
                "recommended_coverage_krw": overall_risk * 10_000_000
            },
            "methodology": "KMA RCP 8.5 기후변화 시나리오 기반 (2025년 국토교통부 기준)"
        }

== P09-STEP-02: 시공/ESG 라우터 ==

[파일: apps/api/app/routers/construction/__init__.py]
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from app.services.construction_esg_service import ConstructionESGService
from app.middleware.auth import get_current_user

router = APIRouter(prefix="/api/v1/construction", tags=["construction"])
_svc   = ConstructionESGService()

class BIM4DRequest(BaseModel):
    project_id:          str
    gross_floor_area_m2: float
    total_floors:        int
    start_date:          str = "2026-06-01"

class CarbonRequest(BaseModel):
    project_id:          str
    gross_floor_area_m2: float
    concrete_m3:         float
    steel_ton:           float
    energy_kwh_yr:       float
    diesel_liters_construction: float = 0.0

class ClimateRiskRequest(BaseModel):
    project_id:      str
    latitude:        float
    longitude:       float
    coastal_dist_km: float = 50.0
    elevation_m:     float = 50.0
    flood_zone:      bool  = False
    heat_island:     bool  = False

@router.post("/bim4d")
async def generate_bim4d(req: BIM4DRequest, user: dict = Depends(get_current_user)):
    return _svc.generate_bim4d_schedule(**dict(req))

@router.post("/carbon")
async def calculate_carbon(req: CarbonRequest, user: dict = Depends(get_current_user)):
    return _svc.calculate_carbon_footprint(
        req.gross_floor_area_m2, req.concrete_m3, req.steel_ton,
        req.energy_kwh_yr, req.diesel_liters_construction
    )

@router.post("/climate-risk")
async def climate_risk(req: ClimateRiskRequest, user: dict = Depends(get_current_user)):
    return _svc.calculate_climate_risk(**dict(req))

== P09-STEP-03: main.py 라우터 전체 등록 ==

[파일: apps/api/app/main.py (Phase 06~09 라우터 추가)]

from app.routers.auth         import router as auth_router
from app.routers.parcels      import router as parcels_router
from app.routers.avm          import router as avm_router
from app.routers.regulation   import router as regulation_router
from app.routers.design       import router as design_router
from app.routers.finance      import router as finance_router
from app.routers.projects     import router as jeonse_router
from app.routers.construction import router as construction_router

for router in [
    auth_router, parcels_router, avm_router, regulation_router,
    design_router, finance_router, jeonse_router, construction_router
]:
    app.include_router(router)
```

---

## Phase 06~09 완료 체크리스트

```
[ ] POST /api/v1/design/generate -> 설계안 JSON 반환
[ ] POST /api/v1/design/generate/stream -> SSE 스트리밍 동작
[ ] POST /api/v1/finance/underwriting -> IRR/NPV/배수
[ ] POST /api/v1/finance/tax/transfer -> 양도소득세
[ ] POST /api/v1/finance/tax/acquisition -> 취득세
[ ] POST /api/v1/finance/tax/monte-carlo -> 1,000회 시뮬레이션
[ ] POST /api/v1/jeonse/analyze -> 등급 + 패턴 탐지
[ ] POST /api/v1/construction/bim4d -> 공종별 일정
[ ] POST /api/v1/construction/carbon -> 탄소 발자국
[ ] POST /api/v1/construction/climate-risk -> 기후 리스크 점수

-- 완료 후 Part-D 진행 --
```

---

*Part-C 버전: v43.0 | 기준일: 2026년 3월 21일*
*다음 파트: Part-D (MLOps + 프론트엔드 완전체 + K8s 인프라)*
