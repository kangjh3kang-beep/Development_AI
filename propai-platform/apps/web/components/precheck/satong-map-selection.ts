"use client";

import type { SiteAnalysisData } from "@/store/useProjectContextStore";
import type { ParcelRow } from "@/lib/parcel-rows";

export const SATONG_MAP_SELECTION_KEY = "satong_map_selection";

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
  geometry?: unknown;
  source: "search" | "excel" | "map";
};

export type SatongMapSelection = {
  savedAt: string;
  parcels: SatongSelectionParcel[];
};

export function readSatongMapSelection(): SatongMapSelection | null {
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
    return {
      savedAt: typeof parsed.savedAt === "string" ? parsed.savedAt : "",
      parcels,
    };
  } catch {
    return null;
  }
}

export function writeSatongMapSelection(parcels: SatongSelectionParcel[]): void {
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
      return {
        id: parcel.pnu || `store-${index}-${parcel.address}`,
        address: (parcel.address ?? "").trim(),
        pnu: parcel.pnu ?? null,
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
    pnu: first.pnu ?? null,
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
      pnu: parcel.pnu || parcel.id,
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
