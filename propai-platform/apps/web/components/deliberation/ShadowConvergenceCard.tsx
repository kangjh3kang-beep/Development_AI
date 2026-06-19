"use client";

/**
 * 중심엔진 수렴 카드 — BFF `/api/v1/deliberation/shadow/stats`(테넌트 스코프) 도메인별 일치율 표시.
 *
 * shadow 관측(플랫폼 vs 엔진 판정) divergence를 인증 BFF 경유로 조회. authoritative 승격 판단 모니터.
 * 기본 off(deliberation_shadow_enabled)거나 미적재면 빈 목록 — "관측 데이터 없음" 정직 안내(무음0).
 */
import { useEffect, useState } from "react";

import { apiClient } from "@/lib/api-client";

type DomainStat = {
  domain: string;
  n: number;
  matched_n: number;
  match_rate: number;
  avg_divergence: number | null;
};
type StatsResp = { stats: DomainStat[]; degraded?: boolean };

type View =
  | { phase: "loading" }
  | { phase: "empty" }
  | { phase: "ready"; stats: DomainStat[] }
  | { phase: "error" };

const PROMOTE_RATE = 0.99; // 설계 승격 게이트(match_rate) — 시각 표식용

export function ShadowConvergenceCard() {
  const [view, setView] = useState<View>({ phase: "loading" });

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const d = await apiClient.get<StatsResp>("/deliberation/shadow/stats");
        if (!alive) return;
        const stats = d.stats || [];
        setView(stats.length ? { phase: "ready", stats } : { phase: "empty" });
      } catch {
        if (alive) setView({ phase: "error" });
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return (
    <section className="cc-panel cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] p-5">
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--tr" />
      <i className="cc-bracket cc-bracket--bl" />
      <i className="cc-bracket cc-bracket--br" />
      <div className="relative z-10 flex items-center justify-between gap-3">
        <h2 className="text-sm font-black text-[var(--text-primary)]">중심엔진 수렴(shadow)</h2>
        <span className="cc-label text-[10px] text-[var(--text-tertiary)]">플랫폼 vs 엔진 일치율</span>
      </div>
      {view.phase === "loading" && (
        <p className="relative z-10 mt-2 text-[11px] text-[var(--text-tertiary)]">불러오는 중…</p>
      )}
      {view.phase === "empty" && (
        <p className="relative z-10 mt-2 text-[11px] text-[var(--text-tertiary)]">
          관측 데이터 없음 — shadow 비활성 또는 미적재(운영 활성화 후 누적).
        </p>
      )}
      {view.phase === "error" && (
        <p className="relative z-10 mt-2 text-[11px] text-[var(--text-tertiary)]">수렴 통계 확인 실패</p>
      )}
      {view.phase === "ready" && (
        <ul className="relative z-10 mt-3 space-y-1.5">
          {view.stats.map((s) => {
            const pct = Math.round(s.match_rate * 1000) / 10;
            const promotable = s.match_rate >= PROMOTE_RATE;
            return (
              <li key={s.domain} className="flex items-center justify-between gap-2 text-[11px]">
                <span className="text-[var(--text-secondary)]">{s.domain}</span>
                <span className="flex items-center gap-2">
                  <span className="text-[var(--text-tertiary)]">n={s.n}</span>
                  <span
                    className={`font-semibold ${promotable ? "text-emerald-500" : "text-amber-500"}`}
                  >
                    {pct}%{promotable ? " · 승격가능" : ""}
                  </span>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
