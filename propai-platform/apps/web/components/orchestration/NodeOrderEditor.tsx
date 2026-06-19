"use client";

/**
 * NodeOrderEditor — 프로필 노드 순서 재배열 UI(B5).
 *
 * 쉬운 설명: 적용한 워크플로우의 분석 순서를 위/아래 버튼(▲▼)으로 바꾼다.
 * 드래그앤드롭 대신 버튼을 쓰는 이유: 외부 DnD 라이브러리 의존을 늘리지 않고,
 * 키보드·스크린리더 접근성이 좋으며, 모바일에서도 견고하기 때문이다.
 *
 * 상위(ProfileManager)가 store.nodeOrder ↔ setNodeOrder로 연결한다. 색상 토큰만 사용.
 */

import { NODES } from "@/lib/orchestration/node-registry";
import type { AnalysisNode, NodeId } from "@/lib/orchestration/types";

const BY_ID: Record<NodeId, AnalysisNode> = Object.fromEntries(
  NODES.map((n) => [n.id, n]),
) as Record<NodeId, AnalysisNode>;

export interface NodeOrderEditorProps {
  /** 현재 순서(NodeId[]). */
  order: NodeId[];
  /** 순서 변경 시 호출(새 순서 전달). */
  onChange: (order: NodeId[]) => void;
}

export function NodeOrderEditor({ order, onChange }: NodeOrderEditorProps) {
  // 두 위치를 맞바꾼 새 배열을 만들어 onChange로 올린다(불변 갱신).
  const swap = (i: number, j: number) => {
    if (j < 0 || j >= order.length) return;
    const next = [...order];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  };

  if (!order.length) return null;

  return (
    <div className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-card)] p-3">
      <p className="mb-2 text-[11px] font-semibold text-[var(--text-secondary)]">
        실행 순서 — ▲▼로 조정(상류가 앞이어야 안정적입니다)
      </p>
      <ul className="grid gap-1.5">
        {order.map((id, i) => {
          const node = BY_ID[id];
          if (!node) return null;
          const isFirst = i === 0;
          const isLast = i === order.length - 1;
          return (
            <li
              key={id}
              className="flex items-center justify-between gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-soft)] px-3 py-1.5"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="shrink-0 text-[10px] font-bold text-[var(--text-tertiary)]">
                  {i + 1}
                </span>
                <span className="truncate text-sm text-[var(--text-primary)]">
                  {node.label}
                </span>
              </span>
              <span className="flex shrink-0 items-center gap-1">
                <button
                  type="button"
                  aria-label={`${node.label} 위로`}
                  disabled={isFirst}
                  onClick={() => swap(i, i - 1)}
                  className="rounded-md border border-[var(--line-strong)] px-2 py-0.5 text-xs text-[var(--text-secondary)] transition-colors hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-30"
                >
                  ▲
                </button>
                <button
                  type="button"
                  aria-label={`${node.label} 아래로`}
                  disabled={isLast}
                  onClick={() => swap(i, i + 1)}
                  className="rounded-md border border-[var(--line-strong)] px-2 py-0.5 text-xs text-[var(--text-secondary)] transition-colors hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] disabled:cursor-not-allowed disabled:opacity-30"
                >
                  ▼
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
