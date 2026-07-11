"use client";

import { useEffect, useRef } from "react";

/**
 * 히어로 영상 폴백 — 절차 생성 스카이라인 애니메이션.
 * 비디오 onError 또는 prefers-reduced-motion 시 노출된다.
 *  • 시드 고정(결정론) — 매 렌더 동일한 스카이라인.
 *  • animate=true: 26초 루프(건물 층별 상승 + 창 점등 + 크레인 회전), rAF.
 *  • animate=false: 정지 1프레임(최종 상태)만 그린다.
 *  • unmount 시 rAF 정리.
 */

// 결정론 PRNG(mulberry32) — 시드 고정으로 항상 같은 결과.
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const LOOP_MS = 26000;
const SEED = 20260712;

type Building = {
  x: number;
  w: number;
  h: number; // 최종 높이(0~1, 캔버스 높이 기준 비율)
  cols: number;
  rows: number;
  delay: number; // 상승 시작 지연(0~1)
  lit: number[]; // 창별 점등 임계값(0~1)
};

export function HeroSkylineCanvas({ animate = true }: { animate?: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return; // jsdom 등 컨텍스트 미지원 환경 방어

    let raf = 0;
    let disposed = false;
    let dpr = 1;
    let W = 0;
    let H = 0;
    let buildings: Building[] = [];

    function build() {
      const rect = canvas!.getBoundingClientRect();
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      W = Math.max(1, Math.floor(rect.width));
      H = Math.max(1, Math.floor(rect.height));
      canvas!.width = Math.floor(W * dpr);
      canvas!.height = Math.floor(H * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);

      // 스카이라인 재구성(시드 고정이라 결과 동일)
      const local = mulberry32(SEED);
      buildings = [];
      let x = -20;
      while (x < W + 40) {
        const w = 44 + Math.floor(local() * 70);
        const h = 0.28 + local() * 0.5;
        const cols = Math.max(2, Math.floor(w / 16));
        const rows = Math.max(4, Math.floor((h * H) / 22));
        const lit: number[] = [];
        for (let i = 0; i < cols * rows; i += 1) {
          lit.push(0.25 + local() * 0.7);
        }
        buildings.push({
          x,
          w,
          h,
          cols,
          rows,
          delay: local() * 0.35,
          lit,
        });
        x += w + 10 + Math.floor(local() * 18);
      }
    }

    function ease(t: number): number {
      return t < 0 ? 0 : t > 1 ? 1 : 1 - Math.pow(1 - t, 3);
    }

    function draw(now: number) {
      // 루프 진행도 0~1
      const p = animate ? (now % LOOP_MS) / LOOP_MS : 1;
      // 상승 페이즈(앞 55%), 이후 유지
      const risePhase = Math.min(1, p / 0.55);

      // 골드 아워 하늘
      const sky = ctx!.createLinearGradient(0, 0, 0, H);
      sky.addColorStop(0, "#1a1206");
      sky.addColorStop(0.42, "#5a3d16");
      sky.addColorStop(0.72, "#b17a34");
      sky.addColorStop(1, "#e8c79a");
      ctx!.fillStyle = sky;
      ctx!.fillRect(0, 0, W, H);

      // 태양 글로우
      const glow = ctx!.createRadialGradient(W * 0.72, H * 0.82, 0, W * 0.72, H * 0.82, H * 0.7);
      glow.addColorStop(0, "rgba(255, 214, 150, 0.55)");
      glow.addColorStop(1, "rgba(255, 214, 150, 0)");
      ctx!.fillStyle = glow;
      ctx!.fillRect(0, 0, W, H);

      // 건물(뒤→앞, 실루엣)
      for (let b = 0; b < buildings.length; b += 1) {
        const bd = buildings[b];
        const local = ease((risePhase - bd.delay) / (1 - bd.delay));
        const bh = bd.h * H * local;
        const by = H - bh;
        // 실루엣
        ctx!.fillStyle = "rgba(14, 14, 16, 0.92)";
        ctx!.fillRect(bd.x, by, bd.w, bh);

        // 창 점등(상승 완료 비율에 비례)
        if (bh > 20) {
          const cellW = bd.w / bd.cols;
          const cellH = 22;
          const visibleRows = Math.floor(bh / cellH);
          for (let r = 0; r < visibleRows; r += 1) {
            for (let c = 0; c < bd.cols; c += 1) {
              const idx = (r * bd.cols + c) % bd.lit.length;
              const threshold = bd.lit[idx];
              const on = p * 1.15 > threshold;
              if (!on) continue;
              const flick = 0.6 + 0.4 * Math.sin((now / 900 + idx) * 1.3);
              ctx!.fillStyle = `rgba(255, 205, 130, ${0.35 + 0.4 * flick})`;
              const wx = bd.x + c * cellW + cellW * 0.28;
              const wy = by + r * cellH + 6;
              ctx!.fillRect(wx, wy, cellW * 0.44, 9);
            }
          }
        }
      }

      // 크레인(전경, 미세 회전)
      const craneX = W * 0.2;
      const craneBase = H;
      const craneTop = H * 0.24;
      ctx!.strokeStyle = "rgba(14, 14, 16, 0.95)";
      ctx!.lineWidth = 3;
      ctx!.beginPath();
      ctx!.moveTo(craneX, craneBase);
      ctx!.lineTo(craneX, craneTop);
      ctx!.stroke();
      const swing = animate ? Math.sin((p * Math.PI * 2)) * 0.08 : 0.04;
      const jibLen = W * 0.22;
      const jx = craneX + Math.cos(swing) * jibLen;
      const jy = craneTop + Math.sin(swing) * jibLen;
      const cx = craneX - Math.cos(swing) * jibLen * 0.4;
      const cy = craneTop - Math.sin(swing) * jibLen * 0.4;
      ctx!.beginPath();
      ctx!.moveTo(cx, cy);
      ctx!.lineTo(jx, jy);
      ctx!.stroke();
      // 후크 라인
      ctx!.lineWidth = 1.5;
      const hookDrop = animate ? (0.3 + 0.25 * Math.sin(p * Math.PI * 2)) : 0.4;
      ctx!.beginPath();
      ctx!.moveTo(jx, jy);
      ctx!.lineTo(jx, jy + (craneBase - jy) * hookDrop);
      ctx!.stroke();

      if (animate && !disposed) {
        raf = requestAnimationFrame(draw);
      }
    }

    build();
    if (animate) {
      raf = requestAnimationFrame(draw);
    } else {
      draw(0); // 정지 1프레임
    }

    const onResize = () => {
      build();
      if (!animate) draw(0);
    };
    window.addEventListener("resize", onResize);

    return () => {
      disposed = true;
      if (raf) cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
    };
  }, [animate]);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="absolute inset-0 h-full w-full"
    />
  );
}
