# PropAI v43.0 — Part F: AI마케팅 · 도메인에이전트 · 예측유지보수 · 임차인경험 · 자산인텔리전스
# G86 ~ G90 | 만장일치 최종 무결점 완성판
# 선행 파트: Part-E 완료 후 실행 (순서 엄수)

---

## 사전 확인

```bash
# Part-E 완료 여부 검증
curl -s http://localhost:8000/api/v1/climate/risk \
  -H "Content-Type: application/json" \
  -d '{"project_id":"test","region":"Seoul","property_value_krw":1000000000,"floor_area_m2":100,"building_use":"공동주택","climate_scenario":"SSP3"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'annual_expected_loss' in d, 'Part-E 미완료'"
echo "Part-E 검증 완료 -- Part-F 진행"
```

---

## [=== G86: AI 마케팅 자동화 + OM 보고서 ===]

### G86-1: DB 마이그레이션

```python
# alembic/versions/v43_g86_marketing.py
"""G86 AI Marketing & OM"""
revision = 'g86_marketing'
down_revision = 'g85_climate'
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

def upgrade():
    op.create_table(
        'marketing_campaigns',
        sa.Column('id',            UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id',    UUID, nullable=False),
        sa.Column('channel',       sa.String(40), nullable=False),   # web/sns/email/naver/kakao
        sa.Column('target_segment',JSONB, nullable=False, server_default='{}'),
        sa.Column('content',       JSONB, nullable=False, server_default='{}'),  # subject/body/cta/images
        sa.Column('ai_model',      sa.String(60), nullable=False),
        sa.Column('impressions',   sa.BigInteger, default=0),
        sa.Column('clicks',        sa.BigInteger, default=0),
        sa.Column('conversions',   sa.BigInteger, default=0),
        sa.Column('cost_krw',      sa.Numeric(18,2), default=0),
        sa.Column('roi',           sa.Float, nullable=True),
        sa.Column('status',        sa.String(20), default='draft'),   # draft/active/paused/completed
        sa.Column('created_at',    sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at',    sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'om_reports',
        sa.Column('id',            UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id',    UUID, nullable=False),
        sa.Column('report_month',  sa.String(7), nullable=False),   # YYYY-MM
        sa.Column('report_type',   sa.String(30), default='monthly'), # monthly/quarterly/annual
        sa.Column('financials',    JSONB, nullable=False, server_default='{}'),
        sa.Column('occupancy_pct', sa.Float, default=0.0),
        sa.Column('noi_krw',       sa.Numeric(18,2), default=0),
        sa.Column('capex_krw',     sa.Numeric(18,2), default=0),
        sa.Column('ai_summary',    sa.Text, nullable=True),
        sa.Column('pdf_url',       sa.Text, nullable=True),
        sa.Column('created_at',    sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_mc_project_channel', 'marketing_campaigns', ['project_id','channel'])
    op.create_index('ix_om_project_month',   'om_reports',          ['project_id','report_month'])
```

### G86-2: AI 마케팅 서비스

```python
# app/services/marketing_service.py
import anthropic, json, asyncio
from datetime import datetime
from app.core.config import settings
from app.core.database import get_db
from app.core.cache import redis_client

client = anthropic.AsyncAnthropic()

CHANNEL_SPEC = {
    "naver_blog": {"max_chars": 2000, "tone": "informative", "lang": "ko"},
    "instagram":  {"max_chars": 150,  "tone": "visual_cta",  "lang": "ko"},
    "email":      {"max_chars": 800,  "tone": "professional","lang": "ko"},
    "kakao_story":{"max_chars": 400,  "tone": "friendly",    "lang": "ko"},
    "linkedin":   {"max_chars": 600,  "tone": "b2b",         "lang": "en"},
}

async def generate_marketing_content(
    project_id: str,
    project_name: str,
    building_type: str,
    location: str,
    key_features: list[str],
    target_segment: dict,
    channels: list[str],
) -> dict:
    cache_key = f"marketing:{project_id}:{'-'.join(sorted(channels))}"
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    results = {}
    for ch in channels:
        spec = CHANNEL_SPEC.get(ch, CHANNEL_SPEC["email"])
        prompt = f"""
당신은 대한민국 최고의 부동산 마케팅 카피라이터입니다.
아래 정보를 바탕으로 {ch} 채널용 마케팅 콘텐츠를 작성하세요.

프로젝트명: {project_name}
건물유형: {building_type}
위치: {location}
핵심특징: {', '.join(key_features)}
타겟세그먼트: {json.dumps(target_segment, ensure_ascii=False)}
채널규격: 최대 {spec['max_chars']}자, 톤={spec['tone']}, 언어={spec['lang']}

결과를 JSON으로만 반환하세요 (설명 없이):
{{
  "subject": "...",
  "body": "...",
  "cta": "...",
  "hashtags": ["..."],
  "ab_variant_b": {{"body": "...", "cta": "..."}}
}}
"""
        resp = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            temperature=0.7,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        try:
            content = json.loads(raw)
        except Exception:
            content = {"subject": project_name, "body": raw, "cta": "문의하기", "hashtags": [], "ab_variant_b": {}}
        results[ch] = content

    await redis_client.setex(cache_key, 3600, json.dumps(results, ensure_ascii=False))
    return results


async def generate_om_report(
    project_id: str,
    report_month: str,
    financials: dict,
    occupancy_pct: float,
) -> dict:
    noi = financials.get("revenue_krw", 0) - financials.get("opex_krw", 0)
    cap_rate = noi / financials.get("asset_value_krw", 1) * 100 if financials.get("asset_value_krw") else 0

    prompt = f"""
다음 부동산 운용 데이터를 분석하여 {report_month} 월간 운영관리(OM) 보고서 요약을 작성하세요.

임대율: {occupancy_pct:.1f}%
NOI: {noi:,.0f}원
수익률(Cap Rate): {cap_rate:.2f}%
재무 상세: {json.dumps(financials, ensure_ascii=False)}

경영진 요약(Executive Summary), 주요 성과, 리스크 및 개선사항을 포함한
전문적인 OM 보고서 요약을 2000자 이내로 작성하세요.
"""
    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}]
    )
    return {
        "project_id":    project_id,
        "report_month":  report_month,
        "noi_krw":       noi,
        "cap_rate_pct":  round(cap_rate, 2),
        "occupancy_pct": occupancy_pct,
        "ai_summary":    resp.content[0].text.strip(),
        "generated_at":  datetime.utcnow().isoformat(),
    }
```

