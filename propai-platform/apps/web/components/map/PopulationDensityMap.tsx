"use client";

/**
 * P4-B 인구밀도 코로플레스 지도 — SGIS 행정동 경계+인구→밀도(명/㎢)를 카카오 폴리곤으로 색칠.
 *
 * 백엔드 POST /market/population-density 가 WGS84 경계 GeoJSON + 동별 인구·면적·밀도를 반환한다
 * (좌표계 UTM-K→WGS84 재투영은 백엔드 처리). 여기선 동 폴리곤을 밀도 5단계 색으로 채우고
 * 범례(명/㎢)+팝업(동명·인구·밀도)을 표시한다. 무자료 동=회색(가짜밀도 금지). 풀스크린=네이티브 API.
 */

import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { loadKakaoMap, geoJsonToKakaoRings } from "@/lib/kakao-map";
import { KakaoMapControls } from "@/components/map/KakaoMapControls";
import { useMapFullscreen } from "@/hooks/useMapFullscreen";

/* eslint-disable @typescript-eslint/no-explicit-any */

type DensityFeature = {
  adm_cd: string;
  name: string;
  geometry: any;
  population: number | null;
  area_km2: number | null;
  density: number | null;
};
type DensityResp = {
  data_source: string;
  features: DensityFeature[];
  legend: { min: number; max: number };
  year?: string;
  reason?: string;
  note?: string;
};

// 밀도 5단계 코로플레스(연청→진적). 무자료=회색(가짜 금지).
const RAMP = ["#dbeafe", "#93c5fd", "#fbbf24", "#fb7185", "#dc2626"];
function densityColor(d: number | null | undefined, min: number, max: number): string {
  if (!d || d <= 0) return "#94a3b8";
  if (max <= min) return RAMP[2];
  const t = (d - min) / (max - min);
  return RAMP[Math.min(RAMP.length - 1, Math.max(0, Math.floor(t * RAMP.length)))];
}

export function PopulationDensityMap({ address, bcode }: { address?: string; bcode?: string }) {
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const polysRef = useRef<any[]>([]);
  const infoRef = useRef<any>(null);
  const fs = useMapFullscreen(mapRef);
  const [data, setData] = useState<DensityResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [mapReady, setMapReady] = useState(false);

  // 데이터 조회(주소/bcode 변경 시).
  useEffect(() => {
    if (!address && !bcode) return;
    let alive = true;
    setLoading(true);
    apiClient
      .post<DensityResp>("/market/population-density", { body: { address, bcode }, useMock: false, timeoutMs: 90000 })
      .then((r) => { if (alive) setData(r); })
      .catch(() => { if (alive) setData({ data_source: "unavailable", features: [], legend: { min: 0, max: 0 }, reason: "조회 실패" }); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [address, bcode]);

  // 지도 렌더(폴리곤 코로플레스).
  useEffect(() => {
    if (!data?.features?.length) return;
    let alive = true;
    void loadKakaoMap().then(() => {
      if (!alive || !mapEl.current) return;
      const kakao = window.kakao;
      if (!mapRef.current) {
        mapRef.current = new kakao.maps.Map(mapEl.current, {
          center: new kakao.maps.LatLng(37.5665, 126.978), level: 6,
        });
        setMapReady(true);
      }
      const map = mapRef.current;
      polysRef.current.forEach((p) => { try { p.setMap(null); } catch { /* noop */ } });
      polysRef.current = [];
      const { min, max } = data.legend || { min: 0, max: 0 };
      const bounds = new kakao.maps.LatLngBounds();
      data.features.forEach((f) => {
        if (!f.geometry) return;
        const color = densityColor(f.density, min, max);
        const html = `<div style="padding:6px 10px;font-size:12px;min-width:150px;">
            <b>${f.name}</b><br/>
            인구 <b>${(f.population ?? 0).toLocaleString()}명</b> · ${f.area_km2 ?? "-"}㎢<br/>
            밀도 <b style="color:${color === "#94a3b8" ? "#64748b" : "#dc2626"}">${f.density ? `${f.density.toLocaleString()}명/㎢` : "무자료"}</b>
          </div>`;
        geoJsonToKakaoRings(kakao, f.geometry).forEach((path: any[]) => {
          const poly = new kakao.maps.Polygon({
            path, strokeWeight: 1.5, strokeColor: "#475569", strokeOpacity: 0.7,
            fillColor: color, fillOpacity: 0.55, zIndex: 2,
          });
          poly.setMap(map);
          polysRef.current.push(poly);
          kakao.maps.event.addListener(poly, "click", () => {
            try { infoRef.current?.close(); } catch { /* noop */ }
            const iw = new kakao.maps.InfoWindow({ content: html, removable: true, zIndex: 900 });
            // 폴리곤 첫 좌표에 정보창.
            iw.open(map, new kakao.maps.LatLng(path[0].getLat(), path[0].getLng()));
            infoRef.current = iw;
          });
          path.forEach((ll: any) => bounds.extend(ll));
        });
      });
      try { map.setBounds(bounds, 30, 30, 30, 30); } catch { /* noop */ }
    });
    return () => { alive = false; };
  }, [data]);

  useEffect(() => () => {
    polysRef.current.forEach((p) => { try { p.setMap(null); } catch { /* noop */ } });
    if (mapRef.current) { mapRef.current = null; }
  }, []);

  const unavailable = data && data.data_source === "unavailable";

  return (
    <section className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 text-base font-bold text-[var(--text-primary)]">
            <span className="text-[var(--accent-strong)]">◉</span> 인구밀도 (행정동)
          </h3>
          <p className="mt-0.5 text-[11px] text-[var(--text-hint)]">
            SGIS 인구주택총조사{data?.year ? `(${data.year})` : ""} · 행정동 경계 · 밀도=인구/면적(명/㎢)
          </p>
        </div>
        {data && !unavailable && data.legend?.max > 0 && (
          <span className="flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--text-hint)]">
            <span className="text-[var(--text-secondary)]">낮음</span>
            {RAMP.map((c) => <span key={c} className="inline-block h-2.5 w-4" style={{ backgroundColor: c }} />)}
            <span className="text-[var(--text-secondary)]">높음</span>
            <span className="ml-1">{data.legend.min.toLocaleString()} ~ {data.legend.max.toLocaleString()} 명/㎢</span>
          </span>
        )}
      </div>
      <div ref={fs.wrapperRef} className={fs.wrapperClass("relative flex flex-col")}>
        <div ref={mapEl} className={fs.mapClass("h-[360px] w-full overflow-hidden rounded-xl border border-[var(--line)]")} />
        <KakaoMapControls mapRef={mapRef} ready={mapReady} onFullscreen={fs.toggle} isFullscreen={fs.isFull} />
        {(loading || unavailable || (data && !data.features?.length)) && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-[var(--surface-soft)]/75 text-center text-xs text-[var(--text-hint)]">
            {loading
              ? "인구밀도 데이터 불러오는 중…"
              : (unavailable
                ? `인구밀도 데이터를 표시할 수 없습니다 (${data?.reason || "SGIS 미제공"}).`
                : "반경 내 행정동 인구밀도 데이터가 없습니다.")}
          </div>
        )}
      </div>
    </section>
  );
}
