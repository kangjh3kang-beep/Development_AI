export type SatongMapLayerId =
  | "cadastre"
  | "zoning"
  | "official-price"
  | "age"
  | "transactions"
  | "presale"
  | "auction"
  | "poi"
  | "terrain"
  | "roadview";

export type VWorldBaseLayer = "Base" | "Satellite" | "Hybrid" | "gray";

export type SatongMapLayerState = {
  enabledLayerIds: SatongMapLayerId[];
  controlsByLayer: Partial<Record<SatongMapLayerId, string[]>>;
};

export type SatongMapFeature = {
  id: string;
  address: string;
  pnu?: string | null;
  lat?: number | null;
  lon?: number | null;
  areaSqm?: number | null;
  zoneType?: string | null;
  zoneType2?: string | null;
  jimok?: string | null;
  officialPricePerSqm?: number | null;
  builtYear?: number | null;
  buildingAgeYears?: number | null;
  geometry?: unknown;
  source?: "search" | "excel" | "map" | "boundary";
};

export const SATONG_RENDERABLE_LAYER_IDS = new Set<SatongMapLayerId>([
  "cadastre",
  "zoning",
  "official-price",
  "age",
  "terrain",
]);

export function isRenderableSatongMapLayer(id: string): id is SatongMapLayerId {
  return SATONG_RENDERABLE_LAYER_IDS.has(id as SatongMapLayerId);
}

export function hasSatongLayer(
  state: SatongMapLayerState | undefined,
  id: SatongMapLayerId,
): boolean {
  return !!state?.enabledLayerIds.includes(id);
}

export function hasSatongLayerControl(
  state: SatongMapLayerState | undefined,
  id: SatongMapLayerId,
  controlId: string,
): boolean {
  return !!state?.controlsByLayer[id]?.includes(controlId);
}

export function satongMapFeatureKey(feature: Pick<SatongMapFeature, "id" | "pnu" | "address">): string {
  return feature.pnu || feature.id || feature.address.trim().replace(/\s+/g, " ");
}

export function zoneColor(zone: string | null | undefined, index: number): string {
  const z = zone || "";
  if (z.includes("상업")) return "#ec4899";
  if (z.includes("주거")) return "#14b8a6";
  if (z.includes("공업")) return "#f59e0b";
  if (z.includes("녹지") || z.includes("관리") || z.includes("농림")) return "#65a30d";
  return ["#2563eb", "#7c3aed", "#0891b2", "#ea580c"][index % 4];
}

const PRICE_RAMP = ["#bae6fd", "#7dd3fc", "#38bdf8", "#fb923c", "#ef4444"];

export function priceColor(price: number | null | undefined, min: number, max: number): string {
  if (!price || price <= 0) return "#94a3b8";
  if (max <= min) return PRICE_RAMP[2];
  const normalized = (price - min) / (max - min);
  const index = Math.min(PRICE_RAMP.length - 1, Math.max(0, Math.floor(normalized * PRICE_RAMP.length)));
  return PRICE_RAMP[index];
}

const AGE_RAMP = ["#7dd3fc", "#34d399", "#facc15", "#fb923c", "#ef4444"];

export function ageColor(age: number | null | undefined): string {
  if (age == null || age < 0) return "#94a3b8";
  if (age < 10) return AGE_RAMP[0];
  if (age < 20) return AGE_RAMP[1];
  if (age < 30) return AGE_RAMP[2];
  if (age < 40) return AGE_RAMP[3];
  return AGE_RAMP[4];
}

export function priceManPyeong(perSqm: number | null | undefined): string {
  if (!perSqm || perSqm <= 0) return "-";
  return `${Math.round((perSqm * 3.305785) / 1e4).toLocaleString()}만원/평`;
}

export function resolveVWorldBaseLayer(state: SatongMapLayerState | undefined): VWorldBaseLayer {
  if (!hasSatongLayer(state, "terrain")) return "Base";
  if (hasSatongLayerControl(state, "terrain", "satellite")) return "Satellite";
  if (hasSatongLayerControl(state, "terrain", "hybrid") || hasSatongLayerControl(state, "terrain", "aerial")) {
    return "Hybrid";
  }
  if (hasSatongLayerControl(state, "terrain", "gray")) return "gray";
  return "Base";
}

export function mergeSatongMapFeatures(features: SatongMapFeature[]): SatongMapFeature[] {
  const byKey = new Map<string, SatongMapFeature>();
  features.forEach((feature) => {
    const key = satongMapFeatureKey(feature);
    const prev = byKey.get(key);
    byKey.set(key, {
      ...prev,
      ...feature,
      areaSqm: feature.areaSqm ?? prev?.areaSqm ?? null,
      zoneType: feature.zoneType ?? prev?.zoneType ?? null,
      zoneType2: feature.zoneType2 ?? prev?.zoneType2 ?? null,
      jimok: feature.jimok ?? prev?.jimok ?? null,
      officialPricePerSqm: feature.officialPricePerSqm ?? prev?.officialPricePerSqm ?? null,
      builtYear: feature.builtYear ?? prev?.builtYear ?? null,
      buildingAgeYears: feature.buildingAgeYears ?? prev?.buildingAgeYears ?? null,
      geometry: feature.geometry ?? prev?.geometry,
      lat: feature.lat ?? prev?.lat ?? null,
      lon: feature.lon ?? prev?.lon ?? null,
    });
  });
  return Array.from(byKey.values());
}