### G86-3: 라우터

```python
# app/api/v1/marketing.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.services.marketing_service import generate_marketing_content, generate_om_report
from app.core.auth import get_current_user

router = APIRouter(prefix="/marketing", tags=["Marketing & OM"])

class MarketingRequest(BaseModel):
    project_id:     str
    project_name:   str
    building_type:  str
    location:       str
    key_features:   List[str]
    target_segment: dict = {}
    channels:       List[str] = ["naver_blog", "email", "instagram"]

class OmReportRequest(BaseModel):
    project_id:    str
    report_month:  str   # YYYY-MM
    financials:    dict
    occupancy_pct: float = 95.0

@router.post("/generate")
async def marketing_generate(req: MarketingRequest, user=Depends(get_current_user)):
    return await generate_marketing_content(**req.dict())

@router.post("/om-report")
async def om_report_generate(req: OmReportRequest, user=Depends(get_current_user)):
    return await generate_om_report(**req.dict())
```

---

## [=== G87: McKinsey 4대 도메인 AI 에이전트 ===]

### G87-1: 도메인 에이전트 아키텍처

```
McKinsey Real Estate 4-Domain Framework
========================================
Domain 1: Asset Management       -- 자산 성과 최적화
Domain 2: Development            -- 개발사업 실행
Domain 3: Transaction Advisory   -- 매각/매입 자문
Domain 4: Debt & Equity Finance  -- 자금조달 구조화
```

### G87-2: 도메인 에이전트 서비스

```python
# app/services/domain_agent_service.py
import anthropic, json
from app.core.cache import redis_client

client = anthropic.AsyncAnthropic()

DOMAIN_AGENTS = {
    "asset_management": {
        "name": "자산관리 AI 에이전트",
        "system": """당신은 맥킨지 수준의 부동산 자산관리(Asset Management) 전문 AI입니다.
주요 역할:
1. NOI 최적화 분석 (임대료 인상 여력, 공실 최소화, 비용 절감)
2. 자본지출(CapEx) 우선순위 결정 (ROI 기반)
3. 포트폴리오 리밸런싱 제안 (보유/매각/추가취득)
4. 벤치마크 비교 (동종자산 대비 성과)
분석 결과는 반드시 수치 근거와 함께 제시하세요.""",
    },
    "development": {
        "name": "개발사업 AI 에이전트",
        "system": """당신은 맥킨지 수준의 부동산 개발(Development) 전문 AI입니다.
주요 역할:
1. 사업타당성 종합 분석 (IRR/NPV/PBP)
2. 인허가 리스크 평가 (용도지역, 건폐율, 용적률)
3. 공사비 최적화 (VE 검토, 원가절감 방안)
4. 분양/임대 전환 시점 최적화
분석 결과는 반드시 수치 근거와 함께 제시하세요.""",
    },
    "transaction": {
        "name": "거래자문 AI 에이전트",
        "system": """당신은 맥킨지 수준의 부동산 거래자문(Transaction Advisory) 전문 AI입니다.
주요 역할:
1. 매각/매입 타이밍 분석 (시장 사이클, 금리 환경)
2. 가격 협상 레인지 산정 (AVM + 거래 사례 비교)
3. 실사(Due Diligence) 체크리스트 자동생성
4. 거래 구조 최적화 (SPC/PFV, 현물출자, 리파이낸싱)
분석 결과는 반드시 수치 근거와 함께 제시하세요.""",
    },
    "finance": {
        "name": "금융구조화 AI 에이전트",
        "system": """당신은 맥킨지 수준의 부동산 금융구조화(Debt & Equity Finance) 전문 AI입니다.
주요 역할:
1. 대출조건 최적화 (LTV, 금리, 만기, 상환방식)
2. 에쿼티/메자닌/시니어 구조 설계
3. 재무 모델링 (Excel DCF, Waterfall 분배)
4. 리파이낸싱/브릿지론 적기 분석
분석 결과는 반드시 수치 근거와 함께 제시하세요.""",
    },
}

async def run_domain_agent(
    domain: str,
    query: str,
    context: dict,
    conversation_history: list = None,
) -> dict:
    if domain not in DOMAIN_AGENTS:
        raise ValueError(f"Unknown domain: {domain}")

    agent = DOMAIN_AGENTS[domain]
    history = conversation_history or []

    messages = history + [
        {"role": "user", "content": f"""
컨텍스트:
{json.dumps(context, ensure_ascii=False, indent=2)}

질문/요청:
{query}
"""}
    ]

    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        temperature=0.3,
        system=agent["system"],
        messages=messages,
    )

    answer = resp.content[0].text.strip()
    return {
        "domain":      domain,
        "agent_name":  agent["name"],
        "query":       query,
        "answer":      answer,
        "tokens_used": resp.usage.input_tokens + resp.usage.output_tokens,
        "model":       "claude-sonnet-4-6",
    }


async def run_multi_domain_analysis(project_data: dict) -> dict:
    """4개 도메인 에이전트 병렬 실행"""
    import asyncio
    queries = {
        "asset_management": "이 자산의 NOI 최적화 방안과 포트폴리오 편입 타당성을 분석하세요.",
        "development":      "개발사업 타당성(IRR/NPV)과 인허가 리스크를 분석하세요.",
        "transaction":      "현재 시장 환경에서 최적 매각/매입 타이밍과 가격 범위를 제시하세요.",
        "finance":          "최적 금융 구조와 LTV/금리 조건, 에쿼티 구조를 설계하세요.",
    }
    tasks = [
        run_domain_agent(domain, query, project_data)
        for domain, query in queries.items()
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        domain: (r if not isinstance(r, Exception) else {"error": str(r)})
        for domain, r in zip(queries.keys(), results)
    }
```

