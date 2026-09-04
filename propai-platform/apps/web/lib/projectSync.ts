/**
 * 프로젝트/분석 서버 동기화 (기기 무관 영속).
 *
 * 프론트 localStorage(zustand) 상태를 로그인 사용자 계정(서버 user_project_store)에
 * 미러링한다. 로그인 시 서버→로컬(syncDown), 변경 시 로컬→서버(debounced syncUp).
 * 비로그인/오프라인이면 localStorage만 사용(graceful).
 */

import { apiClient } from "@/lib/api-client";
import { AUDIT_JOB_STORAGE_KEY } from "@/components/design-audit/DesignAuditWorkspace";
import { MARKET_REPORT_JOB_STORAGE_KEY } from "@/lib/market-report-job";
import { useProjectStore } from "@/store/useProjectStore";
import {
  useProjectContextStore,
  addressTokenMismatch,
  addressRegionMismatch,
  purifyPollutedSnapshot,
  type SiteAnalysisData,
} from "@/store/useProjectContextStore";
import { healPhantomAreaAggregates } from "@/lib/site-analysis-invariants";
import { effectiveLandAreaSqm } from "@/lib/site-area";
import { VERIFY_CACHE_PREFIX } from "@/lib/verification-cache-key";
import { looksLikeAddress } from "@/lib/selection-integrity";
import { useLandScheduleStore } from "@/store/useLandScheduleStore";
import { useDevelopmentPlanStore } from "@/store/useDevelopmentPlanStore";
import {
  defaultEnabledLayerIds,
  defaultSatongMapControls,
  useSatongMapPrefs,
} from "@/store/useSatongMapPrefsStore";
import { usePaidRenderStore } from "@/store/usePaidRenderStore";
import { useRegistryAnalysisStore } from "@/store/useRegistryAnalysisStore";
import { currentUserId, decodeTokenUser } from "@/lib/account-scope";
import { withWritesSuspended } from "@/lib/account-scoped-storage";
import {
  SATONG_DOMINANT_CONSTRAINT_KEY,
  SATONG_MAP_SELECTION_KEY,
  SATONG_PARCEL_SLOPE_KEY,
  SATONG_SITE_LAYOUT_KEY,
} from "@/components/precheck/satong-map-selection";
import { SATONG_MASS_SEED_KEY } from "@/lib/satong-mass-seed";

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
  // ★레거시 전용 — 지금 쓰는 키는 `propai_pipeline_history__<userId>`(계정별 격리)이고
  //   그건 **의도적으로 지우지 않는다**(ProjectPipelinePanel: 키가 격리돼 있어 와이프 없이도
  //   본인 이력이 보존되고 삭제는 본인만 영향). 이 항목은 격리 이전의 **공유키 잔재**만 걷는다.
  //   ★접두로 바꾸지 마라 — 그 순간 계정별 이력까지 지워져 그들이 고친 결함이 되살아난다.
  "propai_pipeline_history",
  "propai_precheck_handoff",  // PreCheck 분석결과 전달(localStorage일 수도)
];
// 주소+컨텍스트 해시로 만들어지는 동적 캐시 키(개수 가변) — 접두사 패턴으로 일괄 제거.
const PROJECT_PERSIST_PREFIXES = [
  "propai_panel_",        // 전문가 패널 분석결과(9유형)
  "propai_scenario_",     // 개발 시나리오 시뮬레이션
  // ★정본 상수를 쓴다 — 종전엔 실재하지 않는 접두를 손으로 적어 뒀는데 실제 키는
  //   `propai_verify_` 여서 이 스윕이 **한 번도 매치된 적이 없었다**(계정 전환 시 이전 계정의
  //   검증 캐시 잔존). 만드는 쪽과 지우는 쪽이 같은 상수를 본다.
  VERIFY_CACHE_PREFIX,
];

