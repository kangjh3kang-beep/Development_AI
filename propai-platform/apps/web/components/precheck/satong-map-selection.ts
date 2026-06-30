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
    })),
    dataSource: "satong-map-shell",
    fetchedAt: new Date().toISOString(),
  };
}
