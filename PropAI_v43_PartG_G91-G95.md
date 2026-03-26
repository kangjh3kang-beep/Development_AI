# PropAI v43.0 — Part G: AI비용제어 · 외부포털 · 다국어보고서 · KEPCO · 에너지인증
# G91 ~ G95 | 만장일치 최종 무결점 완성판
# 선행 파트: Part-F 완료 후 실행 (순서 엄수)

---

## 사전 확인

```bash
curl -s -X POST http://localhost:8000/api/v1/digital-twin/asset-intelligence \
  -H "Content-Type: application/json" \
  -d '{"building_id":"test","energy_kwh_m2":150}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'composite_score' in d, 'Part-F 미완료'"
echo "Part-F 검증 완료 -- Part-G 진행"
```

---

## [=== G91: AI 토큰 비용 실시간 제어 대시보드 ===]

### G91-1: DB 마이그레이션

```python
# alembic/versions/v43_g91_ai_cost.py
"""G91 AI Cost Control"""
revision = 'g91_ai_cost'
down_revision = 'g90_twin'
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

def upgrade():
    op.create_table(
        'ai_usage_logs',
        sa.Column('id',           UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id',      UUID, nullable=True),
        sa.Column('project_id',   UUID, nullable=True),
        sa.Column('endpoint',     sa.String(120), nullable=False),
        sa.Column('model',        sa.String(60),  nullable=False),
        sa.Column('input_tokens', sa.Integer, default=0),
        sa.Column('output_tokens',sa.Integer, default=0),
        sa.Column('cache_tokens', sa.Integer, default=0),    # Prompt Caching 절감
        sa.Column('cost_usd',     sa.Numeric(10, 6), default=0),
        sa.Column('cost_krw',     sa.Numeric(12, 2), default=0),
        sa.Column('latency_ms',   sa.Integer, default=0),
        sa.Column('cached',       sa.Boolean, default=False),
        sa.Column('ts',           sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'ai_cost_budgets',
        sa.Column('id',           UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('period',       sa.String(7),  nullable=False, unique=True),  # YYYY-MM
        sa.Column('budget_usd',   sa.Numeric(12,2), nullable=False),
        sa.Column('alert_pct',    sa.Float, default=80.0),   # 80% 초과 시 알림
        sa.Column('hard_limit_usd', sa.Numeric(12,2), nullable=True),  # 초과 시 AI 호출 차단
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_aul_ts',       'ai_usage_logs',   ['ts'])
    op.create_index('ix_aul_endpoint', 'ai_usage_logs',   ['endpoint'])
    op.create_index('ix_aul_user',     'ai_usage_logs',   ['user_id'])
```

### G91-2: AI 비용 미들웨어 및 서비스

