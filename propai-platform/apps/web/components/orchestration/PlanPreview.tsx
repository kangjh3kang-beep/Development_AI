"use client";

/**
 * PlanPreview — 실행 계획 미리보기.
 *
 * Phase B 블루프린트 §3-B·§2-C(RunStep) 정합. buildPlan 결과(RunStep[])를 실행 전에 보여준다:
 *  - 폐포로 자동 포함된 상류 노드(reason: closure) 표시
 *  - 신선분 스킵(skipReason: fresh) / 미가용 스킵(skipReason: unavailable) 정직 표기
 *  - 과금 합계(estimatedKrw 합) — R8 선표시. 관리자 미설정=0=무료. 동의 후 실행이 원칙.
 *  - unlimited 등급은 합계 대신 "무제한".
 *
 * 무목업: 더미수치 없음. estimatedKrw는 관리자 요율(미설정 0)만 합산한다.
 * 색상은 토큰만 사용(하드코딩 금지).
 */

import { NODES } from "@/lib/orchestration/node-registry";
import type { AnalysisNode, NodeId } from "@/lib/orchestration/types";
import type { RunStep } from "@/store/useOrchestrationStore";

const BY_ID: Record<NodeId, AnalysisNode> = Object.fromEntries(
  NODES.map((n) => [n.id, n]),
) as Record<NodeId, AnalysisNode>;

const won = (n: number) => `${(n ?? 0).toLocaleString("ko-KR")}원`;

/** RunStep reason → 한국어 사유 표기. */
function reasonLabel(step: RunStep): string {
  if (step.skipped) {
    return step.skipReason === "fresh" ? "최신(스킵)" : "미가용(스킵)";
  }
  switch (step.reason) {
    case "selected":
      return "선택";
    case "closure":
      return "의존 자동포함";
    case "guide":
      return "가이드 단계";
    default:
      return "";
  }
}

export interface PlanPreviewProps {
  /** buildPlan 결과. */
  steps: RunStep[];
  /** 무제한 등급(과금 합계 대신 "무제한"). */
  unlimited?: boolean;
}

export function PlanPreview({ steps, unlimited = false }: PlanPreviewProps) {
  const runnable = steps.filter((s) => !s.skipped);
  const skippedFresh = steps.filter((s) => s.skipped && s.skipReason === "fresh");
  const skippedUnavailable = steps.filter(
    (s) => s.skipped && s.skipReason === "unavailable",
  );
  const totalKrw = runnable.reduce((acc, s) => acc + (s.estimatedKrw || 0), 0);
  const chargeableCount = runnable.filter((s) => s.chargeable).length;

  if (steps.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)] p-4 text-center">
        <p className="text-xs text-[var(--text-hint)]">
          분석 항목을 선택하면 실행 계획(상류 의존 포함·과금)이 여기에 표시됩니다.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
      <div className="mb-2.5 flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-bold text-[var(--text-primary)]">실행 계획</p>
        <span className="rounded-full bg-[var(--surface-card)] px-2.5 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)]">
          실행 {runnable.length}개 · 스킵 {skippedFresh.length + skippedUnavailable.length}개
        </span>
      </div>

      {/* 실행 순서(위상순) — 각 노드의 사유 표기 */}
      <ol className="space-y-1.5">
        {steps.map((step, i) => {
          const node = BY_ID[step.node];
          const isSkip = step.skipped;
          return (
            <li
              key={step.node}
              className={`flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-xs ${
                isSkip
                  ? "bg-[var(--surface-muted)] text-[var(--text-tertiary)]"
                  : "bg-[var(--surface-card)] text-[var(--text-secondary)]"
              }`}
            >
              <span className="w-5 shrink-0 text-center font-mono text-[10px] text-[var(--text-hint)]">
                {i + 1}
              </span>
              <span className="min-w-0 flex-1 truncate font-semibold text-[var(--text-primary)]">
                {node?.label ?? step.node}
              </span>
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  isSkip
                    ? "bg-[var(--surface-soft)] text-[var(--text-tertiary)]"
                    : step.reason === "closure"
                      ? "bg-[var(--surface-soft)] text-[var(--text-secondary)]"
                      : "bg-[color-mix(in_srgb,var(--accent-strong)_10%,transparent)] text-[var(--accent-strong)]"
                }`}
              >
                {reasonLabel(step)}
              </span>
              <span className="w-16 shrink-0 text-right font-mono text-[10px] text-[var(--text-tertiary)]">
                {isSkip ? "—" : step.chargeable ? (step.estimatedKrw > 0 ? won(step.estimatedKrw) : "무료") : "무료"}
              </span>
            </li>
          );
        })}
      </ol>

      {/* 과금 합계 — R8 선표시(미설정 0=무료, 동의 후 실행) */}
      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-[var(--line)] pt-3">
        <p className="text-[11px] text-[var(--text-secondary)]">
          {skippedFresh.length > 0 && (
            <span className="mr-2">최신 {skippedFresh.length}개는 재실행·재과금하지 않습니다.</span>
          )}
          {skippedUnavailable.length > 0 && (
            <span className="text-[var(--text-tertiary)]">미가용 {skippedUnavailable.length}개 제외</span>
          )}
        </p>
        <p className="text-xs text-[var(--text-secondary)]">
          예상 과금{" "}
          <b className="text-[var(--text-primary)]">
            {unlimited ? "무제한(관리자)" : totalKrw > 0 ? won(totalKrw) : "무료"}
          </b>
          {!unlimited && chargeableCount > 0 && totalKrw === 0 && (
            <span className="ml-1 text-[var(--text-hint)]">(관리자 미설정 — 무료)</span>
          )}
        </p>
      </div>
    </div>
  );
}
