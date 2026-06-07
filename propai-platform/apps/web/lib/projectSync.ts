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
import { useLandScheduleStore } from "@/store/useLandScheduleStore";

const CTX_KEYS = [
  "projectId", "projectName", "projectStatus",
  "completedStages", "currentStage",
  "siteAnalysis", "designData", "feasibilityData", "esgData", "complianceData",
  "analysisResults", "snapshots",
] as const;

function isLoggedIn(): boolean {
  return typeof window !== "undefined" && !!window.localStorage.getItem("propai_access_token");
}

// 백엔드 UUID 프로젝트만 /projects/{id} 경로로 분석 스냅샷을 직접 영속한다.
// 비-UUID 로컬 프로젝트는 500 회피 위해 기존 user_project_store(syncUp) 경로만 사용.
const _isUuid = (id: string | null | undefined): id is string =>
  !!id && /^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(id);

/** useProjectContextStore의 현재 cross-module 상태에서 ProjectSnapshot 형태를 추출. */
function currentSnapshot(): Record<string, unknown> {
  const s = useProjectContextStore.getState() as unknown as Record<string, unknown>;
  return {
    siteAnalysis: s.siteAnalysis ?? null,
    designData: s.designData ?? null,
    feasibilityData: s.feasibilityData ?? null,
    costData: s.costData ?? null,
    esgData: s.esgData ?? null,
    complianceData: s.complianceData ?? null,
    completedStages: s.completedStages ?? [],
    currentStage: s.currentStage ?? null,
    analysisResults: s.analysisResults ?? [],
    updatedAt: s.updatedAt ?? {},
  };
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
    const ls = (data as { landSchedule?: { byProject?: unknown } }).landSchedule;
    if (ls && typeof ls === "object" && ls.byProject) {
      useLandScheduleStore.setState({ byProject: ls.byProject as never });
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

/* ── 프로젝트별 분석 스냅샷 백엔드 단일출처 동기화 ──
   user_project_store(전체 store blob)와 병행해, 현재 프로젝트의 분석만
   /projects/{id}.analysis_snapshot 컬럼에 직접 영속한다(프로젝트 단위·기기무관).
   UUID 프로젝트에만 적용(로컬 프로젝트는 syncUp 경로 유지). */

let snapTimer: ReturnType<typeof setTimeout> | null = null;

export function scheduleSnapshotSync(): void {
  if (!isLoggedIn() || !pulled) return;
  const pid = useProjectContextStore.getState().projectId;
  if (!_isUuid(pid)) return; // 로컬 프로젝트는 스킵(500 회피)
  if (snapTimer) clearTimeout(snapTimer);
  snapTimer = setTimeout(() => { void pushSnapshot(); }, 1500);
}

export async function pushSnapshot(): Promise<void> {
  if (!isLoggedIn()) return;
  const pid = useProjectContextStore.getState().projectId;
  if (!_isUuid(pid)) return;
  try {
    await apiClient.put(`/projects/${pid}`, {
      body: { analysis_snapshot: currentSnapshot() },
      useMock: false,
      timeoutMs: 30000,
    });
  } catch {
    /* 무시 — 다음 변경 때 재시도(localStorage·user_project_store가 폴백) */
  }
}

const _maxTs = (u: unknown): number => {
  if (!u || typeof u !== "object") return 0;
  const vals = Object.values(u as Record<string, unknown>).filter(
    (v): v is number => typeof v === "number",
  );
  return vals.length ? Math.max(...vals) : 0;
};

/** 이미 확보한 백엔드 snapshot을 store에 적용(중복 GET 없이 ProjectContextBinder가 사용).
    백엔드를 우선 출처로 삼되, 로컬 updatedAt이 더 최신이면 보존(기기간 최신 우선). */
export function applyRemoteSnapshot(
  projectId: string,
  snap: Record<string, unknown> | null | undefined,
): void {
  if (!_isUuid(projectId) || !snap || typeof snap !== "object") return;
  const ctx = useProjectContextStore.getState();
  // 현재 활성 프로젝트가 대상과 다르면(전환됨) 복원 중단(경합 방지).
  if (ctx.projectId !== projectId) return;

  const backendTs = _maxTs((snap as Record<string, unknown>).updatedAt);
  const localTs = _maxTs(ctx.updatedAt);
  if (localTs > backendTs) return; // 로컬이 더 최신 → 보존

  useProjectContextStore.setState({
    siteAnalysis: (snap.siteAnalysis ?? null) as never,
    designData: (snap.designData ?? null) as never,
    feasibilityData: (snap.feasibilityData ?? null) as never,
    costData: (snap.costData ?? null) as never,
    esgData: (snap.esgData ?? null) as never,
    complianceData: (snap.complianceData ?? null) as never,
    completedStages: (snap.completedStages ?? []) as never,
    currentStage: (snap.currentStage ?? null) as never,
    analysisResults: (snap.analysisResults ?? []) as never,
    updatedAt: (snap.updatedAt ?? {}) as never,
  } as never);
}

/** 프로젝트 로드 시 백엔드 analysis_snapshot을 store로 복원(독립 GET).
    UUID 프로젝트에만 적용. ProjectContextBinder는 이미 meta를 받으므로
    applyRemoteSnapshot을 직접 쓰고, 그 외 진입점에서 이 함수를 쓴다. */
export async function restoreSnapshot(projectId: string): Promise<void> {
  if (!isLoggedIn() || !_isUuid(projectId)) return;
  try {
    const res = await apiClient.get<{ analysis_snapshot?: Record<string, unknown> | null }>(
      `/projects/${projectId}`,
      { useMock: false, timeoutMs: 30000 },
    );
    applyRemoteSnapshot(projectId, res?.analysis_snapshot);
  } catch {
    /* 오프라인/실패 → localStorage 스냅샷 유지 */
  }
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
    const landSchedule = { byProject: useLandScheduleStore.getState().byProject };
    await apiClient.put("/store/projects", {
      body: { data: { projectStore: { projects }, contextStore, landSchedule } },
      useMock: false,
    });
  } catch {
    /* 무시 — 다음 변경 때 재시도 */
  }
}
