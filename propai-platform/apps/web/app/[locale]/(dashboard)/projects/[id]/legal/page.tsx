"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

export default function LegalPage() {
  const { id } = useParams() as { id: string };
  const [activeTab, setActiveTab] = useState("current");
  
  return (
    <div className="flex h-[calc(100vh-120px)] w-full overflow-hidden rounded-xl border border-slate-200 dark:border-border-dark bg-white dark:bg-background-dark font-display text-slate-900 dark:text-white shadow-sm">
      {/* Left Panel: Report & List */}
      <div className="flex flex-col flex-1 min-w-0 border-r border-slate-200 dark:border-border-dark overflow-y-auto">
        {/* Page Header */}
        <div className="px-6 py-5 border-b border-slate-200 dark:border-border-dark bg-slate-50/95 dark:bg-background-dark/95 backdrop-blur sticky top-0 z-10">
          <div className="flex flex-wrap justify-between items-end gap-4">
            <div className="flex flex-col gap-1">
              <h1 className="text-slate-900 dark:text-white text-3xl font-bold tracking-tight">Regulation Compliance Audit</h1>
              <div className="flex items-center gap-2 text-slate-500 dark:text-slate-400 text-sm">
                <span className="font-medium">Project ID: {id}</span>
                <span className="size-1 rounded-full bg-slate-300 dark:bg-slate-600"></span>
                <span>Iteration #42</span>
                <span className="size-1 rounded-full bg-slate-300 dark:bg-slate-600"></span>
                <span className="text-emerald-500 dark:text-emerald-400 flex items-center gap-1 font-bold">
                  <span className="size-2 rounded-full bg-emerald-500 dark:bg-emerald-400 animate-pulse"></span>
                  AI Analysis Active
                </span>
              </div>
            </div>
            <div className="flex gap-3">
              <button className="flex items-center gap-2 h-9 px-4 rounded-lg border border-slate-200 dark:border-border-dark bg-white dark:bg-surface-dark text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-border-dark transition-colors text-sm font-medium shadow-sm">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/></svg>
                Export Report
              </button>
            </div>
          </div>
          {/* Tabs */}
          <div className="mt-6 flex">
            <div className="flex p-1 bg-slate-100 dark:bg-surface-dark rounded-lg border border-slate-200 dark:border-border-dark">
              <button onClick={() => setActiveTab("current")} className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${activeTab === 'current' ? 'bg-white dark:bg-background-dark text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}`}>Current Review</button>
              <button onClick={() => setActiveTab("history")} className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${activeTab === 'history' ? 'bg-white dark:bg-background-dark text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}`}>Regulation History</button>
              <button onClick={() => setActiveTab("rules")} className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${activeTab === 'rules' ? 'bg-white dark:bg-background-dark text-slate-900 dark:text-white shadow-sm' : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}`}>Custom Rules</button>
            </div>
          </div>
        </div>
        
        {/* Compliance Table */}
        <div className="p-6">
          <div className="rounded-xl border border-slate-200 dark:border-border-dark bg-white dark:bg-surface-dark overflow-hidden shadow-sm">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-slate-50 dark:bg-[#222630] border-b border-slate-200 dark:border-border-dark">
                  <th className="px-5 py-3 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Regulation</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider w-32">Status</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Actual</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Limit</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">Explanation</th>
                  <th className="px-5 py-3 text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-border-dark">
                {/* Violation Row */}
                <tr className="group hover:bg-slate-50 dark:hover:bg-white/5 transition-colors cursor-pointer bg-red-50 dark:bg-red-500/5">
                  <td className="px-5 py-4 text-slate-900 dark:text-white font-medium flex items-center gap-2">
                    <svg className="text-red-500 shrink-0" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
                    North-Side Setback
                  </td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center rounded-md bg-red-100 dark:bg-red-400/10 px-2 py-1 text-xs font-bold text-red-600 dark:text-red-400 ring-1 ring-inset ring-red-500/20 dark:ring-red-400/20">Violation</span>
                  </td>
                  <td className="px-5 py-4 text-slate-700 dark:text-slate-300 font-mono text-sm">1.2m</td>
                  <td className="px-5 py-4 text-slate-500 dark:text-slate-400 font-mono text-sm">Min 1.5m</td>
                  <td className="px-5 py-4 text-slate-600 dark:text-slate-300 text-sm">Intrusion on Floors 4-5 caused by balcony extension.</td>
                  <td className="px-5 py-4 text-right">
                    <button className="text-primary hover:text-blue-600 dark:hover:text-blue-400 text-sm font-bold flex items-center justify-end gap-1 w-full transition-colors">
                      Resolve <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6"/></svg>
                    </button>
                  </td>
                </tr>
                {/* Warning Row */}
                <tr className="group hover:bg-slate-50 dark:hover:bg-white/5 transition-colors cursor-pointer">
                  <td className="px-5 py-4 text-slate-900 dark:text-white font-medium flex items-center gap-2">
                    <svg className="text-amber-500 shrink-0" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>
                    Sunlight Rights
                  </td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center rounded-md bg-amber-100 dark:bg-amber-400/10 px-2 py-1 text-xs font-bold text-amber-600 dark:text-amber-400 ring-1 ring-inset ring-amber-500/20 dark:ring-amber-400/20">Warning</span>
                  </td>
                  <td className="px-5 py-4 text-slate-700 dark:text-slate-300 font-mono text-sm">2h 05m</td>
                  <td className="px-5 py-4 text-slate-500 dark:text-slate-400 font-mono text-sm">Min 2h 00m</td>
                  <td className="px-5 py-4 text-slate-600 dark:text-slate-300 text-sm">Close to threshold on Winter Solstice.</td>
                  <td className="px-5 py-4 text-right">
                    <button className="text-slate-400 group-hover:text-primary transition-colors text-sm font-bold">Check</button>
                  </td>
                </tr>
                {/* Compliant Row */}
                <tr className="group hover:bg-slate-50 dark:hover:bg-white/5 transition-colors cursor-pointer">
                  <td className="px-5 py-4 text-slate-900 dark:text-white font-medium flex items-center gap-2">
                    <svg className="text-emerald-500 shrink-0" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
                    Building Coverage Ratio
                  </td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center rounded-md bg-emerald-100 dark:bg-emerald-400/10 px-2 py-1 text-xs font-bold text-emerald-700 dark:text-emerald-400 ring-1 ring-inset ring-emerald-500/20 dark:ring-emerald-400/20">Compliant</span>
                  </td>
                  <td className="px-5 py-4 text-slate-700 dark:text-slate-300 font-mono text-sm">48.5%</td>
                  <td className="px-5 py-4 text-slate-500 dark:text-slate-400 font-mono text-sm">Max 50%</td>
                  <td className="px-5 py-4 text-slate-500 dark:text-slate-400 text-sm">Within zoning limits.</td>
                  <td className="px-5 py-4 text-right">
                    <button className="text-slate-400 group-hover:text-slate-700 dark:text-slate-500 dark:group-hover:text-white text-sm font-bold transition-colors">View</button>
                  </td>
                </tr>
                {/* Compliant Row */}
                <tr className="group hover:bg-slate-50 dark:hover:bg-white/5 transition-colors cursor-pointer">
                  <td className="px-5 py-4 text-slate-900 dark:text-white font-medium flex items-center gap-2">
                    <svg className="text-emerald-500 shrink-0" xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/></svg>
                    Floor Area Ratio
                  </td>
                  <td className="px-5 py-4">
                    <span className="inline-flex items-center rounded-md bg-emerald-100 dark:bg-emerald-400/10 px-2 py-1 text-xs font-bold text-emerald-700 dark:text-emerald-400 ring-1 ring-inset ring-emerald-500/20 dark:ring-emerald-400/20">Compliant</span>
                  </td>
                  <td className="px-5 py-4 text-slate-700 dark:text-slate-300 font-mono text-sm">198%</td>
                  <td className="px-5 py-4 text-slate-500 dark:text-slate-400 font-mono text-sm">Max 200%</td>
                  <td className="px-5 py-4 text-slate-500 dark:text-slate-400 text-sm">Optimal usage achieved.</td>
                  <td className="px-5 py-4 text-right">
                    <button className="text-slate-400 group-hover:text-slate-700 dark:text-slate-500 dark:group-hover:text-white text-sm font-bold transition-colors">View</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
      
      {/* Right Panel: Visualization & Action */}
      <div className="w-[480px] shrink-0 border-l border-slate-200 dark:border-border-dark bg-slate-50 dark:bg-surface-dark flex flex-col h-full z-10">
        {/* 3D Visualization Area */}
        <div className="h-1/2 relative group w-full bg-slate-200 dark:bg-[#0f1115]">
          <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
            <button className="size-8 rounded bg-white/80 dark:bg-surface-dark/80 hover:bg-primary text-slate-600 hover:text-white dark:text-white flex items-center justify-center backdrop-blur border border-slate-300 dark:border-white/10 transition-colors shadow-sm">
              <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2v20"/><path d="m17 7-5-5-5 5"/><path d="m17 17-5 5-5-5"/></svg>
            </button>
          </div>
          <div className="absolute top-4 right-4 z-10">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-500/90 text-white shadow-lg backdrop-blur">
              <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/></svg>
              <span className="text-xs font-bold uppercase tracking-wide">Setback Violation</span>
            </div>
          </div>
          
          <div className="w-full h-full bg-cover bg-center" style={{ backgroundImage: 'linear-gradient(to bottom, rgba(15, 17, 21, 0.1), rgba(15, 17, 21, 0.8)), url("https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?q=80&w=2070&auto=format&fit=crop")' }}></div>
          
          <div className="absolute bottom-4 left-4 right-4 z-10">
            <div className="p-3 bg-white/80 dark:bg-black/60 backdrop-blur rounded-lg border border-slate-200 dark:border-white/10 text-xs text-slate-600 dark:text-slate-300 shadow-lg">
              <p><span className="text-slate-900 dark:text-white font-bold">Location:</span> North Facade, Floor 4-5</p>
              <p><span className="text-slate-900 dark:text-white font-bold">Deviation:</span> -0.3m beyond limit</p>
            </div>
          </div>
        </div>
        
        {/* Violation Details & Fixes */}
        <div className="flex-1 overflow-y-auto bg-slate-50 dark:bg-surface-dark flex flex-col">
          <div className="px-6 py-4 border-b border-slate-200 dark:border-border-dark bg-white dark:bg-transparent">
            <h3 className="text-slate-900 dark:text-white font-bold text-lg leading-tight mb-1">North-Side Setback Violation</h3>
            <p className="text-slate-500 dark:text-slate-400 text-sm">Section 12.4.b - High-rise residential zones</p>
          </div>
          
          <div className="p-6 flex flex-col gap-6">
            <div className="flex items-center justify-between">
              <h4 className="text-slate-900 dark:text-white text-sm font-bold uppercase tracking-wider flex items-center gap-2">
                <svg className="text-primary shrink-0" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72"/><path d="m14 7 3 3"/><path d="M5 6v4"/><path d="M19 14v4"/><path d="M10 2v2"/><path d="M7 8H3"/><path d="M21 16h-4"/><path d="M11 3H9"/></svg>
                AI Auto-Correction Options
              </h4>
              <span className="text-xs text-slate-500 font-medium">2 suggestions found</span>
            </div>
            
            {/* Option 1 */}
            <div className="rounded-xl border border-primary/40 dark:border-primary/50 bg-primary/5 p-4 relative overflow-hidden transition-all hover:shadow-[0_0_15px_rgba(19,91,236,0.15)] group cursor-pointer">
              <div className="absolute top-0 right-0 p-2 opacity-100 transition-opacity">
                <div className="bg-primary text-white text-[10px] font-bold px-2 py-0.5 rounded uppercase">Recommended</div>
              </div>
              <div className="flex gap-4">
                <div className="flex-1">
                  <h5 className="text-slate-900 dark:text-white font-bold text-base mb-1">Recess Upper Floors</h5>
                  <p className="text-slate-600 dark:text-slate-400 text-sm mb-3 leading-relaxed">Automatically recess the facade on floors 4 and 5 by 0.3m to meet the 1.5m setback requirement.</p>
                  <div className="flex gap-4 mb-4">
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-slate-500 font-bold">Floor Area Loss</span>
                      <span className="text-red-500 dark:text-red-400 text-sm font-mono font-bold">-15.2 m²</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-slate-500 font-bold">Cost Impact</span>
                      <span className="text-emerald-500 dark:text-emerald-400 text-sm font-mono font-bold">Minimal</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button className="flex-1 h-8 rounded bg-white dark:bg-background-dark border border-slate-300 dark:border-border-dark text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:border-slate-400 dark:hover:border-slate-500 text-xs font-bold transition-colors shadow-sm">
                      Preview on Model
                    </button>
                    <button className="flex-1 h-8 rounded bg-primary text-white shadow hover:bg-blue-600 text-xs font-bold transition-colors">
                      Apply Fix
                    </button>
                  </div>
                </div>
              </div>
            </div>
            
            {/* Option 2 */}
            <div className="rounded-xl border border-slate-200 dark:border-border-dark bg-white dark:bg-background-dark p-4 transition-all hover:border-slate-300 dark:hover:border-slate-600 shadow-sm cursor-pointer">
              <div className="flex gap-4">
                <div className="flex-1">
                  <h5 className="text-slate-900 dark:text-white font-bold text-base mb-1">Shift Building Axis</h5>
                  <p className="text-slate-600 dark:text-slate-400 text-sm mb-3 leading-relaxed">Shift the entire building structure 0.3m south. Requires re-evaluating South-side clearance.</p>
                  <div className="flex gap-4 mb-4">
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-slate-500 font-bold">Floor Area Loss</span>
                      <span className="text-emerald-500 dark:text-emerald-400 text-sm font-mono font-bold">0 m²</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-[10px] uppercase text-slate-500 font-bold">Complexity</span>
                      <span className="text-amber-500 dark:text-amber-400 text-sm font-mono font-bold">High</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button className="flex-1 h-8 rounded bg-slate-50 dark:bg-background-dark border border-slate-200 dark:border-border-dark text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:border-slate-300 dark:hover:border-slate-500 text-xs font-bold transition-colors">
                      Preview on Model
                    </button>
                    <button className="flex-1 h-8 rounded bg-slate-100 dark:bg-surface-dark border border-slate-200 dark:border-border-dark hover:bg-slate-200 dark:hover:bg-border-dark text-slate-900 dark:text-white text-xs font-bold transition-colors">
                      Apply Fix
                    </button>
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