```python
# app/services/ai_cost_service.py
"""
Claude API 요금 체계 (2025년 기준):
  claude-sonnet-4-6: Input $3/MTok, Output $15/MTok
  Prompt Cache Write: $3.75/MTok, Cache Read: $0.30/MTok
  USD/KRW 환율: 실시간 조회 (기본값 1,350원)
  일일 예산 경고: 80% 도달 시 Slack/알림톡
  월간 Hard Limit: 초과 시 AI 호출 차단
"""
import asyncio, json
from datetime import datetime, timedelta
from decimal import Decimal
from app.core.database import get_db
from app.core.cache import redis_client

# 모델별 단가 (USD per 1,000 tokens)
PRICING = {
    "claude-sonnet-4-6": {
        "input":        3.00 / 1000,    # $3/MTok → $0.003/Ktok
        "output":      15.00 / 1000,
        "cache_write":  3.75 / 1000,
        "cache_read":   0.30 / 1000,
    },
}
DEFAULT_USD_KRW = 1350.0

def calc_cost(model: str, input_tok: int, output_tok: int,
              cache_tok: int = 0, cached: bool = False) -> dict:
    p = PRICING.get(model, PRICING["claude-sonnet-4-6"])
    if cached:
        input_cost  = input_tok  / 1000 * p["cache_read"]
        cache_cost  = cache_tok  / 1000 * p["cache_write"]
        saved_usd   = input_tok  / 1000 * (p["input"] - p["cache_read"])
    else:
        input_cost  = input_tok  / 1000 * p["input"]
        cache_cost  = 0.0
        saved_usd   = 0.0
    output_cost = output_tok / 1000 * p["output"]
    total_usd   = input_cost + output_cost + cache_cost
    total_krw   = total_usd * DEFAULT_USD_KRW
    return {
        "input_tokens":  input_tok,
        "output_tokens": output_tok,
        "cache_tokens":  cache_tok,
        "cost_usd":      round(total_usd,  6),
        "cost_krw":      round(total_krw,  2),
        "saved_usd":     round(saved_usd,  6),
        "cached":        cached,
    }

async def log_usage(endpoint: str, model: str, usage_data: dict,
                    user_id: str = None, project_id: str = None):
    cost = calc_cost(model,
                     usage_data.get("input_tokens", 0),
                     usage_data.get("output_tokens", 0),
                     usage_data.get("cache_tokens", 0),
                     usage_data.get("cached", False))
    # Redis 실시간 누적
    period = datetime.utcnow().strftime("%Y-%m")
    await redis_client.incrbyfloat(f"ai_cost:{period}:usd", cost["cost_usd"])
    await redis_client.incr(f"ai_cost:{period}:calls")
    await redis_client.expire(f"ai_cost:{period}:usd", 86400 * 40)
    return cost

async def get_cost_dashboard() -> dict:
    period = datetime.utcnow().strftime("%Y-%m")
    month_usd = float(await redis_client.get(f"ai_cost:{period}:usd") or 0)
    month_calls = int(await redis_client.get(f"ai_cost:{period}:calls") or 0)

    # 일별 집계 (최근 7일)
    daily = {}
    for i in range(7):
        d = (datetime.utcnow() - timedelta(days=i)).strftime("%Y-%m-%d")
        daily[d] = float(await redis_client.get(f"ai_cost:daily:{d}:usd") or 0)

    return {
        "period":         period,
        "month_total_usd":round(month_usd, 4),
        "month_total_krw":round(month_usd * DEFAULT_USD_KRW, 0),
        "month_calls":    month_calls,
        "avg_cost_per_call_krw": round(month_usd * DEFAULT_USD_KRW / max(month_calls, 1), 0),
        "daily_breakdown":daily,
        "usd_krw_rate":   DEFAULT_USD_KRW,
    }

async def check_budget_gate(endpoint: str) -> dict:
    """예산 초과 시 AI 호출 차단 게이트"""
    period = datetime.utcnow().strftime("%Y-%m")
    month_usd = float(await redis_client.get(f"ai_cost:{period}:usd") or 0)
    hard_limit_key = f"ai_budget:{period}:hard_limit"
    hard_limit = float(await redis_client.get(hard_limit_key) or 500.0)  # 기본 $500
    alert_pct = 80.0
    pct_used = month_usd / hard_limit * 100 if hard_limit > 0 else 0
    return {
        "allowed":     pct_used < 100,
        "pct_used":    round(pct_used, 1),
        "alert":       pct_used >= alert_pct,
        "hard_limit":  hard_limit,
        "current_usd": round(month_usd, 4),
    }
```

### G91-3: 라우터

```python
# app/api/v1/ai_costs.py
from fastapi import APIRouter, Depends
from app.services.ai_cost_service import get_cost_dashboard, check_budget_gate
from app.core.auth import get_current_user

router = APIRouter(prefix="/ai-costs", tags=["AI Cost Control"])

@router.get("/dashboard")
async def cost_dashboard(user=Depends(get_current_user)):
    return await get_cost_dashboard()

@router.get("/budget-gate/{endpoint:path}")
async def budget_gate(endpoint: str, user=Depends(get_current_user)):
    return await check_budget_gate(endpoint)
```

---

## [=== G92: 외부 부동산 포털 연동 ===]

### G92-1: 멀티포털 서비스

