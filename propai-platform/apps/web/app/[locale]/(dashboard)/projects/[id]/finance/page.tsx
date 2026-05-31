"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

export default function FinanceSimulationPage() {
  const { id } = useParams() as { id: string };
  const [runs, setRuns] = useState([
    { id: "1025", status: "Active", time: "Started 2 mins ago" },
    { id: "1024", status: "Completed", time: "Today, 10:42 AM" },
    { id: "1023", status: "Completed", time: "Yesterday, 4:15 PM" },
    { id: "1022", status: "Failed", time: "Yesterday, 2:00 PM" }
  ]);

  return (
    <div className="flex h-[calc(100vh-120px)] w-full overflow-hidden rounded-xl border border-slate-200 dark:border-border-dark bg-white dark:bg-background-dark font-display text-slate-900 dark:text-white shadow-sm">
      {/* Sidebar: Sim History */}
      <aside className="w-64 bg-slate-50 dark:bg-[#111318] border-r border-slate-200 dark:border-border-dark flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-200 dark:border-border-dark bg-white dark:bg-transparent">
          <h1 className="text-slate-900 dark:text-white text-base font-bold leading-normal">Sim History</h1>
          <p className="text-slate-500 text-xs font-normal mt-1">Recent Monte Carlo Runs</p>
        </div>
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {runs.map((run, i) => (
            <div key={run.id} className={`flex flex-col gap-1 px-3 py-2 rounded-lg cursor-pointer group transition-colors ${
              run.status === "Active" 
                ? "bg-primary/10 border border-primary/20" 
                : "hover:bg-slate-100 dark:hover:bg-[#1e232e]"
            }`}>
              <div className="flex items-center justify-between">
                <span className={`text-xs font-bold uppercase tracking-wider ${
                  run.status === "Active" ? "text-primary" : run.status === "Completed" ? "text-emerald-500" : "text-red-500"
                }`}>
                  {run.status}
                </span>
                <span className={`material-symbols-outlined text-[16px] ${
                  run.status === "Active" ? "text-primary" : "text-slate-400"
                }`}>
                  {run.status === "Active" ? "play_circle" : run.status === "Completed" ? "history" : "warning"}
                </span>
              </div>
              <p className="text-slate-900 dark:text-white text-sm font-semibold leading-normal">Simulation #{run.id}</p>
              <p className="text-slate-500 text-xs">{run.time}</p>
            </div>
          ))}
        </div>
        <div className="p-4 border-t border-slate-200 dark:border-border-dark bg-white dark:bg-transparent">
          <button className="flex w-full items-center justify-center gap-2 rounded-lg py-2 text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-[#1e232e] hover:text-slate-900 dark:hover:text-white transition-colors text-sm font-bold">
            <span className="material-symbols-outlined text-[18px]">add</span>
            New Simulation
          </button>
        </div>
      </aside>

      {/* Main Workspace */}
      <main className="flex-1 overflow-y-auto bg-slate-50/50 dark:bg-[#0f1115]">
        <div className="p-6 max-w-[1600px] mx-auto min-h-full flex flex-col gap-6">
          <div className="flex flex-col lg:flex-row gap-6 h-full">
            {/* Left Column: Simulation Setup */}
            <div className="w-full lg:w-1/3 xl:w-1/4 flex flex-col gap-6">
              {/* Configuration Card */}
              <div className="bg-white dark:bg-card-dark rounded-xl border border-slate-200 dark:border-border-dark p-5 shadow-sm">
                <div className="flex items-center gap-2 mb-4 border-b border-slate-200 dark:border-border-dark pb-3">
                  <span className="material-symbols-outlined text-primary">tune</span>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-white">Simulation Setup</h3>
                </div>
                <form className="flex flex-col gap-5">
                  {/* Project Data */}
                  <div className="flex flex-col gap-3">
                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider">Project Inputs</h4>
                    <label className="flex flex-col">
                      <span className="text-slate-700 dark:text-slate-300 text-sm font-medium mb-1.5">Land Cost ($)</span>
                      <div className="relative">
                        <input className="w-full bg-slate-50 dark:bg-[#111318] border border-slate-300 dark:border-border-dark rounded-lg py-2.5 px-3 pl-8 text-sm text-slate-900 dark:text-white focus:ring-1 focus:ring-primary focus:border-primary outline-none transition-all" type="text" defaultValue="5,000,000" />
                        <span className="absolute left-3 top-2.5 text-slate-400 text-sm">$</span>
                      </div>
                    </label>
                    <label className="flex flex-col">
                      <span className="text-slate-700 dark:text-slate-300 text-sm font-medium mb-1.5">Target Sales Price ($)</span>
                      <div className="relative">
                        <input className="w-full bg-slate-50 dark:bg-[#111318] border border-slate-300 dark:border-border-dark rounded-lg py-2.5 px-3 pl-8 text-sm text-slate-900 dark:text-white focus:ring-1 focus:ring-primary focus:border-primary outline-none transition-all" type="text" defaultValue="12,500,000" />
                        <span className="absolute left-3 top-2.5 text-slate-400 text-sm">$</span>
                      </div>
                    </label>
                  </div>
                  {/* Risk Parameters */}
                  <div className="flex flex-col gap-4 mt-2">
                    <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider">Risk Parameters</h4>
                    <label className="flex flex-col gap-2">
                      <div className="flex justify-between">
                        <span className="text-slate-700 dark:text-slate-300 text-sm font-medium">Monte Carlo Iterations</span>
                        <span className="text-primary text-sm font-bold">10,000</span>
                      </div>
                      <input className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-primary" max="50000" min="1000" step="1000" type="range" defaultValue="10000" />
                      <div className="flex justify-between text-[10px] text-slate-500">
                        <span>1k</span>
                        <span>50k</span>
                      </div>
                    </label>
                    <label className="flex flex-col gap-2">
                      <div className="flex justify-between">
                        <span className="text-slate-700 dark:text-slate-300 text-sm font-medium">Permit Failure Prob.</span>
                        <span className="text-red-500 dark:text-red-400 text-sm font-bold">12%</span>
                      </div>
                      <input className="w-full h-2 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-red-500" max="100" min="0" step="1" type="range" defaultValue="12" />
                    </label>
                    <label className="flex flex-col">
                      <span className="text-slate-700 dark:text-slate-300 text-sm font-medium mb-1.5">Cost Variation Dist.</span>
                      <select className="w-full bg-slate-50 dark:bg-[#111318] border border-slate-300 dark:border-border-dark rounded-lg py-2.5 px-3 text-sm text-slate-900 dark:text-white focus:ring-1 focus:ring-primary focus:border-primary outline-none">
                        <option>Log-Normal (Standard)</option>
                        <option>Normal (Gaussian)</option>
                        <option>Triangular</option>
                        <option>Uniform</option>
                      </select>
                    </label>
                  </div>
                  <button className="mt-4 w-full bg-primary hover:bg-blue-600 text-white font-bold py-3.5 px-4 rounded-lg shadow-lg shadow-blue-500/20 active:transform active:scale-[0.98] transition-all flex items-center justify-center gap-2" type="button">
                    <span className="material-symbols-outlined">play_arrow</span>
                    Run Simulation
                  </button>
                </form>
              </div>
              
              {/* Setup Info Card */}
              <div className="bg-primary/5 border border-primary/20 rounded-xl p-4">
                <div className="flex items-start gap-3">
                  <span className="material-symbols-outlined text-primary mt-0.5">info</span>
                  <div>
                    <h5 className="text-slate-900 dark:text-white font-bold text-sm">Model Assumptions</h5>
                    <p className="text-slate-600 dark:text-slate-400 text-xs mt-1 leading-relaxed">
                      Calculations assume a 95% confidence interval. Market volatility is based on Q3 2023 index data.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            {/* Right Column: Results Dashboard */}
            <div className="flex-1 flex flex-col gap-6 min-w-0">
              <div className="flex items-center justify-between">
                <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Simulation Results</h2>
                <div className="flex items-center gap-2 text-slate-500 text-sm">
                  <span className="material-symbols-outlined text-[18px]">update</span>
                  Last updated: Just now
                </div>
              </div>

              {/* KPI Cards */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
                {/* Mean NPV */}
                <div className="bg-white dark:bg-card-dark rounded-xl p-4 border border-slate-200 dark:border-border-dark shadow-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="p-1.5 rounded-md bg-blue-500/10 text-blue-500">
                      <span className="material-symbols-outlined text-[20px]">payments</span>
                    </div>
                    <span className="text-slate-500 text-xs font-bold uppercase">Mean NPV</span>
                  </div>
                  <p className="text-2xl font-bold text-slate-900 dark:text-white">$2.1M</p>
                  <div className="flex items-center gap-1 mt-1 text-emerald-500 text-xs font-bold">
                    <span className="material-symbols-outlined text-[14px]">trending_up</span>
                    <span>+4.2% vs Baseline</span>
                  </div>
                </div>
                {/* Mean IRR */}
                <div className="bg-white dark:bg-card-dark rounded-xl p-4 border border-slate-200 dark:border-border-dark shadow-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="p-1.5 rounded-md bg-purple-500/10 text-purple-500">
                      <span className="material-symbols-outlined text-[20px]">percent</span>
                    </div>
                    <span className="text-slate-500 text-xs font-bold uppercase">Mean IRR</span>
                  </div>
                  <p className="text-2xl font-bold text-slate-900 dark:text-white">14.2%</p>
                  <div className="flex items-center gap-1 mt-1 text-slate-500 text-xs font-bold">
                    <span>Target: 15.0%</span>
                  </div>
                </div>
                {/* VaR 95% */}
                <div className="bg-white dark:bg-card-dark rounded-xl p-4 border border-slate-200 dark:border-border-dark shadow-sm relative overflow-hidden group">
                  <div className="absolute inset-0 bg-red-500/5 dark:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-opacity"></div>
                  <div className="flex items-center gap-2 mb-2 relative z-10">
                    <div className="p-1.5 rounded-md bg-red-500/10 text-red-500">
                      <span className="material-symbols-outlined text-[20px]">trending_down</span>
                    </div>
                    <span className="text-slate-500 text-xs font-bold uppercase">VaR (95%)</span>
                  </div>
                  <p className="text-2xl font-bold text-red-500 dark:text-red-400 relative z-10">-$450k</p>
                  <p className="text-xs text-slate-500 mt-1 relative z-10 font-medium">Downside Risk</p>
                </div>
                {/* cVaR 95% */}
                <div className="bg-white dark:bg-card-dark rounded-xl p-4 border border-slate-200 dark:border-border-dark shadow-sm">
                  <div className="flex items-center gap-2 mb-2">
                    <div className="p-1.5 rounded-md bg-orange-500/10 text-orange-500">
                      <span className="material-symbols-outlined text-[20px]">warning</span>
                    </div>
                    <span className="text-slate-500 text-xs font-bold uppercase">cVaR (95%)</span>
                  </div>
                  <p className="text-2xl font-bold text-slate-900 dark:text-white">-$620k</p>
                  <p className="text-xs text-slate-500 mt-1 font-medium">Tail Risk Average</p>
                </div>
                {/* Success Probability */}
                <div className="bg-white dark:bg-card-dark rounded-xl p-4 border border-slate-200 dark:border-border-dark shadow-sm relative overflow-hidden">
                  <div className="absolute bottom-0 left-0 h-1 bg-emerald-500 w-[87%]"></div>
                  <div className="flex items-center gap-2 mb-2">
                    <div className="p-1.5 rounded-md bg-emerald-500/10 text-emerald-500">
                      <span className="material-symbols-outlined text-[20px]">verified</span>
                    </div>
                    <span className="text-slate-500 text-xs font-bold uppercase">Success Prob.</span>
                  </div>
                  <p className="text-2xl font-bold text-emerald-600 dark:text-emerald-400">87.4%</p>
                  <p className="text-xs text-slate-500 mt-1 font-medium">NPV &gt; 0</p>
                </div>
              </div>

              {/* Chart & Scatter Plot */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 min-h-[320px]">
                {/* NPV Histogram */}
                <div className="bg-white dark:bg-card-dark rounded-xl border border-slate-200 dark:border-border-dark p-5 flex flex-col shadow-sm">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">NPV Distribution</h3>
                    <div className="flex gap-2 text-xs">
                      <span className="flex items-center gap-1 text-slate-500"><div className="w-2 h-2 rounded-full bg-primary"></div>Frequency</span>
                      <span className="flex items-center gap-1 text-slate-500"><div className="w-2 h-2 rounded-full bg-red-400"></div>VaR Line</span>
                    </div>
                  </div>
                  <div className="flex-1 flex items-end justify-between gap-1 relative pl-2 pb-2 border-l border-b border-slate-200 dark:border-slate-700">
                    <div className="absolute top-0 bottom-0 left-[60%] w-px border-r border-dashed border-slate-400 dark:border-white/50 z-10 pointer-events-none"></div>
                    <div className="absolute top-2 left-[62%] text-[10px] text-slate-500 dark:text-white/50 font-mono font-bold">Mean</div>
                    <div className="w-full bg-primary/30 rounded-t-sm h-[5%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/30 rounded-t-sm h-[10%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/40 rounded-t-sm h-[15%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/50 rounded-t-sm h-[25%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/60 rounded-t-sm h-[40%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/70 rounded-t-sm h-[55%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/80 rounded-t-sm h-[75%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary rounded-t-sm h-[90%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary rounded-t-sm h-[85%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/80 rounded-t-sm h-[70%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/70 rounded-t-sm h-[50%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/60 rounded-t-sm h-[35%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/50 rounded-t-sm h-[20%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/40 rounded-t-sm h-[10%] hover:opacity-80 transition-opacity"></div>
                    <div className="w-full bg-primary/30 rounded-t-sm h-[5%] hover:opacity-80 transition-opacity"></div>
                  </div>
                  <div className="flex justify-between text-[10px] text-slate-500 mt-2 font-bold">
                    <span>-$1M</span>
                    <span>$0</span>
                    <span>+$5M</span>
                  </div>
                </div>

                {/* Interactive Scatter Plot Container */}
                <div className="bg-white dark:bg-card-dark rounded-xl border border-slate-200 dark:border-border-dark p-5 flex flex-col shadow-sm">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white">Risk Factor Analysis</h3>
                    <select className="bg-transparent border border-slate-200 dark:border-border-dark text-xs text-slate-600 dark:text-slate-400 rounded px-2 py-1 outline-none font-bold">
                      <option>Duration vs IRR</option>
                      <option>Cost vs NPV</option>
                    </select>
                  </div>
                  <div className="flex-1 relative border border-slate-100 dark:border-border-dark bg-slate-50/50 dark:bg-black/20 rounded-lg overflow-hidden">
                    <div className="absolute inset-0 grid grid-cols-4 grid-rows-4 pointer-events-none">
                      <div className="border-r border-b border-slate-200/50 dark:border-border-dark/50"></div>
                      <div className="border-r border-b border-slate-200/50 dark:border-border-dark/50"></div>
                      <div className="border-r border-b border-slate-200/50 dark:border-border-dark/50"></div>
                      <div className="border-b border-slate-200/50 dark:border-border-dark/50"></div>
                      <div className="border-r border-b border-slate-200/50 dark:border-border-dark/50"></div>
                      <div className="border-r border-b border-slate-200/50 dark:border-border-dark/50"></div>
                      <div className="border-r border-b border-slate-200/50 dark:border-border-dark/50"></div>
                      <div className="border-b border-slate-200/50 dark:border-border-dark/50"></div>
                    </div>
                    {/* Dots */}
                    <div className="absolute top-[20%] left-[30%] w-2.5 h-2.5 bg-primary rounded-full opacity-70 hover:scale-150 transition-transform cursor-pointer" title="Scenario 104"></div>
                    <div className="absolute top-[45%] left-[55%] w-2.5 h-2.5 bg-primary rounded-full opacity-70 hover:scale-150 transition-transform cursor-pointer" title="Scenario 992"></div>
                    <div className="absolute top-[30%] left-[40%] w-2.5 h-2.5 bg-primary rounded-full opacity-70 hover:scale-150 transition-transform cursor-pointer" title="Scenario 302"></div>
                    <div className="absolute top-[60%] left-[20%] w-2.5 h-2.5 bg-red-500 rounded-full opacity-90 hover:scale-150 transition-transform cursor-pointer shadow-sm" title="Scenario 881 (Failed)"></div>
                    <div className="absolute top-[15%] left-[75%] w-2.5 h-2.5 bg-emerald-500 rounded-full opacity-90 hover:scale-150 transition-transform cursor-pointer shadow-sm" title="Scenario 12 (Best)"></div>
                    <div className="absolute top-[35%] left-[65%] w-2.5 h-2.5 bg-primary rounded-full opacity-70 hover:scale-150 transition-transform cursor-pointer"></div>
                    <div className="absolute top-[50%] left-[50%] w-2.5 h-2.5 bg-primary rounded-full opacity-70 hover:scale-150 transition-transform cursor-pointer"></div>
                  </div>
                  <div className="flex justify-between items-center mt-2">
                    <span className="text-[10px] text-slate-500 font-bold">Low Duration</span>
                    <span className="text-[10px] text-slate-500 font-bold">Duration (Months)</span>
                    <span className="text-[10px] text-slate-500 font-bold">High Duration</span>
                  </div>
                </div>
              </div>

              {/* Scenario Analysis Table */}
              <div className="bg-white dark:bg-card-dark rounded-xl border border-slate-200 dark:border-border-dark overflow-hidden shadow-sm flex flex-col flex-1 min-h-[250px]">
                <div className="p-4 border-b border-slate-200 dark:border-border-dark flex justify-between items-center bg-slate-50 dark:bg-card-dark">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">Scenario Analysis (Top/Bottom 5)</h3>
                  <button className="text-xs font-bold text-primary hover:text-blue-600 transition-colors">View All Scenarios</button>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="text-slate-500 dark:text-slate-400 text-xs border-b border-slate-200 dark:border-border-dark bg-slate-50/50 dark:bg-[#1a202c]">
                        <th className="p-4 font-bold uppercase tracking-wider">Scenario ID</th>
                        <th className="p-4 font-bold uppercase tracking-wider">Duration</th>
                        <th className="p-4 font-bold uppercase tracking-wider">Cost Variance</th>
                        <th className="p-4 font-bold uppercase tracking-wider">Permit Status</th>
                        <th className="p-4 font-bold uppercase tracking-wider">Final NPV</th>
                        <th className="p-4 font-bold uppercase tracking-wider">IRR</th>
                      </tr>
                    </thead>
                    <tbody className="text-sm">
                      <tr className="border-b border-slate-100 dark:border-border-dark hover:bg-slate-50 dark:hover:bg-[#1e232e] group transition-colors cursor-pointer">
                        <td className="p-4 font-mono font-medium text-slate-600 dark:text-slate-400 group-hover:text-primary transition-colors">#0012</td>
                        <td className="p-4 text-slate-900 dark:text-white font-medium">22 Months</td>
                        <td className="p-4 text-emerald-500 font-bold">-2.5%</td>
                        <td className="p-4"><span className="px-2 py-1 rounded-md bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-500 text-[10px] font-bold uppercase tracking-wider">Approved</span></td>
                        <td className="p-4 font-bold text-slate-900 dark:text-white">$4,250,000</td>
                        <td className="p-4 font-bold text-emerald-500">24.1%</td>
                      </tr>
                      <tr className="border-b border-slate-100 dark:border-border-dark hover:bg-slate-50 dark:hover:bg-[#1e232e] group transition-colors cursor-pointer">
                        <td className="p-4 font-mono font-medium text-slate-600 dark:text-slate-400 group-hover:text-primary transition-colors">#0845</td>
                        <td className="p-4 text-slate-900 dark:text-white font-medium">24 Months</td>
                        <td className="p-4 text-slate-500 dark:text-slate-400 font-bold">0.0%</td>
                        <td className="p-4"><span className="px-2 py-1 rounded-md bg-emerald-100 dark:bg-emerald-500/10 text-emerald-700 dark:text-emerald-500 text-[10px] font-bold uppercase tracking-wider">Approved</span></td>
                        <td className="p-4 font-bold text-slate-900 dark:text-white">$2,100,000</td>
                        <td className="p-4 font-bold text-slate-500 dark:text-slate-400">14.2%</td>
                      </tr>
                      <tr className="border-b border-slate-100 dark:border-border-dark hover:bg-slate-50 dark:hover:bg-[#1e232e] group transition-colors cursor-pointer bg-red-50/50 dark:bg-red-500/5">
                        <td className="p-4 font-mono font-medium text-slate-600 dark:text-slate-400 group-hover:text-primary transition-colors">#4421</td>
                        <td className="p-4 text-slate-900 dark:text-white font-medium">12 Months</td>
                        <td className="p-4 text-slate-500 dark:text-slate-400 font-bold">--</td>
                        <td className="p-4"><span className="px-2 py-1 rounded-md bg-red-100 dark:bg-red-500/10 text-red-700 dark:text-red-500 text-[10px] font-bold uppercase tracking-wider">Rejected</span></td>
                        <td className="p-4 font-bold text-red-600 dark:text-red-500">-$2,500,000</td>
                        <td className="p-4 font-bold text-red-600 dark:text-red-500">-100%</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
