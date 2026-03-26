"""PropAI 7단계 에이전트 오케스트레이터.

LangGraph 기반 상태 머신.
목표: 완주율 ≥ 95% (CoVe O9, 100회 반복).

7단계 흐름:
0. parcel_analysis — VWorld 필지 분석
1. regulation — 법규 검토
2. design — 설계 보고서 생성
3. avm — AVM 시세 추정
4. feasibility — 사업성 분석 (NPV/IRR + 세금 + 전세 리스크)
5. permit — 인허가 준비도 판단
6. report — Claude LLM 종합 보고서 + 투자 등급

각 단계 결과를 AgentStepEvent SSE로 실시간 전송한다.
"""

import time
from collections.abc import AsyncIterator
from uuid import UUID

import structlog
from packages.schemas.enums import AgentStepName
from packages.schemas.events import AgentStepEvent
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.config import get_settings
from apps.api.metrics import AGENT_COMPLETION, AGENT_STEP_DURATION

logger = structlog.get_logger(__name__)

# 7단계 정의
STEPS = [
    AgentStepName.PARCEL_ANALYSIS,
    AgentStepName.REGULATION,
    AgentStepName.DESIGN,
    AgentStepName.AVM,
    AgentStepName.FEASIBILITY,
    AgentStepName.PERMIT,
    AgentStepName.REPORT,
]


class OrchestratorState:
    """오케스트레이터 상태."""
    def __init__(self, project_id: UUID, tenant_id: UUID):
        self.project_id = project_id
        self.tenant_id = tenant_id
        self.results: dict[str, dict] = {}
        self.current_step: int = 0
        self.errors: list[str] = []


