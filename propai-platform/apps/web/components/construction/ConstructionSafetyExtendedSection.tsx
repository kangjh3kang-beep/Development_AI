"use client";

/**
 * ConstructionSafetyExtendedSection — "시공 AI·현장 안전관리" 접힘 섹션(배선 캠페인 2차).
 *
 * 배경: 배선설계도 P2 트리아지 ② 프론트 배선 후보 중 construction(routers/construction.py,
 * 시공일정/ZEB에너지/기후리스크/하자분류 4엔진)과 safety(routers/safety.py, 현장 AI 안전관제)는
 * 이미 완성된 백엔드 서비스인데 화면이 없어 아무도 호출하지 못했다. 두 라우터를 "시공 관련
 * 확장 분석"이라는 같은 섹션 그룹으로 묶어 ProjectConstructionWorkspaceClient 하단에
 * additive로 붙는다(기존 공사비/체크리스트/리스크 흐름은 무수정).
 *
 * 구성 5건:
 *   ① 현장 안전관제 대시보드(GET /safety/dashboard) — 읽기 전용 자동조회(ParkingLogView와
 *      동일한 useQuery 패턴, 폼 없음). RTSP 스트림 분석(/analyze-stream)은 실제 카메라 연동이
 *      필요해 이번 배선 범위 밖(대시보드 조회만 노출 — 무목업 원칙상 폼으로 흉내내지 않는다).
 *   ②~⑤ 시공 일정·ZEB 에너지·기후 리스크·하자 분류 — 1차 ESG 패턴 그대로 재사용
 *      (ExtendedAnalysisPanel + lib/workspace-extended-panels.ts 순수 바디 조립).
 *
 * ★기후리스크는 1차 ESG가 이미 배선한 /climate/risk(routers/climate.py)와 다른 라우터다
 *   (여기는 /construction/climate-risk — 응답 모델이 달라 별도 패널로 둔다. 트리아지 기록만,
 *   중복 여부 정리는 이번 배선 범위 밖).
 *
 * 기본 접힘(AdvancedDrawer). SSOT 커밋 없음(무날조) — 5개 응답 전부 기존 costData/esgData
 * SSOT 슬롯과 물리량·단위가 일치하지 않는다(시공일정=CPM 일수, ZEB=에너지 kWh, 기후리스크=
 * 0~1 위험점수, 하자분류=AI 판정 텍스트, 안전관제=위반 카운트 — 전부 새로운 지표 종류).
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
  constructionScheduleInitialValues,
  buildConstructionScheduleBody,
  zebEnergyInitialValues,
  buildZebEnergyBody,
  constructionClimateInitialValues,
  buildConstructionClimateBody,
  defectClassificationInitialValues,
  buildDefectClassificationBody,
} from "@/lib/workspace-extended-panels";
import { formatPercent100, formatNumber, formatPercent01 } from "@/lib/esg-extended-panels";

/* ── ① 현장 안전관제 대시보드(읽기 전용) ── */

type SafetyDashboardResponse = {
  violations: Array<{
    id: string;
    camera_id: string;
    violation_type: string;
    confidence: number;
    detected_at: string;
    zone: string;
  }>;
  stats: {
    total_violations_today: number;
    helmet_off_count: number;
    vest_off_count: number;
    active_cameras: number;
  };
};

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "요청 실패.";
}

