"use client";

/**
 * Phase 4 · 설계 결과 → 사업성·환경·해설·은행제출 연결 요약 패널.
 *
 * 설계가 적용/변경되면(designData 갱신) 아래 4가지를 스튜디오에서 바로 보여준다.
 *   ① 설계↔수지 실시간 요약: 설계(GFA·층수)로 공사비(estimate-overview)를 1회 산정하고,
 *      검증된 수지/ROI(feasibilityData SSOT)를 함께 카드로 표시(총사업비/예상ROI/NPV).
 *   ② 환경분석 인라인: ESG(탄소·GRESB) 등급을 배지로 요약. 데이터 없으면 정직 빈상태.
 *   ③ 설계해설(쉬운 한국어): DesignInterpreter 6섹션을 카드로 표면화("왜 이런 설계인지").
 *   ④ 은행제출 패키지 원클릭: 기존 BankReadyReportBuilder를 모달로 열어 PF심사용 보고서 생성.
 *
 * 절대 제약(준수):
 *   - 기존 분석/보고서 로직·산식은 재구현하지 않는다. 공사비는 기존 /cost/estimate-overview를
 *     "그대로" 호출하고, 수지/ROI·ESG는 컨텍스트 SSOT(다른 화면이 채운 검증값)를 읽기만 한다.
 *   - 무목업: 데이터가 없으면 가짜 수치 없이 정직 빈상태 + 해당 분석 화면으로 유도.
 *   - 무거운 자동재계산 금지: 공사비는 "설계 시그니처가 바뀌었고 아직 산정되지 않았을 때만"
 *     1회 호출(디바운스). 무한루프 가드(마지막 산정 시그니처 기억).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient } from "@/lib/api-client";
import { BankReadyReportBuilder } from "@/components/report/BankReadyReportBuilder";

/* ── 공사비 estimate-overview 응답(필요 필드만) ── */
interface CostOverview {
  total_won: number;
  unit_cost_per_sqm: number;
  per_pyeong_won: number;
  aboveground_won: number;
  underground_won: number;
  landscape_won: number;
  direct_won: number;
  indirect_won: number;
  range: { min_won: number; expected_won: number; max_won: number };
}

/* ── 설계해설(DesignInterpreter 6섹션) ── */
type DesignAi = Record<string, string> | null;

/** 설계 buildingType(한글/임의) → estimate-overview building_type 코드 매핑(CostEstimationClient와 동일 규칙). */
function mapBuildingType(bt?: string | null): string {
  const s = (bt || "").toString();
  if (/오피스텔/.test(s)) return "officetel";
  if (/지식산업|창고|물류/.test(s)) return "warehouse";
  if (/업무|오피스(?!텔)/.test(s)) return "office";
  if (/연립|다세대|빌라/.test(s)) return "townhouse";
  if (/단독/.test(s)) return "single_house";
  return "apartment";
}

/** 원(KRW) → 억/만 단위 한글 요약. */
function fmtKrw(won?: number | null): string {
  if (won == null || isNaN(won)) return "-";
  const abs = Math.abs(won);
  const sign = won < 0 ? "-" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(1)}억`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString()}만`;
  return `${sign}${Math.round(abs).toLocaleString()}원`;
}

/** ESG 탄소집약도(㎡당 kgCO2) → 쉬운 등급 라벨(낮을수록 우수). 임계는 표시용 가이드. */
function carbonGrade(perSqm?: number | null): { label: string; tone: string } | null {
  if (perSqm == null || perSqm <= 0) return null;
  if (perSqm <= 500) return { label: "우수", tone: "text-emerald-400 border-emerald-400/30 bg-emerald-400/10" };
  if (perSqm <= 800) return { label: "양호", tone: "text-amber-400 border-amber-400/30 bg-amber-400/10" };
  return { label: "개선필요", tone: "text-rose-400 border-rose-400/30 bg-rose-400/10" };
}

interface Props {
  projectId: string;
  /** 스튜디오가 이미 받아온 설계해설(있으면 재호출 없이 표면화만). */
  designAi: DesignAi;
}