// ★`currentUserId`/`decodeTokenUser` 는 `lib/account-scope.ts` 로 옮겼다 — 유료 산출물
//   스토어가 계정별 키를 만들 때 이 함수를 쓰는데, 여기 두면 스토어→projectSync→스토어
//   **순환 임포트**가 된다. 기존 소비처를 위해 이름은 그대로 재수출한다.
export { currentUserId, decodeTokenUser };

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
  // ★유료 산출물(렌더 3,000원/건 · 등기 권리분석 1,200원/필지)은 **키를 지우지 않는다** —
  //   지우면 사용자가 이미 낸 돈이 사라진다. 계정별 키(`<base>__<uid>`)로 갈라 두고
  //   여기서는 **메모리 상태만** 비운다.
  //
  // ★★**쓰기 정지 창 안에서** 비운다 — 이것이 계약이다.
  //   `#839` 는 여기서 그냥 `setState({byProject:{}})` 를 부르고 곧바로 `rehydrate()` 가
  //   *"대기 쓰기를 덮어쓴다"* 고 적었다. **그 주장이 거짓이었다**(적대 리뷰가 실행 재현):
  //   zustand `hydrate()` 는 **버전 마이그레이션 때만** `setItem` 을 부른다. 그래서 빈 값이
  //   그대로 flush 돼 **첫 로그아웃에 유료 산출물이 영구 소실**됐다. 세 로그아웃 경로가 모두
  //   `clearOnLogout()` 을 **토큰 제거보다 먼저** 부르므로 교차계정 가드도 통과했다.
  //   ★그래서 라이브러리 내부 동작에 기대지 않는다 — **쓰기를 아예 못 하게** 만든다.
  //
  // ★복원은 여기서 하지 않는다. `ensureDataOwner()` → `syncAccountScopedStores()` 가
  //   **계정이 바뀐 것을 보고** 한다(로그아웃 경로에서 이전 계정 것을 되살리지 않게).
  withWritesSuspended(() => {
    // ★스토어를 배열로 묶어 돌리지 않는다 — 유니온 타입이 되어 `setState` 시그니처가
    //   서로 호환되지 않는다(tsc 가 잡았다). 각각 명시한다.
    try { usePaidRenderStore.setState({ byProject: {} } as never); } catch { /* noop */ }
    try { useRegistryAnalysisStore.setState({ byProject: {} } as never); } catch { /* noop */ }
    try { useDevelopmentPlanStore.setState({ byProject: {} } as never); } catch { /* noop */ }
    // ★2026-09-04(#965) — 사통맵 레이어 선호. 형제 셋과 달리 `byProject` 가 아니라
    //   **기본값으로** 되돌린다(프로젝트별이 아니라 계정별 UI 선호이므로 «빈 것»이 없다).
    //   ★파생형 락이 이 자리를 짚어 줬다 — 적대 리뷰는 재수화 누락만 봤고, 메모리 와이프
    //     누락은 **락이 찾았다**(같은 결함의 나머지 절반).
    try {
      useSatongMapPrefs.setState({
        controlsByLayer: defaultSatongMapControls(),
        // ★2026-09-04 — 레이어 활성 상태도 함께 되돌린다. 안 하면 계정을 바꿔도 **이전 계정이
        //   켜 둔 레이어**가 화면에 남는다(#965 리뷰가 컨트롤 쪽에서 잡은 것과 같은 축).
        enabledLayerIds: defaultEnabledLayerIds(),
      } as never);
    } catch { /* noop */ }
  });
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
  // 세션 저장소의 현장앱 토큰·핸드오프·사통맵 선택필지 미러도 정리(계정 전환 시 잔존 방지).
  //   ★레인F P0-3: 사통맵 선택(SATONG_MAP_SELECTION_KEY)이 빠져 있으면 비밀번호 변경 등
  //   router.push 소프트 이동(SPA 세션 토큰 유지) 뒤 다음 계정에서 이전 계정 선택 필지가
  //   복원될 수 있었다(계정 격리 구멍) — 정본 상수를 재사용해 하드코딩 없이 한 곳만 고치면
  //   전역이 따라오게 한다.
  try {
    for (const k of Object.keys(window.sessionStorage)) {
      if (
        k.startsWith("propai_site_token:") ||
        k === "propai_precheck_handoff" ||
        k === SATONG_MAP_SELECTION_KEY ||
        // ★W1 지배 제약 뷰 캐시 — 규제 정보라도 "이전 계정이 보던 필지"를 노출하면 계정 격리
        //   위반이다. 정본 상수를 재사용(하드코딩 금지 — 위 SATONG_MAP_SELECTION_KEY 선례).
        k === SATONG_DOMINANT_CONSTRAINT_KEY ||
        // ★W2 경사도 뷰 캐시 — 지형 정보라도 "이전 계정이 보던 필지"를 노출하면 계정 격리
        //   위반이다. 새 뷰 캐시 키는 만드는 즉시 이 목록에 등재한다(W1 교훈).
        k === SATONG_PARCEL_SLOPE_KEY ||
        // ★W3 배치도 뷰 캐시 — 새 뷰 캐시 키는 만드는 즉시 이 목록에 등재한다(W1·W2 교훈).
        k === SATONG_SITE_LAYOUT_KEY ||
        // ★W4 매스 시드 인계 — 뷰 캐시가 아니라 **인계 페이로드**지만 위험은 같거나 더 크다:
        //   남으면 이전 계정이 고른 배치안 층수가 다음 계정의 설계 시드로 들어간다.
        k === SATONG_MASS_SEED_KEY ||
        // ★2026-08-24 실측 누락 2건 — **진행 잡 페이로드**가 남아 이전 계정이 분석한
        //   **부지 주소**(`{jobId, startedAt, address}`)가 다음 계정 화면으로 복원될 수 있었다.
        //   W1~W4 주석이 *"새 키는 만드는 즉시 이 목록에 등재한다"* 를 **네 번** 반복했는데도
        //   또 빠졌다 — 산문이 아니라 **파생형 락**으로 잠근다
        //   (`projectSync.wipeCoverage.test.ts`).
        k === MARKET_REPORT_JOB_STORAGE_KEY ||
        k === AUDIT_JOB_STORAGE_KEY
      ) {
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
/** 마지막으로 계정 스코프 스토어를 맞춘 사용자. `null` 이면 아직 한 번도 안 맞췄다. */
let _lastScopedUid: string | null = null;

/**
 * 계정별 스토어를 **지금 로그인한 계정의 키**로 다시 하이드레이션한다.
 *
 * ★왜 `propai_data_owner` 판정과 **별도**인가 (2026-08-26 · 적대 리뷰가 적발):
 *   세션 만료는 토큰만 지우고 `propai_data_owner` 는 **남긴 채** `/login` 으로 하드 내비게이션한다
 *   (`lib/api-client.ts`). 새 페이지는 **토큰 없이** 스토어를 하이드레이션하므로 어댑터의 스코프가
 *   `guest` 로 고착되고, **같은 계정으로 다시 로그인**하면 `owner === uid` 라 와이프도 복원도
 *   일어나지 않는다. 그 뒤로 그 세션에서 산 유료 산출물은 교차계정 가드에 걸려
 *   **어느 키에도 기록되지 않고 조용히 사라진다.**
 *   → 그래서 소유자 일치 여부와 **무관하게** 계정이 바뀌었으면 맞춘다.
 */
export function syncAccountScopedStores(): void {
  if (typeof window === "undefined") return;
  const uid = currentUserId();
  if (_lastScopedUid === uid) return;
  _lastScopedUid = uid;
  try { void usePaidRenderStore.persist?.rehydrate(); } catch { /* noop */ }
  try { void useRegistryAnalysisStore.persist?.rehydrate(); } catch { /* noop */ }
  try { void useDevelopmentPlanStore.persist?.rehydrate(); } catch { /* noop */ }
  // ★2026-09-04 추가(#965 적대 리뷰 Finding 1). 이 목록은 **목록형**이라 새 계정별 스토어가
  //   조용히 빠진다 — 실제로 빠졌다. 계정별 저장 어댑터는 첫 읽기에서 `scopeUid` 를 고정하고
  //   그 뒤 다른 계정의 쓰기를 **거부**하므로, 여기 없는 스토어는 소프트 계정 전환 후
  //   ①이전 계정의 값을 그대로 보여 주고 ②새 계정의 변경을 **어느 키에도 안 쓴다**(조용히).
  //   → 락을 **파생형**으로 바꿔 다섯 번째가 같은 길을 못 가게 했다
  //     (`lib/__tests__/paid-artifact-account-isolation.test.ts`).
  try { void useSatongMapPrefs.persist?.rehydrate(); } catch { /* noop */ }
}

export function ensureDataOwner(): void {
  if (typeof window === "undefined") return;
  const uid = decodeTokenUser(window.localStorage.getItem("propai_access_token"));
  if (!uid) return; // 비로그인 → 유지(로그인 시 다시 검사)
  const owner = window.localStorage.getItem(DATA_OWNER_KEY);
  if (owner !== uid) {
    clearAllProjectData();
    try { window.localStorage.setItem(DATA_OWNER_KEY, uid); } catch { /* noop */ }
  }
  // ★소유자 일치 여부와 무관하게 맞춘다 — 위 독스트링의 `guest` 고착 경로를 닫는다.
  syncAccountScopedStores();
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

/** 무결성 위반 시 사유 문자열, 정상이면 null.
    ★판별자를 인자로 받는다 — 산식을 복제하지 않고, 차단 범위에 맞는 엄격도만 갈아 끼운다.
      (판별자 선택 근거는 아래 두 소비처 주석에 각각 적었다.) */
function integrityViolation(
  projectId: string,
  snap: Record<string, unknown>,
  mismatch: (a: string | null | undefined, b: string | null | undefined) => boolean,
  scopeLabel: string,
): string | null {
  const recordAddress = projectRecordAddress(projectId);
  const snapAddress = (
    snap.siteAnalysis as { address?: unknown } | null | undefined
  )?.address;
  // ★주소 형태 검사 — 지역 비교만으로는 **주소가 아닌 값**을 못 잡는다.
  //   `addressRegionMismatch` 는 토큰 추출에 실패하면 보수적으로 '일치'를 반환하므로,
  //   엑셀 소유자 컬럼이 주소로 읽힌 값(실측: "◀ 전성결") 앞에서 침묵한다.
  //   `selection-integrity` 가 세 신호를 쓰는 이유가 이것이다 — 여기서도 ①에만 기대지 않는다.
  //   ★프로젝트 레코드 주소가 없어도 판정한다: 깨진 값은 비교 대상이 없어도 깨진 값이다.
  //   ★위양성 실측: 프로덕션 20건의 주소 값 40개 중 비주소 판정은 **1건**(그 손상 건)뿐이었다.
  if (typeof snapAddress === "string" && snapAddress.trim() && !looksLikeAddress(snapAddress)) {
    return `분석 주소("${snapAddress}")가 주소 형태가 아니다 — 데이터 손상`;
  }
  if (
    recordAddress &&
    typeof snapAddress === "string" &&
    mismatch(recordAddress, snapAddress)
  ) {
    return `프로젝트 주소("${recordAddress}") ↔ 분석 주소("${snapAddress}") ${scopeLabel}`;
  }
  return null;
}

/** 스냅샷 컬럼(/projects/{id}.analysis_snapshot) 푸시용 — 차단 범위가 그 프로젝트 하나라
    번지까지 엄격한 판별자를 쓴다(기존 동작 불변). */
function snapshotIntegrityViolation(
  projectId: string,
  snap: Record<string, unknown>,
): string | null {
  return integrityViolation(projectId, snap, addressTokenMismatch, "핵심 토큰 불일치");
}

/** 스토어 blob(/store/projects) 푸시용 — ★번지가 아니라 지역 단위로만 본다.
    차단 범위가 프로젝트 목록·토지조서·전 프로젝트 스냅샷까지 통째이므로, 번지까지 엄격한
    판별자를 쓰면 "지도에서 인접 필지를 추가한다"는 정상 워크플로우가 계정 전체의 동기화를
    멈춘다(useProjectContextStore 가 addressRegionMismatch 를 둔 이유와 같은 판단).
    막으려는 것은 교차오염 — 다른 지역의 선택이 이 프로젝트에 실려 나가는 것이다. */
function storeIntegrityViolation(
  projectId: string,
  snap: Record<string, unknown>,
): string | null {
  return integrityViolation(projectId, snap, addressRegionMismatch, "지역 불일치");
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
  // ★프로젝트 레코드의 대지면적을 **같은 PUT 에 함께** 실어 보낸다.
  //
  //   왜: `projects.total_area_sqm` 은 **생성 시 1회 기록되고 그 뒤 갱신 경로가 없었다.**
  //   필지를 고쳐도 레코드는 생성 시점에 얼어붙어, 같은 부지의 면적을 화면이 두 값으로
  //   말했다(실측: 레코드 5,781 vs 스냅샷 필지합 5,881 · 프로덕션 20건 중 7건이 갈림).
  //
  //   ★산식을 서버에 복제하지 않는다 — 유효면적 판정(다필지 통합 우선·강등 처리)은
  //     `effectiveLandAreaSqm` 한 곳에만 산다. 그 값을 **이미 가진 쪽**이 보낸다.
  //   ★의미는 **대지면적**이다(생성 경로 둘 + `building_compliance_service._get_site_area`
  //     독스트링이 일치). 추측이 아니라 소비처로 확인했다.
  //   ★값이 없으면 **키를 만들지 않는다** — 미확보를 0/null 로 덮어써 레코드를 지우지 않는다.
  const landAreaSqm = effectiveLandAreaSqm(
    useProjectContextStore.getState().siteAnalysis as never,
  );
  const areaPatch =
    typeof landAreaSqm === "number" && Number.isFinite(landAreaSqm) && landAreaSqm > 0
      ? { total_area_sqm: landAreaSqm }
      : {};
  try {
    await apiClient.put(`/projects/${pid}`, {
      body: { analysis_snapshot: snap, ...areaPatch },
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
    // ★자가치유(2026-08-23): 이 경로는 store 액션(updateSiteAnalysis)을 **우회해**
    //   setState 로 직접 쓰므로, 거기 건 불변식이 여기엔 걸리지 않는다. 서버에 이미
    //   고착된 오염본(필지 0건인데 면적 집계만 생존)이 그대로 들어오지 않게 같은
    //   헬퍼를 여기서도 태운다 — 진입점이 둘이면 방어도 둘이어야 한다.
    siteAnalysis: healPhantomAreaAggregates(
      (preserveLocalSiteAnalysis
        ? ctx.siteAnalysis
        : (effective.siteAnalysis ?? null)) as Partial<SiteAnalysisData> | null,
    ) as never,
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
  // ★WP-D 무결성 가드 — 서버 쓰기 경로는 둘인데 가드는 하나에만 걸려 있었다.
  //   ProjectSyncProvider 의 한 구독 콜백이 scheduleSyncUp 과 scheduleSnapshotSync 를 함께
  //   부른다. 스냅샷 경로만 막으면, 같은 오염 siteAnalysis 가 1.5초 뒤 이 경로로
  //   /store/projects 에 실려 나가고(CTX_KEYS 에 siteAnalysis 포함),
  //   syncDown 이 localPid === remotePid 분기에서 그대로 로컬에 되돌린다.
  //   ★키를 빼는 부분 푸시가 아니라 전체 보류인 이유: PUT /store/projects 는 blob 을 통째로
  //     치환한다(routers/user_store.py — data = EXCLUDED.data). 키를 빼면 서버에 남아 있던
  //     정상본까지 지워져 자가치유의 출처가 사라진다. 보류는 마지막 정상본을 남긴다.
  //   영구 차단이 아니다 — 정화·재분석으로 주소가 맞으면 다음 변경에서 다시 푸시된다.
  const pid = useProjectContextStore.getState().projectId;
  const violation = pid ? storeIntegrityViolation(pid, currentSnapshot()) : null;
  if (violation) {
    console.warn(`[projectSync] 스토어 푸시 보류(SSOT 오염 의심): ${violation}`);
    return;
  }
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
