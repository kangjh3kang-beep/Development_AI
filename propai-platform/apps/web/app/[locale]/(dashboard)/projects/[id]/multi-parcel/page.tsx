"use client";

import { useParams } from "next/navigation";

export default function MultiParcelPage() {
  const { id } = useParams() as { id: string };

  return (
    <div className="cc-bracketed flex flex-1 overflow-hidden relative h-[calc(100vh-120px)] rounded-xl border border-[var(--line)] bg-[var(--surface-strong)]">
      <i className="cc-bracket cc-bracket--tl" aria-hidden /><i className="cc-bracket cc-bracket--tr" aria-hidden />
      <i className="cc-bracket cc-bracket--bl" aria-hidden /><i className="cc-bracket cc-bracket--br" aria-hidden />
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
          <div className="bg-[var(--surface-strong)] border border-[var(--line)] rounded-lg shadow-xl p-1.5 flex flex-col gap-1">
            <button aria-label="Select Tool" className="p-2.5 text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] rounded-md transition-colors tooltip-trigger group relative">
              <span className="material-symbols-outlined text-[20px]">near_me</span>
              <div className="absolute left-full ml-2 px-2 py-1 bg-[var(--surface)] text-xs text-[var(--text-primary)] rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none">Select</div>
            </button>
            <button className="p-2.5 text-[var(--data-accent)] bg-[var(--data-accent-soft)] rounded-md transition-colors group relative">
              <span className="material-symbols-outlined text-[20px]">draw</span>
              <div className="absolute left-full ml-2 px-2 py-1 bg-[var(--surface)] text-xs text-[var(--text-primary)] rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none">Draw Polygon</div>
            </button>
            <button className="p-2.5 text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] rounded-md transition-colors group relative">
              <span className="material-symbols-outlined text-[20px]">rectangle</span>
              <div className="absolute left-full ml-2 px-2 py-1 bg-[var(--surface)] text-xs text-[var(--text-primary)] rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none">Rectangle</div>
            </button>
            <div className="h-px w-full bg-[var(--line)] my-0.5"></div>
            <button className="p-2.5 text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] rounded-md transition-colors group relative">
              <span className="material-symbols-outlined text-[20px]">upload_file</span>
              <div className="absolute left-full ml-2 px-2 py-1 bg-[var(--surface)] text-xs text-[var(--text-primary)] rounded opacity-0 group-hover:opacity-100 whitespace-nowrap pointer-events-none">Upload DXF/GeoJSON</div>
            </button>
          </div>
        </div>

        {/* Layer Toggles */}
        <div className="absolute top-6 right-6 z-10">
          <div className="bg-[var(--surface-strong)] border border-[var(--line)] rounded-lg shadow-xl p-1 flex gap-1">
            <button className="px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] bg-[var(--surface-soft)] rounded hover:bg-[var(--surface)]">Map</button>
            <button className="px-3 py-1.5 text-xs font-medium text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-soft)] rounded transition-colors">Satellite</button>
            <button className="px-3 py-1.5 text-xs font-medium text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-soft)] rounded transition-colors">Zoning</button>
          </div>
        </div>

        {/* Map Zoom Controls */}
        <div className="absolute bottom-6 right-6 z-10 flex flex-col gap-2">
          <div className="bg-[var(--surface-strong)] border border-[var(--line)] rounded-lg shadow-xl flex flex-col overflow-hidden">
            <button className="p-3 text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] border-b border-[var(--line)] flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">add</span>
            </button>
            <button className="p-3 text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] border-b border-[var(--line)] flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">remove</span>
            </button>
            <button className="p-3 text-[var(--text-secondary)] hover:bg-[var(--surface-soft)] flex items-center justify-center">
              <span className="material-symbols-outlined text-[20px]">my_location</span>
            </button>
          </div>
        </div>

        {/* Scenario Manager Bar */}
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-10">
          <div className="bg-[var(--surface-strong)]/90 backdrop-blur border border-[var(--line)] rounded-full shadow-2xl px-4 py-2 flex items-center gap-4">
            <div className="flex items-center gap-2 border-r border-[var(--line)] pr-4">
              <span className="cc-label">Scenario A</span>
              <span className="text-xs text-[var(--status-success)] font-mono flex items-center gap-1">
                <span className="material-symbols-outlined text-[14px]">save</span> Saved
              </span>
            </div>
            <div className="flex gap-2">
              <button className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors" title="Undo">
                <span className="material-symbols-outlined text-[20px]">undo</span>
              </button>
              <button className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors" title="Redo">
                <span className="material-symbols-outlined text-[20px]">redo</span>
              </button>
            </div>
            <div className="h-4 w-px bg-[var(--line)]"></div>
            <button className="text-[var(--data-accent)] hover:opacity-80 text-sm font-bold flex items-center gap-2 transition-opacity">
              <span className="material-symbols-outlined text-[18px]">compare_arrows</span>
              Compare
            </button>
          </div>
        </div>
      </main>
      
      {/* Right Analysis Sidebar */}
      <aside className="w-[420px] bg-[var(--surface-strong)] border-l border-[var(--line)] flex flex-col z-20 shadow-2xl overflow-hidden shrink-0">
        {/* Sidebar Header */}
        <div className="px-6 py-5 border-b border-[var(--line)] flex justify-between items-start">
          <div>
            <span className="cc-meta">CONSOLIDATION · ANALYSIS</span>
            <h1 className="mt-1 text-[var(--text-primary)] text-lg font-bold tracking-tight">Consolidation Analysis</h1>
            <p className="text-[var(--text-tertiary)] text-xs mt-1">Real-time metrics for selected boundary.</p>
          </div>
          <div className="flex gap-2">
            <button className="p-1.5 text-[var(--text-tertiary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-soft)] rounded-md transition-colors">
              <span className="material-symbols-outlined text-[20px]">more_horiz</span>
            </button>
          </div>
        </div>
        
        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-8 no-scrollbar">
          {/* 1. Key Metrics Grid */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="cc-label">Parcel Metrics</h3>
              <span className="cc-live"><i />LIVE</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="cc-panel p-3">
                <div className="flex items-center gap-2 mb-1 text-[var(--text-tertiary)]">
                  <span className="material-symbols-outlined text-[18px]">square_foot</span>
                  <span className="cc-label">Total Area</span>
                </div>
                <div className="cc-num text-xl font-bold text-[var(--text-primary)]">45,200 <span className="text-sm font-normal text-[var(--text-tertiary)]">sq ft</span></div>
              </div>
              <div className="cc-panel p-3">
                <div className="flex items-center gap-2 mb-1 text-[var(--text-tertiary)]">
                  <span className="material-symbols-outlined text-[18px]">straighten</span>
                  <span className="cc-label">Frontage</span>
                </div>
                <div className="cc-num text-xl font-bold text-[var(--text-primary)]">120 <span className="text-sm font-normal text-[var(--text-tertiary)]">ft</span></div>
              </div>
              <div className="cc-panel p-3 col-span-2 relative overflow-hidden group">
                <div className="absolute right-0 top-0 p-3 opacity-10 group-hover:opacity-20 transition-opacity">
                  <span className="material-symbols-outlined text-6xl text-[var(--status-success)]">attach_money</span>
                </div>
                <div className="flex items-center gap-2 mb-1 text-[var(--text-tertiary)]">
                  <span className="material-symbols-outlined text-[18px]">currency_exchange</span>
                  <span className="cc-label">Est. Consolidated Value</span>
                </div>
                <div className="cc-num text-2xl font-bold text-[var(--status-success)]">$4,250,000</div>
                <div className="text-xs text-[var(--text-tertiary)] mt-1">+12% vs individual sum</div>
              </div>
            </div>
          </section>
          
          {/* 2. Feasibility Analysis */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="cc-label">Feasibility Checks</h3>
              <div className="flex items-center gap-1.5 bg-[var(--surface-soft)] px-2 py-1 rounded border border-[var(--line)]">
                <div className="size-2 rounded-full bg-[var(--status-success)] animate-pulse"></div>
                <span className="cc-num text-xs font-bold text-[var(--text-primary)]">85% Viable</span>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              {/* Check Item: Pass */}
              <div className="flex items-start gap-3 p-3 bg-[var(--surface-soft)] border border-[var(--line)] rounded-lg">
                <div className="mt-0.5 text-[var(--status-success)] bg-[var(--status-success)]/10 p-1 rounded-full">
                  <span className="material-symbols-outlined text-[16px] block">check</span>
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center">
                    <h4 className="text-sm font-medium text-[var(--text-primary)]">Adjacency</h4>
                    <span className="text-[10px] font-bold text-[var(--status-success)] uppercase">Pass</span>
                  </div>
                  <p className="text-xs text-[var(--text-tertiary)] mt-0.5">All selected parcels share contiguous boundaries.</p>
                </div>
              </div>
              {/* Check Item: Pass */}
              <div className="flex items-start gap-3 p-3 bg-[var(--surface-soft)] border border-[var(--line)] rounded-lg">
                <div className="mt-0.5 text-[var(--status-success)] bg-[var(--status-success)]/10 p-1 rounded-full">
                  <span className="material-symbols-outlined text-[16px] block">check</span>
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center">
                    <h4 className="text-sm font-medium text-[var(--text-primary)]">Zoning Compatibility</h4>
                    <span className="text-[10px] font-bold text-[var(--status-success)] uppercase">Pass</span>
                  </div>
                  <p className="text-xs text-[var(--text-tertiary)] mt-0.5">Combined parcels allow for C-2 Mixed Use.</p>
                </div>
              </div>
              {/* Check Item: Fail/Warn */}
              <div className="flex items-start gap-3 p-3 bg-[var(--surface-soft)] border border-[var(--status-warning)]/30 rounded-lg relative overflow-hidden">
                <div className="absolute left-0 top-0 bottom-0 w-1 bg-[var(--status-warning)]"></div>
                <div className="mt-0.5 text-[var(--status-warning)] bg-[var(--status-warning)]/10 p-1 rounded-full">
                  <span className="material-symbols-outlined text-[16px] block">priority_high</span>
                </div>
                <div className="flex-1">
                  <div className="flex justify-between items-center">
                    <h4 className="text-sm font-medium text-[var(--text-primary)]">Ownership Status</h4>
                    <span className="text-[10px] font-bold text-[var(--status-warning)] uppercase">Review</span>
                  </div>
                  <p className="text-xs text-[var(--text-tertiary)] mt-0.5">Multiple owners detected (3 entities).</p>
                  <button className="text-[10px] text-[var(--data-accent)] mt-2 font-medium hover:underline">View Owner Details</button>
                </div>
              </div>
            </div>
          </section>
          
          {/* 3. Incentives */}
          <section>
            <h3 className="cc-label mb-3">Applicable Incentives</h3>
            <div className="cc-panel rounded-lg overflow-hidden">
              <table className="w-full text-left text-sm">
                <thead className="bg-[var(--surface-soft)] text-[var(--text-tertiary)] text-xs">
                  <tr>
                    <th className="px-3 py-2 font-medium">Program</th>
                    <th className="px-3 py-2 font-medium text-right">Bonus</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--line-subtle)]">
                  <tr>
                    <td className="px-3 py-2 text-[var(--text-primary)]">Affordable Housing</td>
                    <td className="px-3 py-2 text-right text-[var(--status-success)] cc-num">+1.5 FAR</td>
                  </tr>
                  <tr>
                    <td className="px-3 py-2 text-[var(--text-primary)]">Transit Proximity</td>
                    <td className="px-3 py-2 text-right text-[var(--status-success)] cc-num">-15% Tax</td>
                  </tr>
                </tbody>
              </table>
              <div className="px-3 py-2 bg-[var(--surface-soft)] border-t border-[var(--line-subtle)] text-center">
                <a className="text-xs text-[var(--data-accent)] font-medium hover:opacity-80" href="#">View all 5 potential incentives</a>
              </div>
            </div>
          </section>

          {/* 4. Selected Parcels List */}
          <section>
            <div className="flex items-center justify-between mb-3">
              <h3 className="cc-label">Selected Parcels (3)</h3>
            </div>
            <ul className="space-y-2">
              <li className="flex items-center justify-between p-2 hover:bg-[var(--surface-soft)] rounded group transition-colors cursor-pointer border border-transparent hover:border-[var(--line)]">
                <div className="flex items-center gap-3">
                  <div className="size-2 rounded-full bg-[var(--data-accent)]"></div>
                  <div>
                    <div className="cc-num text-sm text-[var(--text-primary)]">APN 5521-012</div>
                    <div className="text-[10px] text-[var(--text-hint)]">12,400 sq ft • Commercial</div>
                  </div>
                </div>
                <button className="text-[var(--text-hint)] hover:text-[var(--status-error)] opacity-0 group-hover:opacity-100 transition-all">
                  <span className="material-symbols-outlined text-[18px]">delete</span>
                </button>
              </li>
              <li className="flex items-center justify-between p-2 hover:bg-[var(--surface-soft)] rounded group transition-colors cursor-pointer border border-transparent hover:border-[var(--line)]">
                <div className="flex items-center gap-3">
                  <div className="size-2 rounded-full bg-[var(--data-accent)]"></div>
                  <div>
                    <div className="cc-num text-sm text-[var(--text-primary)]">APN 5521-013</div>
                    <div className="text-[10px] text-[var(--text-hint)]">18,200 sq ft • Commercial</div>
                  </div>
                </div>
                <button className="text-[var(--text-hint)] hover:text-[var(--status-error)] opacity-0 group-hover:opacity-100 transition-all">
                  <span className="material-symbols-outlined text-[18px]">delete</span>
                </button>
              </li>
              <li className="flex items-center justify-between p-2 hover:bg-[var(--surface-soft)] rounded group transition-colors cursor-pointer border border-transparent hover:border-[var(--line)]">
                <div className="flex items-center gap-3">
                  <div className="size-2 rounded-full bg-[var(--data-accent)]"></div>
                  <div>
                    <div className="cc-num text-sm text-[var(--text-primary)]">APN 5521-014</div>
                    <div className="text-[10px] text-[var(--text-hint)]">14,600 sq ft • Residential</div>
                  </div>
                </div>
                <button className="text-[var(--text-hint)] hover:text-[var(--status-error)] opacity-0 group-hover:opacity-100 transition-all">
                  <span className="material-symbols-outlined text-[18px]">delete</span>
                </button>
              </li>
            </ul>
          </section>
        </div>

        {/* Sidebar Footer */}
        <div className="p-6 border-t border-[var(--line)] bg-[var(--surface-strong)] z-30">
          <button className="flex w-full cursor-pointer items-center justify-center rounded-lg h-12 px-4 bg-[var(--accent-strong)] hover:opacity-90 transition-all text-white text-sm font-bold leading-normal tracking-[0.015em] shadow-[var(--shadow-glow)]">
            <span className="material-symbols-outlined mr-2">assignment</span>
            <span className="truncate">Generate Consolidation Report</span>
          </button>
        </div>
      </aside>
    </div>
  );
}
