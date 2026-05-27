"use client";

import { useState, useCallback } from "react";
import { Button, Card, CardContent, CardTitle } from "@propai/ui";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/* ── Types ── */

type ReportSection = {
  id: string;
  title: string;
  has_data: boolean;
  content: Record<string, unknown>;
};

type ReportMeta = {
  title: string;
  template: string;
  generated_at: string;
  generated_by: string;
  legal_disclaimer: string;
  data_basis_date: string;
};

type ReportCompleteness = {
  total: number;
  filled: number;
  empty: number;
  pct: number;
};

type BankReport = {
  meta: ReportMeta;
  sections: ReportSection[];
  completeness: ReportCompleteness;
};

/* ── Section definitions ── */

const ALL_SECTIONS = [
  { id: "summary", title: "1. 사업개요", required: true, module: "site-analysis" },
  { id: "market", title: "2. 시장분석", required: true, module: "site-analysis" },
  { id: "legal", title: "3. 법규검토", required: true, module: "legal" },
  { id: "design", title: "4. 설계개요", required: false, module: "design" },
  { id: "unit_mix", title: "5. 유닛믹스 분석", required: false, module: "design" },
  { id: "feasibility", title: "6. 사업수지분석", required: true, module: "feasibility" },
  { id: "finance", title: "7. 자금조달계획", required: true, module: "finance" },
  { id: "risk", title: "8. 리스크분석", required: true, module: "feasibility" },
  { id: "esg", title: "9. ESG 분석", required: false, module: "esg" },
  { id: "appendix", title: "10. 부록", required: false, module: "report" },
] as const;

/* ── Helpers ── */

function formatWon(value: unknown): string {
  if (value == null || typeof value !== "number") return "-";
  if (value >= 1e8) return `${(value / 1e8).toLocaleString("ko-KR", { maximumFractionDigits: 1 })}억원`;
  if (value >= 1e4) return `${(value / 1e4).toLocaleString("ko-KR", { maximumFractionDigits: 0 })}만원`;
  return `${value.toLocaleString("ko-KR")}원`;
}

function formatPct(value: unknown): string {
  if (value == null || typeof value !== "number") return "-";
  return `${value.toFixed(1)}%`;
}

function formatNum(value: unknown): string {
  if (value == null) return "-";
  if (typeof value === "number") return value.toLocaleString("ko-KR");
  return String(value);
}

/* ── Progress Ring ── */

function CompletenessRing({ pct }: { pct: number }) {
  const radius = 40;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (pct / 100) * circumference;
  const color = pct >= 80 ? "#22c55e" : pct >= 50 ? "#eab308" : "#ef4444";

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="100" height="100" className="-rotate-90">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="#e5e7eb" strokeWidth="8" />
        <circle
          cx="50"
          cy="50"
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-700"
        />
      </svg>
      <span className="absolute text-lg font-bold" style={{ color }}>
        {pct}%
      </span>
    </div>
  );
}

/* ── Section Content Renderer ── */

