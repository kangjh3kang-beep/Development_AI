"use client";

/**
 * 카카오맵 풀스크린 토글 공용 훅.
 *
 * 카카오맵은 DOM을 다른 컨테이너로 옮기거나 재마운트하면 InfoWindow/오버레이
 * 재init 문제가 생긴다. 그래서 지도 DOM은 그대로 두고, 지도 컨테이너(래퍼)에
 * CSS `fixed inset-0 z-[100]` 클래스만 입혀 화면 전체로 키운다.
 *
 * 사용법:
 *   const fs = useMapFullscreen(mapRef);
 *   <div className={fs.wrapperClass("relative")}>
 *     <div ref={mapEl} className={fs.mapClass("h-[340px] ...")} />
 *     <MapFullscreenButton fs={fs} />   // 또는 fs.toggle() 직접 호출
 *   </div>
 *
 * - 토글 시 지도 엔진별로 크기를 재계산한다(필수):
 *     · 카카오맵: `relayout()` + `setCenter()` (중심 보정 필요)
 *     · Leaflet:  `invalidateSize()` (중심 자동 유지)
 *   둘 중 인스턴스에 존재하는 메서드를 호출한다(카카오·Leaflet 양립).
 * - 풀스크린 동안 body 스크롤 잠금.
 * - ESC 키로 해제.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type MapFullscreen = {
  isFull: boolean;
  toggle: () => void;
  enter: () => void;
  exit: () => void;
  /** 풀스크린 대상 래퍼 ref — 이 div에 attach. 네이티브 Fullscreen API가 이 요소를 전체화면화한다. */
  wrapperRef: { current: HTMLDivElement | null };
  /** 지도 래퍼(부모 relative)에 입힐 클래스 — 풀스크린 시 화면 전체 오버레이. */
  wrapperClass: (base?: string) => string;
  /** 지도 div에 입힐 클래스 — 풀스크린 시 높이를 화면 전체로. */
  mapClass: (base?: string) => string;
};

export type MapFullscreenOptions = {
  /** Native fullscreen can detach Leaflet DOM in some embedded surfaces. Use "css" to keep the map in-place. */
  mode?: "native" | "css";
};

const POSITION_CLASS_NAMES = new Set(["static", "fixed", "absolute", "relative", "sticky"]);

function withoutPositionClass(base: string): string {
  return base
    .split(/\s+/)
    .filter((className) => className && !POSITION_CLASS_NAMES.has(className))
    .join(" ");
}

export function useMapFullscreen(mapRef: { current: any }, options: MapFullscreenOptions = {}): MapFullscreen {
  const [isFull, setIsFull] = useState(false);
  // nativeFs=true면 브라우저 네이티브 Fullscreen API로 전체화면(상위 transform/backdrop-filter가
  // position:fixed를 클리핑하는 버그를 원천 회피 — 진짜 뷰포트 전체). 실패 시 CSS 오버레이 폴백.
  const [nativeFs, setNativeFs] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 토글 직후 지도 크기 재계산. 레이아웃 전환이 페인트된 뒤 호출해야 하므로
  // 약간의 지연을 둔다. 직전 예약 타이머는 정리(언마운트 누수 방지).
  // 카카오맵(relayout)과 Leaflet(invalidateSize) 둘 다 지원 — 존재하는 메서드만 호출.
  const relayoutSoon = useCallback(() => {
    const map = mapRef.current;
    if (!map) return;
    if (!map.relayout && !map.invalidateSize) return;
    // 카카오는 relayout 후 중심이 틀어질 수 있어 미리 중심을 잡아둔다.
    const center = map.relayout ? map.getCenter?.() : undefined;
    if (timerRef.current) clearTimeout(timerRef.current);
    const relayout = () => {
      try {
        if (map.relayout) {
          // 카카오맵: 재배치 후 중심 보정
          map.relayout();
          if (center) map.setCenter(center);
        } else if (map.invalidateSize) {
          // Leaflet: 컨테이너 크기 재인식(중심은 자동 유지)
          map.invalidateSize({ pan: false, debounceMoveend: false });
          map.eachLayer?.((layer: { redraw?: () => void }) => {
            try { layer.redraw?.(); } catch { /* noop */ }
          });
        }
      } catch {
        /* noop */
      }
    };
    if (typeof window !== "undefined") {
      window.requestAnimationFrame(() => {
        relayout();
        window.requestAnimationFrame(relayout);
      });
    }
    timerRef.current = setTimeout(relayout, 80);
    window.setTimeout(relayout, 260);
    window.setTimeout(relayout, 640);
  }, [mapRef]);

  // 언마운트 시 예약된 relayout 타이머 정리.
  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  // enter: 네이티브 Fullscreen API 우선(상위 transform 클리핑 회피). 미지원/실패 시 CSS 오버레이 폴백.
  const enter = useCallback(() => {
    const el = wrapperRef.current;
    const req = el && (el.requestFullscreen || (el as any).webkitRequestFullscreen);
    if (options.mode !== "css" && el && req) {
      Promise.resolve(req.call(el)).then(() => setNativeFs(true)).catch(() => {
        setNativeFs(false); setIsFull(true); relayoutSoon();
      });
    } else {
      setNativeFs(false); setIsFull(true); relayoutSoon();
    }
  }, [options.mode, relayoutSoon]);

  const exit = useCallback(() => {
    if (document.fullscreenElement) {
      Promise.resolve(document.exitFullscreen()).catch(() => {});
    }
    setNativeFs(false); setIsFull(false); relayoutSoon();
  }, [relayoutSoon]);

  const toggle = useCallback(() => {
    if (isFull || document.fullscreenElement) exit();
    else enter();
  }, [isFull, enter, exit]);

  // 네이티브 fullscreenchange 동기화 — 브라우저 UI(ESC·F11)로 해제돼도 상태 일치 + 지도 relayout.
  useEffect(() => {
    const onFsChange = () => {
      const on = !!document.fullscreenElement;
      setIsFull(on);
      setNativeFs(on);
      relayoutSoon();
    };
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, [relayoutSoon]);

  // CSS 폴백 오버레이 동안에만: body 스크롤 잠금 + ESC 해제(네이티브는 브라우저가 처리).
  useEffect(() => {
    if (!isFull || nativeFs) return;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setIsFull(false); relayoutSoon(); }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prevOverflow;
      window.removeEventListener("keydown", onKey);
    };
  }, [isFull, nativeFs, relayoutSoon]);

  const wrapperClass = useCallback(
    (base = "") => {
      const stableBase = withoutPositionClass(base);
      // 네이티브 풀스크린: 브라우저가 요소를 뷰포트 전체로 만들므로 채움(h/w-full)+배경+flex만.
      if (nativeFs) return `${stableBase} h-screen w-screen m-0 bg-[var(--background-deep)] p-3 sm:p-4 flex min-h-0 flex-col`;
      // CSS 폴백 오버레이.
      if (isFull) return `${stableBase} fixed inset-0 z-[9990] m-0 bg-[var(--background-deep)] p-3 sm:p-4 flex min-h-0 flex-col`;
      return base;
    },
    [isFull, nativeFs],
  );

  const mapClass = useCallback(
    (base = "") => (isFull || nativeFs ? `${base} !h-full min-h-0 flex-1` : base),
    [isFull, nativeFs],
  );

  return { isFull: isFull || nativeFs, toggle, enter, exit, wrapperRef, wrapperClass, mapClass };
}