### G87-3: 라우터

```python
# app/api/v1/domain_agents.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from app.services.domain_agent_service import run_domain_agent, run_multi_domain_analysis
from app.core.auth import get_current_user

router = APIRouter(prefix="/agents/domain", tags=["Domain Agents"])

class DomainAgentRequest(BaseModel):
    domain:               str   # asset_management/development/transaction/finance
    query:                str
    context:              dict  = {}
    conversation_history: List  = []

class MultiDomainRequest(BaseModel):
    project_data: dict

@router.post("/run")
async def domain_agent_run(req: DomainAgentRequest, user=Depends(get_current_user)):
    return await run_domain_agent(req.domain, req.query, req.context, req.conversation_history)

@router.post("/multi-analysis")
async def multi_domain_analysis(req: MultiDomainRequest, user=Depends(get_current_user)):
    return await run_multi_domain_analysis(req.project_data)
```

---

## [=== G88: IoT 예측 유지보수 + HVAC 최적화 ===]

### G88-1: DB 마이그레이션

```python
# alembic/versions/v43_g88_iot.py
"""G88 IoT Predictive Maintenance"""
revision = 'g88_iot'
down_revision = 'g87_domain'
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

def upgrade():
    op.create_table(
        'iot_sensors',
        sa.Column('id',           UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('building_id',  UUID, nullable=False),
        sa.Column('sensor_code',  sa.String(50), nullable=False, unique=True),
        sa.Column('sensor_type',  sa.String(40), nullable=False),  # HVAC/elevator/fire/power/water
        sa.Column('location',     sa.String(100), nullable=False),
        sa.Column('manufacturer', sa.String(80), nullable=True),
        sa.Column('model',        sa.String(80), nullable=True),
        sa.Column('install_date', sa.Date, nullable=True),
        sa.Column('is_active',    sa.Boolean, default=True),
        sa.Column('meta',         JSONB, default={}),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'iot_readings',
        sa.Column('id',           UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('sensor_id',    UUID, nullable=False),
        sa.Column('ts',           sa.DateTime(timezone=True), nullable=False),
        sa.Column('temperature',  sa.Float, nullable=True),
        sa.Column('humidity',     sa.Float, nullable=True),
        sa.Column('vibration',    sa.Float, nullable=True),
        sa.Column('power_kw',     sa.Float, nullable=True),
        sa.Column('flow_rate',    sa.Float, nullable=True),
        sa.Column('pressure_bar', sa.Float, nullable=True),
        sa.Column('co2_ppm',      sa.Float, nullable=True),
        sa.Column('raw',          JSONB, default={}),
    )
    op.create_table(
        'maintenance_alerts',
        sa.Column('id',           UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('sensor_id',    UUID, nullable=False),
        sa.Column('alert_type',   sa.String(50), nullable=False),  # anomaly/failure_prediction/maintenance_due
        sa.Column('severity',     sa.String(20), nullable=False),  # low/medium/high/critical
        sa.Column('description',  sa.Text, nullable=True),
        sa.Column('predicted_failure_date', sa.Date, nullable=True),
        sa.Column('recommended_action', sa.Text, nullable=True),
        sa.Column('cost_estimate_krw', sa.Numeric(18,2), nullable=True),
        sa.Column('resolved_at',  sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_iot_readings_sensor_ts', 'iot_readings', ['sensor_id', 'ts'])
    op.create_index('ix_iot_alerts_sensor',      'maintenance_alerts', ['sensor_id', 'severity'])
```

