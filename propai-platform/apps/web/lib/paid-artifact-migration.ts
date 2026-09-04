/**
 * 레거시 **공유키**에 남아 있는 유료 산출물을 **계정별 키로 승계**한다.
 *
 * ## 무엇을 옮기나
 *
 * `propai-paid-renders`(렌더 **3,000원/건**) · `propai-registry-analysis`(등기 권리분석
 * **1,200원/필지**) 는 계정 격리 이전에 **한 브라우저에서 공유되는 키 하나**에 쌓였다.
 * 이제 어댑터가 `<base>__<uid>` 로 쓰므로, 그 이전 저장분은 **아무 계정도 못 본다** —
 * 옮겨 주지 않으면 사용자가 이미 낸 돈이 화면에서 사라진다.
 *
 * ## ★원본을 지우지 않는다
 *
 * 레거시 키는 **읽기만** 한다. 귀속을 잘못해도 원본이 남아 있어, 진짜 주인이 다음에
 * 로그인하면 그때 가져간다. 그래서 이 마이그레이션은 **몇 번 돌려도 안전**하고
 * (승계한 버킷은 `already-owned` 로 건너뛴다), 레거시 키는 와이프 대상이 아니다.
 *
 * ## 언제 부르나
 *
 * `syncFromBackend` 가 **프로젝트 목록을 끝까지 받은 직후**다. 귀속 규칙이 그 목록을
 * 재료로 쓰기 때문이다 — 목록이 절단됐거나 비었으면 판단이 **미룸**으로 떨어진다.
 */
import { currentUserId, GUEST_SCOPE } from "@/lib/account-scope";
import { decideMigration, readLegacyByProject } from "@/lib/account-scoped-storage";
import { DEVELOPMENT_PLAN_STORE_KEY, useDevelopmentPlanStore } from "@/store/useDevelopmentPlanStore";
import { PAID_RENDER_STORE_KEY, usePaidRenderStore } from "@/store/usePaidRenderStore";
import {
  REGISTRY_ANALYSIS_STORE_KEY,
  useRegistryAnalysisStore,
} from "@/store/useRegistryAnalysisStore";

/**
 * 한 스토어의 처리 결과.
 *
 * ★★**정직 고지 — 이 값은 아직 아무도 읽지 않는다(부채).**
 *   종전 주석은 *"왜 안 옮겼는지까지 말한다(조용한 건너뜀 금지)"* 라고 적었는데,
 *   유일한 호출부(`store/useProjectStore.ts` 의 `syncFromBackend`)가 **반환을 버린다.**
 *   즉 **말할 준비만 되어 있고 말하는 곳이 없다** — 주장과 실행이 갈린 상태다
 *   (CLAUDE.md §G30: *"…한다"는 동작 주장은 그 자체가 검증 대상이다*).
 *
 *   ★**왜 지금 안 고치나**: 쓸 만한 통로가 둘 다 이 변경의 범위를 넘는다 —
 *    ①성장루프 이벤트로 보내려면 `GrowthEventType` 과 백엔드 `growth.py:_ALLOWED_TYPES` 를
 *      **같은 커밋에서** 늘려야 한다(한쪽만 하면 서버가 조용히 `rejected` 로 버리고 화면은 초록이다)
 *    ②사용자에게 알리려면(예: *"승계를 미뤘습니다 — 목록이 아직 불완전합니다"*)
 *      **어디에 어떻게 띄울지가 제품 판단**이다.
 *   ★사용자 영향: `defer` 일 때 레거시의 유료 산출물이 **화면에 안 보이는데 이유도 없다.**
 *     다만 다음 동기화에 자동 재시도되므로 **데이터가 사라지지는 않는다**(안전장치 1).
 *
 *   부채를 초록 안에서 보이게 `lib/__tests__/paid-artifact-account-isolation.test.ts` 에
 *   `it.todo` 로 남긴다 — 커밋 메시지에만 적으면 드러나지 않는다(회귀망 규율 C-13).
 */
