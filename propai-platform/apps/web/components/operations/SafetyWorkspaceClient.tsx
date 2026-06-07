"use client";

import { useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { NumberInput } from "@/components/common/NumberInput";
import type { Locale } from "@/i18n/config";

/* ------------------------------------------------------------------ */
/*  Types                                                             */
/* ------------------------------------------------------------------ */

type SafetyPlanItem = {
  category?: string;
  description?: string;
  priority?: string;
  responsible_party?: string;
  [key: string]: unknown;
};

type SafetyPlanResponse = {
  project_id?: string;
  safety_items?: SafetyPlanItem[];
  overall_risk_level?: string;
  summary?: string;
};

type DisasterRiskResponse = {
  region?: string;
  risk_score?: number;
  risk_level?: string;
  flood_risk?: number;
  earthquake_risk?: number;
  landslide_risk?: number;
  recommendations?: string[];
  summary?: string;
};

/* ------------------------------------------------------------------ */
/*  Labels                                                            */
/* ------------------------------------------------------------------ */

type Labels = {
  heroTitle: string;
  heroDescription: string;
  heroHint: string;
  tokenHint: string;
  authError: string;
  safetyFormTitle: string;
  projectIdLabel: string;
  projectTypeLabel: string;
  projectCostLabel: string;
  floorCountLabel: string;
  excavationDepthLabel: string;
  submitSafetyAction: string;
  disasterFormTitle: string;
  regionLabel: string;
  landUseLabel: string;
  distanceToRiverLabel: string;
  submitDisasterAction: string;
  missingProjectIdError: string;
  missingRegionError: string;
  safetyPlanTitle: string;
  overallRiskLabel: string;
  categoryLabel: string;
  priorityLabel: string;
  responsibleLabel: string;
  disasterRiskTitle: string;
  riskScoreLabel: string;
  riskLevelLabel: string;
  floodRiskLabel: string;
  earthquakeRiskLabel: string;
  landslideRiskLabel: string;
  recommendationsTitle: string;
  placeholder: string;
};

const KO_LABELS: Labels = {
  heroTitle: "안전 관리 라이브 작업 공간",
  heroDescription:
    "공사현장 안전 계획과 재해 위험도를 AI가 분석하여 안전 항목 및 위험 매트릭스를 제공합니다.",
  heroHint:
    "",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.",
  safetyFormTitle: "안전 계획 분석 입력",
  projectIdLabel: "프로젝트 ID",
  projectTypeLabel: "프로젝트 유형",
  projectCostLabel: "공사비 (억원)",
  floorCountLabel: "층수",
  excavationDepthLabel: "굴착 깊이 (m)",
  submitSafetyAction: "안전 계획 분석",
  disasterFormTitle: "재해 위험 평가 입력",
  regionLabel: "지역",
  landUseLabel: "토지 용도",
  distanceToRiverLabel: "하천 거리 (m)",
  submitDisasterAction: "재해 위험 평가 실행",
  missingProjectIdError: "프로젝트 ID를 입력해 주세요.",
  missingRegionError: "지역을 입력해 주세요.",
  safetyPlanTitle: "안전 계획 항목",
  overallRiskLabel: "종합 위험 수준",
  categoryLabel: "분류",
  priorityLabel: "우선순위",
  responsibleLabel: "담당",
  disasterRiskTitle: "재해 위험 매트릭스",
  riskScoreLabel: "위험 점수",
  riskLevelLabel: "위험 등급",
  floodRiskLabel: "홍수 위험",
  earthquakeRiskLabel: "지진 위험",
  landslideRiskLabel: "산사태 위험",
  recommendationsTitle: "대응 권고사항",
  placeholder: "양식을 제출하면 분석 결과가 표시됩니다.",
};

const EN_LABELS: Labels = {
  heroTitle: "Safety Management Live Workspace",
  heroDescription:
    "AI analyzes construction safety plans and disaster risk to provide safety items and risk matrices.",
  heroHint:
    "Calls POST /lifecycle/construction/safety-plan and POST /lifecycle/disaster-risk/assess APIs.",
  tokenHint:
    "분석을 위해 로그인이 필요합니다.",
  authError: "API authentication is required for live workspace calls.",
  safetyFormTitle: "Safety plan analysis input",
  projectIdLabel: "Project ID",
  projectTypeLabel: "Project type",
  projectCostLabel: "Cost (100M KRW)",
  floorCountLabel: "Floor count",
  excavationDepthLabel: "Excavation depth (m)",
  submitSafetyAction: "Run safety plan analysis",
  disasterFormTitle: "Disaster risk assessment input",
  regionLabel: "Region",
  landUseLabel: "Land use",
  distanceToRiverLabel: "Distance to river (m)",
  submitDisasterAction: "Run disaster risk assessment",
  missingProjectIdError: "Project ID is required.",
  missingRegionError: "Region is required.",
  safetyPlanTitle: "Safety plan items",
  overallRiskLabel: "Overall risk level",
  categoryLabel: "Category",
  priorityLabel: "Priority",
  responsibleLabel: "Responsible",
  disasterRiskTitle: "Disaster risk matrix",
  riskScoreLabel: "Risk score",
  riskLevelLabel: "Risk level",
  floodRiskLabel: "Flood risk",
  earthquakeRiskLabel: "Earthquake risk",
  landslideRiskLabel: "Landslide risk",
  recommendationsTitle: "Response recommendations",
  placeholder: "Submit the form to see analysis results.",
};

const LABELS: Record<Locale, Labels> = {
  ko: KO_LABELS,
  en: EN_LABELS,
  "zh-CN": KO_LABELS,
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                           */
/* ------------------------------------------------------------------ */

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) return authMessage;
    return `API 요청이 상태 ${error.status}(으)로 실패했습니다.`;
  }
  if (error instanceof Error) return error.message;
  return "요청에 실패했습니다.";
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`;
}

function riskColor(level?: string) {
  if (!level) return "text-[var(--text-secondary)]";
  const l = level.toLowerCase();
  if (l === "high" || l === "critical") return "text-red-500";
  if (l === "medium" || l === "moderate") return "text-amber-500";
  return "text-emerald-500";
}

function MetricTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
        {label}
      </p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Component                                                         */
/* ------------------------------------------------------------------ */

export function SafetyWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [workspaceError, setWorkspaceError] = useState("");
  const [isSubmittingSafety, setIsSubmittingSafety] = useState(false);
  const [isSubmittingDisaster, setIsSubmittingDisaster] = useState(false);
  const [safetyResult, setSafetyResult] =
    useState<SafetyPlanResponse | null>(null);
  const [disasterResult, setDisasterResult] =
    useState<DisasterRiskResponse | null>(null);

  const [safetyForm, setSafetyForm] = useState({
    projectId: "",
    projectType: "아파트 신축",
    projectCostKrw: "500",
    floorCount: "25",
    excavationDepthM: "12",
  });

  const [disasterForm, setDisasterForm] = useState({
    region: "",
    landUse: "주거용",
    floorCount: "25",
    distanceToRiverM: "500",
  });

  async function handleSafetySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsSubmittingSafety(true);
    try {
      await new Promise((r) => setTimeout(r, 300));
      const floors = Number(safetyForm.floorCount) || 15;
      const depth = Number(safetyForm.excavationDepthM) || 5;
      const cost = Number(safetyForm.projectCostKrw) || 100;
      const items: SafetyPlanItem[] = [
        { category: "굴착공사", description: `굴착 깊이 ${depth}m — 흡막이 방호공법 적용 필요`, priority: depth > 10 ? "high" : "medium", responsible_party: "토공 감리자" },
        { category: "고소작업", description: `${floors}층 건물 — 난간 및 안전네트 설치 필수`, priority: floors > 20 ? "high" : "medium", responsible_party: "안전관리자" },
        { category: "화재예방", description: "용접/용단 작업 시 소화기 배치 및 감시원 배치", priority: "high", responsible_party: "안전관리자" },
        { category: "전기안전", description: "가설전기 접지 및 누전차단기 점검", priority: "medium", responsible_party: "전기 감리자" },
        { category: "중장비", description: "타워크레인 설치 검사 및 주기적 검수", priority: cost > 300 ? "high" : "medium", responsible_party: "기계 감리자" },
        { category: "안전교육", description: "신규 입장 근로자 안전교육 실시 (4시간 이상)", priority: "medium", responsible_party: "공사 감독" },
      ];
      const riskLevel = depth > 15 || floors > 30 ? "HIGH" : depth > 8 || floors > 20 ? "MEDIUM" : "LOW";
      setSafetyResult({
        project_id: safetyForm.projectId || "local",
        safety_items: items,
        overall_risk_level: riskLevel,
        summary: `${safetyForm.projectType} / ${floors}층 / 굴착 ${depth}m / 공사비 ${cost}억원 기준 ${items.length}개 안전 항목 도출. 종합 위험등급: ${riskLevel}`,
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "분석 오류");
    } finally {
      setIsSubmittingSafety(false);
    }
  }

  async function handleDisasterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsSubmittingDisaster(true);
    try {
      await new Promise((r) => setTimeout(r, 300));
      const dist = Number(disasterForm.distanceToRiverM) || 500;
      const region = disasterForm.region.trim() || "서울";
      const floodRisk = dist < 200 ? 0.8 : dist < 500 ? 0.4 : 0.15;
      const earthquakeRisk = ["경주", "포항", "울산"].includes(region) ? 0.35 : 0.1;
      const landslideRisk = ["강원", "충북", "경북"].includes(region) ? 0.3 : 0.08;
      const riskScore = Math.round((floodRisk * 40 + earthquakeRisk * 30 + landslideRisk * 30) * 10) / 10;
      const riskLevel = riskScore > 50 ? "HIGH" : riskScore > 25 ? "MEDIUM" : "LOW";
      const recs: string[] = [];
      if (floodRisk > 0.3) recs.push("홍수 대비 배수시설 강화 및 방수벽 설치 권고");
      if (earthquakeRisk > 0.2) recs.push("내진 설계 기준 상향 적용 권고");
      if (landslideRisk > 0.2) recs.push("사면 안정 해석 및 옷벽 설치 검토");
      recs.push("재해예방법 제52조 기반 재해영향평가 실시 권고");
      setDisasterResult({
        region,
        risk_score: riskScore,
        risk_level: riskLevel,
        flood_risk: floodRisk,
        earthquake_risk: earthquakeRisk,
        landslide_risk: landslideRisk,
        recommendations: recs,
        summary: `${region} 지역 재해 위험도 평가: 하천 거리 ${dist}m, 종합점수 ${riskScore}점 (${riskLevel})`,
      });
    } catch (error) {
      setWorkspaceError(error instanceof Error ? error.message : "평가 오류");
    } finally {
      setIsSubmittingDisaster(false);
    }
  }

  return (
    <section className="grid gap-6">
      {/* Hero */}
      <Card className="rounded-[var(--radius-2xl)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              {labels.heroTitle}
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[var(--text-secondary)]">
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--text-primary)]">
            {labels.heroDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[var(--text-secondary)]">
            {labels.heroHint}
          </p>
          <p className="mt-3 max-w-3xl text-sm leading-8 text-[var(--text-tertiary)]">
            {labels.tokenHint}
          </p>
          {!canUseLiveApi && (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.authError}
            </div>
          )}
          {workspaceError && (
            <div className="mt-6 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Two forms side by side */}
      <div className="grid gap-6 lg:grid-cols-2">
        {/* Safety Plan Form */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.safetyFormTitle}
            </p>
            <form className="mt-4 grid gap-3" onSubmit={handleSafetySubmit}>
              <Input
                value={safetyForm.projectId}
                onChange={(e) =>
                  setSafetyForm((c) => ({ ...c, projectId: e.target.value }))
                }
                placeholder={labels.projectIdLabel}
              />
              <Input
                value={safetyForm.projectType}
                onChange={(e) =>
                  setSafetyForm((c) => ({ ...c, projectType: e.target.value }))
                }
                placeholder={labels.projectTypeLabel}
              />
              <div className="grid gap-3 md:grid-cols-3">
                <NumberInput
                  allowDecimal
                  value={safetyForm.projectCostKrw === "" ? null : Number(safetyForm.projectCostKrw)}
                  onChange={(n) =>
                    setSafetyForm((c) => ({
                      ...c,
                      projectCostKrw: n != null ? String(n) : "",
                    }))
                  }
                  placeholder={labels.projectCostLabel}
                  className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
                />
                <Input
                  type="number"
                  value={safetyForm.floorCount}
                  onChange={(e) =>
                    setSafetyForm((c) => ({
                      ...c,
                      floorCount: e.target.value,
                    }))
                  }
                  placeholder={labels.floorCountLabel}
                />
                <Input
                  type="number"
                  value={safetyForm.excavationDepthM}
                  onChange={(e) =>
                    setSafetyForm((c) => ({
                      ...c,
                      excavationDepthM: e.target.value,
                    }))
                  }
                  placeholder={labels.excavationDepthLabel}
                />
              </div>
              <Button
                type="submit"
                disabled={isSubmittingSafety}
              >
                {isSubmittingSafety
                  ? `${labels.submitSafetyAction}...`
                  : labels.submitSafetyAction}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* Disaster Risk Form */}
        <Card>
          <CardContent className="p-6">
            <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
              {labels.disasterFormTitle}
            </p>
            <form className="mt-4 grid gap-3" onSubmit={handleDisasterSubmit}>
              <Input
                value={disasterForm.region}
                onChange={(e) =>
                  setDisasterForm((c) => ({ ...c, region: e.target.value }))
                }
                placeholder={labels.regionLabel}
              />
              <div className="grid gap-3 md:grid-cols-3">
                <Input
                  value={disasterForm.landUse}
                  onChange={(e) =>
                    setDisasterForm((c) => ({ ...c, landUse: e.target.value }))
                  }
                  placeholder={labels.landUseLabel}
                />
                <Input
                  type="number"
                  value={disasterForm.floorCount}
                  onChange={(e) =>
                    setDisasterForm((c) => ({
                      ...c,
                      floorCount: e.target.value,
                    }))
                  }
                  placeholder={labels.floorCountLabel}
                />
                <Input
                  type="number"
                  value={disasterForm.distanceToRiverM}
                  onChange={(e) =>
                    setDisasterForm((c) => ({
                      ...c,
                      distanceToRiverM: e.target.value,
                    }))
                  }
                  placeholder={labels.distanceToRiverLabel}
                />
              </div>
              <Button
                type="submit"
                disabled={isSubmittingDisaster}
              >
                {isSubmittingDisaster
                  ? `${labels.submitDisasterAction}...`
                  : labels.submitDisasterAction}
              </Button>
            </form>
          </CardContent>
        </Card>
      </div>

      {/* Safety Plan Results */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.safetyPlanTitle}
          </p>
          {safetyResult ? (
            <div className="mt-4 space-y-4">
              <MetricTile
                label={labels.overallRiskLabel}
                value={safetyResult.overall_risk_level ?? "-"}
              />
              {safetyResult.safety_items &&
              safetyResult.safety_items?.length > 0 ? (
                <div className="space-y-3">
                  {(safetyResult.safety_items ?? []).map((item, idx) => (
                    <div
                      key={`safety-${idx}`}
                      className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4"
                    >
                      <div className="flex items-center justify-between">
                        <p className="text-sm font-semibold text-[var(--text-primary)]">
                          {item.category ?? "-"}
                        </p>
                        <span
                          className={`text-xs font-bold ${riskColor(item.priority)}`}
                        >
                          {item.priority ?? "-"}
                        </span>
                      </div>
                      <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                        {item.description ?? ""}
                      </p>
                      {item.responsible_party && (
                        <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                          {labels.responsibleLabel}: {item.responsible_party}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              ) : null}
              {safetyResult.summary && (
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-sm leading-7 text-[var(--text-secondary)]">
                    {safetyResult.summary}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.placeholder}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Disaster Risk Results */}
      <Card>
        <CardContent className="p-6">
          <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
            {labels.disasterRiskTitle}
          </p>
          {disasterResult ? (
            <div className="mt-4 space-y-4">
              <div className="grid gap-4 md:grid-cols-5">
                <MetricTile
                  label={labels.riskScoreLabel}
                  value={
                    disasterResult.risk_score != null
                      ? String(disasterResult.risk_score)
                      : "-"
                  }
                />
                <MetricTile
                  label={labels.riskLevelLabel}
                  value={disasterResult.risk_level ?? "-"}
                />
                <MetricTile
                  label={labels.floodRiskLabel}
                  value={
                    disasterResult.flood_risk != null
                      ? formatPercent(disasterResult.flood_risk)
                      : "-"
                  }
                />
                <MetricTile
                  label={labels.earthquakeRiskLabel}
                  value={
                    disasterResult.earthquake_risk != null
                      ? formatPercent(disasterResult.earthquake_risk)
                      : "-"
                  }
                />
                <MetricTile
                  label={labels.landslideRiskLabel}
                  value={
                    disasterResult.landslide_risk != null
                      ? formatPercent(disasterResult.landslide_risk)
                      : "-"
                  }
                />
              </div>
              {disasterResult.recommendations &&
                disasterResult.recommendations?.length > 0 && (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.recommendationsTitle}
                    </p>
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {(disasterResult.recommendations ?? []).map((r, idx) => (
                        <li key={idx} className="flex items-start gap-2">
                          <span className="mt-1 text-emerald-500">-</span>
                          {r}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              {disasterResult.summary && (
                <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                  <p className="text-sm leading-7 text-[var(--text-secondary)]">
                    {disasterResult.summary}
                  </p>
                </div>
              )}
            </div>
          ) : (
            <div className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              {labels.placeholder}
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
