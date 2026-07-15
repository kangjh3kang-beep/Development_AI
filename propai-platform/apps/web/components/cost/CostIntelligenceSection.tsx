"use client";

/**
 * CostIntelligenceSection — "자재가·에스컬레이션(KCCI)" 접힘 섹션(배선 캠페인 2차).
 *
 * 배경: 배선설계도 P2 트리아지 ② 프론트 배선 후보 중 cost-intelligence(routers/cost_intelligence.py)는
 * KCCI(대한건설정책연구원) 자재가 스냅샷·공사비 에스컬레이션(연도별 PPI 전망) 서비스가 이미
 * 완성돼 있는데 화면이 없어 아무도 호출하지 못했다. BimCostDashboard 하단에 additive로 붙는다
 * (기존 BIM 공사비 시뮬레이션 흐름은 무수정).
 *
 * 구성 2건:
 *   ① 최신 자재가 스냅샷(GET /material-prices/latest) — project_id 스코프 자동조회(폼 없음,
 *      ParkingLogView와 동일한 useQuery 자동조회 패턴).
 *   ② 공사비 에스컬레이션 분석(POST /escalation/analyze) — 1차 ESG 패턴 그대로 재사용
 *      (ExtendedAnalysisPanel + lib/workspace-extended-panels.ts 순수 바디 조립).
 *
 * 기본 접힘(AdvancedDrawer). SSOT 커밋 없음(무날조) — costData는 BIM/개산 공사비 전용
 * 슬롯이고, 에스컬레이션은 "미래 시점 전망치"라 물리량이 달라 되먹임하지 않는다.
 */

import { useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Card, CardContent } from "@propai/ui";
import { AdvancedDrawer } from "@/components/common/AdvancedDrawer";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import {
  ExtendedAnalysisPanel,
  type ExtendedAnalysisFormField,
} from "@/components/common/ExtendedAnalysisPanel";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  buildWorkspaceExtendedContext,
  costEscalationInitialValues,
  buildCostEscalationBody,
} from "@/lib/workspace-extended-panels";
import { formatWon, formatPercent01, formatNumber } from "@/lib/esg-extended-panels";

/* ── ① 최신 자재가 스냅샷 ── */

type MaterialPriceItem = {
  material_code: string;
  material_name: string;
  category: string;
  unit: string;
  current_unit_price_krw: number;
  latest_price_index: number;
  mom_change_ratio: number;
  yoy_change_ratio: number;
  estimated_project_cost_krw: number | null;
  alert_level: string;
};

type MaterialPriceAlert = {
  material_code: string;
  severity: string;
  title: string;
  detail: string;
};

type MaterialPriceSnapshot = {
  as_of: string;
  region_code: string;
  items: MaterialPriceItem[];
  alerts: MaterialPriceAlert[];
};

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "요청 실패.";
}