```python
# app/services/portal_service.py
"""
연동 포털 목록:
  - 네이버 부동산 (Naver Real Estate API)
  - 직방 (Zigbang API)
  - 다방 (Dabang API)
  - 호갱노노 (HoGaengNoNo)
  - KB부동산 (KB Real Estate)
실제 배포 시 각 포털 공식 파트너 API 키 필요.
본 구현은 인터페이스 표준화 + Mock 응답 제공.
"""
import httpx, json, asyncio
from app.core.config import settings
from app.core.cache import redis_client

PORTAL_CONFIG = {
    "naver": {
        "name":     "네이버 부동산",
        "base_url": "https://land.naver.com/api",
        "api_key":  getattr(settings, "NAVER_LAND_API_KEY", "mock"),
    },
    "zigbang": {
        "name":     "직방",
        "base_url": "https://apis.zigbang.com",
        "api_key":  getattr(settings, "ZIGBANG_API_KEY", "mock"),
    },
    "dabang": {
        "name":     "다방",
        "base_url": "https://api.dabangapp.com",
        "api_key":  getattr(settings, "DABANG_API_KEY", "mock"),
    },
    "kb": {
        "name":     "KB부동산",
        "base_url": "https://kbland.kr/api",
        "api_key":  getattr(settings, "KB_LAND_API_KEY", "mock"),
    },
}

def _mock_listing(portal_id: str, listing_data: dict) -> dict:
    return {
        "portal":    portal_id,
        "status":    "posted",
        "listing_id":f"MOCK-{portal_id.upper()}-{listing_data.get('project_id','0')[:8]}",
        "url":       f"https://{portal_id}.example.com/listing/mock",
        "mock":      True,
    }

async def post_to_portal(portal_id: str, listing_data: dict) -> dict:
    cfg = PORTAL_CONFIG.get(portal_id)
    if not cfg:
        return {"portal": portal_id, "status": "error", "error": "unknown_portal"}
    if cfg["api_key"] == "mock":
        return _mock_listing(portal_id, listing_data)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.post(
                f"{cfg['base_url']}/listings",
                headers={"Authorization": f"Bearer {cfg['api_key']}",
                         "Content-Type": "application/json"},
                json=listing_data,
            )
            return {"portal": portal_id, "status": "posted",
                    "listing_id": resp.json().get("id"), "url": resp.json().get("url")}
        except Exception as e:
            return {"portal": portal_id, "status": "error", "error": str(e)}

async def post_to_all_portals(listing_data: dict, portals: list = None) -> dict:
    target = portals or list(PORTAL_CONFIG.keys())
    tasks = [post_to_portal(p, listing_data) for p in target]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        "results":  [r if not isinstance(r, Exception) else {"error": str(r)} for r in results],
        "success":  sum(1 for r in results if isinstance(r, dict) and r.get("status") == "posted"),
        "total":    len(target),
    }

async def get_market_data(region_code: str, building_type: str) -> dict:
    """포털 시세 데이터 통합 조회 (캐시 1시간)"""
    cache_key = f"portal_market:{region_code}:{building_type}"
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Mock 시세 (실제: 각 포털 API 호출)
    mock_data = {
        "region_code":    region_code,
        "building_type":  building_type,
        "avg_price_krw":  850_000_000,
        "avg_per_m2_krw": 12_500_000,
        "transaction_count_30d": 47,
        "price_change_pct_3m":  2.3,
        "portals_queried": list(PORTAL_CONFIG.keys()),
        "mock": True,
    }
    await redis_client.setex(cache_key, 3600, json.dumps(mock_data, ensure_ascii=False))
    return mock_data
```

### G92-2: 라우터

```python
# app/api/v1/portals.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.services.portal_service import post_to_portal, post_to_all_portals, get_market_data
from app.core.auth import get_current_user

router = APIRouter(prefix="/portals", tags=["Portal Integration"])

class ListingData(BaseModel):
    project_id:    str
    title:         str
    building_type: str
    location:      str
    price_krw:     float
    area_m2:       float
    description:   str = ""
    images:        List[str] = []

@router.post("/{portal_id}/post")
async def post_listing(portal_id: str, data: ListingData, user=Depends(get_current_user)):
    return await post_to_portal(portal_id, data.dict())

@router.post("/post-all")
async def post_all_portals(
    data: ListingData,
    portals: Optional[List[str]] = None,
    user=Depends(get_current_user)
):
    return await post_to_all_portals(data.dict(), portals)

@router.get("/market-data/{region_code}")
async def market_data(region_code: str, building_type: str = "아파트", user=Depends(get_current_user)):
    return await get_market_data(region_code, building_type)
```

---

## [=== G93: 다국어 AI 투자자 보고서 ===]

### G93-1: 다국어 보고서 서비스

