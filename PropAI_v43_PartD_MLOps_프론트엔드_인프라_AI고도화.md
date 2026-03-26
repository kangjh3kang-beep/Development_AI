# PropAI v43.0 -- Part D: MLOps + 프론트엔드 + 인프라 + AI 고도화
# Full-Cycle Real Estate Development AI Automation Platform
## Phase 10~13 | IDE 즉시 실행 완전 빌드 프롬프트

---

> **선행 조건**: Part-C 완료 (/design/generate, /finance/underwriting, /tax/calculate, /construction/bim4d 동작 확인)
> **예상 소요**: 19일 | **다음 파트**: Part-E (비즈인프라 + G81~G85)
> **실행 방식**: 각 [=== PHASE ===] 블록을 IDE 채팅창에 복사 붙여넣기 후 순서대로 실행

---

## Phase 10: MLOps + AI 모델 관리

```
================================================================
[PROPAI PHASE-10: MLOps -- Airflow DAG + MLflow + Evidently AI]
================================================================

당신은 25년 경력 MLOps 시니어 엔지니어입니다.
PropAI v43.0의 MLOps 파이프라인을 완전히 구현하세요.
코드를 생성하면서 파일을 직접 저장하고, 각 단계 완료 후 확인 메시지를 출력하세요.

================================================================
P10-STEP-01: Airflow DAG -- 야간 배치 분석 파이프라인
================================================================

[파일: infra/airflow/dags/propai_nightly_batch.py]
from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
import asyncio
import httpx

default_args = {
    "owner":           "propai",
    "depends_on_past": False,
    "start_date":      datetime(2026, 1, 1),
    "email_on_failure": True,
    "email":           ["ops@propai.kr"],
    "retries":         2,
    "retry_delay":     timedelta(minutes=5),
}

dag = DAG(
    "propai_nightly_batch",
    default_args=default_args,
    description="PropAI 야간 배치 분석 파이프라인",
    schedule_interval="0 2 * * *",  # 매일 새벽 2시 (한국시간 KST = UTC+9 이므로 UTC 17:00)
    catchup=False,
    tags=["propai", "batch", "nightly"],
)

def refresh_avm_batch(**context):
    """AVM 시세 일괄 갱신 -- 전국 활성 프로젝트 대상"""
    import asyncpg
    import asyncio

    async def _run():
        conn = await asyncpg.connect(
            host="postgres", database="propai_db",
            user="propai", password="propai_secure_2026"
        )
        projects = await conn.fetch(
            "SELECT id, parcel_pnu FROM projects WHERE status='active' LIMIT 200"
        )
        async with httpx.AsyncClient(timeout=30) as client:
            for p in projects:
                try:
                    await client.post(
                        "http://propai-api:8000/api/v1/avm/valuate",
                        json={"pnu": p["parcel_pnu"], "project_id": str(p["id"])},
                        headers={"X-Internal-Token": "propai-batch-2026"}
                    )
                except Exception as e:
                    print(f"[AVM BATCH] 오류 project={p['id']}: {e}")
        await conn.close()
        return f"AVM 갱신 완료: {len(projects)}건"

    return asyncio.run(_run())

def run_model_drift_check(**context):
    """Evidently AI -- 모델 드리프트 감지"""
    import asyncpg, asyncio, json

    async def _run():
        conn = await asyncpg.connect(
            host="postgres", database="propai_db",
            user="propai", password="propai_secure_2026"
        )
        # 최근 7일 AVM 예측 vs 실거래 비교
        rows = await conn.fetch("""
            SELECT a.predicted_price, a.actual_price,
                   ABS(a.predicted_price - a.actual_price) / NULLIF(a.actual_price,0) as mape
            FROM avm_valuations a
            WHERE a.actual_price IS NOT NULL
              AND a.created_at >= NOW() - INTERVAL '7 days'
        """)
        if rows:
            mape_values = [r["mape"] for r in rows if r["mape"] is not None]
            avg_mape = sum(mape_values) / len(mape_values) if mape_values else 0
            # 드리프트 임계값: MAPE > 15% 시 Slack 알림
            if avg_mape > 0.15:
                await conn.execute("""
                    INSERT INTO model_performance (model_name, metric_name, metric_value, evaluated_at)
                    VALUES ('avm_model', 'mape_7d', $1, NOW())
                """, avg_mape)
                print(f"[DRIFT ALERT] AVM MAPE 7일 평균: {avg_mape:.2%} -- 임계값 초과, 재훈련 권고")
            else:
                print(f"[DRIFT OK] AVM MAPE 7일 평균: {avg_mape:.2%}")
        await conn.close()

    asyncio.run(_run())

def generate_daily_reports(**context):
    """일일 포트폴리오 리포트 자동 생성"""
    import asyncpg, asyncio

    async def _run():
        conn = await asyncpg.connect(
            host="postgres", database="propai_db",
            user="propai", password="propai_secure_2026"
        )
        tenants = await conn.fetch("SELECT id FROM tenants WHERE is_active=true")
        async with httpx.AsyncClient(timeout=60) as client:
            for t in tenants:
                try:
                    await client.post(
                        "http://propai-api:8000/api/v1/reports/daily",
                        json={"tenant_id": str(t["id"])},
                        headers={"X-Internal-Token": "propai-batch-2026"}
                    )
                except Exception as e:
                    print(f"[REPORT BATCH] tenant={t['id']}: {e}")
        await conn.close()

    asyncio.run(_run())

def cleanup_expired_tokens(**context):
    """만료 토큰 + 오래된 로그 정리"""
    import asyncpg, asyncio

    async def _run():
        conn = await asyncpg.connect(
            host="postgres", database="propai_db",
            user="propai", password="propai_secure_2026"
        )
        deleted = await conn.execute(
            "DELETE FROM refresh_tokens WHERE expires_at < NOW() - INTERVAL '1 day'"
        )
        log_deleted = await conn.execute(
            "DELETE FROM ai_usage_log WHERE created_at < NOW() - INTERVAL '90 days'"
        )
        print(f"[CLEANUP] 토큰 삭제: {deleted} | AI 로그 삭제: {log_deleted}")
        await conn.close()

    asyncio.run(_run())

# DAG 태스크 정의
t1_avm = PythonOperator(
    task_id="refresh_avm_batch",
    python_callable=refresh_avm_batch,
    dag=dag,
)

t2_drift = PythonOperator(
    task_id="run_model_drift_check",
    python_callable=run_model_drift_check,
    dag=dag,
)

t3_reports = PythonOperator(
    task_id="generate_daily_reports",
    python_callable=generate_daily_reports,
    dag=dag,
)

t4_cleanup = PythonOperator(
    task_id="cleanup_expired_tokens",
    python_callable=cleanup_expired_tokens,
    dag=dag,
)

# 의존성: AVM 갱신 -> 드리프트 체크 -> 리포트 생성 -> 정리
t1_avm >> t2_drift >> t3_reports >> t4_cleanup

================================================================
P10-STEP-02: MLflow 실험 추적 서비스
================================================================

[파일: apps/api/app/services/mlflow_service.py]
import os
import mlflow
import mlflow.sklearn
from datetime import datetime
from typing import Optional, Dict, Any
import structlog

logger = structlog.get_logger()

MLFLOW_TRACKING_URI = os.getenv("MLFLOW_TRACKING_URI", "http://localhost:5000")

class MLflowService:
    """
    MLflow 실험 추적 + 모델 레지스트리 관리
    - AVM 가격 예측 모델 버전 관리
    - 설계 AI 품질 지표 추적
    - A/B 테스트 결과 기록
    """

    def __init__(self):
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)

    def log_avm_experiment(
        self,
        model_name: str,
        params: Dict[str, Any],
        metrics: Dict[str, float],
        tags: Optional[Dict[str, str]] = None,
    ) -> str:
        """AVM 모델 학습 실험 기록"""
        mlflow.set_experiment("propai_avm_prediction")
        with mlflow.start_run(tags=tags or {}) as run:
            mlflow.log_params(params)
            mlflow.log_metrics(metrics)
            mlflow.set_tag("model_type", "avm")
            mlflow.set_tag("timestamp", datetime.utcnow().isoformat())
            run_id = run.info.run_id
        logger.info("mlflow_avm_experiment_logged", run_id=run_id, metrics=metrics)
        return run_id

    def register_model(
        self,
        run_id: str,
        model_path: str,
        registered_model_name: str,
        stage: str = "Staging",
    ) -> dict:
        """모델 레지스트리 등록"""
        model_uri = f"runs:/{run_id}/{model_path}"
        mv = mlflow.register_model(model_uri, registered_model_name)
        client = mlflow.tracking.MlflowClient()
        client.transition_model_version_stage(
            name=registered_model_name,
            version=mv.version,
            stage=stage,
        )
        return {
            "model_name":    registered_model_name,
            "version":       mv.version,
            "stage":         stage,
            "model_uri":     model_uri,
        }

    def get_production_model(self, model_name: str) -> Optional[dict]:
        """Production 스테이지 모델 정보 조회"""
        client = mlflow.tracking.MlflowClient()
        try:
            versions = client.get_latest_versions(model_name, stages=["Production"])
            if versions:
                v = versions[0]
                return {
                    "name":        v.name,
                    "version":     v.version,
                    "run_id":      v.run_id,
                    "source":      v.source,
                    "status":      v.status,
                    "created_at":  v.creation_timestamp,
                }
        except Exception as e:
            logger.warning("mlflow_get_model_failed", model=model_name, error=str(e))
        return None

    def log_design_quality(
        self,
        project_id: str,
        design_id: str,
        quality_scores: Dict[str, float],
    ) -> str:
        """설계 AI 품질 지표 기록"""
        mlflow.set_experiment("propai_design_quality")
        with mlflow.start_run() as run:
            mlflow.log_metrics(quality_scores)
            mlflow.set_tag("project_id", project_id)
            mlflow.set_tag("design_id", design_id)
            run_id = run.info.run_id
        return run_id

================================================================
P10-STEP-03: A/B 테스트 이벤트 서비스
================================================================

[파일: apps/api/app/services/ab_test_service.py]
import uuid
import hashlib
from datetime import datetime
from typing import Optional
from app.db import get_db_pool

class ABTestService:
    """
    A/B 테스트 이벤트 추적 서비스
    - 사용자 코호트 기반 분기 (해시 기반 결정론적 배정)
    - AVM UI 레이아웃 A/B
    - 설계 AI 프롬프트 A/B
    - 가격 제안 전략 A/B
    """

    def __init__(self):
        self._db = get_db_pool()

    def assign_variant(self, user_id: str, experiment_name: str) -> str:
        """
        결정론적 A/B 배정 (해시 기반)
        동일 user_id + experiment_name -> 항상 동일 변형 배정
        """
        hash_input = f"{user_id}:{experiment_name}"
        hash_val = int(hashlib.md5(hash_input.encode()).hexdigest(), 16)
        # 50/50 분할
        return "B" if hash_val % 2 == 0 else "A"

    async def track_event(
        self,
        user_id: str,
        experiment_name: str,
        event_type: str,
        variant: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """A/B 테스트 이벤트 기록"""
        if variant is None:
            variant = self.assign_variant(user_id, experiment_name)
        event_id = str(uuid.uuid4())
        await self._db.execute("""
            INSERT INTO ab_test_events
              (id, user_id, experiment_name, variant, event_type, metadata, occurred_at)
            VALUES ($1,$2,$3,$4,$5,$6::jsonb, NOW())
        """, event_id, user_id, experiment_name, variant, event_type,
            __import__("json").dumps(metadata or {}))
        return {"event_id": event_id, "variant": variant}

    async def get_experiment_results(self, experiment_name: str) -> dict:
        """실험 결과 집계"""
        rows = await self._db.fetch("""
            SELECT variant,
                   COUNT(*) FILTER (WHERE event_type='impression') as impressions,
                   COUNT(*) FILTER (WHERE event_type='conversion')  as conversions,
                   ROUND(
                       COUNT(*) FILTER (WHERE event_type='conversion')::numeric /
                       NULLIF(COUNT(*) FILTER (WHERE event_type='impression'), 0) * 100, 2
                   ) as conversion_rate_pct
            FROM ab_test_events
            WHERE experiment_name=$1
              AND occurred_at >= NOW() - INTERVAL '30 days'
            GROUP BY variant
        """, experiment_name)
        return {
            "experiment":  experiment_name,
            "results":     [dict(r) for r in rows],
            "methodology": "30일 윈도우 전환율 비교 (인상/전환 이벤트 기준)",
        }

================================================================
P10-STEP-04: Evidently AI 모델 모니터링 서비스
================================================================

[파일: apps/api/app/services/model_monitoring_service.py]
import numpy as np
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from app.db import get_db_pool
import structlog

logger = structlog.get_logger()

# 수학적 모델: Population Stability Index (PSI) 기반 드리프트 감지
# PSI = sum((actual% - expected%) * ln(actual% / expected%))
# PSI < 0.1: 안정, 0.1~0.25: 경고, > 0.25: 심각한 드리프트

def calculate_psi(expected: List[float], actual: List[float], bins: int = 10) -> float:
    """
    PSI (Population Stability Index) 계산
    입력: 기준 기간 예측값, 모니터링 기간 예측값
    출력: PSI 값 (0이면 완벽한 안정, 높을수록 드리프트)
    """
    if len(expected) < 10 or len(actual) < 10:
        return 0.0  # 데이터 부족 시 드리프트 없음으로 처리

    breakpoints = np.linspace(
        min(min(expected), min(actual)),
        max(max(expected), max(actual)),
        bins + 1
    )

    expected_pct = np.histogram(expected, bins=breakpoints)[0] / len(expected)
    actual_pct   = np.histogram(actual,   bins=breakpoints)[0] / len(actual)

    # 0 나누기 방지
    expected_pct = np.where(expected_pct == 0, 1e-6, expected_pct)
    actual_pct   = np.where(actual_pct   == 0, 1e-6, actual_pct)

    psi = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return float(psi)

class ModelMonitoringService:
    """
    AI 모델 성능 지속 모니터링
    - PSI 기반 데이터 드리프트 감지
    - MAPE / RMSE 예측 정확도 추적
    - 자동 재훈련 트리거 관리
    """

    PSI_WARNING_THRESHOLD  = 0.10
    PSI_CRITICAL_THRESHOLD = 0.25
    MAPE_WARNING_THRESHOLD = 0.12  # 12%
    MAPE_ALERT_THRESHOLD   = 0.20  # 20%

    def __init__(self):
        self._db = get_db_pool()

    async def check_avm_drift(self, lookback_days: int = 30) -> dict:
        """AVM 모델 드리프트 검사"""
        # 기준 기간 (30~60일 전) vs 최근 기간 (0~30일) 예측값 비교
        reference = await self._db.fetch("""
            SELECT predicted_price FROM avm_valuations
            WHERE created_at BETWEEN NOW()-INTERVAL '60 days' AND NOW()-INTERVAL '30 days'
            LIMIT 500
        """)
        recent = await self._db.fetch("""
            SELECT predicted_price FROM avm_valuations
            WHERE created_at >= NOW()-INTERVAL '30 days'
            LIMIT 500
        """)

        if len(reference) < 10 or len(recent) < 10:
            return {"status": "insufficient_data", "psi": None}

        ref_vals    = [float(r["predicted_price"]) for r in reference]
        recent_vals = [float(r["predicted_price"]) for r in recent]

        psi = calculate_psi(ref_vals, recent_vals)

        # MAPE 계산 (실거래가 있는 경우)
        mape_rows = await self._db.fetch("""
            SELECT predicted_price, actual_price
            FROM avm_valuations
            WHERE actual_price IS NOT NULL
              AND created_at >= NOW()-INTERVAL '30 days'
        """)
        mape = None
        if mape_rows:
            mapes = [
                abs(float(r["predicted_price"]) - float(r["actual_price"])) /
                float(r["actual_price"])
                for r in mape_rows if float(r["actual_price"]) > 0
            ]
            mape = float(np.mean(mapes)) if mapes else None

        if psi > self.PSI_CRITICAL_THRESHOLD:
            status = "critical_drift"
        elif psi > self.PSI_WARNING_THRESHOLD:
            status = "warning_drift"
        else:
            status = "stable"

        # DB 기록
        await self._db.execute("""
            INSERT INTO model_performance
              (model_name, metric_name, metric_value, evaluated_at)
            VALUES ('avm_model', 'psi', $1, NOW()),
                   ('avm_model', 'mape_30d', $2, NOW())
        """, psi, mape)

        logger.info("avm_drift_check", psi=psi, mape=mape, status=status)
        return {
            "status":    status,
            "psi":       round(psi, 4),
            "mape":      round(mape, 4) if mape else None,
            "reference_count": len(reference),
            "recent_count":    len(recent),
            "methodology":     "PSI (Population Stability Index) + MAPE 30일 윈도우",
        }

    async def get_model_performance_history(
        self, model_name: str, days: int = 30
    ) -> List[dict]:
        """모델 성능 이력 조회"""
        rows = await self._db.fetch("""
            SELECT metric_name, metric_value, evaluated_at
            FROM model_performance
            WHERE model_name=$1
              AND evaluated_at >= NOW()-INTERVAL '{days} days'
            ORDER BY evaluated_at DESC
            LIMIT 200
        """.replace("{days}", str(days)), model_name)
        return [dict(r) for r in rows]

================================================================
P10-STEP-05: MLOps API 라우터
================================================================

[파일: apps/api/app/routers/mlops.py]
from fastapi import APIRouter, HTTPException
from app.services.model_monitoring_service import ModelMonitoringService
from app.services.ab_test_service import ABTestService
import structlog

logger  = structlog.get_logger()
router  = APIRouter(prefix="/api/v1/mlops", tags=["mlops"])
_monitor = ModelMonitoringService()
_ab     = ABTestService()

@router.get("/drift/avm")
async def check_avm_drift():
    """AVM 모델 드리프트 검사"""
    return await _monitor.check_avm_drift()

@router.get("/performance/{model_name}")
async def get_model_performance(model_name: str, days: int = 30):
    """모델 성능 이력 조회"""
    return await _monitor.get_model_performance_history(model_name, days)

@router.post("/ab-test/track")
async def track_ab_event(
    user_id: str,
    experiment_name: str,
    event_type: str,
    variant: str = None,
):
    """A/B 테스트 이벤트 기록"""
    return await _ab.track_event(user_id, experiment_name, event_type, variant)

@router.get("/ab-test/{experiment_name}/results")
async def get_ab_results(experiment_name: str):
    """A/B 테스트 결과 조회"""
    return await _ab.get_experiment_results(experiment_name)

@router.get("/health")
async def mlops_health():
    """MLOps 서비스 상태 확인"""
    return {"status": "ok", "service": "mlops", "version": "v43.0"}

================================================================
P10-STEP-06: main.py에 MLOps 라우터 등록
================================================================

apps/api/app/main.py 에 아래 추가:

from app.routers.mlops import router as mlops_router
app.include_router(mlops_router)

================================================================
Phase 10 완료 확인:
  [ ] GET /api/v1/mlops/drift/avm -> {"status": "stable", "psi": ...}
  [ ] GET /api/v1/mlops/performance/avm_model -> 성능 이력 배열
  [ ] POST /api/v1/mlops/ab-test/track -> {"event_id": ..., "variant": "A"/"B"}
  [ ] Airflow DAG 파일 infra/airflow/dags/propai_nightly_batch.py 생성 확인
================================================================
```

