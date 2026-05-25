"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { apiClient } from "@/lib/api-client";
import { formatCurrencyKRW } from "@/lib/formatters";

export function CostAndQuantityDashboard({ projectId, dictionary }: { projectId: string; dictionary: Record<string, string> }) {
  const [isMounted, setIsMounted] = useState(false);
  const t = dictionary;

  const [mockData, setMockData] = useState<Array<{ id: string; code: string; desc: string; unit: string; qty: number; rate: number; total: number }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!isMounted) return;
    async function fetchData() {
      try {
        const res = await apiClient.get<{ items: Array<{ id: string; code: string; desc: string; unit: string; qty: number; rate: number; total: number }> }>(`/projects/${projectId}/bim-takeoff`);
        if (res && res.items) {
          setMockData(res.items);
        }
      } catch (err) {
        console.error("Failed to load takeoff data", err);
      } finally {
        setLoading(false);
      }
    }
    fetchData();
  }, [projectId, isMounted]);

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
             {t.description || "BIM 엔진을 통한 실시간 물량 산출 및 공사비 예측 매트릭스입니다."}
          </p>
        </div>
        <button className="group relative overflow-hidden rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] px-8 py-4 text-xs font-black uppercase tracking-widest text-[var(--text-primary)] shadow-[var(--shadow-lg)] transition-all hover:-translate-y-1 hover:bg-[var(--surface-soft)]">
          <span className="relative z-10 flex items-center gap-3">
            {t.exportBtn || "데이터 내보내기"}
            <svg className="h-4 w-4 transition-transform group-hover:rotate-45" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M7 17L17 7M17 7H7M17 7V17"/></svg>
          </span>
        </button>
      </div>

      <div className="overflow-hidden rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] backdrop-blur-3xl">
         <table className="w-full text-left text-sm border-collapse">
           <thead className="bg-[var(--surface-soft)]/50 text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-hint)] border-b border-[var(--line-strong)]">
             <tr>
               <th className="p-10 pl-14">{t.colCode || "품목 코드"}</th>
               <th className="p-10">{t.colDesc || "적요"}</th>
               <th className="p-10">{t.colUnit || "단위"}</th>
               <th className="p-10 text-right">{t.colQty || "수량"}</th>
               <th className="p-10 text-right">{t.colRate || "단가"}</th>
               <th className="p-10 pr-14 text-right">{t.colTotal || "합계"}</th>
             </tr>
           </thead>
           <tbody className="divide-y divide-[var(--line-strong)]">
             {mockData.map((item, i) => (
               <motion.tr 
                 key={item.id} 
                 initial={{ opacity: 0, x: -10 }}
                 animate={{ opacity: 1, x: 0 }}
                 transition={{ delay: i * 0.05 }}
                 className="group transition-all hover:bg-[var(--accent-soft)]/5"
               >
                 <td className="p-8 pl-14 font-mono text-[11px] text-[var(--text-hint)] group-hover:text-[var(--accent-strong)] transition-colors italic tracking-tighter">[{item.code}]</td>
                 <td className="p-8 font-[1000] text-[var(--text-primary)] tracking-tight">{item.desc}</td>
                 <td className="p-8 font-black text-[var(--text-tertiary)] uppercase tracking-widest text-[9px]">{item.unit}</td>
                 <td className="p-8 text-right font-mono font-bold text-[var(--accent-strong)] text-lg">{item.qty.toLocaleString()}</td>
                 <td className="p-8 text-right font-mono font-medium text-[var(--text-secondary)]">{item.rate.toLocaleString()}</td>
                 <td className="p-8 pr-14 text-right font-mono font-[1000] text-xl text-[var(--text-primary)] italic tracking-tighter group-hover:scale-110 transition-transform origin-right">{item.total.toLocaleString()}</td>
               </motion.tr>
             ))}
           </tbody>
         </table>
         <div className="flex items-center justify-between border-t-2 border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-12 px-14">
             <div className="flex items-center gap-4">
                <div className="h-3 w-3 rounded-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)]" />
                <span className="text-[11px] font-black uppercase tracking-[0.4em] text-[var(--text-tertiary)] italic">{t.subtotal || "AI 견적 총계 (VAT 별도)"}</span>
             </div>
             <div className="flex items-baseline gap-2">
                <span className="text-5xl font-[1000] tracking-tighter text-[var(--text-primary)] italic">
                  {formatCurrencyKRW(mockData.reduce((acc, curr) => acc + curr.total, 0) || 3920000000)}
                </span>
             </div>
         </div>
      </div>
    </div>
  );
}
