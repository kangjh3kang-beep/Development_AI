"use client";

/**
 * 조닝 시그널 지도 호환 컴포넌트.
 *
 * geojson/signals 입력 계약은 유지하고, 지도 렌더링은 SatongMultiMap 단일 엔진으로 통합한다.
 */

import { useMemo } from "react";

import { SatongMultiMap } from "@/components/map/SatongMultiMap";
import { resolveMapCenter, type SatongMapFeature, type SatongMapLayerState } from "@/lib/satong-map-layers";
import { SATONG_POPUP_YIELD } from "@/lib/satong-map-z";
import type { ZoningSignal } from "./types";

const LEVEL_COLOR: Record<string, string> = {
  high: "#10b981",
  mid: "#f59e0b",
  low: "#64748b",
};

export function ZoningSignalMap({
  geojson,
  signals,
  centerHint,
}: {
  geojson: unknown | null;
  signals: ZoningSignal[];
  centerHint?: { lat: number; lon: number } | null;
}) {
  const pnuLevel = useMemo(() => {
    const order: Record<string, number> = { low: 0, mid: 1, high: 2 };
    const byPnu: Record<string, string> = {};
    signals.forEach((signal) => {
      (signal.parcels ?? []).forEach((parcel) => {
        const previous = byPnu[parcel.pnu];
        if (!previous || order[signal.level] > order[previous]) byPnu[parcel.pnu] = signal.level;
      });
    });
    return byPnu;
  }, [signals]);

  const mapFeatures = useMemo<SatongMapFeature[]>(() => {
    if (!geojson || typeof geojson !== "object" || !Array.isArray((geojson as { features?: unknown[] }).features)) {
      return [];
    }
    return ((geojson as { features: Array<{ properties?: Record<string, unknown>; geometry?: unknown }> }).features ?? [])
      .map((feature, index) => {
        const props = feature.properties ?? {};
        const pnu = typeof props.pnu === "string" ? props.pnu : null;
        const address = typeof props.address === "string" ? props.address : pnu || `시그널 필지 ${index + 1}`;
        return {
          id: pnu || address,
          pnu,
          address,
          zoneType: typeof props.zone_type === "string" ? props.zone_type : null,
          geometry: feature.geometry,
          source: "boundary",
        };
      });
  }, [geojson]);

  const statusColors = useMemo(() => {
    const colors: Record<string, string> = {};
    mapFeatures.forEach((feature) => {
      const level = feature.pnu ? pnuLevel[feature.pnu] : undefined;
      if (level) colors[feature.address] = LEVEL_COLOR[level] || LEVEL_COLOR.low;
    });
    return colors;
  }, [mapFeatures, pnuLevel]);

  const statusLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    mapFeatures.forEach((feature) => {
      const level = feature.pnu ? pnuLevel[feature.pnu] : undefined;
      if (level) labels[feature.address] = `조닝 시그널 ${level}`;
    });
    return labels;
  }, [mapFeatures, pnuLevel]);

  const layerState = useMemo<SatongMapLayerState>(
    () => ({
      enabledLayerIds: ["cadastre", "zoning", "terrain"],
      controlsByLayer: {
        cadastre: ["parcel-boundary", "selected-parcel"],
        zoning: ["land-use"],
        terrain: ["base"],
      },
    }),
    [],
  );

  return (
    <div className="relative">
      <SatongMultiMap
        readOnly
        chrome="immersive"
        height={360}
        selectedParcels={mapFeatures}
        layerState={layerState}
        focusTarget={(() => {
          // 공용 좌표 해석 — 유한한 좌표만 focusTarget 로(NaN/null 은 이동 스킵, 서울 폴백 X).
          const c = resolveMapCenter(centerHint);
          return c ? { lat: c.lat, lon: c.lon, label: "조닝 시그널 중심" } : null;
        })()}
        featureStatusColors={statusColors}
        featureStatusLabels={statusLabels}
      />
      {mapFeatures.length === 0 && (
        <div
          /* ★상세정보팝업 양보 계약(SATONG_POPUP_YIELD) — 지도의 **형제**로 놓인 하단 리본이라
             (지도 컨테이너가 isolation:isolate 라) 팝업 위에 그려진다. z 로는 못 이기므로
             팝업이 열려 있는 동안만 물러난다. 상시 고지 문구라 물러나도 잃는 것이 없다. */
          {...{ [SATONG_POPUP_YIELD.passiveAttr]: SATONG_POPUP_YIELD.passiveValue }}
          className="pointer-events-none absolute inset-x-0 bottom-0 m-2 rounded-lg bg-[var(--surface-soft)]/85 px-3 py-2 text-[11px] text-[var(--text-hint)]"
        >
          구획 데이터(geojson)가 없어 위치 개요만 표시합니다. 아래 시그널 카드의 필지 목록을 확인하세요.
        </div>
      )}
    </div>
  );
}

export default ZoningSignalMap;
