"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { apiClient } from "@/lib/api-client";

export function ScheduleSupervisionPanel({ projectId, dictionary }: { projectId: string; dictionary: Record<string, string> }) {
  const [isMounted, setIsMounted] = useState(false);
  const t = dictionary;

  const [tasks, setTasks] = useState<Array<{ task: string; dur: number; dur_months?: number; start?: string; complete: boolean; color: string }>>([]);
  const [totalMonths, setTotalMonths] = useState<number | null>(null);
  const [method, setMethod] = useState<string>("");
  const [estimated, setEstimated] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!isMounted) return;
    let cancelled = false;
    async function fetchSchedule() {
      try {
        const res = await apiClient.get<{ tasks: Array<{ task: string; dur: number; dur_months?: number; start?: string; complete: boolean }>; total_months?: number; method?: string; estimated?: boolean }>(`/projects/${projectId}/construction/schedule`);
        if (cancelled) return;
        if (res && res.tasks) {
          const coloredTasks = (res.tasks ?? []).map((task, i: number) => ({
             ...task,
             color: ["var(--accent-strong)", "var(--status-info)", "var(--status-success)", "var(--status-warning)"][i % 4]
          }));
          setTasks(coloredTasks);
          setTotalMonths(res.total_months ?? null);
          setMethod(res.method ?? "");
          setEstimated(!!res.estimated);
        }
      } catch (err) {
        if (!cancelled) console.error("Failed to load schedule data", err);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    fetchSchedule();
    return () => { cancelled = true; };
  }, [projectId, isMounted]);

  if (!isMounted) return <div className="p-8 text-center text-sm font-bold animate-pulse text-[var(--text-tertiary)] italic uppercase tracking-widest">Initializing Scheduler...</div>;

  return (
    <div className="flex flex-col gap-10">
      <div className="flex items-end justify-between px-2">
        <div className="space-y-4">
          <div className="flex items-center gap-3">
             <div className="h-2 w-10 rounded-full bg-[var(--accent-strong)]" />
             <h4 className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)] uppercase">{t.title || "AI 공정 및 감리 센터"}</h4>
          </div>
          <p className="max-w-2xl text-sm font-medium leading-relaxed text-[var(--text-secondary)] italic underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
             {t.description || "프로젝트 규모(연면적·층수) 기반 공정(공기) 추정 및 공종별 일정입니다."}
          </p>
          <div className="flex flex-wrap items-center gap-2">
            {estimated && (
              <span className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">추정(표준공기 기반) — 실 공정관리 엔진 도입 시 정밀화</span>
            )}
            {totalMonths != null && totalMonths > 0 && (
              <span className="rounded bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-bold text-[var(--accent-strong)]">총 예상 공기 {totalMonths}개월</span>
            )}
          </div>
        </div>
      </div>

      <div className="grid gap-8 xl:grid-cols-[1fr_400px]">
        {/* Gantt Chart Area */}
        <motion.div 
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex min-h-[450px] flex-col rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 shadow-[var(--shadow-2xl)] backdrop-blur-3xl"
        >
           <div className="mb-10 flex items-center justify-between">
              <h5 className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">
                {t.ganttTitle || "PROJECT GANTT TIMELINE"}
              </h5>
              <div className="flex items-center gap-4">
                <span className="h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse" />
                <span className="text-[9px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">AI Optimized</span>
              </div>
           </div>
           
           <div className="flex flex-1 flex-col gap-6">
              {loading ? (
                <div className="flex flex-1 items-center justify-center py-4 text-center text-[10px] font-black uppercase tracking-[0.5em] animate-pulse text-[var(--text-hint)] italic border border-dashed border-[var(--line-strong)] rounded-[2.5rem]">
                  Ochestrating Timelines...
                </div>
              ) : tasks.length === 0 ? (
                <div className="flex flex-1 items-center justify-center py-4 text-center text-[10px] font-bold tracking-widest text-[var(--text-secondary)] italic border border-dashed border-[var(--line-strong)] rounded-[2.5rem] p-6">
                  건축개요(연면적·층수)가 없어 공정을 추정할 수 없습니다. 부지/설계 분석을 먼저 진행하세요.
                </div>
              ) : tasks.map((task, i) => {
                 // 누적 시작 비율(이전 공종 dur 합) — 막대 위치를 공정 순서대로 배치
                 const startPct = tasks.slice(0, i).reduce((s, tk) => s + (tk.dur ?? 0), 0);
                 return (
                 <motion.div
                   key={i}
                   initial={{ opacity: 0, scale: 0.95 }}
                   animate={{ opacity: 1, scale: 1 }}
                   transition={{ delay: i * 0.1 }}
                   className="group flex items-center gap-8 text-[11px] font-black uppercase tracking-widest"
                 >
                    <div className="w-44 shrink-0 text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors italic">
                      <span className="block truncate">{task.task}</span>
                      {task.dur_months != null && <span className="block text-[9px] font-bold text-[var(--text-hint)] normal-case">{task.start} · {task.dur_months}개월</span>}
                    </div>
                    <div className="relative h-10 flex-1 rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)] overflow-hidden group-hover:border-[var(--accent-strong)]/30 transition-colors">
                       <motion.div
                          initial={{ width: 0 }}
                          animate={{ width: `${task.dur}%` }}
                          transition={{ duration: 1, delay: 0.5 + i * 0.1, ease: "circOut" }}
                          className="absolute top-0 h-full rounded-2xl shadow-[var(--shadow-glow)] transition-all"
                          style={{ left: `${Math.min(95, startPct)}%`, backgroundColor: task.color, opacity: task.complete ? 0.3 : 1 }}
                       >
                          <div className="absolute inset-0 bg-white/10" />
                       </motion.div>
                    </div>
                 </motion.div>
                 );
              })}
           </div>
        </motion.div>

        {/* AI Supervision Area */}
        <motion.div 
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex flex-col gap-6 rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 shadow-[var(--shadow-2xl)] backdrop-blur-3xl"
        >
           <h5 className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">
             {t.inspectionTitle || "공종별 공기 분배"}
           </h5>
           <div className="mt-4 flex flex-col gap-4">
              {tasks.length === 0 ? (
                <p className="rounded-[2rem] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-6 text-center text-[11px] font-bold text-[var(--text-secondary)] italic">공정 추정 데이터 없음</p>
              ) : tasks.map((task, i) => (
                 <motion.div
                   key={i}
                   whileHover={{ scale: 1.02, x: 5 }}
                   className="flex flex-col gap-3 rounded-[2rem] bg-[var(--surface-soft)] p-6 shadow-[var(--shadow-sm)] border border-[var(--line)] transition-all hover:bg-[var(--surface)]"
                 >
                    <div className="flex items-center justify-between">
                       <p className="font-black text-sm text-[var(--text-primary)] tracking-tight">{task.task}</p>
                       <span className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest italic">{task.start}</span>
                    </div>
                    <div className="flex items-center gap-3">
                       <div className="h-1.5 w-1.5 rounded-full shadow-[0_0_10px_currentColor]" style={{ backgroundColor: task.color, color: task.color }} />
                       <span className="text-[10px] font-[1000] uppercase tracking-[0.2em] italic" style={{ color: task.color }}>
                          {task.dur_months != null ? `${task.dur_months}개월` : `${task.dur}%`}
                       </span>
                    </div>
                 </motion.div>
              ))}
           </div>

           {method && (
             <div className="mt-auto rounded-2xl bg-[var(--accent-soft)] p-6 border border-[var(--accent-strong)]/10 italic">
                <p className="text-[9px] font-black text-[var(--accent-strong)] uppercase tracking-widest mb-2">산출 방식</p>
                <p className="text-[11px] font-bold text-[var(--text-secondary)] leading-relaxed">
                  {method}
                </p>
             </div>
           )}
        </motion.div>
      </div>
    </div>
  );
}
