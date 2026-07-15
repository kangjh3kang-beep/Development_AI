"use client";

/**
 * 프로젝트 완성도 헬스보드 — 혁신 UX Phase3(additive).
 *
 * store의 `projectCompleteness()` 셀렉터(7단계: 부지·설계·공사비·법규·금융·ESG·인허가)를
 * 단일 진실원으로 사용해 "프로젝트가 어디까지 됐는지"를 도넛 게이지 + 단계 칩으로 보여준다.
 * 가이디드 next-action(getNextRecommendedStage)을 같은 카드에 통합해 "다음에 뭘 할지"를
 * 한눈에 안내한다. 데이터준비가 안 된 단계면 "○○ 먼저 완료" 안내로 폴백한다.
 *
 * 무목업: 각 단계 done/pct는 실데이터(셀렉터) 기반이며, 없으면 "미완료"로 정직 표기.
 * 디자인 토큰만 사용(다크 대비). 라벨/라우트는 lib/lifecycle-stages SSOT에 정합.
 * 활성 프로젝트 컨텍스트가 없으면 렌더하지 않는다(기존 동작 보존).
 */

import Link from "next/link";
import { motion } from "framer-motion";
import { PartyPopper } from "lucide-react";
import {
  useProjectContextStore,
  type ProjectCompletenessKey,
} from "@/store/useProjectContextStore";
import {
  STAGE_META,
  type LifecycleStage,
} from "@/lib/lifecycle-stages";
import { StageIcon } from "@/components/common/StageIcon";

/**
 * 완성도 단계 키(7단계) → SSOT 라이프사이클 단계 매핑.
 * 셀렉터 키(site/cost/compliance)는 일부 라우트명과 다르므로 SSOT 단계로 정규화한다.
 *  - site → site-analysis, cost → construction(시공계획), compliance → legal(법규검토)
 * 매핑된 단계의 STAGE_META로 라벨/라우트/아이콘을 가져온다(라벨 SSOT 정합).
 */
const KEY_TO_STAGE: Record<ProjectCompletenessKey, LifecycleStage> = {
  site: "site-analysis",
  design: "design",
  cost: "construction",
  compliance: "legal",
  finance: "finance",
  esg: "esg",
  permit: "permit",
};

export function ProjectHealthBoard({ locale }: { locale: string }) {
  const projectId = useProjectContextStore((s) => s.projectId);
  const projectCompleteness = useProjectContextStore((s) => s.projectCompleteness);
  const getNextRecommendedStage = useProjectContextStore(
    (s) => s.getNextRecommendedStage,
  );
  // 단계 완료/부분완료는 selector(함수 ref·안정)라 데이터 변경만으로는 리렌더가 안 일어나
  // 완성도가 실제 진행 대비 지연 표시될 수 있다. 모든 모듈 갱신 시 바뀌는 updatedAt을
  // 구독해 변경 시 재계산되도록 한다(표시 정합, 데이터/호출 무변경).
  useProjectContextStore((s) => s.updatedAt);

  if (!projectId) return null;

  const { stages, doneCount, total, pct } = projectCompleteness();

  // 가이디드 next-action: 데이터준비도 기반 추천 단계(없으면 라이프사이클 완료).
  const next = getNextRecommendedStage() as LifecycleStage | null;
  const nextMeta = next ? STAGE_META[next] : null;

  // 도넛 게이지(SVG conic 대신 stroke-dasharray로 토큰색 사용).
  const R = 52;
  const C = 2 * Math.PI * R;
  const dash = (pct / 100) * C;

  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.25 }}
      className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-6 shadow-[var(--shadow-lg)] sm:p-8"
      aria-label="프로젝트 완성도 헬스보드"
    >
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
        {/* ── 도넛 게이지(전체 완성도 %) ── */}
        <div className="flex shrink-0 items-center gap-5">
          <div className="relative h-[128px] w-[128px]">
            <svg
              viewBox="0 0 128 128"
              className="h-full w-full -rotate-90"
              role="img"
              aria-label={`전체 완성도 ${pct}퍼센트`}
            >
              <circle
                cx="64"
                cy="64"
                r={R}
                fill="none"
                stroke="var(--line)"
                strokeWidth="12"
              />
              <circle
                cx="64"
                cy="64"
                r={R}
                fill="none"
                stroke="var(--accent-strong)"
                strokeWidth="12"
                strokeLinecap="round"
                strokeDasharray={`${dash} ${C}`}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-3xl font-[1000] tracking-tighter text-[var(--text-primary)]">
                {pct}%
              </span>
              <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--text-hint)]">
                완성도
              </span>
            </div>
          </div>
          <div className="min-w-0">
            <p className="label-caps text-[var(--accent-strong)]">
              프로젝트 헬스보드
            </p>
            <p className="mt-1 text-lg font-black tracking-tight text-[var(--text-primary)]">
              {doneCount} / {total} 단계 완료
            </p>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              실데이터 기준 — 미완료 단계는 정직 표기됩니다.
            </p>
          </div>
        </div>

        {/* ── 단계 칩(done/미done) ── */}
        <div className="flex flex-1 flex-wrap content-center gap-2">
          {stages.map((st) => {
            const stage = KEY_TO_STAGE[st.key];
            const meta = STAGE_META[stage];
            const state = st.done ? "done" : st.partial ? "partial" : "todo";
            const cls =
              state === "done"
                ? "border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                : state === "partial"
                  ? "border-[var(--line-strong)] bg-[var(--surface-muted)] text-[var(--text-secondary)]"
                  : "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-hint)]";
            return (
              <Link
                key={st.key}
                href={`/${locale}/projects/${projectId}/${meta.route}`}
                className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold transition-all hover:scale-[1.03] ${cls}`}
                aria-label={`${st.label} ${state === "done" ? "완료" : state === "partial" ? "부분 완료" : "미완료"}`}
              >
                <StageIcon id={meta.icon} size={14} />
                <span>{st.label}</span>
                <span aria-hidden className="text-sm leading-none">
                  {state === "done" ? "✓" : state === "partial" ? "◐" : "○"}
                </span>
              </Link>
            );
          })}
        </div>
      </div>

      {/* ── 가이디드 next-action ── */}
      <div className="mt-6 flex flex-col gap-3 border-t border-[var(--line)] pt-5 sm:flex-row sm:items-center sm:justify-between">
        {nextMeta ? (
          <>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent-strong)]">
                <StageIcon id={nextMeta.icon} size={18} />
              </div>
              <div className="min-w-0">
                <p className="label-caps text-[var(--accent-strong)]">
                  다음 추천 작업
                </p>
                <p className="text-sm font-bold text-[var(--text-primary)]">
                  {nextMeta.label} 진행하기
                </p>
              </div>
            </div>
            <Link
              href={`/${locale}/projects/${projectId}/${nextMeta.route}`}
              className="inline-flex h-11 shrink-0 items-center gap-2 whitespace-nowrap rounded-full bg-[var(--accent-strong)] px-6 label-caps text-white shadow-[var(--shadow-glow)] transition-all hover:scale-105"
            >
              {nextMeta.label} 진입 ↗
            </Link>
          </>
        ) : (
          <p className="inline-flex items-center gap-1.5 text-sm font-bold text-[var(--text-secondary)]">
            모든 추천 단계를 완료했습니다 — 라이프사이클 완료 <PartyPopper className="size-4" aria-hidden />
          </p>
        )}
      </div>
    </motion.section>
  );
}
