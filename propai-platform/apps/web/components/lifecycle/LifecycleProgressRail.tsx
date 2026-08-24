"use client";

/**
 * 라이프사이클 진행 레일 — 10단계 여정 가시화(스토어 단일 source).
 *
 * useProjectContextStore에 이미 존재하는 LIFECYCLE_STAGES·completedStages·
 * currentStage·getNextRecommendedStage 자산을 시각화하는 "뷰"다.
 *   - 완료(채움) / 현재(강조·링) / 다음추천(펄스·점선) / 미시작(흐림)
 *   - 각 단계 클릭 → 해당 프로젝트 상세 탭으로 이동(기존 네비 경로 재사용)
 *   - 활성 프로젝트가 없으면 렌더하지 않음(대시보드 무파괴)
 *
 * 디자인 토큰만 사용(하드코딩 hex 없음). 가로/세로 방향 지원.
 */

import Link from "next/link";
import { motion } from "framer-motion";
import { useHydrated } from "@/hooks/useHydrated";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import {
  LIFECYCLE_STAGES,
  STAGE_META,
  type LifecycleStage,
} from "@/lib/lifecycle-stages";
import { resolveStageLabel } from "@/lib/navigation/nav-i18n";
import { StageIcon } from "@/components/common/StageIcon";

// ★"진행중(partial)" 을 별도 상태로 둔다 — 종전엔 주소만 입력한 부지가 **completed** 로
//   셈해져 "부지분석 완료"인데 설계·수지가 못 도는 모순이 화면에 그대로 나왔다.
//   한 일은 인정하되(pending 아님) 끝났다고 말하지 않는다(completed 아님).
type StageStatus = "completed" | "partial" | "current" | "next" | "pending";

const STATUS_NODE: Record<StageStatus, string> = {
  completed:
    "bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] hover:bg-[var(--accent-strong)]/20",
  current:
    "bg-[var(--accent-strong)]/15 text-[var(--accent-strong)] ring-2 ring-[var(--accent-strong)]/40 shadow-[var(--shadow-glow)]",
  next:
    "bg-[var(--surface-muted)] text-[var(--text-secondary)] border border-dashed border-[var(--accent-strong)]/40 hover:text-[var(--accent-strong)]",
  partial:
    "bg-[var(--surface-muted)] text-[var(--text-secondary)] border border-dashed border-[var(--line-strong)]",
  pending: "bg-[var(--surface-muted)] text-[var(--text-hint)] opacity-60",
};

