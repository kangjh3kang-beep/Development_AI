"use client";

/**
 * RunProgressTimeline — 실행 진행 시각화.
 *
 * Phase B 블루프린트 §3-B([graft C])·§2-C 정합. plan(실행 순서)과 nodeResult(노드별 결과)를 묶어
 * 진행 타임라인으로 보여준다. 각 노드는 NodeRunCard로 상태/검증/그라운딩을 정직 표기한다.
 *
 * 상태: idle/queued/running/done/skipped-fresh/skipped-unavailable/needs-input/error
 *       + verifyStatus(pass/warn/fail) + grounding(정직 배지)는 NodeRunCard가 표시.
 *
 * 무목업: plan이 비면 안내만(가짜 진행률 금지). 색상 토큰만 사용.
 */

import { NodeRunCard } from "./NodeRunCard";
import type { NodeId } from "@/lib/orchestration/types";
import type { NodeResult } from "@/store/useOrchestrationStore";

export interface RunProgressTimelineProps {
  /** 실행 계획(노드 순서). buildPlan/store.plan. */
  plan: NodeId[];
  /** 노드별 실행 결과 맵. */
  nodeResult: Record<string, NodeResult>;
  /** 단일 노드 재실행 CTA(미전달 시 카드에 버튼 숨김). */
  onRunNode?: (id: NodeId) => void;
  /** CTA 비활성. */
  runDisabled?: boolean;
}

export function RunProgressTimeline({
  plan,
  nodeResult,
  onRunNode,
  runDisabled = false,
}: RunProgressTimelineProps) {
  if (plan.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-4 text-center">
        <p className="text-xs text-[var(--text-hint)]">
          분석을 실행하면 노드별 진행 상태가 여기에 표시됩니다.
        </p>
      </div>
    );
  }

  // 진행 요약(가짜 진행률 아님 — 실제 결과 집계).
  const done = plan.filter((id) => nodeResult[id]?.state === "done").length;
  const running = plan.filter((id) => nodeResult[id]?.state === "running").length;
  const errored = plan.filter((id) => nodeResult[id]?.state === "error").length;

  return (
    <div>
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-bold text-[var(--text-primary)]">실행 진행</p>
        <span className="rounded-full bg-[var(--surface-soft)] px-2.5 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)]">
          완료 {done}/{plan.length}
          {running > 0 && <span className="ml-1 text-[var(--accent-strong)]">· 실행 중 {running}</span>}
          {errored > 0 && <span className="ml-1 text-[var(--status-warning)]">· 오류 {errored}</span>}
        </span>
      </div>

      <div className="grid gap-2.5">
        {plan.map((id) => (
          <NodeRunCard
            key={id}
            nodeId={id}
            result={nodeResult[id]}
            onRun={onRunNode}
            runDisabled={runDisabled}
          />
        ))}
      </div>
    </div>
  );
}
