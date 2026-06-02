"use client";

/**
 * 필지 경계(구획도) 지도 — 단필지/다필지.
 *
 * /zoning/parcel-boundaries(VWORLD 지적도 geometry + 토지특성)를 호출해
 * 필지 경계 폴리곤을 Leaflet+OSM(무키) 위에 그리고, 용도지역별 색상·면적 라벨을 표시.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window { L: any }
}

type Feature = {
  pnu: string;
  address: string;
  area_sqm: number;
  zone_type: string | null;
  zone_type_2: string | null;
  zone_limits: { max_bcr_pct?: number; max_far_pct?: number } | null;
  geometry: any;
};
type Boundaries = {
  features: Feature[];
  center: { lat: number; lon: number } | null;
  total_area_sqm: number;
  parcel_count: number;
};

let leafletLoading: Promise<void> | null = null;
function loadLeaflet(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("no window"));
  if (window.L) return Promise.resolve();
  if (leafletLoading) return leafletLoading;
  leafletLoading = new Promise((resolve, reject) => {
    if (!document.querySelector('link[data-leaflet]')) {
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

const PALETTE = ["#14b8a6", "#3b82f6", "#f59e0b", "#8b5cf6", "#ec4899", "#65a30d"];
function zoneColor(zone: string | null, i: number): string {
  const z = zone || "";
  if (z.includes("상업")) return "#ec4899";
  if (z.includes("주거")) return "#14b8a6";
  if (z.includes("공업")) return "#f59e0b";
  if (z.includes("녹지") || z.includes("관리") || z.includes("농림")) return "#65a30d";
  return PALETTE[i % PALETTE.length];
}
function pyeong(sqm: number): string {
  return sqm ? `${Math.round(sqm / 3.305785).toLocaleString()}평` : "-";
}

export function ParcelBoundaryMap({ parcels }: { parcels: string[] }) {
  const list = useMemo(() => parcels.map((s) => s.trim()).filter(Boolean), [parcels]);
  const key = list.join("||");
  const [data, setData] = useState<Boundaries | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);

  // 데이터 조회
  useEffect(() => {
    if (!list.length) { setData(null); return; }
    let alive = true;
    setLoading(true); setError("");
    apiClient
      .post<Boundaries>("/zoning/parcel-boundaries", {
        body: { parcels: list.map((a) => ({ address: a })) },
        useMock: false, timeoutMs: 90000,
      })
      .then((d) => { if (alive) setData(d); })
      .catch(() => { if (alive) setError("필지 경계를 불러오지 못했습니다."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // 지도 렌더
  useEffect(() => {
    if (!data || !data.features?.length || !mapEl.current) return;
    let alive = true;
    void loadLeaflet().then(() => {
      if (!alive || !mapEl.current) return;
      const L = window.L;
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
      const map = L.map(mapEl.current, { scrollWheelZoom: false });
      mapRef.current = map;
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19, attribution: "© OpenStreetMap",
      }).addTo(map);
      const group = L.featureGroup().addTo(map);
      data.features.forEach((f, i) => {
        if (!f.geometry) return;
        const color = zoneColor(f.zone_type, i);
        const layer = L.geoJSON(f.geometry, {
          style: { color, weight: 2, fillColor: color, fillOpacity: 0.28 },
        }).addTo(group);
        const z2 = f.zone_type_2 ? ` / ${f.zone_type_2}` : "";
        layer.bindPopup(
          `<b>${i + 1}. ${f.address || f.pnu}</b><br/>용도지역: ${f.zone_type || "-"}${z2}<br/>` +
          `면적: ${f.area_sqm?.toLocaleString()}㎡ (${pyeong(f.area_sqm)})` +
          (f.zone_limits ? `<br/>건폐율 ${f.zone_limits.max_bcr_pct ?? "-"}% · 용적률 ${f.zone_limits.max_far_pct ?? "-"}%` : ""),
        );
      });
      try { map.fitBounds(group.getBounds().pad(0.25)); }
      catch { if (data.center) map.setView([data.center.lat, data.center.lon], 16); }
    });
    return () => { alive = false; if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; } };
  }, [data]);

  if (!list.length) return null;

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-bold text-[var(--text-primary)]">
          🗺️ 필지 구획도 {data ? `(${data.parcel_count}필지 · 총 ${data.total_area_sqm?.toLocaleString()}㎡ / ${pyeong(data.total_area_sqm)})` : ""}
        </p>
        {loading && <span className="text-xs text-[var(--text-hint)]">불러오는 중…</span>}
      </div>
      {error && <p className="mb-2 text-xs text-rose-500">{error}</p>}
      <div ref={mapEl} className="h-[340px] w-full overflow-hidden rounded-xl border border-[var(--line)]" />
      {data && data.features.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {data.features.map((f, i) => (
            <span key={f.pnu + i} className="flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1 text-[11px]">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: zoneColor(f.zone_type, i) }} />
              <span className="font-semibold text-[var(--text-secondary)]">{i + 1}. {f.zone_type || "용도미상"}{f.zone_type_2 ? `·${f.zone_type_2}` : ""}</span>
              <span className="text-[var(--text-hint)]">{Math.round(f.area_sqm).toLocaleString()}㎡</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default ParcelBoundaryMap;
