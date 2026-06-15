"use client";

/**
 * 프로젝트 주변 분양 지도 — 관심지역 모니터링용.
 * 선택한 프로젝트의 중심 좌표 기준 반경 내 분양 단지를 '유형별 색상' 마커로 표시하고,
 * 마커 클릭 시 onSelect(item) → 상세(청약일정·분양가·공고링크) 모달을 연다.
 * 지도 엔진: 카카오맵 JS SDK(loadKakaoMap 재사용).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { loadKakaoMap } from "@/lib/kakao-map";
import { useMapFullscreen } from "@/hooks/useMapFullscreen";

/* eslint-disable @typescript-eslint/no-explicit-any */
declare global { interface Window { kakao: any } }

export type PresaleMarker = {
  house_manage_no: string; pblanc_no: string; name: string; address: string;
  area_name: string; product: string; product_label: string; status: string;
  receipt_begin: string; receipt_end: string; total_households: string;
  url: string; lat: number; lon: number; distance_m: number;
};

// 상태별 색상(분양중/분양예정/분양완료) — 지도 마커 구분.
const STATUS_COLOR: Record<string, string> = {
  접수중: "#10b981", 접수예정: "#3b82f6", 마감: "#94a3b8", 미정: "#f59e0b",
};
const STATUS_LABEL: Record<string, string> = {
  접수중: "분양중", 접수예정: "분양예정", 마감: "분양완료", 미정: "미정",
};
const STATUS_ORDER = ["접수중", "접수예정", "마감", "미정"];

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
  const fs = useMapFullscreen(mapRef);
  const [sdkReady, setSdkReady] = useState(false);
  // 상태 필터(분양중/분양예정/분양완료) — 기본 모두 표시.
  const [active, setActive] = useState<Set<string>>(new Set(STATUS_ORDER));

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
      const st = it.status || "미정";
      if (!active.has(st)) return; // 상태 필터(분양중/예정/완료)
      pts.push([it.lat, it.lon]);
      const col = STATUS_COLOR[st] || "#64748b";
      const stLabel = STATUS_LABEL[st] || st;
      const html = `<div style="min-width:190px;max-width:250px;font-family:sans-serif;">
          <div style="font-weight:700;font-size:13px;color:#0f172a;">${it.name}</div>
          <div style="font-size:11px;margin:2px 0 4px;"><b style="color:${col};">${stLabel}</b> <span style="color:#64748b;">· ${it.product_label}</span></div>
          <div style="font-size:11px;color:#475569;">접수 ${it.receipt_begin || "-"} ~ ${it.receipt_end || "-"}</div>
          <div style="font-size:11px;color:#475569;">공급 ${it.total_households || "-"}세대 · ${Math.round((it.distance_m || 0) / 100) / 10}km</div>
          <div style="margin-top:5px;font-size:11px;color:#2563eb;font-weight:700;cursor:pointer;">상세 보기(청약일정·분양가) ↗</div>
        </div>`;
      const dot = document.createElement("div");
      const op = st === "마감" ? 0.6 : 0.95; // 분양완료는 약하게
      dot.style.cssText = `width:16px;height:16px;border-radius:4px;background:${col};border:2px solid #fff;opacity:${op};cursor:pointer;box-shadow:0 0 4px rgba(0,0,0,.35);transform:rotate(45deg)`;
      const pos = new kakao.maps.LatLng(it.lat, it.lon);
      dot.onclick = () => { openInfo(pos, html); onSelect(it); };
      const ov = new kakao.maps.CustomOverlay({ position: pos, content: dot, xAnchor: 0.5, yAnchor: 0.5, clickable: true });
      ov.setMap(mapRef.current);
      overlaysRef.current.push(ov);
    });
    if (pts.length > 1) {
      try { const b = new kakao.maps.LatLngBounds(); pts.forEach(([la, lo]) => b.extend(new kakao.maps.LatLng(la, lo))); mapRef.current.setBounds(b, 40, 40, 40, 40); } catch { /* noop */ }
    }
  }, [items, center, onSelect, openInfo, active]);

  // 상태별 건수 + 토글
  const counts = STATUS_ORDER.reduce((m, s) => { m[s] = items.filter((i) => (i.status || "미정") === s).length; return m; }, {} as Record<string, number>);
  const toggle = (s: string) => setActive((prev) => { const n = new Set(prev); if (n.has(s)) n.delete(s); else n.add(s); return n; });

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[11px]">
        {STATUS_ORDER.filter((s) => s !== "미정" || counts["미정"] > 0).map((s) => (
          <button key={s} onClick={() => toggle(s)}
            className={`flex items-center gap-1 rounded-full border px-2.5 py-1 font-bold transition-all ${active.has(s) ? "border-transparent text-white" : "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-hint)] line-through opacity-60"}`}
            style={active.has(s) ? { backgroundColor: STATUS_COLOR[s] } : undefined}>
            <span className="h-2 w-2 rotate-45 rounded-[2px]" style={{ backgroundColor: STATUS_COLOR[s] }} />
            {STATUS_LABEL[s]} {counts[s] || 0}
          </button>
        ))}
        <span className="text-[var(--text-hint)]">· 반경 {radiusM / 1000}km · 마커 클릭 시 상세</span>
      </div>
      <div ref={fs.wrapperRef} className={fs.wrapperClass("relative flex flex-col")}>
        <div
          ref={mapEl}
          className={fs.mapClass("w-full rounded-xl border border-[var(--line-strong)]")}
          style={fs.isFull ? undefined : { height: 380 }}
        />
        {/* 풀스크린 토글 — KakaoMapControls 미사용 단독 지도라 버튼 직접 배치 */}
        {sdkReady && (
          <button
            type="button"
            onClick={fs.toggle}
            aria-label={fs.isFull ? "원래 크기로" : "전체화면"}
            className="absolute right-2 top-2 z-[470] flex h-9 w-9 items-center justify-center rounded-md border border-black/10 bg-white text-slate-700 shadow transition-colors hover:bg-slate-100"
          >
            {fs.isFull ? (
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 3v3a3 3 0 0 1-3 3H3M21 9h-3a3 3 0 0 1-3-3V3M3 15h3a3 3 0 0 1 3 3v3M15 21v-3a3 3 0 0 1 3-3h3" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />
              </svg>
            )}
          </button>
        )}
        {!sdkReady && <div className="absolute inset-0 flex items-center justify-center rounded-xl bg-black/30 text-sm font-bold text-white">지도 로딩…</div>}
        {sdkReady && items.length === 0 && <div className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full bg-black/60 px-4 py-1.5 text-xs font-bold text-white">반경 내 분양 단지 없음</div>}
      </div>
    </div>
  );
}
