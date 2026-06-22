/**
 * 프로젝트/분석 서버 동기화 (기기 무관 영속).
 *
 * 프론트 localStorage(zustand) 상태를 로그인 사용자 계정(서버 user_project_store)에
 * 미러링한다. 로그인 시 서버→로컬(syncDown), 변경 시 로컬→서버(debounced syncUp).
 * 비로그인/오프라인이면 localStorage만 사용(graceful).
 */

import { apiClient } from "@/lib/api-client";
import { useProjectStore } from "@/store/useProjectStore";
import {
  useProjectContextStore,
  addressTokenMismatch,
  purifyPollutedSnapshot,
} from "@/store/useProjectContextStore";
import { useLandScheduleStore } from "@/store/useLandScheduleStore";

const CTX_KEYS = [
  "projectId", "projectName", "projectStatus",
  "completedStages", "currentStage",
  "siteAnalysis", "designData", "feasibilityData", "costData", "esgData", "complianceData",
  "analysisResults", "snapshots",
] as const;

function isLoggedIn(): boolean {
  return typeof window !== "undefined" && !!window.localStorage.getItem("propai_access_token");
}

// ── 계정 간 데이터 격리 ──────────────────────────────────────────────
// localStorage(zustand persist)는 브라우저 단위라, 로그아웃/계정전환 때 비우지 않으면
// 같은 브라우저의 다른 계정에 이전 계정 분석이 노출된다(격리붕괴). 아래로 원천 차단한다.
const DATA_OWNER_KEY = "propai_data_owner";
// 분석/프로젝트 데이터가 담긴 localStorage 키 전체(토큰은 별도 관리).
const PROJECT_PERSIST_KEYS = [
  "propai-project-context",   // useProjectContextStore (snapshots·analysisResults·siteAnalysis 등)
  "propai-land-schedule",     // useLandScheduleStore
  "propai-project-storage",   // useProjectStore
  "propai-system-storage",    // useSystemStore (LLM provider·입력 API키 등 민감)
  "propai_pipeline_history",  // 파이프라인 분석이력(프로젝트 상세)
  "propai_precheck_handoff",  // PreCheck 분석결과 전달(localStorage일 수도)
];
// 주소+컨텍스트 해시로 만들어지는 동적 캐시 키(개수 가변) — 접두사 패턴으로 일괄 제거.
const PROJECT_PERSIST_PREFIXES = [
  "propai_panel_",        // 전문가 패널 분석결과(9유형)
  "propai_scenario_",     // 개발 시나리오 시뮬레이션
  "propai_verification_", // 검증 배지 캐시
];

