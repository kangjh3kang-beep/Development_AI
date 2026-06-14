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
 * - 토글 시 카카오맵 `relayout()`을 호출해 새 크기를 반영(필수).
 * - 풀스크린 동안 body 스크롤 잠금.
 * - ESC 키로 해제.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type MapFullscreen = {
  isFull: boolean;
  toggle: () => void;
  enter: () => void;
  exit: () => void;
  /** 지도 래퍼(부모 relative)에 입힐 클래스 — 풀스크린 시 화면 전체 오버레이. */
  wrapperClass: (base?: string) => string;
  /** 지도 div에 입힐 클래스 — 풀스크린 시 높이를 화면 전체로. */
  mapClass: (base?: string) => string;
};

export function useMapFullscreen(mapRef: { current: any }): MapFullscreen {
  const [isFull, setIsFull] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 토글 직후 카카오맵 크기 재계산(relayout). 레이아웃 전환이 페인트된 뒤
  // 호출해야 하므로 약간의 지연을 둔다. 직전 예약 타이머는 정리(언마운트 누수 방지).
  const relayoutSoon = useCallback(() => {
    const map = mapRef.current;
    if (!map?.relayout) return;
    const center = map.getCenter?.();
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => {
      try {
        map.relayout();
        if (center) map.setCenter(center);
      } catch {
        /* noop */
      }
    }, 80);
  }, [mapRef]);

  // 언마운트 시 예약된 relayout 타이머 정리.
  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  const enter = useCallback(() => { setIsFull(true); relayoutSoon(); }, [relayoutSoon]);
  const exit = useCallback(() => { setIsFull(false); relayoutSoon(); }, [relayoutSoon]);
  const toggle = useCallback(() => { setIsFull((v) => !v); relayoutSoon(); }, [relayoutSoon]);

  // 풀스크린 동안: body 스크롤 잠금 + ESC 해제.
  useEffect(() => {
    if (!isFull) return;
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
  }, [isFull, relayoutSoon]);

  const wrapperClass = useCallback(
    (base = "") =>
      isFull
        ? `${base} fixed inset-0 z-[100] m-0 bg-[var(--surface-base,#0b0e14)] p-3 sm:p-4`
        : base,
    [isFull],
  );

  const mapClass = useCallback(
    (base = "") => (isFull ? `${base} !h-full flex-1` : base),
    [isFull],
  );

  return { isFull, toggle, enter, exit, wrapperClass, mapClass };
}
