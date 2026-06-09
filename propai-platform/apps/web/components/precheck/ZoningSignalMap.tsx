"use client";

/**
 * 조닝 시그널 지도 — 대상 필지 + 주변 기회 필지를 카카오맵에 렌더.
 *
 * 백엔드(B: /precheck/zoning-signals)가 parcel-boundaries 형식의 geojson을
 * 동봉하면 구획 폴리곤을 그리고, 없으면 시그널 필지 PNU 라벨만 표시한다.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { loadKakaoMap, geoJsonToKakaoRings } from "@/lib/kakao-map";
import { KakaoMapControls } from "@/components/map/KakaoMapControls";
import type { ZoningSignal } from "./types";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    kakao: any;
  }
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
  const polysRef = useRef<any[]>([]);
  const infoRef = useRef<any>(null);
  const [mapReady, setMapReady] = useState(false);

  // 시그널 → 필지 PNU별 최고 레벨 색상 매핑(폴리곤 강조용)
  const pnuLevel = useMemo(() => {
    const order: Record<string, number> = { low: 0, mid: 1, high: 2 };
    const m: Record<string, string> = {};
    signals.forEach((sig) => {
      (sig.parcels ?? []).forEach((p) => {
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
    void loadKakaoMap().then(() => {
      if (!alive || !mapEl.current) return;
      const kakao = window.kakao;
      if (!mapRef.current) {
        mapRef.current = new kakao.maps.Map(mapEl.current, {
          center: new kakao.maps.LatLng(37.5665, 126.978), level: 4,
        });
      }
      const map = mapRef.current;
      setMapReady(true);
      // 이전 폴리곤/정보창 정리
      polysRef.current.forEach((p) => { try { p.setMap(null); } catch { /* noop */ } });
      polysRef.current = [];
      try { infoRef.current?.close(); } catch { /* noop */ }

      const bounds = new kakao.maps.LatLngBounds();
      let drew = false;

      if (hasGeo) {
        const fc = geojson as any;
        (fc.features ?? []).forEach((feat: any) => {
          const props = feat?.properties ?? {};
          const level = props.pnu ? pnuLevel[props.pnu] : undefined;
          const color = level ? LEVEL_COLOR[level] : "#3b82f6";
          const label = props.address || props.pnu || "필지";
          const html = `<div style="padding:6px 10px;font-size:12px;"><b>${label}</b><br/>용도지역: ${props.zone_type || "-"}</div>`;
          geoJsonToKakaoRings(kakao, feat?.geometry).forEach((path) => {
            const poly = new kakao.maps.Polygon({
              path, strokeWeight: level ? 3 : 1.5, strokeColor: color, strokeOpacity: 0.9,
              fillColor: color, fillOpacity: level ? 0.4 : 0.18,
            });
            poly.setMap(map);
            polysRef.current.push(poly);
            kakao.maps.event.addListener(poly, "click", (e: any) => {
              try { infoRef.current?.close(); } catch { /* noop */ }
              const iw = new kakao.maps.InfoWindow({ position: e.latLng, content: html, removable: true });
              iw.open(map);
              infoRef.current = iw;
            });
            path.forEach((ll: any) => { bounds.extend(ll); drew = true; });
          });
        });
      }

      const applyView = () => {
        try {
          if (drew) map.setBounds(bounds, 30, 30, 30, 30);
          else if (centerHint) map.setCenter(new kakao.maps.LatLng(centerHint.lat, centerHint.lon));
          else map.setCenter(new kakao.maps.LatLng(37.5665, 126.978));
        } catch { /* noop */ }
      };
      applyView();
      setTimeout(() => { if (alive) { try { map.relayout(); } catch { /* noop */ } applyView(); } }, 60);
    });
    return () => {
      alive = false;
      try { infoRef.current?.close(); } catch { /* noop */ }
      polysRef.current.forEach((p) => { try { p.setMap(null); } catch { /* noop */ } });
      polysRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(geojson), JSON.stringify(pnuLevel), centerHint?.lat, centerHint?.lon]);

  return (
    <div className="relative">
      <div
        ref={mapEl}
        className="h-[360px] w-full overflow-hidden rounded-xl border border-[var(--line)]"
      />
      <KakaoMapControls mapRef={mapRef} ready={mapReady} />
      {!hasGeo && (
        <div className="pointer-events-none absolute inset-x-0 bottom-0 m-2 rounded-lg bg-[var(--surface-soft)]/85 px-3 py-2 text-[11px] text-[var(--text-hint)]">
          구획 데이터(geojson)가 없어 위치 개요만 표시합니다. 아래 시그널 카드의 필지 목록을 확인하세요.
        </div>
      )}
    </div>
  );
}

export default ZoningSignalMap;
