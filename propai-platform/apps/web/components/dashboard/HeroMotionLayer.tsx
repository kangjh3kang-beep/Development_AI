"use client";

import { useEffect, useRef, useState } from "react";

import { HeroSkylineCanvas } from "@/components/marketing/HeroSkylineCanvas";

/**
 * 로그인 홈(DashboardHome) hero 카드용 도시건축 배경 애니메이션 — 절대배치 배경 레이어.
 *  • 기본: 배경 영상(hero.mp4) autoPlay muted loop playsInline + 마운트 후 play().catch 킥.
 *  • 영상 onError 또는 prefers-reduced-motion 시 절차 생성 스카이라인 캔버스로 폴백
 *    (HeroSkylineCanvas 재사용 — 마케팅 랜딩과 동일 자산).
 *  • 텍스트 대비 스크림은 호출측(hero 카드)이 위에 얹는다(이 컴포넌트는 순수 배경).
 */
export function HeroMotionLayer() {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [mode, setMode] = useState<"video" | "canvas">("video");
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const mq =
      typeof window.matchMedia === "function"
        ? window.matchMedia("(prefers-reduced-motion: reduce)")
        : null;
    if (mq?.matches) {
      // 모션 감축 설정 → 정지 1프레임 스카이라인.
      /* eslint-disable-next-line react-hooks/set-state-in-effect */
      setReduced(true);
      setMode("canvas");
      return;
    }
    const video = videoRef.current;
    if (video && typeof video.play === "function") {
      try {
        const p = video.play();
        if (p && typeof p.catch === "function") {
          p.catch(() => setMode("canvas")); // 자동재생 차단 → 캔버스 폴백
        }
      } catch {
        setMode("canvas"); // 재생 API 미지원(테스트 등)
      }
    }
  }, []);

  if (mode === "canvas") {
    return (
      <div aria-hidden="true" className="absolute inset-0">
        <HeroSkylineCanvas animate={!reduced} />
      </div>
    );
  }

  return (
    <video
      ref={videoRef}
      aria-hidden="true"
      className="absolute inset-0 h-full w-full"
      style={{ objectFit: "cover" }}
      autoPlay
      muted
      loop
      playsInline
      preload="metadata"
      poster="/landing/hero-poster.webp"
      onError={() => setMode("canvas")}
    >
      <source src="/landing/hero.mp4" type="video/mp4" />
    </video>
  );
}
