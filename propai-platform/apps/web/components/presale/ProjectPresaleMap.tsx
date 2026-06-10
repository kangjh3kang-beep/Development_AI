"use client";

/**
 * 프로젝트 주변 분양 지도 — 관심지역 모니터링용.
 * 선택한 프로젝트의 중심 좌표 기준 반경 내 분양 단지를 '유형별 색상' 마커로 표시하고,
 * 마커 클릭 시 onSelect(item) → 상세(청약일정·분양가·공고링크) 모달을 연다.
 * 지도 엔진: 카카오맵 JS SDK(loadKakaoMap 재사용).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { loadKakaoMap } from "@/lib/kakao-map";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global { interface Window { kakao: any } }

export type PresaleMarker = {
  house_manage_no: string; pblanc_no: string; name: string; address: string;
  area_name: string; product: string; product_label: string; status: string;
  receipt_begin: string; receipt_end: string; total_households: string;
  url: string; lat: number; lon: number; distance_m: number;
};

const PRODUCT_COLOR: Record<string, string> = {
  apt: "#14b8a6", officetel: "#8b5cf6", remndr: "#f59e0b", opt: "#ec4899", pblrent: "#3b82f6",
};
const PRODUCT_LABEL: Record<string, string> = {
  apt: "APT", officetel: "오피스텔·생숙", remndr: "APT 잔여세대", opt: "임의공급", pblrent: "공공지원 민간임대",
};

export function ProjectPresaleMap({
  center, items, radiusM = 3000, onSelect,
}: {
  center: { lat: number; lon: number } | null;
  items: PresaleMarker[];
  radiusM?: number;
  onSelect: (it: PresaleMarker) => void;
}) {
  const mapEl = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]);
  const infoRef = useRef<any>(null);
  const [sdkReady, setSdkReady] = useState(false);

  useEffect(() => {
    let alive = true;
    loadKakaoMap().then(() => alive && setSdkReady(true)).catch(() => {});
    return () => { alive = false; };
  }, []);

  const openInfo = useCallback((pos: any, html: string) => {
    const kakao = window.kakao;
    try { infoRef.current?.close(); } catch { /* noop */ }
    const iw = new kakao.maps.InfoWindow({ position: pos, content: html, removable: true, zIndex: 900 });
    iw.open(mapRef.current);
    infoRef.current = iw;
  }, []);

  // 지도 초기화
  useEffect(() => {
    if (!sdkReady || !center?.lat || !mapEl.current || mapRef.current) return;
    const kakao = window.kakao;
    const c = new kakao.maps.LatLng(center.lat, center.lon);
    const map = new kakao.maps.Map(mapEl.current, { center: c, level: 6 });
    mapRef.current = map;
    // 중심(프로젝트) 마커 + 반경 원
    new kakao.maps.Circle({ center: c, radius: radiusM, strokeWeight: 2, strokeColor: "#14b8a6", strokeOpacity: 0.8, strokeStyle: "dashed", fillColor: "#14b8a6", fillOpacity: 0.04 }).setMap(map);
    const pin = document.createElement("div");
    pin.style.cssText = "width:14px;height:14px;border-radius:50%;background:#ef4444;border:3px solid #fff;box-shadow:0 0 6px rgba(0,0,0,.4)";
    new kakao.maps.CustomOverlay({ position: c, content: pin, xAnchor: 0.5, yAnchor: 0.5, zIndex: 1000 }).setMap(map);
    setTimeout(() => { try { map.relayout(); map.setCenter(c); } catch { /* noop */ } }, 100);
    return () => {
      try { infoRef.current?.close(); } catch { /* noop */ }
      mapRef.current = null;
    };
  }, [sdkReady, center, radiusM]);

  // 분양 마커 갱신(유형별 색)
  useEffect(() => {
    if (!mapRef.current || !window.kakao) return;
    const kakao = window.kakao;
    overlaysRef.current.forEach((o) => { try { o.setMap(null); } catch { /* noop */ } });
    overlaysRef.current = [];
    const pts: Array<[number, number]> = center?.lat ? [[center.lat, center.lon]] : [];
    items.forEach((it) => {
      if (!it.lat || !it.lon) return;
      pts.push([it.lat, it.lon]);
      const col = PRODUCT_COLOR[it.product] || "#64748b";
      const html = `<div style="min-width:190px;max-width:250px;font-family:sans-serif;">
          <div style="font-weight:700;font-size:13px;color:#0f172a;">${it.name}</div>
          <div style="font-size:11px;color:#64748b;margin:2px 0 4px;">${it.product_label} · ${it.status}</div>
          <div style="font-size:11px;color:#475569;">접수 ${it.receipt_begin || "-"} ~ ${it.receipt_end || "-"}</div>
          <div style="font-size:11px;color:#475569;">공급 ${it.total_households || "-"}세대 · ${Math.round((it.distance_m || 0) / 100) / 10}km</div>
          <div style="margin-top:5px;font-size:11px;color:#2563eb;font-weight:700;cursor:pointer;">상세 보기(청약일정·분양가) ↗</div>
        </div>`;
      const dot = document.createElement("div");
      dot.style.cssText = `width:16px;height:16px;border-radius:4px;background:${col};border:2px solid #fff;opacity:.92;cursor:pointer;box-shadow:0 0 4px rgba(0,0,0,.35);transform:rotate(45deg)`;
      const pos = new kakao.maps.LatLng(it.lat, it.lon);
      dot.onclick = () => { openInfo(pos, html); onSelect(it); };
      const ov = new kakao.maps.CustomOverlay({ position: pos, content: dot, xAnchor: 0.5, yAnchor: 0.5, clickable: true });
      ov.setMap(mapRef.current);
      overlaysRef.current.push(ov);
    });
    if (pts.length > 1) {
      try { const b = new kakao.maps.LatLngBounds(); pts.forEach(([la, lo]) => b.extend(new kakao.maps.LatLng(la, lo))); mapRef.current.setBounds(b, 40, 40, 40, 40); } catch { /* noop */ }
    }
  }, [items, center, onSelect, openInfo]);

  const present = new Set(items.map((i) => i.product));

  return (
    <div>
      <div className="mb-2 flex flex-wrap gap-2 text-[11px] text-[var(--text-secondary)]">
        {Object.keys(PRODUCT_LABEL).filter((k) => present.has(k)).map((k) => (
          <span key={k} className="flex items-center gap-1"><span className="h-2.5 w-2.5 rotate-45 rounded-[2px]" style={{ backgroundColor: PRODUCT_COLOR[k] }} />{PRODUCT_LABEL[k]}</span>
        ))}
        <span className="text-[var(--text-hint)]">· 반경 {radiusM / 1000}km · 마커 클릭 시 상세</span>
      </div>
      <div className="relative">
        <div ref={mapEl} className="w-full rounded-xl border border-[var(--line-strong)]" style={{ height: 380 }} />
        {!sdkReady && <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-black/30 text-sm font-bold text-white">지도 로딩…</div>}
        {sdkReady && items.length === 0 && <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-4 py-1.5 text-xs font-bold text-white">반경 내 분양 단지 없음</div>}
      </div>
    </div>
  );
}