class PropAIOrchestrator:
    """7단계 에이전트 오케스트레이터."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.settings = get_settings()

    # ── Step 0: 필지 분석 ──

    async def _step_parcel_analysis(self, state: OrchestratorState) -> dict:
        """VWorldClient로 필지 정보 + 용도지역을 조회한다.

        DB에서 프로젝트의 필지(Parcel) 정보를 조회하여 PNU/주소를 획득한다.
        필지가 없으면 프로젝트 주소 기반으로 처리한다.
        """
        from apps.api.integrations.vworld_client import VWorldClient

        # DB에서 프로젝트 → 필지 정보 조회
        project_info = await self._fetch_project_info(state.project_id)
        pnu = project_info.get("pnu", "")
        address = project_info.get("address", "")

        # state에 프로젝트 메타데이터 보관 (후속 단계에서 참조)
        state.results["_project_meta"] = project_info

        vworld = VWorldClient()

        if pnu:
            parcel = await vworld.get_parcel_info(pnu)
            land_use = await vworld.get_land_use_zone(pnu)
        elif address:
            # PNU 없으면 주소 기반 좌표 조회만 수행
            geocode = await vworld.geocode(address)
            parcel = {
                "pnu": "",
                "address": address,
                "land_area_m2": project_info.get("total_area_sqm", 0.0),
                "lat": geocode.get("lat", 0.0),
                "lon": geocode.get("lon", 0.0),
            }
            land_use = {"land_use_zone": "", "far_limit": 0.0, "bcr_limit": 0.0}
        else:
            # 필지/주소 모두 없으면 기본값
            parcel = {"pnu": "", "address": "", "land_area_m2": 0.0}
            land_use = {"land_use_zone": "", "far_limit": 0.0, "bcr_limit": 0.0}

        await vworld.close()

        return {
            "status": "analyzed",
            "parcel_info": parcel,
            "pnu": pnu,
            "address": address,
            "land_use_zone": land_use.get("land_use_zone", ""),
            "far_limit": land_use.get("far_limit", 0),
            "bcr_limit": land_use.get("bcr_limit", 0),
            "lawd_cd": pnu[:5] if len(pnu) >= 5 else "",
        }

    async def _fetch_project_info(self, project_id: UUID) -> dict:
        """DB에서 프로젝트 + 필지 정보를 조회한다."""
        from sqlalchemy import text

        result: dict = {"project_id": str(project_id)}

        try:
            # 프로젝트 기본 정보
            row = await self.db.execute(
                text(
                    "SELECT name, address, total_area_sqm "
                    "FROM projects WHERE id = :pid"
                ),
                {"pid": str(project_id)},
            )
            proj = row.fetchone()
            if proj:
                result["name"] = proj.name
                result["address"] = proj.address or ""
                result["total_area_sqm"] = proj.total_area_sqm or 0.0

            # 프로젝트에 연결된 첫 번째 필지 PNU
            row = await self.db.execute(
                text(
                    "SELECT pnu, address, area_sqm "
                    "FROM parcels WHERE project_id = :pid "
                    "ORDER BY created_at LIMIT 1"
                ),
                {"pid": str(project_id)},
            )
            parcel = row.fetchone()
            if parcel:
                result["pnu"] = parcel.pnu or ""
                if parcel.address:
                    result["address"] = parcel.address
                if parcel.area_sqm:
                    result["total_area_sqm"] = parcel.area_sqm

        except Exception:
            logger.warning("프로젝트 정보 DB 조회 실패", project_id=str(project_id))

        return result

    # ── Step 1: 법규 검토 ──

    async def _step_regulation(self, state: OrchestratorState) -> dict:
        """RegulationService로 법규를 검토한다."""
        from apps.api.services.regulation_service import RegulationService

        svc = RegulationService(self.db)
        result = await svc.check_regulation(
            project_id=state.project_id,
            tenant_id=state.tenant_id,
            regulation_type="zoning",
            project_info=state.results.get(AgentStepName.PARCEL_ANALYSIS, {}),
        )
        return {
            "regulation_id": str(result.id),
            "is_compliant": result.is_compliant,
            "violations": result.violations,
            "recommendations": result.recommendations,
        }

    # ── Step 2: 설계 생성 ──

    async def _step_design(self, state: OrchestratorState) -> dict:
        """DesignAIService로 설계 보고서를 생성한다 (동기 수집)."""
        from apps.api.services.design_ai_service import DesignAIService

        svc = DesignAIService(self.db)
        parcel = state.results.get(AgentStepName.PARCEL_ANALYSIS, {})
        regulation = state.results.get(AgentStepName.REGULATION, {})

        design_data = {
            "project_id": str(state.project_id),
            "parcel_info": parcel.get("parcel_info", {}),
            "land_use_zone": parcel.get("land_use_zone", ""),
            "far_limit": parcel.get("far_limit", 0),
            "bcr_limit": parcel.get("bcr_limit", 0),
            "is_compliant": regulation.get("is_compliant", True),
        }

        # SSE 스트림을 동기로 전체 수집
        full_text = ""
        async for event in svc.stream_design_report(
            state.project_id, state.tenant_id, design_data,
        ):
            full_text += event.content

        return {
            "status": "design_generated",
            "design_text": full_text[:2000],
            "design_type": "floor_plan",
        }

    # ── Step 3: AVM 시세 추정 ──

    async def _step_avm(self, state: OrchestratorState) -> dict:
        """AVMService로 시세를 추정한다.

        Step 0(PARCEL_ANALYSIS) 결과에서 address/area/pnu/lawd_cd를 가져온다.
        """
        from packages.schemas.models import AVMRequest

        from apps.api.services.avm_service import AVMService

        parcel = state.results.get(AgentStepName.PARCEL_ANALYSIS, {})
        parcel_info = parcel.get("parcel_info", {})

        # Step 0에서 추출된 주소/면적/PNU/법정동코드
        address = parcel.get("address", "") or ""
        pnu = parcel.get("pnu", "") or ""
        lawd_cd = parcel.get("lawd_cd", "") or ""
        area = 330.0  # 최종 폴백

        if isinstance(parcel_info, dict):
            address = parcel_info.get("address", address) or address
            area = parcel_info.get("land_area_m2", area) or area

        # area가 0이면 프로젝트 메타에서 재시도
        if area <= 0:
            meta = state.results.get("_project_meta", {})
            area = meta.get("total_area_sqm", 330.0) or 330.0

        request = AVMRequest(
            project_id=state.project_id,
            address=address,
            area_sqm=area,
            building_age_years=5,
            floor=1,
            pnu=pnu or None,
            lawd_cd=lawd_cd or None,
        )

        svc = AVMService(self.db)
        result = await svc.estimate(request, state.tenant_id)

        return {
            "status": "estimated",
            "estimated_price": result.estimated_price,
            "price_per_sqm": result.price_per_sqm,
            "confidence_score": result.confidence_score,
            "comparable_count": result.comparable_count,
            "model_version": result.model_version,
        }

    # ── Step 4: 사업성 분석 (NPV/IRR + 세금 + 전세 리스크) ──

    async def _step_feasibility(self, state: OrchestratorState) -> dict:
        """세금/전세 리스크를 포함한 사업성을 분석한다.

        Step 3(AVM)의 estimated_price를 투자 원가로,
        Step 0(PARCEL_ANALYSIS)의 address/lawd_cd를 전세 리스크 분석에 사용한다.
        """
        from apps.api.services.jeonse_risk_service import JeonseRiskService
        from apps.api.services.tax_ai_service import TaxAIService

        avm_result = state.results.get(AgentStepName.AVM, {})
        estimated_price = avm_result.get("estimated_price", 0)

        # 취득세 계산
        tax_svc = TaxAIService(self.db)
        tax_result = await tax_svc.calculate(
            project_id=state.project_id,
            tenant_id=state.tenant_id,
            tax_type="acquisition",
            taxable_value=estimated_price,
        )
        acquisition_tax = tax_result.amount

        # Step 0에서 주소/법정동코드 추출
        parcel = state.results.get(AgentStepName.PARCEL_ANALYSIS, {})
        parcel_info = parcel.get("parcel_info", {})
        address = parcel.get("address", "") or ""
        lawd_cd = parcel.get("lawd_cd", "") or ""

        if isinstance(parcel_info, dict):
            address = parcel_info.get("address", address) or address

        jeonse_svc = JeonseRiskService(self.db)
        jeonse_result = await jeonse_svc.analyze(
            project_id=state.project_id,
            tenant_id=state.tenant_id,
            address=address,
            jeonse_price=estimated_price * 0.65,
            sale_price=estimated_price,
            lawd_cd=lawd_cd,
        )

        # NPV/IRR 계산 (할인율 5%, 투자기간 10년, 연 임대수익 3%)
        investment = estimated_price + acquisition_tax
        annual_income = estimated_price * 0.03
        discount_rate = 0.05
        years = 10

        npv = -investment
        for yr in range(1, years + 1):
            npv += annual_income / (1 + discount_rate) ** yr
        terminal_value = estimated_price * (1.02 ** years)
        npv += terminal_value / (1 + discount_rate) ** years

        irr = self._calc_irr(investment, annual_income, terminal_value, years)

        return {
            "status": "analyzed",
            "npv": round(npv),
            "irr": round(irr, 4),
            "acquisition_tax": round(acquisition_tax),
            "jeonse_risk_level": jeonse_result.risk_level,
            "jeonse_ratio": round(jeonse_result.jeonse_ratio, 3),
            "investment_total": round(investment),
        }

    @staticmethod
    def _calc_irr(
        investment: float,
        annual_income: float,
        terminal_value: float,
        years: int,
    ) -> float:
        """이분법으로 IRR을 근사한다."""
        lo, hi = -0.5, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            npv = -investment
            for yr in range(1, years + 1):
                npv += annual_income / (1 + mid) ** yr
            npv += terminal_value / (1 + mid) ** years
            if npv > 0:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    # ── Step 5: 인허가 준비도 ──

    async def _step_permit(self, state: OrchestratorState) -> dict:
        """법규 검토 결과 기반 인허가 준비도를 판단한다."""
        regulation = state.results.get(AgentStepName.REGULATION, {})
        violations = regulation.get("violations", [])
        is_compliant = regulation.get("is_compliant", True)

        permit_ready = is_compliant and len(violations) == 0

        return {
            "status": "reviewed",
            "permit_ready": permit_ready,
            "violation_count": len(violations),
            "warnings": regulation.get("recommendations", []),
        }

    # ── Step 6: 종합 보고서 + 투자 등급 ──

    async def _step_report(self, state: OrchestratorState) -> dict:
        """Claude LLM으로 전체 결과를 종합하여 보고서를 생성한다."""
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(
            model="claude-sonnet-4-5-20250929",
            api_key=self.settings.anthropic_api_key,
            temperature=0.3,
        )

        feasibility = state.results.get(AgentStepName.FEASIBILITY, {})
        npv = feasibility.get("npv", 0)
        irr = feasibility.get("irr", 0)
        permit = state.results.get(AgentStepName.PERMIT, {})
        permit_ready = permit.get("permit_ready", False)
        jeonse_risk = feasibility.get("jeonse_risk_level", "MEDIUM")

        grade = self._determine_investment_grade(npv, irr, permit_ready, jeonse_risk)

        avm_price = state.results.get(AgentStepName.AVM, {}).get("estimated_price", 0)

        prompt = f"""부동산 투자 분석 전문가로서 종합 보고서를 2~3문단으로 작성하세요.

