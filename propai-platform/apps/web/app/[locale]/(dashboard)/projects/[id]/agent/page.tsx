"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

export default function AgentControlPage() {
  const { id } = useParams() as { id: string };

  const [commands, setCommands] = useState([
    { id: "CMD-001", type: "Design Change", target: "HVAC System", details: "Reroute Ductwork for zone 4B", assignee: "ME", assigneeName: "M. Engineering", date: "Nov 18", status: "Pending" },
    { id: "CMD-002", type: "Procurement", target: "Structural Steel", details: "Initiate PO #9921 for beams", assignee: "AI", assigneeName: "Procure-Bot", date: "Nov 14", status: "In Progress" },
    { id: "CMD-003", type: "Labor Assign", target: "Foundation Crew", details: "Shift scheduling for Crew A", assignee: "HR", assigneeName: "Site Admin", date: "Nov 12", status: "Done" },
    { id: "CMD-004", type: "Safety Override", target: "Zone 3 Access", details: "Unlock zone 3 gates", assignee: "AI", assigneeName: "Securi-Bot", date: "Nov 12", status: "Rejected" },
    { id: "CMD-005", type: "Schedule Adj", target: "Concrete Pour", details: "Delay pour due to rain forecast", assignee: "AI", assigneeName: "Sched-Bot", date: "Nov 19", status: "Pending" }
  ]);

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden relative">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-[1600px] mx-auto space-y-6">
          {/* Header */}
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-2">
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-2 mb-1">
                <span className="bg-primary/20 text-primary text-xs font-bold px-2 py-0.5 rounded uppercase tracking-wider">Phase 3</span>
                <span className="text-slate-500 dark:text-slate-400 text-xs font-medium uppercase tracking-wider flex items-center gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span> Live
                </span>
              </div>
              <h1 className="text-3xl md:text-4xl font-bold text-slate-900 dark:text-white tracking-tight">Project Alpha Execution</h1>
              <p className="text-slate-500 dark:text-slate-400 text-base">Full-Cycle Real Estate Development Automation System</p>
            </div>
            <div className="flex gap-3">
              <button className="flex items-center justify-center gap-2 rounded-lg h-10 px-4 bg-white dark:bg-[#111318] border border-slate-200 dark:border-border-dark hover:bg-slate-50 dark:hover:bg-border-dark/50 text-slate-900 dark:text-white text-sm font-bold transition-all">
                <span className="material-symbols-outlined text-[18px]">download</span>
                <span>Report</span>
              </button>
              <button className="flex items-center justify-center gap-2 rounded-lg h-10 px-4 bg-primary hover:bg-blue-600 text-white text-sm font-bold shadow-lg shadow-primary/25 transition-all">
                <span className="material-symbols-outlined text-[18px]">add</span>
                <span>New Command</span>
              </button>
            </div>
          </div>
          
          {/* Stats Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="flex flex-col gap-1 p-5 rounded-xl border border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318] relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-4xl text-slate-900 dark:text-white">layers</span>
              </div>
              <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Design Version</p>
              <div className="flex items-end gap-2">
                <p className="text-slate-900 dark:text-white text-2xl font-bold">v4.2</p>
                <span className="text-emerald-500 text-xs font-bold mb-1.5 bg-emerald-500/10 px-1.5 py-0.5 rounded">+0.0%</span>
              </div>
              <div className="w-full bg-slate-100 dark:bg-border-dark/30 h-1 mt-3 rounded-full overflow-hidden">
                <div className="bg-slate-900 dark:bg-white w-full h-full rounded-full"></div>
              </div>
            </div>
            <div className="flex flex-col gap-1 p-5 rounded-xl border border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318] relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-4xl text-slate-900 dark:text-white">construction</span>
              </div>
              <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Current Phase</p>
              <div className="flex items-end gap-2">
                <p className="text-slate-900 dark:text-white text-2xl font-bold">Construction</p>
                <span className="text-slate-500 dark:text-slate-400 text-xs font-bold mb-1.5">on track</span>
              </div>
              <div className="w-full bg-slate-100 dark:bg-border-dark/30 h-1 mt-3 rounded-full overflow-hidden">
                <div className="bg-primary w-[65%] h-full rounded-full relative overflow-hidden">
                  <div className="absolute inset-0 bg-white/20 animate-[pulse_2s_ease-in-out_infinite]"></div>
                </div>
              </div>
            </div>
            <div className="flex flex-col gap-1 p-5 rounded-xl border border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318] relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-4xl text-slate-900 dark:text-white">trending_up</span>
              </div>
              <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">ROI Projection</p>
              <div className="flex items-end gap-2">
                <p className="text-slate-900 dark:text-white text-2xl font-bold">14.5%</p>
                <span className="text-emerald-500 text-xs font-bold mb-1.5 bg-emerald-500/10 px-1.5 py-0.5 rounded">+1.2%</span>
              </div>
              <div className="w-full bg-slate-100 dark:bg-border-dark/30 h-1 mt-3 rounded-full overflow-hidden">
                <div className="bg-emerald-500 w-[80%] h-full rounded-full"></div>
              </div>
            </div>
            <div className="flex flex-col gap-1 p-5 rounded-xl border border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318] relative overflow-hidden group">
              <div className="absolute top-0 right-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-4xl text-slate-900 dark:text-white">event</span>
              </div>
              <p className="text-slate-500 dark:text-slate-400 text-sm font-medium">Completion Est</p>
              <div className="flex items-end gap-2">
                <p className="text-slate-900 dark:text-white text-2xl font-bold">Nov 15, 2024</p>
                <span className="text-red-500 text-xs font-bold mb-1.5 bg-red-500/10 px-1.5 py-0.5 rounded">-2 days</span>
              </div>
              <div className="w-full bg-slate-100 dark:bg-border-dark/30 h-1 mt-3 rounded-full overflow-hidden">
                <div className="bg-orange-500 w-[45%] h-full rounded-full"></div>
              </div>
            </div>
          </div>
          
          {/* AI Insight Panel */}
          <div className="relative overflow-hidden rounded-xl border border-primary/30 bg-gradient-to-r from-blue-50 dark:from-primary/10 to-white dark:to-[#111318] p-6 shadow-2xl shadow-primary/5">
            <div className="absolute top-0 right-0 p-6 opacity-5">
              <span className="material-symbols-outlined text-[120px] text-primary">auto_awesome</span>
            </div>
            <div className="flex flex-col lg:flex-row gap-6 relative z-10">
              <div className="flex-1 flex flex-col gap-2">
                <div className="flex items-center gap-2 mb-1">
                  <span className="material-symbols-outlined text-primary text-xl animate-pulse">auto_awesome</span>
                  <h2 className="text-lg font-bold text-slate-900 dark:text-white tracking-wide">Recommended Optimal Solution</h2>
                </div>
                <h3 className="text-xl md:text-2xl font-bold text-slate-900 dark:text-white leading-tight">AI Proposal #2401: Material Supplier Shift</h3>
                <p className="text-slate-600 dark:text-slate-400 max-w-3xl leading-relaxed">
                  Reasoning: Supply chain delay detected with <span className="text-slate-900 dark:text-white font-medium">Supplier A (Steel)</span>. Switching to <span className="text-slate-900 dark:text-white font-medium">Supplier B</span> reduces critical path latency by <span className="text-emerald-500 font-bold">4 days</span> despite a 1.5% cost increase. This realignment ensures the foundation phase completes before the projected rain season.
                </p>
              </div>
              <div className="flex items-center justify-start lg:justify-end gap-3 min-w-[200px]">
                <button className="h-10 px-5 rounded-lg border border-slate-300 dark:border-border-dark bg-white dark:bg-[#111318] hover:bg-slate-50 dark:hover:bg-border-dark/50 text-slate-900 dark:text-white font-medium text-sm transition-colors">
                  Analyze Impact
                </button>
                <button className="h-10 px-5 rounded-lg bg-primary hover:bg-blue-600 text-white font-bold text-sm shadow-lg shadow-primary/20 transition-all flex items-center gap-2">
                  <span>Execute Proposal</span>
                  <span className="material-symbols-outlined text-[18px]">arrow_forward</span>
                </button>
              </div>
            </div>
          </div>
          
          {/* Split View: Commands & Log */}
          <div className="grid grid-cols-1 xl:grid-cols-4 gap-6 min-h-[500px]">
            {/* Command Table Section */}
            <div className="xl:col-span-3 flex flex-col bg-white dark:bg-[#111318] border border-slate-200 dark:border-border-dark rounded-xl overflow-hidden shadow-sm">
              <div className="p-4 border-b border-slate-200 dark:border-border-dark flex flex-wrap items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">Execution Commands</h3>
                  <span className="bg-primary/10 text-primary text-xs font-bold px-2 py-0.5 rounded-full">12 Active</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 text-[18px]">search</span>
                    <input className="bg-slate-50 dark:bg-background-dark border border-slate-200 dark:border-border-dark text-slate-900 dark:text-white text-sm rounded-lg pl-9 pr-3 py-1.5 focus:outline-none focus:border-primary w-48 transition-colors" placeholder="Search ID or Target..." type="text" />
                  </div>
                  <button className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-white/5 text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-colors">
                    <span className="material-symbols-outlined text-[20px]">filter_list</span>
                  </button>
                </div>
              </div>
              <div className="overflow-x-auto flex-1">
                <table className="w-full text-left border-collapse">
                  <thead>
                    <tr className="bg-slate-50 dark:bg-background-dark/50 border-b border-slate-200 dark:border-border-dark text-xs font-medium text-slate-500 dark:text-slate-400 uppercase tracking-wider">
                      <th className="px-5 py-3 font-semibold">ID</th>
                      <th className="px-5 py-3 font-semibold">Type</th>
                      <th className="px-5 py-3 font-semibold">Target / Details</th>
                      <th className="px-5 py-3 font-semibold">Assignee</th>
                      <th className="px-5 py-3 font-semibold">Deadline</th>
                      <th className="px-5 py-3 font-semibold">Status</th>
                      <th className="px-5 py-3 font-semibold text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-border-dark text-sm">
                    {commands.map((cmd) => (
                      <tr key={cmd.id} className="group hover:bg-slate-50 dark:hover:bg-white/[0.02] transition-colors">
                        <td className="px-5 py-4 font-mono text-slate-500 dark:text-slate-400">{cmd.id}</td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <span className={`material-symbols-outlined text-[18px] ${
                              cmd.type === "Design Change" ? "text-orange-500" :
                              cmd.type === "Procurement" ? "text-primary" :
                              cmd.type === "Labor Assign" ? "text-slate-500" :
                              cmd.type === "Safety Override" ? "text-red-500" :
                              "text-orange-500"
                            }`}>
                              {cmd.type === "Design Change" ? "architecture" :
                               cmd.type === "Procurement" ? "shopping_cart" :
                               cmd.type === "Labor Assign" ? "group" :
                               cmd.type === "Safety Override" ? "warning" : "calendar_clock"}
                            </span>
                            <span className="text-slate-900 dark:text-white font-medium">{cmd.type}</span>
                          </div>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex flex-col">
                            <span className="text-slate-900 dark:text-white font-medium">{cmd.target}</span>
                            <span className="text-xs text-slate-500 dark:text-slate-400 truncate max-w-[200px]">{cmd.details}</span>
                          </div>
                        </td>
                        <td className="px-5 py-4">
                          <div className="flex items-center gap-2">
                            <div className={`size-6 rounded-full flex items-center justify-center text-[10px] font-bold border ${
                              cmd.assignee === "ME" ? "bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 border-blue-200 dark:border-blue-700" :
                              cmd.assignee === "AI" ? "bg-primary/10 text-primary border-primary/20" :
                              "bg-orange-100 dark:bg-orange-900 text-orange-700 dark:text-orange-200 border-orange-200 dark:border-orange-700"
                            }`}>
                              {cmd.assignee}
                            </div>
                            <span className="text-slate-600 dark:text-slate-400">{cmd.assigneeName}</span>
                          </div>
                        </td>
                        <td className="px-5 py-4 text-slate-900 dark:text-white">{cmd.date}</td>
                        <td className="px-5 py-4">
                          {cmd.status === "Pending" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-orange-100 dark:bg-orange-500/10 text-orange-600 dark:text-orange-500 border border-orange-200 dark:border-orange-500/20">
                              <span className="w-1.5 h-1.5 rounded-full bg-orange-500"></span> Pending
                            </span>
                          )}
                          {cmd.status === "In Progress" && (
                            <div className="flex flex-col gap-1.5 w-24">
                              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-primary">
                                <span className="animate-spin text-[10px] material-symbols-outlined">progress_activity</span> In Progress
                              </span>
                              <div className="h-1 w-full bg-slate-100 dark:bg-background-dark rounded-full overflow-hidden">
                                <div className="h-full bg-primary w-[65%] rounded-full"></div>
                              </div>
                            </div>
                          )}
                          {cmd.status === "Done" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-100 dark:bg-emerald-500/10 text-emerald-600 dark:text-emerald-500 border border-emerald-200 dark:border-emerald-500/20">
                              <span className="material-symbols-outlined text-[14px]">check</span> Done
                            </span>
                          )}
                          {cmd.status === "Rejected" && (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-red-100 dark:bg-red-500/10 text-red-600 dark:text-red-500 border border-red-200 dark:border-red-500/20">
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
                                <button className="p-1.5 rounded text-emerald-600 hover:bg-emerald-50 dark:text-emerald-500 dark:hover:bg-emerald-500/10 transition-colors" title="Approve">
                                  <span className="material-symbols-outlined text-[20px]">check_circle</span>
                                </button>
                                <button className="p-1.5 rounded text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-white dark:hover:bg-white/10 transition-colors" title="Modify">
                                  <span className="material-symbols-outlined text-[20px]">edit</span>
                                </button>
                                <button className="p-1.5 rounded text-red-600 hover:bg-red-50 dark:text-red-500 dark:hover:bg-red-500/10 transition-colors" title="Reject">
                                  <span className="material-symbols-outlined text-[20px]">cancel</span>
                                </button>
                              </>
                            ) : (
                              <button className="p-1.5 rounded text-slate-500 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-white dark:hover:bg-white/10 transition-colors">
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
              <div className="p-3 border-t border-slate-200 dark:border-border-dark flex items-center justify-between">
                <span className="text-xs text-slate-500 dark:text-slate-400 ml-2">Showing 5 of 12 commands</span>
                <div className="flex gap-1">
                  <button className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-white/10 text-slate-500 dark:text-slate-400 disabled:opacity-50">
                    <span className="material-symbols-outlined text-[18px]">chevron_left</span>
                  </button>
                  <button className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-white/10 text-slate-900 dark:text-white">
                    <span className="material-symbols-outlined text-[18px]">chevron_right</span>
                  </button>
                </div>
              </div>
            </div>
            
            {/* Activity Log Section */}
            <div className="xl:col-span-1 flex flex-col bg-white dark:bg-[#111318] border border-slate-200 dark:border-border-dark rounded-xl overflow-hidden shadow-sm h-full max-h-[600px]">
              <div className="p-4 border-b border-slate-200 dark:border-border-dark flex items-center justify-between">
                <h3 className="text-base font-bold text-slate-900 dark:text-white">Activity Audit</h3>
                <button className="text-xs text-primary font-medium hover:underline">View All</button>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-6">
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-slate-200 dark:before:bg-border-dark last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full bg-primary border-2 border-white dark:border-[#111318]"></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-slate-500 dark:text-slate-400">Just now</p>
                    <p className="text-sm text-slate-900 dark:text-white font-medium">AI generated Proposal #2401</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Detected latency in steel supply chain.</p>
                  </div>
                </div>
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-slate-200 dark:before:bg-border-dark last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full bg-emerald-500 border-2 border-white dark:border-[#111318]"></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-slate-500 dark:text-slate-400">15 mins ago</p>
                    <p className="text-sm text-slate-900 dark:text-white font-medium">User 'J. Smith' Approved CMD-002</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Material Order PO #9921 initiated.</p>
                  </div>
                </div>
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-slate-200 dark:before:bg-border-dark last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full bg-red-500 border-2 border-white dark:border-[#111318]"></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-slate-500 dark:text-slate-400">1 hour ago</p>
                    <p className="text-sm text-slate-900 dark:text-white font-medium">CMD-004 Rejected by Admin</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">Safety protocol violation flagged.</p>
                  </div>
                </div>
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-slate-200 dark:before:bg-border-dark last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full bg-slate-300 dark:bg-border-dark border-2 border-white dark:border-[#111318]"></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-slate-500 dark:text-slate-400">3 hours ago</p>
                    <p className="text-sm text-slate-900 dark:text-white font-medium">Daily Sync Completed</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">System synchronized with 4 external APIs.</p>
                  </div>
                </div>
                <div className="relative pl-6 before:content-[''] before:absolute before:left-1.5 before:top-2 before:w-[1px] before:h-full before:bg-slate-200 dark:before:bg-border-dark last:before:hidden">
                  <div className="absolute left-0 top-1.5 w-3 h-3 rounded-full bg-slate-300 dark:bg-border-dark border-2 border-white dark:border-[#111318]"></div>
                  <div className="flex flex-col gap-1">
                    <p className="text-xs text-slate-500 dark:text-slate-400">Yesterday</p>
                    <p className="text-sm text-slate-900 dark:text-white font-medium">Phase 2 Report Archived</p>
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
