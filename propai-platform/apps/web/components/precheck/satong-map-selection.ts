"use client";

import type { SiteAnalysisData } from "@/store/useProjectContextStore";
import type { ParcelRow } from "@/lib/parcel-rows";
import { addressHasJibun, normalizePnu } from "@/lib/pnu";

export const SATONG_MAP_SELECTION_KEY = "satong_map_selection";

// ── 사통맵 뷰 캐시(공용) ─────────────────────────────────────────────────────
//  W1 지배 제약 / W2 필지 경사도처럼 "서버가 준 표시값"을 세션 동안 재사용하는 캐시.
//  ★키만 다른 캐시를 복붙하지 않는다 — 저장/조회/상한/손상처리 로직이 갈리면 한쪽만 고쳐지는
//    발산이 생긴다(이 저장소의 반복 결함). read/writeSatongViewCache 하나를 두 캐시가 공유한다.
//  경계 응답(/zoning/parcel-boundaries)만 지배 제약을 준다. 선택 SSOT(필지 객체)에 넣지 않고
//  뷰 캐시로 분리하는 이유: ① stale 규제가 프로젝트 스냅샷·산출물 페이로드에 박히지 않게,
//  ② 매 응답의 새 객체 identity가 변경감지를 참으로 만들어 commit/save 루프를 돌지 않게.
//  sessionStorage에 함께 두는 이유: 소프트 내비로 셸이 재마운트되면 ref가 비는데
//  selectionBoundaryReady(geometry+연식 보유)가 true라 경계 재조회도 스킵돼 배너가 무음 소실된다.
//  ★이 모듈에 두는 이유(계정 격리): clearAllProjectData(projectSync)가 여기 상수를 import해
//    세션 미러를 일괄 와이프한다. 셸 안에 키를 숨기면 그 와이프 목록에서 빠져 계정 전환 시
//    이전 계정 필지의 규제가 잔존한다 — SATONG_MAP_SELECTION_KEY가 과거에 정확히 그렇게
//    새어나간 전례(레인F P0-3)가 있어 같은 함정을 반복하지 않는다.
export const SATONG_DOMINANT_CONSTRAINT_KEY = "satong_dominant_constraint";
/** W2 필지 경사도(DEM 온디맨드 조회 결과) 뷰 캐시 키. ★계정격리 와이프 목록에 함께 등재. */
export const SATONG_PARCEL_SLOPE_KEY = "satong_parcel_slope";
/** W3 배치도(buildable footprint + 동배치) 뷰 캐시 키. ★계정격리 와이프 목록에 함께 등재. */
export const SATONG_SITE_LAYOUT_KEY = "satong_site_layout";
/** 캐시 상한 — 뷰 캐시라 무한 성장시킬 이유가 없다(초과분은 오래된 것부터 버린다). */
const SATONG_VIEW_CACHE_MAX = 200;

/**
 * 지배 제약 캐시 키 — 저장·조회가 **같은 규칙**이어야 한다.
 *
 * satongMapFeatureKey는 `pnu || id || address`인데 id는 클라이언트 생성 합성값이라 서버 응답과
 * 절대 맞지 않는다. 저장 시엔 id 없는 shape를 넘겨 사실상 `pnu || address`였으므로, pnu 미확보
 * 필지(엑셀·지오코딩 시드, id="P-xxx")는 조회 키가 id로 잡혀 캐시 미스 → 배너 미표시가 됐다.
 * 여기서 id를 배제한 단일 규칙만 노출해 비대칭을 구조적으로 막는다.
 *
 * ★★2026-08-20 재교정 — `pnu || address` 는 **같은 동의 필지를 한 칸에 몰아넣는다.**
 *   신고 프로젝트는 77필지의 주소가 전부 같아, 한 필지의 **경사도·배치 결과가 나머지 76필지에
 *   교차 표시**된다(경사도·배치 캐시는 이 키로 **쓰고 또 읽는다** — 자기 왕복이라 오염이 곧
 *   오답이다).
 *
 *   ★그렇다고 무조건 id 로 떨어지면 **위 비대칭이 되살아난다**: 서버(경계 응답)는 id 를 모르고,
 *   지번이 붙은 주소로 조회한 필지는 `pnu: null` 로 돌아올 수 있다 — 그러면 저장은 주소 키,
 *   조회는 id 키가 되어 배너가 사라진다(실제로 기존 회귀 테스트가 이걸 잡았다).
 *
 *   그래서 **주소가 필지를 특정하는지**로 가른다 — 이 PR 전체가 쓰는 그 판정(addressHasJibun):
 *     ① 진짜 PNU 보유        → PNU (서버와 대칭)
 *     ② 주소에 지번 보유      → 주소 (서버와 대칭 — 서버도 이 주소로 조회했다)
 *     ③ 동 단위 주소뿐        → **필지별 id** (주소가 필지를 특정하지 못하므로 몰면 안 된다)
 *   ③은 애초에 서버로 보내지도 않으므로(resolvable 필터) 캐시 미스일 뿐이고,
 *   **이웃 필지의 규제를 보여주는 것보다 미스가 옳다**(무날조).
 */
