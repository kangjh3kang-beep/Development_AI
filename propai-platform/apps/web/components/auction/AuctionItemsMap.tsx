"use client";

/**
 * 경·공매 물건 위치 지도 — 검색/순위 결과 물건을 지역별로 지도에 마커 표시.
 *
 * 물건 목록(주소)을 POST /auction/geocode 로 좌표 변환(VWorld·캐시·실패스킵, 가짜좌표 금지)한 뒤
 * Leaflet circleMarker 로 찍는다. 마커 색=할인율(유찰 깊을수록 진함), 클릭=상세 선택(onSelect).
 * 지도 엔진: Leaflet + OSM(CDN 동적로드, 새 의존성 0). 풀스크린=useMapFullscreen(네이티브 API).
 * 좌표 미확인 물건은 지도에 안 찍고 "N/M 위치확인" 으로 정직 표기.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useMapFullscreen } from "@/hooks/useMapFullscreen";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global {
  interface Window {
    L: any;
  }
}

export type AuctionMapItem = {
  key: string;
  address?: string | null;
  usage?: string | null;
  min_bid_price?: number | null;
  discount_rate?: number | null;
  fail_count?: number | null;
  status?: string | null;
};

type Located = { key: string; lat: number; lon: number; pnu?: string | null };

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

const won = (n?: number | null) => (n ? `${Math.round(n / 1e4).toLocaleString("ko-KR")}만원` : "-");

/** 할인율(0~100%)→색. 깊을수록 붉게(주목). 무자료=회색. */
function discountColor(rate?: number | null): string {
  if (rate == null || rate <= 0) return "#64748b"; // 슬레이트(신건/무할인)
  if (rate < 20) return "#0ea5e9"; // 청
  if (rate < 40) return "#22c55e"; // 녹
  if (rate < 60) return "#f59e0b"; // 황
  return "#ef4444"; // 적(고할인)
}

export function AuctionItemsMap({
  items,
  onSelect,
}: {
  items: AuctionMapItem[];
  onSelect?: (key: string) => void;
}) {
  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const layerRef = useRef<any>(null);
  const fs = useMapFullscreen(mapRef);
  const [ready, setReady] = useState(false);
  const [loading, setLoading] = useState(false);
  const [note, setNote] = useState("");
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  // 지오코딩 입력(주소 있는 물건만). items 신원은 주소+key 조합 문자열로 안정화.
  const geocodeReq = useMemo(
    () => items.filter((it) => it.key && (it.address || "").trim()).map((it) => ({ key: it.key, address: it.address })),
    [items],
  );
  const reqSig = useMemo(() => geocodeReq.map((r) => r.key).join("|"), [geocodeReq]);

  // 지도 1회 생성.
  useEffect(() => {
    let alive = true;
    loadLeaflet().then(() => {
      if (!alive || !mapEl.current || mapRef.current) return;
      const L = window.L;
      const map = L.map(mapEl.current, { center: [36.5, 127.8], zoom: 7, scrollWheelZoom: true });
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "© OpenStreetMap", maxZoom: 19,
      }).addTo(map);
      layerRef.current = L.layerGroup().addTo(map);
      mapRef.current = map;
      setReady(true);
    }).catch(() => setNote("지도 로딩 실패"));
    return () => {
      alive = false;
      if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
    };
  }, []);

  // 물건 변경 시: 지오코딩 → 마커 갱신.
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    const L = window.L;
    const itemByKey = new Map(items.map((it) => [it.key, it]));
    if (geocodeReq.length === 0) {
      layerRef.current?.clearLayers();
      setNote("주소가 있는 물건이 없습니다.");
      return;
    }
    let alive = true;
    setLoading(true);
    apiClient
      .post<{ located: Located[]; total: number; ok_count: number; note?: string }>("/auction/geocode", { body: { items: geocodeReq }, useMock: false, timeoutMs: 60000 })
      .then((res) => {
        if (!alive || !mapRef.current) return;
        layerRef.current?.clearLayers();
        const located = res.located || [];
        const bounds: [number, number][] = [];
        located.forEach((loc) => {
          const it = itemByKey.get(loc.key);
          const color = discountColor(it?.discount_rate);
          const m = L.circleMarker([loc.lat, loc.lon], {
            radius: 8, color, weight: 2, fillColor: color, fillOpacity: 0.65,
          }).addTo(layerRef.current);
          const html = `<div style="min-width:160px;font-size:12px">
            <b>${(it?.usage || "물건")}</b><br/>
            ${it?.address ? `<span>${it.address}</span><br/>` : ""}
            최저입찰가 <b>${won(it?.min_bid_price)}</b>${it?.discount_rate ? ` · 할인 ${Math.round(it.discount_rate)}%` : ""}
            ${it?.fail_count ? ` · 유찰 ${it.fail_count}회` : ""}
          </div>`;
          m.bindPopup(html);
          m.on("click", () => onSelectRef.current?.(loc.key));
          bounds.push([loc.lat, loc.lon]);
        });
        if (bounds.length > 0) {
          try { mapRef.current.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 }); } catch { /* noop */ }
        }
        setNote(res.note || `${located.length}건 위치 표시`);
      })
      .catch(() => { if (alive) setNote("위치 변환 실패(잠시 후 재시도)"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, reqSig]);

  return (
    <div ref={fs.wrapperRef} className={fs.wrapperClass("relative flex flex-col")}>
      <div
        ref={mapEl}
        className={fs.mapClass("w-full rounded-xl overflow-hidden border border-[var(--line-strong)] z-0")}
        style={fs.isFull ? undefined : { height: 420 }}
      />
      {/* 범례 + 풀스크린 */}
      <div className="pointer-events-none absolute left-3 top-3 z-[1] rounded-lg border border-[var(--line)] bg-[var(--surface)]/90 px-2.5 py-1.5 text-[10px] text-[var(--text-secondary)] backdrop-blur">
        <span className="font-bold text-[var(--text-primary)]">할인율</span>
        {[["신건", "#64748b"], ["~20%", "#0ea5e9"], ["~40%", "#22c55e"], ["~60%", "#f59e0b"], ["60%+", "#ef4444"]].map(([l, c]) => (
          <span key={l} className="ml-1.5 inline-flex items-center gap-0.5">
            <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: c }} />{l}
          </span>
        ))}
      </div>
      <button
        type="button"
        onClick={fs.toggle}
        className="absolute right-3 top-3 z-[1] rounded-lg border border-[var(--line)] bg-[var(--surface)]/90 px-2.5 py-1.5 text-[11px] font-bold text-[var(--text-secondary)] backdrop-blur hover:text-[var(--text-primary)]"
      >
        {fs.isFull ? "✕ 닫기" : "⛶ 전체화면"}
      </button>
      {(loading || !ready) && (
        <div className="absolute inset-0 z-[2] flex items-center justify-center rounded-xl bg-[var(--surface)]/60 text-xs text-[var(--text-secondary)]">
          {!ready ? "지도 로딩…" : "물건 위치 변환 중…"}
        </div>
      )}
      {note && (
        <p className="mt-1.5 text-[11px] text-[var(--text-tertiary)]">📍 {note} · 좌표 미확인 물건은 표시되지 않습니다(가짜좌표 없음).</p>
      )}
    </div>
  );
}