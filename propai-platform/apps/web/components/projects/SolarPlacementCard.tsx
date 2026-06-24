"use client";

/**
 * 일조·건물배치 정밀분석 카드 — /api/v1/site-score/placement.
 * 토지모양·향·층별높이 기반: 8방위 동지 일조시간(일조권 충족)·배치 대안(판상/탑상/중정)별
 * 남향세대·평균 일조·밀도·효율·종합점수 + 우선순위(균형/일조/밀도)별 최적 배치안.
 * 한국 일조권(건축법 시행령 제86조)·태양궤도 천문식 — 글로벌 툴이 모르는 차별점.
 */

import { useEffect, useState } from "react";
import { Sun, Compass } from "lucide-react";
import { apiClient } from "@/lib/api-client";

type Orient = {
  direction: string; grade: string; direct_sun_hours: number;
  longest_continuous_0915_h: number; meets_daylight_right: boolean;
};
type Option = {
  type: string; score: number; south_facing_ratio_pct: number;
  avg_daylight_hours: number; density_units: number; efficiency_pct: number;
  pros?: string[]; cons?: string[]; note?: string;
};
type Placement = {
  envelope?: { max_floors?: number; max_height_m?: number; min_building_spacing_m?: number;
    realistic_far_pct?: number; daylight_loss_pct?: number };
  orientation_scores?: Orient[];
  placement_options?: Option[];
  recommended?: { type: string; score: number; reason: string };
  shadow?: { max_shadow_len_m?: number; noon_altitude_deg?: number };
  priority?: string; error?: string;
};

type Priority = "balanced" | "daylight" | "density";
const PRIORITY_LABEL: Record<Priority, string> = {
  balanced: "균형", daylight: "일조 우선", density: "밀도 우선",
};
const GRADE_COLOR: Record<string, string> = {
  우수: "var(--success, #16a34a)", 양호: "var(--accent-strong, #3b82f6)",
  미흡: "var(--warning, #d97706)", 불가: "var(--danger, #dc2626)",
};

export function SolarPlacementCard({
  address, pnu, zone, landAreaSqm,
}: {
  address?: string | null; pnu?: string | null; zone?: string | null; landAreaSqm?: number | null;
}) {
  const [res, setRes] = useState<Placement | null>(null);
  const [loading, setLoading] = useState(false);
  const [priority, setPriority] = useState<Priority>("balanced");

  useEffect(() => {
    if ((!landAreaSqm || landAreaSqm <= 0) && !pnu) { setRes(null); return; }
    let alive = true;
    setLoading(true);
    apiClient.post<Placement>("/site-score/placement", {
      body: {
        land_area_sqm: landAreaSqm ?? 0, zone: zone ?? "", address: address ?? "",
        pnu: pnu ?? undefined, priority,
      },
      useMock: false, timeoutMs: 45000,
    }).then((r) => { if (alive) setRes(r); })
      .catch(() => { if (alive) setRes(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [pnu, zone, address, landAreaSqm, priority]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5 text-xs text-[var(--text-hint)]">
        일조·건물배치 정밀분석 중…
      </div>
    );
  }
  if (!res || res.error || !res.placement_options?.length) return null;

  const rec = res.recommended;
  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
          <Sun className="size-4" aria-hidden /> 일조·건물배치 최적안
        </p>
        {/* 우선순위 토글 — 다각도(일조 vs 밀도) 트레이드오프 */}
        <div className="flex gap-1 rounded-lg bg-[var(--surface)] p-0.5">
          {(Object.keys(PRIORITY_LABEL) as Priority[]).map((p) => (
            <button key={p} onClick={() => setPriority(p)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-bold transition ${
                priority === p ? "bg-[var(--accent-strong)] text-white"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"}`}>
              {PRIORITY_LABEL[p]}
            </button>
          ))}
        </div>
      </div>

      {/* 최적 배치안 */}
      {rec && (
        <div className="mt-3 rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 p-3">
          <p className="text-xs font-black text-[var(--accent-strong)]">
            추천: {rec.type} <span className="font-bold text-[var(--text-secondary)]">(종합 {rec.score}점)</span>
          </p>
          <p className="mt-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">{rec.reason}</p>
        </div>
      )}

      {/* 8방위 동지 일조시간 */}
      {res.orientation_scores && res.orientation_scores.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 inline-flex items-center gap-1 text-[11px] font-bold text-[var(--text-secondary)]">
            <Compass className="size-3.5" aria-hidden /> 향별 동지 일조시간(일조권 충족)
          </p>
          <div className="grid grid-cols-4 gap-1.5">
            {res.orientation_scores.map((o) => (
              <div key={o.direction} className="rounded-lg border border-[var(--line)] bg-[var(--surface)] p-1.5 text-center">
                <p className="text-[11px] font-black text-[var(--text-primary)]">{o.direction}</p>
                <p className="text-[10px] text-[var(--text-secondary)]">{o.direct_sun_hours}h</p>
                <p className="text-[10px] font-bold" style={{ color: GRADE_COLOR[o.grade] ?? "var(--text-hint)" }}>
                  {o.grade}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 배치 대안 비교 */}
      <div className="mt-4 space-y-2">
        <p className="text-[11px] font-bold text-[var(--text-secondary)]">배치 대안 비교(점수순)</p>
        {res.placement_options.map((o) => (
          <div key={o.type}
            className={`rounded-xl border p-3 ${
              o.type === rec?.type ? "border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/5"
                : "border-[var(--line)] bg-[var(--surface)]"}`}>
            <div className="flex items-center justify-between">
              <p className="text-xs font-black text-[var(--text-primary)]">{o.type}</p>
              <p className="text-[11px] font-bold text-[var(--accent-strong)]">{o.score}점</p>
            </div>
            <div className="mt-1.5 grid grid-cols-4 gap-1 text-center text-[10px]">
              <div><p className="text-[var(--text-hint)]">남향세대</p><p className="font-bold text-[var(--text-primary)]">{o.south_facing_ratio_pct}%</p></div>
              <div><p className="text-[var(--text-hint)]">평균일조</p><p className="font-bold text-[var(--text-primary)]">{o.avg_daylight_hours}h</p></div>
              <div><p className="text-[var(--text-hint)]">세대수</p><p className="font-bold text-[var(--text-primary)]">{o.density_units?.toLocaleString()}</p></div>
              <div><p className="text-[var(--text-hint)]">효율</p><p className="font-bold text-[var(--text-primary)]">{o.efficiency_pct}%</p></div>
            </div>
            {o.note && <p className="mt-1.5 text-[10px] leading-relaxed text-[var(--text-secondary)]">{o.note}</p>}
          </div>
        ))}
      </div>

      {/* 동지 음영 + 근거 */}
      <p className="mt-3 text-[10px] leading-relaxed text-[var(--text-hint)]">
        {res.shadow?.max_shadow_len_m != null &&
          `동지 정오 태양고도 ${res.shadow.noon_altitude_deg}° · 그림자 최대 ${res.shadow.max_shadow_len_m}m. `}
        근거: 태양궤도 천문식 + 건축법 시행령 제86조(정북일조·인동간격 0.8H·일조권 09~15시 연속 2h).
        직사각형 대지·표준 매스타입 근사(정밀 3D 음영은 BIM 매스 결합 시).
      </p>
    </div>
  );
}