export function dominantConstraintKey(
  feature: { pnu?: string | null; address?: string | null; id?: string | null },
): string {
  if (feature.pnu) return feature.pnu;
  const addr = (feature.address || "").trim().replace(/\s+/g, " ");
  if (addressHasJibun(addr)) return addr;
  return feature.id || addr;
}

/** 뷰 캐시 공용 필지 키 — 지배 제약·경사도가 **같은 규칙**을 써야 한 필지가 한 키로 모인다. */
export const parcelViewCacheKey = dominantConstraintKey;

/** 세션 뷰 캐시 읽기(공용) — 손상 캐시는 조용히 빈 맵으로 강등(표시용이라 복구 대상 아님). */
export function readSatongViewCache<T>(storageKey: string): Map<string, T | null> {
  const map = new Map<string, T | null>();
  if (typeof window === "undefined") return map;
  try {
    const raw = window.sessionStorage.getItem(storageKey);
    if (!raw) return map;
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return map;
    for (const entry of parsed) {
      if (Array.isArray(entry) && typeof entry[0] === "string") {
        map.set(entry[0], (entry[1] ?? null) as T | null);
      }
    }
  } catch {
    // 손상된 캐시는 조용히 버린다(다음 조회가 다시 채운다).
  }
  return map;
}

/** 세션 뷰 캐시 쓰기(공용) — 상한 초과분은 오래된 것부터 버린다. 실패는 무시(ref로 동작). */
export function writeSatongViewCache<T>(storageKey: string, map: Map<string, T | null>): void {
  if (typeof window === "undefined") return;
  try {
    const entries = Array.from(map.entries()).slice(-SATONG_VIEW_CACHE_MAX);
    window.sessionStorage.setItem(storageKey, JSON.stringify(entries));
  } catch {
    // 용량 초과 등은 무시 — ref 캐시만으로도 현재 세션 표시는 동작한다(정직 degrade).
  }
}

// ── 하위호환 별칭(W1 소비처 무수정) — 구현은 위 공용 함수 단일 경로.
export function readDominantConstraintCache<T>(): Map<string, T | null> {
  return readSatongViewCache<T>(SATONG_DOMINANT_CONSTRAINT_KEY);
}

export function writeDominantConstraintCache<T>(map: Map<string, T | null>): void {
  writeSatongViewCache<T>(SATONG_DOMINANT_CONSTRAINT_KEY, map);
}

// ★SPA(단일 페이지 앱) 세션 토큰 — 이 JS 모듈이 처음 로드될 때 딱 1회 생성한다.
//   router.push 소프트 내비게이션(산출물 갔다가 복귀 등) 간에는 모듈이 그대로 유지돼 값이
//   같지만, 하드 리로드(F5)·새 탭이면 모듈이 재초기화돼 새 값이 된다. sessionStorage에 저장된
//   선택이 '이번 SPA 세션에 만들어진 것'인지 판별해(같은 탭이라도) 하드 리로드 후 이전 세션
//   선택이 잔존 복원되는 것을 막는 데 쓴다(미연결 신규 진입은 빈 선택으로 시작 — T1).
const SPA_SESSION_TOKEN =
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