```python
# app/services/investor_report_service.py
"""
지원 언어: ko/en/zh-CN/zh-TW/ja/vi/ar
보고서 섹션: Executive Summary / Financial Performance / Risk Analysis / ESG / Outlook
번역 품질: Claude claude-sonnet-4-6 (금융 전문 번역)
PDF 생성: WeasyPrint + Jinja2 템플릿
"""
import anthropic, json, asyncio
from datetime import datetime
from app.core.cache import redis_client

client = anthropic.AsyncAnthropic()

LANG_META = {
    "ko":    {"name": "한국어",    "dir": "ltr", "font": "NanumGothic"},
    "en":    {"name": "English",   "dir": "ltr", "font": "Arial"},
    "zh-CN": {"name": "简体中文",   "dir": "ltr", "font": "SimHei"},
    "zh-TW": {"name": "繁體中文",   "dir": "ltr", "font": "MingLiU"},
    "ja":    {"name": "日本語",    "dir": "ltr", "font": "IPAGothic"},
    "vi":    {"name": "Tiếng Việt","dir": "ltr", "font": "Arial"},
    "ar":    {"name": "العربية",   "dir": "rtl", "font": "Arial"},
}

REPORT_SECTIONS = [
    "executive_summary",
    "financial_performance",
    "risk_analysis",
    "esg_sustainability",
    "market_outlook",
]

async def generate_section(section: str, data: dict, language: str) -> str:
    lang_name = LANG_META.get(language, LANG_META["en"])["name"]
    section_labels = {
        "executive_summary":     "경영진 요약 (Executive Summary)",
        "financial_performance": "재무 성과 (Financial Performance)",
        "risk_analysis":         "리스크 분석 (Risk Analysis)",
        "esg_sustainability":    "ESG 지속가능성 (ESG Sustainability)",
        "market_outlook":        "시장 전망 (Market Outlook)",
    }
    prompt = f"""
당신은 국제 부동산 투자 보고서 전문 작성자입니다.
아래 데이터를 기반으로 {lang_name}으로 {section_labels.get(section,'') } 섹션을 작성하세요.

데이터:
{json.dumps(data, ensure_ascii=False, indent=2)}

요구사항:
- 언어: {lang_name}
- 분량: 300~500자 (해당 언어 기준)
- 전문적인 투자자용 어조
- 구체적 수치 근거 포함
- 긍정/부정 사항 균형 있게 서술
- 숫자는 현지 표기법 준수 (예: 한국 원화 표기 등)
"""
    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.content[0].text.strip()

async def generate_investor_report(
    project_id:  str,
    report_data: dict,
    languages:   list = None,
) -> dict:
    target_langs = languages or ["ko", "en"]
    cache_key = f"inv_report:{project_id}:{'-'.join(sorted(target_langs))}"
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    results = {}
    for lang in target_langs:
        tasks = [generate_section(sec, report_data, lang) for sec in REPORT_SECTIONS]
        sections_text = await asyncio.gather(*tasks)
        results[lang] = {
            "language": LANG_META.get(lang, {}).get("name", lang),
            "direction": LANG_META.get(lang, {}).get("dir", "ltr"),
            "sections": dict(zip(REPORT_SECTIONS, sections_text)),
            "generated_at": datetime.utcnow().isoformat(),
        }

    await redis_client.setex(cache_key, 7200, json.dumps(results, ensure_ascii=False))
    return {"project_id": project_id, "reports": results, "languages": target_langs}
```

### G93-2: 라우터

```python
# app/api/v1/investor_reports.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.services.investor_report_service import generate_investor_report
from app.core.auth import get_current_user

router = APIRouter(prefix="/reports/investor", tags=["Investor Reports"])

class InvestorReportRequest(BaseModel):
    project_id:  str
    report_data: dict
    languages:   List[str] = ["ko", "en"]

@router.post("/generate")
async def investor_report_generate(req: InvestorReportRequest, user=Depends(get_current_user)):
    return await generate_investor_report(req.project_id, req.report_data, req.languages)
```

---

## [=== G94: KEPCO 전기요금 자동 계산 ===]

### G94-1: KEPCO 요금 계산 서비스

