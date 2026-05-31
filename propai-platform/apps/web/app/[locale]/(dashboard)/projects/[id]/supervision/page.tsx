"use client";

import { useParams } from "next/navigation";

export default function SupervisionPage() {
  const { id } = useParams() as { id: string };

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-120px)] relative overflow-hidden bg-background-dark text-white rounded-xl border border-card-border">
      {/* Top Header */}
      <header className="h-16 border-b border-card-border bg-background-dark/95 backdrop-blur flex items-center justify-between px-6 shrink-0 z-20">
        <div className="flex items-center gap-4 text-white">
          {/* Breadcrumbs inline for space saving */}
          <div className="hidden md:flex items-center gap-2 text-sm">
            <span className="text-slate-400">Home</span>
            <span className="text-slate-600 text-xs material-symbols-outlined">chevron_right</span>
            <span className="text-slate-400">Project Alpha</span>
            <span className="text-slate-600 text-xs material-symbols-outlined">chevron_right</span>
            <span className="text-white font-medium">Supervision Hub</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="relative w-64 hidden sm:block">
            <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-[20px]">search</span>
            <input className="w-full bg-surface-dark border-none rounded-lg py-2 pl-10 pr-4 text-sm text-white focus:ring-1 focus:ring-primary placeholder-slate-500" placeholder="Search logs, alerts..." type="text"/>
          </div>
          <button className="relative p-2 text-slate-400 hover:text-white rounded-lg hover:bg-surface-dark transition-colors">
            <span className="material-symbols-outlined">notifications</span>
            <span className="absolute top-2 right-2 size-2 bg-red-500 rounded-full border-2 border-background-dark"></span>
          </button>
        </div>
      </header>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto p-6 scrollbar-hide">
        <div className="max-w-[1600px] mx-auto flex flex-col gap-6">
          {/* Page Heading & Actions */}
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h2 className="text-3xl font-bold text-white tracking-tight">Project Alpha: Block C</h2>
              <p className="text-slate-400 mt-1">Real-time monitoring and automation center</p>
            </div>
            <div className="flex gap-3">
              <button className="px-4 py-2 rounded-lg bg-surface-dark text-white border border-card-border hover:bg-card-border text-sm font-medium flex items-center gap-2 transition-colors">
                <span className="material-symbols-outlined text-[18px]">download</span> Export Report
              </button>
              <button className="px-4 py-2 rounded-lg bg-primary text-white hover:bg-blue-600 text-sm font-medium flex items-center gap-2 shadow-lg shadow-primary/20 transition-all">
                <span className="material-symbols-outlined text-[18px]">add</span> New Log Entry
              </button>
            </div>
          </div>

          {/* KPI Stats Row */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="p-5 rounded-xl bg-surface-dark border border-card-border relative overflow-hidden group">
              <div className="absolute right-0 top-0 p-4 opacity-10 group-hover:opacity-20 transition-opacity">
                <span className="material-symbols-outlined text-6xl text-primary">analytics</span>
              </div>
              <p className="text-slate-400 text-sm font-medium mb-1">Total Completion</p>
              <div className="flex items-end gap-2">
                <p className="text-3xl font-bold text-white">42%</p>
                <span className="text-emerald-400 text-xs font-medium mb-1 flex items-center">+2.4% <span className="material-symbols-outlined text-[14px]">arrow_upward</span></span>
              </div>
              <div className="w-full bg-slate-700 h-1 mt-4 rounded-full overflow-hidden">
                <div className="bg-primary h-full rounded-full" style={{width: "42%"}}></div>
              </div>
            </div>
            
            <div className="p-5 rounded-xl bg-surface-dark border border-card-border relative overflow-hidden">
              <p className="text-slate-400 text-sm font-medium mb-1">Days Remaining</p>
              <div className="flex items-end gap-2">
                <p className="text-3xl font-bold text-white">120</p>
                <span className="text-slate-500 text-xs font-medium mb-1">On Schedule</span>
              </div>
              <div className="flex gap-1 mt-4">
                <div className="h-1 flex-1 bg-emerald-500 rounded-full"></div>
                <div className="h-1 flex-1 bg-emerald-500 rounded-full"></div>
                <div className="h-1 flex-1 bg-slate-700 rounded-full"></div>
              </div>
            </div>
            
            <div className="p-5 rounded-xl bg-surface-dark border border-card-border relative overflow-hidden">
              <p className="text-slate-400 text-sm font-medium mb-1">Safety Score</p>
              <div className="flex items-end gap-2">
                <p className="text-3xl font-bold text-white">98</p>
                <span className="text-slate-400 text-sm font-medium mb-1">/ 100</span>
              </div>
              <p className="text-emerald-400 text-xs mt-2 flex items-center gap-1">
                <span className="material-symbols-outlined text-[16px]">check_circle</span> No incidents this week
              </p>
            </div>
            
            <div className="p-5 rounded-xl bg-surface-dark border border-card-border relative overflow-hidden">
              <p className="text-slate-400 text-sm font-medium mb-1">Manpower on Site</p>
              <div className="flex items-end gap-2">
                <p className="text-3xl font-bold text-white">145</p>
                <span className="text-slate-400 text-sm font-medium mb-1">Workers</span>
              </div>
              <div className="flex -space-x-2 mt-3 overflow-hidden">
                <img alt="Worker Avatar" className="inline-block h-6 w-6 rounded-full ring-2 ring-background-dark" src="https://lh3.googleusercontent.com/aida-public/AB6AXuBH8qDsz-W43Fbg3FZopas1jysQ77VZ25JeiMcMRDVgpLlzFP8LAw1OwKWhwlMyVju1niSMPURGaWS6AQt18BM8r_JMkg5WejpNrd2P7QQhwDcpzGUjy79w7enzNFaW_TPuFfOsyONUc2GzwqGOSS1UxU9k9YFPVywPDkG4v_TGTM2biOsFJrY1rmAvXWyEVPFLrrYuVbJ8lFkpH0bE01_YPZP1rXH-0EAanFvpzNU9laeQXY1B3d-PzK1qOtZ4LrGUQttJRRE_KBI"/>
                <img alt="Worker Avatar" className="inline-block h-6 w-6 rounded-full ring-2 ring-background-dark" src="https://lh3.googleusercontent.com/aida-public/AB6AXuBCR01dDXQBZZBrXzVI-wzls2rU-Z_P8L9XUD1SkOwuTtp954naCyO7vvWq5kjvm9wTK734_16lIT5RBmZYTQuGlg4PWPWB3-xGZdh9t511sXMf4aVogecdZzhyW9H3plvx0QxhxK5HL--8pR_RkqM2MC1SP9owz3Zuge7NCQiB4fZew2wjl2GRzrPUcc9v7S2SLrN4F2oH9SHt1t46s43E_OE5QRPY4Kwhn2Xy0fyFzGkq-J5kr-J1g_GNfFmA08SFq33Os5jx2yw"/>
                <img alt="Worker Avatar" className="inline-block h-6 w-6 rounded-full ring-2 ring-background-dark" src="https://lh3.googleusercontent.com/aida-public/AB6AXuDtpPlE9A3b69OA1mu7znfxVo-jZg4v_YnEfiqeiTxJ67LrT71SqUOfLIDcpildx8skJ8BdkKNruLsZpuVNY0Zy96reLoBN_vxcA380eLrET4lcczGubih5flSq2VX_S5VTmRADQPj9oKn0AbjXCEoi9JvXAE8QceXQRnDKplnQRYqmrnV3SGlSG45pAPZ6gfde3mUcttki37zBUNQnUfSATkPQh7-d2c_2CJsXPIYzdD4nSdhR_CjjrbnYVi6Hj43F0t6koBfu96o"/>
                <span className="h-6 w-6 rounded-full bg-slate-700 ring-2 ring-background-dark flex items-center justify-center text-[10px] text-white font-medium">+142</span>
              </div>
            </div>
          </div>

          {/* Main Grid Content */}
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
            {/* LEFT COLUMN: Operations & Visuals (Span 2) */}
            <div className="xl:col-span-2 flex flex-col gap-6">
              {/* Drone Feed Card */}
              <div className="bg-surface-dark rounded-xl border border-card-border overflow-hidden flex flex-col">
                <div className="p-4 border-b border-card-border flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="size-2 rounded-full bg-red-500 animate-pulse"></div>
                    <h3 className="text-white font-bold text-sm tracking-wide">LIVE DRONE SURVEILLANCE</h3>
                  </div>
                  <div className="flex bg-background-dark rounded-lg p-1">
                    <button className="px-3 py-1 rounded-md bg-slate-700 text-white text-xs font-medium">Live Feed</button>
                    <button className="px-3 py-1 rounded-md text-slate-400 hover:text-white text-xs font-medium transition-colors">BIM Model</button>
                  </div>
                </div>
                <div className="relative aspect-video w-full bg-black group">
                  {/* Video Placeholder */}
                  <div className="absolute inset-0 bg-cover bg-center opacity-80" style={{backgroundImage: "url('https://lh3.googleusercontent.com/aida-public/AB6AXuDDQ0qOdFFG2kXOXbaxbMZhjpWBXhbcX3gSR5kSfHVjfke2dMZ8k0G62NiDeX1LjI95KoHZs2D6gHEC9cuYs_VTt4M0BkNS-ODwAcy0lzJLIneWgCFiyamGKkjWVDzqMtq0bE-UVICawV0jP6TQbfSQDcf6AKCb8UzQqcgLINVuATj6Iz9eV-Hs3tWTzs9t6ZJicSFVTKjhSiOSyk0weyOk9YHFO2js9_iGbPY9K6KniBjQ6PAzbkbsuk68GIBB8fIU1VD-ga64aX4')"}}></div>
                  {/* Overlay UI */}
                  <div className="absolute top-4 left-4 bg-black/60 backdrop-blur px-2 py-1 rounded text-xs text-white font-mono border border-white/10">
                    CAM-04 • ALT: 45m • 4K
                  </div>
                  <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <button className="size-16 rounded-full bg-primary/90 text-white flex items-center justify-center hover:scale-105 transition-transform backdrop-blur-sm shadow-xl">
                      <span className="material-symbols-outlined text-3xl">play_arrow</span>
                    </button>
                  </div>
                  <div className="absolute bottom-0 left-0 right-0 p-4 bg-gradient-to-t from-black/80 to-transparent">
                    <div className="flex items-center justify-between text-white text-xs">
                      <p>Sector 4 Overview</p>
                      <p>Updated: 2 mins ago</p>
                    </div>
                  </div>
                </div>
              </div>

              {/* Task Progress List */}
              <div className="bg-surface-dark rounded-xl border border-card-border p-5">
                <h3 className="text-white font-bold text-sm tracking-wide mb-4">SITE PROGRESS TRACKER</h3>
                <div className="space-y-5">
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-white font-medium">Foundation & Substructure</span>
                      <span className="text-emerald-400 font-bold">100%</span>
                    </div>
                    <div className="w-full bg-slate-700 h-2 rounded-full overflow-hidden">
                      <div className="bg-emerald-500 h-full rounded-full" style={{width: "100%"}}></div>
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-white font-medium">Structural Framing</span>
                      <span className="text-primary font-bold">65%</span>
                    </div>
                    <div className="w-full bg-slate-700 h-2 rounded-full overflow-hidden">
                      <div className="bg-primary h-full rounded-full relative overflow-hidden" style={{width: "65%"}}>
                        <div className="absolute inset-0 bg-white/20 animate-[pulse_2s_infinite]"></div>
                      </div>
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-white font-medium">Electrical Rough-in</span>
                      <span className="text-amber-400 font-bold">22%</span>
                    </div>
                    <div className="w-full bg-slate-700 h-2 rounded-full overflow-hidden">
                      <div className="bg-amber-400 h-full rounded-full" style={{width: "22%"}}></div>
                    </div>
                  </div>
                  <div>
                    <div className="flex justify-between text-sm mb-1">
                      <span className="text-white font-medium">Plumbing & HVAC</span>
                      <span className="text-slate-500 font-bold">Pending</span>
                    </div>
                    <div className="w-full bg-slate-700 h-2 rounded-full overflow-hidden">
                      <div className="bg-slate-500 h-full rounded-full w-0"></div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Daily Log Entry */}
              <div className="bg-surface-dark rounded-xl border border-card-border p-5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-white font-bold text-sm tracking-wide">DAILY SITE LOG</h3>
                  <span className="text-xs text-slate-400">Oct 24, 2023</span>
                </div>
                <div className="flex flex-col gap-4">
                  <textarea className="w-full bg-background-dark border border-card-border rounded-lg p-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary resize-none h-24 transition-colors" placeholder="Enter today's site observations..."></textarea>
                  <div className="border-2 border-dashed border-card-border rounded-lg p-6 flex flex-col items-center justify-center text-center cursor-pointer hover:border-primary/50 hover:bg-background-dark transition-colors">
                    <span className="material-symbols-outlined text-slate-400 text-3xl mb-2">cloud_upload</span>
                    <p className="text-sm text-slate-300 font-medium">Drop site report or photos here</p>
                    <p className="text-xs text-slate-500 mt-1">PDF, JPG, PNG up to 10MB</p>
                  </div>
                </div>
              </div>
            </div>

            {/* RIGHT COLUMN: Analytics & Alerts (Span 1) */}
            <div className="flex flex-col gap-6">
              {/* Payment Automation */}
              <div className="bg-surface-dark rounded-xl border border-card-border p-5 flex flex-col">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-white font-bold text-sm tracking-wide">PROGRESS PAYMENT</h3>
                  <button className="text-primary hover:text-white transition-colors">
                    <span className="material-symbols-outlined">more_horiz</span>
                  </button>
                </div>
                <div className="flex items-center justify-center py-4 relative">
                  {/* Donut Chart Representation */}
                  <div className="size-40 rounded-full bg-gradient-to-tr from-primary to-blue-400 p-4 relative">
                    <div className="absolute inset-0 rounded-full" style={{background: "conic-gradient(#135bec 15%, transparent 0)", transform: "rotate(-90deg)"}}></div>
                    <div className="size-full bg-surface-dark rounded-full flex flex-col items-center justify-center z-10 relative">
                      <span className="text-slate-400 text-xs">Verified Value</span>
                      <span className="text-white text-xl font-bold">$125K</span>
                    </div>
                  </div>
                </div>
                <div className="space-y-3 mt-2">
                  <div className="flex justify-between items-center py-2 border-b border-card-border">
                    <span className="text-slate-400 text-sm">Completed Work</span>
                    <span className="text-white font-medium text-sm">15%</span>
                  </div>
                  <div className="flex justify-between items-center py-2 border-b border-card-border">
                    <span className="text-slate-400 text-sm">Eligible Payment</span>
                    <span className="text-white font-medium text-sm">$125,000</span>
                  </div>
                </div>
                <button className="mt-6 w-full py-3 bg-primary hover:bg-blue-600 text-white rounded-lg font-medium text-sm transition-colors shadow-lg shadow-primary/20 flex justify-center items-center gap-2">
                  <span className="material-symbols-outlined text-[18px]">receipt_long</span> Generate Certificate
                </button>
              </div>

              {/* Error & Alerts Panel */}
              <div className="bg-surface-dark rounded-xl border border-card-border flex flex-col flex-1">
                <div className="p-5 border-b border-card-border flex items-center justify-between">
                  <h3 className="text-white font-bold text-sm tracking-wide">ALERTS & DETECTIONS</h3>
                  <span className="bg-red-500/20 text-red-400 text-xs px-2 py-1 rounded font-medium">3 New</span>
                </div>
                <div className="flex-1 overflow-y-auto max-h-[500px] p-4 space-y-3">
                  {/* Alert Card 1 */}
                  <div className="bg-background-dark border border-red-500/30 rounded-lg p-3 hover:border-red-500/60 transition-colors cursor-pointer group">
                    <div className="flex items-start gap-3">
                      <div className="bg-red-500/20 p-2 rounded text-red-400 mt-0.5">
                        <span className="material-symbols-outlined text-[20px]">warning</span>
                      </div>
                      <div className="flex-1">
                        <h4 className="text-white text-sm font-medium leading-snug">BIM Deviation Detected</h4>
                        <p className="text-slate-400 text-xs mt-1 leading-relaxed">HVAC Ducting in Sector 4 does not match approved model.</p>
                        <div className="flex gap-2 mt-3">
                          <button className="text-xs bg-red-500 text-white px-3 py-1.5 rounded hover:bg-red-600 transition-colors">Review</button>
                          <button className="text-xs text-slate-400 hover:text-white px-2 py-1.5 transition-colors">Dismiss</button>
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Alert Card 2 */}
                  <div className="bg-background-dark border border-amber-500/30 rounded-lg p-3 hover:border-amber-500/60 transition-colors cursor-pointer">
                    <div className="flex items-start gap-3">
                      <div className="bg-amber-500/20 p-2 rounded text-amber-400 mt-0.5">
                        <span className="material-symbols-outlined text-[20px]">schedule</span>
                      </div>
                      <div className="flex-1">
                        <h4 className="text-white text-sm font-medium leading-snug">Schedule Slip Risk</h4>
                        <p className="text-slate-400 text-xs mt-1 leading-relaxed">Concrete curing delayed by 4h due to weather conditions.</p>
                        <div className="mt-2 text-xs text-amber-400 font-medium">Impact: +1 Day</div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Alert Card 3 */}
                  <div className="bg-background-dark border border-card-border rounded-lg p-3 hover:border-slate-500 transition-colors cursor-pointer">
                    <div className="flex items-start gap-3">
                      <div className="bg-slate-700 p-2 rounded text-slate-300 mt-0.5">
                        <span className="material-symbols-outlined text-[20px]">image</span>
                      </div>
                      <div className="flex-1">
                        <h4 className="text-white text-sm font-medium leading-snug">Missing Photo Log</h4>
                        <p className="text-slate-400 text-xs mt-1 leading-relaxed">Zone B daily photo documentation incomplete.</p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="p-3 border-t border-card-border text-center">
                  <button className="text-xs text-primary hover:text-white font-medium transition-colors">View All History</button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
