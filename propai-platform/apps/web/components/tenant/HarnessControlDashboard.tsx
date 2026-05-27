"use client";

import { motion } from "framer-motion";
import { TenantRoutingTable } from "./TenantRoutingTable";
import { useHarnessStore } from "@/store/useHarnessStore";
import { Card, CardContent } from "@propai/ui";

export function HarnessControlDashboard() {
  const { globalStatus, getGlobalMetrics } = useHarnessStore();
  const metrics = getGlobalMetrics();

  const formatNumber = (num: number) => new Intl.NumberFormat('en-US').format(num);

  const getStatusColor = (status: 'optimal' | 'degraded' | 'critical') => {
    switch (status) {
      case 'optimal': return 'text-emerald-400 border-emerald-500/20 bg-emerald-500/10 shadow-[0_0_30px_rgba(16,185,129,0.15)]';
      case 'degraded': return 'text-amber-400 border-amber-500/20 bg-amber-500/10 shadow-[0_0_30px_rgba(245,158,11,0.15)]';
      case 'critical': return 'text-rose-400 border-rose-500/20 bg-rose-500/10 shadow-[0_0_30px_rgba(244,63,94,0.15)]';
    }
  };

  return (
    <div className="flex flex-col gap-10 pb-20 max-w-7xl mx-auto font-sans">
      <div className="space-y-4">
        <h1 className="text-4xl lg:text-5xl font-[900] tracking-tighter text-[var(--text-primary)] uppercase italic">
          Super Admin Harness <span className="text-[var(--accent-strong)] animate-pulse">_</span>
        </h1>
        <p className="text-[var(--text-secondary)] font-medium max-w-3xl text-lg leading-relaxed">
          시스템 전체의 라우팅 매트릭스를 제어하고 서킷 브레이커를 통해 비정상 트래픽을 물리적으로 차단합니다.
        </p>
      </div>

      {/* Global Telemetry Dashboard */}
      <div className="grid gap-6 md:grid-cols-3">
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className={`rounded-[2.5rem] border p-8 transition-all relative overflow-hidden group ${getStatusColor(globalStatus)}`}
        >
          <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-current opacity-20 blur-[40px] group-hover:opacity-30 transition-opacity" />
          <div className="flex items-center justify-between relative z-10">
            <span className="text-[10px] font-black uppercase tracking-[0.2em] opacity-80">Global Matrix Status</span>
            <div className="flex gap-1">
              <div className={`h-2 w-2 rounded-full bg-current ${globalStatus === 'optimal' ? 'animate-bounce' : 'animate-pulse'}`} />
              <div className={`h-2 w-2 rounded-full bg-current ${globalStatus === 'optimal' ? 'animate-bounce delay-75' : 'animate-pulse'}`} />
              <div className={`h-2 w-2 rounded-full bg-current ${globalStatus === 'optimal' ? 'animate-bounce delay-150' : 'animate-pulse'}`} />
            </div>
          </div>
          <div className="mt-6">
            <h3 className="text-5xl font-[1000] tracking-tighter uppercase">{globalStatus}</h3>
          </div>
          <p className="mt-4 text-[10px] font-bold uppercase tracking-widest opacity-80">System Health Indicator</p>
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-muted)] p-8 shadow-[var(--shadow-lg)] relative overflow-hidden"
        >
          <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-blue-500/10 blur-[40px]" />
          <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-tertiary)]">Active Nodes</span>
          <div className="mt-6 flex items-baseline gap-2">
            <h3 className="text-5xl font-[1000] tracking-tighter text-[var(--text-primary)]">{metrics.activeNodes}</h3>
            <span className="text-sm font-bold text-[var(--text-hint)] uppercase">/ Total Connected</span>
          </div>
          <p className="mt-4 text-[10px] font-bold text-rose-400 uppercase tracking-widest">{metrics.suspendedNodes} Nodes Suspended</p>
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-[2.5rem] border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)] p-8 shadow-[0_0_30px_rgba(45,212,191,0.05)] relative overflow-hidden"
        >
          <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-[var(--accent-strong)]/10 blur-[40px]" />
          <span className="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--accent-strong)]">Aggregated Telemetry</span>
          <div className="mt-6">
            <h3 className="text-4xl font-[1000] tracking-tighter text-[var(--text-primary)]">{formatNumber(metrics.totalTokens)}</h3>
          </div>
          <p className="mt-4 text-[10px] font-bold text-[var(--text-tertiary)] uppercase tracking-widest">Total AI Tokens Routed</p>
        </motion.div>
      </div>

      {/* Main Routing Matrix Table */}
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-2xl font-black tracking-tighter text-[var(--text-primary)] uppercase flex items-center gap-3">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-[var(--accent-strong)]"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/></svg>
            Routing Control Matrix
          </h2>
          <span className="text-xs font-mono font-bold text-[var(--text-tertiary)] uppercase tracking-widest bg-[var(--surface-strong)] px-4 py-2 rounded-xl border border-[var(--line)]">
            Live Sync: Connected
          </span>
        </div>
        <TenantRoutingTable />
      </div>

      <div className="grid gap-6 lg:grid-cols-2 mt-4">
         <Card className="rounded-[3rem] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
            <CardContent className="p-10 space-y-6">
               <h3 className="text-xs font-black uppercase tracking-[0.4em] text-[var(--accent-strong)]">Access Log Trace</h3>
               <div className="h-[200px] rounded-2xl bg-[#0a0f14] p-6 font-mono text-[11px] text-emerald-400 overflow-y-auto space-y-2 border border-emerald-500/10">
                 <p className="opacity-70">&gt; Securing global data bus...</p>
                 <p className="opacity-70">&gt; Validating super admin token...</p>
                 <p className="text-emerald-300 font-bold">&gt; AUTH_SUCCESS: Permission L3 Granted.</p>
                 <p className="opacity-70">&gt; Routing table loaded. 5 Nodes detected.</p>
                 <p className="opacity-70 text-amber-400">&gt; WARNING: Node 'Weyland-Yutani' reaching token capacity.</p>
                 <p className="animate-pulse">_</p>
               </div>
            </CardContent>
         </Card>
         <Card className="rounded-[3rem] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
            <CardContent className="p-10 space-y-8">
               <h3 className="text-xs font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">Circuit Configuration</h3>
               <div className="space-y-4">
                  {[
                    { label: "Auto-Suspend (Abuse)", status: "Active" },
                    { label: "Token Quota Limiter", status: "Enabled" },
                    { label: "Cross-tenant Isolation", status: "Enforced" },
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
