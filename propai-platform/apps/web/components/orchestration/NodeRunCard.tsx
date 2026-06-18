"use client";

/**
 * NodeRunCard — 단일 노드 실행 결과 카드.
 *
 * Phase B 블루프린트 §3·§6(e) 정합. 한 노드의 실행 결과를 정직하게 보여준다:
 *  - 실행 상태(idle/running/done/skipped-fresh/skipped-unavailable/needs-input/error)
 *  - 검증 판정(verifyStatus: pass/warn/fail) 배지
 *  - 그라운딩(사실근거) 출처별 ok/unavailable 정직 표기(0 강제·더미 금지)
 *  - 미가용·미실행은 더미수치 대신 정직 라벨 + 실행 CTA(상위가 onRun 주입 시).
 *
 * 무목업: nodeResult가 없거나 미가용이면 "준비중/미실행"을 정직 표기한다.
 * 색상은 토큰만 사용(하드코딩 금지), WCAG AA 대비 유지.
 */

import { Card, CardContent } from "@propai/ui";
import { NODES } from "@/lib/orchestration/node-registry";
import type { AnalysisNode, NodeId } from "@/lib/orchestration/types";
import type {
  NodeResult,
  NodeRunState,
  NodeVerifyStatus,
} from "@/store/useOrchestrationStore";

const BY_ID: Record<NodeId, AnalysisNode> = Object.fromEntries(
  NODES.map((n) => [n.id, n]),
) as Record<NodeId, AnalysisNode>;

/** 실행 상태 → 한국어 라벨 + 토큰 색(상태 색은 토큰만). */
const STATE_META: Record<
  NodeRunState,
  { label: string; tone: "neutral" | "accent" | "ok" | "warn" | "muted" }
> = {
  idle: { label: "대기", tone: "muted" },
  queued: { label: "대기열", tone: "neutral" },
  running: { label: "실행 중", tone: "accent" },
  done: { label: "완료", tone: "ok" },
  "skipped-fresh": { label: "최신(스킵)", tone: "muted" },
  "skipped-unavailable": { label: "미가용", tone: "warn" },
  "needs-input": { label: "입력 필요", tone: "warn" },
  error: { label: "오류", tone: "warn" },
};

/** 검증 판정 → 라벨/색. null은 미검증(정직). */
const VERIFY_META: Record<
  Exclude<NodeVerifyStatus, null>,
  { label: string; color: string }
> = {
  pass: { label: "검증 통과", color: "var(--status-success, var(--accent-strong))" },
  warn: { label: "검증 주의", color: "var(--status-warning)" },
  fail: { label: "검증 실패", color: "var(--status-error, var(--status-warning))" },
};

function toneClass(tone: "neutral" | "accent" | "ok" | "warn" | "muted"): string {
  switch (tone) {
    case "accent":
      return "border-[var(--accent-strong)] text-[var(--accent-strong)] bg-[color-mix(in_srgb,var(--accent-strong)_8%,transparent)]";
    case "ok":
      return "border-[var(--accent-strong)] text-[var(--accent-strong)] bg-[color-mix(in_srgb,var(--accent-strong)_6%,transparent)]";
    case "warn":
      return "border-[var(--status-warning)] text-[var(--status-warning)] bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)]";
    case "muted":
      return "border-[var(--line)] text-[var(--text-tertiary)] bg-[var(--surface-muted)]";
    default:
      return "border-[var(--line-strong)] text-[var(--text-secondary)] bg-[var(--surface-soft)]";
  }
}

const won = (n: number) => `${(n ?? 0).toLocaleString("ko-KR")}원`;

export interface NodeRunCardProps {
  /** 노드 식별자. */
  nodeId: NodeId;
  /** 실행 결과(미실행이면 undefined → 정직 미실행 표기). */
  result?: NodeResult;
  /** 실행 CTA(미실행·재실행). 미전달 시 버튼 숨김. */
  onRun?: (id: NodeId) => void;
  /** CTA 비활성(코인 부족 등). */
  runDisabled?: boolean;
}