export type SatongSelectionParcel = {
  id: string;
  address: string;
  pnu?: string | null;
  lat?: number | null;
  lon?: number | null;
  areaSqm?: number | null;
  zoneType?: string | null;
  jimok?: string | null;
  officialPricePerSqm?: number | null;
  builtYear?: number | null;
  buildingAgeYears?: number | null;
  /** 노후도 무자료 사유(경계 age_status 역전파) — "age 조회 시도됨" 판정에 쓰여 나대지 1필지에
   *  의한 경계 재조회 루프를 끊는다(WP-M3). 런타임 전용(세션 영속 대상 아님). */
  ageStatus?: string | null;
  /** I7/WS-D — 경계 응답 서버 산정치(실효 FAR/BCR·현황 FAR). 미산정 None(무날조).
   *  ★런타임 전용(ageStatus 선례) — 프로젝트 스토어 왕복(selectionToSiteAnalysisPatch)에는
   *  싣지 않으며 재진입 시 경계 재보강이 self-heal한다. */
  effectiveFarPct?: number | null;
  effectiveBcrPct?: number | null;
  currentFarPct?: number | null;
  geometry?: unknown;
  source: "search" | "excel" | "map";
};

export type SatongMapSelection = {
  savedAt: string;
  // ★이 선택을 기록한 SPA 세션 토큰(페이지 로드 수명). 하드 리로드 후 잔존 여부 판별용.
  //   옵셔널 — 이 필드 이전에 저장된 구 payload와 호환(그 경우 sameSpaSession=false로 취급).
  spaSession?: string;
  // ★R2b(HIGH): 이 선택의 소유권 — 프로젝트에서 상속(시드)됐으면 그 projectId, 사용자가
  //   직접 편집했으면 null. spaSession과 동일하게 옵셔널(이 필드 이전 구 payload 호환 —
  //   부재 시 호출부가 안전측(사용자 소유=null)으로 취급). 소유권을 sessionStorage에도 함께
  //   영속해야, 산출물 페이지로 소프트 내비했다가 돌아오는(재마운트) 흔한 재진입 경로에서도
  //   "연결 대상 전환 시 상속 선택만 정리" 판별이 살아남는다(컴포넌트 인스턴스 ref만으로는
  //   재마운트에 소실 — PROBE_P3).
  ownerProjectId?: string | null;
  parcels: SatongSelectionParcel[];
};

// 읽기 결과 — 저장 payload에 '이번 SPA 세션에 기록됐는지'(sameSpaSession)를 덧붙인 런타임 뷰.
export type SatongMapSelectionRead = SatongMapSelection & { sameSpaSession: boolean };

export function readSatongMapSelection(): SatongMapSelectionRead | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(SATONG_MAP_SELECTION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<SatongMapSelection>;
    const parcels = Array.isArray(parsed.parcels)
      ? parsed.parcels.filter((parcel): parcel is SatongSelectionParcel =>
          !!parcel &&
          typeof parcel === "object" &&
          typeof parcel.id === "string" &&
          typeof parcel.address === "string" &&
          parcel.address.trim().length > 0,
        )
      : [];
    if (parcels.length === 0) return null;
    // ownerProjectId: string(소유 프로젝트) 또는 explicit null(사용자 소유)만 신뢰하고,
    //   그 외(부재·오염값)는 undefined로 접어 호출부가 안전측(사용자 소유)으로 취급하게 한다.
    const rawOwner = (parsed as { ownerProjectId?: unknown }).ownerProjectId;
    const ownerProjectId =
      typeof rawOwner === "string" ? rawOwner : rawOwner === null ? null : undefined;
    return {
      savedAt: typeof parsed.savedAt === "string" ? parsed.savedAt : "",
      spaSession: typeof parsed.spaSession === "string" ? parsed.spaSession : undefined,
      // 구 payload(토큰 부재)는 undefined === TOKEN → false → '이전 세션 잔존'으로 취급(정답).
      sameSpaSession: parsed.spaSession === SPA_SESSION_TOKEN,
      ownerProjectId,
      parcels,
    };
  } catch {
    return null;
  }
}

export function writeSatongMapSelection(
  parcels: SatongSelectionParcel[],
  ownerProjectId?: string | null,
): void {
  if (typeof window === "undefined") return;
  try {
    if (parcels.length === 0) {
      window.sessionStorage.removeItem(SATONG_MAP_SELECTION_KEY);
      return;
    }
    window.sessionStorage.setItem(
      SATONG_MAP_SELECTION_KEY,
      JSON.stringify({
        savedAt: new Date().toISOString(),
        spaSession: SPA_SESSION_TOKEN,
        // ★R2b: 호출부가 명시적으로 전달하지 않으면(구 호출부·향후 누락 방지 차원의 기본값)
        //   undefined로 두어 write 시점에 필드 자체를 생략한다(구 payload와 동일 형태 유지).
        ...(ownerProjectId !== undefined ? { ownerProjectId } : {}),
        parcels,
      } satisfies SatongMapSelection),
    );
  } catch {
    // sessionStorage 차단 환경에서는 프로젝트 컨텍스트만 사용한다.
  }
}