function SectionContentView({ section }: { section: ReportSection }) {
  const c = section.content;

  const rows: Array<{ label: string; value: string }> = [];

  switch (section.id) {
    case "summary":
      rows.push(
        { label: "사업명", value: String(c.project_name || "-") },
        { label: "주소", value: String(c.address || "-") },
        { label: "PNU", value: String(c.pnu || "-") },
        { label: "대지면적", value: c.land_area_sqm ? `${formatNum(c.land_area_sqm)} m2` : "-" },
        { label: "용도지역", value: String(c.zone_type || "-") },
        { label: "추정가", value: formatWon(c.estimated_value) },
        { label: "개발유형", value: String(c.development_type || "-") },
        { label: "연면적", value: c.total_gfa_sqm ? `${formatNum(c.total_gfa_sqm)} m2` : "-" },
      );
      break;
    case "market":
      rows.push(
        { label: "분석지역", value: String(c.region || "-") },
        { label: "분석기간", value: String(c.analysis_period || "-") },
      );
      if (c.comparable_transactions && Array.isArray(c.comparable_transactions)) {
        rows.push({ label: "비교거래", value: `${(c.comparable_transactions as unknown[]).length}건` });
      }
      break;
    case "legal":
      if (c.bcr_check && typeof c.bcr_check === "object") {
        const bcr = c.bcr_check as Record<string, unknown>;
        rows.push({ label: "건폐율", value: bcr.compliant ? "적합" : bcr.compliant === false ? "부적합" : "-" });
      }
      if (c.far_check && typeof c.far_check === "object") {
        const far = c.far_check as Record<string, unknown>;
        rows.push({ label: "용적률", value: far.compliant ? "적합" : far.compliant === false ? "부적합" : "-" });
      }
      if (c.violations && Array.isArray(c.violations) && (c.violations as unknown[]).length > 0) {
        rows.push({ label: "위반사항", value: `${(c.violations as unknown[]).length}건` });
      }
      break;
    case "design":
      rows.push(
        { label: "연면적", value: c.total_gfa_sqm ? `${formatNum(c.total_gfa_sqm)} m2` : "-" },
        { label: "층수", value: formatNum(c.floor_count) },
        { label: "건물유형", value: String(c.building_type || "-") },
        { label: "건폐율", value: formatPct(c.bcr_pct) },
        { label: "용적률", value: formatPct(c.far_pct) },
        { label: "주차대수", value: formatNum(c.parking_spaces) },
      );
      break;
    case "unit_mix":
      rows.push(
        { label: "총 세대수", value: formatNum(c.total_units) },
        { label: "총 수입", value: formatWon(c.total_revenue_won) },
        { label: "전용률", value: formatPct(c.gfa_efficiency_pct) },
      );
      break;
    case "feasibility":
      rows.push(
        { label: "총 수입", value: formatWon(c.total_revenue_won) },
        { label: "총 비용", value: formatWon(c.total_cost_won) },
        { label: "순이익", value: formatWon(c.net_profit_won) },
        { label: "수익률", value: formatPct(c.profit_rate_pct) },
        { label: "ROI", value: formatPct(c.roi_pct) },
        { label: "NPV", value: formatWon(c.npv_won) },
        { label: "등급", value: String(c.grade || "-") },
      );
      break;
    case "finance":
      rows.push(
        { label: "자기자본", value: formatWon(c.equity_won) },
        { label: "브릿지론", value: formatWon(c.bridge_loan) },
        { label: "PF 대출", value: formatWon(c.pf_loan) },
        { label: "중도금 대출", value: formatWon(c.midpay_loan) },
        { label: "총 금융비용", value: formatWon(c.total_finance_cost) },
        { label: "가중평균금리", value: formatPct(c.weighted_avg_rate) },
      );
      break;
    case "risk":
      rows.push(
        { label: "시뮬레이션 횟수", value: formatNum(c.simulation_count) },
        { label: "NPV 평균", value: formatWon(c.npv_mean) },
        { label: "NPV P5", value: formatWon(c.npv_p5) },
        { label: "NPV P95", value: formatWon(c.npv_p95) },
        { label: "수익 확률", value: formatPct(typeof c.probability_positive === "number" ? c.probability_positive * 100 : null) },
        { label: "리스크 등급", value: String(c.risk_grade || "-") },
      );
      break;
    case "esg":
      rows.push(
        { label: "내재탄소", value: c.embodied_carbon_kg ? `${formatNum(c.embodied_carbon_kg)} kg` : "-" },
        { label: "운영탄소", value: c.operational_carbon_kg ? `${formatNum(c.operational_carbon_kg)} kg` : "-" },
        { label: "GRESB 점수", value: formatNum(c.gresb_score) },
        { label: "GRESB 등급", value: String(c.gresb_grade || "-") },
      );
      break;
    default:
      Object.entries(c).forEach(([k, v]) => {
        if (v != null && v !== "" && !(Array.isArray(v) && v.length === 0)) {
          rows.push({ label: k, value: typeof v === "object" ? JSON.stringify(v) : String(v) });
        }
      });
  }

  if (rows.length === 0) return <p className="text-sm text-gray-400">표시할 데이터가 없습니다.</p>;

  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
      {rows.map((r) => (
        <div key={r.label} className="contents">
          <dt className="font-medium text-gray-500">{r.label}</dt>
          <dd className="text-gray-900 dark:text-gray-100">{r.value}</dd>
        </div>
      ))}
    </dl>
  );
}

/* ── Main Component ── */

