"use client";

/**
 * UnderwritingSection — "투자 언더라이팅" 접힘 섹션(배선 캠페인 2차).
 *
 * 배경: 배선설계도 P2 트리아지 ② 프론트 배선 후보 중 underwriting(routers/underwriting.py,
 * POST /api/v1/underwriting/{project_id})는 리스크 등급·추천·수익성 지표(ROI 배수·부채비율)를
 * 산출하는 투자 심사 엔진이 이미 완성돼 있는데 화면이 없어 아무도 호출하지 못했다.
 * ProjectFinanceWorkspaceClient 하단에 additive로 붙는다(기존 수지/전세리스크 흐름은 무수정).
 *
 * ★endpoint는 project_id를 경로에도 포함한다(라우터가 path/body project_id 일치를 검증하므로
 * buildUnderwritingBody가 ctx.projectId를 body에 채우고, 이 컴포넌트가 동일 projectId로
 * `/underwriting/{projectId}` 경로를 조립한다).
 *
 * 1차 ESG 패턴 재사용: ExtendedAnalysisPanel + lib/workspace-extended-panels.ts 순수 바디 조립.
 * 기본 접힘(AdvancedDrawer). SSOT 커밋 없음(무날조) — 언더라이팅 응답(risk_score·recommendation
 * 등)은 심사 결과이지 수지 SSOT(FeasibilityData)와 물리량이 다른 파생 지표라 되먹임하지 않는다.
 */

import { useMemo, type ReactNode } from "react";
import { AdvancedDrawer } from "@/components/common/AdvancedDrawer";
import {
  ExtendedAnalysisPanel,
  type ExtendedAnalysisFormField,
} from "@/components/common/ExtendedAnalysisPanel";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  buildWorkspaceExtendedContext,
  underwritingInitialValues,
  buildUnderwritingBody,
} from "@/lib/workspace-extended-panels";
import { formatWon, formatPercent01, formatNumber } from "@/lib/esg-extended-panels";

type UnderwritingResponse = {
  risk_level: string;
  risk_score: number;
  recommendation: string;
  projected_profit_krw: number;
  profit_margin_ratio: number;
  debt_ratio: number;
  equity_multiple: number;
  jeonse_ratio: number | null;
  key_risks: Array<{ factor?: string; detail?: string; [key: string]: unknown }>;
  narrative: string;
};

function renderUnderwritingResult(raw: unknown): ReactNode {
  const r = raw as UnderwritingResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        <Tile label="리스크 등급" value={r.risk_level} />
        <Tile label="리스크 점수" value={formatNumber(r.risk_score)} />
        <Tile label="투자 추천" value={r.recommendation} />
        <Tile label="예상 이익" value={formatWon(r.projected_profit_krw)} />
        {/* profit_margin_ratio/debt_ratio = UnderwritingService 산출 0.0~1.0 비율(현재 계약상
            프론트가 확보한 가장 명확한 근거는 값 자체의 정의역 — 백엔드가 %로 재변환하지 않고
            그대로 반환하는 다른 비율 필드들과 동일 관례를 따른다). */}
        <Tile label="이익률" value={formatPercent01(r.profit_margin_ratio)} />
        <Tile label="부채비율" value={formatPercent01(r.debt_ratio)} />
        <Tile label="자기자본 배수" value={`${formatNumber(r.equity_multiple)}x`} />
      </div>
      {r.narrative ? (
        <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
          {r.narrative}
        </div>
      ) : null}
      {(r.key_risks?.length ?? 0) > 0 ? (
        <div className="grid gap-2">
          {r.key_risks.map((risk, i) => (
            <div key={i} className="rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              {risk.factor ? <span className="font-semibold text-[var(--text-primary)]">{String(risk.factor)}: </span> : null}
              {risk.detail ? String(risk.detail) : JSON.stringify(risk)}
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}

function Tile({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="label-caps text-[var(--text-tertiary)]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

export function UnderwritingSection({ projectId }: { projectId: string }) {
  const projectName = useProjectContextStore((s) => s.projectName);
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const authErrorMessage = "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.";

  const ctx = useMemo(
    () => buildWorkspaceExtendedContext({ projectId, projectName, siteAnalysis, feasibilityData }),
    [projectId, projectName, siteAnalysis, feasibilityData],
  );

  const fields: ExtendedAnalysisFormField[] = [
    { key: "projectName", label: "프로젝트명", type: "text" },
    { key: "totalCostKrw", label: "총사업비 (원)", type: "number" },
    { key: "projectedRevenueKrw", label: "예상 매출 (원)", type: "number" },
    { key: "acquisitionPriceKrw", label: "취득가(매입가, 원)", type: "number" },
    { key: "equityKrw", label: "자기자본 (원)", type: "number" },
    { key: "debtKrw", label: "부채 (원)", type: "number" },
    { key: "jeonseRatio", label: "전세가율 (0~1, 선택)", type: "number" },
  ];

  return (
    <AdvancedDrawer label="투자 언더라이팅 분석">
      <ExtendedAnalysisPanel
        key={`underwriting-${ctx.totalCostWon ?? "none"}-${ctx.equityWon ?? "none"}`}
        title="투자 심사(언더라이팅) 실행"
        fields={fields}
        initialValues={underwritingInitialValues(ctx)}
        buildBody={(values) => buildUnderwritingBody(values, ctx)}
        endpoint={`/underwriting/${projectId}`}
        submitLabel="언더라이팅 실행"
        resultTitle="언더라이팅 결과"
        renderResult={renderUnderwritingResult}
        canUseLiveApi={canUseLiveApi}
        authErrorMessage={authErrorMessage}
        placeholderMessage="폼을 제출하면 결과가 표시됩니다."
        requiredPositiveFields={["totalCostKrw", "projectedRevenueKrw", "acquisitionPriceKrw", "equityKrw"]}
      />
    </AdvancedDrawer>
  );
}