export function NodeRunCard({ nodeId, result, onRun, runDisabled = false }: NodeRunCardProps) {
  const node = BY_ID[nodeId];
  if (!node) return null;

  const state: NodeRunState = result?.state ?? "idle";
  const meta = STATE_META[state];
  const verify = result?.verifyStatus ?? null;
  const grounding = result?.grounding ?? {};
  const groundingEntries = Object.entries(grounding);
  // 미가용·미실행·오류는 실행 CTA를 띄운다(available 노드만).
  const canRun =
    !!onRun &&
    node.available &&
    (state === "idle" || state === "needs-input" || state === "error" || state === "skipped-unavailable");

  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-sm)]">
      <CardContent className="p-4">
        {/* 헤더: 노드 라벨 + 상태 배지 */}
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-sm font-bold text-[var(--text-primary)]">
              {node.label}
            </p>
            <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
              {node.groundingSources.length > 0
                ? `근거: ${node.groundingSources.join("·")}`
                : node.label}
            </p>
          </div>
          <span
            className={`shrink-0 rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${toneClass(meta.tone)}`}
          >
            {state === "running" && (
              <span className="cc-live mr-1 inline-flex align-middle">
                <i />
              </span>
            )}
            {meta.label}
          </span>
        </div>

        {/* 검증 배지 + 과금 표기(완료 시) */}
        {(verify || (result && result.chargedKrw > 0)) && (
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            {verify && (
              <span
                className="rounded-full px-2 py-0.5 text-[10px] font-bold"
                style={{
                  color: VERIFY_META[verify].color,
                  backgroundColor: `color-mix(in srgb, ${VERIFY_META[verify].color} 12%, transparent)`,
                }}
              >
                {VERIFY_META[verify].label}
              </span>
            )}
            {result && result.chargedKrw > 0 && (
              <span className="rounded-full bg-[var(--surface-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
                과금 {won(result.chargedKrw)}
              </span>
            )}
            {result?.verifyStatus == null && state === "done" && (
              <span className="text-[10px] text-[var(--text-hint)]">검증 미수행(정직 표기)</span>
            )}
          </div>
        )}

        {/* 그라운딩(사실근거) 출처별 ok/unavailable 정직 표기 */}
        {groundingEntries.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-1.5">
            {groundingEntries.map(([src, status]) => (
              <span
                key={src}
                className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${
                  status === "ok"
                    ? "bg-[var(--surface-soft)] text-[var(--text-secondary)]"
                    : "bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] text-[var(--status-warning)]"
                }`}
                title={status === "ok" ? "실값 확보" : "미확보(정직 표기)"}
              >
                {status === "ok" ? "✓" : "—"} {src.replace(/^input:/, "입력 ")}
              </span>
            ))}
          </div>
        )}

        {/* 오류 메시지(정직) */}
        {state === "error" && result?.error && (
          <p className="mt-2.5 text-[11px] text-[var(--status-warning)]">오류: {result.error}</p>
        )}

        {/* 미가용·미실행 정직 라벨 + 실행 CTA */}
        {!node.available && (
          <p className="mt-2.5 text-[11px] text-[var(--text-tertiary)]">
            {node.reportContract.unavailableLabel || "현재 이용 불가"}
          </p>
        )}
        {canRun && (
          <button
            type="button"
            onClick={() => onRun?.(nodeId)}
            disabled={runDisabled}
            className="mt-3 whitespace-nowrap rounded-xl border border-[var(--accent-strong)] px-3.5 py-1.5 text-[11px] font-bold text-[var(--accent-strong)] transition-colors hover:bg-[color-mix(in_srgb,var(--accent-strong)_8%,transparent)] disabled:opacity-50"
          >
            {state === "error" || state === "skipped-unavailable" ? "다시 실행" : "실행"}
          </button>
        )}
      </CardContent>
    </Card>
  );
}