export function BankReadyReportBuilder() {
  const {
    projectId,
    projectName,
    siteAnalysis,
    designData,
    feasibilityData,
    esgData,
    complianceData,
    analysisResults,
  } = useProjectContextStore();

  // Section selection state
  const [selectedSections, setSelectedSections] = useState<Set<string>>(
    new Set(ALL_SECTIONS.map((s) => s.id)),
  );
  const [template, setTemplate] = useState<"bank" | "internal">("bank");
  const [report, setReport] = useState<BankReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set());

  // Build project_data payload from store
  const buildProjectData = useCallback(() => {
    // Find analysis results by module
    const findResult = (mod: string) =>
      analysisResults.find((r) => r.module === mod)?.summary ?? {};

    return {
      project_name: projectName,
      site_analysis: siteAnalysis
        ? {
            address: siteAnalysis.address,
            pnu: siteAnalysis.pnu,
            land_area_sqm: siteAnalysis.landAreaSqm,
            estimated_value: siteAnalysis.estimatedValue,
          }
        : {},
      zoning: { zone_type: siteAnalysis?.zoneCode },
      design: designData
        ? {
            total_gfa_sqm: designData.totalGfaSqm,
            floor_count: designData.floorCount,
            building_type: designData.buildingType,
            bcr: designData.bcr,
            far: designData.far,
          }
        : {},
      compliance: complianceData
        ? {
            bcr_compliant: complianceData.bcrCompliant,
            far_compliant: complianceData.farCompliant,
            height_compliant: complianceData.heightCompliant,
            violations: complianceData.violations,
          }
        : {},
      feasibility: feasibilityData
        ? {
            total_revenue_won: feasibilityData.totalRevenueWon,
            total_cost_won: feasibilityData.totalCostWon,
            profit_rate_pct: feasibilityData.profitRatePct,
            grade: feasibilityData.grade,
          }
        : {},
      esg: esgData
        ? {
            embodied_carbon_kg: esgData.embodiedCarbonKg,
            operational_carbon_kg: esgData.operationalCarbonKg,
            total_carbon_per_sqm: esgData.totalCarbonPerSqm,
          }
        : {},
      // Include raw analysis results for modules without typed store fields
      market_analysis: findResult("market"),
      finance: findResult("finance"),
      monte_carlo: findResult("monte-carlo"),
      unit_mix: findResult("unit-mix"),
      gresb: findResult("gresb"),
    };
  }, [projectName, siteAnalysis, designData, feasibilityData, esgData, complianceData, analysisResults]);

  // Determine which sections have data in the store
  const sectionHasData = useCallback(
    (sectionId: string): boolean => {
      switch (sectionId) {
        case "summary":
          return Boolean(siteAnalysis?.address);
        case "market":
          return Boolean(analysisResults.find((r) => r.module === "market"));
        case "legal":
          return complianceData?.bcrCompliant != null;
        case "design":
          return Boolean(designData?.totalGfaSqm);
        case "unit_mix":
          return Boolean(analysisResults.find((r) => r.module === "unit-mix"));
        case "feasibility":
          return feasibilityData?.profitRatePct != null;
        case "finance":
          return Boolean(analysisResults.find((r) => r.module === "finance"));
        case "risk":
          return Boolean(analysisResults.find((r) => r.module === "monte-carlo"));
        case "esg":
          return Boolean(esgData?.embodiedCarbonKg || analysisResults.find((r) => r.module === "gresb"));
        case "appendix":
          return true;
        default:
          return false;
      }
    },
    [siteAnalysis, designData, feasibilityData, esgData, complianceData, analysisResults],
  );

  const filledCount = ALL_SECTIONS.filter((s) => sectionHasData(s.id)).length;

  const toggleSection = (id: string) => {
    setSelectedSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleExpand = (id: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleGenerate = async () => {
    setLoading(true);
    setError(null);
    setReport(null);
    try {
      // 로컬에서 보고서 생성 (백엔드 불필요)
      await new Promise((r) => setTimeout(r, 500));
      const pd = buildProjectData();
      const selected = Array.from(selectedSections);
      const sections: ReportSection[] = ALL_SECTIONS
        .filter((s) => selected.includes(s.id))
        .map((s) => {
          const hasData = sectionHasData(s.id);
          let content: Record<string, unknown> = {};
          if (s.id === "summary") content = { project_name: pd.project_name, ...(pd.site_analysis || {}) };
          else if (s.id === "market") content = pd.market_analysis || {};
          else if (s.id === "legal") content = pd.compliance || {};
          else if (s.id === "design") content = pd.design || {};
          else if (s.id === "unit_mix") content = pd.unit_mix || {};
          else if (s.id === "feasibility") content = pd.feasibility || {};
          else if (s.id === "finance") content = pd.finance || {};
          else if (s.id === "risk") content = pd.monte_carlo || {};
          else if (s.id === "esg") content = { ...(pd.esg || {}), ...(pd.gresb || {}) };
          else content = {};
          return { id: s.id, title: s.title, has_data: hasData, content };
        });
      const filled = sections.filter((s) => s.has_data).length;
      const result: BankReport = {
        meta: {
          title: `${pd.project_name || "프로젝트"} 사업성 분석 보고서`,
          template: template === "bank" ? "금융기관 제출용" : "내부 검토용",
          generated_at: new Date().toISOString(),
          generated_by: "PropAI Platform",
          legal_disclaimer: "본 보고서는 AI 기반 자동 분석 결과이며, 최종 투자 판단은 전문가 자문을 받으시기 바랍니다.",
          data_basis_date: new Date().toLocaleDateString("ko-KR"),
        },
        sections,
        completeness: { total: sections.length, filled, empty: sections.length - filled, pct: sections.length > 0 ? Math.round((filled / sections.length) * 100) : 0 },
      };
      setReport(result);
      setExpandedSections(new Set(result.sections.filter((s) => s.has_data).map((s) => s.id)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "보고서 생성 중 오류가 발생했습니다.");
    } finally {
      setLoading(false);
    }
  };

  const handleDownloadPdf = () => {
    if (!report) return;
    // Create a printable HTML representation and trigger print dialog
    const printWindow = window.open("", "_blank");
    if (!printWindow) return;

    const sectionsHtml = report.sections
      .map(
        (s) => `
      <div style="page-break-inside:avoid;margin-bottom:24px;">
        <h2 style="font-size:16px;font-weight:bold;border-bottom:2px solid #1e3a5f;padding-bottom:4px;margin-bottom:12px;">${s.title}</h2>
        ${
          s.has_data
            ? `<table style="width:100%;border-collapse:collapse;font-size:13px;">
                ${Object.entries(s.content)
                  .filter(([, v]) => v != null && v !== "" && !(Array.isArray(v) && v.length === 0))
                  .map(
                    ([k, v]) =>
                      `<tr><td style="padding:4px 8px;font-weight:500;color:#555;width:40%;border-bottom:1px solid #eee;">${k}</td><td style="padding:4px 8px;border-bottom:1px solid #eee;">${typeof v === "object" ? JSON.stringify(v) : v}</td></tr>`,
                  )
                  .join("")}
               </table>`
            : `<p style="color:#999;font-style:italic;">데이터 없음</p>`
        }
      </div>`,
      )
      .join("");

    printWindow.document.write(`<!DOCTYPE html><html><head><title>${report.meta.title}</title>
      <style>body{font-family:'Noto Sans KR',sans-serif;max-width:800px;margin:40px auto;color:#222;}
      @media print{body{margin:20px;}}</style></head><body>
      <h1 style="font-size:22px;text-align:center;color:#1e3a5f;">${report.meta.title}</h1>
      <p style="text-align:center;color:#777;font-size:12px;">생성일: ${report.meta.data_basis_date} | ${report.meta.generated_by} | 완성도: ${report.completeness.pct}%</p>
      <hr style="border:1px solid #1e3a5f;margin:20px 0;"/>
      ${sectionsHtml}
      <hr style="border:1px solid #ccc;margin:20px 0;"/>
      <p style="font-size:11px;color:#999;">${report.meta.legal_disclaimer}</p>
      </body></html>`);
    printWindow.document.close();
    printWindow.print();
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-start justify-between gap-6">
            <div>
              <CardTitle className="text-xl mb-2">
                은행제출용 사업성 보고서
              </CardTitle>
              <p className="text-sm text-gray-500">
                전 모듈 분석 데이터를 통합하여 PF 대출 심사용 보고서를 자동 생성합니다.
              </p>
              {projectName && (
                <p className="text-sm mt-1 text-blue-600 font-medium">
                  프로젝트: {projectName}
                </p>
              )}
            </div>
            <div className="flex flex-col items-center gap-1">
              <CompletenessRing pct={Math.round((filledCount / ALL_SECTIONS.length) * 100)} />
              <span className="text-xs text-gray-500">
                {filledCount}/{ALL_SECTIONS.length} 섹션 완성
              </span>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Section Selector + Template */}
      <Card>
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-base">섹션 선택</h3>
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-500">템플릿:</label>
              <select
                value={template}
                onChange={(e) => setTemplate(e.target.value as "bank" | "internal")}
                className="rounded-md border border-gray-300 px-3 py-1.5 text-sm dark:border-gray-600 dark:bg-gray-800"
              >
                <option value="bank">금융기관 제출용</option>
                <option value="internal">내부 검토용</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {ALL_SECTIONS.map((s) => {
              const hasData = sectionHasData(s.id);
              return (
                <label
                  key={s.id}
                  className={`flex items-center gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                    selectedSections.has(s.id)
                      ? "border-blue-400 bg-blue-50 dark:bg-blue-950/30"
                      : "border-gray-200 dark:border-gray-700"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedSections.has(s.id)}
                    onChange={() => toggleSection(s.id)}
                    className="rounded border-gray-300"
                  />
                  <span className="flex-1 text-sm">{s.title}</span>
                  <span
                    className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                      hasData
                        ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                        : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
                    }`}
                  >
                    {hasData ? "데이터 있음" : "미완성"}
                  </span>
                  {s.required && (
                    <span className="text-xs text-red-500 font-medium">필수</span>
                  )}
                </label>
              );
            })}
          </div>

          <div className="flex justify-end pt-2">
            <Button
              onClick={handleGenerate}
              disabled={loading || selectedSections.size === 0}
            >
              {loading ? "생성 중..." : "보고서 생성"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <Card>
          <CardContent className="p-4">
            <p className="text-sm text-red-600">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Report Result */}
      {report && (
        <div className="space-y-4">
          {/* Report Header */}
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold">{report.meta.title}</h2>
                  <p className="text-xs text-gray-500 mt-1">
                    생성: {report.meta.data_basis_date} | {report.meta.generated_by} |
                    템플릿: {template === "bank" ? "금융기관 제출용" : "내부 검토용"}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <CompletenessRing pct={report.completeness.pct} />
                  <Button onClick={handleDownloadPdf} variant="secondary">
                    PDF 다운로드
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Section Cards (Accordion) */}
          {report.sections.map((section) => (
            <Card key={section.id}>
              <button
                type="button"
                onClick={() => toggleExpand(section.id)}
                className="w-full text-left"
              >
                <CardContent className="p-4 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <span
                      className={`h-3 w-3 rounded-full ${
                        section.has_data ? "bg-green-500" : "bg-gray-300"
                      }`}
                    />
                    <h3 className="font-semibold text-sm">{section.title}</h3>
                  </div>
                  <span className="text-gray-400 text-lg">
                    {expandedSections.has(section.id) ? "\u25B2" : "\u25BC"}
                  </span>
                </CardContent>
              </button>
              {expandedSections.has(section.id) && (
                <CardContent className="px-4 pb-4 pt-0 border-t border-gray-100 dark:border-gray-800">
                  {section.has_data ? (
                    <SectionContentView section={section} />
                  ) : (
                    <div className="py-3 text-center">
                      <p className="text-sm text-gray-400 mb-2">데이터 없음</p>
                      <a
                        href={`../../${projectId}/${ALL_SECTIONS.find((s) => s.id === section.id)?.module ?? "site-analysis"}`}
                        className="text-sm text-blue-500 hover:underline"
                      >
                        해당 모듈로 이동 &rarr;
                      </a>
                    </div>
                  )}
                </CardContent>
              )}
            </Card>
          ))}

          {/* Legal Disclaimer */}
          <p className="text-xs text-gray-400 text-center px-4">
            {report.meta.legal_disclaimer}
          </p>
        </div>
      )}
    </div>
  );
}