/** JWT 페이로드에서 사용자 식별자(sub/user_id)를 디코드. 실패 시 null. */
function decodeTokenUser(token: string | null): string | null {
  if (!token) return null;
  try {
    const seg = token.split(".")[1];
    if (!seg) return null;
    const json = atob(seg.replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(json) as Record<string, unknown>;
    const uid = payload.sub ?? payload.user_id ?? payload.uid;
    return uid ? String(uid) : null;
  } catch {
    return null;
  }
}

/** 현재 로그인 사용자 식별자(localStorage 키 분리용). 비로그인이면 "guest". */
export function currentUserId(): string {
  if (typeof window === "undefined") return "guest";
  return decodeTokenUser(window.localStorage.getItem("propai_access_token")) || "guest";
}

/** 모든 프로젝트/분석 로컬 데이터를 완전 초기화(메모리 store + localStorage). 토큰은 건드리지 않음. */
export function clearAllProjectData(): void {
  if (typeof window === "undefined") return;
  try {
    useProjectContextStore.setState({
      projectId: null, projectName: "", projectStatus: "",
      completedStages: [], currentStage: null,
      siteAnalysis: null, designData: null, feasibilityData: null,
      costData: null, esgData: null, complianceData: null,
      analysisResults: [], snapshots: {}, updatedAt: {}, analysisCache: {},
    } as never);
  } catch { /* noop */ }
  try { useProjectStore.setState({ projects: [] } as never); } catch { /* noop */ }
  try { useLandScheduleStore.setState({ byProject: {} } as never); } catch { /* noop */ }
  pulled = false; // 빈 상태가 서버로 syncUp되지 않도록(scheduleSyncUp이 pulled=false면 무시)
  for (const k of PROJECT_PERSIST_KEYS) {
    try { window.localStorage.removeItem(k); } catch { /* noop */ }
  }
  // 동적 해시 캐시 키(propai_panel_*·propai_scenario_*·propai_verification_*) 패턴 일괄 제거.
  try {
    for (const k of Object.keys(window.localStorage)) {
      if (PROJECT_PERSIST_PREFIXES.some((p) => k.startsWith(p))) {
        try { window.localStorage.removeItem(k); } catch { /* noop */ }
      }
    }
  } catch { /* noop */ }
  // 세션 저장소의 현장앱 토큰·핸드오프도 정리(계정 전환 시 잔존 방지).
  try {
    for (const k of Object.keys(window.sessionStorage)) {
      if (k.startsWith("propai_site_token:") || k === "propai_precheck_handoff") {
        try { window.sessionStorage.removeItem(k); } catch { /* noop */ }
      }
    }
  } catch { /* noop */ }
}

/** 로그아웃: 분석데이터 + 소유자 표식 모두 제거(다음 로그인은 새 계정으로 깨끗이 시작). */
export function clearOnLogout(): void {
  clearAllProjectData();
  try { window.localStorage.removeItem(DATA_OWNER_KEY); } catch { /* noop */ }
}

/** 현재 토큰의 사용자와 로컬 데이터 소유자가 다르면(계정 전환·잔존) 로컬을 즉시 비운다.
 *  앱 로드/로그인 직후 호출 → 다른 계정 데이터 노출을 원천 차단. */
export function ensureDataOwner(): void {
  if (typeof window === "undefined") return;
  const uid = decodeTokenUser(window.localStorage.getItem("propai_access_token"));
  if (!uid) return; // 비로그인 → 유지(로그인 시 다시 검사)
  const owner = window.localStorage.getItem(DATA_OWNER_KEY);
  if (owner !== uid) {
    clearAllProjectData();
    try { window.localStorage.setItem(DATA_OWNER_KEY, uid); } catch { /* noop */ }
  }
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
    // 필드 provenance(manualFields)·무거운 분석 캐시(analysisCache)도 함께 영속한다.
    //   서버 왕복에서 누락되면 merge 가드(수동입력 보존)와 캐시 재사용이 무력화된다(감사 적발).
    manualFields: s.manualFields ?? {},
    analysisCache: s.analysisCache ?? {},
  };
}

/* ── WP-D: 스냅샷 무결성 가드 ──
   프로젝트 레코드(useProjectStore)의 주소와 분석 스냅샷의 siteAnalysis.address가
   핵심 토큰(시군구·번지)에서 명백히 불일치하면 오염으로 판정해 서버 푸시를 보류한다.
   비교 불능(주소 부재)은 위반 아님 — 정상 동기화를 과차단하지 않는다. */

/** 프로젝트 레코드의 주소 — 무결성 비교 기준. 미설정/빈 문자열이면 null. */
function projectRecordAddress(projectId: string): string | null {
  try {
    const p = useProjectStore.getState().projects.find((x) => x.id === projectId);
    const addr = p?.address;
    return typeof addr === "string" && addr.trim() ? addr : null;
  } catch {
    return null;
  }
}

/** 무결성 위반 시 사유 문자열, 정상이면 null. */
function snapshotIntegrityViolation(
  projectId: string,
  snap: Record<string, unknown>,
): string | null {
  const recordAddress = projectRecordAddress(projectId);
  const snapAddress = (
    snap.siteAnalysis as { address?: unknown } | null | undefined
  )?.address;
  if (
    recordAddress &&
    typeof snapAddress === "string" &&
    addressTokenMismatch(recordAddress, snapAddress)
  ) {
    return `프로젝트 주소("${recordAddress}") ↔ 분석 주소("${snapAddress}") 핵심 토큰 불일치`;
  }
  return null;
}

// 최초 서버 pull 완료 전에는 push 금지(빈 로컬상태로 서버를 덮어쓰는 사고 방지)
let pulled = false;

