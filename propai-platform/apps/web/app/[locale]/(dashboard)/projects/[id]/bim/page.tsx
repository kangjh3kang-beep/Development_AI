"use client";

import { useParams } from "next/navigation";
import { useState } from "react";

export default function BimCostPage() {
  const { id } = useParams() as { id: string };
  const [activeTab, setActiveTab] = useState("cost");

  return (
    <div className="flex-1 flex flex-col min-w-0 h-[calc(100vh-120px)] border border-slate-200 dark:border-border-dark rounded-xl overflow-hidden">
      {/* Toolbar & Breadcrumbs */}
      <div className="flex flex-col border-b border-slate-200 dark:border-border-dark bg-white dark:bg-[#111318] shrink-0">
        {/* Breadcrumbs */}
        <div className="flex items-center px-6 py-2 gap-2 text-xs">
          <a className="text-slate-500 dark:text-slate-400 hover:text-primary" href="#">Project Alpha</a>
          <span className="text-slate-300 dark:text-slate-600">/</span>
          <a className="text-slate-500 dark:text-slate-400 hover:text-primary" href="#">Tower A</a>
          <span className="text-slate-300 dark:text-slate-600">/</span>
          <span className="text-primary font-medium">Phase 2 - Structure</span>
        </div>
        {/* Action Bar */}
        <div className="flex items-center justify-between px-6 pb-3 gap-4">
          <div className="flex items-center gap-2">
            <button className="flex items-center gap-2 h-9 px-3 rounded-lg bg-slate-100 dark:bg-surface-dark text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-[#2a313e] transition-colors border border-slate-200 dark:border-border-dark">
              <span className="material-symbols-outlined text-[18px]">upload_file</span>
              <span className="text-sm font-medium">Import IFC</span>
            </button>
            <button className="flex items-center gap-2 h-9 px-3 rounded-lg bg-slate-100 dark:bg-surface-dark text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-[#2a313e] transition-colors border border-slate-200 dark:border-border-dark">
              <span className="material-symbols-outlined text-[18px]">link</span>
              <span className="text-sm font-medium">Link Design Data</span>
            </button>
            <div className="w-px h-6 bg-slate-200 dark:bg-border-dark mx-1"></div>
            <button className="flex items-center justify-center size-9 rounded-lg text-slate-500 hover:text-primary hover:bg-primary/10 transition-colors" title="Download Report">
              <span className="material-symbols-outlined text-[20px]">download</span>
            </button>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
              <span className="material-symbols-outlined text-emerald-500 text-[16px]">sync</span>
              <span className="text-xs font-medium text-emerald-500">Live Sync Active</span>
            </div>
            <button className="flex items-center gap-2 h-9 px-4 rounded-lg bg-primary hover:bg-blue-600 text-white shadow-lg shadow-blue-500/20 transition-all">
              <span className="material-symbols-outlined text-[18px]">difference</span>
              <span className="text-sm font-bold">Simulate Change</span>
            </button>
          </div>
        </div>
      </div>
      
      {/* Workspace Grid */}
      <div className="flex-1 flex overflow-hidden">
        {/* 3D Model Viewer Container */}
        <div className="flex-1 relative bg-gradient-to-br from-slate-900 to-slate-800 flex flex-col overflow-hidden">
          {/* 3D Viewport Controls */}
          <div className="absolute top-4 left-4 z-10 flex flex-col gap-2">
            <div className="flex flex-col bg-surface-dark/90 backdrop-blur border border-border-dark rounded-lg p-1 shadow-xl">
              <button className="p-2 text-slate-300 hover:text-white hover:bg-white/10 rounded transition-colors" title="Orbit">
                <span className="material-symbols-outlined text-[20px]">3d_rotation</span>
              </button>
              <button className="p-2 text-slate-300 hover:text-white hover:bg-white/10 rounded transition-colors" title="Pan">
                <span className="material-symbols-outlined text-[20px]">pan_tool</span>
              </button>
              <button className="p-2 text-slate-300 hover:text-white hover:bg-white/10 rounded transition-colors" title="Zoom">
                <span className="material-symbols-outlined text-[20px]">zoom_in</span>
              </button>
            </div>
            {/* Layer Controls */}
            <div className="flex flex-col bg-surface-dark/90 backdrop-blur border border-border-dark rounded-lg p-3 shadow-xl gap-2 w-48">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-1">Layers</p>
              <label className="flex items-center gap-2 cursor-pointer group">
                <input defaultChecked className="rounded border-slate-600 bg-slate-700 text-primary focus:ring-offset-surface-dark focus:ring-primary" type="checkbox" />
                <span className="text-xs text-white group-hover:text-primary transition-colors">Structural</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer group">
                <input defaultChecked className="rounded border-slate-600 bg-slate-700 text-primary focus:ring-offset-surface-dark focus:ring-primary" type="checkbox" />
                <span className="text-xs text-white group-hover:text-primary transition-colors">Architectural</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer group">
                <input className="rounded border-slate-600 bg-slate-700 text-primary focus:ring-offset-surface-dark focus:ring-primary" type="checkbox" />
                <span className="text-xs text-slate-400 group-hover:text-primary transition-colors">MEP</span>
              </label>
            </div>
          </div>
          
          {/* The 3D Model Placeholder */}
          <div className="w-full h-full flex items-center justify-center relative overflow-hidden group">
            {/* Abstract Grid Background for 3D space */}
            <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.03)_1px,transparent_1px)] bg-[size:40px_40px] [transform:perspective(1000px)_rotateX(60deg)_translateY(-100px)_scale(2)] opacity-30"></div>
            {/* Mock 3D Object */}
            <div className="relative w-[600px] h-[400px] bg-contain bg-center bg-no-repeat transition-transform duration-700 group-hover:scale-105" data-alt="3D Wireframe building structure model" style={{backgroundImage: "url('https://lh3.googleusercontent.com/aida-public/AB6AXuDt9j2pY7ODcbxf0qQC41xLrw_X9VcE4QMPEt8ow5NIKdv8s-GWteQ_1B1_5gGC2Vth2gUijIJFnIqSD01VBGz8gMrQPdLTJyOKcJjO5WHFFNmkjX9_fNuwIo2gA1u7y79xLLSquwshaEAXXxYAvybldszXv4lX2HRupxjYrOi4qDY5NCQMlVcBp52FdZaHZQM6ix3rXNHDw-bxQAdVodExMiS0VjOMw1Yx_MYfqQnJ3dZsDfUcL5RFHfTFEwqBKlS5xZErE_TIwh8')", maskImage: "linear-gradient(to bottom, black 80%, transparent 100%)", WebkitMaskImage: "linear-gradient(to bottom, black 80%, transparent 100%)", filter: "hue-rotate(190deg) contrast(1.2) brightness(0.8)"}}></div>
            {/* Interactive Tooltip Overlay */}
            <div className="absolute top-1/2 left-1/2 transform translate-x-10 -translate-y-20 bg-surface-dark/90 backdrop-blur border border-primary/50 text-white text-xs rounded p-3 shadow-2xl animate-pulse">
              <div className="flex items-center gap-2 mb-1">
                <div className="size-2 rounded-full bg-primary"></div>
                <span className="font-bold">Wall Section W-204</span>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px] text-slate-400">
                <span>Area:</span> <span className="text-white text-right">45.2 m²</span>
                <span>Material:</span> <span className="text-white text-right">Reinf. Concrete</span>
                <span>Cost:</span> <span className="text-white text-right font-bold">$1,240</span>
              </div>
            </div>
          </div>
          
          {/* View Stats Bottom Bar */}
          <div className="absolute bottom-0 left-0 right-0 h-8 bg-surface-dark border-t border-border-dark flex items-center px-4 justify-between text-[10px] text-slate-400">
            <span>X: 12.4m Y: 45.2m Z: 0.0m</span>
            <div className="flex items-center gap-4">
              <span>Model v2.4 (Latest)</span>
              <span>LOD 300</span>
            </div>
          </div>
        </div>
        
        {/* Right Panel: Costing & Analysis */}
        <div className="w-[420px] bg-white dark:bg-[#111318] border-l border-slate-200 dark:border-border-dark flex flex-col shrink-0">
          {/* Tabs */}
          <div className="flex border-b border-slate-200 dark:border-border-dark px-2">
            <button 
              className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'cost' ? 'border-primary text-primary' : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}`}
              onClick={() => setActiveTab('cost')}
            >
              Cost Estimation
            </button>
            <button 
              className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'takeoff' ? 'border-primary text-primary' : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}`}
              onClick={() => setActiveTab('takeoff')}
            >
              Take-off
            </button>
            <button 
              className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'impact' ? 'border-primary text-primary' : 'border-transparent text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200'}`}
              onClick={() => setActiveTab('impact')}
            >
              Impact
            </button>
          </div>
          
          {/* Panel Content */}
          <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-6">
            {/* Total Cost Card */}
            <div className="p-5 rounded-xl bg-gradient-to-br from-primary/10 to-transparent border border-primary/20">
              <p className="text-slate-500 dark:text-slate-400 text-xs font-medium uppercase tracking-wider mb-1">Total Estimated Cost</p>
              <h3 className="text-3xl font-bold text-slate-900 dark:text-white tracking-tight">$12,450,000</h3>
              <div className="flex items-center gap-2 mt-2">
                <span className="flex items-center text-xs font-bold text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded">
                  <span className="material-symbols-outlined text-[14px] mr-0.5">trending_down</span>
                  2.4%
                </span>
                <span className="text-xs text-slate-400">vs previous version</span>
              </div>
            </div>
            
            {/* Cost Breakdown Charts */}
            <div className="flex flex-col gap-4">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-bold text-slate-900 dark:text-white">Breakdown by Category</h4>
                <button className="text-primary text-xs font-medium hover:underline">View Details</button>
              </div>
              {/* Simple Bar Chart Visualization */}
              <div className="flex flex-col gap-3">
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500 dark:text-slate-400">Materials (65%)</span>
                    <span className="text-slate-900 dark:text-white font-medium">$8.2M</span>
                  </div>
                  <div className="h-2 w-full bg-slate-100 dark:bg-surface-dark rounded-full overflow-hidden">
                    <div className="h-full bg-primary w-[65%] rounded-full"></div>
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500 dark:text-slate-400">Labor (25%)</span>
                    <span className="text-slate-900 dark:text-white font-medium">$3.1M</span>
                  </div>
                  <div className="h-2 w-full bg-slate-100 dark:bg-surface-dark rounded-full overflow-hidden">
                    <div className="h-full bg-sky-400 w-[25%] rounded-full"></div>
                  </div>
                </div>
                <div className="space-y-1">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500 dark:text-slate-400">Overhead (10%)</span>
                    <span className="text-slate-900 dark:text-white font-medium">$1.15M</span>
                  </div>
                  <div className="h-2 w-full bg-slate-100 dark:bg-surface-dark rounded-full overflow-hidden">
                    <div className="h-full bg-slate-500 w-[10%] rounded-full"></div>
                  </div>
                </div>
              </div>
            </div>
            
            {/* Top Cost Drivers Table */}
            <div className="flex flex-col gap-4">
              <h4 className="text-sm font-bold text-slate-900 dark:text-white">Top Cost Drivers</h4>
              <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-border-dark">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 dark:bg-surface-dark text-slate-500 dark:text-slate-400 font-medium border-b border-slate-200 dark:border-border-dark">
                    <tr>
                      <th className="px-3 py-2">Element</th>
                      <th className="px-3 py-2 text-right">Qty</th>
                      <th className="px-3 py-2 text-right">Cost</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200 dark:divide-border-dark bg-white dark:bg-[#151921]">
                    <tr className="hover:bg-slate-50 dark:hover:bg-surface-dark/50 transition-colors cursor-pointer group">
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300 font-medium group-hover:text-primary">Concrete C35</td>
                      <td className="px-3 py-2 text-right text-slate-500 dark:text-slate-400">450 m³</td>
                      <td className="px-3 py-2 text-right text-slate-900 dark:text-white font-medium">$125k</td>
                    </tr>
                    <tr className="hover:bg-slate-50 dark:hover:bg-surface-dark/50 transition-colors cursor-pointer group">
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300 font-medium group-hover:text-primary">Steel Rebar</td>
                      <td className="px-3 py-2 text-right text-slate-500 dark:text-slate-400">120 t</td>
                      <td className="px-3 py-2 text-right text-slate-900 dark:text-white font-medium">$98k</td>
                    </tr>
                    <tr className="hover:bg-slate-50 dark:hover:bg-surface-dark/50 transition-colors cursor-pointer group">
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300 font-medium group-hover:text-primary">Glazing Panel</td>
                      <td className="px-3 py-2 text-right text-slate-500 dark:text-slate-400">85 un</td>
                      <td className="px-3 py-2 text-right text-slate-900 dark:text-white font-medium">$65k</td>
                    </tr>
                    <tr className="hover:bg-slate-50 dark:hover:bg-surface-dark/50 transition-colors cursor-pointer group">
                      <td className="px-3 py-2 text-slate-700 dark:text-slate-300 font-medium group-hover:text-primary">HVAC Ducting</td>
                      <td className="px-3 py-2 text-right text-slate-500 dark:text-slate-400">320 m</td>
                      <td className="px-3 py-2 text-right text-slate-900 dark:text-white font-medium">$42k</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
            
            {/* Alerts / Notifications */}
            <div className="p-4 rounded-lg bg-orange-500/10 border border-orange-500/20 flex gap-3 items-start">
              <span className="material-symbols-outlined text-orange-500 mt-0.5 text-[20px]">warning</span>
              <div className="flex flex-col gap-1">
                <h5 className="text-sm font-bold text-orange-500">Cost Alert</h5>
                <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                  Structural steel prices have increased by 5% in the connected market database. Update rates?
                </p>
                <button className="self-start mt-1 text-xs font-bold text-orange-500 underline decoration-orange-500/50 hover:decoration-orange-500">Update Rates</button>
              </div>
            </div>
          </div>
          
          {/* Bottom Actions */}
          <div className="p-4 border-t border-slate-200 dark:border-border-dark bg-slate-50 dark:bg-surface-dark">
            <button className="w-full h-10 flex items-center justify-center gap-2 bg-slate-900 dark:bg-white text-white dark:text-slate-900 rounded-lg font-bold text-sm hover:opacity-90 transition-opacity">
              <span className="material-symbols-outlined text-[18px]">summarize</span>
              Generate Detailed Report
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
