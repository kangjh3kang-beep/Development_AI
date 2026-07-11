"use client";

/**
 * CadCorrectionSection — "CAD 파라메트릭 자동 보정" 접힘 섹션(배선 캠페인 2차).
 *
 * 배경: 배선설계도 P2 트리아지 ② 프론트 배선 후보 중 cad-correction(routers/cad_correction.py,
 * Phase 15)은 건축물 설계안의 건폐율/용적률/높이 법규 적합성 검증 + 위반 시 자동 보정(반복
 * 알고리즘)이 이미 완성돼 있는데 화면이 없어 아무도 호출하지 못했다. CadBimIntegrationPanel
 * 하단에 additive로 붙는다(기존 2D/3D 생성·편집 흐름은 무수정).
 *
 * ★project_id 필드가 없다(라우터 계약 확인 결과 — BuildingPayload/RegulationPayload에
 * 프로젝트 식별자가 없음). building/regulation 중첩 객체만 조립한다.
 *
 * 1차 ESG 패턴 재사용: ExtendedAnalysisPanel + lib/workspace-extended-panels.ts 순수 바디 조립.
 * 기본 접힘(AdvancedDrawer). SSOT 커밋 없음(무날조) — 이 패널은 "가상의 건축개요 시나리오"를
 * 검증하는 what-if 도구이지, designData(설계 확정 SSOT)를 갱신하는 액션이 아니다.
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
  cadCorrectionInitialValues,
  buildCadCheckBody,
  cadAutoCorrectInitialValues,
  buildCadAutoCorrectBody,
} from "@/lib/workspace-extended-panels";
import { formatNumber } from "@/lib/esg-extended-panels";

type CheckResponse = {
  is_compliant: boolean;
  violations: Array<{ item: string; current_value: number; limit_value: number; excess: number }>;
  building_info: { bcr: number; far: number; height_m: number; gross_floor_area_sqm: number };
};

function renderCheckResult(raw: unknown): ReactNode {
  const r = raw as CheckResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <Tile label="적합 여부" value={r.is_compliant ? "적합" : "부적합"} />
        <Tile label="위반 항목 수" value={`${r.violations?.length ?? 0}건`} />
        <Tile label="건폐율" value={`${formatNumber(r.building_info?.bcr)}%`} />
        <Tile label="용적률" value={`${formatNumber(r.building_info?.far)}%`} />
      </div>
      {(r.violations?.length ?? 0) > 0 ? (
        <div className="grid gap-2">
          {r.violations.map((v, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-xs">
              <span className="text-[var(--text-secondary)]">{v.item}</span>
              <span className="text-[var(--text-primary)]">
                {formatNumber(v.current_value)} / 한도 {formatNumber(v.limit_value)}
              </span>
              <span className="text-[var(--spot)]">초과 {formatNumber(v.excess)}</span>
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}

type CorrectionResponse = {
  is_compliant: boolean;
  iterations: number;
  corrections_applied: string[];
  corrected: Record<string, unknown>;
};

function renderAutoCorrectResult(raw: unknown): ReactNode {
  const r = raw as CorrectionResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <Tile label="보정 후 적합 여부" value={r.is_compliant ? "적합" : "부적합"} />
        <Tile label="반복 횟수" value={`${r.iterations}회`} />
      </div>
      {(r.corrections_applied?.length ?? 0) > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--text-secondary)]">
          {r.corrections_applied.map((c, i) => (
            <li key={i}>{c}</li>
          ))}
        </ul>
      ) : null}
      {r.corrected ? (
        <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4 text-xs text-[var(--text-secondary)]">
          <p className="mb-2 text-[11px] uppercase tracking-[0.2em] text-[var(--text-tertiary)]">보정된 설계안</p>
          {Object.entries(r.corrected).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between py-0.5">
              <span>{k}</span>
              <span className="font-semibold text-[var(--text-primary)]">{JSON.stringify(v)}</span>
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
      <p className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-tertiary)]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}

export function CadCorrectionSection({ projectId }: { projectId: string }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const authErrorMessage = "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.";

  const ctx = useMemo(
    () => buildWorkspaceExtendedContext({ projectId, siteAnalysis, designData }),
    [projectId, siteAnalysis, designData],
  );

  const fields: ExtendedAnalysisFormField[] = [
    { key: "siteAreaSqm", label: "대지면적 (㎡)", type: "number" },
    { key: "buildingAreaSqm", label: "건축면적 (㎡)", type: "number" },
    { key: "numFloors", label: "층수", type: "number", allowDecimal: false },
    { key: "floorHeightM", label: "층고 (m)", type: "number" },
    { key: "maxBcr", label: "건폐율 상한 (%)", type: "number" },
    { key: "maxFar", label: "용적률 상한 (%)", type: "number" },
    { key: "maxHeightM", label: "높이 상한 (m, 0=제한없음)", type: "number" },
  ];

  const autoCorrectFields: ExtendedAnalysisFormField[] = [
    ...fields,
    { key: "maxIter", label: "최대 보정 반복 횟수", type: "number", allowDecimal: false },
  ];

  const requiredPositiveFields = ["siteAreaSqm", "buildingAreaSqm", "numFloors", "maxBcr", "maxFar"];

  return (
    <AdvancedDrawer label="CAD 파라메트릭 자동 보정 (건폐율·용적률·높이 법규 검증)">
      <div className="grid gap-6">
        <ExtendedAnalysisPanel
          key={`cad-check-${ctx.landAreaSqm ?? "none"}-${ctx.effectiveBcrPct ?? "none"}-${ctx.effectiveFarPct ?? "none"}`}
          title="법규 적합성 검증"
          fields={fields}
          initialValues={cadCorrectionInitialValues(ctx)}
          buildBody={(values) => buildCadCheckBody(values)}
          endpoint="/cad-correction/check"
          submitLabel="법규 검증 실행"
          resultTitle="법규 검증 결과"
          renderResult={renderCheckResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={requiredPositiveFields}
        />

        <ExtendedAnalysisPanel
          key={`cad-auto-correct-${ctx.landAreaSqm ?? "none"}-${ctx.effectiveBcrPct ?? "none"}-${ctx.effectiveFarPct ?? "none"}`}
          title="법규 위반 자동 보정"
          fields={autoCorrectFields}
          initialValues={cadAutoCorrectInitialValues(ctx)}
          buildBody={(values) => buildCadAutoCorrectBody(values)}
          endpoint="/cad-correction/auto-correct"
          submitLabel="자동 보정 실행"
          resultTitle="자동 보정 결과"
          renderResult={renderAutoCorrectResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={requiredPositiveFields}
        />
      </div>
    </AdvancedDrawer>
  );
}
