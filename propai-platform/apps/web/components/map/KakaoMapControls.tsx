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

import { useEffect, useRef, useState, type ReactNode } from "react";
import { toggleUseDistrict } from "@/lib/kakao-map";

/* eslint-disable @typescript-eslint/no-explicit-any */

type MapType = "ROADMAP" | "SKYVIEW" | "HYBRID";

const PYEONG = 3.305785;

/** 좌측 아이콘 버튼 — 롤오버(hover) 시 메뉴명 툴팁 표시. */
function IconBtn({
  active, onClick, label, children,
}: { active: boolean; onClick: () => void; label: string; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={`group relative flex h-9 w-9 items-center justify-center rounded-md border border-black/10 shadow transition-colors ${
        active ? "bg-[var(--accent-strong)] text-white" : "bg-white text-slate-700 hover:bg-slate-100"
      }`}
    >
      {children}
      {/* 우측 상단 배치 → 툴팁은 왼쪽으로 펼쳐 지도 밖으로 넘치지 않게 */}
      <span className="pointer-events-none absolute right-full mr-2 whitespace-nowrap rounded bg-black/80 px-2 py-1 text-[11px] font-semibold text-white opacity-0 shadow transition-opacity duration-150 group-hover:opacity-100">
        {label}
      </span>
    </button>
  );
}

