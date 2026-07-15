"use client";

/**
 * 다음 단계 CTA — 개요 탭의 순수 진입 유도(읽기전용).
 *
 * P1 구조재편: 기존 딥인티그레이션 8탭 허브(LifecycleStageViews)는 상단탭과 진입이
 * 중복되고 일부 목업이 섞여 있어 제거했다. 대신 단계 SSOT(lib/lifecycle-stages)의
 * getNextRecommendedStage를 사용해 "다음 추천 단계"로 바로 진입하는 단일 CTA만 둔다.
 * (각 단계의 실제 위젯은 해당 서브페이지에 이미 존재 — 기능 손실 없음.)
 *
 * 디자인 토큰만 사용. 활성 프로젝트 컨텍스트가 없으면 렌더하지 않는다.
 */

import Link from "next/link";
import { motion } from "framer-motion";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { LIFECYCLE_STAGES, STAGE_META, type LifecycleStage } from "@/lib/lifecycle-stages";
import { StageIcon } from "@/components/common/StageIcon";

/**
 * 현재 단계(currentStage) 기준 워크플로우상 "바로 다음 단계"를 계산한다.
 * 완료 여부와 무관하게 SSOT(LIFECYCLE_STAGES) 순서의 다음 단계를 반환한다.
 * 현재 단계가 마지막이면 null(=라이프사이클 완료). currentStage가 SSOT에
 * 없는 단계(contracts 등)면 매칭 실패로 폴백 신호(undefined) 반환.
 */
function nextOf(currentStage: string): LifecycleStage | null | undefined {
  const idx = LIFECYCLE_STAGES.indexOf(currentStage as LifecycleStage);
  if (idx === -1) return undefined; // SSOT 외 단계 → 폴백
  if (idx >= LIFECYCLE_STAGES.length - 1) return null; // 마지막 단계 → 완료
  return LIFECYCLE_STAGES[idx + 1];
}

export function NextStageCta({
  locale,
  projectId: projectIdProp,
  currentStage,
}: {
  locale: string;
  /** route param projectId — store 바인딩 레이스와 무관하게 즉시 렌더되도록 props 우선. */
  projectId?: string;
  currentStage?: LifecycleStage | string;
}) {
  const storeProjectId = useProjectContextStore((s) => s.projectId);
  // props가 주어지면 우선(레이아웃 route param), 없으면 store 폴백.
  const projectId = projectIdProp ?? storeProjectId;
  const getNextRecommendedStage = useProjectContextStore((s) => s.getNextRecommendedStage);

  if (!projectId) return null;

  // 현재 단계가 전달되면 그 "바로 다음 단계"로 안내(자기참조 방지).
  // 마지막 단계면 완료 처리. SSOT 외 단계(undefined)는 기존 추천 폴백.
  let next: LifecycleStage | null;
  if (currentStage !== undefined) {
    const resolved = nextOf(currentStage);
    if (resolved === undefined) {
      next = getNextRecommendedStage() as LifecycleStage | null;
    } else {
      next = resolved;
    }
  } else {
    next = getNextRecommendedStage() as LifecycleStage | null;
  }

  // 모든 단계 완료(또는 마지막 단계) → 완료 안내(CTA 숨김).
  if (next === null) return null;

  const target: LifecycleStage = next;
  const meta = STAGE_META[target];

  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.5 }}
      className="flex flex-col items-start gap-6 rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-lg)] sm:flex-row sm:items-center sm:justify-between"
      aria-label="다음 단계 안내"
    >
      <div className="flex items-center gap-5">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-[var(--accent-soft)] text-[var(--accent-strong)] shadow-[var(--shadow-glow)]">
          <StageIcon id={meta.icon} size={26} />
        </div>
        <div className="min-w-0">
          <p className="label-caps text-[var(--accent-strong)]">
            다음 단계
          </p>
          <p className="mt-1 text-lg font-black tracking-tight text-[var(--text-primary)]">
            {meta.label}
          </p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            상단 탭 또는 진행바에서도 각 단계로 이동할 수 있습니다.
          </p>
        </div>
      </div>
      <Link
        href={`/${locale}/projects/${projectId}/${meta.route}`}
        className="inline-flex h-14 shrink-0 items-center gap-3 whitespace-nowrap rounded-full bg-[var(--accent-strong)] px-8 label-caps text-white shadow-[var(--shadow-glow)] transition-all hover:scale-105"
      >
        {meta.label} 진입 ↗
      </Link>
    </motion.section>
  );
}
