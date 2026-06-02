/**
 * 프로젝트/분석 서버 동기화 (기기 무관 영속).
 *
 * 프론트 localStorage(zustand) 상태를 로그인 사용자 계정(서버 user_project_store)에
 * 미러링한다. 로그인 시 서버→로컬(syncDown), 변경 시 로컬→서버(debounced syncUp).
 * 비로그인/오프라인이면 localStorage만 사용(graceful).
 */

import { apiClient } from "@/lib/api-client";
import { useProjectStore } from "@/store/useProjectStore";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const CTX_KEYS = [
  "projectId", "projectName", "projectStatus",
  "completedStages", "currentStage",
  "siteAnalysis", "designData", "feasibilityData", "esgData", "complianceData",
  "analysisResults", "snapshots",
] as const;

function isLoggedIn(): boolean {
  return typeof window !== "undefined" && !!window.localStorage.getItem("propai_access_token");
}

// 최초 서버 pull 완료 전에는 push 금지(빈 로컬상태로 서버를 덮어쓰는 사고 방지)
let pulled = false;

export async function syncDown(): Promise<void> {
  if (!isLoggedIn()) return;
  try {
    const res = await apiClient.get<{ data: Record<string, unknown> }>("/store/projects");
    const data = (res?.data || {}) as {
      projectStore?: { projects?: unknown[] };
      contextStore?: Record<string, unknown>;
    };
    if (Array.isArray(data.projectStore?.projects)) {
      useProjectStore.setState({ projects: data.projectStore!.projects as never });
    }
    if (data.contextStore && typeof data.contextStore === "object") {
      const patch: Record<string, unknown> = {};
      for (const k of CTX_KEYS) {
        if (k in data.contextStore!) patch[k] = data.contextStore![k];
      }
      useProjectContextStore.setState(patch as never);
    }
  } catch {
    /* 오프라인/미인증 → 로컬 유지 */
  } finally {
    pulled = true;
  }
}

let timer: ReturnType<typeof setTimeout> | null = null;

export function scheduleSyncUp(): void {
  if (!isLoggedIn() || !pulled) return;
  if (timer) clearTimeout(timer);
  timer = setTimeout(() => { void syncUp(); }, 1500);
}

export async function syncUp(): Promise<void> {
  if (!isLoggedIn()) return;
  try {
    const ps = useProjectStore.getState();
    const cs = useProjectContextStore.getState() as unknown as Record<string, unknown>;
    const contextStore: Record<string, unknown> = {};
    for (const k of CTX_KEYS) contextStore[k] = cs[k];
    // base64 이미지는 용량(서버/네트워크) 절약 위해 제외, 서버 URL만 동기화
    const projects = ps.projects.map((p) => ({
      ...p,
      siteImageUrl:
        p.siteImageUrl && !p.siteImageUrl.startsWith("data:") ? p.siteImageUrl : undefined,
    }));
    await apiClient.put("/store/projects", {
      body: { data: { projectStore: { projects }, contextStore } },
      useMock: false,
    });
  } catch {
    /* 무시 — 다음 변경 때 재시도 */
  }
}