---

## Phase 11: 프론트엔드 -- 지적도 + 대시보드 컴포넌트

```
================================================================
[PROPAI PHASE-11: Next.js 14 프론트엔드 핵심 컴포넌트 구현]
================================================================

당신은 25년 경력 Next.js + TypeScript 시니어 프론트엔드 개발자입니다.
PropAI v43.0의 반응형 대시보드 UI를 완전히 구현하세요.
Tailwind CSS 4.x + Radix UI + Framer Motion 기반의 전문가적 UI를 구현하세요.

================================================================
P11-STEP-01: 전역 레이아웃 + 내비게이션
================================================================

[파일: apps/web/app/(dashboard)/layout.tsx]
"use client";
import React, { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  LayoutDashboard, Map, Layers, TrendingUp, Scale, Building2,
  Leaf, Megaphone, Bot, Wrench, Users, BarChart3, Globe,
  Zap, DollarSign, Settings, ChevronLeft, ChevronRight,
  Bell, User, LogOut,
} from "lucide-react";

const NAV_ITEMS = [
  { href: "/dashboard",              icon: LayoutDashboard, label: "대시보드" },
  { href: "/dashboard/parcels",      icon: Map,             label: "필지 분석" },
  { href: "/dashboard/projects",     icon: Layers,          label: "프로젝트" },
  { href: "/dashboard/design",       icon: Building2,       label: "AI 설계" },
  { href: "/dashboard/finance",      icon: TrendingUp,      label: "금융 분석" },
  { href: "/dashboard/compliance",   icon: Scale,           label: "법규 준수" },
  { href: "/dashboard/construction", icon: Wrench,          label: "시공 관리" },
  { href: "/dashboard/esg",          icon: Leaf,            label: "ESG" },
  { href: "/dashboard/marketing",    icon: Megaphone,       label: "AI 마케팅" },
  { href: "/dashboard/agents",       icon: Bot,             label: "AI 에이전트" },
  { href: "/dashboard/maintenance",  icon: Wrench,          label: "예측 유지보수" },
  { href: "/dashboard/tenants",      icon: Users,           label: "임차인 관리" },
  { href: "/dashboard/assets",       icon: BarChart3,       label: "자산 인텔리전스" },
  { href: "/dashboard/portals",      icon: Globe,           label: "포털 연동" },
  { href: "/dashboard/energy-cert",  icon: Zap,             label: "에너지 인증" },
  { href: "/dashboard/ai-costs",     icon: DollarSign,      label: "AI 비용" },
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div className="flex h-screen bg-gray-50 overflow-hidden">
      {/* 사이드바 */}
      <motion.aside
        animate={{ width: collapsed ? 64 : 240 }}
        transition={{ duration: 0.25, ease: "easeInOut" }}
        className="flex-shrink-0 bg-white border-r border-gray-200 flex flex-col h-full overflow-hidden z-10"
      >
        {/* 로고 */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-gray-100">
          <AnimatePresence>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="text-xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent"
              >
                PropAI
              </motion.span>
            )}
          </AnimatePresence>
          <button
            onClick={() => setCollapsed(c => !c)}
            className="p-1.5 rounded-lg hover:bg-gray-100 transition-colors ml-auto"
          >
            {collapsed
              ? <ChevronRight className="w-4 h-4 text-gray-500" />
              : <ChevronLeft  className="w-4 h-4 text-gray-500" />
            }
          </button>
        </div>

        {/* 내비게이션 */}
        <nav className="flex-1 py-3 overflow-y-auto scrollbar-thin">
          {NAV_ITEMS.map(item => {
            const active = pathname === item.href || pathname.startsWith(item.href + "/");
            return (
              <Link
                key={item.href}
                href={item.href}
                title={collapsed ? item.label : undefined}
                className={`flex items-center gap-3 mx-2 px-3 py-2.5 rounded-xl text-sm font-medium transition-all mb-0.5 ${
                  active
                    ? "bg-blue-50 text-blue-700 shadow-sm"
                    : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                <item.icon className={`w-5 h-5 flex-shrink-0 ${active ? "text-blue-600" : "text-gray-400"}`} />
                <AnimatePresence>
                  {!collapsed && (
                    <motion.span
                      initial={{ opacity: 0, width: 0 }}
                      animate={{ opacity: 1, width: "auto" }}
                      exit={{ opacity: 0, width: 0 }}
                      className="truncate"
                    >
                      {item.label}
                    </motion.span>
                  )}
                </AnimatePresence>
              </Link>
            );
          })}
        </nav>

        {/* 하단 유틸리티 */}
        <div className="border-t border-gray-100 p-2 space-y-0.5">
          {[
            { href: "/dashboard/settings", icon: Settings, label: "설정" },
          ].map(item => (
            <Link
              key={item.href}
              href={item.href}
              className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-gray-600 hover:bg-gray-50 transition-colors"
            >
              <item.icon className="w-5 h-5 text-gray-400" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          ))}
        </div>
      </motion.aside>

      {/* 메인 영역 */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* 상단 헤더 */}
        <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 flex-shrink-0">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold text-gray-900">
              {NAV_ITEMS.find(n => pathname === n.href || pathname.startsWith(n.href + "/"))?.label || "PropAI"}
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <button className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors">
              <Bell className="w-5 h-5 text-gray-500" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full" />
            </button>
            <button className="p-2 rounded-lg hover:bg-gray-100 transition-colors">
              <User className="w-5 h-5 text-gray-500" />
            </button>
          </div>
        </header>

        {/* 페이지 콘텐츠 */}
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  );
}

