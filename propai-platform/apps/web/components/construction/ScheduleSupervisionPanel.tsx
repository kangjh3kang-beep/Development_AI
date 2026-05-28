"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
export function ScheduleSupervisionPanel({ projectId, dictionary }: { projectId: string; dictionary: Record<string, string> }) {
  const [isMounted, setIsMounted] = useState(false);
  const t = dictionary;

  const [tasks, setTasks] = useState<Array<{ task: string; dur: number; complete: boolean; color: string }>>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!isMounted) return;
    async function fetchSchedule() {
      try {
        const res = await apiClient.get<{ tasks: Array<{ task: string; dur: number; complete: boolean }> }>(`/projects/${projectId}/construction/schedule`);
        if (res && res.tasks) {
          const coloredTasks = res.tasks.map((task, i: number) => ({
             ...task,
             color: ["var(--accent-strong)", "var(--info)", "var(--success)", "var(--warning)"][i % 4]
          }));
          setTasks(coloredTasks);
        }
      } catch (err) {
        console.error("Failed to load schedule data", err);
      } finally {
        setLoading(false);
      }
    }
    fetchSchedule();
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
             {t.description || "실시간 공정률 추적 및 AI 기반 자동 감리 로그 시스템입니다."}
          </p>
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
              ) : tasks.map((task, i) => (
                 <motion.div 
                   key={i} 
                   initial={{ opacity: 0, scale: 0.95 }}
                   animate={{ opacity: 1, scale: 1 }}
                   transition={{ delay: i * 0.1 }}
                   className="group flex items-center gap-8 text-[11px] font-black uppercase tracking-widest"
                 >
                    <div className="w-40 truncate text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors italic">{task.task}</div>
                    <div className="relative h-10 flex-1 rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)] overflow-hidden group-hover:border-[var(--accent-strong)]/30 transition-colors">
                       <motion.div 
                          initial={{ width: 0 }}
                          animate={{ width: `${task.dur}%` }}
                          transition={{ duration: 1, delay: 0.5 + i * 0.1, ease: "circOut" }}
                          className="absolute top-0 h-full rounded-2xl shadow-[var(--shadow-glow)] transition-all" 
                          style={{ left: `${i * 12}%`, backgroundColor: task.color, opacity: task.complete ? 0.3 : 1 }}
                       >
                          <div className="absolute inset-0 bg-white/10" />
                       </motion.div>
                    </div>
                 </motion.div>
              ))}
           </div>
        </motion.div>

        {/* AI Supervision Area */}
        <motion.div 
          initial={{ opacity: 0, x: 20 }}
          animate={{ opacity: 1, x: 0 }}
          className="flex flex-col gap-6 rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 shadow-[var(--shadow-2xl)] backdrop-blur-3xl"
        >
           <h5 className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">
             {t.inspectionTitle || "REAL-TIME AI SUPERVISION"}
           </h5>
           <div className="mt-4 flex flex-col gap-4">
              {[
                { title: "기초 철근 배근 검사", status: t.statusApproved || "승인 완료", time: "2시간 전", color: "var(--success)" },
                { title: "콘크리트 타설 품질 점검", status: t.statusAlert || "주의 요망", time: "진행 중", color: "var(--spot)" },
                { title: "안전망 설치 확인", status: t.statusPending || "검토 대기", time: "어제", color: "var(--warning)" },
              ].map((insp, i) => (
                 <motion.div 
                   key={i} 
                   whileHover={{ scale: 1.02, x: 5 }}
                   className="flex flex-col gap-3 rounded-[2rem] bg-[var(--surface-soft)] p-6 shadow-[var(--shadow-sm)] border border-[var(--line)] transition-all hover:bg-[var(--surface)] group/insp"
                 >
                    <div className="flex items-center justify-between">
                       <p className="font-black text-sm text-[var(--text-primary)] tracking-tight">{insp.title}</p>
                       <span className="text-[9px] font-black text-[var(--text-hint)] uppercase tracking-widest italic">{insp.time}</span>
                    </div>
                    <div className="flex items-center gap-3">
                       <div className="h-1.5 w-1.5 rounded-full animate-pulse shadow-[0_0_10px_currentColor]" style={{ backgroundColor: insp.color, color: insp.color }} />
                       <span className="text-[10px] font-[1000] uppercase tracking-[0.2em] italic" style={{ color: insp.color }}>
                          {insp.status}
                       </span>
                    </div>
                 </motion.div>
              ))}
           </div>
           
           <div className="mt-auto rounded-2xl bg-[var(--accent-soft)] p-6 border border-[var(--accent-strong)]/10 italic">
              <p className="text-[9px] font-black text-[var(--accent-strong)] uppercase tracking-widest mb-2">AI 지시사항</p>
              <p className="text-[11px] font-bold text-[var(--text-secondary)] leading-relaxed underline decoration-[var(--accent-strong)]/20 underline-offset-4">
                "C동 4층 슬라브 타설 전 철근 간격 보완이 필요합니다. 공정에 영향을 미치지 않도록 즉시 조치를 권고합니다."
              </p>
           </div>
        </motion.div>
      </div>
    </div>
  );
}
