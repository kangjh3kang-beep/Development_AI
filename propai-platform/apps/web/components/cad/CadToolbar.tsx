"use client";

import { useCadStore } from "@/store/use-cad-store";
import type { CadTool } from "@/components/cad/types";

const TOOLS: Array<{ id: CadTool; label: string; shortcut: string }> = [
  { id: "select", label: "선택", shortcut: "V" },
  { id: "point", label: "점", shortcut: "P" },
  { id: "line", label: "선", shortcut: "L" },
  { id: "polygon", label: "면", shortcut: "G" },
];

export function CadToolbar() {
  const tool = useCadStore((s) => s.tool);
  const gridSnap = useCadStore((s) => s.gridSnap);
  const floorCount = useCadStore((s) => s.floorCount);
  const buildingHeightM = useCadStore((s) => s.buildingHeightM);
  const undoStack = useCadStore((s) => s.undoStack);
  const redoStack = useCadStore((s) => s.redoStack);
  const pendingPointIds = useCadStore((s) => s.pendingPointIds);

  const setTool = useCadStore((s) => s.setTool);
  const setGridSnap = useCadStore((s) => s.setGridSnap);
  const setFloorCount = useCadStore((s) => s.setFloorCount);
  const setBuildingHeight = useCadStore((s) => s.setBuildingHeight);
  const undo = useCadStore((s) => s.undo);
  const redo = useCadStore((s) => s.redo);
  const removeSelected = useCadStore((s) => s.removeSelected);
  const completePending = useCadStore((s) => s.completePending);
  const cancelPending = useCadStore((s) => s.cancelPending);
  const resetCanvas = useCadStore((s) => s.resetCanvas);
  const selectedId = useCadStore((s) => s.selectedId);

  return (
    <div
      className="flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--line)] bg-[var(--surface)] px-4 py-3"
      role="toolbar"
      aria-label="CAD 도구 모음"
    >
      {/* 도구 버튼 */}
      <div className="flex gap-1" role="radiogroup" aria-label="그리기 도구">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="radio"
            aria-checked={tool === t.id}
            aria-label={`${t.label} 도구 (${t.shortcut})`}
            onClick={() => setTool(t.id)}
            className={`rounded-xl px-3 py-1.5 text-sm font-medium transition-colors ${
              tool === t.id
                ? "bg-[var(--accent)] text-white"
                : "bg-[var(--surface-soft)] text-[var(--foreground)] hover:bg-[var(--surface-muted)]"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="mx-1 h-6 w-px bg-[var(--line)]" aria-hidden="true" />

      {/* 폴리곤 완성/취소 */}
      {tool === "polygon" && pendingPointIds.length >= 3 && (
        <button
          type="button"
          onClick={completePending}
          className="rounded-xl bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white"
          aria-label="폴리곤 완성"
        >
          완성
        </button>
      )}
      {pendingPointIds.length > 0 && (
        <button
          type="button"
          onClick={cancelPending}
          className="rounded-xl bg-[var(--surface-soft)] px-3 py-1.5 text-sm font-medium text-[var(--foreground)]"
          aria-label="취소"
        >
          취소
        </button>
      )}

      {/* Undo / Redo */}
      <button
        type="button"
        onClick={undo}
        disabled={undoStack.length === 0}
        aria-label="실행 취소"
        className="rounded-xl bg-[var(--surface-soft)] px-3 py-1.5 text-sm font-medium text-[var(--foreground)] disabled:opacity-40"
      >
        ↩ 실행취소
      </button>
      <button
        type="button"
        onClick={redo}
        disabled={redoStack.length === 0}
        aria-label="다시 실행"
        className="rounded-xl bg-[var(--surface-soft)] px-3 py-1.5 text-sm font-medium text-[var(--foreground)] disabled:opacity-40"
      >
        ↪ 다시실행
      </button>

      {/* 선택 삭제 */}
      {selectedId && (
        <button
          type="button"
          onClick={removeSelected}
          aria-label="선택 요소 삭제"
          className="rounded-xl bg-red-500/10 px-3 py-1.5 text-sm font-medium text-red-600"
        >
          삭제
        </button>
      )}

      <div className="mx-1 h-6 w-px bg-[var(--line)]" aria-hidden="true" />

      {/* 그리드 스냅 */}
      <label className="flex items-center gap-1.5 text-sm text-[rgba(19,33,47,0.72)]">
        <input
          type="checkbox"
          checked={gridSnap}
          onChange={(e) => setGridSnap(e.target.checked)}
          className="accent-[var(--accent)]"
          aria-label="그리드 스냅 활성화"
        />
        스냅
      </label>

      <div className="mx-1 h-6 w-px bg-[var(--line)]" aria-hidden="true" />

      {/* 건물 설정 */}
      <label className="flex items-center gap-1.5 text-sm text-[rgba(19,33,47,0.72)]">
        층수
        <input
          type="number"
          min={1}
          max={100}
          value={floorCount}
          onChange={(e) => setFloorCount(Number(e.target.value))}
          className="w-14 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-sm"
          aria-label="층수"
        />
      </label>

      <label className="flex items-center gap-1.5 text-sm text-[rgba(19,33,47,0.72)]">
        높이(m)
        <input
          type="number"
          min={0}
          step={0.5}
          value={buildingHeightM}
          onChange={(e) => setBuildingHeight(Number(e.target.value))}
          className="w-16 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-2 py-1 text-sm"
          aria-label="건물 높이 (미터)"
        />
      </label>

      {/* 초기화 */}
      <button
        type="button"
        onClick={resetCanvas}
        className="ml-auto rounded-xl bg-[var(--surface-soft)] px-3 py-1.5 text-sm font-medium text-[rgba(19,33,47,0.56)] hover:text-[var(--foreground)]"
        aria-label="캔버스 초기화"
      >
        초기화
      </button>
    </div>
  );
}
