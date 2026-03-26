"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardTitle, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

type ProjectSummary = {
  id: string;
  name: string;
  status: string;
  total_area_sqm: number | null;
};

type PaginatedResponse<T> = {
  items: T[];
  page: number;
  page_size: number;
  has_next: boolean;
};

type MaterialSnapshot = {
  as_of: string;
  items: Array<{
    material_code: string;
    material_name: string;
    current_unit_price_krw: number;
    latest_price_index: number;
    mom_change_ratio: number;
    yoy_change_ratio: number;
    estimated_project_cost_krw: number | null;
    alert_level: string;
    history: Array<{ source_name: string }>;
  }>;
  alerts: Array<{ title: string; detail: string }>;
};

type EscalationSnapshot = {
  adjusted_cost_krw: number;
  overall_escalation_ratio: number;
  ppi_source: string;
  summary: string;
  material_impacts: Array<{
    material_code: string;
    material_name: string;
    weight_ratio: number;
    delta_ratio: number;
    cost_impact_krw: number;
  }>;
};

function formatCurrency(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(2)}%`;
}

function extractErrorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return "API 인증이 필요합니다.";
    }
    return `API request failed with status ${error.status}.`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "Request failed.";
}

export function ConstructionCostWorkspaceClient({
  locale,
}: {
  locale: Locale;
}) {
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [manualProjectId, setManualProjectId] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [materialResult, setMaterialResult] = useState<MaterialSnapshot | null>(null);
  const [escalationResult, setEscalationResult] =
    useState<EscalationSnapshot | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [form, setForm] = useState({
    regionCode: "KR",
    materialCodes:
      "ready_mix_concrete,rebar_sd400_d13,h_beam_steel,glass_lowe_panel",
    baseCost: "18500000000",
    baselineYear: "2024",
    targetYear: "2027",
    durationMonths: "20",
    materialShare: "0.62",
    laborShare: "0.28",
    overheadShare: "0.10",
    contingency: "0.07",
  });

  const projectsQuery = useQuery({
    queryKey: ["projects", "cost-intelligence-picker"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<PaginatedResponse<ProjectSummary>>(
        "/projects?page=1&page_size=20",
        { useMock: false },
      ),
  });

  useEffect(() => {
    if (!selectedProjectId && projectsQuery.data?.items.length) {
      setSelectedProjectId(projectsQuery.data.items[0].id);
    }
  }, [projectsQuery.data, selectedProjectId]);

  const selectedProject =
    projectsQuery.data?.items.find((project) => project.id === selectedProjectId) ??
    null;
  const activeProjectId = manualProjectId.trim() || selectedProject?.id || "";

  const materialQuery = useQuery({
    queryKey: ["cost-intelligence", "materials", activeProjectId || "portfolio", form.regionCode, form.materialCodes],
    enabled: canUseLiveApi,
    queryFn: () => {
      const params = new URLSearchParams({
        region_code: form.regionCode.trim() || "KR",
        material_codes: form.materialCodes.trim(),
      });
      if (activeProjectId) {
        params.set("project_id", activeProjectId);
      }
      return apiClient.get<MaterialSnapshot>(
        `/cost-intelligence/material-prices/latest?${params.toString()}`,
        { useMock: false },
      );
    },
  });

  const escalationQuery = useQuery({
    queryKey: ["cost-intelligence", "escalation", activeProjectId],
    enabled: canUseLiveApi && Boolean(activeProjectId),
    queryFn: () =>
      apiClient.get<EscalationSnapshot>(
        `/cost-intelligence/escalation/${activeProjectId}/latest`,
        { useMock: false },
      ),
  });

  useEffect(() => {
    setMaterialResult(null);
    setEscalationResult(null);
  }, [activeProjectId]);

  async function handleRefreshMaterials(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    setIsRefreshing(true);
    try {
      const response = await apiClient.post<MaterialSnapshot>(
        "/cost-intelligence/material-prices/refresh",
        {
          useMock: false,
          body: {
            project_id: activeProjectId || null,
            region_code: form.regionCode.trim() || "KR",
            material_codes: form.materialCodes.split(",").map((item) => item.trim()).filter(Boolean),
          },
        },
      );
      setMaterialResult(response);
      void materialQuery.refetch();
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error));
    } finally {
      setIsRefreshing(false);
    }
  }

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setWorkspaceError("");
    if (!activeProjectId) {
      setWorkspaceError("실제 프로젝트 UUID가 필요합니다.");
      return;
    }
    setIsAnalyzing(true);
    try {
      const response = await apiClient.post<EscalationSnapshot>(
        "/cost-intelligence/escalation/analyze",
        {
          useMock: false,
          body: {
            project_id: activeProjectId,
            base_construction_cost_krw: Number(form.baseCost),
            baseline_year: Number(form.baselineYear),
            target_year: Number(form.targetYear),
            construction_duration_months: Number(form.durationMonths),
            material_share_ratio: Number(form.materialShare),
            labor_share_ratio: Number(form.laborShare),
            overhead_share_ratio: Number(form.overheadShare),
            contingency_ratio: Number(form.contingency),
            region_code: form.regionCode.trim() || "KR",
            material_codes: form.materialCodes.split(",").map((item) => item.trim()).filter(Boolean),
          },
        },
      );
      setEscalationResult(response);
      void escalationQuery.refetch();
    } catch (error) {
      setWorkspaceError(extractErrorMessage(error));
    } finally {
      setIsAnalyzing(false);
    }
  }

  const materials = materialResult ?? materialQuery.data ?? null;
  const escalation = escalationResult ?? escalationQuery.data ?? null;

  return (
    <section className="grid gap-6">
      <Card className="rounded-[2rem] bg-[var(--surface-strong)] shadow-[0_20px_60px_rgba(19,33,47,0.08)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              COST INTELLIGENCE
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[rgba(19,33,47,0.7)]">
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--foreground)]">
            KCCI 자재가와 PPI 공사비 보정 시뮬레이션
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[rgba(19,33,47,0.72)]">
            프로젝트별 자재 노출액과 최신 공사비 보정안을 실 API 기준으로 확인합니다.
          </p>
          {workspaceError ? (
            <div className="mt-6 rounded-[1.5rem] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {workspaceError}
            </div>
          ) : null}
        </CardContent>
      </Card>
      <Card>
        <CardContent className="grid gap-5 p-6 lg:grid-cols-[1.3fr_0.7fr]">
          <div className="grid gap-3">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                비용 추적 대상 프로젝트
              </p>
              <CardTitle className="mt-2 text-xl">라이브 프로젝트</CardTitle>
            </div>
            {projectsQuery.isLoading ? (
              <SkeletonLoader count={1} itemClassName="h-14" />
            ) : (
              <div className="grid gap-3">
                {projectsQuery.isError ? (
                  <WorkspaceQueryErrorCard
                    title="프로젝트 목록 로드 실패"
                    description="비용 인텔리전스 대상 프로젝트를 불러오지 못했습니다. 수동 UUID 입력은 계속 사용할 수 있습니다."
                    message={extractErrorMessage(projectsQuery.error)}
                    actionLabel="다시 시도"
                    onRetry={() => {
                      void projectsQuery.refetch();
                    }}
                  />
                ) : null}
                <Select
                  label="라이브 프로젝트"
                  value={selectedProjectId}
                  onValueChange={setSelectedProjectId}
                  options={[
                    {
                      label:
                        projectsQuery.data?.items.length
                          ? "라이브 프로젝트"
                          : "라이브 프로젝트가 아직 없습니다.",
                      value: "",
                      disabled: true,
                    },
                    ...(projectsQuery.data?.items.map((project) => ({
                      label: project.name,
                      value: project.id,
                    })) ?? []),
                  ]}
                />
              </div>
            )}
            <Input
              value={manualProjectId}
              onChange={(event) => setManualProjectId(event.target.value)}
              placeholder="수동 프로젝트 UUID"
            />
          </div>
          <div className="rounded-[1.5rem] bg-[var(--surface-soft)] p-5">
            <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
              현재 대상
            </p>
            <p className="mt-3 text-sm font-semibold text-[var(--foreground)]">
              {(selectedProject?.name ?? activeProjectId) || "-"}
            </p>
            <p className="mt-2 text-sm text-[rgba(19,33,47,0.68)]">
              {selectedProject?.status ?? "수동 대상"}
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-2">
        <Card>
          <CardContent className="grid gap-5 p-6">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                자재가 스냅샷 갱신
              </p>
              <CardTitle className="mt-2 text-xl">최신 자재가 추이</CardTitle>
            </div>
            <form className="grid gap-4" onSubmit={handleRefreshMaterials}>
              <p className="text-xs uppercase tracking-[0.2em] text-[rgba(19,33,47,0.45)]">
                권역 코드
              </p>
              <Input
                value={form.regionCode}
                onChange={(event) =>
                  setForm((current) => ({ ...current, regionCode: event.target.value }))
                }
                placeholder="권역 코드"
              />
              <p className="text-xs uppercase tracking-[0.2em] text-[rgba(19,33,47,0.45)]">
                자재 코드 목록
              </p>
              <Input
                value={form.materialCodes}
                onChange={(event) =>
                  setForm((current) => ({ ...current, materialCodes: event.target.value }))
                }
                placeholder="자재 코드 목록"
              />
              <Button type="submit" disabled={!canUseLiveApi || isRefreshing}>
                {isRefreshing ? "자재가 새로고침..." : "자재가 새로고침"}
              </Button>
            </form>
            {materialQuery.isLoading ? (
              <SkeletonLoader count={3} itemClassName="h-24" />
            ) : null}
            {materialQuery.isError ? (
              <WorkspaceQueryErrorCard
                title="자재가 조회 실패"
                description="최신 자재가 추이를 가져오지 못했습니다. 같은 조건으로 다시 조회하면 됩니다."
                message={extractErrorMessage(materialQuery.error)}
                actionLabel="다시 시도"
                onRetry={() => {
                  void materialQuery.refetch();
                }}
              />
            ) : null}
            {materials ? (
              <div className="grid gap-4">
                <div className="rounded-[1.5rem] border border-[var(--line)] bg-[var(--surface-soft)] p-4 text-sm text-[rgba(19,33,47,0.72)]">
                  <p>소스: {materials.items[0]?.history.at(-1)?.source_name ?? "-"}</p>
                  <p className="mt-2">{new Date(materials.as_of).toLocaleString(locale)}</p>
                  <p className="mt-2">경보: {materials.alerts.length}</p>
                </div>
                {materials.items.map((item) => (
                  <div
                    key={item.material_code}
                    className="rounded-[1.5rem] border border-[var(--line)] bg-white p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--foreground)]">
                          {item.material_name}
                        </p>
                        <p className="mt-1 text-xs uppercase tracking-[0.2em] text-[rgba(19,33,47,0.5)]">
                          {item.material_code}
                        </p>
                      </div>
                      <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                        {item.alert_level}
                      </span>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-3">
                      <p>{formatCurrency(locale, item.current_unit_price_krw)}</p>
                      <p>{item.latest_price_index.toFixed(2)}</p>
                      <p>
                        {item.estimated_project_cost_krw
                          ? formatCurrency(locale, item.estimated_project_cost_krw)
                          : "-"}
                      </p>
                    </div>
                    <p className="mt-4 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                      MoM {formatPercent(item.mom_change_ratio)} / YoY{" "}
                      {formatPercent(item.yoy_change_ratio)}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
        <Card>
          <CardContent className="grid gap-5 p-6">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                공사비 에스컬레이션 분석
              </p>
              <CardTitle className="mt-2 text-xl">최신 공사비 보정안</CardTitle>
            </div>
            <form className="grid gap-4 md:grid-cols-2" onSubmit={handleAnalyze}>
              <Input
                value={form.baseCost}
                onChange={(event) =>
                  setForm((current) => ({ ...current, baseCost: event.target.value }))
                }
                placeholder="기준 공사비(원)"
              />
              <Input
                value={form.durationMonths}
                onChange={(event) =>
                  setForm((current) => ({ ...current, durationMonths: event.target.value }))
                }
                placeholder="공사 기간(개월)"
              />
              <Input
                value={form.baselineYear}
                onChange={(event) =>
                  setForm((current) => ({ ...current, baselineYear: event.target.value }))
                }
                placeholder="기준 연도"
              />
              <Input
                value={form.targetYear}
                onChange={(event) =>
                  setForm((current) => ({ ...current, targetYear: event.target.value }))
                }
                placeholder="목표 연도"
              />
              <Input
                value={form.materialShare}
                onChange={(event) =>
                  setForm((current) => ({ ...current, materialShare: event.target.value }))
                }
                placeholder="자재 비중"
              />
              <Input
                value={form.laborShare}
                onChange={(event) =>
                  setForm((current) => ({ ...current, laborShare: event.target.value }))
                }
                placeholder="노무 비중"
              />
              <Input
                value={form.overheadShare}
                onChange={(event) =>
                  setForm((current) => ({ ...current, overheadShare: event.target.value }))
                }
                placeholder="간접비 비중"
              />
              <Input
                value={form.contingency}
                onChange={(event) =>
                  setForm((current) => ({ ...current, contingency: event.target.value }))
                }
                placeholder="컨틴전시 비율"
              />
              <div className="md:col-span-2">
                <Button type="submit" disabled={!canUseLiveApi || isAnalyzing}>
                  {isAnalyzing ? "에스컬레이션 분석..." : "에스컬레이션 분석"}
                </Button>
              </div>
            </form>
            {activeProjectId && escalationQuery.isLoading ? (
              <SkeletonLoader count={2} itemClassName="h-24" />
            ) : null}
            {activeProjectId && escalationQuery.isError ? (
              <WorkspaceQueryErrorCard
                title="공사비 보정안 조회 실패"
                description="프로젝트의 최신 에스컬레이션 시나리오를 읽지 못했습니다. 새 분석을 수행하거나 다시 조회하세요."
                message={extractErrorMessage(escalationQuery.error)}
                actionLabel="다시 시도"
                onRetry={() => {
                  void escalationQuery.refetch();
                }}
              />
            ) : null}
            {escalation ? (
              <div className="grid gap-4">
                <div className="rounded-[1.5rem] border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                  <p className="text-sm font-semibold text-[var(--foreground)]">
                    보정 후 공사비
                  </p>
                  <p className="mt-3 text-2xl font-bold text-[var(--foreground)]">
                    {formatCurrency(locale, escalation.adjusted_cost_krw)}
                  </p>
                  <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                    상승률: {formatPercent(escalation.overall_escalation_ratio)}
                  </p>
                  <p className="mt-2 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                    소스: {escalation.ppi_source}
                  </p>
                  <p className="mt-2 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                    {escalation.summary}
                  </p>
                </div>
                {escalation.material_impacts.map((item) => (
                  <div
                    key={item.material_code}
                    className="rounded-[1.5rem] border border-[var(--line)] bg-white p-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <p className="text-sm font-semibold text-[var(--foreground)]">
                        {item.material_name}
                      </p>
                      <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                        {formatPercent(item.weight_ratio)}
                      </span>
                    </div>
                    <p className="mt-3 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                      Delta {formatPercent(item.delta_ratio)} / Impact{" "}
                      {formatCurrency(locale, item.cost_impact_krw)}
                    </p>
                  </div>
                ))}
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
