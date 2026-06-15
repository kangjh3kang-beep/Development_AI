"use client";

/**
 * 필지 경계(구획도) 지도 — 단필지/다필지.
 *
 * /zoning/parcel-boundaries(VWORLD 지적도 geometry + 토지특성)를 호출해
 * 필지 경계 폴리곤을 카카오맵 위에 그리고, 용도지역별 색상·면적 라벨을 표시.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";
import { normalizeZoning } from "@/lib/kr-building-regulations";
import { loadKakaoMap, geoJsonToKakaoRings } from "@/lib/kakao-map";
import { KakaoMapControls } from "@/components/map/KakaoMapControls";
import { useMapFullscreen } from "@/hooks/useMapFullscreen";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window { kakao: any }
}

type Feature = {
  pnu: string;
  address: string;
  area_sqm: number;
  area_source?: string | null;
  area_confidence?: "high" | "mid" | "low" | "none" | null;
  area_note?: string | null;
  area_ledger_sqm?: number | null;   // 토지대장(공부상) 면적
  area_cadastral_sqm?: number | null; // 지적도 등록면적
  zone_type: string | null;
  zone_type_2: string | null;
  zone_limits: { max_bcr_pct?: number; max_far_pct?: number } | null;
  geometry: any;
};
type Adjacency = { contiguous: boolean | null; components: number | null; note: string };
type Neighbor = { pnu: string; jimok: string; is_road: boolean; geometry: any };
type Boundaries = {
  features: Feature[];
  center: { lat: number; lon: number } | null;
  total_area_sqm: number;
  parcel_count: number;
  adjacency?: Adjacency;
  neighbors?: Neighbor[];       // A+D: 주변 필지·도로(벡터 지적도)
  merged_geometry?: any;        // B: 통합개발 외곽선
  min_gap_m?: number | null;    // C: 실제 최소 이격(m)
};

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

export function ParcelBoundaryMap({
  parcels,
  statusColors,
  statusLabels,
  highlight,
  onParcelClick,
  primaryZone,
}: {
  parcels: string[];
  statusColors?: Record<string, string>; // 주소 → 채움색(계약/동의 상태강조)
  statusLabels?: Record<string, string>; // 주소 → 상태 라벨(팝업)
  highlight?: string; // 강조할 주소(토지조서 행 클릭)
  onParcelClick?: (address: string) => void;
  // 부지분석 확정 용도지역(siteAnalysis.zoneCode) — 구획도·시나리오 용도지역 표기를 단일 출처로
  // 정합시키기 위한 SSOT 오버레이. 주(첫) 필지에만 적용(지적도 토지특성 vs 확정값 불일치 해소).
  primaryZone?: string | null;
}) {
  const list = useMemo(() => parcels.map((s) => s.trim()).filter(Boolean), [parcels]);
  const key = list.join("||");
  // 주 필지의 표시 용도지역 = 확정 SSOT(primaryZone) 우선, 없으면 지적도 토지특성(zone_type).
  // 주소 정규화 비교로 첫 필지(분석 대상)에만 적용 — 다른 필지는 원래 토지특성 유지.
  const normAddr = (a?: string | null) => (a || "").replace(/\s+/g, "");
  const primaryAddr = normAddr(list[0]);
  // 지도 라벨을 계산 측 표준 명칭과 정합("일반상업"→"일반상업지역"). 매칭 실패 시 원문 유지.
  const primaryZoneLabel = primaryZone ? (normalizeZoning(primaryZone) ?? primaryZone) : primaryZone;
  const effZone = (f: Feature, i: number): string | null => {
    if (primaryZoneLabel && (i === 0 || normAddr(f.address) === primaryAddr)) return primaryZoneLabel;
    return f.zone_type;
  };
  const [data, setData] = useState<Boundaries | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const polysRef = useRef<any[]>([]);
  const infoRef = useRef<any>(null);
  const [mapReady, setMapReady] = useState(false); // 카카오맵 생성 완료 → 툴바 활성
  const fs = useMapFullscreen(mapRef);

  // 데이터 조회
  useEffect(() => {
    if (!list.length) { setData(null); return; }
    let alive = true;
    setLoading(true); setError("");
    apiClient
      .post<Boundaries>("/zoning/parcel-boundaries", {
        body: { parcels: list.map((a) => ({ address: a })) },
        useMock: false, timeoutMs: 45000,
      })
      .then((d) => { if (alive) setData(d); })
      .catch((e: unknown) => {
        if (!alive) return;
        // 에러 종류별 진단 문구 — apiClient는 타임아웃(408)·HTTP오류(5xx 등)는
        // ApiClientError(.status)로, 네트워크 실패는 status 없는 일반 에러로 던진다.
        if (e instanceof ApiClientError) {
          const s = e.status;
          if (s === 408) setError("응답 지연(VWorld 지적도 서버 지연) — 잠시 후 재시도");
          else if (s >= 500) setError("서버 오류로 필지 경계를 불러오지 못함");
          else if (s === 0) setError("네트워크 오류 — 연결 상태를 확인하세요");
          else setError("필지 경계를 불러오지 못했습니다.");
        } else {
          // ApiClientError가 아니면 fetch 자체 실패(네트워크 단절 등)
          setError("네트워크 오류 — 연결 상태를 확인하세요");
        }
      })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  // 지도 렌더
  useEffect(() => {
    if (!data || !data.features?.length || !mapEl.current) return;
    let alive = true;
    void loadKakaoMap().then(() => {
      if (!alive || !mapEl.current) return;
      const kakao = window.kakao;
      if (!mapRef.current) {
        mapRef.current = new kakao.maps.Map(mapEl.current, {
          center: new kakao.maps.LatLng(37.5665, 126.978), level: 3,
          // 위성+라벨(하이브리드) 기본 — 항공사진과 지적좌표 정합이 좋아 '도로에서 뜨는' 착시↓
          mapTypeId: kakao.maps.MapTypeId.HYBRID,
        });
      }
      const map = mapRef.current;
      setMapReady(true);
      // 이전 폴리곤/정보창 정리
      polysRef.current.forEach((p) => { try { p.setMap(null); } catch { /* noop */ } });
      polysRef.current = [];
      try { infoRef.current?.close(); } catch { /* noop */ }

      const bounds = new kakao.maps.LatLngBounds();
      let hasPt = false;
      let hiBounds: any = null;

      // ── A+D: 주변 필지·도로(정밀 벡터 지적도) — 선택 필지 아래에 깔아 "빈 공간=도로/인접지"를 명확히 ──
      (data.neighbors ?? []).forEach((nb) => {
        if (!nb.geometry) return;
        geoJsonToKakaoRings(kakao, nb.geometry).forEach((path) => {
          const poly = new kakao.maps.Polygon({
            path,
            strokeWeight: 1,
            strokeColor: nb.is_road ? "#b08746" : "#94a3b8",
            strokeOpacity: nb.is_road ? 0.8 : 0.55,
            fillColor: nb.is_road ? "#e7d3a8" : "#cbd5e1",
            fillOpacity: nb.is_road ? 0.3 : 0.06,
            zIndex: 1,
          });
          poly.setMap(map);
          polysRef.current.push(poly);
        });
      });

      (data.features ?? []).forEach((f, i) => {
        if (!f.geometry) return;
        const zoneDisp = effZone(f, i);
        const sc = statusColors?.[f.address || ""];
        const color = sc || zoneColor(zoneDisp, i);
        const isHi = !!highlight && f.address === highlight;
        const z2 = f.zone_type_2 ? ` / ${f.zone_type_2}` : "";
        const stat = statusLabels?.[f.address || ""];
        const html =
          `<div style="padding:6px 10px;font-size:12px;min-width:160px;">` +
          `<b>${i + 1}. ${f.address || f.pnu}</b>` + (stat ? ` <span style="color:#0e7490">[${stat}]</span>` : "") +
          `<br/>용도지역: ${zoneDisp || "-"}${z2}<br/>` +
          `면적: ${f.area_sqm?.toLocaleString()}㎡ (${pyeong(f.area_sqm)})</div>`;
        geoJsonToKakaoRings(kakao, f.geometry).forEach((path) => {
          const poly = new kakao.maps.Polygon({
            path, strokeWeight: isHi ? 4 : 2, strokeColor: isHi ? "#ef4444" : color,
            strokeOpacity: 0.9, fillColor: color, fillOpacity: isHi ? 0.5 : 0.28,
            zIndex: 3,
          });
          poly.setMap(map);
          polysRef.current.push(poly);
          kakao.maps.event.addListener(poly, "click", (e: any) => {
            try { infoRef.current?.close(); } catch { /* noop */ }
            const iw = new kakao.maps.InfoWindow({ position: e.latLng, content: html, removable: true });
            iw.open(map);
            infoRef.current = iw;
            if (onParcelClick) onParcelClick(f.address || "");
          });
          path.forEach((ll: any) => { bounds.extend(ll); hasPt = true; });
          if (isHi) {
            hiBounds = hiBounds || new kakao.maps.LatLngBounds();
            path.forEach((ll: any) => hiBounds.extend(ll));
          }
        });
      });
      // ── B: 통합개발 외곽선(슬리버 없는 union 단일 경계) — 굵은 청색 점선 ──
      if (data.parcel_count >= 2 && data.merged_geometry) {
        geoJsonToKakaoRings(kakao, data.merged_geometry).forEach((path) => {
          const poly = new kakao.maps.Polygon({
            path, strokeWeight: 3, strokeColor: "#0ea5e9", strokeOpacity: 0.95,
            strokeStyle: "dash", fillColor: "#0ea5e9", fillOpacity: 0.04, zIndex: 5,
          });
          poly.setMap(map);
          polysRef.current.push(poly);
        });
      }

      const applyBounds = () => {
        try {
          if (hiBounds) map.setBounds(hiBounds, 60, 60, 60, 60);
          else if (hasPt) map.setBounds(bounds, 30, 30, 30, 30);
          else if (data.center) map.setCenter(new kakao.maps.LatLng(data.center.lat, data.center.lon));
        } catch { /* noop */ }
      };
      applyBounds();
      setTimeout(() => { if (alive) { try { map.relayout(); } catch { /* noop */ } applyBounds(); } }, 60);
    });
    return () => {
      alive = false;
      try { infoRef.current?.close(); } catch { /* noop */ }
      polysRef.current.forEach((p) => { try { p.setMap(null); } catch { /* noop */ } });
      polysRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, highlight, primaryZone, JSON.stringify(statusColors)]);

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
      {/* 면적 교차검증 — 주 필지(첫 필지)의 토지대장↔지적도 대조 결과 */}
      {(() => {
        const f0 = data?.features?.[0];
        if (!f0?.area_note || f0.area_confidence === "high") return null;
        const low = f0.area_confidence === "low";
        return (
          <div className={`mb-2 rounded-lg border px-3 py-2 text-[11px] font-semibold ${
            low ? "border-amber-500/30 bg-amber-500/10 text-amber-400" : "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-secondary)]"
          }`}>
            {low ? "⚠️ 면적 검증 주의 — " : "ℹ️ 면적 출처 — "}{f0.area_note}
            {f0.area_ledger_sqm && f0.area_cadastral_sqm && (
              <span className="ml-1 text-[var(--text-hint)]">(대장 {f0.area_ledger_sqm.toLocaleString()}㎡ · 지적 {f0.area_cadastral_sqm.toLocaleString()}㎡)</span>
            )}
          </div>
        );
      })()}
      {/* 다필지 인접성(통합개발 가능 여부) */}
      {data && data.parcel_count >= 2 && data.adjacency && (
        <div className={`mb-2 rounded-lg border px-3 py-2 text-[11px] font-semibold ${
          data.adjacency.contiguous === true
            ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-400"
            : data.adjacency.contiguous === false
              ? "border-rose-500/30 bg-rose-500/10 text-rose-400"
              : "border-amber-500/30 bg-amber-500/10 text-amber-400"
        }`}>
          {data.adjacency.contiguous === true ? "🔗 통합개발 가능 — " : data.adjacency.contiguous === false ? "✂ 통합개발 불가 — " : "❔ 인접성 미상 — "}
          {data.adjacency.note}
        </div>
      )}
      {/* 정밀 구획도 범례 — 주변 필지·도로(벡터 지적도) + 통합 외곽선 */}
      {data && (data.neighbors?.length || data.merged_geometry) && (
        <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 px-1 text-[10px] text-[var(--text-hint)]">
          <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-teal-500/40 ring-1 ring-teal-500" />선택 필지</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-slate-300/30 ring-1 ring-slate-400" />주변 필지</span>
          <span className="flex items-center gap-1"><span className="inline-block h-2.5 w-2.5 rounded-sm bg-amber-200/40 ring-1 ring-amber-600" />도로</span>
          {data.parcel_count >= 2 && (
            <span className="flex items-center gap-1"><span className="inline-block h-0 w-3 border-t-2 border-dashed border-sky-500" />통합개발 경계</span>
          )}
          <span className="ml-auto text-[var(--text-hint)]">지적도(VWorld) 벡터 · 위성 베이스 권장</span>
        </div>
      )}
      <div ref={fs.wrapperRef} className={fs.wrapperClass("relative flex flex-col")}>
        <div ref={mapEl} className={fs.mapClass("h-[340px] w-full overflow-hidden rounded-xl border border-[var(--line)]")} />
        <KakaoMapControls mapRef={mapRef} ready={mapReady} onFullscreen={fs.toggle} isFullscreen={fs.isFull} />
        {/* 로딩/빈결과 오버레이 — 무한 '불러오는 중' 방지 */}
        {(loading || (!loading && !error && (!data || !data.features?.length))) && (
          <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-[var(--surface-soft)]/70 text-xs text-[var(--text-hint)]">
            {loading
              ? "지적도 경계 불러오는 중…"
              : "필지 경계를 찾지 못했습니다 (지번 정확도·VWorld 지적도 미제공 가능). 주소를 확인하세요."}
          </div>
        )}
      </div>
      {data && data.features?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {(data.features ?? []).map((f, i) => (
            <span key={f.pnu + i} className="flex items-center gap-1.5 rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1 text-[11px]">
              <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ background: zoneColor(effZone(f, i), i) }} />
              <span className="font-semibold text-[var(--text-secondary)]">{i + 1}. {effZone(f, i) || "용도미상"}{f.zone_type_2 ? `·${f.zone_type_2}` : ""}</span>
              <span className="text-[var(--text-hint)]">{Math.round(f.area_sqm).toLocaleString()}㎡</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export default ParcelBoundaryMap;