export function KakaoMapControls({
  mapRef,
  ready,
  onFullscreen,
  isFullscreen,
}: {
  mapRef: { current: any };
  ready: boolean;
  /** 풀스크린 토글 콜백(미전달 시 버튼 미표시). useMapFullscreen.toggle 연결. */
  onFullscreen?: () => void;
  /** 현재 풀스크린 여부 — 아이콘/라벨(확대↔축소) 전환. */
  isFullscreen?: boolean;
}) {
  const [mapType, setMapType] = useState<MapType>("ROADMAP");
  const [district, setDistrict] = useState(false);
  const [measure, setMeasure] = useState<null | "distance" | "area">(null);
  const [measureText, setMeasureText] = useState("");
  const [rvOn, setRvOn] = useState(false);

  const rvElRef = useRef<HTMLDivElement | null>(null);
  const rvRef = useRef<any>(null);
  // 로드뷰 좌하단 위치 미니맵(PiP) — 현재 로드뷰 지점·시선방향을 작은 지도로 실시간 표시
  const rvMiniElRef = useRef<HTMLDivElement | null>(null);
  const rvMiniRef = useRef<any>(null);
  const rvMarkerRef = useRef<any>(null);

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

  // ── 로드뷰 + 좌하단 위치 미니맵(PiP) ──
  useEffect(() => {
    const kakao = (window as any).kakao;
    if (!ready || !mapRef.current || !kakao) return;
    if (!rvOn) return;
    const center = mapRef.current.getCenter();
    if (!rvRef.current && rvElRef.current) rvRef.current = new kakao.maps.Roadview(rvElRef.current);
    const rv = rvRef.current;

    // 시선방향 표시 마커: 가운데 점 + 위쪽 부채꼴(시선). wrap을 회전시켜 방향 표현.
    const wrap = document.createElement("div");
    wrap.style.cssText = "position:relative;width:30px;height:30px;transform-origin:50% 50%;transition:transform .12s linear";
    const cone = document.createElement("div");
    cone.style.cssText = "position:absolute;left:50%;top:-1px;transform:translateX(-50%);width:0;height:0;border-left:9px solid transparent;border-right:9px solid transparent;border-bottom:15px solid rgba(37,99,235,.55)";
    const dot = document.createElement("div");
    dot.style.cssText = "position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);width:11px;height:11px;border-radius:50%;background:#2563eb;border:2px solid #fff;box-shadow:0 0 3px rgba(0,0,0,.5)";
    wrap.appendChild(cone); wrap.appendChild(dot);

    const lsnrs: any[] = [];
    try {
      new kakao.maps.RoadviewClient().getNearestPanoId(center, 100, (panoId: any) => {
        if (!panoId || !rv) {
          setRvOn(false);
          // eslint-disable-next-line no-alert
          alert("이 위치 주변의 로드뷰가 없습니다.");
          return;
        }
        rv.setPanoId(panoId, center);
        setTimeout(() => { try { rv.relayout(); } catch { /* noop */ } }, 80);

        // 미니맵 생성(최초 1회) + 마커 부착
        if (rvMiniElRef.current && !rvMiniRef.current) {
          rvMiniRef.current = new kakao.maps.Map(rvMiniElRef.current, { center, level: 3, draggable: false, disableDoubleClickZoom: true });
          try { rvMiniRef.current.setZoomable(false); } catch { /* noop */ }
        }
        const mini = rvMiniRef.current;
        if (mini) {
          rvMarkerRef.current = new kakao.maps.CustomOverlay({ map: mini, position: center, content: wrap, xAnchor: 0.5, yAnchor: 0.5, zIndex: 10 });
          setTimeout(() => { try { mini.relayout(); mini.setCenter(center); } catch { /* noop */ } }, 120);

          // 로드뷰 위치 이동 → 미니맵 중심·마커 동기화
          lsnrs.push(kakao.maps.event.addListener(rv, "position_changed", () => {
            try { const p = rv.getPosition(); mini.setCenter(p); rvMarkerRef.current?.setPosition(p); } catch { /* noop */ }
          }));
          // 시점(방위) 변경 → 부채꼴 회전(pan: 0=북, 시계방향)
          lsnrs.push(kakao.maps.event.addListener(rv, "viewpoint_changed", () => {
            try { wrap.style.transform = `rotate(${rv.getViewpoint().pan}deg)`; } catch { /* noop */ }
          }));
        }
      });
    } catch { setRvOn(false); }

    return () => {
      lsnrs.forEach((l) => { try { kakao.maps.event.removeListener(l); } catch { /* noop */ } });
      try { rvMarkerRef.current?.setMap(null); } catch { /* noop */ }
      rvMarkerRef.current = null;
    };
  }, [rvOn, ready, mapRef]);

  if (!ready) return null;

  const txtBtn = (active: boolean) =>
    `px-2.5 py-1 text-[11px] font-bold transition-colors ${active ? "bg-[var(--accent-strong)] text-white" : "bg-white/90 text-slate-700 hover:bg-white"}`;

  return (
    <>
      {/* 상단 우측: 지도유형 + 지적편집도 — 한 줄 가로로 연달아 */}
      {/* 우측 상단: 텍스트 컨트롤(한 줄) + 그 아래 세로 아이콘 메뉴
          로드뷰 진입 시에는 지도유형/지적편집도 토글이 '지도로' 닫기버튼과 겹치므로 숨긴다. */}
      <div className={`absolute right-2 top-2 z-[450] flex flex-col items-end gap-1.5 ${rvOn ? "hidden" : ""}`}>
        <div className="flex items-center gap-1">
          <div className="flex overflow-hidden rounded-md border border-black/10 shadow-sm">
            {(["ROADMAP", "SKYVIEW", "HYBRID"] as MapType[]).map((t) => (
              <button key={t} type="button" onClick={() => setMapType(t)} className={txtBtn(mapType === t)}>
                {t === "ROADMAP" ? "일반" : t === "SKYVIEW" ? "위성" : "하이브리드"}
              </button>
            ))}
          </div>
          <button type="button" onClick={() => setDistrict((v) => !v)} className={`${txtBtn(district)} rounded-md border border-black/10 shadow-sm`}>
            지적편집도
          </button>
        </div>

        {/* 세로 아이콘 메뉴: 풀스크린·로드뷰·거리·면적 측정(롤오버 시 메뉴명 툴팁) */}
        <div className="flex flex-col items-end gap-1.5 rounded-lg bg-black/5 p-1 backdrop-blur-sm">
          {onFullscreen && (
            <IconBtn active={!!isFullscreen} onClick={onFullscreen} label={isFullscreen ? "원래 크기로" : "전체화면"}>
              {isFullscreen ? (
                /* 축소(나가기) — 안쪽으로 모이는 화살표 */
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M9 3v3a3 3 0 0 1-3 3H3M21 9h-3a3 3 0 0 1-3-3V3M3 15h3a3 3 0 0 1 3 3v3M15 21v-3a3 3 0 0 1 3-3h3" />
                </svg>
              ) : (
                /* 확대(전체화면) — 바깥으로 향하는 화살표 */
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3" />
                </svg>
              )}
            </IconBtn>
          )}
          <IconBtn active={rvOn} onClick={() => setRvOn((v) => !v)} label="로드뷰">
            {/* CCTV 카메라 */}
            <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M16.75 12h3.63a1 1 0 0 1 .9 1.45l-2.04 4.07a1 1 0 0 1-1.71.13l-2.12-2.97" />
              <path d="M17.1 9.05a1 1 0 0 1 .45 1.34l-3.11 6.21a1 1 0 0 1-1.34.45L3.6 12.3a2.92 2.92 0 0 1-1.3-3.91L3.7 5.6a2.92 2.92 0 0 1 3.92-1.3z" />
              <path d="M2 19h3.76a2 2 0 0 0 1.8-1.1L9 15" />
              <path d="M2 21v-4" />
              <circle cx="9" cy="9" r="2" />
            </svg>
          </IconBtn>
        <IconBtn active={measure === "distance"} onClick={() => setMeasure((m) => (m === "distance" ? null : "distance"))} label="거리측정">
          {/* 점-선-점(거리) */}
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="5" cy="19" r="2" fill="currentColor" /><circle cx="19" cy="5" r="2" fill="currentColor" /><path d="M6.5 17.5l11-11" strokeDasharray="3 2.5" />
          </svg>
        </IconBtn>
        <IconBtn active={measure === "area"} onClick={() => setMeasure((m) => (m === "area" ? null : "area"))} label="면적측정">
          {/* 다각형(면적) */}
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
            <polygon points="4,8 12,3 20,9 16,20 7,19" />
          </svg>
        </IconBtn>
          {measure && (
            <IconBtn active={false} onClick={clearMeasure} label="지우기">
              {/* 휴지통 */}
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13" />
              </svg>
            </IconBtn>
          )}
        </div>
      </div>

      {/* 측정 결과 라벨(하단 좌측) */}
      {measure && (
        <div className="absolute bottom-2 left-2 z-[450] rounded-md bg-black/70 px-3 py-1.5 text-[11px] font-bold text-white">
          {measureText || (measure === "distance" ? "지도를 클릭해 거리 측정" : "지도를 클릭해 면적 측정")}
        </div>
      )}

      {/* 로드뷰 오버레이 + 닫기 + 좌하단 위치 미니맵 */}
      <div ref={rvElRef} className={`absolute inset-0 z-[455] overflow-hidden rounded-xl ${rvOn ? "" : "hidden"}`} />
      {rvOn && (
        <button type="button" onClick={() => setRvOn(false)} className="absolute right-2 top-2 z-[470] rounded-md bg-black/70 px-2.5 py-1 text-[11px] font-bold text-white shadow-md hover:bg-black/85">
          ✕ 지도로
        </button>
      )}
      {/* 좌하단 위치 미니맵(PiP): 현재 로드뷰 지점·시선방향 실시간 표시 */}
      <div className={`absolute bottom-2 left-2 z-[465] ${rvOn ? "" : "hidden"}`}>
        <div className="overflow-hidden rounded-lg border-2 border-white/80 shadow-lg" style={{ width: 150, height: 110 }}>
          <div ref={rvMiniElRef} className="h-full w-full bg-slate-200" />
        </div>
        <div className="mt-0.5 text-center text-[9px] font-bold text-white drop-shadow">현재 위치</div>
      </div>
    </>
  );
}

export default KakaoMapControls;
