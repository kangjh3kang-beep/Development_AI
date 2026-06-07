"use client";

/**
 * EnvironmentSummaryCard — 환경분석(일조·조망·스카이라인) 컴팩트 보조카드.
 *
 * 전체 패널(EnvironmentAnalysisPanel)은 부지분석 화면에만 두고, 의사결정 단계에는
 * 단계 맥락에 맞는 요약만 녹여낸다.
 *   - focus="solar" : 정북 일조사선·동지 일조시간(법정 요건) → 인허가 화면.
 *   - focus="view"  : 조망 개방도·스카이라인(분양가치 근거) → 사업성/분양 화면.
 *
 * POST /api/v1/environment/analyze 재사용. graceful — 실패/데이터부족 시 카드 자체를 숨긴다
 * (추가 호출이 기존 화면을 깨지 않도록).
 */

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type { EnvironmentResult, SolarGrade, SkylinePosition } from "./types";

const GRADE_COLOR: Record<SolarGrade, string> = {
  양호: "#10b981",
  보통: "#f59e0b",
  불리: "#ef4444",
};
const SKYLINE_COLOR: Record<SkylinePosition, string> = {
  돌출: "#f59e0b",
  조화: "#10b981",
  매몰: "#60a5fa",
};

const n1 = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: 1 });

export function EnvironmentSummaryCard({
  address,
  pnu,
  focus,
}: {
  address?: string | null;
  pnu?: string | null;
  /** solar=일조(인허가) / view=조망·스카이라인(사업성·분양가치) */
  focus: "solar" | "view";
}) {
  const [res, setRes] = useState<EnvironmentResult | null>(null);

  useEffect(() => {
    const a = (address || "").trim();
    if (!a && !pnu) return;
    let cancelled = false;
    // 비동기 콜백 내부에서만 setState(이펙트 본문 동기 setState 회피).
    const load = async () => {
      try {
        const d = await apiClient.post<EnvironmentResult>("/environment/analyze", {
          body: { address: a || null, pnu: pnu ?? null, season: "winter" },
          useMock: false,
          timeoutMs: 60000,
        });
        if (!cancelled && d?.ok) setRes(d);
      } catch {
        /* graceful — 실패/데이터부족 시 카드 숨김 */
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [address, pnu]);

  // 데이터 없으면(미수신·실패·데이터부족) 렌더하지 않음 — 섹션 숨김(graceful)
  if (!res?.ok) return null;

  const solar = res.solar;
  const view = res.view;
  const skyline = res.skyline;

  if (focus === "solar") {
    if (!solar) return null;
    const setbackApplies = solar.north_setback?.applies;
    return (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">☀️</span>
            <div>
              <h4 className="text-sm font-black text-[var(--text-primary)]">일조 환경 (법정 요건)</h4>
              <p className="text-[10px] text-[var(--text-hint)]">정북 일조사선·동지 일조시간 (약식 추정)</p>
            </div>
          </div>
          <span
            className="rounded-full px-2.5 py-1 text-xs font-black"
            style={{ color: GRADE_COLOR[solar.grade], background: `${GRADE_COLOR[solar.grade]}22` }}
          >
            {solar.grade}
          </span>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] p-3 text-center">
            <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">동지 일조시간</p>
            <p className="text-sm font-black text-[var(--text-primary)]">{n1(solar.sunlight_hours_winter)} h</p>
          </div>
          <div
            className={`rounded-lg border p-3 text-center ${
              setbackApplies
                ? "border-amber-500/40 bg-amber-500/10"
                : "border-[var(--line)] bg-[var(--surface-muted)]"
            }`}
          >
            <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">정북 일조사선</p>
            <p className="text-sm font-black text-[var(--text-primary)]">
              {setbackApplies ? `이격 ${n1(solar.north_setback.required_m)}m` : "미적용"}
            </p>
          </div>
        </div>

        {setbackApplies && solar.north_setback.detail && (
          <p className="mt-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] leading-relaxed text-amber-200/90">
            ⚠ {solar.north_setback.detail}
          </p>
        )}
        <p className="mt-2 text-[10px] text-[var(--text-hint)]">
          참고용 약식 추정 — 정밀 일조분석/측량이 아닙니다. 상세는 부지분석 환경 패널 참조.
        </p>
      </div>
    );
  }

  // focus === "view"
  if (!view && !skyline) return null;
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-lg">🏙️</span>
          <div>
            <h4 className="text-sm font-black text-[var(--text-primary)]">조망·스카이라인 (분양가치 근거)</h4>
            <p className="text-[10px] text-[var(--text-hint)]">개방도·주변 건물 높이 비교 (약식 추정)</p>
          </div>
        </div>
        {skyline && (
          <span
            className="rounded-full px-2.5 py-1 text-xs font-black"
            style={{ color: SKYLINE_COLOR[skyline.position], background: `${SKYLINE_COLOR[skyline.position]}22` }}
          >
            {skyline.position}
          </span>
        )}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2">
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] p-3 text-center">
          <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">조망 개방도</p>
          <p className="text-sm font-black text-[var(--text-primary)]">{Math.round(view?.openness_score ?? 0)} / 100</p>
        </div>
        <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] p-3 text-center">
          <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">대상/주변 평균 높이</p>
          <p className="text-sm font-black text-[var(--text-primary)]">
            {n1(skyline?.subject_height_m)}m / {n1(skyline?.neighbor_avg_m)}m
          </p>
        </div>
      </div>

      {view?.best_directions && view.best_directions?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {(view.best_directions ?? []).map((d, i) => (
            <span
              key={`${d}-${i}`}
              className="rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-300"
            >
              🧭 {d} 트임
            </span>
          ))}
        </div>
      )}
      <p className="mt-2 text-[10px] text-[var(--text-hint)]">
        참고용 약식 추정 — 분양가 산정 보조지표. 상세는 부지분석 환경 패널 참조.
      </p>
    </div>
  );
}
