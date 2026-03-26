"use client";

import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Card, CardContent, CardTitle } from "@propai/ui";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { apiClient } from "@/lib/api-client";
import type { SafetyDashboardData, SafetyViolation } from "@/components/cad/types";

const VIOLATION_BADGE: Record<
  SafetyViolation["violation_type"],
  { bg: string; text: string; label: string; glow: string }
> = {
  helmet_off: {
    bg: "bg-red-500/10",
    text: "text-red-400",
    label: "안전모 미착용",
    glow: "shadow-[0_0_20px_rgba(239,68,68,0.3)]",
  },
  vest_off: {
    bg: "bg-amber-500/10",
    text: "text-amber-400",
    label: "조끼 미착용",
    glow: "shadow-[0_0_20px_rgba(245,158,11,0.3)]",
  },
};

export function SafetyCCTVDashboard() {
  const { data, isLoading } = useQuery({
    queryKey: ["safety", "dashboard"],
    queryFn: () => apiClient.get<SafetyDashboardData>("/safety/dashboard"),
    refetchInterval: 10_000,
  });

  const feedRef = useRef<HTMLUListElement>(null);

  // data에서 직접 파생 (setState in effect 방지)
  const liveViolations = data?.violations ?? [];

  // 피드 자동 스크롤
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
    <section className="grid gap-6" aria-label="지능형 CCTV 관제 대시보드">
      {/* KPI 카드 */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {[
          { label: "오늘 위반 건수", value: stats.total_violations_today, unit: "건", color: "text-red-400" },
          { label: "안전모 미착용", value: stats.helmet_off_count, unit: "건", color: "text-red-400" },
          { label: "조끼 미착용", value: stats.vest_off_count, unit: "건", color: "text-amber-400" },
          { label: "활성 카메라", value: stats.active_cameras, unit: "대", color: "text-emerald-400" },
        ].map((kpi) => (
          <motion.div
            key={kpi.label}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
          >
            <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
              <CardContent className="p-5">
                <p className="text-xs uppercase tracking-widest text-slate-400">
                  {kpi.label}
                </p>
                <p className={`mt-2 text-3xl font-bold ${kpi.color}`}>
                  {kpi.value}
                  <span className="ml-1 text-sm font-normal text-slate-500">{kpi.unit}</span>
                </p>
              </CardContent>
            </Card>
          </motion.div>
        ))}
      </div>

      {/* 메인: 영상 + 실시간 알림 */}
      <div className="grid gap-6 lg:grid-cols-[1fr_380px]">
        {/* CCTV 영상 모니터 */}
        <Card className="overflow-hidden border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
          <CardContent className="p-0">
            <div className="relative aspect-video w-full bg-black">
              {/* 영상 프록시 연결 대기 시 플레이스홀더 */}
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-3">
                <div className="relative">
                  <div className="h-16 w-16 rounded-full border-2 border-emerald-500/30" />
                  <motion.div
                    className="absolute inset-0 rounded-full border-2 border-emerald-400 border-t-transparent"
                    animate={{ rotate: 360 }}
                    transition={{ duration: 2, repeat: Infinity, ease: "linear" }}
                  />
                </div>
                <p className="text-sm text-slate-400">RTSP 스트림 대기 중...</p>
                <div className="flex gap-2">
                  {["cam-01", "cam-02", "cam-03", "cam-04"].map((cam) => (
                    <span
                      key={cam}
                      className="rounded-full bg-emerald-500/10 px-3 py-1 text-[10px] font-mono text-emerald-400"
                    >
                      {cam}
                    </span>
                  ))}
                </div>
              </div>
              {/* 좌상단 LIVE 배지 */}
              <div className="absolute left-4 top-4 flex items-center gap-2">
                <motion.div
                  className="h-2.5 w-2.5 rounded-full bg-red-500"
                  animate={{ opacity: [1, 0.3, 1] }}
                  transition={{ duration: 1.5, repeat: Infinity }}
                />
                <span className="rounded bg-red-500/20 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-red-400">
                  LIVE
                </span>
              </div>
              {/* 우상단 YOLOv8 태그 */}
              <div className="absolute right-4 top-4">
                <span className="rounded bg-cyan-500/20 px-2 py-0.5 text-[10px] font-mono text-cyan-400">
                  YOLOv8 · 5-frame skip
                </span>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* 실시간 위반 알림 피드 */}
        <Card className="border-white/5 bg-gradient-to-br from-[#0f172a] to-[#1e293b] backdrop-blur-xl">
          <CardContent className="flex h-full flex-col p-5">
            <CardTitle className="mb-4 flex items-center gap-2 text-base text-slate-200">
              <motion.span
                className="inline-block h-2 w-2 rounded-full bg-red-500"
                animate={{ scale: [1, 1.3, 1] }}
                transition={{ duration: 1.2, repeat: Infinity }}
              />
              실시간 적발 로그
            </CardTitle>
            <ul
              ref={feedRef}
              className="flex-1 space-y-2 overflow-y-auto pr-1"
              style={{ maxHeight: "420px" }}
              aria-label="안전 위반 알림 피드"
            >
              <AnimatePresence initial={false}>
                {liveViolations.map((v) => {
                  const badge = VIOLATION_BADGE[v.violation_type];
                  return (
                    <motion.li
                      key={v.id}
                      initial={{ opacity: 0, x: 40, height: 0 }}
                      animate={{ opacity: 1, x: 0, height: "auto" }}
                      exit={{ opacity: 0, x: -40 }}
                      transition={{ duration: 0.35, ease: "easeOut" }}
                      className={`rounded-xl border border-white/5 bg-white/[0.03] p-3.5 ${badge.glow}`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <span className={`inline-block rounded-full ${badge.bg} px-2.5 py-0.5 text-[10px] font-bold ${badge.text}`}>
                            {badge.label}
                          </span>
                          <p className="mt-1.5 text-xs text-slate-400">
                            {v.zone} · {v.camera_id}
                          </p>
                        </div>
                        <span className="shrink-0 text-right text-[10px] text-slate-500">
                          {new Date(v.detected_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                        </span>
                      </div>
                      <div className="mt-2 h-1 overflow-hidden rounded-full bg-white/5">
                        <motion.div
                          className={`h-full rounded-full ${v.violation_type === "helmet_off" ? "bg-red-500" : "bg-amber-500"}`}
                          initial={{ width: 0 }}
                          animate={{ width: `${v.confidence * 100}%` }}
                          transition={{ duration: 0.6, delay: 0.1 }}
                        />
                      </div>
                      <p className="mt-1 text-[10px] text-slate-500">
                        신뢰도 {(v.confidence * 100).toFixed(0)}%
                      </p>
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
