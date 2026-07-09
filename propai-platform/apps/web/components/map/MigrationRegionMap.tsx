"use client";

/**
 * 권역 인구이동망 코로플레스 지도 — 대상 시군구가 속한 시도의 시군구별 '순이동'을 발산색으로 채운다.
 *
 * 백엔드 POST /market/migration-region 이 WGS84 시군구 경계 GeoJSON + 시군구별 순이동(KOSIS)을
 * 반환한다(좌표계 UTM-K→WGS84 재투영은 백엔드 처리). 여기선 순이동을 발산(diverging) 색으로 칠한다:
 *   전출초과(순유출·음수)=적색 계열 / 전입초과(순유입·양수)=청색 계열 / 0=중립 / 무자료=회색.
 * 대상 시군구는 굵은 테두리로 강조. 범례(순유출↔순유입)+팝업(시군구명·순이동·전입/전출) 표시.
 * 무자료·무키는 회색/미표시(가짜 순이동 금지). 인구밀도 지도(PopulationDensityMap)와 동일 스택 재사용.
 */

import { useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { loadKakaoMap, geoJsonToKakaoRings } from "@/lib/kakao-map";
import { KakaoMapControls } from "@/components/map/KakaoMapControls";
import { useMapFullscreen } from "@/hooks/useMapFullscreen";

type MigrationFeature = {
  adm_cd: string;
  name: string;
  geometry: any;
  net_migration: number | null;
  total_inflow: number | null;
  total_outflow: number | null;
  is_target: boolean;
};
type MigrationRegionResp = {
  data_source: string;
  features: MigrationFeature[];
  legend: { min_net: number; max_net: number; max_abs: number };
  year?: string;
  sido?: string;
  matched?: number;
  reason?: string;
  note?: string;
};

// 순이동 발산 램프(약→강 3단계). 순유출=적, 순유입=청, 중립=연회, 무자료=회.
const OUT_RAMP = ["#fecaca", "#f87171", "#dc2626"]; // 전출초과(순유출)
const IN_RAMP = ["#bfdbfe", "#60a5fa", "#2563eb"]; // 전입초과(순유입)
const NEUTRAL = "#e2e8f0"; // 순이동 0(균형)
const NODATA = "#94a3b8"; // 무자료
function netColor(net: number | null | undefined, maxAbs: number): string {
  if (net === null || net === undefined) return NODATA;
  if (maxAbs <= 0 || net === 0) return NEUTRAL;
  const t = Math.min(1, Math.abs(net) / maxAbs); // 0~1
  const ramp = net < 0 ? OUT_RAMP : IN_RAMP;
  const idx = Math.min(ramp.length - 1, Math.max(0, Math.floor(t * ramp.length)));
  return ramp[idx];
}

export function MigrationRegionMap({ address, bcode }: { address?: string; bcode?: string }) {
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const polysRef = useRef<any[]>([]);
  const infoRef = useRef<any>(null);
  // 훅 반환 객체를 통째로 들면 wrapperRef가 섞여 렌더 중 ref 접근으로 추론된다.
  // 구조 분해로 ref와 렌더-안전 값을 분리(PopulationDensityMap/SatongMultiMap과 동일 패턴).
  const {
    isFull: isMapFullscreen,
    toggle: toggleMapFullscreen,
    wrapperRef: fullscreenWrapperRef,
    wrapperClass: fullscreenWrapperClass,
    mapClass: fullscreenMapClass,
  } = useMapFullscreen(mapRef);
  const [data, setData] = useState<MigrationRegionResp | null>(null);
  const [loading, setLoading] = useState(false);
  const [mapReady, setMapReady] = useState(false);

  // 데이터 조회(주소/bcode 변경 시).
  /* eslint-disable react-hooks/set-state-in-effect -- 외부 API fetch 동안 로딩 표시(PopulationDensityMap과 동일 패턴). */
  useEffect(() => {
    if (!address && !bcode) return;
    let alive = true;
    setLoading(true);
    apiClient
      .post<MigrationRegionResp>("/market/migration-region", { body: { address, bcode }, useMock: false, timeoutMs: 90000 })
      .then((r) => { if (alive) setData(r); })
      .catch(() => { if (alive) setData({ data_source: "unavailable", features: [], legend: { min_net: 0, max_net: 0, max_abs: 0 }, reason: "조회 실패" }); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [address, bcode]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // 지도 렌더(순이동 발산 코로플레스).
  useEffect(() => {
    if (!data?.features?.length) return;
    let alive = true;
    void loadKakaoMap().then(() => {
      if (!alive || !mapEl.current) return;
      const kakao = window.kakao;
      if (!mapRef.current) {
        mapRef.current = new kakao.maps.Map(mapEl.current, {
          center: new kakao.maps.LatLng(37.5665, 126.978), level: 8,
        });
        setMapReady(true);
      }
      const map = mapRef.current;
      polysRef.current.forEach((p) => { try { p.setMap(null); } catch { /* noop */ } });
      polysRef.current = [];
      const maxAbs = data.legend?.max_abs ?? 0;
      const bounds = new kakao.maps.LatLngBounds();
      data.features.forEach((f) => {
        if (!f.geometry) return;
        const net = f.net_migration;
        const color = netColor(net, maxAbs);
        const netTxt = net === null || net === undefined
          ? "무자료"
          : `${net > 0 ? "+" : ""}${net.toLocaleString()}명 (${net < 0 ? "순유출" : net > 0 ? "순유입" : "균형"})`;
        const netCol = net === null || net === undefined ? "#64748b" : net < 0 ? "#dc2626" : net > 0 ? "#2563eb" : "#475569";
        const html = `<div style="padding:6px 10px;font-size:12px;min-width:160px;">
            <b>${f.name}${f.is_target ? " ★대상" : ""}</b><br/>
            순이동 <b style="color:${netCol}">${netTxt}</b><br/>
            전입 ${(f.total_inflow ?? 0).toLocaleString()} · 전출 ${(f.total_outflow ?? 0).toLocaleString()}
          </div>`;
        geoJsonToKakaoRings(kakao, f.geometry).forEach((path: any[]) => {
          const poly = new kakao.maps.Polygon({
            path,
            // 대상 시군구는 굵은 강조 테두리, 나머지는 얇은 회색.
            strokeWeight: f.is_target ? 3.5 : 1.2,
            strokeColor: f.is_target ? "#0f172a" : "#64748b",
            strokeOpacity: f.is_target ? 1 : 0.6,
            fillColor: color, fillOpacity: 0.6, zIndex: f.is_target ? 5 : 2,
          });
          poly.setMap(map);
          polysRef.current.push(poly);
          kakao.maps.event.addListener(poly, "click", () => {
            try { infoRef.current?.close(); } catch { /* noop */ }
            const iw = new kakao.maps.InfoWindow({ content: html, removable: true, zIndex: 900 });
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
            <span className="text-[var(--accent-strong)]">◉</span> 권역 순이동 (시군구)
          </h3>
          <p className="mt-0.5 text-[11px] text-[var(--text-hint)]">
            KOSIS 시군구별 이동자수{data?.year ? `(${data.year})` : ""} · 시도 권역 · 순이동=전입−전출(발산색)
          </p>
        </div>
        {data && !unavailable && (data.features?.length ?? 0) > 0 && (
          <span className="flex flex-wrap items-center gap-1.5 text-[10px] text-[var(--text-hint)]">
            <span className="text-[var(--text-secondary)]">순유출</span>
            {[...OUT_RAMP].reverse().map((c) => <span key={c} className="inline-block h-2.5 w-4" style={{ backgroundColor: c }} />)}
            <span className="inline-block h-2.5 w-4" style={{ backgroundColor: NEUTRAL }} />
            {IN_RAMP.map((c) => <span key={c} className="inline-block h-2.5 w-4" style={{ backgroundColor: c }} />)}
            <span className="text-[var(--text-secondary)]">순유입</span>
            {data.legend?.max_abs > 0 && (
              <span className="ml-1">±{data.legend.max_abs.toLocaleString()}명</span>
            )}
          </span>
        )}
      </div>
      <div ref={fullscreenWrapperRef} className={fullscreenWrapperClass("relative flex flex-col")}>
        <div ref={mapEl} className={fullscreenMapClass("h-[360px] w-full overflow-hidden rounded-xl border border-[var(--line)]")} />
        <KakaoMapControls mapRef={mapRef} ready={mapReady} onFullscreen={toggleMapFullscreen} isFullscreen={isMapFullscreen} />
        {(loading || unavailable || (data && !data.features?.length)) && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-[var(--surface-soft)]/75 text-center text-xs text-[var(--text-hint)]">
            {loading
              ? "권역 순이동 데이터 불러오는 중…"
              : (unavailable
                ? `권역 순이동 지도를 표시할 수 없습니다 (${data?.reason || "KOSIS/SGIS 미제공"}).`
                : "권역 내 시군구 순이동 데이터가 없습니다.")}
          </div>
        )}
      </div>
    </section>
  );
}
