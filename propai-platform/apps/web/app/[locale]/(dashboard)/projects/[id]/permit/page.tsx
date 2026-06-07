"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { NextStageCta } from "@/components/projects/NextStageCta";
import { ProjectPermitWorkspaceClient } from "@/components/projects/ProjectPermitWorkspaceClient";
import { DesignChangePredictPanel } from "@/components/design-risk/DesignChangePredictPanel";
import { EnvironmentSummaryCard } from "@/components/environment/EnvironmentSummaryCard";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { LIFECYCLE_STAGES, STAGE_META } from "@/lib/lifecycle-stages";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";

/** /permits/ai-analysis 응답(개발방식별 인허가 가능성·근거법령·문제점·해결방안). */
type PermitMethod = {
  method: string;
  possibility: string;
  score: number;
  key_laws?: string[];
  issues?: string[];
  solutions?: string[];
};
type PermitAnalysis = {
  ai?: boolean;
  summary: string;
  methods: PermitMethod[];
  recommendation: string;
  site?: { zone_type?: string | null; max_far?: number | null };
};

/** /permits/feasibility-matrix 응답(용도지역 기반 개발방식 허용/불가·복잡도). */
type FeasibilityItem = {
  development_type: string;
  type_name: string;
  is_permitted: boolean;
  permit_complexity: number;
  complexity_label: string;
  reason: string;
};
type FeasibilityMatrix = {
  zone_type: string;
  permitted_count: number;
  total_count: number;
  items: FeasibilityItem[];
  summary: string;
};

