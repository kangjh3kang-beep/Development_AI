"use client";

import { useParams } from "next/navigation";

export default function MultiParcelPage() {
  const { id } = useParams() as { id: string };

  return (
    <div className="flex flex-1 overflow-hidden relative h-[calc(100vh-120px)] rounded-xl border border-card-border bg-[#0a0c10]">
      {/* Interactive Map Section */}
      <main className="flex-1 relative overflow-hidden group/map">
        {/* Map Background Layer */}
        <div className="absolute inset-0 z-0 opacity-80" style={{backgroundImage: "url('https://lh3.googleusercontent.com/aida-public/AB6AXuAUM72htFBp7obfKmYpAaOVvcDs18Qk2HFHQq8UY8qbsZc7Hn4WIwOAHCJl2Lf39XGVUXu2m0dLR52x49DTCrCtldX26Tx1ldqJllv_iiyfy_qqRzVGPjSBpag9dOgT3rIEv79S47LH2Ie-cJh4QYkLWwhJeVw3L3ZaDNmV66C_Q8n6kJHzk16ipIORXjbQHlmZKMHeIPePkDd-w7rTXIquPyOb5Z0qTXcKC68X4_pCRFMl9OIR2tqVqWXP2BLU9L5hryBc9jWCgZM')", backgroundSize: "cover", backgroundPosition: "center", filter: "grayscale(100%) invert(100%) hue-rotate(180deg) brightness(0.6) contrast(1.2)"}}></div>
        
        {/* Map Overlay (Simulated Data Layers) */}
        <div className="absolute inset-0 z-0 pointer-events-none">
          {/* SVG Visualization of Selected Parcels */}
          <svg className="w-full h-full opacity-90" style={{mixBlendMode: "screen"}}>
            <path d="M 400 300 L 600 280 L 650 450 L 380 480 Z" fill="rgba(19, 91, 236, 0.25)" stroke="#135bec" strokeDasharray="10 5" strokeWidth="3"></path>
            <circle cx="400" cy="300" fill="#135bec" r="5" stroke="white" strokeWidth="2"></circle>
            <circle cx="600" cy="280" fill="#135bec" r="5" stroke="white" strokeWidth="2"></circle>
            <circle cx="650" cy="450" fill="#135bec" r="5" stroke="white" strokeWidth="2"></circle>
            <circle cx="380" cy="480" fill="#135bec" r="5" stroke="white" strokeWidth="2"></circle>
            <foreignObject height="40" width="120" x="480" y="350">
              <div className="bg-black/80 backdrop-blur-sm text-white text-xs px-2 py-1 rounded text-center border border-primary">
                  Consolidated Site <br/> 45,200 sq ft
              </div>
            </foreignObject>
          </svg>
        </div>
        
        {/* Floating Drawing Toolbar */}
        <div className="absolute top-6 left-6 z-10 flex flex-col gap-2">
          <div className="bg-[#1c1f27] border border-[#282e39] rounded-lg shadow-xl p-1.5 flex flex-col gap-1">
            <button aria-label="Select Tool" className="p-2.5 text-white hover:bg-[#282e39] rounded-md transition-colors tooltip-trigger group relative">
              <span className="material-symbols-outlined text-[20px]">near_me</span>
              <div className="absolute left-full ml-2 px-2 py-1 bg-black text-xs text-white rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none">Select</div>
            </button>
            <button className="p-2.5 text-primary bg-[#135bec]/10 rounded-md transition-colors group relative">
              <span className="material-symbols-outlined text-[20px]">draw</span>
              <div className="absolute left-full ml-2 px-2 py-1 bg-black text-xs text-white rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none">Draw Polygon</div>
            </button>
            <button className="p-2.5 text-white hover:bg-[#282e39] rounded-md transition-colors group relative">
              <span className="material-symbols-outlined text-[20px]">rectangle</span>
              <div className="absolute left-full ml-2 px-2 py-1 bg-black text-xs text-white rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none">Rectangle</div>
            </button>
            <div className="h-px w-full bg-[#282e39] my-0.5"></div>
            <button className="p-2.5 text-white hover:bg-[#282e39] rounded-md transition-colors group relative">
              <span className="material-symbols-outlined text-[20px]">upload_file</span>
              <div className="absolute left-full ml-2 px-2 py-1 bg-black text-xs text-white rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none">Upload DXF/GeoJSON</div>
            </button>
          </div>
        </div>
        
        {/* Layer Toggles */}
        <div className="absolute top-6 right-6 z-10">
          <div className="bg-[#1c1f27] border border-[#282e39] rounded-lg shadow-xl p-1 flex gap-1">
            <button className="px-3 py-1.5 text-xs font-medium text-white bg-[#282e39] rounded hover:bg-[#323945]">Map</button>
            <button className="px-3 py-1.5 text-xs font-medium text-[#9da6b9] hover:text-white hover:bg-[#282e39] rounded transition-colors">Satellite</button>
            <button className="px-3 py-1.5 text-xs font-medium text-[#9da6b9] hover:text-white hover:bg-[#282e39] rounded transition-colors">Zoning</button>
          </div>
        </div>
        
        {/* Map Zoom Controls */}
        <div className="absolute bottom-6 right-6 z-10 flex flex-col gap-2">
          <div className="bg-[#1c1f27] border border-[#282e39] rounded-lg shadow-xl flex flex-col overflow-hidden">
            <button className="p-3 text-white hover:bg-[#282e39] border-b border-[#282e39] flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">add</span>
            </button>
            <button className="p-3 text-white hover:bg-[#282e39] border-b border-[#282e39] flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">remove</span>
            </button>
            <button className="p-3 text-white hover:bg-[#282e39] flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">my_location</span>
            </button>
          </div>
        </div>
        
        {/* Scenario Manager Bar */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10">
          <div className="bg-[#1c1f27]/90 backdrop-blur border border-[#282e39] rounded-full shadow-2xl px-4 py-2 flex items-center gap-4">
            <div className="flex items-center gap-2 border-r border-[#3b4354] pr-4">
              <span className="text-[#9da6b9] text-xs uppercase tracking-wider font-semibold">Scenario A</span>
              <span className="text-xs text-green-400 font-mono flex items-center gap-1">
                <span className="material-symbols-outlined text-[14px]">save</span> Saved
              </span>
            </div>
            <div className="flex gap-2">
              <button className="text-[#9da6b9] hover:text-white transition-colors" title="Undo">
                <span className="material-symbols-outlined text-[20px]">undo</span>
              </button>
              <button className="text-[#9da6b9] hover:text-white transition-colors" title="Redo">
                <span className="material-symbols-outlined text-[20px]">redo</span>
              </button>
            </div>
            <div className="h-4 w-px bg-[#3b4354]"></div>
            <button className="text-primary hover:text-primary/80 text-sm font-bold flex items-center gap-2 transition-colors">
              <span className="material-symbols-outlined text-[18px]">compare_arrows</span>
              Compare
            </button>
          </div>
        </div>
      </main>
      
      {/* Right Analysis Sidebar */}
      <aside className="w-[420px] bg-[#111318] border-l border-[#282e39] flex flex-col z-20 shadow-2xl overflow-hidden shrink-0">
        {/* Sidebar Header */}
        <div className="px-6 py-5 border-b border-[#282e39] flex justify-between items-start">
          <div>
            <h1 className="text-white text-lg font-bold tracking-tight">Consolidation Analysis</h1>
            <p className="text-[#9da6b9] text-xs mt-1">Real-time metrics for selected boundary.</p>
          </div>
          <div className="flex gap-2">
            <button className="p-1.5 text-[#9da6b9] hover:text-white hover:bg-[#282e39] rounded-md transition-colors">
              <span className="material-symbols-outlined text-[20px]">more_horiz</span>
            </button>
          </div>
        </div>
        
        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-8 no-scrollbar">
          {/* 1. Key Metrics Grid */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[#9da6b9] text-xs font-bold uppercase tracking-widest">Parcel Metrics</h3>
              <span className="text-[10px] bg-primary/20 text-primary px-1.5 py-0.5 rounded border border-primary/30">LIVE</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="bg-[#1c1f27] border border-[#282e39] p-3 rounded-lg">
                <div className="flex items-center gap-2 mb-1 text-[#9da6b9]">
                  <span className="material-symbols-outlined text-[18px]">square_foot</span>
                  <span className="text-xs font-medium">Total Area</span>
                </div>
                <div className="text-xl font-bold text-white font-display">45,200 <span className="text-sm font-normal text-[#9da6b9]">sq ft</span></div>
              </div>
              <div className="bg-[#1c1f27] border border-[#282e39] p-3 rounded-lg">
                <div className="flex items-center gap-2 mb-1 text-[#9da6b9]">
                  <span className="material-symbols-outlined text-[18px]">straighten</span>
                  <span className="text-xs font-medium">Frontage</span>
                </div>
                <div className="text-xl font-bold text-white font-display">120 <span className="text-sm font-normal text-[#9da6b9]">ft</span></div>
              </div>
              <div className="bg-[#1c1f27] border border-[#282e39] p-3 rounded-lg col-span-2 relative overflow-hidden group">
                <div className="absolute right-0 top-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                  <span className="material-symbols-outlined text-6xl text-emerald-500">attach_money</span>
                </div>
                <div className="flex items-center gap-2 mb-1 text-[#9da6b9]">
                  <span className="material-symbols-outlined text-[18px]">currency_exchange</span>
                  <span className="text-xs font-medium">Est. Consolidated Value</span>
                </div>
                <div className="text-2xl font-bold text-white font-display text-emerald-400">$4,250,000</div>
                <div className="text-xs text-[#9da6b9] mt-1">+12% vs individual sum</div>
              </div>
            </div>
          </section>
          
          {/* 2. Feasibility Analysis */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[#9da6b9] text-xs font-bold uppercase tracking-widest">Feasibility Checks</h3>
              <div className="flex items-center gap-1.5 bg-[#1c1f27] px-2 py-1 rounded border border-[#282e39]">
                <div className="size-2 rounded-full bg-emerald-500 animate-pulse"></div>
                <span className="text-xs font-bold text-white">85% Viable</span>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              {/* Check Item: Pass */}
              <div className="flex items-start gap-3 p-3 bg-[#1c1f27]/50 border border-[#282e39] rounded-lg">
                <div className="mt-0.5 text-emerald-500 bg-emerald-500/10 p-1 rounded-full">
                  <span className="material-symbols-outlined text-[16px] block">check</span>
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center">
                    <h4 className="text-sm font-medium text-white">Adjacency</h4>
                    <span className="text-[10px] font-bold text-emerald-500 uppercase">Pass</span>
                  </div>
                  <p className="text-xs text-[#9da6b9] mt-0.5">All selected parcels share contiguous boundaries.</p>
                </div>
              </div>
              {/* Check Item: Pass */}
              <div className="flex items-start gap-3 p-3 bg-[#1c1f27]/50 border border-[#282e39] rounded-lg">
                <div className="mt-0.5 text-emerald-500 bg-emerald-500/10 p-1 rounded-full">
                  <span className="material-symbols-outlined text-[16px] block">check</span>
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center">
                    <h4 className="text-sm font-medium text-white">Zoning Compatibility</h4>
                    <span className="text-[10px] font-bold text-emerald-500 uppercase">Pass</span>
                  </div>
                  <p className="text-xs text-[#9da6b9] mt-0.5">Combined parcels allow for C-2 Mixed Use.</p>
                </div>
              </div>
              {/* Check Item: Fail/Warn */}
              <div className="flex items-start gap-3 p-3 bg-[#1c1f27]/50 border border-orange-500/30 rounded-lg relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-orange-500"></div>
                <div className="mt-0.5 text-orange-500 bg-orange-500/10 p-1 rounded-full">
                  <span className="material-symbols-outlined text-[16px] block">priority_high</span>
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center">
                    <h4 className="text-sm font-medium text-white">Ownership Status</h4>
                    <span className="text-[10px] font-bold text-orange-500 uppercase">Review</span>
                  </div>
                  <p className="text-xs text-[#9da6b9] mt-0.5">Multiple owners detected (3 entities).</p>
                  <button className="text-[10px] text-primary mt-2 font-medium hover:underline">View Owner Details</button>
                </div>
              </div>
            </div>
          </section>
          
          {/* 3. Incentives */}
          <section>
            <h3 className="text-[#9da6b9] text-xs font-bold uppercase tracking-widest mb-3">Applicable Incentives</h3>
            <div className="bg-[#1c1f27] rounded-lg border border-[#282e39] overflow-hidden">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#282e39] text-[#9da6b9] text-xs">
                  <tr>
                    <th className="px-3 py-2 font-medium">Program</th>
                    <th className="px-3 py-2 font-medium text-right">Bonus</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#282e39]">
                  <tr>
                    <td className="px-3 py-2 text-white">Affordable Housing</td>
                    <td className="px-3 py-2 text-right text-emerald-400 font-mono">+1.5 FAR</td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2 text-white">Transit Proximity</td>
                    <td className="px-3 py-2 text-right text-emerald-400 font-mono">-15% Tax</td>
                  </tr>
                </tbody>
              </table>
              <div className="px-3 py-2 bg-[#1c1f27] border-t border-[#282e39] text-center">
                <a className="text-xs text-primary font-medium hover:text-primary/80" href="#">View all 5 potential incentives</a>
              </div>
            </div>
          </section>
          
          {/* 4. Selected Parcels List */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[#9da6b9] text-xs font-bold uppercase tracking-widest">Selected Parcels (3)</h3>
            </div>
            <ul className="space-y-2">
              <li className="flex items-center justify-between p-2 hover:bg-[#1c1f27] rounded group transition-colors cursor-pointer border border-transparent hover:border-[#282e39]">
                <div className="flex items-center gap-3">
                  <div className="size-2 rounded-full bg-primary"></div>
                  <div>
                    <div className="text-sm text-white font-mono">APN 5521-012</div>
                    <div className="text-[10px] text-[#586173]">12,400 sq ft • Commercial</div>
                  </div>
                </div>
                <button className="text-[#586173] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all">
                  <span className="material-symbols-outlined text-[18px]">delete</span>
                </button>
              </li>
              <li className="flex items-center justify-between p-2 hover:bg-[#1c1f27] rounded group transition-colors cursor-pointer border border-transparent hover:border-[#282e39]">
                <div className="flex items-center gap-3">
                  <div className="size-2 rounded-full bg-primary"></div>
                  <div>
                    <div className="text-sm text-white font-mono">APN 5521-013</div>
                    <div className="text-[10px] text-[#586173]">18,200 sq ft • Commercial</div>
                  </div>
                </div>
                <button className="text-[#586173] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all">
                  <span className="material-symbols-outlined text-[18px]">delete</span>
                </button>
              </li>
              <li className="flex items-center justify-between p-2 hover:bg-[#1c1f27] rounded group transition-colors cursor-pointer border border-transparent hover:border-[#282e39]">
                <div className="flex items-center gap-3">
                  <div className="size-2 rounded-full bg-primary"></div>
                  <div>
                    <div className="text-sm text-white font-mono">APN 5521-014</div>
                    <div className="text-[10px] text-[#586173]">14,600 sq ft • Residential</div>
                  </div>
                </div>
                <button className="text-[#586173] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all">
                  <span className="material-symbols-outlined text-[18px]">delete</span>
                </button>
              </li>
            </ul>
          </section>
        </div>
        
        {/* Sidebar Footer */}
        <div className="p-6 border-t border-[#282e39] bg-[#111318] z-30">
          <button className="flex w-full cursor-pointer items-center justify-center rounded-lg h-12 px-4 bg-primary hover:bg-blue-600 transition-colors text-white text-sm font-bold leading-normal tracking-[0.015em] shadow-[0_0_15px_rgba(19,91,236,0.3)]">
            <span className="material-symbols-outlined mr-2">assignment</span>
            <span className="truncate">Generate Consolidation Report</span>
          </button>
        </div>
      </aside>
    </div>
  );
}