export async function syncDown(): Promise<void> {
  if (!isLoggedIn()) return;
  // ★먼저 소유자 검사: 로컬에 다른 계정 데이터가 남아있으면 비운 뒤 서버 데이터를 받는다.
  ensureDataOwner();
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
      const remote = data.contextStore as Record<string, unknown>;
      const localPid = useProjectContextStore.getState().projectId;
      const remotePid =
        typeof remote.projectId === "string" ? remote.projectId : null;
      if (localPid && remotePid && localPid !== remotePid) {
        // WP-D 머지 가드: 로컬 활성 프로젝트와 서버 blob의 프로젝트가 다르면
        // live 필드(siteAnalysis 등)를 덮지 않는다(다른 프로젝트 분석이 현재
        // 화면을 오염시키는 사고 방지). snapshots만 프로젝트별 updatedAt 최신
        // 우선으로 병합한다(applyRemoteSnapshot과 동일 규칙 — 동률은 서버 우선).
        const localSnaps = (useProjectContextStore.getState().snapshots ??
          {}) as Record<string, { updatedAt?: unknown } | undefined>;
        const remoteSnaps = (
          remote.snapshots && typeof remote.snapshots === "object"
            ? remote.snapshots
            : {}
        ) as Record<string, { updatedAt?: unknown } | undefined>;
        const merged: Record<string, unknown> = { ...localSnaps };
        for (const [pid, snap] of Object.entries(remoteSnaps)) {
          if (!snap || typeof snap !== "object") continue;
          const local = localSnaps[pid];
          if (!local || _maxTs(local.updatedAt) <= _maxTs(snap.updatedAt)) {
            merged[pid] = snap;
          }
        }
        useProjectContextStore.setState({ snapshots: merged } as never);
      } else {
        const patch: Record<string, unknown> = {};
        for (const k of CTX_KEYS) {
          if (k in remote) patch[k] = remote[k];
        }
        useProjectContextStore.setState(patch as never);
      }
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
  // WP-D 무결성 가드: 오염 의심 상태는 스케줄 자체를 보류한다.
  // 이후 정상 변경(store 갱신)이 오면 다시 스케줄되므로 영구 차단이 아니다.
  const violation = snapshotIntegrityViolation(pid, currentSnapshot());
  if (violation) {
    console.warn(`[projectSync] 스냅샷 푸시 보류(SSOT 오염 의심): ${violation}`);
    return;
  }
  if (snapTimer) clearTimeout(snapTimer);
  snapTimer = setTimeout(() => { void pushSnapshot(); }, 1500);
}