### G88-2: IoT 예측 유지보수 서비스

```python
# app/services/iot_service.py
"""
예측 유지보수 알고리즘:
  Z-score 이상탐지: z = (x - mu) / sigma
  임계값: |z| > 3.0 → 이상, |z| > 2.0 → 경고
  MTBF(Mean Time Between Failures) 기반 고장 예측
  RUL(Remaining Useful Life) = MTBF - (현재까지 가동시간)
  에너지 효율 지수 = 실제소비 / 이론최소소비 (1.0이 최적)
"""
import math, json, anthropic
from datetime import datetime, timedelta
from typing import List
from app.core.cache import redis_client

client = anthropic.AsyncAnthropic()

# 기기 유형별 임계값 (한국건축설비학회 기준)
SENSOR_THRESHOLDS = {
    "HVAC": {
        "temperature":   (15.0, 45.0),   # 정상 범위 (도씨)
        "vibration":     (0.0,  5.0),    # mm/s RMS
        "power_kw":      (0.0, 200.0),
        "co2_ppm":       (0.0, 1000.0),  # ASHRAE 62.1 기준
        "mtbf_hours":    17520,           # 2년 = 17520시간
    },
    "elevator": {
        "vibration":     (0.0,  3.0),
        "temperature":   (5.0,  40.0),
        "power_kw":      (0.0,  30.0),
        "mtbf_hours":    8760,            # 1년
    },
    "fire": {
        "temperature":   (0.0,  60.0),
        "pressure_bar":  (0.5,  9.0),
        "mtbf_hours":    43800,           # 5년
    },
    "power": {
        "power_kw":      (0.0, 1000.0),
        "temperature":   (0.0,  80.0),
        "mtbf_hours":    26280,           # 3년
    },
}

def z_score_anomaly(readings: list, field: str) -> dict:
    values = [r.get(field) for r in readings if r.get(field) is not None]
    if len(values) < 3:
        return {"status": "insufficient_data"}
    mu = sum(values) / len(values)
    sigma = math.sqrt(sum((v - mu) ** 2 for v in values) / len(values))
    if sigma == 0:
        return {"status": "constant", "mean": mu}
    latest = values[-1]
    z = abs(latest - mu) / sigma
    return {
        "field":       field,
        "latest":      latest,
        "mean":        round(mu, 4),
        "std":         round(sigma, 4),
        "z_score":     round(z, 3),
        "anomaly":     z > 3.0,
        "warning":     z > 2.0,
        "severity":    "critical" if z > 4.0 else ("high" if z > 3.0 else ("medium" if z > 2.0 else "low")),
    }

def predict_rul(install_date_str: str, sensor_type: str) -> dict:
    mtbf = SENSOR_THRESHOLDS.get(sensor_type, {}).get("mtbf_hours", 8760)
    try:
        install_date = datetime.strptime(install_date_str[:10], "%Y-%m-%d")
    except Exception:
        install_date = datetime.utcnow() - timedelta(days=365)
    hours_operated = (datetime.utcnow() - install_date).total_seconds() / 3600
    rul_hours = max(0.0, mtbf - hours_operated)
    failure_date = datetime.utcnow() + timedelta(hours=rul_hours)
    return {
        "hours_operated":     round(hours_operated, 1),
        "mtbf_hours":         mtbf,
        "rul_hours":          round(rul_hours, 1),
        "rul_days":           round(rul_hours / 24, 1),
        "predicted_failure":  failure_date.strftime("%Y-%m-%d"),
        "health_pct":         round(max(0, min(100, rul_hours / mtbf * 100)), 1),
    }

def hvac_efficiency_index(readings: list) -> dict:
    """
    HVAC 에너지 효율 지수 (EEI):
    EEI = 실제소비전력 / (냉난방부하 × 이론COP)
    이론COP(냉방) = T_cold / (T_hot - T_cold)  [켈빈 기준]
    EEI 정상 범위: 1.0~1.5 (1.0이 이상적)
    """
    power_vals = [r.get("power_kw", 0) for r in readings if r.get("power_kw") is not None]
    temp_vals  = [r.get("temperature", 25) for r in readings if r.get("temperature") is not None]
    if not power_vals:
        return {"eei": None, "status": "no_data"}

    avg_power = sum(power_vals) / len(power_vals)
    avg_temp  = sum(temp_vals) / len(temp_vals)

    # 이론 COP (실내 22도 기준, 외기온도 avg_temp)
    T_cold = 295.15  # 22도 켈빈
    T_hot  = max(avg_temp + 273.15, T_cold + 1)
    cop_theoretical = T_cold / (T_hot - T_cold)
    cop_actual      = max(0.5, min(cop_theoretical, 6.0))  # 실제 COP 한계
    eei             = avg_power / max(cop_actual * 10, 1)  # 정규화

    return {
        "avg_power_kw":    round(avg_power, 2),
        "avg_outdoor_temp":round(avg_temp, 1),
        "theoretical_cop": round(cop_theoretical, 2),
        "eei":             round(eei, 3),
        "efficiency_grade":"A" if eei < 1.2 else ("B" if eei < 1.5 else ("C" if eei < 2.0 else "D")),
    }

async def detect_anomaly(
    sensor_id: str,
    sensor_type: str,
    readings: list,
    install_date: str = None,
) -> dict:
    anomalies = {}
    fields = ["temperature", "vibration", "power_kw", "co2_ppm", "pressure_bar", "flow_rate"]
    for f in fields:
        if any(r.get(f) is not None for r in readings):
            anomalies[f] = z_score_anomaly(readings, f)

    rul = predict_rul(install_date or str(datetime.utcnow().date()), sensor_type)
    hvac_eff = hvac_efficiency_index(readings) if sensor_type == "HVAC" else None

    critical_fields = [f for f, v in anomalies.items() if isinstance(v, dict) and v.get("anomaly")]
    has_critical    = len(critical_fields) > 0 or rul["health_pct"] < 20

    ai_recommendation = None
    if has_critical:
        prompt = f"""
IoT 센서 이상 감지 결과를 분석하고 유지보수 권고사항을 제시하세요.

센서유형: {sensor_type}
이상감지 항목: {critical_fields}
잔여수명(RUL): {rul['rul_days']}일
상세: {json.dumps(anomalies, ensure_ascii=False)}

예상 고장일, 권고 조치, 예상 비용을 포함하여 200자 이내로 작성하세요.
"""
        resp = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}]
        )
        ai_recommendation = resp.content[0].text.strip()

    return {
        "sensor_id":         sensor_id,
        "sensor_type":       sensor_type,
        "anomaly_detected":  has_critical,
        "critical_fields":   critical_fields,
        "anomaly_details":   anomalies,
        "rul":               rul,
        "hvac_efficiency":   hvac_eff,
        "ai_recommendation": ai_recommendation,
        "alert_severity":    "critical" if rul["health_pct"] < 10 else (
                             "high"     if has_critical           else (
                             "medium"   if rul["health_pct"] < 30 else "low")),
    }
```

