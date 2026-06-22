"use client";

import { useEffect, useMemo, useState } from "react";
import { Construction } from "lucide-react";
import { motion } from "framer-motion";
import { apiClient } from "@/lib/api-client";
import { formatCurrencyKRW } from "@/lib/formatters";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { getZoningSpec } from "@/lib/kr-building-regulations";

/** estimate-overview 항목별 적산(QTO) 행 — cost.py items[] 스키마 정합. */
interface QtoItem {
  name?: string;
  spec?: string;
  unit?: string;
  quantity?: number;
  unit_cost_won?: number;
  cost_won?: number;
}

interface OverviewResult {
  total_won: number;
  direct_won: number;
  qto_source?: string; // bim | derived
  items?: QtoItem[];
}

/** 설계 buildingType(한글/임의) → estimate-overview building_type 코드 매핑. */
function mapBuildingType(bt?: string | null): string {
  const s = (bt || "").toString();
  if (/오피스텔/.test(s)) return "officetel";
  if (/지식산업|창고|물류/.test(s)) return "warehouse";
  if (/업무|오피스(?!텔)/.test(s)) return "office";
  if (/연립|다세대|빌라/.test(s)) return "townhouse";
  if (/단독/.test(s)) return "single_house";
  return "apartment";
}

export function CostAndQuantityDashboard({ projectId, dictionary }: { projectId: string; dictionary: Record<string, string> }) {
  const [isMounted, setIsMounted] = useState(false);
  const t = dictionary;

  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const ctxProjectId = useProjectContextStore((s) => s.projectId);

  const [items, setItems] = useState<QtoItem[]>([]);
  const [qtoSource, setQtoSource] = useState<string>("derived");
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState("");

  useEffect(() => {
    setIsMounted(true);
  }, []);

  // 부지면적 × 용적률로 GFA 폴백(설계 미완 시).
  const fallbackGfa = useMemo(() => {
    // ★다필지면 통합 면적으로 적산 GFA를 역산(대표값 과소산출 방지).
    const land = effectiveLandAreaSqm(siteAnalysis) ?? 0;
    if (land <= 0) return 0;
    const spec = siteAnalysis?.zoneCode ? getZoningSpec(siteAnalysis.zoneCode) : null;
    const far = spec?.floorAreaRatioMax ?? 0;
    if (far <= 0) return 0;
    return Math.round((land * far) / 100);
  }, [siteAnalysis]);

  // 건축개요(설계 우선, 부지 폴백) — estimate-overview 요청 파라미터.
  const overview = useMemo(() => {
    const gfa = designData?.totalGfaSqm && designData.totalGfaSqm > 0 ? Math.round(designData.totalGfaSqm) : fallbackGfa;
    return {
      building_type: mapBuildingType(designData?.buildingType),
      total_gfa_sqm: gfa,
      floor_count_above: designData?.floorCount && designData.floorCount > 0 ? designData.floorCount : 15,
      floor_count_below: 2,
      structure_type: "RC",
    };
  }, [designData?.totalGfaSqm, designData?.buildingType, designData?.floorCount, fallbackGfa]);

  useEffect(() => {
    if (!isMounted) return;
    // 컨텍스트 프로젝트와 라우트 프로젝트가 다르면(미동기) 산출 보류 — 무목업 정직 표기.
    if (ctxProjectId && ctxProjectId !== projectId) { setLoading(false); return; }
    if (!overview.total_gfa_sqm || overview.total_gfa_sqm <= 0) { setLoading(false); return; }
    let cancelled = false;
    async function fetchData() {
      setLoading(true); setErr("");
      try {
        const res = await apiClient.post<OverviewResult>("/cost/estimate-overview", {
          body: { ...overview, project_id: projectId || undefined },
          useMock: false,
          timeoutMs: 30000,
        });
        if (cancelled) return;
        setItems(res?.items ?? []);
        setQtoSource(res?.qto_source ?? "derived");
      } catch (error) {
        if (cancelled) return;
        console.error("Failed to load takeoff data", error);
        setErr("공사 물량 산출에 실패했습니다. 입력값(연면적·층수)을 확인하세요.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchData();
    return () => { cancelled = true; };
  }, [projectId, ctxProjectId, isMounted, overview]);

  const subtotal = useMemo(() => items.reduce((acc, it) => acc + (it.cost_won ?? 0), 0), [items]);

  if (!isMounted) return <div className="p-8 text-center text-sm font-bold animate-pulse text-[var(--text-tertiary)] italic uppercase tracking-widest">Initializing...</div>;

  if (loading) return (
    <div className="flex h-64 flex-col items-center justify-center gap-6">
      <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--accent-strong)] border-t-transparent shadow-[var(--shadow-glow)]" />
      <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)] animate-pulse">AI 산출 내역 분석 중...</p>
    </div>
  );

  return (
    <div className="flex flex-col gap-10">
      <div className="flex items-end justify-between px-2">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
             <div className="h-2 w-10 rounded-full bg-[var(--accent-strong)]" />
             <h4 className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)] uppercase">{t.title || "AI 산출 내역서"}</h4>
          </div>
          <p className="max-w-2xl text-sm font-medium leading-relaxed text-[var(--text-secondary)] italic underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
             {t.description || "건축개요(설계·부지) 기반 항목별 물량 산출(QTO) 및 공사비 매트릭스입니다."}
          </p>
          <div className="flex items-center gap-2">
            {qtoSource === "bim"
              ? <span className="inline-flex items-center gap-1 rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-bold text-emerald-400"><Construction className="size-3" aria-hidden />BIM 매스 실치수 적산</span>
              : <span className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">건축개요 역산(추정) — 설계/BIM 완성 시 정밀화</span>}
          </div>
        </div>
        <button className="group relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] px-8 py-4 text-xs font-black uppercase tracking-widest text-[var(--text-primary)] shadow-[var(--shadow-lg)] transition-all hover:-translate-y-1 hover:bg-[var(--surface-soft)]">
          <span className="relative z-10 flex items-center gap-3">
            {t.exportBtn || "데이터 내보내기"}
            <svg className="h-4 w-4 transition-transform group-hover:rotate-45" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M7 17L17 7M17 7H7M17 7V17"/></svg>
          </span>
        </button>
      </div>

      {err ? (
        <div className="rounded-[2rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-10 text-center text-sm font-bold text-amber-400 italic">{err}</div>
      ) : items.length === 0 ? (
        <div className="rounded-[2rem] border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-10 text-center text-sm font-medium text-[var(--text-secondary)] italic">
          건축개요(연면적·층수)가 없어 물량을 산출할 수 없습니다. 부지/설계 분석을 먼저 진행하면 자동으로 채워집니다.
        </div>
      ) : (
      <div className="overflow-hidden rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] backdrop-blur-3xl">
         <table className="w-full text-left text-sm border-collapse">
           <thead className="bg-[var(--surface-soft)]/50 text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-hint)] border-b border-[var(--line-strong)]">
             <tr>
               <th className="p-10 pl-14">{t.colCode || "공종"}</th>
               <th className="p-10">{t.colDesc || "규격"}</th>
               <th className="p-10">{t.colUnit || "단위"}</th>
               <th className="p-10 text-right">{t.colQty || "수량"}</th>
               <th className="p-10 text-right">{t.colRate || "단가"}</th>
               <th className="p-10 pr-14 text-right">{t.colTotal || "합계"}</th>
             </tr>
           </thead>
           <tbody className="divide-y divide-[var(--line-strong)]">
             {items.map((item, i) => (
               <motion.tr
                 key={`${item.name ?? "item"}-${i}`}
                 initial={{ opacity: 0, x: -10 }}
                 animate={{ opacity: 1, x: 0 }}
                 transition={{ delay: i * 0.05 }}
                 className="group transition-all hover:bg-[var(--accent-soft)]/5"
               >
                 <td className="p-8 pl-14 font-[1000] text-[var(--text-primary)] tracking-tight">{item.name || "-"}</td>
                 <td className="p-8 font-medium text-[var(--text-secondary)] tracking-tight">{item.spec || "-"}</td>
                 <td className="p-8 font-black text-[var(--text-tertiary)] uppercase tracking-widest text-[9px]">{item.unit || "-"}</td>
                 <td className="p-8 text-right font-mono font-bold text-[var(--accent-strong)] text-lg">{(item.quantity ?? 0).toLocaleString()}</td>
                 <td className="p-8 text-right font-mono font-medium text-[var(--text-secondary)]">{(item.unit_cost_won ?? 0).toLocaleString()}</td>
                 <td className="p-8 pr-14 text-right font-mono font-[1000] text-xl text-[var(--text-primary)] italic tracking-tighter group-hover:scale-110 transition-transform origin-right">{(item.cost_won ?? 0).toLocaleString()}</td>
               </motion.tr>
             ))}
           </tbody>
         </table>
         <div className="flex items-center justify-between border-t-2 border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-12 px-14">
             <div className="flex items-center gap-4">
                <div className="h-3 w-3 rounded-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)]" />
                <span className="text-[11px] font-black uppercase tracking-[0.4em] text-[var(--text-tertiary)] italic">{t.subtotal || "항목별 적산 합계 (VAT 별도)"}</span>
             </div>
             <div className="flex items-baseline gap-2">
                <span className="text-5xl font-[1000] tracking-tighter text-[var(--text-primary)] italic">
                  {subtotal > 0 ? formatCurrencyKRW(subtotal) : "—"}
                </span>
             </div>
         </div>
      </div>
      )}
    </div>
  );
}
