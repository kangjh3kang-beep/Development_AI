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
import { STAGE_META, type LifecycleStage } from "@/lib/lifecycle-stages";
import { StageIcon } from "@/components/common/StageIcon";

export function NextStageCta({ locale }: { locale: string }) {
  const projectId = useProjectContextStore((s) => s.projectId);
  const getNextRecommendedStage = useProjectContextStore((s) => s.getNextRecommendedStage);

  if (!projectId) return null;

  const next = getNextRecommendedStage() as LifecycleStage | null;
  // 모든 단계 완료 → 보고서로 마무리 유도.
  const target: LifecycleStage = next ?? "report";
  const meta = STAGE_META[target];
  const allDone = next === null;

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
          <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--accent-strong)]">
            {allDone ? "라이프사이클 완료" : "다음 추천 단계"}
          </p>
          <p className="mt-1 text-lg font-black tracking-tight text-[var(--text-primary)]">
            {meta.label}
          </p>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {allDone
              ? "모든 단계가 완료되었습니다. 최종 보고서를 확인하세요."
              : "상단 탭 또는 진행바에서도 각 단계로 이동할 수 있습니다."}
          </p>
        </div>
      </div>
      <Link
        href={`/${locale}/projects/${projectId}/${meta.route}`}
        className="inline-flex h-14 shrink-0 items-center gap-3 whitespace-nowrap rounded-full bg-[var(--accent-strong)] px-8 text-xs font-black uppercase tracking-[0.2em] text-white shadow-[var(--shadow-glow)] transition-all hover:scale-105"
      >
        {meta.label} 진입 ↗
      </Link>
    </motion.section>
  );
}
