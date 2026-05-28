"use client";

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import type { SafetyDashboardData, SafetyViolation } from "@/components/cad/types";

const VIOLATION_BADGE: Record<
  SafetyViolation["violation_type"],
  { bg: string; text: string; label: string; glow: string }
> = {
  helmet_off: {
    bg: "rgba(239, 68, 68, 0.15)",
    text: "var(--error)",
    label: "안전모 미착용",
    glow: "0 0 25px rgba(239, 68, 68, 0.25)",
  },
  vest_off: {
    bg: "rgba(245, 158, 11, 0.15)",
    text: "var(--warning)",
    label: "안전조끼 미착용",
    glow: "0 0 25px rgba(245, 158, 11, 0.25)",
  },
};

export function SafetyCCTVDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["safety", "dashboard"],
    queryFn: () => (async () => ({} as SafetyDashboardData))(),
    refetchInterval: 5_000,
  });

  const feedRef = useRef<HTMLUListElement>(null);
  const liveViolations = data?.violations ?? [];

  useEffect(() => {
    if (feedRef.current) {
      feedRef.current.scrollTop = 0;
    }
  }, [liveViolations.length]);

  if (isLoading) {
    return <SkeletonLoader count={3} itemClassName="h-48" />;
  }

  if (!data) return null;

  const { stats } = data;

  return (
    <section className="grid gap-8" aria-label="지능형 CCTV 안전 관제">
      {/* KPI Stats Grid */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "금일 위반 총계", value: stats.total_violations_today, unit: "건", color: "var(--error)", trend: "last 24h" },
          { label: "안전모 미착용", value: stats.helmet_off_count, unit: "건", color: "var(--error)", trend: "critical" },
          { label: "안전조끼 미착용", value: stats.vest_off_count, unit: "건", color: "var(--warning)", trend: "warning" },
          { label: "활성 AI 카메라", value: stats.active_cameras, unit: "대", color: "var(--success)", trend: "online" },
        ].map((kpi, idx) => (
          <motion.div
            key={kpi.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: idx * 0.1 }}
          >
            <Card className="border-[var(--line-strong)] bg-[var(--surface-strong)]/80 backdrop-blur-md shadow-[var(--shadow-lg)] overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full" style={{ backgroundColor: kpi.color }} />
              <CardContent className="p-6">
                <div className="flex justify-between items-start">
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                    {kpi.label}
                  </p>
                  <span className="text-[9px] font-black uppercase px-2 py-0.5 rounded-full border border-white/5 bg-white/5 opacity-50">
                    {kpi.trend}
                  </span>
                </div>
                <p className="mt-4 text-4xl font-[1000] tracking-tighter" style={{ color: kpi.color }}>
                  {kpi.value}
                  <span className="ml-1 text-sm font-bold text-[var(--text-hint)] tracking-normal">{kpi.unit}</span>
                </p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-8 lg:grid-cols-[1fr_420px]">
        {/* Main CCTV Viewport */}
        <Card className="relative overflow-hidden border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)]">
          <CardContent className="p-0">
            <div className="relative aspect-video w-full bg-slate-950">
              {/* Scanline Effect Overlay */}
              <div className="absolute inset-0 pointer-events-none opacity-20 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.02),rgba(0,255,0,0.01),rgba(0,0,118,0.02))] z-10" style={{ backgroundSize: "100% 2px, 3px 100%" }} />
              
              {/* Camera Stream Placeholder */}
              <div className="absolute inset-0 flex flex-col items-center justify-center">
                <div className="relative mb-6">
                  <div className="h-24 w-24 rounded-full border-[3px] border-[var(--accent)]/20" />
                  <motion.div
                    className="absolute inset-0 rounded-full border-[3px] border-[var(--accent)] border-t-transparent shadow-[0_0_20px_var(--accent)]"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                  />
                  <div className="absolute inset-0 flex items-center justify-center">
                     <div className="h-2 w-2 rounded-full bg-[var(--accent)] animate-pulse" />
                  </div>
                </div>
                <div className="text-center space-y-2">
                   <p className="text-sm font-bold text-[var(--text-secondary)] italic font-mono uppercase tracking-widest">Initialising Stream Protocol...</p>
                   <p className="text-[10px] font-black text-[var(--text-hint)] uppercase tracking-[0.3em]">AI Handshake v2.4.9-Stable</p>
                </div>
                
                <div className="mt-8 flex gap-3">
                  {["N_GATE_01", "W_ZONE_04", "B1_PARK_02", "CRANE_TOP_01"].map((cam) => (
                    <button
                      key={cam}
                      className="rounded-lg bg-[var(--surface-soft)] px-4 py-2 text-[10px] font-black uppercase text-[var(--text-secondary)] border border-[var(--line)] hover:border-[var(--accent)] transition-all"
                    >
                      {cam}
                    </button>
                  ))}
                </div>
              </div>

              {/* HUD Elements */}
              <div className="absolute left-8 top-8 flex items-center gap-4 bg-black/60 backdrop-blur-xl px-5 py-3 rounded-2xl border border-white/10 z-20">
                <motion.div
                  className="h-3 w-3 rounded-full bg-[var(--error)] shadow-[0_0_15px_var(--error)]"
                  animate={{ opacity: [1, 0.4, 1] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                />
                <div className="flex flex-col">
                  <span className="text-[11px] font-black uppercase tracking-[0.2em] text-[var(--error)] leading-none">LIVE FEED</span>
                  <span className="text-[9px] font-mono text-white/40 mt-1">REC - 00:24:11:09</span>
                </div>
              </div>

              <div className="absolute right-8 top-8 z-20">
                <span className="rounded-2xl bg-[var(--accent-soft)] px-5 py-3 text-[10px] font-black uppercase tracking-widest text-[var(--accent)] border border-[var(--accent)]/20 backdrop-blur-xl">
                   ODS AI · YOLOv8 REAL-TIME
                </span>
              </div>

              {/* Bottom Telemetry */}
              <div className="absolute bottom-8 left-8 right-8 flex justify-between items-end z-20 font-mono text-[9px] text-white/30 uppercase tracking-widest">
                <div className="space-y-1">
                  <p>LAT: 37.5665° N / LON: 126.9780° E</p>
                  <p>ALT: +42.5M MSL / TEMP: 22.4°C</p>
                </div>
                <div className="text-right space-y-1">
                  <p>BITRATE: 8.4 MBPS / JITTER: 2MS</p>
                  <p>FPS: 59.94 / ENCODE: H.265 HEVC</p>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Real-time Detection Logs */}
        <Card className="flex flex-col border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden">
          <CardContent className="flex h-full flex-col p-8">
            <CardTitle className="mb-8 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="h-4 w-1 bg-[var(--error)]" />
                <span className="text-[12px] font-black uppercase tracking-[0.3em] text-[var(--text-primary)]">AI Detection Log</span>
              </div>
              <span className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest">Streaming Real-time</span>
            </CardTitle>

            <ul
              ref={feedRef}
              className="flex-1 space-y-4 overflow-y-auto pr-2 custom-scrollbar"
              style={{ maxHeight: "480px" }}
              aria-label="안전 위반 알림 피드"
            >
              <AnimatePresence initial={false}>
                {liveViolations.map((v) => {
                  const badge = VIOLATION_BADGE[v.violation_type];
                  return (
                    <motion.li
                      key={v.id}
                      initial={{ opacity: 0, x: 30, height: 0 }}
                      animate={{ opacity: 1, x: 0, height: "auto" }}
                      exit={{ opacity: 0, scale: 0.95 }}
                      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                      className="group relative rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]/50 p-5 transition-all hover:bg-[var(--surface)]"
                      style={{ boxShadow: badge.glow }}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0">
                          <span className="inline-flex items-center rounded-lg px-2.5 py-1 text-[9px] font-black uppercase tracking-[0.1em] border" style={{ backgroundColor: badge.bg, color: badge.text, borderColor: badge.text + "40" }}>
                            {badge.label}
                          </span>
                          <p className="mt-3 text-[11px] font-bold text-[var(--text-secondary)] font-mono">
                            ZONE: <span className="text-[var(--text-primary)]">{v.zone}</span> 
                            <span className="mx-2 opacity-20">|</span> 
                            CAM: <span className="text-[var(--text-primary)]">{v.camera_id}</span>
                          </p>
                        </div>
                        <span className="shrink-0 font-mono text-[10px] font-bold text-[var(--text-hint)]">
                          {new Date(v.detected_at).toLocaleTimeString("ko-KR", { hour12: false })}
                        </span>
                      </div>

                      <div className="mt-4">
                        <div className="flex justify-between items-center mb-1.5">
                           <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">AI Confidence</span>
                           <span className="text-[10px] font-black text-[var(--text-secondary)] font-mono">{(v.confidence * 100).toFixed(1)}%</span>
                        </div>
                        <div className="h-1 overflow-hidden rounded-full bg-[var(--line)]">
                          <motion.div
                            className="h-full rounded-full"
                            style={{ backgroundColor: badge.text }}
                            initial={{ width: 0 }}
                            animate={{ width: `${v.confidence * 100}%` }}
                            transition={{ duration: 1, ease: "easeOut" }}
                          />
                        </div>
                      </div>

                      {/* Action Button */}
                      <button className="absolute bottom-4 right-5 opacity-0 group-hover:opacity-100 transition-opacity text-[9px] font-black uppercase text-[var(--accent)] border-b border-[var(--accent)]">
                        View Frame
                      </button>
                    </motion.li>
                  );
                })}
              </AnimatePresence>
            </ul>
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
