"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useCadStore } from "@/store/use-cad-store";
import {
  executeCommand,
  getCompletions,
  getCommandHint,
  type CommandResult,
} from "@/lib/cad-command-parser";

type HistoryEntry = {
  input: string;
  result: CommandResult;
};

export function CadCommandLine() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [value, setValue] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>([]);
  const [historyIdx, setHistoryIdx] = useState(-1);
  const [completions, setCompletions] = useState<string[]>([]);
  const [showCompletions, setShowCompletions] = useState(false);

  // Store에서 필요한 상태/액션 가져오기
  const store = useCadStore();

  const handleExecute = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;

    let result: CommandResult;
    try {
      result = executeCommand(trimmed, {
      addPoint: store.addPoint,
      addLine: store.addLine,
      addRect: store.addRect,
      addCircle: store.addCircle,
      addText: store.addText,
      addPolygon: store.addPolygon,
      removeSelected: store.removeSelected,
      undo: store.undo,
      redo: store.redo,
      setSelected: store.setSelected,
      movePoint: store.movePoint,
      points: store.points,
      lines: store.lines,
      polygons: store.polygons,
      rects: store.rects,
      circles: store.circles,
      texts: store.texts,
      selectedId: store.selectedId,
      selectedIds: store.selectedIds,
      scale: store.scale,
    });
    } catch (e) {
      result = { ok: false, message: e instanceof Error ? e.message : "명령 실행 오류" };
    }

    setHistory((prev) => [...prev.slice(-19), { input: trimmed, result }]);
    setValue("");
    setHistoryIdx(-1);
    setShowCompletions(false);
  }, [value, store]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleExecute();
        return;
      }
      if (e.key === "Escape") {
        setValue("");
        setShowCompletions(false);
        inputRef.current?.blur();
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        const inputs = history.map((h) => h.input);
        if (inputs.length === 0) return;
        const nextIdx = historyIdx < 0 ? inputs.length - 1 : Math.max(0, historyIdx - 1);
        setHistoryIdx(nextIdx);
        setValue(inputs[nextIdx]);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        const inputs = history.map((h) => h.input);
        if (historyIdx < 0) return;
        const nextIdx = historyIdx + 1;
        if (nextIdx >= inputs.length) {
          setHistoryIdx(-1);
          setValue("");
        } else {
          setHistoryIdx(nextIdx);
          setValue(inputs[nextIdx]);
        }
        return;
      }
      if (e.key === "Tab") {
        e.preventDefault();
        if (completions.length === 1) {
          setValue(completions[0] + " ");
          setShowCompletions(false);
        }
      }
    },
    [handleExecute, history, historyIdx, completions],
  );

  // 자동완성 업데이트
  useEffect(() => {
    if (value.trim()) {
      const list = getCompletions(value);
      setCompletions(list);
      setShowCompletions(list.length > 0 && list.length <= 8);
    } else {
      setCompletions([]);
      setShowCompletions(false);
    }
  }, [value]);

  // 글로벌 단축키: / 또는 : 으로 포커스
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "/" || e.key === ":") {
        e.preventDefault();
        inputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // 최근 히스토리 5개만 표시
  const recentHistory = history.slice(-5);

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] overflow-hidden">
      {/* 히스토리 */}
      {recentHistory.length > 0 && (
        <div className="max-h-[120px] overflow-y-auto border-b border-[var(--line)] px-3 py-2 text-xs font-mono">
          {recentHistory.map((entry, i) => (
            <div key={i} className="flex gap-2">
              <span className="text-[var(--text-hint)] shrink-0">&gt;</span>
              <span className="text-[var(--text-secondary)]">{entry.input}</span>
              <span
                className={entry.result.ok ? "text-emerald-600" : "text-red-500"}
              >
                {entry.result.message.split("\n")[0]}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* 입력 */}
      <div className="relative flex items-center gap-2 px-3 py-2">
        <span className="text-xs font-bold text-[var(--accent)] select-none">명령:</span>
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onFocus={() => value.trim() && setShowCompletions(completions.length > 0)}
          onBlur={() => setTimeout(() => setShowCompletions(false), 150)}
          placeholder="명령 입력 (HELP로 목록 확인, / 키로 포커스)"
          className="flex-1 bg-transparent text-sm font-mono text-[var(--text-primary)] outline-none placeholder:text-[var(--text-hint)]"
          aria-label="CAD 명령 입력. 위/아래 키로 히스토리 탐색, Tab으로 자동완성"
          aria-autocomplete="list"
          autoComplete="off"
          spellCheck={false}
        />

        {/* 자동완성 + 파라미터 힌트 */}
        {showCompletions && (
          <div className="absolute bottom-full left-0 mb-1 ml-12 flex flex-col gap-1">
            <div className="flex gap-1 flex-wrap">
              {completions.map((c) => (
                <button
                  key={c}
                  type="button"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    setValue(c + " ");
                    setShowCompletions(false);
                    inputRef.current?.focus();
                  }}
                  className="rounded-lg bg-[var(--surface-soft)] px-2 py-0.5 text-[11px] font-mono text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] border border-[var(--line)]"
                >
                  {c}
                </button>
              ))}
            </div>
            {completions.length === 1 && (
              <span className="text-[10px] font-mono text-[var(--text-hint)] ml-1">
                {getCommandHint(completions[0])}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
