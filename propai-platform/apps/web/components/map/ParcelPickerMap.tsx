"use client";

/**
 * ParcelPickerMap — 지도 클릭으로 필지를 다중 선택하는 컴포넌트.
 *
 * 사용 방법:
 *   1. 지도를 클릭하면 해당 좌표의 필지 정보를 백엔드에서 조회한다.
 *   2. 조회 완료 후 지도 위에 '확인 카드'가 나타난다 (즉시 추가 안 함).
 *   3. 확인 카드에서 [＋추가]를 누르면 staged(선택 대기) 목록에 쌓인다.
 *   4. 하단 바의 [완료(N필지 등록)]를 누르면 onPickMany(staged) 콜백이 호출된다.
 *   5. 단일 선택용 onPick(하위호환)도 그대로 지원한다.
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
  /** 단일 필지 선택 콜백 — 하위호환용. onPickMany와 함께 사용 가능 */
  onPick?: (parcel: ParcelAtPointResult) => void;
  /** 다중 필지 선택 완료 콜백 — 완료 버튼 클릭 시 staged 배열 전달 */
  onPickMany?: (parcels: ParcelAtPointResult[]) => void;
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

/** ㎡ → 평 변환(소수점 1자리) */
function toP(sqm: number): string {
  return (sqm / 3.305785).toFixed(1);
}