## 분석 결과
- NPV: {npv:,.0f}원
- IRR: {irr:.1%}
- 인허가 준비: {"완료" if permit_ready else "미완료"}
- 전세 리스크: {jeonse_risk}
- 투자 등급: {grade}
- AVM 추정가: {avm_price:,.0f}원

투자 의사결정에 도움이 되도록 한국어로 간결하게 작성하세요."""

        try:
            response = await llm.ainvoke(prompt)
            report_text = response.content
        except Exception:
            report_text = (
                f"투자 등급 {grade}. NPV {npv:,.0f}원, IRR {irr:.1%}. "
                "상세 분석은 전문가 상담을 권장합니다."
            )

        return {
            "status": "generated",
            "investment_grade": grade,
            "final_report": report_text[:3000],
            "total_steps": len(STEPS),
        }

    @staticmethod
    def _determine_investment_grade(
        npv: float, irr: float, permit_ready: bool, jeonse_risk: str,
    ) -> str:
        """투자 매력도 A~F 등급을 산출한다."""
        score = 0
        if npv > 0:
            score += 30
        if irr > 0.08:
            score += 25
        elif irr > 0.05:
            score += 15
        if permit_ready:
            score += 20
        if jeonse_risk in ("SAFE", "LOW"):
            score += 15
        elif jeonse_risk == "MEDIUM":
            score += 10
        if npv > 500_000_000:
            score += 10

        if score >= 85:
            return "A"
        if score >= 70:
            return "B"
        if score >= 55:
            return "C"
        if score >= 40:
            return "D"
        if score >= 25:
            return "E"
        return "F"

    # ── 단계 디스패처 ──

    async def _execute_step(self, step_name: AgentStepName, state: OrchestratorState) -> dict:
        """개별 단계를 실행하고 Prometheus 메트릭을 기록한다."""
        dispatch = {
            AgentStepName.PARCEL_ANALYSIS: self._step_parcel_analysis,
            AgentStepName.REGULATION: self._step_regulation,
            AgentStepName.DESIGN: self._step_design,
            AgentStepName.AVM: self._step_avm,
            AgentStepName.FEASIBILITY: self._step_feasibility,
            AgentStepName.PERMIT: self._step_permit,
            AgentStepName.REPORT: self._step_report,
        }
        handler = dispatch.get(step_name)
        if handler is None:
            return {"error": f"알 수 없는 단계: {step_name}"}

        start = time.monotonic()
        result = await handler(state)
        duration = time.monotonic() - start
        AGENT_STEP_DURATION.labels(step_name=step_name).observe(duration)
        return result

    # ── 메인 실행 ──

    async def run(
        self,
        project_id: UUID,
        tenant_id: UUID,
    ) -> AsyncIterator[AgentStepEvent]:
        """7단계 파이프라인을 실행하며 각 단계를 SSE로 스트리밍한다."""
        logger.info("오케스트레이터 시작", project_id=str(project_id))
        state = OrchestratorState(project_id, tenant_id)

        for i, step_name in enumerate(STEPS):
            # 시작 이벤트
            yield AgentStepEvent(
                step_index=i,
                step_name=step_name,
                status="running",
                progress_pct=i / len(STEPS),
            )

            try:
                result = await self._execute_step(step_name, state)
                state.results[step_name] = result
                state.current_step = i + 1

                # 완료 이벤트
                yield AgentStepEvent(
                    step_index=i,
                    step_name=step_name,
                    status="completed",
                    progress_pct=(i + 1) / len(STEPS),
                    data=result,
                )

            except Exception as e:
                error_msg = f"단계 '{step_name}' 실행 실패: {e}"
                state.errors.append(error_msg)
                logger.error(error_msg)

                # 오류 이벤트 — 실패해도 다음 단계 계속 진행
                yield AgentStepEvent(
                    step_index=i,
                    step_name=step_name,
                    status="error",
                    progress_pct=(i + 1) / len(STEPS),
                    error_message=str(e),
                )

        status = "success" if not state.errors else "partial"
        AGENT_COMPLETION.labels(status=status).inc()
        logger.info(
            "오케스트레이터 완료",
            completed_steps=state.current_step,
            errors=len(state.errors),
        )
