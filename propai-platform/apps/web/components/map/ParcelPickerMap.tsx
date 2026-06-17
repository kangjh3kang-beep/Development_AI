"use client";

/**
 * ParcelPickerMap — 지도 클릭으로 필지를 선택하는 컴포넌트.
 *
 * 사용 방법:
 *   1. 지도를 클릭하면 클릭한 좌표(lat/lon)를 백엔드에 전송한다.
 *   2. 백엔드(POST /zoning/parcel-at-point)가 해당 좌표의 필지 정보를 돌려준다.
 *   3. 필지를 찾으면 마커와 구획 폴리곤을 지도 위에 그리고 onPick 콜백을 호출한다.
 *   4. 필지를 못 찾으면 팝업으로 정직하게 안내한다(가짜 데이터 생성 금지).
 *
 * SSR 안전: dynamicMap(ssr:false)로 감싸서 사용해야 한다(이 파일을 직접 import 금지).
 * 지도 엔진: Leaflet + OSM (CDN 동적 로드, 새 npm 의존성 없음).
 * 좌표 주의: Leaflet은 [lat, lng] 순, GeoJSON은 [lng, lat] 순이라 변환이 필요하다.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useMapFullscreen } from "@/hooks/useMapFullscreen";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    L: any;
  }
}

/** 백엔드 /zoning/parcel-at-point 응답 형태 */
export interface ParcelAtPointResult {
  found: boolean;
  pnu?: string;
  /** 지번 주소 */
  address?: string;
  jibun?: string;
  /** 법정동 코드(10자리) — PNU 앞 10자리 */
  bcode?: string;
  area_sqm?: number | null;
  zone_type?: string | null;
  jimok?: string | null;
  bcr_pct?: number | null;
  far_pct?: number | null;
  /** GeoJSON Polygon/MultiPolygon — 필지 경계 */
  geometry?: any;
  lat?: number;
  lon?: number;
  reason?: string;
}

interface ParcelPickerMapProps {
  /** 필지 선택 완료 시 콜백 — 부모가 handleAddressSelect로 필지를 추가한다 */
  onPick: (parcel: ParcelAtPointResult) => void;
  /** 지도 높이(px), 기본 360 */
  height?: number;
}

/** Leaflet CDN 단일 로딩 (AuctionItemsMap과 동일 패턴) */
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
    const script = document.createElement("script");
    script.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Leaflet 로드 실패"));
    document.head.appendChild(script);
  });
  return leafletLoading;
}

/**
 * GeoJSON Polygon/MultiPolygon 좌표([lng, lat])를
 * Leaflet 좌표([lat, lng]) 배열의 배열로 변환한다.
 */
function geoJsonToLeafletRings(geometry: any): [number, number][][] {
  if (!geometry) return [];
  const rings: [number, number][][] = [];
  const addRing = (coords: number[][]) => {
    const ring = coords
      .filter((c) => Array.isArray(c) && c.length >= 2)
      // GeoJSON은 [lng, lat]이므로 뒤집는다
      .map(([lng, lat]) => [lat, lng] as [number, number]);
    if (ring.length >= 3) rings.push(ring);
  };
  if (geometry.type === "Polygon") {
    (geometry.coordinates || []).forEach(addRing);
  } else if (geometry.type === "MultiPolygon") {
    (geometry.coordinates || []).forEach((poly: number[][][]) =>
      (poly || []).forEach(addRing),
    );
  }
  return rings;
}

