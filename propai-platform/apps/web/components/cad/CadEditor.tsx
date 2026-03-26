"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { CadToolbar } from "@/components/cad/CadToolbar";
import { ComplianceHud } from "@/components/compliance/ComplianceHud";
import { useCadStore } from "@/store/use-cad-store";

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
      <p className="text-sm text-[rgba(19,33,47,0.48)]">캔버스를 준비하고 있습니다…</p>
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

  return (
    <section className="grid gap-4" aria-label="CAD 파라메트릭 에디터">
      <CadToolbar />
      <div className="relative" ref={containerRef}>
        <div className="overflow-hidden rounded-2xl border border-[var(--line)] bg-white">
          <CadCanvasInner width={canvasSize.width} height={canvasSize.height} />
        </div>
        <ComplianceHud projectId={projectId} />
      </div>
      <div
        className="flex gap-4 text-xs text-[rgba(19,33,47,0.48)]"
        aria-live="polite"
      >
        <span>점: {points.length}</span>
        <span>선: {lines.length}</span>
        <span>면: {polygons.length}</span>
      </div>
    </section>
  );
}
