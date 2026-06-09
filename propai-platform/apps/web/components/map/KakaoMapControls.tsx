"use client";

/**
 * 카카오맵 공용 컨트롤 툴바 — 모든 카카오맵에 재사용.
 *
 * 기능: ①지도유형(일반/위성/하이브리드) ②지적편집도(용도지역 종별) 오버레이
 *      ③거리·면적 측정 ④로드뷰(거리뷰).
 *
 * 부모는 position:relative 래퍼 안의 지도 div와 함께 이 컴포넌트를 렌더하고,
 * 생성된 kakao 지도 인스턴스를 mapRef로, 준비완료를 ready로 전달한다.
 */

import { useEffect, useRef, useState } from "react";
import { toggleUseDistrict } from "@/lib/kakao-map";

/* eslint-disable @typescript-eslint/no-explicit-any */

type MapType = "ROADMAP" | "SKYVIEW" | "HYBRID";

const PYEONG = 3.305785;

export function KakaoMapControls({
  mapRef,
  ready,
}: {
  mapRef: { current: any };
  ready: boolean;
}) {
  const [mapType, setMapType] = useState<MapType>("ROADMAP");
  const [district, setDistrict] = useState(false);
  const [measure, setMeasure] = useState<null | "distance" | "area">(null);
  const [measureText, setMeasureText] = useState("");
  const [rvOn, setRvOn] = useState(false);

  const rvElRef = useRef<HTMLDivElement | null>(null);
  const rvRef = useRef<any>(null);

  // 측정 상태
  const pointsRef = useRef<any[]>([]);
  const lineRef = useRef<any>(null);
  const polyRef = useRef<any>(null);
  const dotsRef = useRef<any[]>([]);
  const clickLsnrRef = useRef<any>(null);

  // ── 지도유형 ──
  useEffect(() => {
    const kakao = (window as any).kakao;
    if (!ready || !mapRef.current || !kakao) return;
    try { mapRef.current.setMapTypeId(kakao.maps.MapTypeId[mapType]); } catch { /* noop */ }
  }, [mapType, ready, mapRef]);

  // ── 지적편집도(용도지역 종별) ──
  useEffect(() => {
    if (!ready || !mapRef.current) return;
    toggleUseDistrict((window as any).kakao, mapRef.current, district);
  }, [district, ready, mapRef]);

  // ── 거리·면적 측정 ──
  function clearMeasure() {
    const kakao = (window as any).kakao;
    const rm = (o: any) => { try { o?.setMap?.(null); } catch { /* noop */ } };
    rm(lineRef.current); lineRef.current = null;
    rm(polyRef.current); polyRef.current = null;
    dotsRef.current.forEach(rm); dotsRef.current = [];
    pointsRef.current = [];
    if (clickLsnrRef.current) {
      try { kakao.maps.event.removeListener(clickLsnrRef.current); } catch { /* noop */ }
      clickLsnrRef.current = null;
    }
    setMeasureText("");
  }

  useEffect(() => {
    const kakao = (window as any).kakao;
    if (!ready || !mapRef.current || !kakao) return;
    const map = mapRef.current;
    clearMeasure();
    if (!measure) {
      try { map.setCursor(""); map.setDoubleClickZoom(true); } catch { /* noop */ }
      return;
    }
    try { map.setCursor("crosshair"); map.setDoubleClickZoom(false); } catch { /* noop */ }

    const dotEl = () => {
      const d = document.createElement("div");
      d.style.cssText = "width:8px;height:8px;border-radius:50%;background:#ef4444;border:2px solid #fff;box-shadow:0 0 3px rgba(0,0,0,.4)";
      return d;
    };
    const onClick = (e: any) => {
      pointsRef.current.push(e.latLng);
      const pts = pointsRef.current;
      dotsRef.current.push(new kakao.maps.CustomOverlay({ map, position: e.latLng, content: dotEl(), xAnchor: 0.5, yAnchor: 0.5, zIndex: 5 }));
      if (measure === "distance") {
        if (lineRef.current) lineRef.current.setMap(null);
        lineRef.current = new kakao.maps.Polyline({ map, path: pts, strokeWeight: 3, strokeColor: "#ef4444", strokeOpacity: 0.95 });
        const len = Math.round(lineRef.current.getLength());
        setMeasureText(len >= 1000 ? `거리 ${(len / 1000).toFixed(2)} km (${len.toLocaleString()} m)` : `거리 ${len.toLocaleString()} m`);
      } else {
        if (polyRef.current) polyRef.current.setMap(null);
        if (pts.length >= 3) {
          polyRef.current = new kakao.maps.Polygon({ map, path: pts, strokeWeight: 2, strokeColor: "#ef4444", strokeOpacity: 0.9, fillColor: "#ef4444", fillOpacity: 0.18 });
          const area = Math.round(polyRef.current.getArea());
          setMeasureText(`면적 ${area.toLocaleString()} ㎡ (${Math.round(area / PYEONG).toLocaleString()} 평)`);
        } else {
          setMeasureText("면적: 점을 3개 이상 찍으세요");
        }
      }
    };
    clickLsnrRef.current = kakao.maps.event.addListener(map, "click", onClick);
    return () => { try { kakao.maps.event.removeListener(clickLsnrRef.current); } catch { /* noop */ } };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measure, ready, mapRef]);

  // ── 로드뷰 ──
  useEffect(() => {
    const kakao = (window as any).kakao;
    if (!ready || !mapRef.current || !kakao) return;
    if (!rvOn) return;
    const center = mapRef.current.getCenter();
    if (!rvRef.current && rvElRef.current) rvRef.current = new kakao.maps.Roadview(rvElRef.current);
    try {
      new kakao.maps.RoadviewClient().getNearestPanoId(center, 100, (panoId: any) => {
        if (panoId && rvRef.current) {
          rvRef.current.setPanoId(panoId, center);
          setTimeout(() => { try { rvRef.current.relayout(); } catch { /* noop */ } }, 80);
        } else {
          setRvOn(false);
          // eslint-disable-next-line no-alert
          alert("이 위치 주변의 로드뷰가 없습니다.");
        }
      });
    } catch { setRvOn(false); }
  }, [rvOn, ready, mapRef]);

  if (!ready) return null;

  const btn = (active: boolean) =>
    `px-2 py-1 text-[11px] font-bold rounded-md transition-colors ${active ? "bg-[var(--accent-strong)] text-white" : "bg-white/90 text-slate-700 hover:bg-white"}`;

  return (
    <>
      {/* 우상단 툴바 */}
      <div className="absolute right-2 top-2 z-[450] flex flex-col items-end gap-1">
        <div className="flex overflow-hidden rounded-md border border-black/10 shadow-sm">
          {(["ROADMAP", "SKYVIEW", "HYBRID"] as MapType[]).map((t) => (
            <button key={t} type="button" onClick={() => setMapType(t)} className={btn(mapType === t)}>
              {t === "ROADMAP" ? "일반" : t === "SKYVIEW" ? "위성" : "하이브리드"}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          <button type="button" onClick={() => setDistrict((v) => !v)} className={`${btn(district)} border border-black/10 shadow-sm`}>
            지적편집도
          </button>
          <button type="button" onClick={() => { setRvOn((v) => !v); }} className={`${btn(rvOn)} border border-black/10 shadow-sm`}>
            로드뷰
          </button>
        </div>
        <div className="flex gap-1">
          <button type="button" onClick={() => setMeasure((m) => (m === "distance" ? null : "distance"))} className={`${btn(measure === "distance")} border border-black/10 shadow-sm`}>
            거리측정
          </button>
          <button type="button" onClick={() => setMeasure((m) => (m === "area" ? null : "area"))} className={`${btn(measure === "area")} border border-black/10 shadow-sm`}>
            면적측정
          </button>
          {measure && (
            <button type="button" onClick={clearMeasure} className={`${btn(false)} border border-black/10 shadow-sm`}>
              지우기
            </button>
          )}
        </div>
      </div>

      {/* 측정 결과 라벨 */}
      {measure && (
        <div className="absolute left-2 top-2 z-[450] rounded-md bg-black/70 px-3 py-1.5 text-[11px] font-bold text-white">
          {measureText || (measure === "distance" ? "지도를 클릭해 거리 측정" : "지도를 클릭해 면적 측정")}
        </div>
      )}

      {/* 로드뷰 오버레이 + 닫기 */}
      <div ref={rvElRef} className={`absolute inset-0 z-[440] rounded-xl overflow-hidden ${rvOn ? "" : "hidden"}`} />
      {rvOn && (
        <button type="button" onClick={() => setRvOn(false)} className="absolute right-2 top-2 z-[460] rounded-md bg-black/70 px-2 py-1 text-[11px] font-bold text-white">
          ✕ 지도로
        </button>
      )}
    </>
  );
}

export default KakaoMapControls;
