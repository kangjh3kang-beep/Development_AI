"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { CadToolbar } from "@/components/cad/CadToolbar";
import { AutoDesignPanel } from "@/components/cad/AutoDesignPanel";
import { DrawingAnalysisPanel } from "@/components/cad/DrawingAnalysisPanel";
// ExportPanel은 우측 CadExportPanel로 통합됨
import { CadCommandLine } from "@/components/cad/CadCommandLine";
import { ComplianceHud } from "@/components/compliance/ComplianceHud";
import LayerPanel from "@/components/cad/LayerPanel";
import { CadCompliancePanel } from "@/components/cad/CadCompliancePanel";
import { CadBimSidePanel } from "@/components/cad/CadBimSidePanel";
import { CadExportPanel } from "@/components/cad/CadExportPanel";
import { useCadStore } from "@/store/use-cad-store";

type LeftPanelTab = "design" | "analysis" | "layers";
type RightPanelTab = "none" | "compliance" | "bim" | "export";

const CadCanvasInner = dynamic(
  () =>
    import("@/components/cad/CadCanvasInner").then((mod) => mod.CadCanvasInner),
  { ssr: false, loading: () => <CanvasPlaceholder /> },
);

function CanvasPlaceholder() {
  return (
    <div
      className="flex items-center justify-center rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]"
      style={{ height: 560 }}
      aria-label="CAD 캔버스 로딩 중"
    >
      <p className="text-sm text-[var(--text-hint)]">캔버스를 준비하고 있습니다…</p>
    </div>
  );
}

type CadEditorProps = {
  projectId: string;
};

