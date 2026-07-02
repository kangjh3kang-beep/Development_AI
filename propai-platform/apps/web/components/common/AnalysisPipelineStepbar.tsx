"use client";

/**
 * AnalysisPipelineStepbar — 생성허브 공용 "분석 파이프라인 3단계" 스텝바 (공용).
 *
 * 왜 필요한가(쉬운 설명):
 * 각 산출물이 "어떤 데이터를 수집해 → 어떻게 검증하고 → 어떤 전문가 LLM으로 완결했는지"의
 * 진행 상태가 화면마다 제각각이거나 아예 없었다. 이 공용 스텝바로 6산출물이 동일한 3단계
 * (수집 → 검증(교차·정직강등) → 전문가 LLM 완결) 표기를 공유한다(한 곳을 고치면 6페이지 따라옴).
 *
 * ★ProjectLifecyclePipeline(10단계 라이프사이클)과 별개 — 이건 "한 산출물의 분석 3단계"다.
 * ★props-driven: 각 단계 상태(대기/진행/완료/실패)와 데이터원 라벨을 호출측이 주입한다(무목업:
 *   실제 상태만 전달, 추정/시장표준 데이터를 쓰면 "추정·시장표준" 정직배지 슬롯으로 명시).
 * ★디자인 토큰만 사용(--accent-strong 등).
 */

/** 단계 상태 — 대기/진행/완료/실패. */
export type PipelineStepStatus = "idle" | "running" | "done" | "failed";

/** 3단계 파이프라인의 각 단계(id 고정: collect/verify/expert). */
export type PipelineStepId = "collect" | "verify" | "expert";

export interface PipelineStep {
  id: PipelineStepId;
  /** 단계 라벨(기본값 있음 — 미전달 시 표준 라벨 사용). */
  label?: string;
  status: PipelineStepStatus;
  /** 데이터원 라벨(예: "VWorld·MOLIT 실거래"). 없으면 미표시. */
  sourceLabel?: string | null;
  /** 추정·시장표준 데이터 사용 시 정직배지(예: "추정·시장표준"). 없으면 미표시. */
  honestBadge?: string | null;
}

/** 표준 3단계 기본 라벨. */
const DEFAULT_LABELS: Record<PipelineStepId, string> = {
  collect: "수집",
  verify: "검증 (교차·정직강등)",
  expert: "전문가 LLM 완결",
};

/** 상태별 색/아이콘 토큰. */
function stepVisual(status: PipelineStepStatus): {
  ring: string;
  text: string;
  dot: string;
} {
  switch (status) {
    case "done":
      return {
        ring: "border-[var(--accent-strong)]/50 bg-[var(--accent-strong)]/10",
        text: "text-[var(--accent-strong)]",
        dot: "bg-[var(--accent-strong)]",
      };
    case "running":
      return {
        ring: "border-[var(--accent-strong)]/40 bg-[var(--surface-secondary)]",
        text: "text-[var(--text-primary)]",
        dot: "bg-[var(--accent-strong)] animate-pulse",
      };
    case "failed":
      return {
        ring: "border-[var(--danger,#dc2626)]/40 bg-[var(--surface-secondary)]",
        text: "text-[var(--danger,#dc2626)]",
        dot: "bg-[var(--danger,#dc2626)]",
      };
    case "idle":
    default:
      return {
        ring: "border-[var(--line)] bg-[var(--surface-soft)]",
        text: "text-[var(--text-hint)]",
        dot: "bg-[var(--text-hint)]",
      };
  }
}

function StepNode({ step, index }: { step: PipelineStep; index: number }) {
  const label = step.label ?? DEFAULT_LABELS[step.id];
  const v = stepVisual(step.status);
  return (
    <div className="flex min-w-0 flex-1 items-start gap-2">
      <span
        className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[10px] font-black ${v.ring} ${v.text}`}
        aria-hidden="true"
      >
        {step.status === "done" ? (
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 6 9 17l-5-5" />
          </svg>
        ) : (
          index + 1
        )}
      </span>
      <span className="min-w-0">
        <span className={`block text-[12px] font-bold leading-tight ${v.text}`}>{label}</span>
        {step.sourceLabel && (
          <span className="block truncate text-[10px] font-medium text-[var(--text-tertiary)]" title={step.sourceLabel}>
            {step.sourceLabel}
          </span>
        )}
        {step.honestBadge && (
          <span className="mt-0.5 inline-block rounded-full border border-[var(--warning,#d97706)]/40 bg-[var(--warning,#d97706)]/10 px-1.5 py-0.5 text-[9px] font-bold leading-none text-[var(--warning,#d97706)]">
            {step.honestBadge}
          </span>
        )}
      </span>
    </div>
  );
}

/** 표준 3단계를 채운 기본 스텝(전부 대기) — 호출측이 부분 override 하기 쉽게 노출. */
export function defaultPipelineSteps(): PipelineStep[] {
  return [
    { id: "collect", status: "idle" },
    { id: "verify", status: "idle" },
    { id: "expert", status: "idle" },
  ];
}

export function AnalysisPipelineStepbar({
  steps,
  title = "분석 파이프라인",
  className = "",
}: {
  /** 3단계(collect/verify/expert). 미전달 시 전부 대기 상태로 표시. */
  steps?: PipelineStep[];
  title?: string;
  className?: string;
}) {
  const rows = steps && steps.length > 0 ? steps : defaultPipelineSteps();

  return (
    <div
      className={`rounded-xl border border-[var(--line)] bg-[var(--surface-secondary)] px-4 py-2.5 ${className}`}
    >
      {title && (
        <p className="mb-2 text-[10px] font-black uppercase tracking-wider text-[var(--text-hint)]">
          {title}
        </p>
      )}
      <div className="flex items-stretch gap-1.5">
        {rows.map((step, i) => (
          <div key={step.id} className="flex min-w-0 flex-1 items-center">
            <StepNode step={step} index={i} />
            {i < rows.length - 1 && (
              <span className="mx-1 hidden h-px flex-1 self-center bg-[var(--line)] sm:block" aria-hidden="true" />
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