export function ParcelPickerMap({ onPick, height = 360 }: ParcelPickerMapProps) {
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  // 현재 선택된 필지의 레이어(마커+폴리곤)를 저장해 다음 클릭 시 교체한다
  const layerRef = useRef<any>(null);
  const fs = useMapFullscreen(mapRef);

  const [status, setStatus] = useState<"idle" | "loading" | "found" | "notfound" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");
  // 가장 최근에 선택된 필지 정보(화면 표시용)
  const [selected, setSelected] = useState<ParcelAtPointResult | null>(null);
  // 콜백 ref — useEffect 클로저에서 최신 onPick을 참조하기 위함
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;
  const querySeqRef = useRef(0); // 연타 응답 경합 가드: 마지막 클릭만 반영(stale 필지 폐기)

  /** 클릭한 좌표로 필지를 조회하고 결과를 지도에 표시한다 */
  const queryParcel = useCallback(async (lat: number, lon: number) => {
    const seq = ++querySeqRef.current;
    setStatus("loading");
    setStatusMsg("필지 조회 중…");
    const L = window.L;
    const map = mapRef.current;
    if (!map) return;

    // 이전 선택 레이어 제거
    if (layerRef.current) {
      try { layerRef.current.remove(); } catch { /* noop */ }
      layerRef.current = null;
    }

    // 클릭 위치에 임시 마커 표시(조회 중 피드백)
    const tempMarker = L.circleMarker([lat, lon], {
      radius: 6, color: "#3b82f6", weight: 2, fillColor: "#3b82f6", fillOpacity: 0.5,
    }).addTo(map);

    let result: ParcelAtPointResult;
    try {
      result = await apiClient.post<ParcelAtPointResult>(
        "/zoning/parcel-at-point",
        { body: { lat, lon }, useMock: false, timeoutMs: 20000 },
      );
    } catch {
      tempMarker.remove();
      if (seq !== querySeqRef.current) return; // 더 새로운 클릭이 있었으면 무시
      setStatus("error");
      setStatusMsg("조회 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.");
      return;
    }

    tempMarker.remove();
    if (seq !== querySeqRef.current) return; // stale 응답 폐기(연타 시 마지막 클릭만 반영)

    if (!result.found) {
      // 클릭 지점에서 필지를 못 찾은 경우 — 팝업으로 정직하게 안내(가짜 생성 없음)
      const msg = result.reason || "클릭 지점에서 필지를 찾지 못했습니다. 건물 내부나 지적도 제공 구역을 클릭해 주세요.";
      setStatus("notfound");
      setStatusMsg(msg);
      // 클릭 위치에 'X' 마커로 미확인 표시
      const notFoundLayer = L.layerGroup().addTo(map);
      L.circleMarker([lat, lon], {
        radius: 7, color: "#ef4444", weight: 2, fillColor: "#ef4444", fillOpacity: 0.3,
      }).bindPopup(`<div style="font-size:12px;max-width:200px;">${msg}</div>`, { maxWidth: 220 }).openPopup().addTo(notFoundLayer);
      layerRef.current = notFoundLayer;
      return;
    }

    // 찾은 경우 — 마커 + 구획 폴리곤 표시
    setStatus("found");
    setStatusMsg("");
    setSelected(result);

    const layer = L.layerGroup().addTo(map);
    layerRef.current = layer;

    // 필지 정보 팝업 HTML 구성
    const areaText = result.area_sqm
      ? `${result.area_sqm.toLocaleString()}㎡ (${(result.area_sqm / 3.305785).toFixed(1)}평)`
      : "면적 미확인";
    const popup = L.popup({ maxWidth: 260 }).setContent(
      `<div style="font-size:12px;line-height:1.6;padding:2px 4px;">` +
      `<b>${result.address || result.pnu}</b><br/>` +
      `용도지역: ${result.zone_type || "미확인"}<br/>` +
      `면적: ${areaText}` +
      (result.bcr_pct ? `<br/>건폐율 ${result.bcr_pct}% · 용적률 ${result.far_pct ?? "-"}%` : "") +
      `</div>`,
    );

    if (result.geometry) {
      // 필지 경계 폴리곤을 그린다
      const rings = geoJsonToLeafletRings(result.geometry);
      if (rings.length > 0) {
        const poly = L.polygon(rings, {
          color: "#3b82f6", weight: 2.5, fillColor: "#3b82f6", fillOpacity: 0.22,
        }).addTo(layer);
        poly.bindPopup(popup);
        poly.openPopup();
        // 폴리곤 경계에 맞춰 지도 이동
        try { map.fitBounds(poly.getBounds(), { padding: [40, 40], maxZoom: 17 }); } catch { /* noop */ }
      }
    }

    // 중심점 마커(폴리곤 없을 때도 위치 표시)
    const marker = L.circleMarker([lat, lon], {
      radius: 7, color: "#3b82f6", weight: 2.5, fillColor: "#3b82f6", fillOpacity: 0.8,
    }).addTo(layer);
    if (!result.geometry) marker.bindPopup(popup).openPopup();

    // 부모(GlobalAddressSearch)에 선택 필지 전달
    onPickRef.current(result);
  }, []);

  // Leaflet 지도 초기화 (컴포넌트 마운트 시 1회)
  useEffect(() => {
    let alive = true;
    loadLeaflet()
      .then(() => {
        if (!alive || !mapEl.current || mapRef.current) return;
        const L = window.L;
        // 서울 중심으로 초기화, 스크롤 줌 활성
        const map = L.map(mapEl.current, {
          center: [37.5665, 126.978],
          zoom: 12,
          scrollWheelZoom: true,
        });
        // OSM 타일 (카카오 키 없이 전 세계 사용 가능)
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: "© OpenStreetMap",
          maxZoom: 19,
        }).addTo(map);
        mapRef.current = map;

        // 지도 클릭 → 필지 조회
        map.on("click", (e: any) => {
          void queryParcel(e.latlng.lat, e.latlng.lng);
        });
      })
      .catch(() => {
        setStatus("error");
        setStatusMsg("지도 로딩에 실패했습니다.");
      });

    return () => {
      alive = false;
      if (mapRef.current) {
        try { mapRef.current.remove(); } catch { /* noop */ }
        mapRef.current = null;
      }
      leafletLoading = null; // 다음 마운트에서 재로딩 가능하도록 초기화
    };
  }, [queryParcel]);

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-3">
      {/* 안내 메시지 */}
      <p className="text-[11px] font-semibold text-[var(--text-secondary)]">
        지도를 클릭하면 해당 위치의 필지가 자동으로 추가됩니다.
        <span className="ml-1 text-[var(--text-hint)]">(건물 외곽선이나 도로 제외 지적도 영역 클릭)</span>
      </p>

      {/* 상태 메시지 — 로딩/오류/미발견 표시 */}
      {status === "loading" && (
        <div className="flex items-center gap-1.5 text-[11px] text-[var(--accent-strong)]">
          <div className="h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent-strong)] border-t-transparent" />
          {statusMsg}
        </div>
      )}
      {status === "notfound" && (
        <p className="text-[11px] font-semibold text-amber-500">⚠ {statusMsg}</p>
      )}
      {status === "error" && (
        <p className="text-[11px] font-semibold text-red-500">✕ {statusMsg}</p>
      )}

      {/* 선택된 필지 미리보기 칩 */}
      {status === "found" && selected && (
        <div className="flex flex-wrap items-center gap-1.5 rounded-lg border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-2.5 py-1.5 text-[11px]">
          <span className="font-bold text-[var(--accent-strong)]">선택됨</span>
          <span className="text-[var(--text-primary)]">{selected.address || selected.pnu}</span>
          {selected.area_sqm && (
            <span className="text-[var(--text-secondary)]">
              {Math.round(selected.area_sqm).toLocaleString()}㎡
            </span>
          )}
          {selected.zone_type && (
            <span className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 font-semibold text-[var(--text-secondary)]">
              {selected.zone_type}
            </span>
          )}
        </div>
      )}

      {/* Leaflet 지도 캔버스 — useMapFullscreen 래퍼 */}
      <div ref={fs.wrapperRef} className={fs.wrapperClass("relative")}>
        <div
          ref={mapEl}
          className={fs.mapClass("w-full overflow-hidden rounded-lg border border-[var(--line)]")}
          style={{ height }}
        />
        {/* 풀스크린 버튼 */}
        <button
          type="button"
          onClick={fs.toggle}
          title={fs.isFull ? "전체화면 종료" : "전체화면"}
          className="absolute right-2 top-2 z-[400] rounded-lg border border-[var(--line-strong)] bg-[var(--surface)]/90 p-1.5 text-[var(--text-secondary)] shadow hover:bg-[var(--surface-muted)] transition-colors"
          aria-label="전체화면"
        >
          {fs.isFull ? (
            // 전체화면 종료 아이콘(닫힘)
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/><path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/></svg>
          ) : (
            // 전체화면 열기 아이콘(확장)
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8V5a2 2 0 0 1 2-2h3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M21 16v3a2 2 0 0 1-2 2h-3"/><path d="M8 21H5a2 2 0 0 1-2-2v-3"/></svg>
          )}
        </button>
        {/* 초기 안내 오버레이(아직 클릭 전) */}
        {status === "idle" && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg">
            <span className="rounded-lg bg-[var(--surface)]/80 px-3 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] shadow">
              지도를 클릭해 필지 선택
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

export default ParcelPickerMap;