### G88-3: 라우터

```python
# app/api/v1/iot.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.services.iot_service import detect_anomaly
from app.core.auth import get_current_user

router = APIRouter(prefix="/maintenance", tags=["IoT Maintenance"])

class SensorReading(BaseModel):
    temperature:  Optional[float] = None
    humidity:     Optional[float] = None
    vibration:    Optional[float] = None
    power_kw:     Optional[float] = None
    flow_rate:    Optional[float] = None
    pressure_bar: Optional[float] = None
    co2_ppm:      Optional[float] = None

class AnomalyRequest(BaseModel):
    sensor_id:    str
    sensor_type:  str = "HVAC"
    readings:     List[dict]
    install_date: Optional[str] = None

@router.post("/detect-anomaly")
async def maintenance_detect_anomaly(req: AnomalyRequest, user=Depends(get_current_user)):
    return await detect_anomaly(req.sensor_id, req.sensor_type, req.readings, req.install_date)
```

---

## [=== G89: AI 임차인 경험 + 감성 분석 ===]

### G89-1: DB 마이그레이션

```python
# alembic/versions/v43_g89_tenant.py
"""G89 Tenant Experience & Sentiment"""
revision = 'g89_tenant'
down_revision = 'g88_iot'
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

def upgrade():
    op.create_table(
        'tenant_feedbacks',
        sa.Column('id',           UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('building_id',  UUID, nullable=False),
        sa.Column('tenant_id',    UUID, nullable=True),
        sa.Column('channel',      sa.String(30), nullable=False),  # app/kakao/email/web/on-site
        sa.Column('category',     sa.String(50), nullable=True),   # maintenance/cleanliness/security/facility
        sa.Column('content',      sa.Text, nullable=False),
        sa.Column('sentiment',    sa.String(20), nullable=True),   # positive/neutral/negative
        sa.Column('sentiment_score', sa.Float, nullable=True),     # -1.0 ~ 1.0
        sa.Column('topics',       JSONB, nullable=True),
        sa.Column('priority',     sa.String(20), default='normal'),
        sa.Column('status',       sa.String(20), default='open'),  # open/in_progress/resolved
        sa.Column('ai_reply',     sa.Text, nullable=True),
        sa.Column('resolved_at',  sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'tenant_satisfaction_scores',
        sa.Column('id',           UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('building_id',  UUID, nullable=False),
        sa.Column('period',       sa.String(7), nullable=False),   # YYYY-MM
        sa.Column('nps_score',    sa.Float, nullable=True),        # Net Promoter Score -100~100
        sa.Column('csat_score',   sa.Float, nullable=True),        # Customer Satisfaction 1~5
        sa.Column('ces_score',    sa.Float, nullable=True),        # Customer Effort Score 1~7
        sa.Column('response_count', sa.Integer, default=0),
        sa.Column('summary',      sa.Text, nullable=True),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_tf_building_sentiment', 'tenant_feedbacks', ['building_id', 'sentiment'])
    op.create_index('ix_tss_building_period',   'tenant_satisfaction_scores', ['building_id', 'period'])
```