export function LifecycleProgressRail({
  locale,
  projectId: projectIdProp,
  orientation = "horizontal",
  className = "",
}: {
  locale: string;
  /** route param projectId — store 바인딩 레이스와 무관하게 즉시 렌더되도록 props 우선. */
  projectId?: string;
  orientation?: "horizontal" | "vertical";
  className?: string;
}) {
  const storeProjectId = useProjectContextStore((s) => s.projectId);
  // props가 주어지면 우선(레이아웃 route param), 없으면 store 폴백.
  const projectId = projectIdProp ?? storeProjectId;
  const projectName = useProjectContextStore((s) => s.projectName);
  const completedStages = useProjectContextStore((s) => s.completedStages);
  const currentStage = useProjectContextStore((s) => s.currentStage);
  const getNextRecommendedStage = useProjectContextStore((s) => s.getNextRecommendedStage);
  // 진행도·완료 판정의 단일 소비원(SSOT) — store의 데이터유무 판정 선택자.
  // markStageComplete를 일관 호출하지 않는 모듈 탓에 completedStages가 비어 "0/11 고정"되던
  // 버그를 해소: 실데이터가 채워진 단계(부지분석 등)를 완료로 일관 표시한다.
  // ★완료 판정 SSOT — `stageHasData`("데이터가 있는가")를 완료로 읽던 것이 헬스보드와
  //   갈린 원인이었다. 완료는 `stageCompletion`("끝났는가") 하나로만 판정한다.
  const stageCompletion = useProjectContextStore((s) => s.stageCompletion);
  // ★진행도는 **persist 저장소(localStorage)** 에서 파생된다 — 서버엔 그 저장소가 없다.
  //   재수화 전에 그대로 쓰면 서버 `0` / 클라 `1` 로 **하이드레이션 불일치**가 나고,
  //   React 가 이 서브트리를 버리고 다시 그리며 uncaught error 를 던진다(2026-08-13 실측).
  //   그래서 저장소 파생값은 **재수화 이후에만** 렌더에 쓴다.
  //   잠금: `e2e/hydration-lifecycle-rail.spec.ts`(수정 전 red → 후 green 확인)
  const hydrated = useHydrated();

  // 활성 프로젝트가 없으면 표시하지 않는다(대시보드/레이아웃 무파괴).
  // ★props 로 받은 id 는 route param 이라 서버·클라가 같다 — 게이트 불필요.
  //   store 폴백으로 얻은 값만 재수화 뒤로 미룬다. 안 그러면 **컴포넌트 유무 자체**가 갈린다.
  if (!projectIdProp && !hydrated) return null;
  if (!projectId) return null;

  const nextStage = hydrated ? getNextRecommendedStage() : undefined;
  // 완료 = 사용자가 완료 표시했거나(completedStages) **수치가 확보**됐다(stageCompletion==="done").
  const isDone = (id: LifecycleStage) =>
    hydrated && (completedStages.includes(id) || stageCompletion(id) === "done");
  // 진행중 = 시작은 했으나 수치가 없다(예: 주소만 있고 면적 미확보). 완료로 세지 않는다.
  const isPartial = (id: LifecycleStage) =>
    hydrated && !isDone(id) && stageCompletion(id) === "partial";
  const completedCount = LIFECYCLE_STAGES.filter((id) => isDone(id)).length;
  const partialCount = LIFECYCLE_STAGES.filter((id) => isPartial(id)).length;
  // ★진행률의 분자는 **완료만** 센다. 진행중을 섞으면 다시 "끝난 것처럼" 보인다.
  const pct = Math.round((completedCount / LIFECYCLE_STAGES.length) * 100);

  function statusOf(id: LifecycleStage): StageStatus {
    if (isDone(id)) return "completed";
    if (isPartial(id)) return "partial";
    if (hydrated && currentStage === id) return "current";
    if (nextStage === id) return "next";
    return "pending";
  }

  const isVertical = orientation === "vertical";

  return (
    <section
      className={`rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-4 shadow-[var(--shadow-lg)] ${className}`}
      aria-label="프로젝트 라이프사이클 진행 현황"
    >
      <header className="mb-3 flex items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-black uppercase tracking-[0.25em] text-[var(--accent-strong)]">
            라이프사이클 진행
          </p>
          {hydrated && projectName && (
            <p className="truncate text-[13px] font-bold text-[var(--text-primary)]">{projectName}</p>
          )}
        </div>
        <span className="shrink-0 rounded-full border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-1 text-[11px] font-bold text-[var(--text-secondary)]">
          {hydrated
            ? `완료 ${completedCount}/${LIFECYCLE_STAGES.length} · ${pct}%${partialCount > 0 ? ` · 진행중 ${partialCount}` : ""}`
            : `—/${LIFECYCLE_STAGES.length}`}
        </span>
      </header>

      {/* 진행 바 */}
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div
          className={`h-full rounded-full bg-[var(--accent-strong)] ${
            // 재수화 직후 0%→실제값이 0.5초에 걸쳐 자라 보이지 않게, 첫 채움에는 전이를 끈다.
            hydrated ? "transition-[width] duration-500" : ""
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>

      <ol
        className={
          isVertical
            ? "flex flex-col gap-1.5"
            : // 10단계를 모두 보이게 — 잘림(scrollbar-hide+overflow) 대신 wrap 어포던스.
              "flex flex-wrap items-center gap-y-2 gap-x-1"
        }
      >
        {LIFECYCLE_STAGES.map((id, index) => {
          const meta = STAGE_META[id];
          // ★라벨은 로케일을 탄다 — `locale` 은 이미 링크(`stageRoute`)에만 쓰이고
          //   있었다. 같은 결함이 route-registry 에도 있었고 함께 봉합했다.
          const stageLabel = resolveStageLabel(id, meta.label, locale);
          const status = statusOf(id);

          const node = (
            <motion.div
              initial={{ opacity: 0, y: isVertical ? 0 : 8, x: isVertical ? -8 : 0 }}
              animate={{ opacity: 1, y: 0, x: 0 }}
              transition={{ delay: index * 0.04, duration: 0.25 }}
              className={`relative flex items-center gap-2 rounded-[var(--radius-xl)] px-3 py-2 transition-all duration-300 ${
                isVertical ? "w-full" : "min-w-[88px] flex-col text-center"
              } ${STATUS_NODE[status]} cursor-pointer`}
              title={stageLabel}
            >
              {status === "current" && (
                <span className="absolute -right-1 -top-1 flex h-3 w-3" aria-hidden="true">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent-strong)] opacity-50" />
                  <span className="relative inline-flex h-3 w-3 rounded-full bg-[var(--accent-strong)]" />
                </span>
              )}
              {status === "next" && (
                <span className="absolute -right-1 -top-1 flex h-2.5 w-2.5" aria-hidden="true">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent-strong)] opacity-40" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full border border-[var(--accent-strong)] bg-[var(--surface)]" />
                </span>
              )}
              <span className="flex h-6 w-6 items-center justify-center">
                {status === "completed" ? (
                  <svg
                    width={18}
                    height={18}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
                    <polyline points="22 4 12 14.01 9 11.01" />
                  </svg>
                ) : (
                  <StageIcon id={meta.icon} size={18} />
                )}
              </span>
              <span className="text-[10px] font-bold uppercase leading-tight tracking-[0.08em]">
                {stageLabel}
              </span>
            </motion.div>
          );

          // 모든 단계 진입 허용(pending 포함) — 진입 화면이 needs-input을 정직 안내.
          const cell = (
            <Link href={`/${locale}/projects/${projectId}/${meta.route}`} className="block">
              {node}
            </Link>
          );

          return (
            <li key={id} className={isVertical ? "" : "flex items-center"}>
              {cell}
              {!isVertical && index < LIFECYCLE_STAGES.length - 1 && (
                <span
                  aria-hidden="true"
                  className={`mx-0.5 h-0.5 w-3 shrink-0 rounded-full ${
                    isDone(id)
                      ? "bg-[var(--accent-strong)]"
                      : "bg-[var(--line)]"
                  }`}
                />
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