export default function PermitPage() {
  const params = useParams();
  const locale = params.locale as string;
  const id = params.id as string;

  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const completedStages = useProjectContextStore((s) => s.completedStages);
  const currentStage = useProjectContextStore((s) => s.currentStage);
  const { dictionary } = useDictionary((isValidLocale(locale) ? locale : "ko") as Locale);

  // ── 인허가 AI 분석(/permits/ai-analysis) — 진입 시 부지 컨텍스트로 1회 자동호출 ──
  const [analysis, setAnalysis] = useState<PermitAnalysis | null>(null);
  const [analysisState, setAnalysisState] = useState<"idle" | "loading" | "done" | "gated" | "error" | "no-site">("idle");
  // ── 용도지역 기반 인허가 가능성 매트릭스(/permits/feasibility-matrix) ──
  const [matrix, setMatrix] = useState<FeasibilityMatrix | null>(null);
  const ranRef = useRef<string | null>(null); // 무한루프 가드(주소+pnu 1회)

  // 용도지역(zone_type) 전파 — 부지분석 확정 zoneCode 우선, 없으면 AI 진단 site.zone_type 폴백.
  const siteAddress = siteAnalysis?.address ?? null;
  const sitePnu = siteAnalysis?.pnu ?? null;
  const siteZoneCode = siteAnalysis?.zoneCode ?? null;
  const zoneType = siteZoneCode || analysis?.site?.zone_type || null;

  useEffect(() => {
    const address = siteAddress;
    const key = `${id}:${address ?? ""}:${sitePnu ?? ""}`;
    if (!address) {
      setAnalysisState("no-site");
      return;
    }
    if (ranRef.current === key) return; // 동일 컨텍스트 재호출 방지(주소+pnu 1회)
    ranRef.current = key;
    // 무한로딩 근본 제거: 요청 토큰으로 "이 effect가 시작한 호출의 응답"만 state에 반영.
    // (store siteAnalysis 객체 참조 변동으로 effect가 재실행/cleanup 돼도 진행중 요청의 결과는 유실되지 않음)
    let active = true;
    (async () => {
      setAnalysisState("loading");
      try {
        // site는 effect 시작 시점의 스냅샷을 직접 캡처(스토어 참조 변동 영향 차단)
        const siteSnapshot = siteAnalysis && siteAnalysis.address === address ? siteAnalysis : undefined;
        const res = await apiClient.post<PermitAnalysis>("/permits/ai-analysis", {
          body: {
            address,
            pnu: sitePnu || undefined,
            site: siteSnapshot,
          },
          useMock: false,
          timeoutMs: 150000,
        });
        if (!active) return;
        setAnalysis(res);
        setAnalysisState("done");
      } catch (err) {
        if (!active) return;
        // 402 = LLM 쿼터/과금 게이트 → graceful 안내(목업 금지)
        if (err instanceof ApiClientError && err.status === 402) {
          setAnalysisState("gated");
        } else {
          setAnalysisState("error");
        }
      }
    })();
    return () => {
      // ranRef가 동일 key 재실행을 막으므로, 이 cleanup이 도는 경우는 사실상
      // 마운트 해제뿐. 진행중 요청은 active=false로 마킹돼 stale state set만 차단.
      active = false;
    };
    // 원시값(주소·pnu)만 의존 — siteAnalysis 객체 참조 변동에 의한 불필요한 재실행/로딩 stranding 방지.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, siteAddress, sitePnu]);

  // 용도지역이 확보되면 개발방식 인허가 가능성 매트릭스 조회(LLM 미사용·실패 무관)
  useEffect(() => {
    if (!zoneType) {
      setMatrix(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const res = await apiClient.post<FeasibilityMatrix>("/permits/feasibility-matrix", {
          body: { zone_type: zoneType },
          useMock: false,
        });
        if (!cancelled) setMatrix(res);
      } catch {
        if (!cancelled) setMatrix(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [zoneType]);

  const safeLocale = (isValidLocale(locale) ? locale : "ko") as Locale;

  // 진행바: 라이프사이클 SSOT(10단계) × store 실제 상태(완료/현재) — 프로젝트별로 달라짐.
  const permitStages = useMemo(() => {
    const done = new Set(completedStages);
    return LIFECYCLE_STAGES.map((stage) => ({
      label: STAGE_META[stage].label,
      status: done.has(stage)
        ? ("completed" as const)
        : currentStage === stage
          ? ("current" as const)
          : ("pending" as const),
    }));
  }, [completedStages, currentStage]);
  const progressPct = permitStages.length
    ? Math.round((permitStages.filter((s) => s.status === "completed").length / permitStages.length) * 100)
    : 0;

  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary?.workspace.modeLive ?? "LIVE"
      : dictionary?.workspace.modeMock ?? "MOCK";
  const t = dictionary?.modulePlaceholders["permit"];

  return (
    <div className="grid gap-8 p-6 lg:p-12">
      {/* ① 컨텍스트 헤더 — 3구역 표준(ModulePlaceholder) */}
      {t && (
        <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }}>
          <ModulePlaceholder
            eyebrow={t.eyebrow}
            title={t.title}
            description={t.description}
            statusLabel={runtimeMode}
            localeLabel={locale}
            items={t.items}
          />
        </motion.div>
      )}

      <div className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-10 shadow-xl">
        <div className="mb-10 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 className="text-xl font-bold text-[var(--text-primary)]">개발 라이프사이클 진행 현황</h3>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              프로젝트 단계 완료 상태(부지분석→보고서) 기준 · 인허가는 후반 단계입니다.
            </p>
          </div>
          <span className="text-sm font-black text-[var(--accent-strong)]">진행률 {progressPct}%</span>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-6">
          {permitStages.map((stage, i, arr) => (
            <div key={stage.label} className="flex flex-1 items-center gap-4 min-w-[120px]">
              <div className="flex flex-col items-center gap-3 flex-1 text-center">
                <div className={`flex h-12 w-12 items-center justify-center rounded-full border-2 text-sm font-black transition-all ${
                  stage.status === "completed"
                    ? "bg-[var(--accent-strong)] border-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)]"
                    : stage.status === "current"
                    ? "border-[var(--accent-strong)] text-[var(--accent-strong)] bg-[var(--accent-soft)] animate-pulse shadow-md"
                    : "border-[var(--line-strong)] text-[var(--text-hint)]"
                }`}>
                  {stage.status === "completed" ? "\u2713" : i + 1}
                </div>
                <span className={`text-sm font-bold ${stage.status === "current" ? "text-[var(--accent-strong)]" : "text-[var(--text-tertiary)]"}`}>
                  {stage.label}
                </span>
              </div>
              {i < arr.length - 1 && (
                <div className={`mb-8 h-0.5 flex-1 ${stage.status === "completed" ? "bg-[var(--accent-strong)]" : "bg-[var(--line)]"}`} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── 용도지역 기반 개발방식 인허가 가능성 매트릭스(permit_validator 실엔진) ── */}
      <div className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-8 shadow-lg">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-2">
          <div>
            <h3 className="text-xl font-bold text-[var(--text-primary)]">개발방식별 인허가 가능성</h3>
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              {zoneType
                ? `용도지역 「${zoneType}」 기준 허용·복잡도 (국토계획법 제76조 행위제한)`
                : "부지분석에서 용도지역이 확정되면 개발방식별 가능/불가가 산출됩니다."}
            </p>
          </div>
          {matrix && (
            <span className="text-sm font-black text-[var(--accent-strong)]">
              {matrix.permitted_count}/{matrix.total_count}개 가능
            </span>
          )}
        </div>
        {matrix && matrix.items?.length > 0 ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {(matrix.items ?? []).map((it) => (
              <div
                key={it.development_type}
                className={`rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 ${
                  it.is_permitted ? "" : "opacity-60"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-bold text-[var(--text-primary)]">{it.type_name}</span>
                  <span className={`rounded-full border px-2 py-0.5 text-[10px] font-bold ${
                    it.is_permitted
                      ? "border-emerald-500/30 bg-emerald-500/15 text-emerald-600"
                      : "border-rose-500/30 bg-rose-500/15 text-rose-600"
                  }`}>
                    {it.is_permitted ? "허가 가능" : "불가"}
                  </span>
                </div>
                {it.is_permitted && (
                  <p className="mt-2 text-[11px] font-semibold text-[var(--text-tertiary)]">
                    인허가 난이도 · {it.complexity_label}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-2xl bg-[var(--surface-soft)] px-6 py-8 text-center text-sm text-[var(--text-tertiary)]">
            {zoneType ? "인허가 가능성 데이터를 불러오지 못했습니다." : "용도지역 정보가 없습니다 — 부지분석을 먼저 진행하세요."}
          </p>
        )}
      </div>

      {/* ── AI 규제·인허가 진단(/permits/ai-analysis) — 진입 시 부지 컨텍스트로 자동 분석 ── */}
      <div className="flex flex-col gap-6 rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-8">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-xl font-bold text-[var(--text-primary)]">AI 인허가 진단</h3>
          {analysisState === "done" && (
            <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${
              analysis?.ai
                ? "border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]"
                : "border-[var(--line-strong)] text-[var(--text-tertiary)]"
            }`}>
              {analysis?.ai ? "AI 분석" : "규칙기반"}
            </span>
          )}
        </div>

        {analysisState === "loading" && (
          <p className="animate-pulse text-sm font-semibold text-[var(--text-tertiary)]">
            상위법령·조례·용도지역을 종합 분석 중입니다… (최대 1분)
          </p>
        )}
        {analysisState === "no-site" && (
          <p className="text-sm text-[var(--text-tertiary)]">
            부지 주소가 없습니다. 부지분석 단계를 먼저 진행하면 자동으로 인허가 진단이 실행됩니다.
          </p>
        )}
        {analysisState === "gated" && (
          <p className="text-sm text-[var(--text-secondary)]">
            AI 인허가 진단은 LLM 사용량(코인)이 필요합니다. 잔여 사용량 충전 후 다시 진입하면 자동 실행됩니다.
            <br />
            (용도지역 기반 개발방식 가능성은 위 매트릭스에서 확인할 수 있습니다.)
          </p>
        )}
        {analysisState === "error" && (
          <p className="text-sm text-rose-500">인허가 AI 진단에 실패했습니다. 잠시 후 다시 시도하세요.</p>
        )}

        {analysisState === "done" && analysis && (
          <div className="space-y-5">
            <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{analysis.summary}</p>

            {(() => {
              const top = [...(analysis.methods || [])].sort((a, b) => (b.score || 0) - (a.score || 0))[0];
              if (!top) return null;
              return (
                <div className="space-y-4 rounded-2xl border border-[var(--line)] bg-[var(--surface-strong)] p-5 shadow-sm">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-black text-[var(--text-primary)]">추천 개발방식 · {top.method}</p>
                    <span className="rounded-full border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/10 px-2.5 py-0.5 text-xs font-bold text-[var(--accent-strong)]">
                      가능성 {top.possibility} · {top.score}점
                    </span>
                  </div>
                  {(top.issues?.length ?? 0) > 0 && (
                    <div>
                      <p className="text-xs font-bold text-amber-600">인허가 문제점</p>
                      <ul className="mt-1 space-y-0.5 text-sm text-[var(--text-secondary)]">
                        {top.issues!.map((it, i) => (
                          <li key={i}>· {it}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(top.solutions?.length ?? 0) > 0 && (
                    <div>
                      <p className="text-xs font-bold text-emerald-600">해결방안</p>
                      <ul className="mt-1 space-y-0.5 text-sm text-[var(--text-secondary)]">
                        {top.solutions!.map((s, i) => (
                          <li key={i}>· {s}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })()}

            {analysis.recommendation && (
              <div className="rounded-2xl border-l-4 border-[var(--accent-strong)] bg-[var(--surface-strong)] p-5 shadow-sm">
                <p className="mb-1 text-xs font-bold uppercase tracking-widest text-[var(--accent-strong)]">종합 권고</p>
                <p className="text-sm font-medium leading-relaxed text-[var(--text-primary)]">{analysis.recommendation}</p>
              </div>
            )}
            <p className="text-[11px] text-[var(--text-tertiary)]">
              개발방식별 상세 분석(근거법령·다필지 통합 용적률·전문가 패널)은 아래 인허가 작업 영역에서 확인할 수 있습니다.
            </p>
          </div>
        )}
      </div>

      {/* ── 일조 환경 보조카드(정북 일조사선·동지 일조시간 = 법정 요건) ── */}
      {(siteAnalysis?.address || siteAnalysis?.pnu) && (
        <EnvironmentSummaryCard
          address={siteAnalysis?.address}
          pnu={siteAnalysis?.pnu}
          focus="solar"
        />
      )}

      {/* ── 설계변경 사전예측 (D3) ── */}
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-black tracking-tight text-[var(--text-primary)]">설계변경 리스크 사전예측</h2>
        <p className="text-[var(--text-secondary)]">착공 전 법규초과·필수요소 누락·정합 모순을 미리 잡아내고 저비용 보완방안을 제시합니다.</p>
      </div>
      <DesignChangePredictPanel projectId={id} />

      {/* ── Live Workspace Client ── */}
      <ProjectPermitWorkspaceClient locale={safeLocale} projectId={id} />

      {/* ③ 다음 단계 CTA */}
      <NextStageCta locale={locale} currentStage="permit" />
    </div>
  );
}