export function satongSelectionAddresses(parcels: SatongSelectionParcel[]): string[] {
  return parcels.map((parcel) => parcel.address).filter(Boolean);
}

export function satongSelectionToParcelRows(
  parcels: SatongSelectionParcel[],
): ParcelRow[] {
  return parcels
    .filter((parcel) => (parcel.areaSqm ?? 0) > 0)
    .map((parcel) => ({
      address: parcel.address,
      area_sqm: parcel.areaSqm ?? null,
      zone_type: parcel.zoneType ?? null,
      farPct: null,
      bcrPct: null,
      farLegalPct: null,
      bcrLegalPct: null,
    }));
}

/** 프로젝트 스토어(SiteAnalysisData.parcels) → precheck 선택필지. read-side 하이드레이션용.
 *  옵션B로 좌표·경계가 SSOT에 있으면 필지별 정밀 복원. 없으면 fallbackCoord(대표점, 옵션A)를
 *  첫 필지에 주입해 POI·개발계획 레이어가 최소한 대표점 기준으로라도 발동하게 한다(무날조: 없으면 null). */
export function siteAnalysisParcelsToSelection(
  parcels: Array<{
    pnu?: string | null;
    address?: string | null;
    areaSqm?: number | null;
    landCategory?: string | null;
    zoneCode?: string | null;
    lat?: number | null;
    lon?: number | null;
    geometry?: unknown;
    officialPricePerSqm?: number | null;
    builtYear?: number | null;
    buildingAgeYears?: number | null;
  }>,
  fallbackCoord?: { lat: number; lon: number } | null,
): SatongSelectionParcel[] {
  return parcels
    .filter((parcel) => (parcel.address ?? "").trim().length > 0)
    .map((parcel, index) => {
      // 필지별 좌표 우선(옵션B). 첫 필지에 한해 좌표 부재 시 대표점 폴백(옵션A).
      const lat = parcel.lat ?? (index === 0 ? fallbackCoord?.lat ?? null : null);
      const lon = parcel.lon ?? (index === 0 ? fallbackCoord?.lon ?? null : null);
      // ★영속된 **가짜 PNU** 를 읽는 순간 버린다(자가치유). 과거 selectionToSiteAnalysisPatch 가
      //   `pnu || id` 로 저장해, PNU 칸에 주소 합성문자열이 들어앉은 프로젝트가 이미 존재한다.
      //   그 값을 그대로 실어 나르면 ①지번 파생이 무동작 ②경계응답의 진짜 PNU 승격이 차단
      //   ③경계 요청에 실려 나가 보강 전체가 죽는다(lib/pnu normalizePnu 주석의 라이브 실측).
      //   ★id 도 가짜 PNU 를 쓰면 안 된다 — 같은 동의 77필지가 **전부 같은 id** 가 돼
      //   React key 충돌·필지 제거 오작동이 난다(index 기반 합성 id 는 필지별로 다르다).
      const pnu = normalizePnu(parcel.pnu);
      return {
        id: pnu || `store-${index}-${parcel.address}`,
        address: (parcel.address ?? "").trim(),
        pnu,
        lat,
        lon,
        areaSqm: parcel.areaSqm ?? null,
        zoneType: parcel.zoneCode ?? null,
        jimok: parcel.landCategory ?? null,
        officialPricePerSqm: parcel.officialPricePerSqm ?? null,
        builtYear: parcel.builtYear ?? null,
        buildingAgeYears: parcel.buildingAgeYears ?? null,
        geometry: parcel.geometry ?? null,
        source: "map" as const,
      };
    });
}

/** 프로젝트 SSOT(siteAnalysis) → precheck 선택필지.
 *  - parcels 필드가 **존재**하면(빈 배열 포함) 그것이 권위 출처: 채워져 있으면 필지별 정밀 복원,
 *    빈 배열이면 사용자가 명시적으로 비운 상태이므로 []를 반환한다(주소 폴백으로 삭제한 필지를
 *    부활시키지 않는다 — 재마운트/새로고침 부활 방지).
 *  - parcels 필드가 **부재**(undefined/null)인 레거시 단일필지 프로젝트만 대표 필드
 *    (주소·PNU·좌표·면적·용도지역)로 1필지를 구성한다(SSOT 실데이터 그대로 — 무날조, 없으면 null).
 *    주소조차 없으면 빈 배열(정직). */
