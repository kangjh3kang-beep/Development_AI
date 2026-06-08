"use client";

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";

/**
 * 대시보드 사이드바 — ESG 통합 점수.
 * 과거 하드코딩 "84.2 / A+"를 제거(무목업 원칙). 가짜 숫자는 절대 만들지 않는다.
 *
 * ⚠️ 현재 상태(정직 표기): 포트폴리오 ESG 요약을 돌려주는 GET 엔드포인트가
 *    라이브 백엔드에 아직 없다(ESG 백엔드는 /api/v1/esg/* POST 전용).
 *    따라서 운영에서는 항상 "N/A" 빈상태로 표시된다. 이는 의도된 정직 표기이며,
 *    백엔드에 GET /api/v1/analytics/esg(overall_score · gresb_rating) 요약 라우트가
 *    추가되면 별도 수정 없이 자동으로 실점수가 채워진다.
 */
type EsgApi = {
  overall_score?: number;
  gresb_rating?: string;
};

export function DashboardEsgScore() {
  const [score, setScore] = useState<number | null>(null);
  const [grade, setGrade] = useState<string | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "empty">("loading");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiClient.get<EsgApi>("/analytics/esg");
        if (cancelled) return;
        const s = typeof res.overall_score === "number" && Number.isFinite(res.overall_score)
          ? res.overall_score
          : null;
        if (s === null) {
          setState("empty");
        } else {
          setScore(s);
          setGrade(res.gresb_rating ?? null);
          setState("ok");
        }
      } catch {
        if (!cancelled) setState("empty");
      }
    })();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="pt-6 border-t border-[var(--line)] space-y-4">
      {/* 네온 시안/모노 영문 라벨 폐기 → 한국어 라벨 + 본문 서체 큰 숫자(C2) */}
      <div className="flex items-center justify-between">
        <h4 className="db-panel-label">ESG 통합 점수</h4>
        <span className="db-panel-meta">GRESB 기준</span>
      </div>

      <div className="relative h-40 w-full overflow-hidden rounded-2xl border border-[var(--line)] bg-[var(--surface)]">
        <div className="cc-grid-bg cc-grid-bg--radial opacity-40" />

        <div className="relative z-10 flex h-full flex-col items-center justify-center gap-1">
          {state === "loading" ? (
            <span className="text-3xl font-semibold text-[var(--text-tertiary)] animate-pulse tabular-nums">— · —</span>
          ) : state === "empty" ? (
            <div className="flex flex-col items-center gap-1.5 text-center px-4">
              <span className="text-2xl font-semibold text-[var(--text-tertiary)]">—</span>
              <span className="text-[12px] font-medium text-[var(--text-tertiary)] leading-snug">
                ESG 분석 데이터 없음
                <br />
                <span className="text-[11px] text-[var(--text-hint)]">프로젝트 분석 후 산출됩니다</span>
              </span>
            </div>
          ) : (
            <>
              {/* 큰 숫자는 본문 서체 계열 + 중립 화이트(상태색 절제) */}
              <span className="text-5xl font-bold tabular-nums text-[var(--text-primary)] leading-none">
                {score!.toFixed(1)}
              </span>
              <div className="mt-2 flex items-center gap-2">
                <span className="text-[12px] font-medium text-[var(--text-tertiary)]">100점 만점</span>
                {grade ? <span className="db-status-chip">{grade}</span> : null}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
