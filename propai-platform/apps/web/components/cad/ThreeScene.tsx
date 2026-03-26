"use client";

import { useEffect, useRef, useState } from "react";

const LOADING_TEXT = "Loading 3D scene...";
const ERROR_TEXT = "Canvas rendering is not available in this browser.";

function drawPreview(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
  frame: number,
) {
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#eef5ff";
  context.fillRect(0, 0, width, height);

  const towerWidth = Math.max(120, width * 0.18);
  const towerHeight = Math.max(220, height * 0.52);
  const towerX = width / 2 - towerWidth / 2;
  const towerY = height / 2 - towerHeight / 2;
  const accentOffset = Math.sin(frame / 18) * 8;

  context.fillStyle = "#13212f";
  context.fillRect(towerX, towerY, towerWidth, towerHeight);

  context.fillStyle = "#2a5b84";
  context.fillRect(towerX + 14, towerY + 16, towerWidth - 28, towerHeight - 32);

  context.fillStyle = "#f8fbff";
  for (let row = 0; row < 7; row += 1) {
    for (let col = 0; col < 3; col += 1) {
      context.fillRect(
        towerX + 24 + col * ((towerWidth - 60) / 2),
        towerY + 28 + row * ((towerHeight - 70) / 6),
        22,
        16,
      );
    }
  }

  context.fillStyle = "#d97706";
  context.beginPath();
  context.arc(width * 0.24 + accentOffset, height * 0.28, 18, 0, Math.PI * 2);
  context.fill();

  context.fillStyle = "#0e7490";
  context.beginPath();
  context.arc(width * 0.76 - accentOffset, height * 0.68, 14, 0, Math.PI * 2);
  context.fill();

  context.strokeStyle = "rgba(19,33,47,0.14)";
  context.lineWidth = 1;
  for (let line = 0; line < 6; line += 1) {
    const y = height - 24 - line * 22;
    context.beginPath();
    context.moveTo(24, y);
    context.lineTo(width - 24, y);
    context.stroke();
  }

  context.fillStyle = "rgba(19,33,47,0.84)";
  context.font = "600 14px sans-serif";
  context.fillText("PropAI CAD preview", 24, 34);
}

export default function ThreeScene() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const frameRef = useRef(0);
  const animationFrameRef = useRef<number | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !canvasRef.current) {
      return;
    }

    const canvas = canvasRef.current;
    const context = canvas.getContext("2d");

    if (!context) {
      const errorTimer = window.setTimeout(() => {
        setError(ERROR_TEXT);
        setIsLoading(false);
      }, 0);

      return () => {
        window.clearTimeout(errorTimer);
      };
    }

    const paint = () => {
      const width = canvas.clientWidth || 800;
      const height = canvas.clientHeight || 500;

      canvas.width = width;
      canvas.height = height;
      drawPreview(context, width, height, frameRef.current);
    };

    const tick = () => {
      frameRef.current += 1;
      paint();
      setIsLoading(false);
      animationFrameRef.current = window.requestAnimationFrame(tick);
    };

    const handleResize = () => {
      paint();
    };

    paint();
    animationFrameRef.current = window.requestAnimationFrame(tick);
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);

      if (animationFrameRef.current !== null) {
        window.cancelAnimationFrame(animationFrameRef.current);
      }
    };
  }, []);

  return (
    <div className="relative h-[500px] w-full overflow-hidden rounded-xl border border-slate-200 bg-slate-50 shadow-md">
      {isLoading ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-100/90">
          <p className="text-base font-semibold text-slate-700">{LOADING_TEXT}</p>
        </div>
      ) : null}
      {error ? (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-100/95 px-6 text-center">
          <p className="text-sm font-medium text-[var(--spot)]">{error}</p>
        </div>
      ) : null}
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}