function MaterialPricesPanel({ projectId }: { projectId: string }) {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["cost-intelligence", "material-prices", "latest", projectId],
    queryFn: () =>
      apiClient.get<MaterialPriceSnapshot>(
        `/cost-intelligence/material-prices/latest?project_id=${encodeURIComponent(projectId)}`,
        { useMock: false },
      ),
  });

  return (
    <Card>
      <CardContent className="p-6">
        <p className="label-caps text-[var(--text-tertiary)]">
          최신 자재가 스냅샷 (KCCI)
        </p>

        {isLoading ? <SkeletonLoader count={1} itemClassName="h-40" className="mt-4" /> : null}

        {isError ? (
          <div className="mt-4">
            <WorkspaceQueryErrorCard
              title="자재가 스냅샷을 불러오지 못했습니다."
              description="네트워크 상태를 확인한 뒤 다시 시도하세요."
              message={extractErrorMessage(error)}
              actionLabel="다시 시도"
              onRetry={() => {
                void refetch();
              }}
            />
          </div>
        ) : null}

        {data ? (
          <div className="mt-4 space-y-4">
            <p className="text-xs text-[var(--text-tertiary)]">
              기준일 {new Date(data.as_of).toLocaleDateString("ko-KR")} · 지역 {data.region_code}
            </p>
            {data.items.length > 0 ? (
              <div className="grid gap-2">
                {data.items.map((item) => (
                  <div
                    key={item.material_code}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-[var(--r-card)] bg-[var(--surface-soft)] px-4 py-3 text-xs"
                  >
                    <span className="font-semibold text-[var(--text-primary)]">
                      {item.material_name} <span className="text-[var(--text-tertiary)]">({item.category})</span>
                    </span>
                    <span className="text-[var(--text-secondary)]">
                      {formatWon(item.current_unit_price_krw)}/{item.unit} · 지수 {formatNumber(item.latest_price_index)}
                    </span>
                    <span className="text-[var(--text-tertiary)]">
                      전월대비 {formatPercent01(item.mom_change_ratio)} · 전년대비 {formatPercent01(item.yoy_change_ratio)}
                    </span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-bold uppercase ${
                        item.alert_level === "high"
                          ? "bg-[color-mix(in_srgb,var(--status-error)_12%,transparent)] text-[var(--status-error)]"
                          : item.alert_level === "medium"
                            ? "bg-[color-mix(in_srgb,var(--status-warning)_12%,transparent)] text-[var(--status-warning)]"
                            : "bg-[color-mix(in_srgb,var(--status-success)_12%,transparent)] text-[var(--status-success)]"
                      }`}
                    >
                      {item.alert_level}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-7 text-[var(--text-secondary)]">
                조회된 자재가 스냅샷이 없습니다.
              </p>
            )}
            {data.alerts.length > 0 ? (
              <div className="grid gap-2">
                {data.alerts.map((alert, i) => (
                  <div key={`${alert.material_code}-${i}`} className="rounded-[var(--r-card)] bg-[var(--surface-soft)] px-4 py-3 text-xs">
                    <span className="font-semibold text-[var(--text-primary)]">{alert.title}</span>
                    <p className="mt-1 text-[var(--text-secondary)]">{alert.detail}</p>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/* ── ② 공사비 에스컬레이션 분석 ── */

type CostEscalationResponse = {
  baseline_year: number;
  target_year: number;
  base_construction_cost_krw: number;
  adjusted_cost_krw: number;
  escalation_amount_krw: number;
  overall_escalation_ratio: number;
  contingency_amount_krw: number;
  ppi_source: string;
  material_impacts: Array<{
    material_name: string;
    weight_ratio: number;
    delta_ratio: number;
    cost_impact_krw: number;
  }>;
  yearly_projection: Array<{ year: number; escalation_ratio: number; projected_cost_krw: number }>;
  alerts: Array<{ severity: string; title: string; detail: string }>;
  summary: string;
};

function renderEscalationResult(raw: unknown): ReactNode {
  const r = raw as CostEscalationResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        <Tile label={`${r.baseline_year}→${r.target_year} 조정 공사비`} value={formatWon(r.adjusted_cost_krw)} />
        {/* overall_escalation_ratio = escalation_amount_krw/base_construction_cost_krw(0.0~1.0 비율,
            cost_escalation_engine.py round(...,4) — ":.1%" 포맷 문자열로도 확인됨). */}
        <Tile label="전체 상승률" value={formatPercent01(r.overall_escalation_ratio)} />
        <Tile label="상승 금액" value={formatWon(r.escalation_amount_krw)} />
        <Tile label="예비비" value={formatWon(r.contingency_amount_krw)} />
        <Tile label="PPI 출처" value={r.ppi_source} />
      </div>
      {r.summary ? (
        <div className="rounded-[var(--r-card)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
          {r.summary}
        </div>
      ) : null}
      {(r.material_impacts?.length ?? 0) > 0 ? (
        <div className="grid gap-2">
          {r.material_impacts.map((m, i) => (
            <div key={i} className="flex items-center justify-between rounded-[var(--r-card)] bg-[var(--surface-soft)] px-3 py-2 text-xs">
              <span className="text-[var(--text-secondary)]">{m.material_name} (가중 {formatPercent01(m.weight_ratio)})</span>
              <span className="text-[var(--text-primary)]">{formatPercent01(m.delta_ratio)} · {formatWon(m.cost_impact_krw)}</span>
            </div>
          ))}
        </div>
      ) : null}
      {(r.yearly_projection?.length ?? 0) > 0 ? (
        <div className="grid gap-2">
          {r.yearly_projection.map((y) => (
            <div key={y.year} className="flex items-center justify-between rounded-[var(--r-card)] bg-[var(--surface)] px-3 py-2 text-xs">
              <span className="text-[var(--text-secondary)]">{y.year}년</span>
              <span className="text-[var(--text-primary)]">+{formatPercent01(y.escalation_ratio)}</span>
              <span className="text-[var(--text-tertiary)]">{formatWon(y.projected_cost_krw)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}

function Tile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-[var(--r-card)] bg-[var(--surface)] p-4">
      <p className="label-caps text-[var(--text-tertiary)]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

/* ── 조립: 컴포넌트 ── */

export function CostIntelligenceSection({ projectId }: { projectId: string }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);
  const costData = useProjectContextStore((s) => s.costData);

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const authErrorMessage = "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.";

  const ctx = useMemo(
    () => buildWorkspaceExtendedContext({ projectId, siteAnalysis, designData, feasibilityData, costData }),
    [projectId, siteAnalysis, designData, feasibilityData, costData],
  );

  const escalationFields: ExtendedAnalysisFormField[] = [
    { key: "baseConstructionCostKrw", label: "기준 공사비 (원)", type: "number" },
    { key: "baselineYear", label: "기준 연도", type: "number", allowDecimal: false },
    { key: "targetYear", label: "목표 연도", type: "number", allowDecimal: false },
    { key: "constructionDurationMonths", label: "공사 기간 (개월)", type: "number", allowDecimal: false },
    { key: "regionCode", label: "지역 코드", type: "text" },
  ];

  return (
    <AdvancedDrawer label="자재가·에스컬레이션 분석 (KCCI)">
      <div className="grid gap-6">
        <MaterialPricesPanel projectId={projectId} />
        <ExtendedAnalysisPanel
          key={`cost-escalation-${ctx.totalConstructionCostWon ?? "none"}`}
          title="공사비 에스컬레이션 분석"
          fields={escalationFields}
          initialValues={costEscalationInitialValues(ctx)}
          buildBody={(values) => buildCostEscalationBody(values, ctx)}
          endpoint="/cost-intelligence/escalation/analyze"
          submitLabel="에스컬레이션 분석 실행"
          resultTitle="에스컬레이션 분석 결과"
          renderResult={renderEscalationResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={["baseConstructionCostKrw", "targetYear"]}
        />
      </div>
    </AdvancedDrawer>
  );
}
