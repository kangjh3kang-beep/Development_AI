"use client";

/**
 * PermitCasesSection — "인허가 사례(건축HUB)" 접힘 검색 섹션(배선 캠페인 2차).
 *
 * 배경: 배선설계도 P2 트리아지(_workspace/TRIAGE_wiring_p2_2026-07-11.md) ② 프론트 배선
 * 후보 중 permit-cases(routers/permit_cases.py, GET /api/v1/permit-cases)는 건축HUB
 * 기반 동일 법정동 인허가 사례를 이미 조회·정규화·분위수 요약까지 완성했는데 화면이
 * 없어 아무도 호출하지 못했다.
 *
 * ★GET+쿼리 엔드포인트라 1차 ESG 클러스터의 ExtendedAnalysisPanel(POST 폼→단일 결과)과
 * 형태가 다르다(검색 폼→목록+분위수 요약). 그래서 공용 패널을 억지로 GET에 맞추지 않고
 * 전용 소형 컴포넌트로 둔다(바디/쿼리 조립 순수함수만 lib/workspace-extended-panels.ts
 * 공용 — buildPermitCaseQuery/permitCaseInitialValues).
 *
 * 기본 접힘(AdvancedDrawer) — 화면을 어지럽히지 않고, 필요할 때만 펼쳐 쓴다.
 * SSOT 커밋 없음(무날조): 인허가 사례는 참고용 시장 사례 조회일 뿐, 프로젝트 자체의
 * 확정값이 아니므로 useProjectContextStore에 되먹임하지 않는다.
 */

import { useCallback, useState, type FormEvent } from "react";
import { Button, Card, CardContent, Input } from "@propai/ui";
import { AdvancedDrawer } from "@/components/common/AdvancedDrawer";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  buildWorkspaceExtendedContext,
  permitCaseInitialValues,
  buildPermitCaseQuery,
  type PermitCaseKind,
} from "@/lib/workspace-extended-panels";
import { extractApiErrorMessage } from "@/lib/esg-extended-panels";

type PermitCaseRecord = {
  land_area_sqm: number | null;
  building_area_sqm: number | null;
  total_floor_area_sqm: number | null;
  bcr_pct: number | null;
  far_pct: number | null;
  floors_above: number | null;
  floors_below: number | null;
  main_use: string | null;
  permit_date: string | null;
  construction_start_date: string | null;
  approval_date: string | null;
};

type PermitCaseSummary = {
  count: number;
  bcr_p25: number | null;
  bcr_p50: number | null;
  bcr_p75: number | null;
  far_p25: number | null;
  far_p50: number | null;
  far_p75: number | null;
  main_use_top3: string[];
  recent_24m_count: number;
  permit_to_start_days_p50: number | null;
  permit_to_approval_days_p50: number | null;
};

type PermitCaseResponse = {
  cases: PermitCaseRecord[];
  summary: PermitCaseSummary;
  total: number;
  source: string;
  note: string | null;
};

function fmtPct(v: number | null): string {
  return v == null ? "-" : `${v.toFixed(1)}%`;
}

function fmtDays(v: number | null): string {
  return v == null ? "-" : `${v}일`;
}