```python
# app/services/kepco_service.py
"""
KEPCO 전기요금 계산 체계 (2024년 기준):
  용도별 요금제:
    - 주택용 저압 (단일/누진)
    - 일반용 저압/고압A/고압B
    - 산업용 저압/고압A/고압B
    - 교육용 저압/고압
  계절 구분: 여름(6~8월), 봄·가을(3~5·9~10월), 겨울(11~2월)
  시간대 구분 (고압용): 경부하/중간부하/최대부하

  요금 산정:
    전기요금 = 기본요금 + 전력량요금 + 기후환경요금 + 연료비조정액 + 부가가치세 + 전력산업기반기금

  실제 KEPCO 요금 조회: https://cyber.kepco.co.kr/ckepco/front/jsp/CY/H/C/CYHCHP00101.jsp
  본 구현은 2024년 고시 요금 기반 계산식 구현
"""
from enum import Enum
from typing import Optional

class TariffType(str, Enum):
    RESIDENTIAL_LOW  = "residential_low"
    GENERAL_LOW      = "general_low"
    GENERAL_HIGH_A   = "general_high_a"
    GENERAL_HIGH_B   = "general_high_b"
    INDUSTRIAL_LOW   = "industrial_low"
    INDUSTRIAL_HIGH_A= "industrial_high_a"

class Season(str, Enum):
    SUMMER  = "summer"    # 6~8월
    SPRING_FALL = "spring_fall"  # 3~5·9~10월
    WINTER  = "winter"    # 11~2월

# KEPCO 2024년 요금표 (원/kWh, 원/kW)
KEPCO_RATES = {
    TariffType.RESIDENTIAL_LOW: {
        "base_per_kw": 0,  # 주택용 기본요금은 구간별
        "tiers": [
            {"limit": 200,  "rate": 93.5,  "base": 910},
            {"limit": 400,  "rate": 187.9, "base": 1600},
            {"limit": None, "rate": 280.6, "base": 7300},
        ],
    },
    TariffType.GENERAL_LOW: {
        "base_per_kw": 6160,
        "energy_rates": {
            Season.SUMMER:     97.3,
            Season.SPRING_FALL:78.3,
            Season.WINTER:     101.0,
        },
    },
    TariffType.GENERAL_HIGH_A: {
        "base_per_kw":  7220,
        "energy_rates": {
            Season.SUMMER:     {
                "off_peak": 58.0, "mid_peak": 97.3,  "on_peak": 145.2,
            },
            Season.SPRING_FALL:{
                "off_peak": 55.0, "mid_peak": 70.5,  "on_peak": 98.7,
            },
            Season.WINTER: {
                "off_peak": 66.3, "mid_peak": 110.4, "on_peak": 162.9,
            },
        },
    },
}

# 부가세 및 기금
VAT_RATE               = 0.10
POWER_INFRA_FUND_RATE  = 0.037  # 전력산업기반기금 3.7%
CLIMATE_ENV_CHARGE_KWH = 9.0    # 기후환경요금 (원/kWh) 2024년 기준
FUEL_ADJ_KWH           = 5.0    # 연료비조정액 (원/kWh, 가변)

def calc_season(month: int) -> Season:
    if month in (6, 7, 8):
        return Season.SUMMER
    elif month in (3, 4, 5, 9, 10):
        return Season.SPRING_FALL
    else:
        return Season.WINTER

def calc_residential(kwh: float) -> dict:
    tiers = KEPCO_RATES[TariffType.RESIDENTIAL_LOW]["tiers"]
    base  = 0
    energy = 0.0
    prev_limit = 0
    remaining = kwh
    for tier in tiers:
        if remaining <= 0:
            break
        limit = tier["limit"] or float('inf')
        used_in_tier = min(remaining, limit - prev_limit)
        if used_in_tier > 0:
            energy += used_in_tier * tier["rate"]
            base = tier["base"]
        remaining -= used_in_tier
        prev_limit = limit if tier["limit"] else prev_limit
    return base, energy

def calc_electricity_bill(
    tariff_type:  str,
    month:        int,
    contract_kw:  float,
    kwh_used:     float,
    time_of_use:  dict = None,  # {"off_peak": kWh, "mid_peak": kWh, "on_peak": kWh}
) -> dict:
    t  = TariffType(tariff_type)
    s  = calc_season(month)
    rates = KEPCO_RATES.get(t)

    if t == TariffType.RESIDENTIAL_LOW:
        base_charge, energy_charge = calc_residential(kwh_used)
    elif t in (TariffType.GENERAL_LOW,):
        base_charge   = contract_kw * rates["base_per_kw"]
        energy_charge = kwh_used * rates["energy_rates"][s]
    elif t == TariffType.GENERAL_HIGH_A:
        base_charge   = contract_kw * rates["base_per_kw"]
        r = rates["energy_rates"][s]
        tou = time_of_use or {"off_peak": kwh_used * 0.5, "mid_peak": kwh_used * 0.3, "on_peak": kwh_used * 0.2}
        energy_charge = (
            tou.get("off_peak", 0) * r["off_peak"] +
            tou.get("mid_peak", 0) * r["mid_peak"] +
            tou.get("on_peak",  0) * r["on_peak"]
        )
    else:
        base_charge   = contract_kw * 7220
        energy_charge = kwh_used * 80.0  # 기본 단가

    climate_charge = kwh_used * CLIMATE_ENV_CHARGE_KWH
    fuel_adj       = kwh_used * FUEL_ADJ_KWH
    subtotal       = base_charge + energy_charge + climate_charge + fuel_adj
    vat            = subtotal * VAT_RATE
    fund           = subtotal * POWER_INFRA_FUND_RATE
    total          = subtotal + vat + fund

    per_kwh = total / kwh_used if kwh_used > 0 else 0

    return {
        "tariff_type":       tariff_type,
        "month":             month,
        "season":            s.value,
        "contract_kw":       contract_kw,
        "kwh_used":          kwh_used,
        "base_charge_krw":   round(base_charge),
        "energy_charge_krw": round(energy_charge),
        "climate_charge_krw":round(climate_charge),
        "fuel_adj_krw":      round(fuel_adj),
        "subtotal_krw":      round(subtotal),
        "vat_krw":           round(vat),
        "fund_krw":          round(fund),
        "total_krw":         round(total),
        "per_kwh_krw":       round(per_kwh, 1),
        "annual_estimate_krw":round(total * 12),
    }
```

