"use client";

import React, { useEffect, useRef } from "react";
import { motion } from "framer-motion";
import { useGenerationStore } from "@/store/useGenerationStore";
import type { CommonDictionary } from "@/i18n/get-dictionary";

interface GenerationMonitorConsoleProps {
  dictionary: CommonDictionary;
}

export function GenerationMonitorConsole({ dictionary }: GenerationMonitorConsoleProps) {
  const t = dictionary.pages.generation;
  const { steps, isGenerating, status, results } = useGenerationStore();
  const terminalScrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll terminal log to bottom — 컨테이너 내부 스크롤만 조정(전역 스크롤 점프 금지).
  // scrollIntoView는 페이지 전체를 하단으로 점프시키므로 컨테이너 scrollTop만 갱신한다.
  useEffect(() => {
    if (isGenerating && terminalScrollRef.current) {
      const el = terminalScrollRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [steps, isGenerating]);

  // Extract all compiled logs
  const logs = steps
    .filter((s) => s.status !== "idle")
    .map((s) => ({
      id: s.stepId,
      name: s.name,
      log: s.logMessage || "Awaiting telemetry hook...",
      status: s.status,
    }));

  return (
    <div className="flex flex-col gap-6">
      {/* ── Console Header ── */}
      <div className="flex items-center justify-between border-b border-[var(--line-strong)]/40 pb-4">
        <div className="flex items-center gap-3">
          <span className="flex h-2.5 w-2.5 rounded-full bg-[var(--accent-strong)] animate-pulse shadow-[var(--shadow-glow)]" />
          <h4 className="text-xs font-black uppercase tracking-[0.25em] text-[var(--text-primary)]">
            {t.terminalTitle}
          </h4>
        </div>
        <span className="text-[10px] font-mono text-[var(--text-hint)] uppercase">
          Status: <span className={isGenerating ? "text-amber-500 font-bold" : "text-emerald-500 font-bold"}>
            {isGenerating ? "WIRING_ENGINE" : "ONLINE"}
          </span>
        </span>
      </div>

      {/* ── Terminal Emulator ── */}
      <div className="relative rounded-[2rem] border border-[var(--line-strong)] bg-neutral-950 p-6 shadow-2xl">
        <div className="absolute top-4 right-6 flex items-center gap-1.5 opacity-60">
          <span className="h-2 w-2 rounded-full bg-red-500/80" />
          <span className="h-2 w-2 rounded-full bg-amber-500/80" />
          <span className="h-2 w-2 rounded-full bg-emerald-500/80" />
        </div>

        <div ref={terminalScrollRef} className="h-[280px] overflow-y-auto font-mono text-[11px] leading-relaxed text-emerald-400/90 space-y-3.5 scrollbar-thin scrollbar-thumb-neutral-800">
          {logs.length === 0 ? (
            <div className="flex h-full items-center justify-center text-[var(--text-hint)] italic select-none">
              {t.terminalReady}
            </div>
          ) : (
            <>
              {logs.map((log, index) => {
                const isRunning = log.status === "running";
                const isCompleted = log.status === "completed";
                const isFailed = log.status === "failed";

                return (
                  <motion.div
                    key={log.id}
                    initial={{ opacity: 0, x: -10 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex flex-col gap-1 border-l-2 border-emerald-500/20 pl-3.5"
                  >
                    <div className="flex items-center gap-2">
                      <span className={`text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-md ${
                        isCompleted ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" :
                        isRunning ? "bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse" :
                        "bg-red-500/10 text-red-400 border border-red-500/20"
                      }`}>
                        {log.status}
                      </span>
                      <span className="text-neutral-400 font-bold">{log.name}</span>
                    </div>
                    <div className="text-neutral-300/80 font-mono whitespace-pre-wrap">
                      $ {log.log}
                    </div>
                  </motion.div>
                );
              })}
            </>
          )}
        </div>
      </div>

      {/* ── Active Module Progress Dashboard ── */}
      {isGenerating && (
        <div className="grid gap-4.5 rounded-[2rem] border border-[var(--line-strong)] bg-[var(--surface-strong)]/40 p-6 backdrop-blur-3xl">
          <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
            {t.activeEngine} Pipeline
          </p>

          <div className="space-y-4">
            {steps.map((step) => {
              const isRunning = step.status === "running";
              const isCompleted = step.status === "completed";
              
              return (
                <div key={step.stepId} className="flex flex-col gap-1.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className={`font-bold transition-colors ${
                      isCompleted ? "text-[var(--text-primary)]" :
                      isRunning ? "text-[var(--accent-strong)] animate-pulse" : "text-[var(--text-hint)]"
                    }`}>
                      {step.name}
                    </span>
                    <span className="font-mono text-[10px] text-[var(--text-hint)]">
                      {step.progress}%
                    </span>
                  </div>

                  {/* Progressive Bar */}
                  <div className="relative h-1.5 w-full rounded-full bg-[var(--line-strong)]/20 overflow-hidden">
                    <motion.div
                      className={`h-full rounded-full ${
                        isCompleted ? "bg-[var(--text-primary)]" : "bg-[var(--accent-strong)]"
                      }`}
                      initial={{ width: 0 }}
                      animate={{ width: `${step.progress}%` }}
                      transition={{ duration: 0.4, ease: "easeOut" }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
