"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { CadToolbar } from "@/components/cad/CadToolbar";
import { AutoDesignPanel } from "@/components/cad/AutoDesignPanel";
import { DrawingAnalysisPanel } from "@/components/cad/DrawingAnalysisPanel";
import { ExportPanel } from "@/components/cad/ExportPanel";
import { CadCommandLine } from "@/components/cad/CadCommandLine";
import { ComplianceHud } from "@/components/compliance/ComplianceHud";
import LayerPanel from "@/components/cad/LayerPanel";
import { CadCompliancePanel } from "@/components/cad/CadCompliancePanel";
import { CadBimSidePanel } from "@/components/cad/CadBimSidePanel";
import { CadExportPanel } from "@/components/cad/CadExportPanel";
import { useCadStore } from "@/store/use-cad-store";

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
    <section className="grid gap-4" aria-label="CAD 파라메트릭 에디터">
      <CadToolbar />

      {/* 우측 패널 탭 버튼 */}
      <div className="flex items-center gap-1" role="group" aria-label="확장 패널">
        {RIGHT_PANEL_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => toggleRightPanel(tab.id)}
            className={`rounded-xl px-3 py-1.5 text-xs font-bold transition-colors ${
              rightPanel === tab.id
                ? "bg-[var(--accent)] text-white"
                : "bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
            aria-pressed={rightPanel === tab.id}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div
        className={`grid gap-4 ${
          rightPanel !== "none"
            ? "grid-cols-[280px_1fr_320px]"
            : "grid-cols-[280px_1fr]"
        }`}
      >
        {/* 좌측: AI 설계 패널 + 레이어 */}
        <div className="flex flex-col gap-4 overflow-y-auto" style={{ maxHeight: 640 }}>
          <AutoDesignPanel projectId={projectId} />
          <DrawingAnalysisPanel />
          <LayerPanel />
          <ExportPanel projectId={projectId} />
        </div>

        {/* 중앙: 캔버스 + HUD */}
        <div className="relative" ref={containerRef}>
          <div className="overflow-hidden rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] shadow-[var(--shadow-lg)]">
            <CadCanvasInner width={canvasSize.width} height={canvasSize.height} />
          </div>
          <ComplianceHud projectId={projectId} />

          {/* TEXT 인라인 입력 오버레이 */}
          {textInputPending && (
            <div className="absolute inset-0 z-10 flex items-center justify-center bg-black/20 rounded-2xl">
              <form
                onSubmit={handleTextSubmit}
                className="flex items-center gap-2 rounded-xl bg-[var(--surface)] px-4 py-3 shadow-lg border border-[var(--line-strong)]"
                role="dialog"
                aria-label="텍스트 입력"
              >
                <span className="text-xs font-bold text-[var(--accent)]">텍스트:</span>
                <input
                  ref={textInputRef}
                  type="text"
                  value={textValue}
                  onChange={(e) => setTextValue(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Escape") handleTextCancel(); }}
                  placeholder="텍스트 내용 입력 후 Enter"
                  className="w-64 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-1.5 text-sm font-mono outline-none focus:border-[var(--accent)]"
                  aria-label="텍스트 내용"
                  autoComplete="off"
                  maxLength={200}
                />
                <button type="submit" className="rounded-lg bg-[var(--accent)] px-3 py-1.5 text-xs font-bold text-white">
                  확인
                </button>
                <button type="button" onClick={handleTextCancel} className="rounded-lg bg-[var(--surface-soft)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)]">
                  취소
                </button>
              </form>
            </div>
          )}
        </div>

        {/* 우측: 확장 패널 (슬라이드) */}
        {rightPanel !== "none" && (
          <div className="flex flex-col gap-4 overflow-y-auto" style={{ maxHeight: 640 }}>
            {rightPanel === "compliance" && (
              <CadCompliancePanel projectId={projectId} />
            )}
            {rightPanel === "bim" && (
              <CadBimSidePanel projectId={projectId} />
            )}
            {rightPanel === "export" && (
              <CadExportPanel projectId={projectId} />
            )}
          </div>
        )}
      </div>

      {/* 커맨드라인 */}
      <CadCommandLine />

      <div
        className="flex gap-4 text-xs text-[var(--text-hint)]"
        aria-live="polite"
      >
        <span>점: {points.length}</span>
        <span>선: {lines.length}</span>
        <span>면: {polygons.length}</span>
        <span>사각형: {rects.length}</span>
        <span>원: {circles.length}</span>
        <span>문자: {texts.length}</span>
        {selectedIds.length > 0 && (
          <span className="text-[var(--accent)] font-medium">선택: {selectedIds.length}</span>
        )}
        <span className="ml-auto">
          X: {(cursorPos.x / cadScale).toFixed(1)} Y: {(cursorPos.y / cadScale).toFixed(1)} m
        </span>
        <span>줌: {Math.round(viewScale * 100)}%</span>
      </div>
    </section>
  );
}
