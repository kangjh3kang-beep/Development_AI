"use client";

import { motion } from "framer-motion";
import { TenantRoutingTable } from "./TenantRoutingTable";
import { useHarnessStore } from "@/store/useHarnessStore";
import { Card, CardContent } from "@propai/ui";

export function HarnessControlDashboard() {
  const { globalStatus, getGlobalMetrics } = useHarnessStore();
  const metrics = getGlobalMetrics();

  const formatNumber = (num: number) => new Intl.NumberFormat('en-US').format(num);

  // 상태 → 토큰 색(하드코딩 색 금지). current(글자색) 기반 발광은 currentColor로 파생.
  const getStatusColor = (status: 'optimal' | 'degraded' | 'critical') => {
    switch (status) {
      case 'optimal': return 'text-[var(--status-success)] border-[var(--status-success)]/20 bg-[color-mix(in_srgb,var(--status-success)_10%,transparent)] shadow-[0_0_30px_color-mix(in_srgb,var(--status-success)_15%,transparent)]';
      case 'degraded': return 'text-[var(--status-warning)] border-[var(--status-warning)]/20 bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] shadow-[0_0_30px_color-mix(in_srgb,var(--status-warning)_15%,transparent)]';
      case 'critical': return 'text-[var(--status-error)] border-[var(--status-error)]/20 bg-[color-mix(in_srgb,var(--status-error)_10%,transparent)] shadow-[0_0_30px_color-mix(in_srgb,var(--status-error)_15%,transparent)]';
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
            <span className="cc-label !text-current opacity-80">Global Matrix Status</span>
            <div className="flex gap-1">
              <div className={`h-2 w-2 rounded-full bg-current ${globalStatus === 'optimal' ? 'animate-bounce' : 'animate-pulse'}`} />
              <div className={`h-2 w-2 rounded-full bg-current ${globalStatus === 'optimal' ? 'animate-bounce delay-75' : 'animate-pulse'}`} />
              <div className={`h-2 w-2 rounded-full bg-current ${globalStatus === 'optimal' ? 'animate-bounce delay-150' : 'animate-pulse'}`} />
            </div>
          </div>
          <div className="mt-6">
            <h3 className="cc-num text-5xl font-[1000] tracking-tighter uppercase">{globalStatus}</h3>
          </div>
          <p className="mt-4 text-[10px] font-bold uppercase tracking-widest opacity-80">System Health Indicator</p>
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-muted)] p-8 shadow-[var(--shadow-lg)] relative overflow-hidden"
        >
          <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-[var(--data-accent-soft)] blur-[40px]" />
          <span className="cc-label">Active Nodes</span>
          <div className="mt-6 flex items-baseline gap-2">
            <h3 className="cc-num text-5xl font-[1000] tracking-tighter text-[var(--text-primary)]">{metrics.activeNodes}</h3>
            <span className="text-sm font-bold text-[var(--text-hint)] uppercase">/ Total Connected</span>
          </div>
          <p className="cc-num mt-4 text-[10px] font-bold text-[var(--status-error)] uppercase tracking-widest">{metrics.suspendedNodes} Nodes Suspended</p>
        </motion.div>

        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="rounded-[2.5rem] border border-[var(--accent-strong)]/20 bg-[var(--accent-soft)] p-8 shadow-[var(--shadow-lg)] relative overflow-hidden"
        >
          <div className="absolute -right-10 -top-10 h-32 w-32 rounded-full bg-[var(--accent-strong)]/10 blur-[40px]" />
          <span className="cc-meta">Aggregated Telemetry</span>
          <div className="mt-6">
            <h3 className="cc-num text-4xl font-[1000] tracking-tighter text-[var(--text-primary)]">{formatNumber(metrics.totalTokens)}</h3>
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
          <span className="cc-live bg-[var(--surface-strong)] px-4 py-2 rounded-xl border border-[var(--line)]">
            <i />Live Sync
          </span>
        </div>
        <TenantRoutingTable />
      </div>

      <div className="grid gap-6 lg:grid-cols-2 mt-4">
         <Card className="cc-bracketed rounded-[3rem] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
            <i className="cc-bracket cc-bracket--tl" />
            <i className="cc-bracket cc-bracket--tr" />
            <i className="cc-bracket cc-bracket--bl" />
            <i className="cc-bracket cc-bracket--br" />
            <CardContent className="p-10 space-y-6">
               <div className="flex items-center justify-between">
                  <h3 className="cc-meta">Access Log Trace</h3>
                  <span className="cc-chip-data">STANDBY</span>
               </div>
               {/* 실시간 접근 로그 스트림 미연동 — 가짜 로그 라인 제거(무목업), 정직 빈상태. */}
               <div className="relative flex h-[200px] flex-col items-center justify-center gap-2 overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-6 text-center">
                 <div className="cc-grid-bg opacity-50" />
                 <div className="cc-scanline" />
                 <span className="relative z-10 cc-num text-xl text-[var(--text-tertiary)]">_</span>
                 <p className="relative z-10 text-[13px] font-bold text-[var(--text-primary)]">접근 로그 스트림 연동 예정</p>
                 <p className="relative z-10 text-[11px] font-medium text-[var(--text-tertiary)] leading-relaxed">
                   실시간 라우팅 접근 로그를 연결하면<br />여기에 인증·라우팅 이벤트가 표시됩니다.
                 </p>
               </div>
            </CardContent>
         </Card>
         <Card className="rounded-[3rem] border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-lg)]">
            <CardContent className="p-10 space-y-8">
               <h3 className="cc-label">Circuit Configuration</h3>
               <div className="space-y-4">
                  {[
                    { label: "Auto-Suspend (Abuse)", status: "Active" },
                    { label: "Token Quota Limiter", status: "Enabled" },
                    { label: "Cross-tenant Isolation", status: "Enforced" },
                  ].map((item, i) => (
                    <div key={i} className="flex items-center justify-between p-4 rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)]">
                       <span className="text-xs font-black uppercase text-[var(--text-primary)]">{item.label}</span>
                       <span className="text-[10px] font-black uppercase tracking-widest text-[var(--status-success)]">[{item.status}]</span>
                    </div>
                  ))}
               </div>
            </CardContent>
         </Card>
      </div>
    </div>
  );
}