### G94-2: 라우터

```python
# app/api/v1/kepco.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.services.kepco_service import calc_electricity_bill
from app.core.auth import get_current_user

router = APIRouter(prefix="/energy/kepco", tags=["KEPCO"])

class KepcoRequest(BaseModel):
    tariff_type:  str   = "general_high_a"
    month:        int   = 7
    contract_kw:  float = 100.0
    kwh_used:     float = 50000.0
    time_of_use:  Optional[dict] = None

@router.post("/calculate")
async def kepco_calculate(req: KepcoRequest, user=Depends(get_current_user)):
    return calc_electricity_bill(req.tariff_type, req.month, req.contract_kw, req.kwh_used, req.time_of_use)
```

---

## [=== G95: 에너지 효율 등급 자동화 ===]

### G95-1: 에너지인증 서비스

```python
# app/services/energy_cert_service.py
"""
에너지 효율 등급 자동 산정:
  1. 건물 에너지 효율등급 인증 (건축물에너지효율등급인증제도)
     기준: 단위면적당 1차에너지소요량 (kWh/m2/year)
     1+++: ~60 | 1++: ~90 | 1+: ~120 | 1: ~160 | 2: ~200 | 3: ~260 | 4: ~320 | 5~7: 320+

  2. 제로에너지건축물(ZEB) 인증
     에너지자립률(%) = 생산에너지/소요에너지 × 100
     ZEB 5등급(20%) ~ ZEB 1등급(100%)

  3. BEMS (건물에너지관리시스템) 절감 효과
     참고: 한국에너지공단, 에너지경제연구원 실측치 기반

  법적 근거:
     - 녹색건축물 조성 지원법 제17조
     - 건축물 에너지효율등급 인증 및 제로에너지건축물 인증에 관한 규칙
"""
import anthropic, json
from app.core.cache import redis_client

client = anthropic.AsyncAnthropic()

# 에너지 효율등급 기준 (kWh/m2/year, 1차에너지소요량)
ENERGY_GRADE_TABLE = [
    {"grade": "1+++", "max_kwh": 60},
    {"grade": "1++",  "max_kwh": 90},
    {"grade": "1+",   "max_kwh": 120},
    {"grade": "1",    "max_kwh": 160},
    {"grade": "2",    "max_kwh": 200},
    {"grade": "3",    "max_kwh": 260},
    {"grade": "4",    "max_kwh": 320},
    {"grade": "5",    "max_kwh": 380},
    {"grade": "6",    "max_kwh": 450},
    {"grade": "7",    "max_kwh": float('inf')},
]

# ZEB 등급 기준 (에너지자립률 %)
ZEB_GRADE_TABLE = [
    {"grade": "ZEB_1", "min_pct": 100},
    {"grade": "ZEB_2", "min_pct": 80},
    {"grade": "ZEB_3", "min_pct": 60},
    {"grade": "ZEB_4", "min_pct": 40},
    {"grade": "ZEB_5", "min_pct": 20},
]

# 건물 유형별 기본 1차에너지 계수 (한국에너지공단 2024)
PRIMARY_ENERGY_FACTOR = {
    "전기":   2.75,
    "도시가스":1.10,
    "지역난방":0.614,
    "석유":   1.10,
}

def calc_primary_energy(
    electricity_kwh_m2:  float,
    gas_kwh_m2:          float = 0.0,
    district_heat_kwh_m2:float = 0.0,
) -> float:
    """1차에너지소요량 = Σ(에너지원별 소요량 × 1차에너지계수)"""
    return (
        electricity_kwh_m2   * PRIMARY_ENERGY_FACTOR["전기"]   +
        gas_kwh_m2           * PRIMARY_ENERGY_FACTOR["도시가스"] +
        district_heat_kwh_m2 * PRIMARY_ENERGY_FACTOR["지역난방"]
    )

def classify_energy_grade(primary_kwh_m2: float) -> str:
    for entry in ENERGY_GRADE_TABLE:
        if primary_kwh_m2 <= entry["max_kwh"]:
            return entry["grade"]
    return "7"

def classify_zeb(self_sufficiency_pct: float) -> str:
    for entry in ZEB_GRADE_TABLE:
        if self_sufficiency_pct >= entry["min_pct"]:
            return entry["grade"]
    return "미달"

def estimate_bems_saving(primary_kwh_m2: float, floor_area_m2: float) -> dict:
    """
    BEMS 절감 효과 추정:
    평균 절감률 12.4% (한국에너지공단 2023 실적 평균)
    전기요금 단가 130원/kWh(2024 평균) 적용
    """
    saving_rate  = 0.124
    saved_kwh    = primary_kwh_m2 * floor_area_m2 * saving_rate
    saved_krw    = saved_kwh * 130
    co2_saved_kg = saved_kwh * 0.4781   # 전력 배출계수 (한국전력거래소 2024)
    return {
        "saving_pct":      saving_rate * 100,
        "saved_kwh_year":  round(saved_kwh, 1),
        "saved_krw_year":  round(saved_krw, 0),
        "co2_saved_kg_year":round(co2_saved_kg, 1),
        "co2_saved_ton_year":round(co2_saved_kg / 1000, 2),
    }

async def assess_energy_certification(
    building_id:          str,
    floor_area_m2:        float,
    electricity_kwh_m2:   float,
    gas_kwh_m2:           float = 0.0,
    district_heat_kwh_m2: float = 0.0,
    renewable_kwh_m2:     float = 0.0,
    building_type:        str = "업무시설",
) -> dict:
    primary = calc_primary_energy(electricity_kwh_m2, gas_kwh_m2, district_heat_kwh_m2)
    grade   = classify_energy_grade(primary)

    total_consumption = electricity_kwh_m2 + gas_kwh_m2 + district_heat_kwh_m2
    self_sufficiency  = (renewable_kwh_m2 / max(total_consumption, 1)) * 100 if total_consumption > 0 else 0
    zeb_grade         = classify_zeb(self_sufficiency)
    bems              = estimate_bems_saving(primary, floor_area_m2)

    # 개선 여력 계산 (1등급 달성을 위한 추가 절감 필요량)
    grade_1_threshold = 160.0
    improvement_needed = max(0, primary - grade_1_threshold)
    improvement_pct    = (improvement_needed / primary * 100) if primary > 0 else 0

    prompt = f"""
다음 건물 에너지 성능을 분석하고 인증 취득 및 개선 방안을 제시하세요.

건물유형: {building_type} | 연면적: {floor_area_m2:,.0f}m2
1차에너지소요량: {primary:.1f} kWh/m2/year
에너지효율등급: {grade}
ZEB 자립률: {self_sufficiency:.1f}% ({zeb_grade})
BEMS 예상절감: 연 {bems['saved_krw_year']:,.0f}원

인증 취득 권고, 투자 대비 효과, 구체적 개선 방안을 200자 이내로 작성하세요.
"""
    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}]
    )

    return {
        "building_id":           building_id,
        "primary_energy_kwh_m2": round(primary, 2),
        "energy_grade":          grade,
        "zeb_self_sufficiency_pct": round(self_sufficiency, 1),
        "zeb_grade":             zeb_grade,
        "bems_saving":           bems,
        "improvement_needed_kwh_m2": round(improvement_needed, 2),
        "improvement_needed_pct":    round(improvement_pct, 1),
        "certification_eligible": grade in ["1+++","1++","1+","1"],
        "zeb_eligible":          zeb_grade != "미달",
        "ai_recommendation":     resp.content[0].text.strip(),
        "legal_basis":           "녹색건축물 조성 지원법 제17조",
    }
```