export function PermitCasesSection({ projectId }: { projectId: string }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const ctx = buildWorkspaceExtendedContext({ projectId, siteAnalysis });

  const [values, setValues] = useState(() => permitCaseInitialValues(ctx));
  const [result, setResult] = useState<PermitCaseResponse | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState("");

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;
  const authErrorMessage = "라이브 작업 공간 호출을 위해 API 인증이 필요합니다.";

  const submit = useCallback(async () => {
    setError("");
    if (!values.pnu.trim()) {
      setError("PNU(필지고유번호)를 입력하세요.");
      return;
    }
    setIsSubmitting(true);
    try {
      const query = buildPermitCaseQuery(values);
      const response = await apiClient.get<PermitCaseResponse>(
        `/permit-cases?${new URLSearchParams(query).toString()}`,
        { useMock: false },
      );
      setResult(response);
    } catch (err) {
      setError(extractApiErrorMessage(err, authErrorMessage));
    } finally {
      setIsSubmitting(false);
    }
  }, [values]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submit();
  }

  function setKind(kind: PermitCaseKind) {
    setValues((prev) => ({ ...prev, kind }));
  }

  return (
    <AdvancedDrawer label="인허가 사례 조회 (건축HUB · 법정동 기준)">
      <Card>
        <CardContent className="p-6">
          <p className="label-caps text-[var(--text-tertiary)]">
            인허가 사례 검색
          </p>
          <form className="mt-4 grid gap-3" onSubmit={handleSubmit}>
            <div className="grid gap-3 md:grid-cols-[2fr_1fr]">
              <Input
                value={values.pnu}
                onChange={(e) => setValues((prev) => ({ ...prev, pnu: e.target.value }))}
                placeholder="PNU(필지고유번호, 최소 앞 10자리)"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => setKind("arch")}
                  className={`flex-1 rounded-lg border px-3 py-2 text-xs font-bold uppercase tracking-widest ${
                    values.kind === "arch"
                      ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]"
                      : "border-[var(--line)] text-[var(--text-tertiary)]"
                  }`}
                >
                  건축(arch)
                </button>
                <button
                  type="button"
                  onClick={() => setKind("hs")}
                  className={`flex-1 rounded-lg border px-3 py-2 text-xs font-bold uppercase tracking-widest ${
                    values.kind === "hs"
                      ? "border-[var(--accent-strong)] bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]"
                      : "border-[var(--line)] text-[var(--text-tertiary)]"
                  }`}
                >
                  주택(hs)
                </button>
              </div>
            </div>
            <Button type="submit" disabled={!canUseLiveApi || isSubmitting}>
              {isSubmitting ? "조회 중..." : "인허가 사례 조회"}
            </Button>
          </form>

          {isSubmitting ? <SkeletonLoader count={1} itemClassName="h-32" className="mt-4" /> : null}

          {error ? (
            <div className="mt-4">
              <WorkspaceQueryErrorCard
                title="인허가 사례 조회 오류"
                description="PNU 값을 확인한 뒤 다시 시도하세요."
                message={error}
                actionLabel="다시 시도"
                onRetry={submit}
              />
            </div>
          ) : null}

          {result ? (
            <div className="mt-6 space-y-4">
              {result.note ? (
                <p className="text-xs leading-6 text-[var(--text-tertiary)]">{result.note}</p>
              ) : null}
              <div className="grid gap-4 md:grid-cols-3">
                <Tile label="전체 사례 수" value={`${result.total}건`} />
                <Tile label="최근 24개월" value={`${result.summary.recent_24m_count}건`} />
                <Tile
                  label="주용도 상위3"
                  value={result.summary.main_use_top3.length > 0 ? result.summary.main_use_top3.join(", ") : "-"}
                />
                <Tile
                  label="건폐율 중앙값(25~75분위)"
                  value={`${fmtPct(result.summary.bcr_p50)} (${fmtPct(result.summary.bcr_p25)}~${fmtPct(result.summary.bcr_p75)})`}
                />
                <Tile
                  label="용적률 중앙값(25~75분위)"
                  value={`${fmtPct(result.summary.far_p50)} (${fmtPct(result.summary.far_p25)}~${fmtPct(result.summary.far_p75)})`}
                />
                <Tile
                  label="허가→착공/사용승인 중앙값"
                  value={`${fmtDays(result.summary.permit_to_start_days_p50)} / ${fmtDays(result.summary.permit_to_approval_days_p50)}`}
                />
              </div>

              {result.cases.length > 0 ? (
                <div className="grid gap-2">
                  {result.cases.map((c, i) => (
                    <div
                      key={i}
                      className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[var(--surface-soft)] px-4 py-3 text-xs"
                    >
                      <span className="font-semibold text-[var(--text-primary)]">
                        {c.main_use ?? "-"}
                      </span>
                      <span className="text-[var(--text-secondary)]">
                        건폐율 {fmtPct(c.bcr_pct)} · 용적률 {fmtPct(c.far_pct)}
                      </span>
                      <span className="text-[var(--text-tertiary)]">
                        지상 {c.floors_above ?? "-"}F / 지하 {c.floors_below ?? "-"}F
                      </span>
                      <span className="text-[var(--text-tertiary)]">
                        허가 {c.permit_date ?? "-"}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm leading-7 text-[var(--text-secondary)]">
                  조회된 사례가 없습니다.
                </p>
              )}
            </div>
          ) : !error && !isSubmitting ? (
            <div className="mt-6 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[var(--text-secondary)]">
              PNU를 입력하고 조회하면 동일 법정동 인허가 사례와 분위수 요약이 표시됩니다.
            </div>
          ) : null}
        </CardContent>
      </Card>
    </AdvancedDrawer>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-xl)] bg-[var(--surface)] p-4">
      <p className="label-caps text-[var(--text-tertiary)]">{label}</p>
      <p className="mt-2 text-sm font-semibold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