export function CadEditor({ projectId }: CadEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [canvasSize, setCanvasSize] = useState({ width: 800, height: 560 });

  const setTool = useCadStore((s) => s.setTool);
  const undo = useCadStore((s) => s.undo);
  const redo = useCadStore((s) => s.redo);
  const removeSelected = useCadStore((s) => s.removeSelected);
  const completePending = useCadStore((s) => s.completePending);
  const points = useCadStore((s) => s.points);
  const lines = useCadStore((s) => s.lines);
  const polygons = useCadStore((s) => s.polygons);
  const rects = useCadStore((s) => s.rects);
  const circles = useCadStore((s) => s.circles);
  const texts = useCadStore((s) => s.texts);
  const selectedIds = useCadStore((s) => s.selectedIds);
  const cursorPos = useCadStore((s) => s.cursorPos);
  const viewScale = useCadStore((s) => s.viewScale);
  const cadScale = useCadStore((s) => s.scale);
  const textInputPending = useCadStore((s) => s.textInputPending);
  const confirmTextInput = useCadStore((s) => s.confirmTextInput);
  const cancelTextInput = useCadStore((s) => s.cancelTextInput);

  const [textValue, setTextValue] = useState("");
  const textInputRef = useRef<HTMLInputElement>(null);
  const [leftPanel, setLeftPanel] = useState<LeftPanelTab>("design");
  const [rightPanel, setRightPanel] = useState<RightPanelTab>("none");

  // 캔버스 크기 자동 조정
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        if (width > 0) {
          setCanvasSize({ width: Math.floor(width), height: 560 });
        }
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 키보드 단축키
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "z") {
        e.preventDefault();
        if (e.shiftKey) {
          redo();
        } else {
          undo();
        }
        return;
      }

      switch (e.key.toLowerCase()) {
        case "v":
          setTool("select");
          break;
        case "p":
          setTool("point");
          break;
        case "l":
          setTool("line");
          break;
        case "g":
          setTool("polygon");
          break;
        case "t":
          setTool("text");
          break;
        case "r":
          setTool("rect");
          break;
        case "c":
          setTool("circle");
          break;
        case "delete":
        case "backspace":
          removeSelected();
          break;
        case "enter":
          completePending();
          break;
      }
    },
    [setTool, undo, redo, removeSelected, completePending],
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // TEXT 인라인 입력 포커스
  useEffect(() => {
    if (textInputPending && textInputRef.current) {
      textInputRef.current.focus();
    }
  }, [textInputPending]);

  const handleTextSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      if (textValue.trim()) {
        confirmTextInput(textValue);
        setTextValue("");
      }
    },
    [textValue, confirmTextInput],
  );

  const handleTextCancel = useCallback(() => {
    cancelTextInput();
    setTextValue("");
  }, [cancelTextInput]);

  const RIGHT_PANEL_TABS: Array<{ id: RightPanelTab; label: string }> = [
    { id: "compliance", label: "검증" },
    { id: "bim", label: "BIM" },
    { id: "export", label: "내보내기" },
  ];

  const toggleRightPanel = useCallback(
    (tab: RightPanelTab) => {
      setRightPanel((prev) => (prev === tab ? "none" : tab));
    },
    [],
  );

  return (
    <div className="flex h-[calc(100vh-160px)] w-full overflow-hidden bg-slate-50 dark:bg-[#090b10] rounded-xl border border-slate-200 dark:border-border-dark shadow-sm font-display text-slate-900 dark:text-white" aria-label="CAD 파라메트릭 에디터">
      {/* ── 좌측 툴바 ── */}
      <aside className="w-16 flex flex-col items-center bg-white dark:bg-[#111318] border-r border-slate-200 dark:border-border-dark py-4 gap-4 shrink-0 z-40">
        <div className="flex flex-col gap-2 w-full px-2">
          <button onClick={() => setTool("select")} className={`group flex flex-col items-center justify-center w-full aspect-square rounded-lg relative transition-colors ${useCadStore.getState().tool === 'select' ? 'bg-primary/10 text-primary dark:bg-border-dark dark:text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-border-dark dark:hover:text-white'}`} title="Select">
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m3 3 7.07 16.97 2.51-7.39 7.39-2.51L3 3z"/><path d="m13 13 6 6"/></svg>
            <span className="absolute left-14 bg-white dark:bg-surface-dark px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 transition-opacity border border-slate-200 dark:border-border-dark whitespace-nowrap pointer-events-none z-50 shadow-sm">Select (V)</span>
          </button>
        </div>
        <div className="w-8 h-px bg-slate-200 dark:bg-border-dark" />
        
        <div className="flex flex-col gap-2 w-full px-2">
          <button onClick={() => setTool("line")} className={`group flex flex-col items-center justify-center w-full aspect-square rounded-lg relative transition-colors ${useCadStore.getState().tool === 'line' ? 'bg-primary/10 text-primary dark:bg-border-dark dark:text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-border-dark dark:hover:text-white'}`}>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="5" x2="19" y1="12" y2="12"/></svg>
            <span className="absolute left-14 bg-white dark:bg-surface-dark px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 transition-opacity border border-slate-200 dark:border-border-dark whitespace-nowrap pointer-events-none z-50 shadow-sm">Line (L)</span>
          </button>
          <button onClick={() => setTool("rect")} className={`group flex flex-col items-center justify-center w-full aspect-square rounded-lg relative transition-colors ${useCadStore.getState().tool === 'rect' ? 'bg-primary/10 text-primary dark:bg-border-dark dark:text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-border-dark dark:hover:text-white'}`}>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect width="18" height="18" x="3" y="3" rx="2" ry="2"/></svg>
            <span className="absolute left-14 bg-white dark:bg-surface-dark px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 transition-opacity border border-slate-200 dark:border-border-dark whitespace-nowrap pointer-events-none z-50 shadow-sm">Rectangle (R)</span>
          </button>
          <button onClick={() => setTool("polygon")} className={`group flex flex-col items-center justify-center w-full aspect-square rounded-lg relative transition-colors ${useCadStore.getState().tool === 'polygon' ? 'bg-primary/10 text-primary dark:bg-border-dark dark:text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-border-dark dark:hover:text-white'}`}>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 2l9 4-3 10H6L3 6l9-4z"/></svg>
            <span className="absolute left-14 bg-white dark:bg-surface-dark px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 transition-opacity border border-slate-200 dark:border-border-dark whitespace-nowrap pointer-events-none z-50 shadow-sm">Polygon (G)</span>
          </button>
          <button onClick={() => setTool("circle")} className={`group flex flex-col items-center justify-center w-full aspect-square rounded-lg relative transition-colors ${useCadStore.getState().tool === 'circle' ? 'bg-primary/10 text-primary dark:bg-border-dark dark:text-white' : 'text-slate-400 hover:bg-slate-100 hover:text-slate-600 dark:hover:bg-border-dark dark:hover:text-white'}`}>
            <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/></svg>
            <span className="absolute left-14 bg-white dark:bg-surface-dark px-2 py-1 rounded text-xs opacity-0 group-hover:opacity-100 transition-opacity border border-slate-200 dark:border-border-dark whitespace-nowrap pointer-events-none z-50 shadow-sm">Circle (C)</span>
          </button>
        </div>
      </aside>

      {/* ── 중앙 뷰포트 ── */}
      <main className="flex-1 flex flex-col relative overflow-hidden">
        {/* Top Overlay Bar */}
        <div className="absolute top-4 left-4 right-4 flex justify-between items-start z-20 pointer-events-none">
          <div className="bg-white/90 dark:bg-surface-dark/90 backdrop-blur-sm p-1 rounded-lg border border-slate-200 dark:border-border-dark shadow-sm pointer-events-auto">
            <div className="flex h-8 items-center justify-center gap-1">
              <label className="cursor-pointer h-full px-3 rounded flex items-center justify-center text-slate-500 dark:text-gray-400 hover:text-slate-800 dark:hover:text-white transition-all has-[:checked]:bg-primary has-[:checked]:text-white">
                <span className="text-xs font-bold uppercase tracking-wider">Wireframe</span>
                <input className="hidden" name="viewmode" type="radio" value="Wireframe" />
              </label>
              <div className="w-px h-4 bg-slate-300 dark:bg-gray-700" />
              <label className="cursor-pointer h-full px-3 rounded flex items-center justify-center text-slate-500 dark:text-gray-400 hover:text-slate-800 dark:hover:text-white transition-all has-[:checked]:bg-primary has-[:checked]:text-white">
                <span className="text-xs font-bold uppercase tracking-wider">Shaded</span>
                <input defaultChecked className="hidden" name="viewmode" type="radio" value="Shaded" />
              </label>
            </div>
          </div>
          
          <div className="flex gap-2 bg-white/90 dark:bg-surface-dark/90 backdrop-blur-sm p-1 rounded-lg border border-slate-200 dark:border-border-dark shadow-sm pointer-events-auto">
             <button className="p-1.5 text-slate-500 dark:text-gray-400 hover:text-slate-800 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10 rounded transition-colors" onClick={undo} title="Undo">
               <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 7v6h6"/><path d="M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13"/></svg>
             </button>
             <button className="p-1.5 text-slate-500 dark:text-gray-400 hover:text-slate-800 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10 rounded transition-colors" onClick={redo} title="Redo">
               <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 7v6h-6"/><path d="M3 17a9 9 0 0 1 9-9 9 9 0 0 1 6 2.3l3 2.7"/></svg>
             </button>
          </div>
        </div>

        {/* Canvas Area */}
        <div className="w-full h-full relative" ref={containerRef} style={{ backgroundImage: 'linear-gradient(to right, var(--line-subtle) 1px, transparent 1px), linear-gradient(to bottom, var(--line-subtle) 1px, transparent 1px)', backgroundSize: '40px 40px' }}>
          <CadCanvasInner width={canvasSize.width} height={canvasSize.height} />
          
          {textInputPending && (
            <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/10 dark:bg-black/40 backdrop-blur-sm">
              <form onSubmit={handleTextSubmit} className="flex items-center gap-2 rounded-xl bg-white dark:bg-surface-dark px-4 py-3 shadow-xl border border-slate-200 dark:border-border-dark">
                <span className="text-xs font-bold text-primary">텍스트 입력:</span>
                <input ref={textInputRef} type="text" value={textValue} onChange={(e) => setTextValue(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") handleTextCancel(); }} className="w-64 rounded-lg border border-slate-200 dark:border-border-dark bg-slate-50 dark:bg-[#111318] px-3 py-1.5 text-sm font-mono outline-none focus:border-primary focus:ring-1 focus:ring-primary text-slate-900 dark:text-white" autoFocus autoComplete="off" />
                <button type="submit" className="rounded-lg bg-primary hover:bg-primary-dark px-3 py-1.5 text-xs font-bold text-white transition-colors">확인</button>
                <button type="button" onClick={handleTextCancel} className="rounded-lg bg-slate-100 dark:bg-border-dark hover:bg-slate-200 dark:hover:bg-gray-700 px-3 py-1.5 text-xs font-medium text-slate-600 dark:text-gray-300 transition-colors">취소</button>
              </form>
            </div>
          )}
        </div>

        {/* Bottom Status Bar */}
        <div className="h-8 bg-white dark:bg-[#111318] border-t border-slate-200 dark:border-border-dark flex items-center justify-between px-4 text-[11px] font-mono text-slate-500 dark:text-gray-400 shrink-0 z-20">
          <div className="flex items-center gap-4">
            <span className="text-primary font-bold">READY</span>
            <span>요소: {points.length + lines.length + polygons.length + rects.length + circles.length}개</span>
            {selectedIds.length > 0 && <span className="text-emerald-500 font-bold">선택: {selectedIds.length}개</span>}
          </div>
          <div className="flex items-center gap-4">
            <span>X: {(cursorPos.x / cadScale).toFixed(2)}m</span>
            <span>Y: {(cursorPos.y / cadScale).toFixed(2)}m</span>
            <div className="w-px h-3 bg-slate-300 dark:bg-border-dark" />
            <span>줌: {Math.round(viewScale * 100)}%</span>
          </div>
        </div>
      </main>

      {/* ── 우측 속성 패널 ── */}
      <aside className="w-[320px] bg-white dark:bg-[#111318] border-l border-slate-200 dark:border-border-dark flex flex-col overflow-y-auto shrink-0 z-40">
        <div className="p-4 border-b border-slate-200 dark:border-border-dark">
          <div className="flex items-center justify-between mb-1">
            <h3 className="text-slate-900 dark:text-white text-sm font-bold uppercase tracking-wider">Properties</h3>
            <button className="text-slate-400 hover:text-slate-700 dark:hover:text-white"><svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/></svg></button>
          </div>
          <div className="text-primary text-xs font-mono">{selectedIds.length > 0 ? `선택됨 (${selectedIds.length})` : '선택 없음'}</div>
        </div>
        
        {/* Transform / Info */}
        <div className="p-4 border-b border-slate-200 dark:border-border-dark">
           <div className="flex items-center gap-2 mb-3 text-slate-500 dark:text-gray-400">
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="m21 16-4 4-4-4"/><path d="M17 20V4"/><path d="m3 8 4-4 4 4"/><path d="M7 4v16"/></svg>
             <span className="text-xs font-bold uppercase">Transform & Info</span>
           </div>
           
           <div className="space-y-3">
             <div className="flex flex-col gap-1.5">
               <label className="text-[10px] text-slate-500 dark:text-gray-500 font-mono uppercase">Current Tool</label>
               <div className="bg-slate-50 dark:bg-surface-dark border border-slate-200 dark:border-border-dark rounded text-xs text-slate-900 dark:text-white px-3 py-2 font-mono uppercase tracking-wider">
                 {useCadStore.getState().tool}
               </div>
             </div>
             
             <div className="flex items-center justify-between gap-4 mt-2">
                <label className="text-xs text-slate-500 dark:text-gray-400">Lines</label>
                <span className="text-xs font-bold text-slate-900 dark:text-white">{lines.length}</span>
             </div>
             <div className="flex items-center justify-between gap-4">
                <label className="text-xs text-slate-500 dark:text-gray-400">Polygons</label>
                <span className="text-xs font-bold text-slate-900 dark:text-white">{polygons.length + rects.length + circles.length}</span>
             </div>
           </div>
        </div>

        {/* AI Auto Design Panels */}
        <div className="flex flex-col flex-1 p-4 gap-4">
           <div className="flex items-center gap-2 mb-1 text-slate-500 dark:text-gray-400">
             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M2 12h20"/><path d="M12 2v20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
             <span className="text-xs font-bold uppercase">AI Modules</span>
           </div>
           
           <div className="flex flex-col gap-4 overflow-y-auto pr-1">
             <div className="bg-slate-50 dark:bg-surface-dark rounded-xl border border-slate-200 dark:border-border-dark p-3">
               <AutoDesignPanel projectId={projectId} />
             </div>
             <div className="bg-slate-50 dark:bg-surface-dark rounded-xl border border-slate-200 dark:border-border-dark p-3">
               <CadCompliancePanel projectId={projectId} />
             </div>
             <div className="bg-slate-50 dark:bg-surface-dark rounded-xl border border-slate-200 dark:border-border-dark p-3">
               <CadExportPanel projectId={projectId} />
             </div>
           </div>
        </div>
      </aside>
    </div>
  );
}