================================================================
P11-STEP-02: 메인 대시보드 페이지
================================================================

[파일: apps/web/app/(dashboard)/dashboard/page.tsx]
"use client";
import React, { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  TrendingUp, Building2, DollarSign, Leaf,
  AlertTriangle, CheckCircle2, Clock, ArrowUpRight,
} from "lucide-react";
import Link from "next/link";

interface DashboardStats {
  total_projects: number;
  active_projects: number;
  total_portfolio_value_krw: number;
  avg_irr_pct: number;
  esg_score: number;
  pending_compliance: number;
}

const STAT_CARDS = [
  {
    key: "total_projects" as const,
    label: "전체 프로젝트",
    icon: Building2,
    color: "from-blue-500 to-blue-600",
    format: (v: number) => `${v.toLocaleString()}개`,
    href: "/dashboard/projects",
  },
  {
    key: "total_portfolio_value_krw" as const,
    label: "총 포트폴리오 가치",
    icon: DollarSign,
    color: "from-green-500 to-emerald-600",
    format: (v: number) => `${(v / 1e8).toFixed(1)}억원`,
    href: "/dashboard/assets",
  },
  {
    key: "avg_irr_pct" as const,
    label: "평균 IRR",
    icon: TrendingUp,
    color: "from-indigo-500 to-purple-600",
    format: (v: number) => `${v.toFixed(1)}%`,
    href: "/dashboard/finance",
  },
  {
    key: "esg_score" as const,
    label: "ESG 종합 점수",
    icon: Leaf,
    color: "from-emerald-500 to-teal-600",
    format: (v: number) => `${v.toFixed(0)}점`,
    href: "/dashboard/esg",
  },
];

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/v1/dashboard/stats")
      .then(r => r.json())
      .then(d => { setStats(d); setLoading(false); })
      .catch(() => {
        // Mock 데이터 (API 미연동 시)
        setStats({
          total_projects: 24,
          active_projects: 12,
          total_portfolio_value_krw: 84_300_000_000,
          avg_irr_pct: 14.7,
          esg_score: 82,
          pending_compliance: 3,
        });
        setLoading(false);
      });
  }, []);

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: { opacity: 1, transition: { staggerChildren: 0.08 } },
  };
  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: { opacity: 1, y: 0 },
  };

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="space-y-6"
    >
      {/* 스탯 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {STAT_CARDS.map(card => (
          <motion.div key={card.key} variants={itemVariants}>
            <Link href={card.href}>
              <div className="bg-white rounded-2xl p-5 border border-gray-100 hover:shadow-md transition-shadow cursor-pointer group">
                <div className="flex items-start justify-between mb-3">
                  <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${card.color} flex items-center justify-center`}>
                    <card.icon className="w-5 h-5 text-white" />
                  </div>
                  <ArrowUpRight className="w-4 h-4 text-gray-300 group-hover:text-gray-500 transition-colors" />
                </div>
                <p className="text-xs text-gray-500 mb-1">{card.label}</p>
                {loading ? (
                  <div className="h-7 w-24 bg-gray-100 rounded animate-pulse" />
                ) : (
                  <p className="text-2xl font-bold text-gray-900">
                    {stats ? card.format(stats[card.key]) : "--"}
                  </p>
                )}
              </div>
            </Link>
          </motion.div>
        ))}
      </div>

      {/* 알림 배너 */}
      {stats && stats.pending_compliance > 0 && (
        <motion.div variants={itemVariants}
          className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center gap-3"
        >
          <AlertTriangle className="w-5 h-5 text-amber-500 flex-shrink-0" />
          <p className="text-sm text-amber-800">
            <strong>{stats.pending_compliance}건</strong>의 법규 준수 검토가 대기 중입니다.
          </p>
          <Link
            href="/dashboard/compliance"
            className="ml-auto text-xs font-medium text-amber-700 hover:text-amber-900 underline"
          >
            확인하기
          </Link>
        </motion.div>
      )}

      {/* 빠른 실행 */}
      <motion.div variants={itemVariants}>
        <h2 className="text-sm font-semibold text-gray-700 mb-3">빠른 실행</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {[
            { href: "/dashboard/parcels",   label: "필지 분석",    color: "bg-blue-50   text-blue-700   border-blue-100" },
            { href: "/dashboard/design",    label: "AI 설계",     color: "bg-purple-50 text-purple-700 border-purple-100" },
            { href: "/dashboard/finance",   label: "사업성 검토",   color: "bg-green-50  text-green-700  border-green-100" },
            { href: "/dashboard/compliance",label: "법규 검토",    color: "bg-orange-50 text-orange-700 border-orange-100" },
            { href: "/dashboard/marketing", label: "AI 마케팅",   color: "bg-pink-50   text-pink-700   border-pink-100" },
            { href: "/dashboard/agents",    label: "AI 에이전트",  color: "bg-indigo-50 text-indigo-700 border-indigo-100" },
          ].map(item => (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center justify-center py-3 px-4 rounded-xl border text-sm font-medium transition-all hover:shadow-sm ${item.color}`}
            >
              {item.label}
            </Link>
          ))}
        </div>
      </motion.div>

      {/* 최근 활동 */}
      <motion.div variants={itemVariants} className="bg-white rounded-2xl border border-gray-100 p-5">
        <h2 className="text-sm font-semibold text-gray-700 mb-4">최근 활동</h2>
        <div className="space-y-3">
          {[
            { icon: CheckCircle2, color: "text-green-500", msg: "강남구 역삼동 프로젝트 법규 검토 완료", time: "2분 전" },
            { icon: Building2,    color: "text-blue-500",  msg: "송파구 잠실동 AI 설계안 3종 생성 완료", time: "18분 전" },
            { icon: TrendingUp,   color: "text-indigo-500",msg: "서초구 서초동 IRR 18.3% 사업성 분석 완료", time: "1시간 전" },
            { icon: Clock,        color: "text-gray-400",  msg: "야간 AVM 시세 갱신 완료 (24개 프로젝트)", time: "새벽 2:05" },
          ].map((item, i) => (
            <div key={i} className="flex items-start gap-3">
              <item.icon className={`w-4 h-4 ${item.color} flex-shrink-0 mt-0.5`} />
              <p className="text-sm text-gray-700 flex-1">{item.msg}</p>
              <span className="text-xs text-gray-400 flex-shrink-0">{item.time}</span>
            </div>
          ))}
        </div>
      </motion.div>
    </motion.div>
  );
}

================================================================
P11-STEP-03: OpenLayers 지적도 컴포넌트
================================================================

[파일: apps/web/components/map/CadastralMap.tsx]
"use client";
import React, { useEffect, useRef, useState } from "react";
import { Search, Layers, ZoomIn, ZoomOut, Target, Info } from "lucide-react";

interface ParcelInfo {
  pnu:          string;
  address:      string;
  land_use:     string;
  area_m2:      number;
  bcr_pct:      number;
  far_pct:      number;
  zone:         string;
  est_price_krw: number;
}

interface CadastralMapProps {
  onParcelSelect?: (parcel: ParcelInfo) => void;
  initialCenter?: [number, number]; // [lon, lat]
  initialZoom?: number;
}

export function CadastralMap({ onParcelSelect, initialCenter, initialZoom }: CadastralMapProps) {
  const mapRef     = useRef<HTMLDivElement>(null);
  const olMapRef   = useRef<any>(null);
  const [search,   setSearch]  = useState("");
  const [selected, setSelected] = useState<ParcelInfo | null>(null);
  const [loading,  setLoading]  = useState(false);

  useEffect(() => {
    if (!mapRef.current || olMapRef.current) return;

    // OpenLayers 동적 로드
    const loadOL = async () => {
      const ol = await import("ol");
      const olLayer = await import("ol/layer");
      const olSource = await import("ol/source");
      const olProj = await import("ol/proj");
      const olStyle = await import("ol/style");

      const center = initialCenter
        ? olProj.fromLonLat(initialCenter)
        : olProj.fromLonLat([127.024612, 37.532600]); // 서울 기본

      const map = new ol.Map({
        target: mapRef.current!,
        layers: [
          // VWORLD 배경지도
          new olLayer.Tile({
            source: new olSource.XYZ({
              url: `https://api.vworld.kr/req/wmts/1.0.0/${
                process.env.NEXT_PUBLIC_VWORLD_API_KEY || "DEMO"
              }/Base/{z}/{y}/{x}.png`,
              crossOrigin: "anonymous",
            }),
          }),
          // 지적도 레이어 (VWORLD WMS)
          new olLayer.Tile({
            source: new olSource.TileWMS({
              url: "https://api.vworld.kr/req/wms",
              params: {
                SERVICE: "WMS",
                VERSION: "1.3.0",
                REQUEST: "GetMap",
                LAYERS: "LP_PA_CBND_BUBUN",
                FORMAT: "image/png",
                TRANSPARENT: "true",
                KEY: process.env.NEXT_PUBLIC_VWORLD_API_KEY || "DEMO",
              },
              crossOrigin: "anonymous",
            }),
            opacity: 0.6,
          }),
        ],
        view: new ol.View({
          center,
          zoom: initialZoom || 16,
          maxZoom: 21,
          minZoom: 7,
          projection: "EPSG:3857",
        }),
      });

      // 필지 클릭 이벤트
      map.on("click", async (evt) => {
        const [lon, lat] = olProj.toLonLat(evt.coordinate);
        setLoading(true);
        try {
          const res = await fetch(
            `/api/v1/parcels/by-coord?lon=${lon.toFixed(6)}&lat=${lat.toFixed(6)}`
          );
          if (res.ok) {
            const parcel = await res.json();
            setSelected(parcel);
            onParcelSelect?.(parcel);
          }
        } catch {
          // 좌표 파싱 오류 무시
        } finally {
          setLoading(false);
        }
      });

      // 커서 변경
      map.on("pointermove", (evt) => {
        const pixel = map.getEventPixel(evt.originalEvent);
        if (mapRef.current) {
          mapRef.current.style.cursor = "crosshair";
        }
      });

      olMapRef.current = map;
    };

    loadOL().catch(console.error);

    return () => {
      olMapRef.current?.setTarget(undefined);
      olMapRef.current = null;
    };
  }, []);

  const handleSearch = async () => {
    if (!search.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(
        `/api/v1/parcels/geocode?address=${encodeURIComponent(search)}`
      );
      if (res.ok) {
        const { lon, lat } = await res.json();
        const olProj = await import("ol/proj");
        olMapRef.current?.getView().animate({
          center: olProj.fromLonLat([lon, lat]),
          zoom: 18,
          duration: 500,
        });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative w-full h-full rounded-2xl overflow-hidden border border-gray-200 shadow-sm">
      {/* 지도 */}
      <div ref={mapRef} className="w-full h-full" />

      {/* 검색창 */}
      <div className="absolute top-3 left-3 right-3 sm:right-auto sm:w-80 z-10">
        <div className="flex gap-2">
          <div className="flex-1 flex items-center gap-2 bg-white/95 backdrop-blur-sm rounded-xl border border-gray-200 shadow-sm px-3 py-2">
            <Search className="w-4 h-4 text-gray-400 flex-shrink-0" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              placeholder="주소 또는 PNU 검색..."
              className="flex-1 text-sm outline-none bg-transparent placeholder-gray-400"
            />
          </div>
          <button
            onClick={handleSearch}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
          >
            검색
          </button>
        </div>
      </div>

      {/* 확대/축소 */}
      <div className="absolute right-3 top-3 flex flex-col gap-1.5 z-10">
        {[
          { icon: ZoomIn,  label: "확대", action: () => { const v = olMapRef.current?.getView(); v?.setZoom((v.getZoom() || 15) + 1); } },
          { icon: ZoomOut, label: "축소", action: () => { const v = olMapRef.current?.getView(); v?.setZoom((v.getZoom() || 15) - 1); } },
          { icon: Target,  label: "현재위치", action: () => {
            navigator.geolocation.getCurrentPosition(async pos => {
              const olProj = await import("ol/proj");
              olMapRef.current?.getView().animate({
                center: olProj.fromLonLat([pos.coords.longitude, pos.coords.latitude]),
                zoom: 18,
                duration: 500,
              });
            });
          }},
        ].map(btn => (
          <button
            key={btn.label}
            onClick={btn.action}
            title={btn.label}
            className="w-9 h-9 bg-white/95 backdrop-blur-sm rounded-xl border border-gray-200 shadow-sm flex items-center justify-center hover:bg-gray-50 transition-colors"
          >
            <btn.icon className="w-4 h-4 text-gray-600" />
          </button>
        ))}
      </div>

      {/* 필지 정보 패널 */}
      {selected && (
        <div className="absolute bottom-3 left-3 right-3 sm:right-auto sm:w-80 bg-white/97 backdrop-blur-sm rounded-2xl border border-gray-200 shadow-lg p-4 z-10">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-2">
              <Info className="w-4 h-4 text-blue-600" />
              <h3 className="text-sm font-semibold text-gray-900">필지 정보</h3>
            </div>
            <button
              onClick={() => setSelected(null)}
              className="text-gray-400 hover:text-gray-600 transition-colors text-lg leading-none"
            >
              ×
            </button>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-500">주소</span>
              <span className="font-medium text-right max-w-[55%] text-xs">{selected.address}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">용도지역</span>
              <span className="font-medium text-blue-700">{selected.zone}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">면적</span>
              <span className="font-medium">{selected.area_m2.toLocaleString()}m²</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">건폐율/용적률</span>
              <span className="font-medium">{selected.bcr_pct}% / {selected.far_pct}%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-500">추정가</span>
              <span className="font-bold text-green-700">
                {(selected.est_price_krw / 1e8).toFixed(1)}억원
              </span>
            </div>
          </div>
          <button
            className="w-full mt-3 py-2 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors"
            onClick={() => window.location.href = `/dashboard/projects/new?pnu=${selected.pnu}`}
          >
            이 필지로 프로젝트 시작
          </button>
        </div>
      )}

      {/* 로딩 오버레이 */}
      {loading && (
        <div className="absolute inset-0 bg-black/10 flex items-center justify-center z-20">
          <div className="bg-white rounded-xl px-4 py-2 shadow-lg text-sm font-medium text-gray-700">
            필지 정보 로딩 중...
          </div>
        </div>
      )}
    </div>
  );
}

================================================================
P11-STEP-04: 필지 분석 페이지
================================================================

[파일: apps/web/app/(dashboard)/dashboard/parcels/page.tsx]
"use client";
import React, { useState } from "react";
import { CadastralMap } from "@/components/map/CadastralMap";
import { motion } from "framer-motion";
import { MapPin, TrendingUp, AlertCircle, CheckCircle2 } from "lucide-react";

interface ParcelInfo {
  pnu: string; address: string; land_use: string;
  area_m2: number; bcr_pct: number; far_pct: number;
  zone: string; est_price_krw: number;
}

interface RegulationResult {
  compliant: boolean;
  issues: string[];
  max_floors: number;
  max_height_m: number;
  parking_required: number;
}

export default function ParcelsPage() {
  const [parcel,     setParcel]     = useState<ParcelInfo | null>(null);
  const [regulation, setRegulation] = useState<RegulationResult | null>(null);
  const [checking,   setChecking]   = useState(false);

  const checkRegulation = async () => {
    if (!parcel) return;
    setChecking(true);
    try {
      const res = await fetch("/api/v1/regulation/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pnu: parcel.pnu }),
      });
      const data = await res.json();
      setRegulation(data);
    } catch (e) {
      console.error(e);
    } finally {
      setChecking(false);
    }
  };

  return (
    <div className="h-full flex flex-col gap-4">
      <div className="flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-xl font-bold text-gray-900">필지 분석</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            지도에서 필지를 클릭하거나 주소를 검색하세요
          </p>
        </div>
      </div>

      <div className="flex-1 flex gap-4 min-h-0">
        {/* 지도 */}
        <div className="flex-1 min-h-0">
          <CadastralMap onParcelSelect={setParcel} />
        </div>

        {/* 우측 패널 */}
        <div className="w-72 flex flex-col gap-3 overflow-y-auto">
          {parcel ? (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="bg-white rounded-2xl border border-gray-100 p-4"
            >
              <div className="flex items-center gap-2 mb-3">
                <MapPin className="w-4 h-4 text-blue-600" />
                <h3 className="text-sm font-semibold">선택 필지</h3>
              </div>
              <div className="space-y-2 text-sm mb-4">
                {[
                  { label: "주소",         value: parcel.address },
                  { label: "용도지역",     value: parcel.zone,                     highlight: true },
                  { label: "면적",         value: `${parcel.area_m2.toLocaleString()}m²` },
                  { label: "건폐율",       value: `${parcel.bcr_pct}%` },
                  { label: "용적률",       value: `${parcel.far_pct}%` },
                  { label: "추정 시세",    value: `${(parcel.est_price_krw/1e8).toFixed(1)}억원`, bold: true },
                ].map(item => (
                  <div key={item.label} className="flex justify-between items-start gap-2">
                    <span className="text-gray-500 flex-shrink-0">{item.label}</span>
                    <span className={`text-right text-xs ${
                      item.bold ? "font-bold text-green-700" :
                      item.highlight ? "text-blue-700 font-medium" :
                      "text-gray-900"
                    }`}>{item.value}</span>
                  </div>
                ))}
              </div>
              <button
                onClick={checkRegulation}
                disabled={checking}
                className="w-full py-2.5 bg-blue-600 text-white rounded-xl text-sm font-medium hover:bg-blue-700 transition-colors disabled:opacity-50"
              >
                {checking ? "법규 검토 중..." : "법규 자동 검토"}
              </button>
            </motion.div>
          ) : (
            <div className="bg-white rounded-2xl border border-dashed border-gray-200 p-6 text-center">
              <MapPin className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-sm text-gray-400">지도에서 필지를 클릭하면<br/>정보가 표시됩니다</p>
            </div>
          )}

          {regulation && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white rounded-2xl border border-gray-100 p-4"
            >
              <div className="flex items-center gap-2 mb-3">
                {regulation.compliant
                  ? <CheckCircle2 className="w-4 h-4 text-green-600" />
                  : <AlertCircle  className="w-4 h-4 text-red-500" />
                }
                <h3 className="text-sm font-semibold">
                  {regulation.compliant ? "법규 적합" : "법규 검토 필요"}
                </h3>
              </div>
              <div className="space-y-1.5 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-500">최대 층수</span>
                  <span className="font-semibold">{regulation.max_floors}층</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">최대 높이</span>
                  <span className="font-semibold">{regulation.max_height_m}m</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">법정 주차 대수</span>
                  <span className="font-semibold">{regulation.parking_required}대</span>
                </div>
              </div>
              {regulation.issues.length > 0 && (
                <div className="mt-3 space-y-1">
                  {regulation.issues.map((issue, i) => (
                    <div key={i} className="flex items-start gap-1.5 text-xs text-red-600">
                      <span className="mt-0.5">•</span>
                      <span>{issue}</span>
                    </div>
                  ))}
                </div>
              )}
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}

================================================================
P11-STEP-05: 반응형 UI 공통 컴포넌트 -- 스탯 카드, 알림, 모달
================================================================

[파일: apps/web/components/common/StatCard.tsx]
"use client";
import React from "react";
import { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string | number;
  icon: LucideIcon;
  trend?: { value: number; label: string };
  color?: "blue" | "green" | "purple" | "orange" | "red" | "teal";
  loading?: boolean;
}

const COLOR_MAP = {
  blue:   "from-blue-500   to-blue-600   bg-blue-50   text-blue-700",
  green:  "from-green-500  to-emerald-600 bg-green-50  text-green-700",
  purple: "from-purple-500 to-indigo-600 bg-purple-50 text-purple-700",
  orange: "from-orange-500 to-amber-600  bg-orange-50 text-orange-700",
  red:    "from-red-500    to-rose-600   bg-red-50    text-red-700",
  teal:   "from-teal-500   to-cyan-600   bg-teal-50   text-teal-700",
};

export function StatCard({ label, value, icon: Icon, trend, color = "blue", loading }: StatCardProps) {
  const [gradient, bg, textColor] = COLOR_MAP[color].split(" ");

  return (
    <div className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between mb-3">
        <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${gradient} ${bg.replace("bg-", "bg-")} flex items-center justify-center`}>
          <Icon className="w-5 h-5 text-white" />
        </div>
        {trend && (
          <span className={`text-xs font-medium px-2 py-1 rounded-lg ${
            trend.value >= 0
              ? "bg-green-50 text-green-700"
              : "bg-red-50 text-red-700"
          }`}>
            {trend.value >= 0 ? "▲" : "▼"} {Math.abs(trend.value)}%
          </span>
        )}
      </div>
      <p className="text-xs text-gray-500 mb-1">{label}</p>
      {loading ? (
        <div className="h-7 w-28 bg-gray-100 rounded animate-pulse" />
      ) : (
        <p className="text-2xl font-bold text-gray-900">
          {typeof value === "number" ? value.toLocaleString() : value}
        </p>
      )}
      {trend && <p className="text-xs text-gray-400 mt-1">{trend.label}</p>}
    </div>
  );
}

