"use client";

import { useState, useCallback } from "react";
import { Button, Card, CardContent, CardTitle } from "@propai/ui";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { TrustBadge } from "@/components/common/TrustBadge";
import { DataSourceNotice } from "@/components/ui/DataSourceNotice";
import { apiClient, ApiClientError } from "@/lib/api-client";

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
  { id: "unit_mix", title: "5. 평형 구성 분석", required: false, module: "design" },
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
  // 완성도 구간 → 의미 고정 상태색 토큰(성공/경고/오류). 양테마 자동 대응.
  const color =
    pct >= 80
      ? "var(--status-success)"
      : pct >= 50
        ? "var(--status-warning)"
        : "var(--status-error)";

  return (
    <div className="relative inline-flex items-center justify-center">
      <svg width="100" height="100" className="-rotate-90">
        <circle cx="50" cy="50" r={radius} fill="none" stroke="var(--border-muted)" strokeWidth="8" />
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
      <span className="absolute font-[var(--font-display)] text-lg font-bold" style={{ color }}>
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

  if (rows.length === 0)
    return (
      <p className="text-sm text-[var(--paper-ink)] opacity-60">표시할 데이터가 없습니다.</p>
    );

  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm text-[var(--paper-ink)]">
      {rows.map((r) => (
        <div key={r.label} className="contents">
          <dt className="font-medium opacity-60">{r.label}</dt>
          <dd className="font-[var(--font-mono)]">{r.value}</dd>
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
  const [downloadingFmt, setDownloadingFmt] = useState<"pdf" | "pptx" | "docx" | null>(null);
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
            // ★다필지면 통합 면적 — 은행제출 보고서 사업규모가 통합 부지 기준이 되도록.
            land_area_sqm: effectiveLandAreaSqm(siteAnalysis),
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
      // 원장(ledger) 권위소스 병합 + 10섹션 종합은 백엔드 단일 출처에서 수행한다.
      // 프론트 store는 식별자(project_id/pnu/address) 전달 + 미적재분 보조 입력으로만 사용한다.
      const pd = buildProjectData();
      const result = await apiClient.post<BankReport>("/bank-report/generate", {
        body: {
          project_data: pd,
          selected_sections: Array.from(selectedSections),
          template,
          project_id: projectId || undefined,
          pnu: siteAnalysis?.pnu || undefined,
          address: siteAnalysis?.address || undefined,
        },
        useMock: false,
        timeoutMs: 90000,
      });

      if (!result || !Array.isArray(result.sections) || result.sections?.length === 0) {
        // 무목업: 원장·store 모두 비어 종합할 실데이터가 없으면 가짜 채움 없이 정직 안내.
        setError(
          "보고서로 종합할 분석 데이터가 없습니다. 부지분석·법규·수지 등 선행 분석을 먼저 실행해 주세요.",
        );
        return;
      }

      setReport(result);
      setExpandedSections(new Set((result.sections ?? []).filter((s) => s.has_data).map((s) => s.id)));
    } catch (err) {
      if (err instanceof ApiClientError && (err.status === 401 || err.status === 403)) {
        setError("보고서 생성 권한이 없습니다. 로그인 또는 구독 상태를 확인해 주세요.");
      } else if (err instanceof ApiClientError && err.status === 404) {
        setError("선행 분석 데이터를 찾을 수 없습니다. 부지분석·수지 등 분석을 먼저 실행해 주세요.");
      } else {
        setError(err instanceof Error ? err.message : "보고서 생성 중 오류가 발생했습니다.");
      }
    } finally {
      setLoading(false);
    }
  };

  // 통합 보고서 생성엔진: 서버에서 PDF/PPTX/DOCX 렌더(과거 window.print HTML 인쇄 대체).
  // 같은 데이터·같은 디자인으로 3포맷을 받는다(브라우저 인쇄 품질 편차 제거).
  const handleDownload = async (format: "pdf" | "pptx" | "docx") => {
    if (!report) return;
    setDownloadingFmt(format);
    setError(null);
    try {
      const { apiBaseUrl } = apiClient.getRuntimeConfig();
      const baseUrl = apiBaseUrl || "/api/proxy";
      const token =
        typeof window !== "undefined"
          ? localStorage.getItem("propai_access_token") ?? ""
          : "";
      const res = await fetch(
        `${baseUrl}/bank-report/generate/report?format=${format}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            project_data: buildProjectData(),
            selected_sections: Array.from(selectedSections),
            template,
            project_id: projectId || undefined,
            pnu: siteAnalysis?.pnu || undefined,
            address: siteAnalysis?.address || undefined,
          }),
        },
      );
      if (!res.ok) {
        let detail = `다운로드 실패 (HTTP ${res.status})`;
        try {
          const j = (await res.json()) as { detail?: string; message?: string };
          if (j?.detail || j?.message) detail = (j.detail ?? j.message) as string;
        } catch {
          /* 본문 비-JSON */
        }
        throw new Error(detail);
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `bank_report.${format}`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "다운로드 중 오류가 발생했습니다.");
    } finally {
      setDownloadingFmt(null);
    }
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
              <p className="text-sm text-[var(--text-secondary)]">
                전 모듈 분석 데이터를 통합하여 PF 대출 심사용 보고서를 자동 생성합니다.
              </p>
              {projectName && (
                <p className="text-sm mt-1 font-medium text-[var(--accent-strong)]">
                  프로젝트: {projectName}
                </p>
              )}
              <TrustBadge className="mt-3" />
            </div>
            <div className="flex flex-col items-center gap-1">
              <CompletenessRing pct={Math.round((filledCount / ALL_SECTIONS.length) * 100)} />
              <span className="font-[var(--font-mono)] text-xs text-[var(--text-tertiary)]">
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
            <h3 className="text-base font-semibold text-[var(--text-primary)]">섹션 선택</h3>
            <div className="flex items-center gap-2">
              <label className="text-sm text-[var(--text-tertiary)]">템플릿:</label>
              <select
                value={template}
                onChange={(e) => setTemplate(e.target.value as "bank" | "internal")}
                className="rounded-[var(--r-input)] border border-[var(--line)] bg-[var(--surface)] px-3 py-1.5 text-sm text-[var(--text-primary)] outline-none transition-colors focus:border-[var(--accent-strong)]"
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
                  className={`flex cursor-pointer items-center gap-3 rounded-[var(--r-card)] border p-3 transition-colors ${
                    selectedSections.has(s.id)
                      ? "border-[var(--accent-strong)] bg-[var(--accent-soft)]"
                      : "border-[var(--line)] hover:border-[var(--line-strong)]"
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={selectedSections.has(s.id)}
                    onChange={() => toggleSection(s.id)}
                    className="h-5 w-5 rounded-[var(--r-input)] accent-[var(--accent-strong)]"
                  />
                  <span className="flex-1 text-sm text-[var(--text-primary)]">{s.title}</span>
                  <span
                    className={`inline-flex items-center rounded-[var(--r-pill)] px-2 py-0.5 font-[var(--font-mono)] text-[11px] font-medium ${
                      hasData
                        ? "bg-[color-mix(in_srgb,var(--status-success)_16%,transparent)] text-[var(--status-success)]"
                        : "bg-[var(--surface-muted)] text-[var(--text-tertiary)]"
                    }`}
                  >
                    {hasData ? "데이터 있음" : "미완성"}
                  </span>
                  {s.required && (
                    <span className="text-xs font-medium text-[var(--status-error)]">필수</span>
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
            <p className="text-sm text-[var(--status-error)]">{error}</p>
          </CardContent>
        </Card>
      )}

      {/* Report Result */}
      {report && (
        <div className="space-y-4">
          {/* Report Header (문서 도구 막대) */}
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-lg font-bold text-[var(--text-primary)]">{report.meta.title}</h2>
                  <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                    생성: {report.meta.data_basis_date} | {report.meta.generated_by} |
                    템플릿: {template === "bank" ? "금융기관 제출용" : "내부 검토용"}
                  </p>
                </div>
                <div className="flex items-center gap-4">
                  <CompletenessRing pct={report.completeness.pct} />
                  {/* 통합 보고서 생성엔진: 서버 렌더 3포맷(과거 브라우저 인쇄 대체) */}
                  <div className="flex items-center gap-1.5">
                    {(["pdf", "pptx", "docx"] as const).map((fmt) => (
                      <Button
                        key={fmt}
                        onClick={() => handleDownload(fmt)}
                        variant="secondary"
                        disabled={downloadingFmt !== null}
                      >
                        {downloadingFmt === fmt
                          ? "생성 중…"
                          : fmt === "pdf"
                            ? "PDF"
                            : fmt === "pptx"
                              ? "PPT"
                              : "Word"}
                      </Button>
                    ))}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* 보고서 미리보기 — 종이 문서 뷰(--paper 4종·테마 불변) */}
          <div className="overflow-hidden rounded-md bg-[var(--paper)] text-[var(--paper-ink)] shadow-[var(--shadow-lg)]">
            {(report.sections ?? []).map((section, idx) => (
              <div key={section.id} className={idx > 0 ? "border-t border-[var(--paper-line)]" : ""}>
                <button
                  type="button"
                  onClick={() => toggleExpand(section.id)}
                  className="flex w-full items-center justify-between bg-[var(--paper-section)] px-4 py-3 text-left"
                >
                  <div className="flex items-center gap-3">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{
                        backgroundColor: section.has_data
                          ? "var(--status-success)"
                          : "color-mix(in srgb, var(--paper-ink) 28%, transparent)",
                      }}
                    />
                    <h3 className="text-sm font-semibold text-[var(--paper-ink)]">{section.title}</h3>
                  </div>
                  <span className="text-lg text-[var(--paper-ink)] opacity-50">
                    {expandedSections.has(section.id) ? "\u25B2" : "\u25BC"}
                  </span>
                </button>
                {expandedSections.has(section.id) && (
                  <div className="border-t border-[var(--paper-line)] px-4 pb-4 pt-3">
                    {section.has_data ? (
                      <SectionContentView section={section} />
                    ) : (
                      <div className="py-3 text-center">
                        <p className="mb-2 text-sm text-[var(--paper-ink)] opacity-60">데이터 없음</p>
                        <a
                          href={`../../${projectId}/${ALL_SECTIONS.find((s) => s.id === section.id)?.module ?? "site-analysis"}`}
                          className="text-sm text-[var(--accent-strong)] hover:underline"
                        >
                          해당 모듈로 이동 &rarr;
                        </a>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* 공공데이터 출처·참고용 고지 — 공용 DataSourceNotice 배선(종이 톤 유지) */}
            <div className="px-4 pb-4 pt-1">
              <DataSourceNotice
                source="공공데이터(국토교통부·조달청 등) 통합 분석"
                updatedAt={report.meta.data_basis_date}
                note={report.meta.legal_disclaimer}
                style={{
                  fontSize: "11px",
                  color: "color-mix(in srgb, var(--paper-ink) 62%, transparent)",
                  borderTop: "1px solid var(--paper-line)",
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
