"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { ModuleCommandStrip } from "@/components/layout/ModuleCommandStrip";

export default function AgentControlPage() {
  const { id } = useParams() as { id: string };

  // NOTE(무목업): 아래 commands/activity 로그는 정적 데모(mockup) 데이터다.
  // 본 작업은 시각/마크업 전파만 수행하므로 동작은 그대로 두고 외형만 토큰화했다.
  // 실데이터 배선은 별도 백엔드 연동 작업으로 분리한다.
  const [commands] = useState([
    { id: "CMD-001", type: "Design Change", target: "HVAC System", details: "Reroute Ductwork for zone 4B", assignee: "ME", assigneeName: "M. Engineering", date: "Nov 18", status: "Pending" },
    { id: "CMD-002", type: "Procurement", target: "Structural Steel", details: "Initiate PO #9921 for beams", assignee: "AI", assigneeName: "Procure-Bot", date: "Nov 14", status: "In Progress" },
    { id: "CMD-003", type: "Labor Assign", target: "Foundation Crew", details: "Shift scheduling for Crew A", assignee: "HR", assigneeName: "Site Admin", date: "Nov 12", status: "Done" },
    { id: "CMD-004", type: "Safety Override", target: "Zone 3 Access", details: "Unlock zone 3 gates", assignee: "AI", assigneeName: "Securi-Bot", date: "Nov 12", status: "Rejected" },
    { id: "CMD-005", type: "Schedule Adj", target: "Concrete Pour", details: "Delay pour due to rain forecast", assignee: "AI", assigneeName: "Sched-Bot", date: "Nov 19", status: "Pending" }
  ]);

  // 커맨드 유형 → 의미색(디자인 토큰). 하드코딩 Tailwind 색 제거.
  const typeColor = (t: string): string => {
    if (t === "Design Change" || t === "Schedule Adj") return "var(--status-warning)";
    if (t === "Procurement") return "var(--data-accent)";
    if (t === "Safety Override") return "var(--status-error)";
    return "var(--text-tertiary)";
  };
  const typeIcon = (t: string): string => {
    if (t === "Design Change") return "architecture";
    if (t === "Procurement") return "shopping_cart";
    if (t === "Labor Assign") return "group";
    if (t === "Safety Override") return "warning";
    return "calendar_clock";
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[1600px] mx-auto space-y-6">
          {/* ⓪ 커맨드센터 HUD 스트립 — 모듈 식별·LIVE(시각 전용) */}
          <ModuleCommandStrip label="AGENT CONTROL · 실행 커맨드" meta="PHASE 3" />

          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-2">
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="cc-chip-data uppercase">Phase 3</span>
                <span className="cc-live"><i />Live</span>
              </div>
              <h1 className="text-3xl md:text-4xl font-bold text-[var(--text-primary)] tracking-tight">Project Alpha Execution</h1>
              <p className="text-[var(--text-secondary)] text-base">Full-Cycle Real Estate Development Automation System</p>
            </div>
            <div className="flex gap-3">
              <button className="cc-interactive flex items-center justify-center gap-2 rounded-lg h-10 px-4 bg-[var(--surface-strong)] border border-[var(--line-strong)] hover:bg-[var(--surface-soft)] text-[var(--text-primary)] text-sm font-bold">
                <span className="material-symbols-outlined text-[18px]">download</span>
                <span>Report</span>
              </button>
              <button className="flex items-center justify-center gap-2 rounded-lg h-10 px-4 bg-[var(--accent-strong)] hover:opacity-90 text-white text-sm font-bold shadow-[var(--shadow-md)] transition-all">
                <span className="material-symbols-outlined text-[18px]">add</span>
                <span>New Command</span>
              </button>
            </div>
          </div>

          {/* Stats Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="cc-panel cc-interactive flex flex-col gap-1 p-5 relative overflow-hidden group">
              <div className="cc-grid-bg opacity-30" />
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-4xl text-[var(--text-primary)]">layers</span>
              </div>
              <p className="cc-label">Design Version</p>
              <div className="flex items-end gap-2">
                <p className="cc-num text-2xl font-bold">v4.2</p>
                <span className="text-xs font-bold mb-1.5 px-1.5 py-0.5 rounded" style={{ color: "var(--status-success)", background: "color-mix(in srgb, var(--status-success) 12%, transparent)" }}>+0.0%</span>
              </div>
              <div className="w-full bg-[var(--line)] h-1 mt-3 rounded-full overflow-hidden">
                <div className="bg-[var(--text-primary)] w-full h-full rounded-full"></div>
              </div>
            </div>
            <div className="cc-panel cc-interactive flex flex-col gap-1 p-5 relative overflow-hidden group">
              <div className="cc-grid-bg opacity-30" />
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-4xl text-[var(--text-primary)]">construction</span>
              </div>
              <p className="cc-label">Current Phase</p>
              <div className="flex items-end gap-2">
                <p className="text-[var(--text-primary)] text-2xl font-bold">Construction</p>
                <span className="text-[var(--text-tertiary)] text-xs font-bold mb-1.5">on track</span>
              </div>
              <div className="w-full bg-[var(--line)] h-1 mt-3 rounded-full overflow-hidden">
                <div className="bg-[var(--data-accent)] w-[65%] h-full rounded-full relative overflow-hidden">
                  <div className="absolute inset-0 bg-white/20 animate-[pulse_2s_ease-in-out_infinite] motion-reduce:animate-none"></div>
                </div>
              </div>
            </div>
            <div className="cc-panel cc-interactive flex flex-col gap-1 p-5 relative overflow-hidden group">
              <div className="cc-grid-bg opacity-30" />
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-4xl text-[var(--text-primary)]">trending_up</span>
              </div>
              <p className="cc-label">ROI Projection</p>
              <div className="flex items-end gap-2">
                <p className="cc-num cc-num--data text-2xl font-bold">14.5%</p>
                <span className="text-xs font-bold mb-1.5 px-1.5 py-0.5 rounded" style={{ color: "var(--status-success)", background: "color-mix(in srgb, var(--status-success) 12%, transparent)" }}>+1.2%</span>
              </div>
              <div className="w-full bg-[var(--line)] h-1 mt-3 rounded-full overflow-hidden">
                <div className="w-[80%] h-full rounded-full" style={{ background: "var(--status-success)" }}></div>
              </div>
            </div>
            <div className="cc-panel cc-interactive flex flex-col gap-1 p-5 relative overflow-hidden group">
              <div className="cc-grid-bg opacity-30" />
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-4xl text-[var(--text-primary)]">event</span>
              </div>
              <p className="cc-label">Completion Est</p>
              <div className="flex items-end gap-2">
                <p className="cc-num text-2xl font-bold">Nov 15, 2024</p>
                <span className="text-xs font-bold mb-1.5 px-1.5 py-0.5 rounded" style={{ color: "var(--status-error)", background: "color-mix(in srgb, var(--status-error) 12%, transparent)" }}>-2 days</span>
              </div>
              <div className="w-full bg-[var(--line)] h-1 mt-3 rounded-full overflow-hidden">
                <div className="w-[45%] h-full rounded-full" style={{ background: "var(--status-warning)" }}></div>
              </div>
            </div>
          </div>

          {/* AI Insight Panel */}
          <div className="cc-bracketed relative overflow-hidden rounded-xl border border-[var(--data-accent-line)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-xl)]">
            <div className="cc-grid-bg opacity-30" />
            <i className="cc-bracket cc-bracket--tl" />
            <i className="cc-bracket cc-bracket--tr" />
            <i className="cc-bracket cc-bracket--bl" />
            <i className="cc-bracket cc-bracket--br" />
            <div className="absolute top-0 right-0 p-6 opacity-5">
              <span className="material-symbols-outlined text-[120px] text-[var(--data-accent)]">auto_awesome</span>
            </div>
            <div className="flex flex-col lg:flex-row gap-6 relative z-10">
              <div className="flex-1 flex flex-col gap-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="material-symbols-outlined text-[var(--data-accent)] text-xl animate-pulse motion-reduce:animate-none">auto_awesome</span>
                  <h2 className="cc-meta text-[11px]">Recommended Optimal Solution</h2>
                </div>
                <h3 className="text-xl md:text-2xl font-bold text-[var(--text-primary)] leading-tight">AI Proposal #2401: Material Supplier Shift</h3>
                <p className="text-[var(--text-secondary)] max-w-3xl leading-relaxed">
                  Reasoning: Supply chain delay detected with <span className="text-[var(--text-primary)] font-medium">Supplier A (Steel)</span>. Switching to <span className="text-[var(--text-primary)] font-medium">Supplier B</span> reduces critical path latency by <span className="font-bold" style={{ color: "var(--status-success)" }}>4 days</span> despite a 1.5% cost increase. This realignment ensures the foundation phase completes before the projected rain season.
                </p>
              </div>
              <div className="flex items-center justify-start lg:justify-end gap-3 min-w-[200px]">
                <button className="cc-interactive h-10 px-5 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-soft)] hover:bg-[var(--surface)] text-[var(--text-primary)] font-medium text-sm">
                  Analyze Impact
                </button>
                <button className="h-10 px-5 rounded-lg bg-[var(--accent-strong)] hover:opacity-90 text-white font-bold text-sm shadow-[var(--shadow-md)] transition-all flex items-center gap-2">
                  <span>Execute Proposal</span>
                  <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                </button>
              </div>
            </div>
          </div>

          {/* Split View: Commands & Log */}
          <div className="grid grid-cols-1 xl:grid-cols-4 gap-6 min-h-[500px]">
            {/* Command Table Section */}
            <div className="cc-panel xl:col-span-3 flex flex-col">
              <div className="cc-panel__head flex-wrap">
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-bold text-[var(--text-primary)]">Execution Commands</h3>
                  <span className="cc-chip-data rounded-full">12 Active</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-hint)] text-[18px]">search</span>
                    <input className="bg-[var(--surface)] border border-[var(--line)] text-[var(--text-primary)] text-sm rounded-lg pl-9 pr-3 py-1.5 focus:outline-none focus:border-[var(--data-accent)] w-48 transition-colors" placeholder="Search ID or Target..." type="text" />
                  </div>
                  <button className="p-1.5 rounded hover:bg-[var(--surface-soft)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors">
                    <span className="material-symbols-outlined text-[20px]">filter_list</span>
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto flex-1">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-[var(--surface)] border-b border-[var(--line)]">
                      <th className="px-5 py-3 cc-label text-left">ID</th>
                      <th className="px-5 py-3 cc-label text-left">Type</th>
                      <th className="px-5 py-3 cc-label text-left">Target / Details</th>
                      <th className="px-5 py-3 cc-label text-left">Assignee</th>
                      <th className="px-5 py-3 cc-label text-left">Deadline</th>
                      <th className="px-5 py-3 cc-label text-left">Status</th>
                      <th className="px-5 py-3 cc-label text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--line-subtle)] text-sm">
                    {commands.map((cmd) => (
                      <tr key={cmd.id} className="group hover:bg-[var(--surface-soft)] transition-colors">
                        <td className="px-5 py-4 cc-num text-[var(--text-tertiary)]">{cmd.id}</td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <span className="material-symbols-outlined text-[18px]" style={{ color: typeColor(cmd.type) }}>
                              {typeIcon(cmd.type)}
                            </span>
                            <span className="text-[var(--text-primary)] font-medium">{cmd.type}</span>
                          </div>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex flex-col">
                            <span className="text-[var(--text-primary)] font-medium">{cmd.target}</span>
                            <span className="text-xs text-[var(--text-tertiary)] truncate max-w-[200px]">{cmd.details}</span>
                          </div>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <div
                              className="size-6 rounded-full flex items-center justify-center text-[10px] font-bold border"
                              style={
                                cmd.assignee === "ME"
                                  ? { color: "var(--status-info)", background: "color-mix(in srgb, var(--status-info) 12%, transparent)", borderColor: "color-mix(in srgb, var(--status-info) 30%, transparent)" }
                                  : cmd.assignee === "AI"
                                  ? { color: "var(--data-accent)", background: "var(--data-accent-soft)", borderColor: "var(--data-accent-line)" }
                                  : { color: "var(--status-warning)", background: "color-mix(in srgb, var(--status-warning) 12%, transparent)", borderColor: "color-mix(in srgb, var(--status-warning) 30%, transparent)" }
                              }
                            >
                              {cmd.assignee}
                            </div>
                            <span className="text-[var(--text-secondary)]">{cmd.assigneeName}</span>
                          </div>
                        </td>
                        <td className="px-5 py-4 cc-num text-[var(--text-primary)]">{cmd.date}</td>
                        <td className="px-5 py-4">
                          {cmd.status === "Pending" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border" style={{ color: "var(--status-warning)", background: "color-mix(in srgb, var(--status-warning) 10%, transparent)", borderColor: "color-mix(in srgb, var(--status-warning) 22%, transparent)" }}>
                              <span className="w-1.5 h-1.5 rounded-full" style={{ background: "var(--status-warning)" }}></span> Pending
                            </span>
                          )}
                          {cmd.status === "In Progress" && (
                            <div className="flex flex-col gap-1.5 w-24">
                              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--data-accent)]">
                                <span className="animate-spin motion-reduce:animate-none text-[10px] material-symbols-outlined">progress_activity</span> In Progress
                              </span>
                              <div className="h-1 w-full bg-[var(--line)] rounded-full overflow-hidden">
                                <div className="h-full bg-[var(--data-accent)] w-[65%] rounded-full"></div>
                              </div>
                            </div>
                          )}
                          {cmd.status === "Done" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border" style={{ color: "var(--status-success)", background: "color-mix(in srgb, var(--status-success) 10%, transparent)", borderColor: "color-mix(in srgb, var(--status-success) 22%, transparent)" }}>
                              <span className="material-symbols-outlined text-[14px]">check</span> Done
                            </span>
                          )}
                          {cmd.status === "Rejected" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border" style={{ color: "var(--status-error)", background: "color-mix(in srgb, var(--status-error) 10%, transparent)", borderColor: "color-mix(in srgb, var(--status-error) 22%, transparent)" }}>
                              Rejected
                            </span>
                          )}
                        </td>
                        <td className="px-5 py-4 text-right">
                          <div className={`flex items-center justify-end gap-1 ${
                            cmd.status === "Pending" ? "opacity-100 sm:opacity-0 group-hover:opacity-100" : "opacity-40 group-hover:opacity-100"
                          } transition-opacity`}>
                            {cmd.status === "Pending" ? (
                              <>
                                <button className="p-1.5 rounded transition-colors hover:bg-[var(--surface-soft)]" style={{ color: "var(--status-success)" }} title="Approve">
                                  <span className="material-symbols-outlined text-[20px]">check_circle</span>
                                </button>
                                <button className="p-1.5 rounded text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-soft)] transition-colors" title="Modify">
                                  <span className="material-symbols-outlined text-[20px]">edit</span>
                                </button>
                                <button className="p-1.5 rounded transition-colors hover:bg-[var(--surface-soft)]" style={{ color: "var(--status-error)" }} title="Reject">
                                  <span className="material-symbols-outlined text-[20px]">cancel</span>
                                </button>
                              </>
                            ) : (
                              <button className="p-1.5 rounded text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-soft)] transition-colors">
                                <span className="material-symbols-outlined text-[20px]">
                                  {cmd.status === "Done" ? "visibility" : cmd.status === "Rejected" ? "history" : "more_horiz"}
                                </span>
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="p-3 border-t border-[var(--line)] flex items-center justify-between">
                <span className="text-xs text-[var(--text-tertiary)] ml-2">Showing 5 of 12 commands</span>
                <div className="flex gap-1">
                  <button className="p-1.5 rounded hover:bg-[var(--surface-soft)] text-[var(--text-tertiary)] disabled:opacity-50">
                    <span className="material-symbols-outlined text-[18px]">chevron_left</span>
                  </button>
                  <button className="p-1.5 rounded hover:bg-[var(--surface-soft)] text-[var(--text-primary)]">
                    <span className="material-symbols-outlined text-[18px]">chevron_right</span>
                  </button>
                </div>
              </div>
            </div>

            {/* Activity Log Section */}
            <div className="cc-panel xl:col-span-1 flex flex-col h-full max-h-[600px]">
              <div className="cc-panel__head">
                <h3 className="text-base font-bold text-[var(--text-primary)]">Activity Audit</h3>
                <button className="text-xs text-[var(--accent-strong)] font-medium hover:underline">View All</button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-6">
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-[var(--line)] last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full bg-[var(--data-accent)] border-2 border-[var(--surface-strong)]"></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-[var(--text-tertiary)]">Just now</p>
                    <p className="text-sm text-[var(--text-primary)] font-medium">AI generated Proposal #2401</p>
                    <p className="text-xs text-[var(--text-tertiary)]">Detected latency in steel supply chain.</p>
                  </div>
                </div>
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-[var(--line)] last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full border-2 border-[var(--surface-strong)]" style={{ background: "var(--status-success)" }}></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-[var(--text-tertiary)]">15 mins ago</p>
                    <p className="text-sm text-[var(--text-primary)] font-medium">User &apos;J. Smith&apos; Approved CMD-002</p>
                    <p className="text-xs text-[var(--text-tertiary)]">Material Order PO #9921 initiated.</p>
                  </div>
                </div>
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-[var(--line)] last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full border-2 border-[var(--surface-strong)]" style={{ background: "var(--status-error)" }}></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-[var(--text-tertiary)]">1 hour ago</p>
                    <p className="text-sm text-[var(--text-primary)] font-medium">CMD-004 Rejected by Admin</p>
                    <p className="text-xs text-[var(--text-tertiary)]">Safety protocol violation flagged.</p>
                  </div>
                </div>
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-[var(--line)] last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full bg-[var(--line-strong)] border-2 border-[var(--surface-strong)]"></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-[var(--text-tertiary)]">3 hours ago</p>
                    <p className="text-sm text-[var(--text-primary)] font-medium">Daily Sync Completed</p>
                    <p className="text-xs text-[var(--text-tertiary)]">System synchronized with 4 external APIs.</p>
                  </div>
                </div>
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-[var(--line)] last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full bg-[var(--line-strong)] border-2 border-[var(--surface-strong)]"></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-[var(--text-tertiary)]">Yesterday</p>
                    <p className="text-sm text-[var(--text-primary)] font-medium">Phase 2 Report Archived</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