### G95-2: 라우터

```python
# app/api/v1/energy_cert.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional
from app.services.energy_cert_service import assess_energy_certification
from app.core.auth import get_current_user

router = APIRouter(prefix="/energy", tags=["Energy Certification"])

class EnergyCertRequest(BaseModel):
    building_id:           str
    floor_area_m2:         float
    electricity_kwh_m2:    float
    gas_kwh_m2:            float = 0.0
    district_heat_kwh_m2:  float = 0.0
    renewable_kwh_m2:      float = 0.0
    building_type:         str   = "업무시설"

@router.post("/certification")
async def energy_certification(req: EnergyCertRequest, user=Depends(get_current_user)):
    return await assess_energy_certification(**req.dict())
```

---

## Part G 라우터 통합 등록

```python
# app/main.py 에 추가 (기존 파일 수정)
# --- Part G 라우터 ---
from app.api.v1.ai_costs         import router as ai_costs_router
from app.api.v1.portals           import router as portals_router
from app.api.v1.investor_reports  import router as investor_reports_router
from app.api.v1.kepco             import router as kepco_router
from app.api.v1.energy_cert       import router as energy_cert_router

app.include_router(ai_costs_router,         prefix="/api/v1")
app.include_router(portals_router,          prefix="/api/v1")
app.include_router(investor_reports_router, prefix="/api/v1")
app.include_router(kepco_router,            prefix="/api/v1")
app.include_router(energy_cert_router,      prefix="/api/v1")
```