function SafetyDashboardPanel() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["safety", "dashboard"],
    queryFn: () => apiClient.get<SafetyDashboardResponse>("/safety/dashboard", { useMock: false }),
  });

  return (
    <Card>
      <CardContent className="p-6">
        <p className="text-xs uppercase tracking-[0.24em] text-[var(--text-tertiary)]">
          현장 안전관제 대시보드
        </p>

        {isLoading ? <SkeletonLoader count={1} itemClassName="h-32" className="mt-4" /> : null}

        {isError ? (
          <div className="mt-4">
            <WorkspaceQueryErrorCard
              title="안전관제 데이터를 불러오지 못했습니다."
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
            <div className="grid gap-4 sm:grid-cols-2 md:grid-cols-4">
              <Tile label="오늘 위반" value={`${data.stats.total_violations_today}건`} />
              <Tile label="안전모 미착용" value={`${data.stats.helmet_off_count}건`} />
              <Tile label="조끼 미착용" value={`${data.stats.vest_off_count}건`} />
              <Tile label="가동 카메라" value={`${data.stats.active_cameras}대`} />
            </div>
            {data.violations.length > 0 ? (
              <div className="grid gap-2">
                {data.violations.map((v) => (
                  <div
                    key={v.id}
                    className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[var(--surface-soft)] px-4 py-3 text-xs"
                  >
                    <span className="font-semibold text-[var(--text-primary)]">{v.violation_type}</span>
                    <span className="text-[var(--text-secondary)]">{v.zone}</span>
                    <span className="text-[var(--text-tertiary)]">신뢰도 {formatPercent01(v.confidence)}</span>
                    <span className="text-[var(--text-tertiary)]">
                      {new Date(v.detected_at).toLocaleString("ko-KR")}
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm leading-7 text-[var(--text-secondary)]">최근 위반 기록이 없습니다.</p>
            )}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

/* ── ②~⑤ 시공 AI 4엔진(공용 패널 재사용) ── */

type ScheduleResponse = {
  total_duration_days: number;
  critical_path: string[];
  milestones: Array<{ name?: string; day?: number; [key: string]: unknown }>;
};

function renderScheduleResult(raw: unknown): ReactNode {
  const r = raw as ScheduleResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <Tile label="총 공사기간" value={`${r.total_duration_days}일`} />
        <Tile label="주공정선 공정수" value={`${r.critical_path?.length ?? 0}개`} />
      </div>
      {(r.milestones?.length ?? 0) > 0 ? (
        <div className="grid gap-2">
          {r.milestones.map((m, i) => (
            <div key={i} className="rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-xs text-[var(--text-secondary)]">
              {JSON.stringify(m)}
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}

type ZebEnergyResponse = {
  annual_energy_demand_kwh: number;
  annual_renewable_generation_kwh: number;
  zeb_grade: string;
  energy_independence_rate: number;
  recommendations: string[];
};

function renderZebEnergyResult(raw: unknown): ReactNode {
  const r = raw as ZebEnergyResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-2">
        <Tile label="ZEB 등급" value={r.zeb_grade} />
        {/* ★1차 ESG "에너지효율등급·ZEB 인증 추정" 패널(energy.py /energy/certification)과 동일
            ConstructionAIService.estimate_zeb_energy를 호출 — energy_independence_rate는 그쪽과
            동일하게 이미 ×100(0~100) 스케일이다(construction_ai_service.py 내 동일 산식).
            formatPercent01을 쓰면 재곱(×100) 버그가 재발하므로 formatPercent100 사용. */}
        <Tile label="에너지 자립률" value={formatPercent100(r.energy_independence_rate)} />
        <Tile label="연간 에너지수요" value={formatNumber(r.annual_energy_demand_kwh, " kWh")} />
        <Tile label="연간 재생에너지 생산" value={formatNumber(r.annual_renewable_generation_kwh, " kWh")} />
      </div>
      {(r.recommendations?.length ?? 0) > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--text-secondary)]">
          {r.recommendations.map((rec, i) => (
            <li key={i}>{rec}</li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

type ConstructionClimateResponse = {
  flood_risk_score: number;
  heat_risk_score: number;
  overall_risk_level: string;
  mitigation_tips: string[];
};

function renderConstructionClimateResult(raw: unknown): ReactNode {
  const r = raw as ConstructionClimateResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        <Tile label="종합 위험등급" value={r.overall_risk_level} />
        {/* flood/heat_risk_score는 ge=0,le=1 위험점수(비율 아님) — 1차 ESG 기후리스크 패널과
            동일하게 formatNumber로 그대로 표시(퍼센트 변환 없음, 동일 관례). */}
        <Tile label="침수위험 점수" value={formatNumber(r.flood_risk_score)} />
        <Tile label="폭염위험 점수" value={formatNumber(r.heat_risk_score)} />
      </div>
      {(r.mitigation_tips?.length ?? 0) > 0 ? (
        <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--text-secondary)]">
          {r.mitigation_tips.map((tip, i) => (
            <li key={i}>{tip}</li>
          ))}
        </ul>
      ) : null}
    </>
  );
}

type DefectClassificationResponse = {
  defect_type: string;
  severity: string;
  confidence: number;
  description: string;
  repair_recommendation: string;
};

function renderDefectClassificationResult(raw: unknown): ReactNode {
  const r = raw as DefectClassificationResponse;
  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        <Tile label="하자 유형" value={r.defect_type} />
        <Tile label="심각도" value={r.severity} />
        <Tile label="판정 신뢰도" value={formatPercent01(r.confidence)} />
      </div>
      {r.description ? (
        <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
          {r.description}
        </div>
      ) : null}
      {r.repair_recommendation ? (
        <div className="rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
          {r.repair_recommendation}
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

/* ── 조립: 컴포넌트 ── */

export function ConstructionSafetyExtendedSection({ projectId }: { projectId: string }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const authErrorMessage = "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.";

  const ctx = useMemo(
    () => buildWorkspaceExtendedContext({ projectId, siteAnalysis, designData }),
    [projectId, siteAnalysis, designData],
  );

  const scheduleFields: ExtendedAnalysisFormField[] = [
    { key: "totalAreaSqm", label: "총 시공 면적 (㎡)", type: "number" },
    { key: "floorsAbove", label: "지상 층수", type: "number", allowDecimal: false },
    { key: "floorsBelow", label: "지하 층수", type: "number", allowDecimal: false },
    { key: "structureType", label: "구조형식 (RC/SRC/SC)", type: "text" },
  ];

  const zebFields: ExtendedAnalysisFormField[] = [
    { key: "totalAreaSqm", label: "총 면적 (㎡)", type: "number" },
    { key: "floors", label: "층수", type: "number", allowDecimal: false },
    { key: "windowWallRatio", label: "창면적비 (0.1~0.9)", type: "number" },
    { key: "insulationGrade", label: "단열등급", type: "text" },
  ];

  const climateFields: ExtendedAnalysisFormField[] = [
    { key: "lat", label: "위도", type: "number" },
    { key: "lon", label: "경도", type: "number" },
    { key: "constructionPeriodMonths", label: "공사 기간 (개월)", type: "number", allowDecimal: false },
  ];

  const defectFields: ExtendedAnalysisFormField[] = [
    { key: "imageUrl", label: "하자 사진 URL", type: "text" },
    { key: "location", label: "하자 위치 설명", type: "text" },
  ];

  return (
    <AdvancedDrawer label="시공 AI 확장 분석 (일정·ZEB에너지·기후리스크·하자분류·현장안전)">
      <div className="grid gap-6">
        <SafetyDashboardPanel />

        <ExtendedAnalysisPanel
          key={`construction-schedule-${ctx.totalGfaSqm ?? "none"}-${ctx.floorCount ?? "none"}`}
          title="시공 일정 생성 (표준품셈 13공정)"
          fields={scheduleFields}
          initialValues={constructionScheduleInitialValues(ctx)}
          buildBody={(values) => buildConstructionScheduleBody(values, ctx)}
          endpoint="/construction/schedule"
          submitLabel="시공 일정 생성"
          resultTitle="시공 일정 결과"
          renderResult={renderScheduleResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={["totalAreaSqm", "floorsAbove"]}
        />

        <ExtendedAnalysisPanel
          key={`zeb-energy-${ctx.totalGfaSqm ?? "none"}-${ctx.floorCount ?? "none"}`}
          title="ZEB 에너지 시뮬레이션"
          fields={zebFields}
          initialValues={zebEnergyInitialValues(ctx)}
          buildBody={(values) => buildZebEnergyBody(values, ctx)}
          endpoint="/construction/zeb-energy"
          submitLabel="ZEB 시뮬레이션 실행"
          resultTitle="ZEB 시뮬레이션 결과"
          renderResult={renderZebEnergyResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
          requiredPositiveFields={["totalAreaSqm"]}
        />

        <ExtendedAnalysisPanel
          key={`construction-climate-${ctx.lat ?? "none"}-${ctx.lon ?? "none"}`}
          title="시공 기후 리스크 분석"
          fields={climateFields}
          initialValues={constructionClimateInitialValues(ctx)}
          buildBody={(values) => buildConstructionClimateBody(values, ctx)}
          endpoint="/construction/climate-risk"
          submitLabel="기후 리스크 분석 실행"
          resultTitle="기후 리스크 분석 결과"
          renderResult={renderConstructionClimateResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
        />

        <ExtendedAnalysisPanel
          key="defect-classification"
          title="하자 사진 AI 분류"
          fields={defectFields}
          initialValues={defectClassificationInitialValues()}
          buildBody={(values) => buildDefectClassificationBody(values, ctx)}
          endpoint="/construction/defect-classify"
          submitLabel="하자 분류 실행"
          resultTitle="하자 분류 결과"
          renderResult={renderDefectClassificationResult}
          canUseLiveApi={canUseLiveApi}
          authErrorMessage={authErrorMessage}
          placeholderMessage="폼을 제출하면 결과가 표시됩니다."
        />
      </div>
    </AdvancedDrawer>
  );
}