export type PaidArtifactMigrationReport = {
  store: string;
  action: "migrate" | "defer" | "noop" | "skip";
  reason: string;
  /** 이번에 승계한 프로젝트 버킷 수. */
  adopted: number;
};

type ByProject = Record<string, unknown[]>;

/** 스토어 하나를 처리한다(테스트가 스토어 배선과 무관하게 태울 수 있도록 인자를 받는다). */
export function migrateOneStore(args: {
  store: string;
  legacyKey: string;
  owned: ByProject;
  visibleProjectIds: ReadonlySet<string>;
  truncated: boolean;
  commit: (merged: ByProject) => void;
  readLegacy?: (key: string) => ByProject | null;
}): PaidArtifactMigrationReport {
  const read = args.readLegacy ?? readLegacyByProject;
  const decision = decideMigration<unknown>({
    legacy: read(args.legacyKey),
    owned: args.owned,
    visibleProjectIds: args.visibleProjectIds,
    truncated: args.truncated,
  });
  if (decision.action === "migrate") {
    args.commit(decision.merged);
    return {
      store: args.store,
      action: "migrate",
      reason: `승계 ${decision.adopted.length}건 · 남김 ${decision.left.length}건`,
      adopted: decision.adopted.length,
    };
  }
  return { store: args.store, action: decision.action, reason: decision.reason, adopted: 0 };
}

/**
 * 두 유료 산출물 스토어를 한 번에 처리한다.
 *
 * ★비로그인(`guest`)이면 **아무것도 하지 않는다** — 귀속할 계정이 없는데 옮기면 다음에
 *   로그인한 사람의 것이 되어 버린다. 이 함수가 막으려는 그 누출을 스스로 만드는 셈이다.
 */
export function migratePaidArtifacts(args: {
  visibleProjectIds: ReadonlySet<string>;
  truncated: boolean;
}): PaidArtifactMigrationReport[] {
  if (currentUserId() === GUEST_SCOPE) {
    return [
      { store: PAID_RENDER_STORE_KEY, action: "skip", reason: "guest", adopted: 0 },
      { store: REGISTRY_ANALYSIS_STORE_KEY, action: "skip", reason: "guest", adopted: 0 },
      { store: DEVELOPMENT_PLAN_STORE_KEY, action: "skip", reason: "guest", adopted: 0 },
    ];
  }
  return [
    migrateOneStore({
      store: PAID_RENDER_STORE_KEY,
      legacyKey: PAID_RENDER_STORE_KEY,
      owned: usePaidRenderStore.getState().byProject as unknown as ByProject,
      visibleProjectIds: args.visibleProjectIds,
      truncated: args.truncated,
      commit: (merged) => usePaidRenderStore.setState({ byProject: merged } as never),
    }),
    migrateOneStore({
      store: REGISTRY_ANALYSIS_STORE_KEY,
      legacyKey: REGISTRY_ANALYSIS_STORE_KEY,
      owned: useRegistryAnalysisStore.getState().byProject as unknown as ByProject,
      visibleProjectIds: args.visibleProjectIds,
      truncated: args.truncated,
      commit: (merged) => useRegistryAnalysisStore.setState({ byProject: merged } as never),
    }),
    // ★유료는 아니지만 **같은 클래스**다 — 구조가 같으니(byProject) 같은 기계로 덮는다.
    //   "고친 자리의 형제를 스윕한다"(버그수정 기본정책 전역 전파방지).
    migrateOneStore({
      store: DEVELOPMENT_PLAN_STORE_KEY,
      legacyKey: DEVELOPMENT_PLAN_STORE_KEY,
      owned: useDevelopmentPlanStore.getState().byProject as unknown as ByProject,
      visibleProjectIds: args.visibleProjectIds,
      truncated: args.truncated,
      commit: (merged) => useDevelopmentPlanStore.setState({ byProject: merged } as never),
    }),
  ];
}
