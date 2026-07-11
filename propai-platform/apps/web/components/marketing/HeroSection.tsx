"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import { HeroSkylineCanvas } from "./HeroSkylineCanvas";

/**
 * 히어로 — 720px 라운드 컨테이너 + 배경 영상(hero.mp4).
 *  • autoPlay muted loop playsInline + 마운트 후 play().catch 킥.
 *  • 잉크 스크림(하단 강 → 상단 약)으로 텍스트 대비 확보.
 *  • 영상 onError 또는 prefers-reduced-motion 시 절차 스카이라인 캔버스로 폴백.
 */
export function HeroSection({ locale }: { locale: string }) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [mode, setMode] = useState<"video" | "canvas">("video");
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const mq =
      typeof window.matchMedia === "function"
        ? window.matchMedia("(prefers-reduced-motion: reduce)")
        : null;
    if (mq?.matches) {
      // 마운트 시 외부 환경(모션 설정)과 1회 동기화 — 이 파일 다른 곳/코드베이스 관례와 동일.
      /* eslint-disable-next-line react-hooks/set-state-in-effect */
      setReducedMotion(true);
      setMode("canvas"); // 모션 감축 → 캔버스 정지 1프레임
      return;
    }
    const video = videoRef.current;
    if (video && typeof video.play === "function") {
      // 일부 브라우저는 autoPlay가 무시되므로 명시적으로 재생을 킥한다.
      try {
        const p = video.play();
        if (p && typeof p.catch === "function") {
          p.catch(() => setMode("canvas"));
        }
      } catch {
        // 재생 API 미지원(테스트 환경 등) — 폴백 캔버스로 전환
        setMode("canvas");
      }
    }
  }, []);

  return (
    <section className="mkt-section mkt-section--paper" style={{ paddingBlock: "clamp(40px, 5vw, 72px)" }}>
      <div className="mkt-container">
        <div
          className="mkt-reveal"
          style={{
            position: "relative",
            height: "clamp(520px, 78vh, 720px)",
            borderRadius: 24,
            overflow: "hidden",
            border: "1px solid var(--mkt-line)",
            background: "var(--mkt-ink)",
          }}
        >
          {mode === "video" ? (
            <video
              ref={videoRef}
              className="absolute inset-0 h-full w-full"
              style={{ objectFit: "cover" }}
              autoPlay
              muted
              loop
              playsInline
              preload="metadata"
              poster="/landing/hero-poster.webp"
              onError={() => setMode("canvas")}
              aria-hidden="true"
            >
              <source src="/landing/hero.mp4" type="video/mp4" />
            </video>
          ) : (
            <HeroSkylineCanvas animate={!reducedMotion} />
          )}

          {/* 잉크 스크림: 하단 0.6 → 상단 0.08 (단방향) */}
          <div
            aria-hidden="true"
            className="absolute inset-0"
            style={{
              background:
                "linear-gradient(to top, rgba(14,14,16,0.6) 0%, rgba(14,14,16,0.28) 42%, rgba(14,14,16,0.08) 100%)",
            }}
          />

          {/* 콘텐츠 */}
          <div
            className="absolute inset-0 flex flex-col justify-between"
            style={{ padding: "clamp(24px, 4vw, 56px)" }}
          >
            <div>
              <span className="mkt-label-pill" style={{ borderColor: "rgba(255,255,255,0.3)", color: "#fff" }}>
                <span className="mkt-glyph" style={{ color: "var(--mkt-accent-soft)" }}>
                  ✦
                </span>
                부동산개발 전주기 AI 플랫폼
              </span>
            </div>

            <div className="flex flex-col gap-6">
              <h1 className="mkt-display" style={{ color: "#fff", maxWidth: "16ch" }}>
                땅부터 준공까지,
                <br />
                AI로 사통팔땅!
              </h1>
              <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                <Link href={`/${locale}/precheck`} className="mkt-pill-btn mkt-pill-btn--light">
                  지금 필지 분석하기
                  <ArrowRight aria-hidden="true" className="mkt-arrow h-[18px] w-[18px]" />
                </Link>
                <p
                  className="mkt-body"
                  style={{ color: "rgba(255,255,255,0.82)", maxWidth: "42ch" }}
                >
                  주소 하나로 사전검토부터 수지분석·설계·인허가까지.
                </p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
