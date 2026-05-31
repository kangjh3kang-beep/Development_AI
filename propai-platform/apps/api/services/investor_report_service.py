"""Investor report generation service."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.database.models.phase_e_climate import ClimateRiskAssessment
from apps.api.database.models.phase_e_esg import ESGReport
from apps.api.database.models.phase_e_underwriting import InvestmentUnderwriting
from apps.api.database.models.phase_f_asset_intelligence import AssetIntelligenceSnapshot
from apps.api.database.models.phase_g_multilingual import MultilingualReport, TranslationJob

_LANG_LABELS = {
    "ko": "투자자 보고서",
    "en": "Investor Report",
    "ja": "投資家レポート",
    "zh": "投资者报告",
}


_LANG_LABELS = {
    "ko": "Investor Report (KO)",
    "en": "Investor Report",
    "ja": "Investor Report (JA)",
    "zh": "Investor Report (ZH)",
}


class InvestorReportService:
    """Generate multilingual investor report variants using stored project signals."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _latest(self, model, project_id: UUID):
        stmt = select(model).where(model.project_id == project_id).order_by(model.created_at.desc()).limit(1)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _compose_source_text(
        *,
        project_name: str,
        asset_type: str,
        include_sections: list[str],
        investment_highlights: list[str],
        risks: list[str],
        underwriting,
        esg_report,
        climate_report,
        asset_snapshot,
    ) -> str:
        details: list[str] = [f"Project: {project_name}", f"Asset type: {asset_type}"]
        if "executive-summary" in include_sections:
            highlights = ", ".join(investment_highlights) or "execution readiness and resilient demand"
            details.append(f"Highlights: {highlights}")
        if underwriting is not None and "financials" in include_sections:
            details.append(
                f"Underwriting: {underwriting.recommendation}, margin {underwriting.profit_margin_ratio:.1%}, "
                f"risk {underwriting.risk_level}."
            )
        if esg_report is not None and "esg" in include_sections:
            details.append(
                f"ESG: E {esg_report.environmental_score}, "
                f"S {esg_report.social_score}, G {esg_report.governance_score}."
            )
        if climate_report is not None and "risks" in include_sections:
            details.append(
                f"Climate: flood {climate_report.flood_risk_score:.2f}, heat {climate_report.heat_risk_score:.2f}, "
                f"AEL {climate_report.annual_expected_loss_krw:,.0f} KRW."
            )
        if asset_snapshot is not None and "market" in include_sections:
            details.append(
                f"Asset intelligence: score {asset_snapshot.composite_score}, grade {asset_snapshot.grade}, "
                f"adjusted value {asset_snapshot.adjusted_value_krw:,.0f} KRW."
            )
        if risks:
            details.append(f"Risk factors: {', '.join(risks)}")
        return "\n".join(details)

    @staticmethod
    def _translate(title_prefix: str, language: str, source_text: str) -> tuple[str, str, float]:
        heading = _LANG_LABELS.get(language, "Investor Report")
        translated = f"[{language.upper()}] {source_text}"
        quality = 0.93 if language in {"ko", "en"} else 0.88
        return f"{title_prefix} {heading}", translated, quality

    async def generate(
        self,
        *,
        tenant_id: UUID,
        project_id: UUID,
        project_name: str,
        asset_type: str,
        target_languages: list[str],
        investment_highlights: list[str],
        risks: list[str],
        include_sections: list[str],
    ) -> list[MultilingualReport]:
        underwriting = await self._latest(InvestmentUnderwriting, project_id)
        esg_report = await self._latest(ESGReport, project_id)
        climate_report = await self._latest(ClimateRiskAssessment, project_id)
        asset_snapshot = await self._latest(AssetIntelligenceSnapshot, project_id)

        source_text = self._compose_source_text(
            project_name=project_name,
            asset_type=asset_type,
            include_sections=include_sections,
            investment_highlights=investment_highlights,
            risks=risks,
            underwriting=underwriting,
            esg_report=esg_report,
            climate_report=climate_report,
            asset_snapshot=asset_snapshot,
        )

        # ── report_interpreter LLM 종합 내러티브를 source_text에 결합 (graceful fallback) ──
        try:
            from app.services.ai.report_interpreter import ReportInterpreter

            interp = await ReportInterpreter().generate_report_narrative({
                "project_name": project_name,
                "financial_analysis": (
                    {
                        "profit_rate_pct": getattr(underwriting, "profit_margin_ratio", None),
                        "risk_level": getattr(underwriting, "risk_level", None),
                    }
                    if underwriting is not None
                    else {}
                ),
                "risk_assessment": {"top_risks": risks},
                "building_design": {"development_type": asset_type},
            })
            if isinstance(interp, dict) and interp:
                _labels = {
                    "executive_summary": "총평",
                    "site_narrative": "입지 분석",
                    "financial_narrative": "재무 분석",
                    "risk_narrative": "리스크 평가",
                    "recommendation_narrative": "투자 권고",
                    "legal_compliance_narrative": "법규 적합성",
                }
                parts = [
                    f"[AI {_labels[k]}] {interp[k]}"
                    for k in _labels
                    if interp.get(k)
                ]
                if parts:
                    source_text = source_text + "\n\n=== AI 종합 분석 ===\n" + "\n\n".join(parts)
        except Exception:
            pass

        variants: list[MultilingualReport] = []
        for language in target_languages:
            title, translated_text, quality = self._translate(project_name, language, source_text)
            report = MultilingualReport(
                tenant_id=tenant_id,
                project_id=project_id,
                report_type="investor",
                source_language="ko",
                target_language=language,
                title=title,
                source_text=source_text,
                translated_text=translated_text,
                translation_engine="deterministic-template",
                quality_score=quality,
                version=1,
                metadata_json={"include_sections": include_sections},
            )
            self.db.add(report)
            await self.db.flush()
            self.db.add(
                TranslationJob(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    report_id=report.id,
                    source_language="ko",
                    target_language=language,
                    status="completed",
                    word_count=len(source_text.split()),
                    token_cost=len(source_text.split()) * 2,
                )
            )
            variants.append(report)

        await self.db.commit()
        for report in variants:
            await self.db.refresh(report)
        return variants
