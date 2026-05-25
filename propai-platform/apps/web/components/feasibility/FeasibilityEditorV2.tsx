"use client";

import { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useFeasibilityV2Store } from "@/store/use-feasibility-v2-store";
import { ProjectTypeSelector } from "./ProjectTypeSelector";
import { ModuleInputForm } from "./ModuleInputForm";
import { FeasibilityResultView } from "./FeasibilityResultView";
import { MonteCarloPanel } from "./MonteCarloPanel";
import { VersionHistoryView } from "./VersionHistoryView";
import { AIRecommendationPanel } from "./AIRecommendationPanel";
import { ExcelExportButton } from "./ExcelExportButton";

interface Props {
  projectId: string;
}

const TABS = [
  { key: "input" as const, label: "Intelligence Input", icon: "⌨️" },
  { key: "result" as const, label: "Analysis Report", icon: "📊" },
  { key: "montecarlo" as const, label: "Risk Simulation", icon: "🎲" },
  { key: "version" as const, label: "History Ledger", icon: "📜" },
] as const;

export function FeasibilityEditorV2({ projectId }: Props) {
  const {
    activeTab,
    setActiveTab,
    result,
    isCalculating,
    error,
    fetchModules,
    fetchCommitLog,
  } = useFeasibilityV2Store();

  useEffect(() => {
    fetchModules();
    fetchCommitLog(projectId);
  }, [fetchModules, fetchCommitLog, projectId]);

  return (
    <div className="flex flex-col gap-10">
      {/* ── High-Fidelity Tab Navigation ── */}
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between px-2">
        <div className="flex items-center gap-2 rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-1.5 backdrop-blur-xl shadow-[var(--shadow-xl)]">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`relative flex items-center gap-3 rounded-full px-6 py-3 text-[11px] font-[1000] uppercase tracking-widest transition-all ${
                activeTab === tab.key
                  ? "text-white"
                  : "text-[var(--text-hint)] hover:text-[var(--text-secondary)] hover:bg-[var(--line)]/5"
              }`}
            >
              {activeTab === tab.key && (
                <motion.div
                  layoutId="activeTabFeasibility"
                  className="absolute inset-0 rounded-full bg-[var(--accent-strong)] shadow-[var(--shadow-glow)]"
                  transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                />
              )}
              <span className="relative z-10">{tab.icon}</span>
              <span className="relative z-10">{tab.label}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-4">
          <AnimatePresence mode="wait">
            {isCalculating && (
              <motion.div 
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="flex items-center gap-3 rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-5 py-2.5 text-[10px] font-black uppercase tracking-widest text-[var(--accent-strong)] backdrop-blur-md"
              >
                <div className="h-2.5 w-2.5 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
                Processing Engine...
              </motion.div>
            )}
          </AnimatePresence>
          {result && <ExcelExportButton />}
        </div>
      </div>

      {/* ── Status Messages ── */}
      <AnimatePresence>
        {error && (
          <motion.div 
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            className="rounded-[2rem] border border-rose-500/20 bg-rose-500/10 p-6 text-sm font-bold text-rose-400 backdrop-blur-3xl shadow-2xl flex items-center gap-4"
          >
            <div className="h-10 w-10 rounded-2xl bg-rose-500/20 flex items-center justify-center text-rose-400">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
            </div>
            {error}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Studio Content Area ── */}
      <div className="relative min-h-[600px]">
        <AnimatePresence mode="wait">
          {activeTab === "input" && (
            <motion.div
              key="input"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -30, filter: "blur(10px)" }}
              className="grid gap-10 lg:grid-cols-[340px_1fr]"
            >
              <div className="space-y-6">
                 <div className="glass rounded-[2.5rem] p-8 border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)]">
                    <p className="text-[10px] font-[1000] uppercase tracking-[0.4em] text-[var(--text-hint)] mb-6">Execution Strategy</p>
                    <ProjectTypeSelector />
                 </div>
              </div>
              <div className="glass rounded-[3rem] p-1 border border-[var(--line)] bg-[var(--surface-soft)] overflow-hidden shadow-[var(--shadow-xl)]">
                 <div className="rounded-[3rem] p-10 bg-[var(--surface-strong)] backdrop-blur-3xl">
                    <ModuleInputForm />
                 </div>
              </div>
            </motion.div>
          )}

          {activeTab === "result" && (
            <motion.div
              key="result"
              initial={{ opacity: 0, y: 30 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -30, filter: "blur(10px)" }}
              className="space-y-10"
            >
              <FeasibilityResultView />
              <div className="glass rounded-[3rem] p-1 border border-[var(--line)] bg-[var(--surface-soft)] overflow-hidden shadow-[var(--shadow-xl)]">
                <div className="rounded-[3rem] p-12 bg-[var(--surface-strong)] backdrop-blur-3xl">
                  <AIRecommendationPanel />
                </div>
              </div>
            </motion.div>
          )}

          {activeTab === "montecarlo" && (
            <motion.div
              key="montecarlo"
              initial={{ opacity: 0, scale: 0.98 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.98, filter: "blur(10px)" }}
            >
              <MonteCarloPanel />
            </motion.div>
          )}

          {activeTab === "version" && (
            <motion.div
              key="version"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <VersionHistoryView projectId={projectId} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
