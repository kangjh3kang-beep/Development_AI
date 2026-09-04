/**
 * 프로젝트 **삭제 생명주기 트리거** — 지운 프로젝트가 되살아나던 것.
 *
 * ## 무엇이 있었나(실측)
 *
 * `deleteProject`(`store/useProjectStore.ts`)는 **프로젝트 목록에서만** 지운다. 그런데
 * 프로젝트에 딸린 로컬 데이터는 세 곳에 더 남는다:
 *
 *   · `useProjectContextStore.snapshots[id]`  — 프로젝트별 분석 캐시.
 *     삭제 액션이 **전 코드베이스에 0건**이었다(`snapshots` 참조 14건 중 지우는 곳 없음).
 *   · `useLandScheduleStore.byProject[id]`    — 토지조서. per-project 제거 경로 없음.
 *   · `useProjectContextStore.projectId`      — 활성 프로젝트가 지워진 id 인 채로 남는다.
 *
 * ★그리고 `snapshots` 는 `CTX_KEYS` 에 들어 있어 **매 syncUp 마다 서버 blob 으로 재업로드**된다.
 *   즉 지운 프로젝트의 분석이 서버에 남고, 다음 `syncDown` 이 그것을 다시 내려 준다 —
 *   **삭제가 동기화로 되돌려진다.**
 *
 * ## 왜 store 액션이 아니라 여기인가
 *
 * 정리 대상이 **서로 다른 세 스토어**에 걸쳐 있다. 어느 한 스토어의 액션으로 만들면 그 스토어가
 * 나머지를 import 해야 해서 순환이 생긴다. 생명주기는 **스토어 위 계층**의 일이다.
 */
import { useLandScheduleStore } from "@/store/useLandScheduleStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/** 정리 결과 — 호출부가 "무엇이 실제로 지워졌는지" 확인·기록할 수 있게 사실만 돌려준다. */
export interface ProjectPurgeResult {
  snapshotRemoved: boolean;
  landScheduleRemoved: boolean;
  activeContextCleared: boolean;
}

/**
 * 프로젝트에 딸린 **로컬** 데이터를 전부 정리한다(서버 삭제는 호출부 소관).
 *
 * ★멱등하다 — 이미 없는 것은 없다고 답하고 아무것도 바꾸지 않는다.
 * ★활성 프로젝트를 지우면 컨텍스트도 비운다. 안 그러면 화면이 **존재하지 않는 프로젝트**를
 *   가리킨 채로 남고, 그 상태에서 분석을 하면 고아 데이터가 다시 생긴다.
 */
export function purgeProjectLocalData(projectId: string): ProjectPurgeResult {
  const result: ProjectPurgeResult = {
    snapshotRemoved: false,
    landScheduleRemoved: false,
    activeContextCleared: false,
  };
  if (!projectId) return result;

  try {
    const ctx = useProjectContextStore.getState();
    const snapshots = { ...((ctx.snapshots ?? {}) as Record<string, unknown>) };
    if (projectId in snapshots) {
      delete snapshots[projectId];
      result.snapshotRemoved = true;
    }
    const patch: Record<string, unknown> = { snapshots };
    if (ctx.projectId === projectId) {
      // 활성 컨텍스트 초기화 — clearProject 와 같은 자리를 비운다(파생까지 함께).
      Object.assign(patch, {
        projectId: null,
        projectName: "",
        projectStatus: "",
        siteAnalysis: null,
        designData: null,
        feasibilityData: null,
        costData: null,
        esgData: null,
        complianceData: null,
        decisionBrief: null,
        completedStages: [],
        currentStage: null,
        analysisResults: [],
        updatedAt: {},
        manualFields: {},
      });
      result.activeContextCleared = true;
    }
    if (result.snapshotRemoved || result.activeContextCleared) {
      useProjectContextStore.setState(patch as never);
    }
  } catch {
    /* 스토어 미초기화(SSR 등) — 정리 실패는 삭제 자체를 막지 않는다 */
  }

  try {
    const ls = useLandScheduleStore.getState();
    const byProject = { ...((ls.byProject ?? {}) as Record<string, unknown>) };
    if (projectId in byProject) {
      delete byProject[projectId];
      result.landScheduleRemoved = true;
      useLandScheduleStore.setState({ byProject } as never);
    }
  } catch {
    /* 위와 같다 */
  }

  return result;
}
