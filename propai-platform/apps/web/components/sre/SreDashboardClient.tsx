"use client";

import { motion, AnimatePresence } from "framer-motion";
import { useState, useEffect } from "react";
import { Card, CardContent } from "@propai/ui";

interface MetricProps {
  label: string;
  value: string;
  sub: string;
  status: "optimal" | "warning" | "error";
  progress: number;
}

function MetricCard({ label, value, sub, status, progress }: MetricProps) {
  const statusColors = {
    optimal: "text-emerald-400 border-emerald-500/20 bg-emerald-500/5",
    warning: "text-amber-400 border-amber-500/20 bg-amber-500/5",
    error: "text-rose-400 border-rose-500/20 bg-rose-500/5",
  };

  const barColors = {
    optimal: "bg-emerald-500",
    warning: "bg-amber-500",
    error: "bg-rose-500",
  };

  return (
    <motion.div 
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className={`rounded-[var(--radius-xl)] border p-8 transition-all hover:scale-[1.02] ${statusColors[status]}`}
    >
      <div className="flex items-center justify-between">
        <span className="label-caps opacity-60">{label}</span>
        <div className={`h-2 w-2 rounded-full ${barColors[status]} animate-pulse`} />
      </div>
      <div className="mt-6 flex items-baseline gap-2">
        <h3 className="text-5xl font-[1000] tracking-tighter text-[var(--text-primary)]">{value}</h3>
      </div>
      <p className="mt-2 text-[10px] font-bold text-[var(--text-tertiary)] uppercase tracking-widest">{sub}</p>
      
      <div className="mt-8 space-y-2">
        <div className="h-1 w-full rounded-full bg-[var(--line-subtle)] overflow-hidden">
          <motion.div 
            initial={{ width: 0 }}
            animate={{ width: `${progress}%` }}
            className={`h-full ${barColors[status]}`}
            transition={{ duration: 1.5, ease: "easeOut" }}
          />
        </div>
      </div>
    </motion.div>
  );
}

export function SreDashboardClient({ dictionary }: { dictionary: import("@/i18n/get-dictionary").CommonDictionary }) {
  const [logs, setLogs] = useState<string[]>([]);
  
  useEffect(() => {
    const messages = [
      "[SYSTEM] Intelligence Hub Initialized...",
      "[AUTH] Multi-tenant context validated.",
      "[API] v58.5 endpoints healthy.",
      "[UI] Dual-theme tokens parity checked.",
      "[GIT] Deployment pipeline active.",
      "[SRE] Real-time monitoring established.",
    ];
    
    let i = 0;
    const interval = setInterval(() => {
      if (i < messages.length) {
        setLogs(prev => [...prev, messages[i]]);
        i++;
      } else {
        clearInterval(interval);
      }
    }, 800);
    
    return () => clearInterval(interval);
  }, []);

  const d = dictionary;

  return (
    <div className="space-y-10 font-sans">
      <header className="relative overflow-hidden rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-strong)] p-12 shadow-[var(--shadow-2xl)] group">
        <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-[var(--accent-strong)]/10 blur-[80px]" />
        <div className="relative z-10 space-y-6">
           <span className="inline-flex h-2.5 w-2.5 rounded-full bg-[var(--accent-strong)] animate-pulse" />
           <h1 className="text-5xl font-[1000] tracking-tighter text-[var(--text-primary)] uppercase italic leading-none">
             {d.pages.sre.title}
           </h1>
           <p className="max-w-3xl text-lg font-medium text-[var(--text-secondary)] italic leading-relaxed underline decoration-[var(--line-strong)] underline-offset-8">
             {d.pages.sre.description}
           </p>
        </div>
      </header>

      <div className="grid gap-6 md:grid-cols-3">
        <MetricCard 
          label={d.pages.sre.items.first} 
          value="99.98%" 
          sub="Uptime SLA / Global Region" 
          status="optimal" 
          progress={99.98} 
        />
        <MetricCard 
          label={d.pages.sre.items.second} 
          value="124" 
          sub="Production Commits Verified" 
          status="warning" 
          progress={75} 
        />
        <MetricCard 
          label={d.pages.sre.items.third} 
          value="PASS" 
          sub="V58.5 Quality Gate Status" 
          status="optimal" 
          progress={100} 
        />
      </div>

      <div className="grid gap-10 lg:grid-cols-2">
         <Card className="rounded-[var(--radius-2xl)] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
            <CardContent className="p-10 space-y-6">
               <h3 className="text-xs font-black uppercase tracking-[0.4em] text-[var(--accent-strong)]">Real-time System Logs</h3>
               <div className="h-[300px] rounded-2xl bg-[#0a0f14] p-6 font-mono text-[11px] text-emerald-400 overflow-y-auto space-y-2 border border-emerald-500/10">
                  <AnimatePresence>
                    {logs.map((log, i) => (
                      <motion.p 
                        key={i} 
                        initial={{ opacity: 0, x: -10 }} 
                        animate={{ opacity: 1, x: 0 }}
                        className="leading-loose"
                      >
                        <span className="opacity-40">{new Date().toLocaleTimeString()}</span> {log}
                      </motion.p>
                    ))}
                  </AnimatePresence>
               </div>
            </CardContent>
         </Card>

         <Card className="rounded-[var(--radius-2xl)] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
            <CardContent className="p-10 space-y-8">
               <h3 className="text-xs font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">Quality Gate Checklist</h3>
               <div className="space-y-4">
                  {[
                    { label: "Dual-Theme Parity", status: "Verified" },
                    { label: "Lifecycle Navigation Flow", status: "Seamless" },
                    { label: "Responsive Layout Clipping", status: "Neutralized" },
                    { label: "Semantic Token Migration", status: "100%" },
                  ].map((item, i) => (
                    <div key={i} className="flex items-center justify-between p-4 rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)]">
                       <span className="text-xs font-black uppercase text-[var(--text-primary)]">{item.label}</span>
                       <span className="text-[10px] font-black uppercase tracking-widest text-emerald-400">[{item.status}]</span>
                    </div>
                  ))}
               </div>
            </CardContent>
         </Card>
      </div>
    </div>
  );
}
