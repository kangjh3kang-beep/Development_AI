"use client";

import { useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { ApiClientError, apiClient } from "@/lib/api-client";
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
  heroTitle: "안전 관리 라이브 워크스페이스",
  heroDescription:
    "공사현장 안전 계획과 재해 위험도를 AI가 분석하여 안전 항목 및 위험 매트릭스를 제공합니다.",
  heroHint:
    "POST /lifecycle/construction/safety-plan 및 POST /lifecycle/disaster-risk/assess API를 호출합니다.",
  tokenHint:
    "라이브 API 호출에는 NEXT_PUBLIC_API_ACCESS_TOKEN 또는 localStorage.propai_access_token이 필요합니다.",
  authError: "라이브 워크스페이스 호출을 위해 API 인증이 필요합니다.",
  safetyFormTitle: "안전 계획 분석 입력",
  projectIdLabel: "프로젝트 ID",
  projectTypeLabel: "프로젝트 유형",
  projectCostLabel: "공사비 (억원)",
  floorCountLabel: "층수",
  excavationDepthLabel: "굴착 깊이 (m)",
  submitSafetyAction: "안전 계획 분석 실행",
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
    "Live API calls require NEXT_PUBLIC_API_ACCESS_TOKEN or localStorage.propai_access_token.",
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

    if (!safetyForm.projectId.trim()) {
      setWorkspaceError(labels.missingProjectIdError);
      return;
    }

    setIsSubmittingSafety(true);
    try {
      const res = await apiClient.post<SafetyPlanResponse>(
        "/lifecycle/construction/safety-plan",
        {
          useMock: false,
          body: {
            project_id: safetyForm.projectId.trim(),
            project_type: safetyForm.projectType,
            project_cost_krw:
              Number(safetyForm.projectCostKrw) * 100_000_000 || undefined,
            floor_count: Number(safetyForm.floorCount) || undefined,
            excavation_depth_m:
              Number(safetyForm.excavationDepthM) || undefined,
          },
        },
      );
      setSafetyResult(res);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSubmittingSafety(false);
    }
  }

  async function handleDisasterSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");

    if (!disasterForm.region.trim()) {
      setWorkspaceError(labels.missingRegionError);
      return;
    }

    setIsSubmittingDisaster(true);
    try {
      const res = await apiClient.post<DisasterRiskResponse>(
        "/lifecycle/disaster-risk/assess",
        {
          useMock: false,
          body: {
            region: disasterForm.region.trim(),
            land_use: disasterForm.landUse,
            floor_count: Number(disasterForm.floorCount) || undefined,
            distance_to_river_m:
              Number(disasterForm.distanceToRiverM) || undefined,
          },
        },
      );
      setDisasterResult(res);
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error, labels.authError));
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
                <Input
                  type="number"
                  value={safetyForm.projectCostKrw}
                  onChange={(e) =>
                    setSafetyForm((c) => ({
                      ...c,
                      projectCostKrw: e.target.value,
                    }))
                  }
                  placeholder={labels.projectCostLabel}
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
                disabled={!canUseLiveApi || isSubmittingSafety}
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
                disabled={!canUseLiveApi || isSubmittingDisaster}
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
              safetyResult.safety_items.length > 0 ? (
                <div className="space-y-3">
                  {safetyResult.safety_items.map((item, idx) => (
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
                disasterResult.recommendations.length > 0 && (
                  <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5">
                    <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
                      {labels.recommendationsTitle}
                    </p>
                    <ul className="mt-3 space-y-2 text-sm leading-7 text-[var(--text-secondary)]">
                      {disasterResult.recommendations.map((r, idx) => (
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