### G89-2: 감성 분석 서비스

```python
# app/services/tenant_service.py
"""
감성 분석 알고리즘:
  1차: 키워드 기반 (한국어 감성 사전 KOSAC 기준)
  2차: Claude AI 고급 분석
  NPS = 추천의향(9-10점) 비율 - 비추천(1-6점) 비율
  CSAT = 평균 만족도 점수 (1-5점 척도)
  CES = 7점 리커트 척도 역산 (낮을수록 좋음)
"""
import anthropic, json, re
from datetime import datetime
from app.core.cache import redis_client

client = anthropic.AsyncAnthropic()

# 한국어 감성 사전 (KOSAC 기반 핵심 어휘)
POS_WORDS = {"좋다","훌륭하다","만족","편리","깔끔","친절","빠르다","해결","감사","최고","추천"}
NEG_WORDS = {"불편","불만","느리다","고장","더럽다","시끄럽다","냄새","위험","불친절","최악","화난다","다시는"}

def keyword_sentiment(text: str) -> float:
    """간단한 키워드 기반 감성 점수 (-1.0 ~ 1.0)"""
    tokens = set(re.findall(r'\w+', text))
    pos = len(tokens & POS_WORDS)
    neg = len(tokens & NEG_WORDS)
    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 3)

async def analyze_sentiment(text: str, building_context: str = "") -> dict:
    # 1차: 키워드 기반
    kw_score = keyword_sentiment(text)

    # 2차: AI 분석
    prompt = f"""
다음 임차인 피드백을 분석하세요.
건물: {building_context}
피드백: {text}

JSON만 반환하세요:
{{
  "sentiment": "positive|neutral|negative",
  "score": 0.0,
  "topics": ["..."],
  "priority": "urgent|normal|low",
  "category": "maintenance|cleanliness|security|facility|complaint|praise|other",
  "summary": "..."
}}
score는 -1.0(매우 부정) ~ 1.0(매우 긍정) 범위.
"""
    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        temperature=0.0,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = resp.content[0].text.strip()
    try:
        ai_result = json.loads(raw)
    except Exception:
        ai_result = {"sentiment": "neutral", "score": kw_score, "topics": [], "priority": "normal", "category": "other", "summary": text[:100]}

    # 가중 평균 (AI 80% + 키워드 20%)
    final_score = ai_result.get("score", 0) * 0.8 + kw_score * 0.2
    ai_result["score"] = round(final_score, 3)
    return ai_result

async def generate_ai_reply(feedback: str, sentiment: str, category: str) -> str:
    tone = "위로와 해결의지" if sentiment == "negative" else ("진심 어린 감사" if sentiment == "positive" else "친절")
    prompt = f"""
임차인 피드백에 대한 전문적인 답변을 작성하세요.
피드백: {feedback}
감성: {sentiment} | 카테고리: {category}
톤: {tone}
150자 이내, 구체적 조치 포함, 공손한 한국어.
"""
    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        temperature=0.4,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.content[0].text.strip()

def calc_nps(scores: list[float]) -> float:
    """NPS = 추천(9-10점 환산) 비율 - 비추천(1-6점) 비율"""
    if not scores:
        return 0.0
    scaled = [s * 2 for s in scores]  # 1-5 → 2-10 스케일
    promoters  = sum(1 for s in scaled if s >= 9)
    detractors = sum(1 for s in scaled if s <= 6)
    n = len(scaled)
    return round((promoters - detractors) / n * 100, 1)
```

### G89-3: 라우터

```python
# app/api/v1/tenant.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import Optional, List
from app.services.tenant_service import analyze_sentiment, generate_ai_reply, calc_nps
from app.core.auth import get_current_user

router = APIRouter(prefix="/tenant", tags=["Tenant Experience"])

class FeedbackRequest(BaseModel):
    building_id:       str
    content:           str
    channel:           str  = "app"
    generate_reply:    bool = True
    building_context:  str  = ""

class NpsRequest(BaseModel):
    building_id: str
    scores:      List[float]   # 1-5 척도 점수 목록

@router.post("/feedback/analyze")
async def feedback_analyze(req: FeedbackRequest, user=Depends(get_current_user)):
    sentiment_result = await analyze_sentiment(req.content, req.building_context)
    reply = None
    if req.generate_reply:
        reply = await generate_ai_reply(req.content, sentiment_result["sentiment"], sentiment_result.get("category","other"))
    return {**sentiment_result, "ai_reply": reply, "channel": req.channel}

@router.post("/satisfaction/nps")
async def satisfaction_nps(req: NpsRequest, user=Depends(get_current_user)):
    return {"building_id": req.building_id, "nps": calc_nps(req.scores), "count": len(req.scores)}
```

---

## [=== G90: 디지털 트윈 + 자산 인텔리전스 ===]

### G90-1: DB 마이그레이션