export function DesignOutcomeSummary({ projectId, designAi }: Props) {
  // ── SSOT(모세혈관 스토어) ── 설계·공사비·수지·환경은 단일 진실원을 읽는다.
  const designData = useProjectContextStore((s) => s.designData);
  const costData = useProjectContextStore((s) => s.costData);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);
  const esgData = useProjectContextStore((s) => s.esgData);
  const updateCostData = useProjectContextStore((s) => s.updateCostData);

  // ── 설계↔공사비 1회 산정(디바운스·무한루프 가드) ──
  const [costLoading, setCostLoading] = useState(false);
  const [costError, setCostError] = useState<string | null>(null);
  // 마지막으로 공사비를 산정한 설계 시그니처. 같으면 재호출하지 않는다(무한루프·과호출 방지).
  const costSigRef = useRef<string | null>(null);

  // ── 은행제출 패키지 모달 ──
  const [showBankReport, setShowBankReport] = useState(false);

  // 설계가 적용/변경되면 공사비를 1회 산정해 SSOT(costData)에 기록 → 수지/ROI까지 연쇄 갱신.
  // ★기존 공사비 화면과 동일한 /cost/estimate-overview를 그대로 호출(산식 재구현 없음).
  const estimateCost = useCallback(
    async (gfa: number, floors: number, bt: string | null, sig: string) => {
      setCostLoading(true);
      setCostError(null);
      try {
        const r = await apiClient.post<CostOverview>("/cost/estimate-overview", {
          body: {
            building_type: mapBuildingType(bt),
            total_gfa_sqm: Math.round(gfa),
            floor_count_above: floors,
            floor_count_below: 1,
            structure_type: "RC",
            project_id: projectId || undefined,
          },
          useMock: false,
          timeoutMs: 30000,
        });
        // 수지·ROI 연동: 공사비를 컨텍스트에 저장(다른 화면과 동일 스키마).
        updateCostData({
          totalConstructionCostWon: r.total_won,
          perSqmWon: r.unit_cost_per_sqm,
          perPyeongWon: r.per_pyeong_won,
          abovegroundWon: r.aboveground_won,
          undergroundWon: r.underground_won,
          landscapeWon: r.landscape_won,
          directWon: r.direct_won,
          indirectWon: r.indirect_won,
          rangeMinWon: r.range?.min_won ?? null,
          rangeMaxWon: r.range?.max_won ?? null,
          source: "overview",
        });
        costSigRef.current = sig; // 산정 완료 시그니처 기록(같은 설계는 재호출 안 함)
      } catch {
        setCostError("공사비 자동 산정에 실패했습니다. 공사비 분석 화면에서 직접 산정할 수 있습니다.");
      } finally {
        setCostLoading(false);
      }
    },
    [projectId, updateCostData],
  );

  useEffect(() => {
    const gfa = designData?.totalGfaSqm ?? 0;
    const floors = designData?.floorCount ?? 0;
    if (!(gfa > 0 && floors > 0)) return; // 설계 기반(GFA·층수) 없으면 산정 불가(빈상태)
    // 설계 시그니처: GFA·층수·용도가 바뀌면 새 산정. 동일하면(이미 산정) skip.
    const sig = `${Math.round(gfa)}|${floors}|${designData?.buildingType ?? ""}`;
    if (costSigRef.current === sig) return; // 무한루프·과호출 가드
    // 이미 같은 설계로 공사비(SSOT)가 있으면 재호출하지 않고 시그니처만 동기화.
    if (costData?.totalConstructionCostWon && costData.source === "overview" && costSigRef.current == null) {
      costSigRef.current = sig;
      return;
    }
    if (costLoading) return;
    void estimateCost(gfa, floors, designData?.buildingType ?? null, sig);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [designData?.totalGfaSqm, designData?.floorCount, designData?.buildingType]);

  // 설계 기반이 아예 없으면(아직 설계 생성 전) 패널을 빈상태로만 안내.
  const hasDesign = !!(designData?.totalGfaSqm && designData.totalGfaSqm > 0);

  // 총사업비 추정: 공사비(SSOT)가 있으면 그 값 사용(가짜 합성 금지). 수지(SSOT)의 총비용 우선.
  const totalProjectCost = feasibilityData?.totalCostWon ?? costData?.totalConstructionCostWon ?? null;
  const roiPct = feasibilityData?.roiPct ?? null;
  const npvWon = feasibilityData?.npvWon ?? null;
  const profitRate = feasibilityData?.profitRatePct ?? null;

  const cGrade = carbonGrade(esgData?.totalCarbonPerSqm);

  // 설계해설 6섹션(있는 것만).
  const aiSections: [string, string][] = [
    ["design_overview", "설계 개요"],
    ["mass_strategy", "매스 전략"],
    ["floor_efficiency", "평면 효율"],
    ["compliance_review", "법규 준수"],
    ["circulation_core", "동선·코어"],
    ["improvement", "개선 제안"],
  ];
  const hasAi = !!designAi && aiSections.some(([k]) => designAi[k]);

  return (
    <div className="flex flex-col gap-5">
      {/* ── 섹션 헤더 ── */}
      <div className="flex flex-wrap items-end justify-between gap-3 px-2">
        <div className="flex items-center gap-3">
          <span className="h-2 w-8 rounded-full bg-[var(--accent-strong)]" />
          <h5 className="text-lg font-[1000] tracking-tight text-[var(--text-primary)]">
            설계 결과 · 사업성·환경 연결
          </h5>
        </div>
        {/* 은행제출 패키지 원클릭 — 설계+수지+법규 통합 PF심사 보고서(기존 빌더 재사용) */}
        <button
          type="button"
          onClick={() => setShowBankReport(true)}
          disabled={!hasDesign}
          className="flex items-center gap-2 rounded-full border border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] px-5 py-2.5 text-[11px] font-black uppercase tracking-widest text-[var(--accent-strong)] transition-all hover:bg-[var(--accent-strong)] hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
          title={hasDesign ? "PF 대출 심사용 보고서를 생성합니다" : "먼저 설계를 생성하세요"}
        >
          <span className="text-[13px] leading-none">🏦</span>
          PF심사용 보고서 생성
        </button>
      </div>

      {!hasDesign ? (
        /* ── 빈상태(무목업): 설계 전이면 가짜 수치 없이 정직 안내 ── */
        <div className="flex flex-col items-center gap-2 rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] px-6 py-10 text-center">
          <span className="text-2xl">📊</span>
          <p className="text-sm font-bold text-[var(--text-secondary)]">설계를 생성하면 사업성·환경 요약이 자동으로 채워집니다</p>
          <p className="max-w-md text-xs leading-relaxed text-[var(--text-hint)]">
            위에서 설계안을 적용하면 연면적·층수를 기준으로 공사비·수지(ROI·NPV)·ESG가 연동되어 표시됩니다.
          </p>
        </div>
      ) : (
        <>
          {/* ── ① 설계↔수지 실시간 요약 카드(총사업비/예상ROI/NPV) ── */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {/* 총사업비 */}
            <SummaryCard
              label="총사업비"
              loading={costLoading && totalProjectCost == null}
              value={totalProjectCost != null ? fmtKrw(totalProjectCost) : "—"}
              hint={
                costData?.source === "overview"
                  ? "설계 연동 자동 산정"
                  : totalProjectCost != null
                    ? "수지 SSOT"
                    : "공사비 분석 필요"
              }
              tone="text-[var(--text-primary)]"
            />
            {/* 공사비(범위) */}
            <SummaryCard
              label="공사비"
              loading={costLoading && costData?.totalConstructionCostWon == null}
              value={costData?.totalConstructionCostWon != null ? fmtKrw(costData.totalConstructionCostWon) : "—"}
              hint={
                costData?.rangeMinWon != null && costData?.rangeMaxWon != null
                  ? `${fmtKrw(costData.rangeMinWon)}~${fmtKrw(costData.rangeMaxWon)}`
                  : "설계 GFA 기준"
              }
              tone="text-[var(--text-primary)]"
            />
            {/* 예상 ROI */}
            <SummaryCard
              label="예상 ROI"
              value={roiPct != null ? `${roiPct.toFixed(1)}%` : "—"}
              hint={
                profitRate != null
                  ? `수익률 ${profitRate.toFixed(1)}%`
                  : roiPct == null
                    ? "수지분석 필요"
                    : ""
              }
              tone={
                roiPct == null
                  ? "text-[var(--text-hint)]"
                  : roiPct >= 0
                    ? "text-emerald-400"
                    : "text-rose-400"
              }
            />
            {/* NPV */}
            <SummaryCard
              label="NPV"
              value={npvWon != null ? fmtKrw(npvWon) : "—"}
              hint={npvWon == null ? "수지분석 필요" : npvWon >= 0 ? "사업성 양호" : "사업성 주의"}
              tone={npvWon == null ? "text-[var(--text-hint)]" : npvWon >= 0 ? "text-emerald-400" : "text-rose-400"}
            />
          </div>

          {/* 공사비 자동 산정 진행/오류 정직 표기 */}
          {costLoading && (
            <p className="-mt-2 px-2 text-[11px] font-bold text-[var(--text-hint)]">
              <span className="mr-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--accent-strong)]" />
              설계 기준 공사비 자동 산정 중…
            </p>
          )}
          {costError && (
            <p className="-mt-2 px-2 text-[11px] font-bold text-amber-400">{costError}</p>
          )}
          {/* 수지/ROI가 아직 없으면 무목업: 수지분석 화면으로 유도(가짜 ROI 금지). */}
          {!costLoading && roiPct == null && (
            <p className="-mt-2 px-2 text-[11px] text-[var(--text-hint)]">
              ※ 예상 ROI·NPV는 <b className="text-[var(--text-secondary)]">수지분석</b> 화면에서 산출 시 자동 연동됩니다(가짜 수치 미표시).
            </p>
          )}

          {/* ── ② 환경분석 인라인(ESG 배지) ── */}
          <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-3.5">
            <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">환경분석 · ESG</span>
            {esgData?.totalCarbonPerSqm || esgData?.embodiedCarbonKg ? (
              <div className="flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs">
                {cGrade && (
                  <span className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-black ${cGrade.tone}`}>
                    탄소집약도 {cGrade.label}
                  </span>
                )}
                {esgData?.totalCarbonPerSqm != null && (
                  <span className="flex items-center gap-1.5">
                    <span className="text-[var(--text-hint)]">㎡당 탄소</span>
                    <b className="cc-num text-[var(--text-primary)]">{Math.round(esgData.totalCarbonPerSqm).toLocaleString()}</b>
                    <span className="text-[var(--text-hint)]">kgCO₂</span>
                  </span>
                )}
                {esgData?.embodiedCarbonKg != null && (
                  <span className="flex items-center gap-1.5">
                    <span className="text-[var(--text-hint)]">내재탄소</span>
                    <b className="cc-num text-[var(--text-primary)]">{Math.round(esgData.embodiedCarbonKg).toLocaleString()}</b>
                    <span className="text-[var(--text-hint)]">kg</span>
                  </span>
                )}
                {esgData?.operationalCarbonKg != null && (
                  <span className="flex items-center gap-1.5">
                    <span className="text-[var(--text-hint)]">운영탄소</span>
                    <b className="cc-num text-[var(--text-primary)]">{Math.round(esgData.operationalCarbonKg).toLocaleString()}</b>
                    <span className="text-[var(--text-hint)]">kg</span>
                  </span>
                )}
              </div>
            ) : (
              /* 무목업: ESG 데이터 없으면 정직 빈상태 + 일조는 도면(C-02 음영분석)에서 확인 안내 */
              <span className="text-xs text-[var(--text-hint)]">
                ESG 분석 결과가 없습니다. ESG 화면에서 분석 시 등급·탄소량이 표시됩니다. 일조(음영)는 2D 도면의 <b className="text-[var(--text-secondary)]">음영 분석(C-02)</b>에서 확인하세요.
              </span>
            )}
          </div>

          {/* ── ③ 설계해설(쉬운 한국어) — DesignInterpreter 6섹션 표면화 ── */}
          {hasAi && designAi && (
            <div className="rounded-2xl border border-indigo-400/20 bg-[var(--surface-soft)] px-5 py-4">
              <div className="mb-3 flex items-center gap-2">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400" />
                <p className="text-[9px] font-black uppercase tracking-[0.3em] text-indigo-300">설계 해설 · 왜 이런 설계인가 · Claude</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {aiSections
                  .filter(([k]) => designAi[k])
                  .map(([k, label]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-4 py-3">
                      <p className="mb-1 text-[9px] font-black uppercase tracking-widest text-indigo-300/80">{label}</p>
                      <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-[var(--text-secondary)]">{designAi[k]}</p>
                    </div>
                  ))}
              </div>
              <p className="mt-3 text-[9px] text-[var(--text-hint)]">AI 생성 · 비전문가용 쉬운 해설 · 참고용</p>
            </div>
          )}
        </>
      )}

      {/* ══════════════ 은행제출 패키지 모달(기존 BankReadyReportBuilder 재사용) ══════════════ */}
      <AnimatePresence>
        {showBankReport && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 overflow-y-auto bg-black/60 backdrop-blur-sm"
            onClick={(e) => {
              if (e.target === e.currentTarget) setShowBankReport(false);
            }}
          >
            <div className="flex min-h-full items-start justify-center p-6 pt-16">
              <motion.div
                initial={{ opacity: 0, scale: 0.96, y: 16 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.96, y: 16 }}
                className="w-full max-w-4xl rounded-3xl border border-[var(--line-strong)] bg-[var(--surface)] p-6 shadow-[var(--shadow-2xl)]"
              >
                <div className="mb-4 flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="text-lg">🏦</span>
                    <h4 className="text-base font-black text-[var(--text-primary)]">PF심사용 사업성 보고서</h4>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowBankReport(false)}
                    className="rounded-full px-2 text-xl text-[var(--text-hint)] hover:text-[var(--text-primary)]"
                    aria-label="닫기"
                  >
                    ×
                  </button>
                </div>
                {/* 설계+수지+법규+ESG 통합 보고서 — 기존 빌더 그대로(로직·PDF 경로 불변) */}
                <BankReadyReportBuilder />
              </motion.div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── 요약 수치 카드(공통) ── */
function SummaryCard({
  label,
  value,
  hint,
  tone,
  loading,
}: {
  label: string;
  value: string;
  hint?: string;
  tone: string;
  loading?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3.5">
      <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{label}</p>
      {loading ? (
        <div className="mt-2 h-5 w-16 animate-pulse rounded bg-[var(--surface-muted)]" />
      ) : (
        <p className={`mt-1 cc-num text-xl font-black ${tone}`}>{value}</p>
      )}
      {hint && !loading && <p className="mt-0.5 text-[10px] text-[var(--text-hint)]">{hint}</p>}
    </div>
  );
}
