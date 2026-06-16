"use client";

/**
 * 대량 배치 구역 미리보기 지도 — 분석한 구역(중심+반경 / bbox)을 Kakao 지도에 시각화.
 *
 * region_geo = { center:{lat,lon}, bbox:[minlon,minlat,maxlon,maxlat], radius_m? }
 * 중심 마커 + 반경 원(있으면) + bbox 사각형을 그려 "어느 구역을 분석했는지" 보여준다.
 * 좌표는 백엔드(VWorld 지오코딩)가 산출한 실값만 사용 — 가짜 좌표 없음.
 */

import { useEffect, useRef, useState } from "react";
import { loadKakaoMap } from "@/lib/kakao-map";

type Geo = {
  center?: { lat: number; lon: number } | null;
  bbox?: number[] | null; // [minLon, minLat, maxLon, maxLat]
  radius_m?: number | null;
};

declare global {
  interface Window { kakao: any }
}

export function BatchRegionMap({ geo, height = 280 }: { geo: Geo; height?: number }) {
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    loadKakaoMap().then(() => alive && setReady(true)).catch((e) => alive && setError(String(e?.message || e)));
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!ready || !mapEl.current || !geo?.center?.lat) return;
    const kakao = window.kakao;
    const center = new kakao.maps.LatLng(geo.center.lat, geo.center.lon);
    const map = new kakao.maps.Map(mapEl.current, { center, level: 6 });
    mapRef.current = map;

    // 중심 마커
    const marker = new kakao.maps.Marker({ position: center });
    marker.setMap(map);

    const overlays: any[] = [marker];

    // 반경 원(center 모드)
    if (geo.radius_m && geo.radius_m > 0) {
      const circle = new kakao.maps.Circle({
        center, radius: geo.radius_m, strokeWeight: 2, strokeColor: "#3b82f6",
        strokeOpacity: 0.9, strokeStyle: "dashed", fillColor: "#3b82f6", fillOpacity: 0.06,
      });
      circle.setMap(map);
      overlays.push(circle);
    }

    // bbox 사각형
    if (geo.bbox && geo.bbox.length === 4) {
      const [minLon, minLat, maxLon, maxLat] = geo.bbox;
      const rectBounds = new kakao.maps.LatLngBounds(
        new kakao.maps.LatLng(minLat, minLon),
        new kakao.maps.LatLng(maxLat, maxLon),
      );
      const rect = new kakao.maps.Rectangle({
        bounds: rectBounds, strokeWeight: 2, strokeColor: "#14b8a6",
        strokeOpacity: 0.8, strokeStyle: "solid", fillColor: "#14b8a6", fillOpacity: 0.04,
      });
      rect.setMap(map);
      overlays.push(rect);
      try { map.setBounds(rectBounds); } catch { /* noop */ }
    }

    const t = setTimeout(() => { try { map.relayout(); map.setCenter(center); } catch { /* noop */ } }, 100);
    return () => {
      clearTimeout(t);
      overlays.forEach((o) => { try { o.setMap(null); } catch { /* noop */ } });
      mapRef.current = null;
    };
  }, [ready, geo]);

  if (error) {
    return <p className="text-[11px] text-[var(--text-tertiary)]">지도를 불러오지 못했습니다({error}).</p>;
  }
  return (
    <div className="overflow-hidden rounded-xl border border-[var(--line)]">
      <div ref={mapEl} style={{ width: "100%", height }} />
    </div>
  );
}