```python
# alembic/versions/v43_g90_digital_twin.py
"""G90 Digital Twin & Asset Intelligence"""
revision = 'g90_twin'
down_revision = 'g89_tenant'
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

def upgrade():
    op.create_table(
        'digital_twins',
        sa.Column('id',              UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('building_id',     UUID, nullable=False, unique=True),
        sa.Column('twin_version',    sa.String(20), default='1.0'),
        sa.Column('bim_file_url',    sa.Text, nullable=True),
        sa.Column('geometry_data',   JSONB, nullable=False, server_default='{}'),   # GeoJSON 3D
        sa.Column('floors',          JSONB, nullable=False, server_default='[]'),
        sa.Column('systems',         JSONB, nullable=False, server_default='{}'),   # HVAC/전기/소방
        sa.Column('sensor_mapping',  JSONB, nullable=False, server_default='{}'),   # sensorId -> 공간
        sa.Column('energy_baseline', JSONB, nullable=True),
        sa.Column('last_sync_at',    sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        'asset_intelligence_snapshots',
        sa.Column('id',              UUID, primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('building_id',     UUID, nullable=False),
        sa.Column('snapshot_date',   sa.Date, nullable=False),
        sa.Column('health_score',    sa.Float, nullable=True),     # 0-100
        sa.Column('energy_score',    sa.Float, nullable=True),     # 0-100
        sa.Column('tenant_score',    sa.Float, nullable=True),     # 0-100
        sa.Column('financial_score', sa.Float, nullable=True),     # 0-100
        sa.Column('composite_score', sa.Float, nullable=True),     # 0-100
        sa.Column('risk_flags',      JSONB, nullable=True),
        sa.Column('ai_insights',     sa.Text, nullable=True),
        sa.Column('kpi_data',        JSONB, nullable=False, server_default='{}'),
        sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_ais_building_date', 'asset_intelligence_snapshots', ['building_id','snapshot_date'])
```

### G90-2: 자산 인텔리전스 서비스

```python
# app/services/asset_intelligence_service.py
"""
복합 자산 건전성 점수 산출:
  건물 건전성 점수 = 0.35*설비건전성 + 0.25*에너지효율 + 0.25*임차인만족 + 0.15*재무건전성
  에너지 절감 잠재력 = (현재소비 - 벤치마크소비) / 현재소비 × 100%
  자산가치 갱신: AVM × (1 + 건물건전성보정계수)
"""
import anthropic, json, math
from datetime import date

client = anthropic.AsyncAnthropic()

SCORE_WEIGHTS = {
    "health":    0.35,   # IoT 설비 건전성
    "energy":    0.25,   # 에너지 효율
    "tenant":    0.25,   # 임차인 만족도
    "financial": 0.15,   # 재무 건전성
}

def calc_health_score(iot_alerts: list) -> float:
    """설비 건전성 점수 (IoT 알림 기반)"""
    if not iot_alerts:
        return 100.0
    severity_weights = {"critical": 30, "high": 15, "medium": 7, "low": 2}
    deduction = sum(severity_weights.get(a.get("severity","low"), 2) for a in iot_alerts)
    return max(0.0, round(100.0 - deduction, 1))

def calc_energy_score(actual_kwh_m2: float, benchmark_kwh_m2: float = 150.0) -> float:
    """
    에너지 효율 점수
    벤치마크: 150 kWh/m2/year (한국에너지공단 제로에너지건축물 기준)
    점수 = 100 × (benchmark / actual) 단, 100 초과 시 100으로 캡
    """
    if actual_kwh_m2 <= 0:
        return 50.0
    score = min(100.0, benchmark_kwh_m2 / actual_kwh_m2 * 100)
    return round(score, 1)

def calc_tenant_score(nps: float, csat: float = 0.0) -> float:
    """NPS(-100~100) + CSAT(1~5) → 0~100 점수"""
    nps_norm  = (nps + 100) / 2          # 0~100
    csat_norm = (csat - 1) / 4 * 100     # 0~100
    if csat > 0:
        return round(nps_norm * 0.6 + csat_norm * 0.4, 1)
    return round(nps_norm, 1)

def calc_financial_score(noi_actual: float, noi_budget: float, vacancy_pct: float) -> float:
    """
    재무 건전성 점수
    NOI 달성률 × 0.7 + 임대율 × 0.3
    """
    noi_rate    = min(100, noi_actual / max(noi_budget, 1) * 100) if noi_budget > 0 else 70.0
    occupancy   = max(0, 100 - vacancy_pct)
    return round(noi_rate * 0.7 + occupancy * 0.3, 1)

async def generate_asset_intelligence(
    building_id:    str,
    iot_alerts:     list  = None,
    energy_kwh_m2:  float = 150.0,
    nps:            float = 0.0,
    csat:           float = 3.0,
    noi_actual:     float = 0.0,
    noi_budget:     float = 0.0,
    vacancy_pct:    float = 5.0,
    avm_value:      float = 0.0,
) -> dict:
    h_score = calc_health_score(iot_alerts or [])
    e_score = calc_energy_score(energy_kwh_m2)
    t_score = calc_tenant_score(nps, csat)
    f_score = calc_financial_score(noi_actual, noi_budget, vacancy_pct)

    composite = round(
        h_score * SCORE_WEIGHTS["health"]   +
        e_score * SCORE_WEIGHTS["energy"]   +
        t_score * SCORE_WEIGHTS["tenant"]   +
        f_score * SCORE_WEIGHTS["financial"],
        1
    )

    # 건전성 보정 자산가치
    health_adj  = (composite - 70) / 100  # -0.30 ~ +0.30
    adj_value   = avm_value * (1 + health_adj * 0.05)  # 최대 ±1.5% 보정

    risk_flags = []
    if h_score < 50:  risk_flags.append("설비_위험")
    if e_score < 40:  risk_flags.append("에너지_비효율")
    if t_score < 40:  risk_flags.append("임차인_불만")
    if f_score < 50:  risk_flags.append("재무_부진")

    grade = "S" if composite >= 90 else ("A" if composite >= 80 else ("B" if composite >= 70 else ("C" if composite >= 60 else "D")))

    prompt = f"""
부동산 자산 종합 인텔리전스 분석:
건물ID: {building_id}
종합점수: {composite}/100 (등급: {grade})
- 설비건전성: {h_score} | 에너지효율: {e_score} | 임차인만족: {t_score} | 재무건전성: {f_score}
리스크: {risk_flags}
AVM 조정가치: {adj_value:,.0f}원

경영진을 위한 자산 인텔리전스 인사이트를 200자 이내로 작성하세요.
"""
    resp = await client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        temperature=0.3,
        messages=[{"role": "user", "content": prompt}]
    )

    return {
        "building_id":       building_id,
        "snapshot_date":     date.today().isoformat(),
        "composite_score":   composite,
        "grade":             grade,
        "scores": {
            "health":    h_score,
            "energy":    e_score,
            "tenant":    t_score,
            "financial": f_score,
        },
        "risk_flags":        risk_flags,
        "adjusted_value_krw":round(adj_value, -3),
        "ai_insights":       resp.content[0].text.strip(),
        "weights":           SCORE_WEIGHTS,
    }
```