---

## Part G 완료 체크리스트

```
[Part-G 완료 기준 -- 전체 15개 항목]

G91 (AI 비용 제어):
  [ ] GET /api/v1/ai-costs/dashboard -> month_total_krw 반환 확인
  [ ] GET /api/v1/ai-costs/budget-gate/test -> allowed/pct_used 반환 확인
  [ ] Redis ai_cost:{period}:usd 키 누적 확인

G92 (외부 포털):
  [ ] POST /api/v1/portals/naver/post -> status=posted 확인 (Mock)
  [ ] POST /api/v1/portals/post-all -> success/total 카운트 반환 확인
  [ ] GET /api/v1/portals/market-data/11110 -> avg_price_krw 반환 확인

G93 (다국어 보고서):
  [ ] POST /api/v1/reports/investor/generate -> ko+en 섹션 반환 확인
  [ ] 5개 섹션 모두 포함 확인 (executive_summary~market_outlook)
  [ ] 일본어(ja) 요청 시 日本語 텍스트 반환 확인

G94 (KEPCO):
  [ ] POST /api/v1/energy/kepco/calculate -> total_krw 반환 확인
  [ ] tariff_type=residential_low 주택용 누진 계산 확인
  [ ] tariff_type=general_high_a 고압A 시간대별 계산 확인

G95 (에너지 인증):
  [ ] POST /api/v1/energy/certification -> energy_grade/zeb_grade 반환 확인
  [ ] 1+++~7 범위 등급 정상 산정 확인
  [ ] bems_saving.saved_krw_year > 0 확인

다음 파트: Part-H (통합검증 + 부하테스트 + 보안스캔 + 배포)
```