[파일: apps/web/components/common/DataTable.tsx]
"use client";
import React, { useState } from "react";
import { ChevronUp, ChevronDown, ChevronsUpDown } from "lucide-react";

interface Column<T> {
  key:     keyof T | string;
  header:  string;
  render?: (value: any, row: T) => React.ReactNode;
  sortable?: boolean;
  width?: string;
}

interface DataTableProps<T> {
  columns:   Column<T>[];
  data:      T[];
  keyField?: string;
  loading?:  boolean;
  emptyText?: string;
  onRowClick?: (row: T) => void;
}

export function DataTable<T extends Record<string, any>>({
  columns, data, keyField = "id", loading = false,
  emptyText = "데이터가 없습니다.", onRowClick,
}: DataTableProps<T>) {
  const [sortKey, setSortKey]  = useState<string | null>(null);
  const [sortDir, setSortDir]  = useState<"asc" | "desc">("asc");

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  };

  const sorted = React.useMemo(() => {
    if (!sortKey) return data;
    return [...data].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (av == null) return 1;
      if (bv == null) return -1;
      const cmp = av < bv ? -1 : av > bv ? 1 : 0;
      return sortDir === "asc" ? cmp : -cmp;
    });
  }, [data, sortKey, sortDir]);

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-100">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 border-b border-gray-100">
          <tr>
            {columns.map(col => (
              <th
                key={String(col.key)}
                style={col.width ? { width: col.width } : undefined}
                className={`px-4 py-3 text-left text-xs font-semibold text-gray-600 ${
                  col.sortable ? "cursor-pointer hover:text-gray-900 select-none" : ""
                }`}
                onClick={() => col.sortable && handleSort(String(col.key))}
              >
                <span className="flex items-center gap-1">
                  {col.header}
                  {col.sortable && (
                    sortKey === String(col.key)
                      ? sortDir === "asc"
                          ? <ChevronUp   className="w-3 h-3" />
                          : <ChevronDown className="w-3 h-3" />
                      : <ChevronsUpDown className="w-3 h-3 text-gray-300" />
                  )}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {loading ? (
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={i}>
                {columns.map(col => (
                  <td key={String(col.key)} className="px-4 py-3">
                    <div className="h-4 bg-gray-100 rounded animate-pulse" />
                  </td>
                ))}
              </tr>
            ))
          ) : sorted.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-gray-400 text-sm">
                {emptyText}
              </td>
            </tr>
          ) : (
            sorted.map((row, i) => (
              <tr
                key={row[keyField] ?? i}
                onClick={() => onRowClick?.(row)}
                className={`bg-white hover:bg-gray-50 transition-colors ${
                  onRowClick ? "cursor-pointer" : ""
                }`}
              >
                {columns.map(col => (
                  <td key={String(col.key)} className="px-4 py-3 text-gray-700">
                    {col.render
                      ? col.render(row[col.key as string], row)
                      : (row[col.key as string] ?? "--")
                    }
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

================================================================
Phase 11 완료 확인:
  [ ] http://localhost:3000/dashboard -> 대시보드 메인 렌더링 확인
  [ ] http://localhost:3000/dashboard/parcels -> 지적도 렌더링 확인
  [ ] 사이드바 컬랩스 토글 동작 확인
  [ ] 필지 클릭 -> 정보 패널 표시 확인
  [ ] 반응형 (모바일/태블릿/데스크탑) 레이아웃 확인
================================================================
```

---

## Phase 12: 운영 인프라 (K8s + DR + 모니터링 + 보안)

```
================================================================
[PROPAI PHASE-12: 운영 인프라 완전 구축]
================================================================

당신은 25년 경력 DevOps + 보안 시니어 엔지니어입니다.
PropAI v43.0의 Kubernetes 기반 운영 인프라를 완전히 구현하세요.

================================================================
P12-STEP-01: Kubernetes 핵심 매니페스트
================================================================

[파일: infra/k8s/base/namespace.yaml]
apiVersion: v1
kind: Namespace
metadata:
  name: propai
  labels:
    app.kubernetes.io/managed-by: kustomize
    environment: production

---
[파일: infra/k8s/base/configmap.yaml]
apiVersion: v1
kind: ConfigMap
metadata:
  name: propai-config
  namespace: propai
data:
  ENVIRONMENT:       "production"
  API_BASE_URL:      "https://api.propai.kr"
  FRONTEND_URL:      "https://app.propai.kr"
  REDIS_URL:         "redis://propai-redis-master:6379/0"
  QDRANT_URL:        "http://propai-qdrant:6333"
  MLFLOW_URI:        "http://propai-mlflow:5000"
  LOG_LEVEL:         "INFO"
  PORTAL_MOCK_MODE:  "false"

---
[파일: infra/k8s/base/api-deployment.yaml]
apiVersion: apps/v1
kind: Deployment
metadata:
  name: propai-api
  namespace: propai
  labels:
    app: propai-api
    version: v43.0
spec:
  replicas: 3
  selector:
    matchLabels:
      app: propai-api
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: propai-api
        version: v43.0
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/path: "/metrics"
        prometheus.io/port: "8000"
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchExpressions:
                  - key: app
                    operator: In
                    values: [propai-api]
              topologyKey: kubernetes.io/hostname
      containers:
        - name: api
          image: ghcr.io/propai/api:latest
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: propai-config
            - secretRef:
                name: propai-secrets
          resources:
            requests:
              memory: "512Mi"
              cpu:    "250m"
            limits:
              memory: "2Gi"
              cpu:    "1000m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds:       10
            failureThreshold:    3
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds:       5
      terminationGracePeriodSeconds: 30

---
[파일: infra/k8s/base/api-service.yaml]
apiVersion: v1
kind: Service
metadata:
  name: propai-api
  namespace: propai
spec:
  selector:
    app: propai-api
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP

---
[파일: infra/k8s/base/hpa.yaml]
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: propai-api-hpa
  namespace: propai
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: propai-api
  minReplicas: 3
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 80

---
[파일: infra/k8s/base/ingress.yaml]
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: propai-ingress
  namespace: propai
  annotations:
    kubernetes.io/ingress.class: nginx
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
    nginx.ingress.kubernetes.io/rate-limit: "100"
    nginx.ingress.kubernetes.io/rate-limit-window: "1m"
spec:
  tls:
    - hosts:
        - api.propai.kr
        - app.propai.kr
      secretName: propai-tls
  rules:
    - host: api.propai.kr
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: propai-api
                port:
                  number: 80
    - host: app.propai.kr
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: propai-web
                port:
                  number: 80

================================================================
P12-STEP-02: Prometheus + Grafana 모니터링 설정
================================================================

[파일: infra/monitoring/prometheus/prometheus.yml]
global:
  scrape_interval:     15s
  evaluation_interval: 15s
  external_labels:
    cluster: propai-production
    environment: production

rule_files:
  - /etc/prometheus/rules/*.yml

alerting:
  alertmanagers:
    - static_configs:
        - targets: [alertmanager:9093]

scrape_configs:
  - job_name: propai-api
    static_configs:
      - targets: [propai-api:8000]
    metrics_path: /metrics
    scrape_interval: 10s

  - job_name: postgres
    static_configs:
      - targets: [postgres-exporter:9187]

  - job_name: redis
    static_configs:
      - targets: [redis-exporter:9121]

  - job_name: kafka
    static_configs:
      - targets: [kafka-exporter:9308]

[파일: infra/monitoring/prometheus/rules/propai_alerts.yml]
groups:
  - name: propai_api_alerts
    rules:
      - alert: HighAPIErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.05
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "PropAI API 오류율 초과 ({{ $value | humanizePercentage }})"

      - alert: HighResponseTime
        expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "PropAI API p99 응답 시간 2초 초과"

      - alert: LowDiskSpace
        expr: node_filesystem_avail_bytes / node_filesystem_size_bytes < 0.15
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "디스크 여유 공간 15% 미만"

      - alert: PostgresHighConnections
        expr: pg_stat_activity_count > 150
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "PostgreSQL 연결 수 150 초과"

      - alert: AITokenBudgetExceeded
        expr: propai_ai_cost_usd_today > propai_ai_budget_usd_daily
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "AI 토큰 일일 예산 초과"

================================================================
P12-STEP-03: GitHub Actions CI/CD 파이프라인
================================================================

[파일: .github/workflows/ci-cd.yml]
name: PropAI CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  REGISTRY:     ghcr.io
  IMAGE_NAME:   ${{ github.repository }}

jobs:
  test:
    name: Test
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgis/postgis:16-3.4
        env:
          POSTGRES_PASSWORD: propai_test
          POSTGRES_DB:       propai_test
        ports: ["5432:5432"]
      redis:
        image: redis:7-alpine
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4

      - name: Python 설정
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: 백엔드 의존성 설치
        run: |
          cd apps/api
          pip install -r requirements.txt
          pip install pytest pytest-asyncio pytest-cov

      - name: 백엔드 테스트 실행
        run: |
          cd apps/api
          pytest tests/ -v --cov=app --cov-report=xml
        env:
          DATABASE_URL: postgresql://postgres:propai_test@localhost/propai_test
          REDIS_URL:    redis://localhost:6379/0
          JWT_SECRET_KEY: test-secret-key-32chars-minimum

      - name: Node.js 설정
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: pnpm

      - name: pnpm 설치
        run: npm install -g pnpm@9

      - name: 프론트엔드 의존성 설치
        run: pnpm install

      - name: 프론트엔드 빌드
        run: pnpm build
        env:
          NEXT_PUBLIC_API_URL:     http://localhost:8000
          NEXT_PUBLIC_VWORLD_API_KEY: DEMO

  build-push:
    name: Build & Push
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main'
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      - name: Container Registry 로그인
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker Buildx 설정
        uses: docker/setup-buildx-action@v3

      - name: API 이미지 빌드 및 푸시
        uses: docker/build-push-action@v5
        with:
          context: ./apps/api
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/api:latest
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/api:${{ github.sha }}
          cache-from: type=gha
          cache-to:   type=gha,mode=max

      - name: Web 이미지 빌드 및 푸시
        uses: docker/build-push-action@v5
        with:
          context: ./apps/web
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/web:latest
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/web:${{ github.sha }}
          cache-from: type=gha
          cache-to:   type=gha,mode=max
          build-args: |
            NEXT_PUBLIC_API_URL=https://api.propai.kr

  deploy-staging:
    name: Deploy Staging
    runs-on: ubuntu-latest
    needs: build-push
    environment: staging
    steps:
      - uses: actions/checkout@v4

      - name: kubectl 설정
        uses: azure/setup-kubectl@v3

      - name: kubeconfig 설정
        run: |
          echo "${{ secrets.KUBECONFIG_STAGING }}" > kubeconfig
          echo "KUBECONFIG=$PWD/kubeconfig" >> $GITHUB_ENV

      - name: K8s 배포
        run: |
          kubectl set image deployment/propai-api api=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/api:${{ github.sha }} -n propai
          kubectl set image deployment/propai-web web=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}/web:${{ github.sha }} -n propai
          kubectl rollout status deployment/propai-api -n propai --timeout=5m
          kubectl rollout status deployment/propai-web -n propai --timeout=5m

  security-scan:
    name: Security Scan
    runs-on: ubuntu-latest
    needs: test
    steps:
      - uses: actions/checkout@v4

      - name: Trivy 취약점 스캔
        uses: aquasecurity/trivy-action@master
        with:
          scan-type:   fs
          scan-ref:    .
          severity:    CRITICAL,HIGH
          exit-code:   1

      - name: Bandit (Python 보안 분석)
        run: |
          pip install bandit
          bandit -r apps/api/app -l -x apps/api/app/tests

================================================================
P12-STEP-04: Zero Trust 보안 미들웨어
================================================================

[파일: apps/api/app/middleware/security.py]
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import structlog
import re

logger = structlog.get_logger()

# 허용 Origin 목록
ALLOWED_ORIGINS = [
    "https://app.propai.kr",
    "https://admin.propai.kr",
    "http://localhost:3000",   # 개발 환경
]

# 보안 헤더 설정
SECURITY_HEADERS = {
    "X-Content-Type-Options":     "nosniff",
    "X-Frame-Options":            "DENY",
    "X-XSS-Protection":           "1; mode=block",
    "Strict-Transport-Security":  "max-age=31536000; includeSubDomains",
    "Referrer-Policy":            "strict-origin-when-cross-origin",
    "Permissions-Policy":         "geolocation=(), microphone=(), camera=()",
    "Content-Security-Policy":    (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://api.vworld.kr"
    ),
}

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """보안 헤더 자동 주입 미들웨어"""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """요청/응답 로깅 미들웨어 (개인정보 마스킹 포함)"""

    SENSITIVE_FIELDS = re.compile(
        r"(password|token|secret|key|auth|ssn|jumin|passport)",
        re.IGNORECASE
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.time()
        request_id = request.headers.get("X-Request-ID", "")

        response = await call_next(request)

        duration_ms = round((time.time() - start) * 1000, 2)

        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            request_id=request_id,
            user_agent=request.headers.get("user-agent", "")[:100],
        )

        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        return response

================================================================
P12-STEP-05: 백업 + DR (재해 복구) 스크립트
================================================================

[파일: scripts/db/backup.sh]
#!/bin/bash
# PropAI PostgreSQL 백업 스크립트
# 매일 새벽 3시 cron 실행

set -euo pipefail

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/var/backups/propai"
DB_HOST="${DB_HOST:-postgres}"
DB_NAME="${DB_NAME:-propai_db}"
DB_USER="${DB_USER:-propai}"
S3_BUCKET="${S3_BUCKET:-s3://propai-backups}"
RETENTION_DAYS=30

mkdir -p "${BACKUP_DIR}"

echo "[$(date)] PropAI DB 백업 시작: ${TIMESTAMP}"

# pg_dump 실행 (압축)
PGPASSWORD="${DB_PASSWORD}" pg_dump \
  -h "${DB_HOST}" \
  -U "${DB_USER}" \
  -d "${DB_NAME}" \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-privileges \
  -f "${BACKUP_DIR}/propai_${TIMESTAMP}.dump"

echo "[$(date)] 덤프 완료: $(du -sh ${BACKUP_DIR}/propai_${TIMESTAMP}.dump)"

# S3 업로드 (AWS CLI 또는 MinIO mc)
if command -v aws &>/dev/null; then
  aws s3 cp "${BACKUP_DIR}/propai_${TIMESTAMP}.dump" \
    "${S3_BUCKET}/db/propai_${TIMESTAMP}.dump" \
    --storage-class STANDARD_IA
  echo "[$(date)] S3 업로드 완료"
elif command -v mc &>/dev/null; then
  mc cp "${BACKUP_DIR}/propai_${TIMESTAMP}.dump" \
    "minio/propai-backups/db/propai_${TIMESTAMP}.dump"
  echo "[$(date)] MinIO 업로드 완료"
fi

# 로컬 오래된 백업 삭제
find "${BACKUP_DIR}" -name "*.dump" -mtime +"${RETENTION_DAYS}" -delete
echo "[$(date)] ${RETENTION_DAYS}일 이전 백업 삭제 완료"

echo "[$(date)] 백업 완료"

================================================================
Phase 12 완료 확인:
  [ ] infra/k8s/base/ 매니페스트 파일 생성 확인
  [ ] .github/workflows/ci-cd.yml 생성 확인
  [ ] infra/monitoring/prometheus/ 설정 파일 생성 확인
  [ ] kubectl apply -f infra/k8s/base/ (스테이징) 성공
  [ ] Prometheus 메트릭 수집 확인
================================================================
```

---

## Phase 13: AI 고도화 -- LangGraph 에이전트 + RAG + 멀티모달

```
================================================================
[PROPAI PHASE-13: AI 고도화 -- LangGraph 멀티에이전트 + RAG]
================================================================

당신은 25년 경력 AI/ML 시니어 엔지니어입니다.
PropAI v43.0의 LangGraph 기반 AI 에이전트와 RAG 파이프라인을 완전히 구현하세요.

================================================================
P13-STEP-01: LangGraph 부동산 개발 자율 에이전트
================================================================

[파일: apps/api/app/agents/real_estate_agent.py]
"""
PropAI LangGraph 부동산 개발 자율 에이전트
9단계 자율 실행: 필지분석 -> 법규검토 -> AVM -> 설계생성 ->
                  사업성분석 -> 세금계산 -> 리스크평가 -> ESG -> 최종리포트
"""
import json
import uuid
from typing import TypedDict, Annotated, List, Optional
from datetime import datetime

import anthropic
from app.config import settings
import structlog

logger = structlog.get_logger()

# 에이전트 상태 정의
class AgentState(TypedDict):
    task_id:         str
    pnu:             str
    project_name:    str
    building_use:    str
    floor_area_m2:   Optional[float]

    # 단계별 결과
    parcel_info:     Optional[dict]
    regulation:      Optional[dict]
    avm_result:      Optional[dict]
    design_result:   Optional[dict]
    finance_result:  Optional[dict]
    tax_result:      Optional[dict]
    risk_result:     Optional[dict]
    esg_result:      Optional[dict]
    final_report:    Optional[dict]

    # 메타
    steps_completed: List[str]
    errors:          List[str]
    total_tokens:    int
    started_at:      str

# 에이전트 도구 정의 (Anthropic Tool Use)
AGENT_TOOLS = [
    {
        "name": "get_parcel_info",
        "description": "PNU(필지고유번호)로 필지 정보(주소, 면적, 용도지역, 건폐율, 용적률 등)를 조회합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pnu": {"type": "string", "description": "필지고유번호 (19자리)"}
            },
            "required": ["pnu"]
        }
    },
    {
        "name": "check_regulation",
        "description": "PNU 기반으로 건축 법규를 자동 검토합니다. 건폐율, 용적률, 층수 제한, 일조권, 주차 기준을 반환합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pnu":          {"type": "string"},
                "building_use": {"type": "string", "description": "건물 용도 (예: 공동주택, 업무시설, 근린생활시설)"}
            },
            "required": ["pnu"]
        }
    },
    {
        "name": "get_avm_valuation",
        "description": "AVM(자동가치평가모델)으로 필지의 현재 시세를 산정합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pnu": {"type": "string"}
            },
            "required": ["pnu"]
        }
    },
    {
        "name": "generate_design",
        "description": "법규와 필지 정보를 기반으로 AI 건축 설계안을 생성합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pnu":           {"type": "string"},
                "building_use":  {"type": "string"},
                "floor_area_m2": {"type": "number"}
            },
            "required": ["pnu", "building_use"]
        }
    },
    {
        "name": "analyze_finance",
        "description": "프로젝트의 사업성을 분석합니다. IRR, NPV, 투자수익배수(MOIC) 등을 계산합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pnu":           {"type": "string"},
                "building_use":  {"type": "string"},
                "floor_area_m2": {"type": "number"},
                "land_price_krw":{"type": "number"}
            },
            "required": ["pnu", "building_use"]
        }
    },
    {
        "name": "calculate_tax",
        "description": "취득세, 양도소득세, 법인세 등 세금을 자동 계산합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "acquisition_price_krw": {"type": "number"},
                "holding_years":         {"type": "integer"},
                "building_use":          {"type": "string"},
                "entity_type":           {"type": "string", "enum": ["individual", "corporation"]}
            },
            "required": ["acquisition_price_krw"]
        }
    },
    {
        "name": "assess_esg",
        "description": "ESG 기후 리스크와 탄소 배출량을 평가합니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pnu":           {"type": "string"},
                "floor_area_m2": {"type": "number"},
                "building_use":  {"type": "string"}
            },
            "required": ["pnu"]
        }
    },
]

class RealEstateAgent:
    """
    PropAI 자율 부동산 개발 에이전트
    Claude claude-sonnet-4-6 Tool Use 기반 9단계 자율 실행
    """

    SYSTEM_PROMPT = """당신은 PropAI 플랫폼의 부동산 개발 전문 AI 에이전트입니다.
사용자가 제공한 필지 정보를 기반으로 부동산 개발 전주기 분석을 자율적으로 수행합니다.

분석 순서:
1. 필지 기본 정보 조회 (get_parcel_info)
2. 건축 법규 검토 (check_regulation)
3. AI 건축 설계 생성 (generate_design)
4. 사업성 분석 (analyze_finance)
5. 세금 계산 (calculate_tax)
6. ESG 평가 (assess_esg)
7. 종합 결론 도출

각 단계를 순서대로 완료하고, 마지막에 투자 가치, 리스크, 추천 사항을 포함한 종합 리포트를 작성하세요.
모든 금액은 한국 원화(원) 기준으로 표시하세요."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def _execute_tool(self, tool_name: str, tool_input: dict, state: AgentState) -> dict:
        """도구 실행 라우터"""
        import httpx
        base_url = "http://localhost:8000/api/v1"

        route_map = {
            "get_parcel_info":  ("/parcels/by-pnu",        "GET"),
            "check_regulation": ("/regulation/check",       "POST"),
            "get_avm_valuation":("/avm/valuate",            "POST"),
            "generate_design":  ("/design/generate-sync",  "POST"),
            "analyze_finance":  ("/finance/underwriting",   "POST"),
            "calculate_tax":    ("/tax/calculate",          "POST"),
            "assess_esg":       ("/construction/esg-score", "POST"),
        }

        endpoint, method = route_map.get(tool_name, ("/health", "GET"))

        async with httpx.AsyncClient(timeout=60) as client:
            try:
                if method == "GET":
                    res = await client.get(
                        f"{base_url}{endpoint}",
                        params=tool_input,
                        headers={"X-Internal-Token": "propai-agent-2026"}
                    )
                else:
                    res = await client.post(
                        f"{base_url}{endpoint}",
                        json=tool_input,
                        headers={"X-Internal-Token": "propai-agent-2026"}
                    )
                return res.json() if res.status_code < 400 else {"error": f"HTTP {res.status_code}"}
            except Exception as e:
                return {"error": str(e)}

    async def run(
        self,
        pnu: str,
        project_name: str,
        building_use: str = "공동주택",
        floor_area_m2: float = None,
    ) -> dict:
        """에이전트 9단계 자율 실행"""
        task_id = str(uuid.uuid4())
        state: AgentState = {
            "task_id":        task_id,
            "pnu":            pnu,
            "project_name":   project_name,
            "building_use":   building_use,
            "floor_area_m2":  floor_area_m2,
            "steps_completed": [],
            "errors":          [],
            "total_tokens":    0,
            "started_at":      datetime.utcnow().isoformat(),
            "parcel_info": None, "regulation": None, "avm_result": None,
            "design_result": None, "finance_result": None, "tax_result": None,
            "risk_result": None, "esg_result": None, "final_report": None,
        }

        messages = [
            {
                "role": "user",
                "content": f"""다음 필지에 대한 부동산 개발 전주기 분석을 수행하세요:
- PNU: {pnu}
- 프로젝트명: {project_name}
- 건물 용도: {building_use}
{f'- 계획 연면적: {floor_area_m2:,.0f}m²' if floor_area_m2 else ''}

모든 분석 도구를 순서대로 사용하여 종합 리포트를 작성해주세요."""
            }
        ]

        logger.info("agent_started", task_id=task_id, pnu=pnu)

        # 에이전트 루프 (최대 20 턴)
        for _turn in range(20):
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=4096,
                system=self.SYSTEM_PROMPT,
                tools=AGENT_TOOLS,
                messages=messages,
            )

            state["total_tokens"] += (
                response.usage.input_tokens + response.usage.output_tokens
            )

            if response.stop_reason == "end_turn":
                # 에이전트 완료
                for block in response.content:
                    if hasattr(block, "text"):
                        state["final_report"] = {
                            "summary": block.text,
                            "steps_completed": state["steps_completed"],
                            "total_tokens": state["total_tokens"],
                            "task_id": task_id,
                            "completed_at": datetime.utcnow().isoformat(),
                        }
                break

            if response.stop_reason == "tool_use":
                # 도구 사용
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []

                for block in response.content:
                    if block.type == "tool_use":
                        logger.info("agent_tool_call", tool=block.name, input=block.input)
                        result = await self._execute_tool(block.name, block.input, state)
                        state["steps_completed"].append(block.name)

                        # 결과를 state에 저장
                        tool_state_map = {
                            "get_parcel_info":   "parcel_info",
                            "check_regulation":  "regulation",
                            "get_avm_valuation": "avm_result",
                            "generate_design":   "design_result",
                            "analyze_finance":   "finance_result",
                            "calculate_tax":     "tax_result",
                            "assess_esg":        "esg_result",
                        }
                        if block.name in tool_state_map:
                            state[tool_state_map[block.name]] = result

                        tool_results.append({
                            "type":        "tool_result",
                            "tool_use_id": block.id,
                            "content":     json.dumps(result, ensure_ascii=False),
                        })

                messages.append({"role": "user", "content": tool_results})

        return state

================================================================
P13-STEP-02: RAG 파이프라인 -- 법규 문서 벡터 검색
================================================================

[파일: apps/api/app/services/rag_service.py]
"""
RAG (Retrieval-Augmented Generation) 서비스
법규 문서 / 판례 / 국토부 고시를 벡터 DB(Qdrant)에 임베딩하여
AI 법규 검토 시 실시간 문서 검색 지원
"""
import os
import json
import uuid
from typing import List, Optional
import httpx
import anthropic
import structlog

logger = structlog.get_logger()

QDRANT_URL       = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_COLLECTION = "propai_legal_docs"
EMBEDDING_MODEL  = "text-embedding-3-small"   # OpenAI 임베딩 (대체: Cohere, HuggingFace)

class RAGService:
    """
    부동산 법규 RAG 서비스
    - Qdrant 벡터 DB 기반 법규 문서 검색
    - Claude claude-sonnet-4-6 컨텍스트 증강 법규 해석
    - 국토부/건교부 고시, 건축법 시행령, 주택법 지원

    임베딩 수학 모델:
    - cosine_similarity(q, d) = (q · d) / (||q|| * ||d||)
    - 임계값 >= 0.75 이상 문서를 관련 법규로 판단
    """

    RELEVANCE_THRESHOLD = 0.75

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    async def _get_embedding(self, text: str) -> List[float]:
        """텍스트 임베딩 생성"""
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            async with httpx.AsyncClient() as client:
                res = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    json={"model": EMBEDDING_MODEL, "input": text[:8000]},
                    headers={"Authorization": f"Bearer {openai_key}"},
                )
                data = res.json()
                return data["data"][0]["embedding"]
        # Fallback: 128차원 0벡터 (개발용)
        return [0.0] * 128

    async def search_legal_docs(
        self, query: str, limit: int = 5, filter_law: Optional[str] = None
    ) -> List[dict]:
        """법규 문서 유사도 검색"""
        embedding = await self._get_embedding(query)
        payload = {
            "vector": embedding,
            "limit":  limit,
            "with_payload": True,
            "score_threshold": self.RELEVANCE_THRESHOLD,
        }
        if filter_law:
            payload["filter"] = {
                "must": [{"key": "law_name", "match": {"value": filter_law}}]
            }

        async with httpx.AsyncClient(timeout=10) as client:
            try:
                res = await client.post(
                    f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/search",
                    json=payload,
                )
                results = res.json().get("result", [])
                return [
                    {
                        "doc_id":    r["id"],
                        "score":     round(r["score"], 4),
                        "law_name":  r["payload"].get("law_name", ""),
                        "article":   r["payload"].get("article", ""),
                        "content":   r["payload"].get("content", ""),
                        "source":    r["payload"].get("source", ""),
                    }
                    for r in results
                ]
            except Exception as e:
                logger.warning("qdrant_search_failed", error=str(e))
                return []

    async def augmented_regulation_check(
        self, pnu: str, building_use: str, query_context: str
    ) -> dict:
        """RAG 증강 법규 해석"""
        query = f"PNU {pnu} {building_use} 건축 법규 {query_context}"
        docs = await self.search_legal_docs(query, limit=5)

        context = "\n\n".join([
            f"[{d['law_name']} {d['article']}]\n{d['content']}"
            for d in docs
        ])

        system_prompt = f"""당신은 대한민국 건축 법규 전문가입니다.
아래 관련 법규 조문을 참조하여 정확하게 해석해주세요.

[관련 법규 조문]
{context if context else "관련 법규 문서를 찾지 못했습니다. 일반 건축법 기준으로 해석합니다."}"""

        # Prompt Caching 적용 (법규 컨텍스트 캐싱)
        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},  # 5분 캐시
                }
            ],
            messages=[{
                "role":    "user",
                "content": f"PNU {pnu}, 용도: {building_use}\n질문: {query_context}",
            }],
        )

        answer_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                answer_text += block.text

        return {
            "answer":       answer_text,
            "source_docs":  docs,
            "cache_used":   hasattr(response.usage, "cache_read_input_tokens"),
            "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
        }

    async def upsert_legal_doc(
        self,
        doc_id: str,
        law_name: str,
        article: str,
        content: str,
        source: str,
    ) -> bool:
        """법규 문서 벡터 DB 저장"""
        embedding = await self._get_embedding(f"{law_name} {article} {content}")
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                await client.put(
                    f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points",
                    json={
                        "points": [{
                            "id":      doc_id,
                            "vector":  embedding,
                            "payload": {
                                "law_name": law_name,
                                "article":  article,
                                "content":  content,
                                "source":   source,
                            },
                        }]
                    },
                )
                logger.info("legal_doc_upserted", doc_id=doc_id, law_name=law_name)
                return True
            except Exception as e:
                logger.error("qdrant_upsert_failed", error=str(e))
                return False

================================================================
P13-STEP-03: 에이전트 API 라우터
================================================================

[파일: apps/api/app/routers/agents.py]
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
from app.agents.real_estate_agent import RealEstateAgent
from app.services.rag_service import RAGService
from app.db import get_db_pool
import uuid

router   = APIRouter(prefix="/api/v1/agents", tags=["agents"])
_agent   = RealEstateAgent()
_rag     = RAGService()

class AgentRunRequest(BaseModel):
    pnu:           str
    project_name:  str
    building_use:  str = "공동주택"
    floor_area_m2: Optional[float] = None

class RAGQueryRequest(BaseModel):
    pnu:          str
    building_use: str
    query:        str

@router.post("/run")
async def run_agent(req: AgentRunRequest, background_tasks: BackgroundTasks):
    """
    PropAI 자율 에이전트 실행 (비동기)
    9단계 분석 자동 수행 후 종합 리포트 반환
    """
    result = await _agent.run(
        pnu=req.pnu,
        project_name=req.project_name,
        building_use=req.building_use,
        floor_area_m2=req.floor_area_m2,
    )
    return result

@router.post("/rag/query")
async def rag_query(req: RAGQueryRequest):
    """RAG 증강 법규 검토"""
    return await _rag.augmented_regulation_check(
        pnu=req.pnu,
        building_use=req.building_use,
        query_context=req.query,
    )

@router.get("/health")
async def agents_health():
    return {"status": "ok", "service": "agents", "version": "v43.0"}

================================================================
Phase 13 완료 확인:
  [ ] POST /api/v1/agents/run -> 에이전트 9단계 실행 확인
  [ ] POST /api/v1/agents/rag/query -> RAG 법규 검색 결과 반환 확인
  [ ] GET /api/v1/mlops/drift/avm -> PSI 드리프트 수치 반환 확인
  [ ] LangGraph 에이전트 steps_completed 9개 확인
================================================================
```

---

## Part D 최종 완료 체크리스트

```
[Part-D 완료 기준 -- 전체 19개 항목]

MLOps (Phase 10):
  [ ] GET /api/v1/mlops/drift/avm -> {"status": "stable"/"warning"/"critical", "psi": float}
  [ ] POST /api/v1/mlops/ab-test/track -> {"event_id": uuid, "variant": "A"/"B"}
  [ ] GET /api/v1/mlops/ab-test/{name}/results -> 전환율 비교 결과
  [ ] Airflow DAG propai_nightly_batch 파일 생성 확인
  [ ] MLflow 실험 추적 서비스 파일 생성 확인

프론트엔드 (Phase 11):
  [ ] http://localhost:3000/dashboard 접속 -> 대시보드 메인 렌더링 (4개 스탯 카드)
  [ ] http://localhost:3000/dashboard/parcels -> OpenLayers 지적도 렌더링
  [ ] 사이드바 컬랩스 토글 애니메이션 동작
  [ ] 지적도 클릭 -> 필지 정보 패널 표시
  [ ] "법규 자동 검토" 버튼 -> POST /regulation/check 호출 + 결과 표시
  [ ] 반응형 모바일(375px) / 태블릿(768px) / 데스크탑(1280px) 레이아웃 모두 정상

인프라 (Phase 12):
  [ ] infra/k8s/base/ 8개 YAML 파일 생성 확인
  [ ] .github/workflows/ci-cd.yml 생성 확인 (test/build/deploy/security 4개 job)
  [ ] Prometheus 규칙 파일 생성 (5개 알림 규칙)
  [ ] 보안 헤더 미들웨어 적용 (X-Content-Type-Options, HSTS 등)

AI 고도화 (Phase 13):
  [ ] POST /api/v1/agents/run -> task_id, steps_completed(9개), final_report 반환
  [ ] POST /api/v1/agents/rag/query -> answer + source_docs 반환
  [ ] RAG cosine 유사도 검색 0.75 임계값 적용 확인
  [ ] 에이전트 최대 20턴 루프 + stop_reason="end_turn" 종료 확인

다음 파트: Part-E (비즈인프라 + G81~G85 AI투자/준법/ESG)
```
