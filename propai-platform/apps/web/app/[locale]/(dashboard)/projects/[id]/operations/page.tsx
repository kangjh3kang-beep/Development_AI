"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { motion } from "framer-motion";
import { ModulePlaceholder } from "@/components/layout/ModulePlaceholder";
import { isValidLocale, type Locale } from "@/i18n/config";
import { isMockMode } from "@/lib/runtime-mode";
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
        <div className="h-12 w-12 animate-spin rounded-full border-4 border-[var(--data-accent)] border-t-transparent shadow-[var(--data-glow)]" />
      </div>
    );
  }

  const runtimeMode = isMockMode()
    ? dictionary.workspace.modeMock
    : dictionary.workspace.modeLive;

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
          className="cc-panel cc-bracketed cc-interactive relative overflow-hidden rounded-[var(--radius-2xl)] p-12 shadow-2xl"
        >
          <i className="cc-bracket cc-bracket--tl" aria-hidden /><i className="cc-bracket cc-bracket--tr" aria-hidden />
          <i className="cc-bracket cc-bracket--bl" aria-hidden /><i className="cc-bracket cc-bracket--br" aria-hidden />
          <div className="cc-grid-bg" aria-hidden />
          <div className="relative z-10 flex items-center justify-between gap-4 mb-10">
            <div className="flex items-center gap-4">
              <div className="h-10 w-10 rounded-2xl bg-[var(--data-accent-soft)] flex items-center justify-center text-[var(--data-accent)]">
                <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>
              </div>
              <h3 className="cc-meta">자산 가동 KPI · ASSET UPTIME</h3>
            </div>
            <span className="cc-live"><i />LIVE</span>
          </div>

          <div className="relative z-10 grid gap-4">
            {data?.kpis.map((item, i) => (
              <motion.div
                key={item.label}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 + i * 0.1 }}
                className="flex items-center justify-between rounded-3xl bg-[var(--surface-soft)] border border-[var(--line)] p-8 transition-all hover:border-[var(--data-accent-line)] group/row"
              >
                <div className="space-y-1">
                  <span className="cc-label group-hover/row:text-[var(--data-accent)] transition-colors">{item.label}</span>
                  <p className="text-[9px] font-bold text-[var(--text-hint)] uppercase tracking-widest">Real-time Performance</p>
                </div>
                <span className="cc-num text-4xl font-black tracking-tighter">{item.value}</span>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* Maintenance Intelligence */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.3 }}
          className="cc-panel cc-bracketed cc-interactive relative overflow-hidden rounded-[var(--radius-2xl)] p-12 shadow-2xl"
        >
          <i className="cc-bracket cc-bracket--tl" aria-hidden /><i className="cc-bracket cc-bracket--tr" aria-hidden />
          <i className="cc-bracket cc-bracket--bl" aria-hidden /><i className="cc-bracket cc-bracket--br" aria-hidden />
          <div className="cc-grid-bg" aria-hidden />
          <div className="relative z-10 flex items-center gap-4 mb-10">
            <div className="h-10 w-10 rounded-2xl bg-[var(--chart-2)]/10 flex items-center justify-center text-[var(--chart-2)]">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>
            </div>
            <h3 className="cc-meta" style={{ color: "var(--chart-2)" }}>유지보수 및 예지정비 · PREDICTIVE</h3>
          </div>

          <div className="relative z-10 grid gap-4">
            {data?.maintenance.map((item, i) => (
              <motion.div
                key={item.label}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5 + i * 0.1 }}
                className="flex items-center justify-between rounded-3xl bg-[var(--surface-soft)] border border-[var(--line)] p-8 transition-all hover:border-[var(--chart-2)]/40 group/row"
              >
                <div className="space-y-1">
                  <span className="cc-label group-hover/row:text-[var(--chart-2)] transition-colors">{item.label}</span>
                  <p className="text-[9px] font-bold text-[var(--text-hint)] uppercase tracking-widest">System Readiness</p>
                </div>
                <span className={`cc-num text-xl font-black ${item.label.includes("긴급") && item.value !== "0 건" ? "text-[var(--status-error)]" : ""}`}>
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
        className="cc-panel cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] p-12 lg:p-20 shadow-2xl group"
      >
        <i className="cc-bracket cc-bracket--tl" aria-hidden /><i className="cc-bracket cc-bracket--tr" aria-hidden />
        <i className="cc-bracket cc-bracket--bl" aria-hidden /><i className="cc-bracket cc-bracket--br" aria-hidden />
        <div className="cc-grid-bg cc-grid-bg--radial" aria-hidden />
        <div className="relative z-10 mb-14 flex items-center justify-between">
            <div className="space-y-4">
              <span className="cc-meta">IoT SENSOR NETWORK · STREAM</span>
              <h3 className="text-4xl font-black text-[var(--text-primary)] tracking-tighter">실시간 IoT 환경 지표<span className="text-[var(--data-accent)]">.</span></h3>
              <p className="text-sm font-medium text-[var(--text-tertiary)] tracking-tight italic">사통팔땅 오케스트레이터와 연결된 스마트 센서 네트워크의 실시간 스트림입니다.</p>
            </div>
            <span className="cc-live"><i />LIVE STREAM</span>
        </div>

        <div className="relative z-10 grid gap-8 md:grid-cols-3">
          {data?.sensors.map((item, i) => (
            <motion.div
               key={item.label}
               initial={{ opacity: 0, scale: 0.9 }}
               whileInView={{ opacity: 1, scale: 1 }}
               transition={{ delay: 0.1 * i }}
               className="cc-interactive group/sensor relative flex flex-col gap-10 rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-12"
            >
              <div className="flex items-center justify-between">
                <span className="text-5xl drop-shadow-2xl transition-transform group-hover/sensor:scale-125 duration-500">{item.icon}</span>
                <div className="h-8 w-8 rounded-full border border-[var(--data-accent-line)] bg-[var(--data-accent-soft)] flex items-center justify-center">
                  <div className="h-1.5 w-1.5 rounded-full bg-[var(--data-accent)]" />
                </div>
              </div>
              <div>
                <p className="cc-label group-hover/sensor:text-[var(--data-accent)] transition-colors">{item.label}</p>
                <div className="flex items-baseline gap-2 mt-4">
                  <p className="cc-num text-5xl font-black leading-none tracking-tighter group-hover/sensor:scale-105 transition-transform origin-left">{item.value}</p>
                  <span className="cc-chip-data" style={{ color: "var(--status-success)", background: "color-mix(in srgb, var(--status-success) 12%, transparent)", borderColor: "color-mix(in srgb, var(--status-success) 30%, transparent)" }}>NOMINAL</span>
                </div>
              </div>
              <div className="absolute bottom-10 right-10 opacity-0 group-hover/sensor:opacity-100 transition-opacity">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--data-accent)" strokeWidth="2"><path d="M21 12H3m18 0l-4-4m4 4l-4 4"/></svg>
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
        className="cc-bracketed relative flex flex-col gap-8 lg:flex-row lg:items-center lg:justify-between overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--data-accent-line)] bg-[var(--data-accent-soft)] p-10 lg:px-14 shadow-2xl"
      >
         <i className="cc-bracket cc-bracket--tl" aria-hidden /><i className="cc-bracket cc-bracket--tr" aria-hidden />
         <i className="cc-bracket cc-bracket--bl" aria-hidden /><i className="cc-bracket cc-bracket--br" aria-hidden />
         <div className="relative z-10 flex flex-col gap-3">
            <span className="cc-live"><i />INTELLIGENCE REPORT</span>
            <p className="text-2xl font-black text-[var(--text-primary)] tracking-tight">수익 안정화 단계 진입<span className="text-[var(--text-tertiary)] ml-3 font-medium text-lg leading-relaxed italic">/ 월간 수익 가이드라인 기준 12.4% 초과 달성</span></p>
         </div>
         <button className="cc-interactive group relative z-10 overflow-hidden rounded-[var(--radius-lg)] bg-[var(--accent-strong)] px-10 py-5 text-sm font-black text-white transition-all hover:scale-105 active:scale-95 shadow-[var(--shadow-glow)]">
            <span className="relative z-10 flex items-center gap-3">
              운영 리포트 생성
              <svg className="h-5 w-5 transition-transform group-hover:translate-x-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M7 17L17 7M17 7H7M17 7V17"/></svg>
            </span>
         </button>
      </motion.div>
    </div>
  );
}