export async function pushSnapshot(): Promise<void> {
  if (!isLoggedIn()) return;
  const pid = useProjectContextStore.getState().projectId;
  if (!_isUuid(pid)) return;
  const snap = currentSnapshot();
  // WP-D 무결성 가드: 푸시 직전 최종 검증(디바운스 사이 상태 변화 대비) —
  // 오염 스냅샷이 서버에 고착되는 마지막 길목을 차단한다.
  const violation = snapshotIntegrityViolation(pid, snap);
  if (violation) {
    console.warn(`[projectSync] 스냅샷 푸시 보류(SSOT 오염 의심): ${violation}`);
    return;
  }
  try {
    await apiClient.put(`/projects/${pid}`, {
      body: { analysis_snapshot: snap },
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

  // WP-D: 적용 직전 무결성 검증 — 서버에 이미 고착된 오염 스냅샷(프로젝트 레코드
  // 주소와 토큰 불일치)은 siteAnalysis·파생 designData를 정화한 뒤 적용한다.
  const violation = snapshotIntegrityViolation(
    projectId,
    snap as Record<string, unknown>,
  );
  const effective = violation
    ? purifyPollutedSnapshot(snap as Record<string, unknown>)
    : (snap as Record<string, unknown>);
  if (violation) {
    console.warn(`[projectSync] 원격 스냅샷 정화 후 적용(SSOT 오염 의심): ${violation}`);
  }

  const backendTs = _maxTs(effective.updatedAt);
  const localTs = _maxTs(ctx.updatedAt);
  if (localTs > backendTs) return; // 로컬이 더 최신 → 보존

  // ★H2 병합 가드: 로컬 siteAnalysis가 다필지(parcels[])를 이미 보유하는데, 들어오는
  //   원격 스냅샷의 siteAnalysis가 필지 배열이 더 빈약(없음/대표 1필지)하면 — 보강(enrichParcels)
  //   완료 전 시점에 푸시된 '대표 단일필지' 스냅샷이 timestamp만 같거나 살짝 높아 전체 필지를
  //   덮어쓰는 타이밍 사고가 생긴다. 통합 필지를 보존하기 위해 siteAnalysis만 로컬값을 유지한다
  //   (그 외 모듈은 원격 우선 규칙 그대로). 무목업: 로컬이 빈약하면 원격을 그대로 채택.
  const localSA = ctx.siteAnalysis as { parcels?: unknown[] } | null;
  const remoteSA = (effective.siteAnalysis ?? null) as { parcels?: unknown[] } | null;
  const localParcelN = Array.isArray(localSA?.parcels) ? localSA!.parcels!.length : 0;
  const remoteParcelN = Array.isArray(remoteSA?.parcels) ? remoteSA!.parcels!.length : 0;
  // ★보존 조건은 '원격이 대표 단일/빈 아티팩트(<=1)'일 때로 좁힌다. 정당한 교차기기 필지
  //   감소(예: 33→20 실편집, 원격 newer)는 remoteParcelN>1 이라 보존하지 않고 원격을 채택해
  //   lost-update(원격 최신 무시)를 피한다 — 보강 전 '대표 1필지' 덮어쓰기 사고만 막는다.
  const preserveLocalSiteAnalysis = localParcelN > 1 && remoteParcelN <= 1;
  if (preserveLocalSiteAnalysis) {
    console.warn(
      `[projectSync] 원격 스냅샷이 대표 단일/빈 필지(${remoteParcelN}) — siteAnalysis는 로컬 통합 필지(${localParcelN}) 보존`,
    );
  }

  useProjectContextStore.setState({
    siteAnalysis: (preserveLocalSiteAnalysis
      ? ctx.siteAnalysis
      : (effective.siteAnalysis ?? null)) as never,
    designData: (effective.designData ?? null) as never,
    feasibilityData: (effective.feasibilityData ?? null) as never,
    costData: (effective.costData ?? null) as never,
    esgData: (effective.esgData ?? null) as never,
    complianceData: (effective.complianceData ?? null) as never,
    completedStages: (effective.completedStages ?? []) as never,
    currentStage: (effective.currentStage ?? null) as never,
    analysisResults: (effective.analysisResults ?? []) as never,
    // ★MEDIUM fix: siteAnalysis를 로컬(통합 다필지)로 보존할 때 updatedAt.siteAnalysis 도 로컬값을
    //   유지한다. 그렇지 않고 원격(1필지 시대) updatedAt 을 통째로 덮으면, 보존한 다필지 면적과
    //   원격에서 채택한 feasibility/design/cost(1필지 기준 매출·공사비)가 동시 표시되는데
    //   isStale 이 둘의 updatedAt 을 같은 원격값으로 보아 stale 을 못 잡아 '조용한 불일치'가 된다.
    //   siteAnalysis 타임스탬프를 로컬(=다필지 분석 시점, 더 최신)로 두면 isStale("feasibility"/
    //   "design"/"cost")=true → 기존 자동재계산 CTA 가 떠 파생값을 통합 기준으로 치유한다.
    updatedAt: (preserveLocalSiteAnalysis
      ? {
          ...(effective.updatedAt ?? {}),
          siteAnalysis:
            ((ctx.updatedAt as Record<string, number> | undefined)?.siteAnalysis) ?? Date.now(),
        }
      : (effective.updatedAt ?? {})) as never,
    // provenance·캐시 복원(currentSnapshot과 대칭) — 구 스냅샷(필드 부재)은 ?? {} 폴백.
    manualFields: (effective.manualFields ?? {}) as never,
    analysisCache: (effective.analysisCache ?? {}) as never,
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