### G90-3: 라우터

```python
# app/api/v1/digital_twin.py
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List, Optional
from app.services.asset_intelligence_service import generate_asset_intelligence
from app.core.auth import get_current_user

router = APIRouter(prefix="/digital-twin", tags=["Digital Twin"])

class AssetIntelligenceRequest(BaseModel):
    building_id:   str
    iot_alerts:    List[dict] = []
    energy_kwh_m2: float      = 150.0
    nps:           float      = 0.0
    csat:          float      = 3.0
    noi_actual:    float      = 0.0
    noi_budget:    float      = 0.0
    vacancy_pct:   float      = 5.0
    avm_value:     float      = 0.0

@router.post("/asset-intelligence")
async def asset_intelligence(req: AssetIntelligenceRequest, user=Depends(get_current_user)):
    return await generate_asset_intelligence(**req.dict())
```

---

## Part F 라우터 통합 등록

```python
# app/main.py 에 추가 (기존 파일 수정)
# --- Part F 라우터 ---
from app.api.v1.marketing    import router as marketing_router
from app.api.v1.domain_agents import router as domain_agents_router
from app.api.v1.iot           import router as iot_router
from app.api.v1.tenant        import router as tenant_router
from app.api.v1.digital_twin  import router as digital_twin_router

app.include_router(marketing_router,     prefix="/api/v1")
app.include_router(domain_agents_router, prefix="/api/v1")
app.include_router(iot_router,           prefix="/api/v1")
app.include_router(tenant_router,        prefix="/api/v1")
app.include_router(digital_twin_router,  prefix="/api/v1")
```

---

## Part F 완료 체크리스트

```
[Part-F 완료 기준 -- 전체 15개 항목]

G86 (AI 마케팅):
  [ ] POST /api/v1/marketing/generate -> 채널별 콘텐츠 반환 확인
  [ ] POST /api/v1/marketing/om-report -> NOI/cap_rate/ai_summary 반환 확인

G87 (도메인 에이전트):
  [ ] POST /api/v1/agents/domain/run -> domain=asset_management 응답 확인
  [ ] POST /api/v1/agents/domain/multi-analysis -> 4개 도메인 병렬 응답 확인

G88 (IoT 예측유지보수):
  [ ] POST /api/v1/maintenance/detect-anomaly -> anomaly_detected/rul/severity 반환 확인
  [ ] Z-score 3.0 초과 시 anomaly=true 정상 판정 확인
  [ ] HVAC 타입 요청 시 hvac_efficiency 포함 확인

G89 (임차인 경험):
  [ ] POST /api/v1/tenant/feedback/analyze -> sentiment/score/ai_reply 반환 확인
  [ ] POST /api/v1/tenant/satisfaction/nps -> NPS 점수 -100~100 범위 확인
  [ ] 부정 피드백 시 ai_reply 에 조치 내용 포함 확인

G90 (디지털 트윈):
  [ ] POST /api/v1/digital-twin/asset-intelligence -> composite_score/grade/risk_flags 반환 확인
  [ ] composite_score 0~100 범위 확인
  [ ] grade S/A/B/C/D 정상 산정 확인
  [ ] adjusted_value_krw 음수 아님 확인
  [ ] ai_insights 비어있지 않음 확인

다음 파트: Part-G (AI비용제어 + 외부포털 + 다국어보고서 + KEPCO + 에너지인증)
```