export function siteAnalysisToSelection(
  siteAnalysis: {
    address?: string | null;
    pnu?: string | null;
    coordinates?: { lat: number; lon: number } | null;
    landAreaSqm?: number | null;
    repLandAreaSqm?: number | null;
    zoneCode?: string | null;
    parcels?: Parameters<typeof siteAnalysisParcelsToSelection>[0] | null;
  } | null,
): SatongSelectionParcel[] {
  if (!siteAnalysis) return [];
  const fallbackCoord = siteAnalysis.coordinates ?? null;
  if (Array.isArray(siteAnalysis.parcels)) {
    // 빈 배열 = 명시적 clear(플랫폼은 빈 parcels를 쓰는 유일한 경로가 사용자 초기화) → 부활 금지.
    return siteAnalysis.parcels.length > 0
      ? siteAnalysisParcelsToSelection(siteAnalysis.parcels, fallbackCoord)
      : [];
  }
  const address = (siteAnalysis.address ?? "").trim();
  if (!address) return [];
  return [
    {
      id: siteAnalysis.pnu || `store-rep-${address}`,
      address,
      pnu: siteAnalysis.pnu ?? null,
      lat: fallbackCoord?.lat ?? null,
      lon: fallbackCoord?.lon ?? null,
      areaSqm: siteAnalysis.repLandAreaSqm ?? siteAnalysis.landAreaSqm ?? null,
      zoneType: siteAnalysis.zoneCode ?? null,
      jimok: null,
      officialPricePerSqm: null,
      builtYear: null,
      buildingAgeYears: null,
      geometry: null,
      source: "map" as const,
    },
  ];
}

export function selectionToSiteAnalysisPatch(
  parcels: SatongSelectionParcel[],
): Partial<SiteAnalysisData> | null {
  if (parcels.length === 0) return null;

  const first = parcels[0];
  const totalArea = parcels.reduce((sum, parcel) => sum + (parcel.areaSqm ?? 0), 0);
  const effectiveArea =
    totalArea > 0 ? totalArea : first.areaSqm != null && first.areaSqm > 0 ? first.areaSqm : null;
  const zoneSet = new Set(parcels.map((parcel) => parcel.zoneType).filter(Boolean));

  return {
    address: first.address,
    pnu: normalizePnu(first.pnu),
    coordinates:
      first.lat != null && first.lon != null
        ? { lat: first.lat, lon: first.lon }
        : null,
    zoneCode: first.zoneType ?? null,
    dominantZoneCode: first.zoneType ?? null,
    zoneMixed: zoneSet.size > 1,
    landAreaSqm: effectiveArea,
    landAreaSqmTotal: effectiveArea,
    repLandAreaSqm: first.areaSqm ?? null,
    parcelCount: parcels.length,
    parcels: parcels.map((parcel) => ({
      // ★★여기가 6번 재발한 "77행이 전부 동 이름" 의 발원지였다.
      //   `parcel.id` 는 PNU 미확보 시 **주소를 정규화한 합성값**이라, PNU 칸에 주소가 들어갔다.
      //   PNU 가 아닌 것은 PNU 칸에 넣지 않는다 — 미확보는 빈 문자열(기존 소비처가 `p.pnu ||`
      //   폴백으로 이미 취급하는 '미확보' 표기와 동일). 없는 값을 지어내지 않는다(무날조).
      pnu: normalizePnu(parcel.pnu) ?? "",
      address: parcel.address,
      areaSqm: parcel.areaSqm ?? 0,
      landCategory: parcel.jimok || "미확인",
      ownerType: "미확인",
      zoneCode: parcel.zoneType ?? null,
      // 옵션B: 지도 복원용 좌표·경계·속성을 SSOT에 보존(재진입 시 필지별 정밀 앵커). 미확보는 null.
      lat: parcel.lat ?? null,
      lon: parcel.lon ?? null,
      geometry: parcel.geometry ?? null,
      officialPricePerSqm: parcel.officialPricePerSqm ?? null,
      builtYear: parcel.builtYear ?? null,
      buildingAgeYears: parcel.buildingAgeYears ?? null,
    })),
    dataSource: "satong-map-shell",
    fetchedAt: new Date().toISOString(),
  };
}
