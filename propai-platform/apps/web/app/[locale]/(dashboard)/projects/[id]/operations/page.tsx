"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { isValidLocale, type Locale } from "@/i18n/config";
import { useDictionary } from "@/hooks/use-dictionary";
import { apiClient } from "@/lib/api-client";

export default function OperationsPage() {
  const { locale, id } = useParams() as { locale: string; id: string };
  const { dictionary, isLoading } = useDictionary(locale as Locale);
  
  const [data, setData] = useState<{ kpis: any[], maintenance: any[], sensors: any[] } | null>(null);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    async function fetchStatus() {
      try {
        const res = await apiClient.get<any>(`/projects/${id}/operations/status`);
        setData(res);
      } catch (err) {
        console.error("Failed to fetch operations status", err);
      } finally {
        setFetching(false);
      }
    }
    fetchStatus();
  }, [id]);

  if (isLoading || fetching || !dictionary) {
    return (
      <div className="flex h-[60vh] items-center justify-center">
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-teal-500 border-t-transparent shadow-[0_0_20px_rgba(20,184,166,0.3)]" />
      </div>
    );
  }

  const runtimeMode =
    process.env.NEXT_PUBLIC_USE_MOCKS === "false"
      ? dictionary.workspace.modeLive
      : dictionary.workspace.modeMock;

  const t = dictionary.modulePlaceholders["operations"];

  return (
    <div className="flex flex-col gap-12 pb-20">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
      >
        <ModulePlaceholder
          eyebrow={t.eyebrow}
          title={t.title}
          description={t.description}
          statusLabel={runtimeMode}
          localeLabel={locale}
          items={t.items}
        />
      </motion.div>

      <div className="grid gap-10 md:grid-cols-2">
        {/* Operations KPI Analytics */}
        <motion.div 
          initial={{ opacity: 0, x: -30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-[3.5rem] border border-white/5 bg-[#0a0f14]/80 p-12 shadow-2xl backdrop-blur-3xl"
        >
          <div className="flex items-center gap-4 mb-10">
            <div className="h-10 w-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-400">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>
            </div>
            <h3 className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">자산 가동 KPI</h3>
          </div>

          <div className="grid gap-4">
            {data?.kpis.map((item, i) => (
              <motion.div 
                key={item.label}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 + i * 0.1 }}
                className="flex items-center justify-between rounded-3xl bg-white/5 border border-white/5 p-8 transition-all hover:bg-white/10 group/row"
              >
                <div className="space-y-1">
                  <span className="text-[11px] font-black uppercase tracking-widest text-white/40 group-hover/row:text-teal-400 transition-colors">{item.label}</span>
                  <p className="text-[9px] font-bold text-white/10 uppercase">Real-time Performance</p>
                </div>
                <span className="text-4xl font-black text-white tracking-tighter italic">{item.value}</span>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Maintenance Intelligence */}
        <motion.div 
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="rounded-[3.5rem] border border-white/5 bg-[#0a0f14]/80 p-12 shadow-2xl backdrop-blur-3xl"
        >
          <div className="flex items-center gap-4 mb-10">
            <div className="h-10 w-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-400">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
            </div>
            <h3 className="text-[10px] font-black text-white/40 uppercase tracking-[0.4em]">유지보수 및 예지정비</h3>
          </div>

          <div className="grid gap-4">
            {data?.maintenance.map((item, i) => (
              <motion.div 
                key={item.label}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 + i * 0.1 }}
                className="flex items-center justify-between rounded-3xl bg-white/5 border border-white/5 p-8 transition-all hover:bg-white/10 group/row"
              >
                <div className="space-y-1">
                  <span className="text-[11px] font-black uppercase tracking-widest text-white/40 group-hover/row:text-indigo-400 transition-colors">{item.label}</span>
                  <p className="text-[9px] font-bold text-white/10 uppercase">System Readiness</p>
                </div>
                <span className={`text-xl font-black italic ${item.label.includes("긴급") && item.value !== "0 건" ? "text-red-500 shadow-[0_0_15px_#ef4444]" : "text-white"}`}>
                  {item.value}
                </span>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </div>

      {/* ── Real-time IoT Environment Hub ── */}
      <motion.div 
        initial={{ opacity: 0, y: 40 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="rounded-[4rem] border border-white/5 bg-[#0a0f14]/50 p-12 lg:p-20 shadow-2xl backdrop-blur-xl group"
      >
        <div className="mb-14 flex items-center justify-between">
            <div className="space-y-4">
              <h3 className="text-4xl font-black text-white tracking-tighter">실시간 IoT 환경 지표<span className="text-teal-400">.</span></h3>
              <p className="text-sm font-medium text-white/30 tracking-tight italic">사통팔땅 오케스트레이터와 연결된 스마트 센서 네트워크의 실시간 스트림입니다.</p>
            </div>
            <div className="flex h-12 items-center gap-4 rounded-2xl bg-teal-500/10 px-6 ring-1 ring-teal-500/30">
                <span className="h-2 w-2 rounded-full bg-teal-500 animate-ping shadow-[0_0_10px_#14b8a6]" />
                <span className="text-[10px] font-black text-teal-400 uppercase tracking-[0.4em]">Live Stream</span>
            </div>
        </div>
        
        <div className="grid gap-8 md:grid-cols-3">
          {data?.sensors.map((item, i) => (
            <motion.div 
               key={item.label} 
               initial={{ opacity: 0, scale: 0.9 }}
               whileInView={{ opacity: 1, scale: 1 }}
               transition={{ delay: 0.1 * i }}
               className="group/sensor relative flex flex-col gap-10 rounded-[3rem] border border-white/5 bg-white/5 p-12 transition-all hover:-translate-y-2 hover:bg-white/10"
            >
              <div className="flex items-center justify-between">
                <span className="text-5xl drop-shadow-2xl transition-transform group-hover/sensor:scale-125 duration-500">{item.icon}</span>
                <div className="h-8 w-8 rounded-full border border-white/10 bg-white/5 flex items-center justify-center">
                  <div className="h-1.5 w-1.5 rounded-full bg-teal-500" />
                </div>
              </div>
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.4em] text-white/30 group-hover/sensor:text-teal-400 transition-colors">{item.label}</p>
                <div className="flex items-baseline gap-2 mt-4">
                  <p className="text-5xl font-black text-white leading-none tracking-tighter group-hover/sensor:scale-105 transition-transform origin-left">{item.value}</p>
                  <span className="text-[10px] font-black text-white/20">NOMINAL</span>
                </div>
              </div>
              <div className="absolute bottom-10 right-10 opacity-0 group-hover/sensor:opacity-100 transition-opacity">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2" strokeOpacity="0.2"><path d="M21 12H3m18 0l-4-4m4 4l-4 4"/></svg>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* ── Action Command Bar ── */}
      <motion.div 
        initial={{ opacity: 0, y: 30 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        className="flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between rounded-[3rem] border border-white/10 bg-teal-500/10 p-10 lg:px-14 shadow-2xl backdrop-blur-3xl ring-1 ring-teal-500/20"
      >
         <div className="flex flex-col gap-3">
            <div className="flex items-center gap-3">
              <div className="h-2 w-2 rounded-full bg-teal-500 shadow-[0_0_10px_#14b8a6]" />
              <p className="text-[10px] font-black text-teal-400 uppercase tracking-[0.4em]">Intelligence Report</p>
            </div>
            <p className="text-2xl font-black text-white tracking-tight">수익 안정화 단계 진입<span className="text-white/30 ml-3 font-medium text-lg leading-relaxed italic">/ 월간 수익 가이드라인 기준 12.4% 초과 달성</span></p>
         </div>
         <button className="group relative overflow-hidden rounded-[2rem] bg-white px-10 py-5 text-sm font-black text-[#0a0f14] transition-all hover:scale-105 hover:bg-teal-400 active:scale-95 shadow-[0_0_40px_rgba(255,255,255,0.1)]">
            <span className="relative z-10 flex items-center gap-3">
              운영 리포트 생성
              <svg className="h-5 w-5 transition-transform group-hover:translate-x-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M7 17L17 7M17 7H7M17 7V17"/></svg>
            </span>
         </button>
      </motion.div>
    </div>
  );
}
