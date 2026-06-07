"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useCadStore } from "@/store/use-cad-store";

export function DrawingAnalysisPanel() {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const setAnalysis = useCadStore((s) => s.setAnalysis);
  const resetCanvas = useCadStore((s) => s.resetCanvas);
  
  const [analysisResult, setAnalysisResult] = useState<{
    score: number;
    issues: Array<{ id: string; type: string; desc: string; severity: "high" | "med" | "low" }>;
  } | null>(null);

  const points = useCadStore((s) => s.points);
  const polygons = useCadStore((s) => s.polygons);
  const rects = useCadStore((s) => s.rects);
  const cadScale = useCadStore((s) => s.scale);
  const floorCount = useCadStore((s) => s.floorCount);
  const buildingHeightM = useCadStore((s) => s.buildingHeightM);

  const startAnalysis = () => {
    setIsAnalyzing(true);
    setAnalysisResult(null);

    // 실제 캔버스 데이터를 분석 (setTimeout은 UX용 최소 지연)
    setTimeout(() => {
      setIsAnalyzing(false);

      // 1. 도형이 없으면 분석 불가
      if (rects.length === 0 && polygons.length === 0 && points.length === 0) {
        setAnalysisResult({
          score: 0,
          issues: [{ id: "empty", type: "DATA", desc: "캔버스에 도형이 없습니다. 먼저 도면을 그리거나 AI 자동 설계를 실행하세요.", severity: "high" }],
        });
        setAnalysis(false, []);
        return;
      }

      // 2. 면적 계산 (사각형 + 폴리곤)
      let totalRectArea = 0;
      for (const rc of rects) {
        totalRectArea += (rc.width / cadScale) * (rc.height / cadScale);
      }

      let totalPolygonArea = 0;
      for (const pg of polygons) {
        const pts = pg.pointIds
          .map((pid: string) => points.find((p) => p.id === pid))
          .filter((p): p is typeof points[0] => p !== undefined);
        if (pts.length >= 3) {
          let area = 0;
          for (let i = 0; i < pts.length; i++) {
            const j = (i + 1) % pts.length;
            area += pts[i].x * pts[j].y - pts[j].x * pts[i].y;
          }
          totalPolygonArea += Math.abs(area) / 2 / (cadScale * cadScale);
        }
      }

      // 3. 대지면적 = 가장 큰 도형 (첫 번째 사각형 또는 폴리곤)
      const siteArea = rects.length > 0
        ? (rects[0].width / cadScale) * (rects[0].height / cadScale)
        : totalPolygonArea > 0 ? totalPolygonArea : 500;

      // 건축면적 = 나머지 사각형 합계 (첫 번째 제외)
      const buildingArea = rects.length > 1
        ? rects.slice(1).reduce((s, r) => s + (r.width / cadScale) * (r.height / cadScale), 0)
        : totalRectArea;

      // 4. 건폐율/용적률 계산
      const bcr = siteArea > 0 ? (buildingArea / siteArea) * 100 : 0;
      const far = siteArea > 0 ? (buildingArea * floorCount / siteArea) * 100 : 0;
      const height = floorCount * buildingHeightM;

      // 5. 법규 체크 (제2종일반주거 기본값)
      const maxBcr = 60, maxFar = 250, maxHeight = 21;
      const issues: Array<{ id: string; type: string; desc: string; severity: "high" | "med" | "low"; x?: number; y?: number }> = [];

      if (bcr > maxBcr) {
        issues.push({
          id: "bcr", type: "BCR",
          desc: `건폐율 초과: ${bcr.toFixed(1)}% > 한도 ${maxBcr}%`,
          severity: "high",
          x: rects[0]?.x ?? 100, y: rects[0]?.y ?? 50,
        });
      }
      if (far > maxFar) {
        issues.push({
          id: "far", type: "FAR",
          desc: `용적률 초과: ${far.toFixed(1)}% > 한도 ${maxFar}%`,
          severity: "high",
          x: rects[0]?.x ?? 100, y: (rects[0]?.y ?? 50) + 30,
        });
      }
      if (height > maxHeight) {
        issues.push({
          id: "height", type: "HEIGHT",
          desc: `높이 제한 초과: ${height.toFixed(1)}m > 한도 ${maxHeight}m`,
          severity: "high",
          x: rects[0]?.x ?? 100, y: (rects[0]?.y ?? 50) + 60,
        });
      }
      if (bcr <= maxBcr && far <= maxFar && height <= maxHeight) {
        issues.push({
          id: "ok", type: "PASS",
          desc: `법규 적합: 건폐율 ${bcr.toFixed(1)}%, 용적률 ${far.toFixed(1)}%, 높이 ${height.toFixed(1)}m`,
          severity: "low",
        });
      }

      // 6. 점수 산정
      let score = 100;
      if (bcr > maxBcr) score -= 30;
      if (far > maxFar) score -= 30;
      if (height > maxHeight) score -= 20;
      if (rects.length < 2) score -= 10;
      score = Math.max(0, Math.min(100, score));

      const markers = issues
        .filter((i) => i.x !== undefined)
        .map((i) => ({ id: i.id, x: i.x!, y: i.y!, severity: i.severity, desc: i.desc }));

      setAnalysisResult({ score, issues });
      setAnalysis(false, markers);
    }, 500);
  };

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-4">
      <div className="flex flex-col gap-2">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">AI 도면 분석</h3>
        <button
          onClick={startAnalysis}
          disabled={isAnalyzing}
          className="w-full rounded-xl bg-indigo-600 px-4 py-2 text-sm font-semibold text-white transition-opacity disabled:opacity-50"
        >
          {isAnalyzing ? "분석 중..." : "도면 분석"}
        </button>
      </div>

      <AnimatePresence mode="wait">
        {isAnalyzing ? (
          <motion.div
            key="analyzing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex items-center gap-3 py-4"
          >
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-indigo-600 border-t-transparent" />
            <p className="text-xs text-[var(--text-secondary)] animate-pulse">법규 대조 분석 중...</p>
          </motion.div>
        ) : analysisResult ? (
          <motion.div
            key="result"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex flex-col gap-3"
          >
            {/* 점수 + 이슈 수 */}
            <div className="flex items-center gap-3">
              <div className="flex-1 rounded-xl bg-[var(--surface-soft)] p-3 text-center">
                <p className="text-[10px] font-bold text-[var(--text-hint)] uppercase">적합도</p>
                <p className={`text-xl font-bold ${analysisResult.score > 80 ? "text-emerald-500" : analysisResult.score > 50 ? "text-amber-500" : "text-red-500"}`}>{analysisResult.score}%</p>
              </div>
              <div className="flex-1 rounded-xl bg-[var(--surface-soft)] p-3 text-center">
                <p className="text-[10px] font-bold text-[var(--text-hint)] uppercase">위반</p>
                <p className="text-xl font-bold text-red-500">{(analysisResult.issues ?? []).filter(i => i.severity === "high").length}</p>
              </div>
            </div>

            {/* 이슈 목록 */}
            <div className="flex flex-col gap-1.5">
              {(analysisResult.issues ?? []).map((issue) => (
                <div key={issue.id} className="flex items-start gap-2 rounded-lg bg-[var(--surface-soft)] p-2.5">
                  <div className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${
                    issue.severity === "high" ? "bg-red-500" : issue.severity === "med" ? "bg-amber-500" : "bg-emerald-500"
                  }`} />
                  <p className="text-xs text-[var(--text-secondary)] leading-relaxed">{issue.desc}</p>
                </div>
              ))}
            </div>
          </motion.div>
        ) : (
          <p className="text-xs text-[var(--text-hint)] py-2">도면을 그린 후 분석을 실행하세요.</p>
        )}
      </AnimatePresence>
    </div>
  );
}
