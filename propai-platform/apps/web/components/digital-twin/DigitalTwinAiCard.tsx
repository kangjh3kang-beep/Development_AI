"use client";

/**
 * 가상준공 AI 해설 카드 — 디지털트윈 씬 로드 후 온디맨드로 LLM 해설을 생성.
 *
 * POST /api/v1/digital-twin/interpret → 5섹션(설계의도·주변맥락·조망일조·개발시사·분양하이라이트).
 *
 * ⚠ 정직성 가드(비협상): 실제 씬/컨텍스트 수치만 근거. "AI 해석·참고용" 라벨 +
 *   grounding(사용 데이터) 표기 + 검증 배지(AnalysisVerdict) 결합. 가짜 콘텐츠 생성 금지.
 *
 * context는 가용 시에만 useProjectContextStore에서 추출(없으면 생략 — 과설계 금지).
 */

import { useCallback, useMemo, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { AnalysisVerdict } from "@/components/analysis/AnalysisVerdict";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type {
  DigitalTwinInterpretResponse,
  DigitalTwinScenePayload,
} from "./types";

/** 섹션 키→라벨(표시 순서). */
const SECTION_LABELS: Array<[string, string]> = [
  ["design_rationale", "설계 의도·적합성"],
  ["context_fit", "주변 맥락·스카이라인"],
  ["view_sunlight", "조망·일조"],
  ["development_implication", "개발 시사점"],
  ["marketing_highlight", "분양 하이라이트"],
];

export function DigitalTwinAiCard({
  address,
  pnu,
  scenePayload,
}: {
  address?: string;
  pnu?: string | null;
  /** 이미 받은 씬 페이로드(백엔드 재구성 비용 절감용으로 그대로 전달). */
  scenePayload?: DigitalTwinScenePayload | null;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [res, setRes] = useState<DigitalTwinInterpretResponse | null>(null);

  // 컨텍스트는 가용 시에만 전달(없으면 생략).
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);
  const esgData = useProjectContextStore((s) => s.esgData);

  const context = useMemo(() => {
    const ctx: Record<string, unknown> = {};
    if (feasibilityData?.profitRatePct != null) ctx.roi = feasibilityData.profitRatePct;
    if (esgData?.totalCarbonPerSqm != null) ctx.esg = esgData.totalCarbonPerSqm;
    if (siteAnalysis?.zoneCode) ctx.zone_type = siteAnalysis.zoneCode;
    if (designData) {
      const summary: Record<string, unknown> = {};
      if (designData.buildingType) summary.building_type = designData.buildingType;
      if (designData.totalGfaSqm != null) summary.total_gfa_sqm = designData.totalGfaSqm;
      if (designData.floorCount != null) summary.floor_count = designData.floorCount;
      if (designData.bcr != null) summary.bcr = designData.bcr;
      if (designData.far != null) summary.far = designData.far;
      if (Object.keys(summary).length > 0) ctx.design_summary = summary;
    }
    return Object.keys(ctx).length > 0 ? ctx : undefined;
  }, [feasibilityData, esgData, siteAnalysis, designData]);

  const run = useCallback(async () => {
    const a = (address || "").trim();
    if (!a && !pnu) {
      setErr("대상지 주소 또는 PNU가 필요합니다.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await apiClient.post<DigitalTwinInterpretResponse>("/digital-twin/interpret", {
        body: {
          address: a || null,
          pnu: pnu ?? null,
          scene: scenePayload ?? null,
          context: context ?? null,
        },
        useMock: false,
        timeoutMs: 60000,
      });
      if (r?.ok) {
        setRes(r);
      } else {
        setRes(null);
        setErr(r?.message || "AI 해설 생성 실패 — 근거 데이터가 부족할 수 있습니다.");
      }
    } catch {
      setRes(null);
      setErr("AI 해설 요청 실패 — 네트워크 확인 후 다시 시도하세요.");
    } finally {
      setBusy(false);
    }
  }, [address, pnu, scenePayload, context]);

  const usedFields = res?.grounding?.used_fields ?? [];

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
      {/* 헤더 */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm font-black tracking-tight text-[var(--text-primary)]">
            ✦ 가상준공 AI 해설
          </span>
          <span className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-[10px] font-bold text-amber-600 dark:text-amber-400">
            AI 해석·참고용
          </span>
          {res?.cached && (
            <span className="rounded-full border border-[var(--line)] bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-secondary)]">
              캐시
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={run}
          disabled={busy}
          className="h-8 shrink-0 rounded-lg border border-[var(--accent-strong)] bg-[var(--accent-soft)] px-4 text-[11px] font-black uppercase tracking-widest text-[var(--accent-strong)] transition-all hover:brightness-110 disabled:opacity-50"
        >
          {busy ? "해설 생성 중…" : res ? "다시 생성" : "AI 해설 생성"}
        </button>
      </div>

      <p className="text-[11px] leading-relaxed text-[var(--text-secondary)]">
        씬(지형·필지·주변·매스)과 분석 컨텍스트(가용 시 ROI·ESG·용도지역·설계개요)에 근거한 설계
        의도·주변 맥락·조망/일조·개발 시사점·분양 하이라이트를 생성합니다. 실측·인허가 결론이 아닙니다.
      </p>

      {busy && (
        <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-4 text-[11px] text-[var(--text-hint)]">
          AI가 씬과 컨텍스트를 해석하는 중입니다(최대 30초 이상 소요될 수 있습니다)…
        </div>
      )}

      {err && !busy && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 text-[11px] font-medium text-red-500">
          {err}
        </div>
      )}

      {res?.ok && res.sections && (
        <>
          {usedFields.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)]">
                사용 데이터
              </span>
              {usedFields.map((f) => (
                <span
                  key={f}
                  className="rounded-full border border-[var(--line)] bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]"
                >
                  {f}
                </span>
              ))}
            </div>
          )}

          {/* 검증 배지 + 5섹션 해석(표준 컴포넌트 재사용) */}
          <AnalysisVerdict
            analysisType="digital_twin_interpret"
            context={res.sections as unknown as Record<string, unknown>}
            interpretation={res.sections as unknown as Record<string, unknown>}
            sectionLabels={SECTION_LABELS}
            interpretationTitle="가상준공 AI 해설"
            autoRunVerification
            // 응답 최상위 ledger_hash(원장 sha256) — 피드백 조인키(미노출이면 undefined·안전).
            ledgerHash={(res as unknown as { ledger_hash?: string })?.ledger_hash}
          />

          {res.note && <p className="text-[10px] text-[var(--text-hint)]">{res.note}</p>}
        </>
      )}
    </div>
  );
}
