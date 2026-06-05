"use client";

/**
 * 조닝 시그널 지도 — 대상 필지 + 주변 기회 필지를 Leaflet+OSM(무키)에 렌더.
 *
 * 백엔드(B: /precheck/zoning-signals)가 parcel-boundaries 형식의 geojson을
 * 동봉하면 구획 폴리곤을 그리고, 없으면 시그널 필지 PNU 라벨만 표시한다.
 * ParcelBoundaryMap의 leaflet 로더/토큰 패턴을 따른다.
 */

import { useEffect, useMemo, useRef } from "react";
import type { ZoningSignal } from "./types";

declare global {
  interface Window {
    L: any;
  }
}

let leafletLoading: Promise<void> | null = null;
function loadLeaflet(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.L) return Promise.resolve();
  if (leafletLoading) return leafletLoading;
  leafletLoading = new Promise((resolve, reject) => {
    if (!document.querySelector("link[data-leaflet]")) {
      const css = document.createElement("link");
      css.rel = "stylesheet";
      css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
      css.setAttribute("data-leaflet", "1");
      document.head.appendChild(css);
    }
    const s = document.createElement("script");
    s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    s.async = true;
    s.onload = () => resolve();
    s.onerror = () => reject(new Error("Leaflet 로드 실패"));
    document.head.appendChild(s);
  });
  return leafletLoading;
}

const LEVEL_COLOR: Record<string, string> = {
  high: "#10b981", // emerald-500
  mid: "#f59e0b", // amber-500
  low: "#64748b", // slate-500
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
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);

  // 시그널 → 필지 PNU별 최고 레벨 색상 매핑(폴리곤 강조용)
  const pnuLevel = useMemo(() => {
    const order: Record<string, number> = { low: 0, mid: 1, high: 2 };
    const m: Record<string, string> = {};
    signals.forEach((sig) => {
      sig.parcels.forEach((p) => {
        const prev = m[p.pnu];
        if (!prev || order[sig.level] > order[prev]) m[p.pnu] = sig.level;
      });
    });
    return m;
  }, [signals]);

  const hasGeo =
    !!geojson &&
    typeof geojson === "object" &&
    Array.isArray((geojson as any).features) &&
    (geojson as any).features.length > 0;

  useEffect(() => {
    if (!mapEl.current) return;
    let alive = true;
    void loadLeaflet().then(() => {
      if (!alive || !mapEl.current) return;
      const L = window.L;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
      const map = L.map(mapEl.current, { scrollWheelZoom: false });
      mapRef.current = map;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap",
      }).addTo(map);

      const group = L.featureGroup().addTo(map);
      let drew = false;

      if (hasGeo) {
        const fc = geojson as any;
        const layer = L.geoJSON(fc, {
          style: (feat: any) => {
            const pnu = feat?.properties?.pnu;
            const level = pnu ? pnuLevel[pnu] : undefined;
            const color = level ? LEVEL_COLOR[level] : "#3b82f6";
            return {
              color,
              weight: level ? 3 : 1.5,
              fillColor: color,
              fillOpacity: level ? 0.4 : 0.18,
            };
          },
          onEachFeature: (feat: any, lyr: any) => {
            const props = feat?.properties ?? {};
            const label = props.address || props.pnu || "필지";
            lyr.bindPopup(
              `<b>${label}</b><br/>용도지역: ${props.zone_type || "-"}`,
            );
          },
        }).addTo(group);
        if (layer.getLayers().length) drew = true;
      }

      try {
        if (drew) {
          map.fitBounds(group.getBounds().pad(0.25));
        } else if (centerHint) {
          map.setView([centerHint.lat, centerHint.lon], 16);
        } else {
          map.setView([37.5665, 126.978], 13); // 서울 기본
        }
      } catch {
        map.setView([37.5665, 126.978], 13);
      }
    });
    return () => {
      alive = false;
      if (mapRef.current) {
        mapRef.current.remove();
        mapRef.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(geojson), JSON.stringify(pnuLevel), centerHint?.lat, centerHint?.lon]);

  return (
    <div className="relative">
      <div
        ref={mapEl}
        className="h-[360px] w-full overflow-hidden rounded-xl border border-[var(--line)]"
      />
      {!hasGeo && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 m-2 rounded-lg bg-[var(--surface-soft)]/85 px-3 py-2 text-[11px] text-[var(--text-hint)]">
          구획 데이터(geojson)가 없어 위치 개요만 표시합니다. 아래 시그널 카드의 필지 목록을 확인하세요.
        </div>
      )}
    </div>
  );
}

export default ZoningSignalMap;
