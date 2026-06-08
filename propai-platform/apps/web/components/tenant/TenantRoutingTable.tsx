"use client";

import { motion } from "framer-motion";
import { useHarnessStore, TenantNode, TenantStatus, UserRole } from "@/store/useHarnessStore";

export function TenantRoutingTable() {
  const { nodes, toggleNodeStatus, updateNodeRole } = useHarnessStore();

  // 라우팅 상태 → 토큰 색(하드코딩 색 금지). 발광은 color-mix로 동일 상태색에서 파생.
  const getStatusColor = (status: TenantStatus) => {
    switch (status) {
      case 'active': return 'text-[var(--status-success)] bg-[color-mix(in_srgb,var(--status-success)_10%,transparent)] border-[var(--status-success)]/20 shadow-[0_0_10px_color-mix(in_srgb,var(--status-success)_20%,transparent)]';
      case 'throttled': return 'text-[var(--status-warning)] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] border-[var(--status-warning)]/20 shadow-[0_0_10px_color-mix(in_srgb,var(--status-warning)_20%,transparent)]';
      case 'suspended': return 'text-[var(--status-error)] bg-[color-mix(in_srgb,var(--status-error)_10%,transparent)] border-[var(--status-error)]/20 shadow-[0_0_10px_color-mix(in_srgb,var(--status-error)_20%,transparent)]';
    }
  };

  const formatTokens = (tokens: number) => {
    return new Intl.NumberFormat('en-US', { notation: "compact", compactDisplay: "short" }).format(tokens);
  };

  return (
    <div className="w-full overflow-hidden rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-muted)]/50 backdrop-blur-xl shadow-[var(--shadow-xl)]">
      <div className="overflow-x-auto custom-scrollbar">
        <table className="w-full text-left text-sm text-[var(--text-secondary)]">
          <thead className="bg-[var(--surface-strong)] text-xs uppercase tracking-[0.2em] text-[var(--text-tertiary)] border-b border-[var(--line-strong)]">
            <tr>
              <th className="px-8 py-6 font-black">Node ID / Tenant Name</th>
              <th className="px-8 py-6 font-black">Routing Status</th>
              <th className="px-8 py-6 font-black">Assigned Capacity</th>
              <th className="px-8 py-6 font-black">Telemetry (Tokens)</th>
              <th className="px-8 py-6 font-black text-right">Circuit Breaker</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--line)]">
            {nodes.map((node: TenantNode, idx) => (
              <motion.tr 
                key={node.id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: idx * 0.1 }}
                className="hover:bg-[var(--surface-soft)] transition-colors group"
              >
                <td className="px-8 py-6">
                  <div className="flex flex-col">
                    <span className="font-bold text-[var(--text-primary)] tracking-wide">{node.name}</span>
                    <span className="cc-num text-[10px] text-[var(--text-hint)] uppercase tracking-widest">{node.id}</span>
                  </div>
                </td>
                <td className="px-8 py-6">
                  <div className={`inline-flex items-center gap-2 rounded-full border px-3 py-1 ${getStatusColor(node.status)}`}>
                    <div className={`h-1.5 w-1.5 rounded-full ${node.status === 'active' ? 'bg-[var(--status-success)] animate-pulse' : node.status === 'throttled' ? 'bg-[var(--status-warning)]' : 'bg-[var(--status-error)]'}`} />
                    <span className="text-[10px] font-bold uppercase tracking-widest">{node.status}</span>
                  </div>
                </td>
                <td className="px-8 py-6">
                  <div className="flex flex-col gap-1">
                    <select 
                      value={node.role}
                      onChange={(e) => updateNodeRole(node.id, e.target.value as UserRole)}
                      className="bg-transparent text-[11px] font-bold uppercase tracking-widest text-[var(--text-primary)] border-b border-[var(--line-strong)] focus:outline-none focus:border-[var(--accent-strong)] cursor-pointer appearance-none"
                    >
                      <option value="super_admin">Super Admin (L3)</option>
                      <option value="tenant_admin">Tenant Admin (L2)</option>
                      <option value="user">Standard User (L1)</option>
                    </select>
                    <span className="text-[10px] text-[var(--accent-strong)] uppercase tracking-widest opacity-80">{node.aiModel}</span>
                  </div>
                </td>
                <td className="px-8 py-6">
                  <div className="flex flex-col">
                    <span className="cc-num text-sm text-[var(--text-primary)] font-bold">{formatTokens(node.tokenUsage)}</span>
                    <span className="text-[10px] text-[var(--text-hint)] uppercase tracking-widest">Last ping: {node.lastActive}</span>
                  </div>
                </td>
                <td className="px-8 py-6 text-right space-x-2">
                  <button 
                    onClick={() => toggleNodeStatus(node.id, node.status === 'active' ? 'throttled' : 'active')}
                    className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${
                      node.status === 'throttled' 
                        ? 'bg-[var(--accent-strong)] text-white shadow-[0_0_15px_color-mix(in_srgb,var(--accent-strong)_40%,transparent)] hover:bg-[var(--accent-strong)]/80'
                        : 'bg-[var(--surface-strong)] text-[var(--text-tertiary)] hover:text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]'
                    }`}
                  >
                    Limit
                  </button>
                  <button 
                    onClick={() => toggleNodeStatus(node.id, node.status === 'suspended' ? 'active' : 'suspended')}
                    className={`px-4 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all ${
                      node.status === 'suspended'
                        ? 'bg-[var(--status-error)] text-white shadow-[0_0_15px_color-mix(in_srgb,var(--status-error)_40%,transparent)] hover:opacity-90'
                        : 'bg-[var(--surface-strong)] text-[var(--text-tertiary)] hover:text-[var(--status-error)] hover:bg-[color-mix(in_srgb,var(--status-error)_10%,transparent)] border border-transparent hover:border-[var(--status-error)]/20'
                    }`}
                  >
                    Suspend
                  </button>
                </td>
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