export function ParcelPickerMap({ onPick, onPickMany, height = 360 }: ParcelPickerMapProps) {
  const mapEl = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<any>(null);
  const fs = useMapFullscreen(mapRef);

  // 조회 상태
  const [status, setStatus] = useState<"idle" | "loading" | "found" | "notfound" | "error">("idle");
  const [statusMsg, setStatusMsg] = useState("");

  // 확인 대기 중인 필지(클릭→조회완료, 아직 staged에 안 들어간 상태)
  const [pending, setPending] = useState<ParcelAtPointResult | null>(null);
  // 임시 마커 레이어(pending 상태일 때 지도 위에 표시, 취소/추가 시 제거)
  const pendingLayerRef = useRef<any>(null);

  // staged: 사용자가 [＋추가]로 확정한 필지 목록
  const [staged, setStaged] = useState<ParcelAtPointResult[]>([]);
  // staged 필지별 폴리곤 레이어 — pnu → Leaflet layerGroup
  const stagedLayersRef = useRef<Map<string, any>>(new Map());

  // 콜백 ref — useEffect 클로저에서 최신 onPick/onPickMany를 참조하기 위함
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;
  const onPickManyRef = useRef(onPickMany);
  onPickManyRef.current = onPickMany;
  // staged를 ref로도 보관 — queryParcel이 staged를 의존하지 않게 해 지도 재생성(폴리곤 소실)을 막는다.
  const stagedRef = useRef<ParcelAtPointResult[]>([]);
  stagedRef.current = staged;

  // 연타 응답 경합 가드: 마지막 클릭만 반영(stale 필지 폐기)
  const querySeqRef = useRef(0);

  /** pending 레이어(임시 마커·폴리곤) 지도에서 제거 */
  const clearPendingLayer = useCallback(() => {
    if (pendingLayerRef.current) {
      try { pendingLayerRef.current.remove(); } catch { /* noop */ }
      pendingLayerRef.current = null;
    }
  }, []);

  /** staged 특정 필지의 폴리곤 레이어 지도에서 제거 */
  const removeStagedLayer = useCallback((pnu: string) => {
    const layer = stagedLayersRef.current.get(pnu);
    if (layer) {
      try { layer.remove(); } catch { /* noop */ }
      stagedLayersRef.current.delete(pnu);
    }
  }, []);

  /** staged 모든 폴리곤 레이어 지도에서 제거 */
  const clearAllStagedLayers = useCallback(() => {
    stagedLayersRef.current.forEach((layer) => {
      try { layer.remove(); } catch { /* noop */ }
    });
    stagedLayersRef.current.clear();
  }, []);

  /**
   * staged 필지를 '선택됨' 녹색 폴리곤으로 지도에 고정 표시.
   * 이미 레이어가 있으면 건너뛴다.
   */
  const addStagedLayer = useCallback((parcel: ParcelAtPointResult) => {
    const map = mapRef.current;
    const L = window.L;
    if (!map || !L || !parcel.pnu) return;
    if (stagedLayersRef.current.has(parcel.pnu)) return; // 이미 표시됨

    const layer = L.layerGroup().addTo(map);

    // 선택됨 — 녹색 폴리곤
    if (parcel.geometry) {
      const rings = geoJsonToLeafletRings(parcel.geometry);
      if (rings.length > 0) {
        L.polygon(rings, {
          color: "#22c55e", weight: 2.5, fillColor: "#22c55e", fillOpacity: 0.28,
        }).addTo(layer);
      }
    }

    // 중심 마커(녹색)
    if (parcel.lat != null && parcel.lon != null) {
      L.circleMarker([parcel.lat, parcel.lon], {
        radius: 7, color: "#22c55e", weight: 2.5, fillColor: "#22c55e", fillOpacity: 0.9,
      }).addTo(layer);
    }

    stagedLayersRef.current.set(parcel.pnu, layer);
  }, []);

  /** 클릭한 좌표로 필지를 조회하고 결과를 pending 상태로 둔다 */
  const queryParcel = useCallback(async (lat: number, lon: number) => {
    const seq = ++querySeqRef.current;
    setStatus("loading");
    setStatusMsg("필지 조회 중…");
    setPending(null);
    clearPendingLayer();

    const L = window.L;
    const map = mapRef.current;
    if (!map) return;

    // 클릭 위치에 임시 파란 마커 표시(조회 중 피드백)
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
      // 클릭 지점에서 필지를 못 찾은 경우 — 정직하게 안내(가짜 생성 없음)
      const msg = result.reason || "클릭 지점에서 필지를 찾지 못했습니다. 건물 내부나 지적도 제공 구역을 클릭해 주세요.";
      setStatus("notfound");
      setStatusMsg(msg);
      // 클릭 위치에 빨간 'X' 마커로 미확인 표시
      const notFoundLayer = L.layerGroup().addTo(map);
      L.circleMarker([lat, lon], {
        radius: 7, color: "#ef4444", weight: 2, fillColor: "#ef4444", fillOpacity: 0.3,
      }).bindPopup(`<div style="font-size:12px;max-width:200px;">${msg}</div>`, { maxWidth: 220 }).openPopup().addTo(notFoundLayer);
      pendingLayerRef.current = notFoundLayer;
      return;
    }

    // 이미 staged에 있는 필지인지 확인(ref로 읽어 deps 오염 방지)
    const alreadyStaged = stagedRef.current.some((s) => s.pnu && s.pnu === result.pnu);

    setStatus("found");
    setStatusMsg("");
    // lat/lon 정보 보완(확인 카드·staged 레이어에서 좌표 재사용)
    result.lat = lat;
    result.lon = lon;
    setPending(result);

    // 임시 pending 레이어 표시(파란 폴리곤 + 마커)
    const layer = L.layerGroup().addTo(map);
    pendingLayerRef.current = layer;

    if (result.geometry && !alreadyStaged) {
      const rings = geoJsonToLeafletRings(result.geometry);
      if (rings.length > 0) {
        const poly = L.polygon(rings, {
          color: "#3b82f6", weight: 2.5, fillColor: "#3b82f6", fillOpacity: 0.22,
        }).addTo(layer);
        // 폴리곤 경계에 맞춰 지도 이동
        try { map.fitBounds(poly.getBounds(), { padding: [40, 40], maxZoom: 17 }); } catch { /* noop */ }
      }
    }

    // 중심점 마커(폴리곤 없을 때도 위치 표시)
    L.circleMarker([lat, lon], {
      radius: 7, color: "#3b82f6", weight: 2.5, fillColor: "#3b82f6", fillOpacity: 0.8,
    }).addTo(layer);

    // 하위호환: 단일 모드(onPick만, onPickMany 없음)에서만 즉시 호출.
    // 다중 모드(onPickMany 존재)에선 확인 카드 [＋추가] 승인 흐름을 거쳐야 하므로 즉시 호출하지 않는다.
    if (onPickRef.current && !onPickManyRef.current) {
      onPickRef.current(result);
    }
  }, [clearPendingLayer]);

  /** [＋추가] 버튼: pending 필지를 staged에 넣고 녹색 폴리곤으로 고정 */
  const handleConfirmAdd = useCallback(() => {
    if (!pending || !pending.found) return;
    const pnu = pending.pnu;

    // 같은 pnu 중복 방지
    if (pnu && staged.some((s) => s.pnu === pnu)) {
      clearPendingLayer();
      setPending(null);
      setStatus("idle");
      return;
    }

    setStaged((prev) => [...prev, pending]);
    // pending 레이어 제거 후 staged 녹색 레이어 고정
    clearPendingLayer();
    addStagedLayer(pending);
    setPending(null);
    setStatus("idle");
  }, [pending, staged, clearPendingLayer, addStagedLayer]);

  /** [취소] 버튼: pending 상태 취소(임시 마커·폴리곤 제거) */
  const handleCancelPending = useCallback(() => {
    clearPendingLayer();
    setPending(null);
    setStatus("idle");
  }, [clearPendingLayer]);

  /** [제거] 버튼: 이미 staged된 필지를 목록과 지도에서 제거 */
  const handleRemoveStaged = useCallback((pnu: string) => {
    setStaged((prev) => prev.filter((s) => s.pnu !== pnu));
    removeStagedLayer(pnu);
    clearPendingLayer();
    setPending(null);
    setStatus("idle");
  }, [removeStagedLayer, clearPendingLayer]);

  /** [전체취소] 버튼: staged 전부 제거 */
  const handleClearAll = useCallback(() => {
    setStaged([]);
    clearAllStagedLayers();
    clearPendingLayer();
    setPending(null);
    setStatus("idle");
  }, [clearAllStagedLayers, clearPendingLayer]);

  /** [완료(N필지 등록)] 버튼: onPickMany 콜백 호출 */
  const handleComplete = useCallback(() => {
    if (staged.length === 0) return;
    onPickManyRef.current?.(staged);
  }, [staged]);

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
      // staged 레이어 맵도 초기화(지도가 사라지면 참조 불필요)
      stagedLayersRef.current.clear();
      leafletLoading = null; // 다음 마운트에서 재로딩 가능하도록 초기화
    };
  }, [queryParcel]);

  // staged 합산 면적 계산
  const totalAreaSqm = staged.reduce((acc, p) => acc + (p.area_sqm ?? 0), 0);

  // pending이 이미 staged에 있는지 여부(확인 카드 표시용)
  const pendingAlreadyStaged = pending?.pnu
    ? staged.some((s) => s.pnu === pending.pnu)
    : false;

  return (
    <div className="flex flex-col gap-2 rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-3">
      {/* 안내 메시지 */}
      <p className="text-[11px] font-semibold text-[var(--text-secondary)]">
        지도를 클릭하면 해당 필지가 확인 카드로 표시됩니다. [＋추가]로 선택 목록에 담고 [완료]로 등록하세요.
        <span className="ml-1 text-[var(--text-hint)]">(건물 외곽선이나 도로도 선택 가능, 지목은 카드에서 확인)</span>
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
            // 전체화면 종료 아이콘
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M8 3v3a2 2 0 0 1-2 2H3"/><path d="M21 8h-3a2 2 0 0 1-2-2V3"/><path d="M3 16h3a2 2 0 0 1 2 2v3"/><path d="M16 21v-3a2 2 0 0 1 2-2h3"/></svg>
          ) : (
            // 전체화면 열기 아이콘
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 8V5a2 2 0 0 1 2-2h3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M21 16v3a2 2 0 0 1-2 2h-3"/><path d="M8 21H5a2 2 0 0 1-2-2v-3"/></svg>
          )}
        </button>

        {/* 초기 안내 오버레이(아직 클릭 전) */}
        {status === "idle" && staged.length === 0 && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg">
            <span className="rounded-lg bg-[var(--surface)]/80 px-3 py-1.5 text-[11px] font-semibold text-[var(--text-secondary)] shadow">
              지도를 클릭해 필지 선택
            </span>
          </div>
        )}

        {/* ── 확인 카드 오버레이 — 조회 완료 후 사용자가 추가/취소를 결정하는 카드 ── */}
        {status === "found" && pending && (
          <div className="absolute bottom-10 left-1/2 z-[500] -translate-x-1/2 w-[calc(100%-32px)] max-w-sm">
            <div className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface)]/95 p-3 shadow-[var(--shadow-lg)] backdrop-blur-sm">
              {/* 필지 요약 정보 */}
              <div className="mb-2 space-y-0.5">
                <p className="text-[12px] font-bold text-[var(--text-primary)] leading-snug">
                  {/* 주소 또는 PNU 표시 */}
                  {pending.address || pending.jibun || pending.pnu}
                </p>
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[var(--text-secondary)]">
                  {/* 면적(㎡·평) */}
                  {pending.area_sqm != null && pending.area_sqm > 0 && (
                    <span className="font-semibold text-[var(--accent-strong)]">
                      {Math.round(pending.area_sqm).toLocaleString()}㎡ ({toP(pending.area_sqm)}평)
                    </span>
                  )}
                  {/* 용도지역 */}
                  {pending.zone_type && (
                    <span className="rounded bg-[var(--surface-muted)] px-1.5 py-0.5 font-semibold">
                      {pending.zone_type}
                    </span>
                  )}
                  {/* 지목 — 도로 등도 그대로 표기(필터 없음) */}
                  {pending.jimok && (
                    <span>지목 <b>{pending.jimok}</b></span>
                  )}
                </div>
              </div>

              {/* 버튼 영역 */}
              {pendingAlreadyStaged ? (
                // 이미 staged에 있는 필지 → 제거 옵션 표시
                <div className="flex items-center gap-2">
                  <span className="flex-1 text-[11px] font-bold text-emerald-500">이미 선택됨</span>
                  <button
                    type="button"
                    onClick={() => pending.pnu && handleRemoveStaged(pending.pnu)}
                    className="rounded-lg border border-red-400/40 bg-red-500/10 px-3 py-1.5 text-[11px] font-bold text-red-500 hover:bg-red-500/20 transition-colors"
                  >
                    제거
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelPending}
                    className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-muted)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] hover:bg-[var(--surface)] transition-colors"
                  >
                    닫기
                  </button>
                </div>
              ) : (
                // 신규 필지 → 추가/취소 버튼
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleConfirmAdd}
                    className="flex-1 rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-bold text-white hover:opacity-90 transition-opacity"
                  >
                    ＋추가
                  </button>
                  <button
                    type="button"
                    onClick={handleCancelPending}
                    className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-muted)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] hover:bg-[var(--surface)] transition-colors"
                  >
                    취소
                  </button>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── 하단 고정 바 — 선택 필지 수·합산 면적·완료/전체취소 ── */}
      <div className="flex items-center gap-2 rounded-lg border border-[var(--line)] bg-[var(--surface-muted)]/60 px-3 py-2">
        {/* 선택 현황 */}
        <div className="flex-1 text-[11px]">
          {staged.length > 0 ? (
            <span className="font-bold text-[var(--text-primary)]">
              선택 <span className="text-[var(--accent-strong)]">{staged.length}필지</span>
              {totalAreaSqm > 0 && (
                <span className="ml-1.5 font-normal text-[var(--text-secondary)]">
                  · 합산 {Math.round(totalAreaSqm).toLocaleString()}㎡
                </span>
              )}
            </span>
          ) : (
            <span className="text-[var(--text-hint)]">아직 선택된 필지 없음</span>
          )}
        </div>

        {/* 전체취소 버튼 — staged가 있을 때만 활성 */}
        {staged.length > 0 && (
          <button
            type="button"
            onClick={handleClearAll}
            className="rounded-lg border border-[var(--line-strong)] px-2.5 py-1.5 text-[10px] font-bold text-[var(--text-secondary)] hover:border-red-400/50 hover:text-red-500 hover:bg-red-500/10 transition-colors"
          >
            전체취소
          </button>
        )}

        {/* 완료 버튼 — staged가 있을 때만 활성(없으면 비활성 스타일) */}
        <button
          type="button"
          disabled={staged.length === 0}
          onClick={handleComplete}
          className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-bold text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 transition-opacity"
        >
          완료({staged.length}필지 등록)
        </button>
      </div>
    </div>
  );
}

export default ParcelPickerMap;
