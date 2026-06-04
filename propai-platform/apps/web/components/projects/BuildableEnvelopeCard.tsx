"use client";

/**
 * 한국 정북일조 빌더블 인벨로프(베팅 D).
 * 부지(대지면적·용도지역)로 /api/v1/site-score/envelope 를 호출해 건축가능 최대 연면적·
 * 현실 층수·정북일조 손실률을 표시. 글로벌 툴이 모르는 한국 정북일조를 정량화.
 */

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";

type Envelope = {
  applies_north_light: boolean; binding: string; daylight_loss_pct: number;
  far_gfa_sqm: number; effective_gfa_sqm: number; envelope_gfa_sqm?: number;
  max_floors: number; max_height_m: number; daylight_ceiling_m?: number;
  daylight_ceiling_floors?: number; geometry_source?: string;
  min_building_spacing_m?: number; min_building_spacing_blank_wall_m?: number;
  road_side?: string; note?: string; error?: string;
  shadow_analysis?: {
    winter_solstice?: Record<string, { solar_altitude_deg: number; shadow_len_m: number | null }>;
    noon_altitude_deg?: number; max_shadow_len_m?: number; latitude?: number; note?: string;
  };
};

const eok = (sqm: number) => `${sqm.toLocaleString()}㎡`;

export function BuildableEnvelopeCard() {
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const design = useProjectContextStore((s) => s.designData);
  const [res, setRes] = useState<Envelope | null>(null);

  const area = site?.landAreaSqm ?? null;
  const zone = site?.zoneCode ?? "";
  const pnu = site?.pnu ?? null;

  useEffect(() => {
    if ((!area || area <= 0) && !pnu) { setRes(null); return; }
    let cancelled = false;
    apiClient.post<Envelope>("/site-score/envelope", {
      body: { land_area_sqm: area ?? 0, zone, pnu: pnu ?? undefined, floor_height_m: 3.0 },
    }).then((r) => { if (!cancelled) setRes(r); }).catch(() => { if (!cancelled) setRes(null); });
    return () => { cancelled = true; };
  }, [area, zone, pnu]);

  if ((!area && !pnu) || !res || res.error) return null;

  const lossBinding = res.binding === "정북일조";

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-bold text-[var(--text-primary)]">빌더블 인벨로프 (정북일조)</h4>
          <p className="text-[11px] text-[var(--text-secondary)]">
            {zone || "용도지역 미상"}{area ? ` · 대지 ${eok(area)}` : ""}
            {res.geometry_source ? ` · ${res.geometry_source}` : ""}
          </p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs font-black ${lossBinding ? "bg-amber-500/10 text-amber-600" : "bg-emerald-500/10 text-emerald-600"}`}>
          한도: {res.binding}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="건축가능 연면적" value={eok(res.effective_gfa_sqm)} sub={`용적률한도 ${eok(res.far_gfa_sqm)}`} accent />
        <Tile label="현실 최고층" value={`${res.max_floors}층`} sub={`약 ${res.max_height_m}m`} />
        <Tile label="정북일조 천장" value={res.daylight_ceiling_m != null ? `${res.daylight_ceiling_m}m` : "—"} sub={res.applies_north_light ? "사선 최고선" : "미적용 용도"} />
        <Tile label="일조 손실률" value={`${res.daylight_loss_pct}%`} sub={lossBinding ? "용적률 대비 손실" : "여유"} accent={lossBinding} />
      </div>

      {(res.min_building_spacing_m || res.road_side) && (
        <p className="mt-2 text-[11px] text-[var(--text-secondary)]">
          {res.min_building_spacing_m ? `동간 채광거리(공동주택) 권고 ${res.min_building_spacing_m}m(0.8H)·무창벽 ${res.min_building_spacing_blank_wall_m}m` : ""}
          {res.road_side ? `${res.min_building_spacing_m ? " · " : ""}접도: ${res.road_side}` : ""}
        </p>
      )}
      {design?.totalGfaSqm != null && (
        <p className="mt-3 text-[11px] text-[var(--text-secondary)]">
          현재 설계 연면적 {eok(Math.round(design.totalGfaSqm))} / 건축가능 {eok(res.effective_gfa_sqm)}
          {design.totalGfaSqm > res.effective_gfa_sqm ? " — ⚠ 한도 초과 검토" : " — 한도 내"}
        </p>
      )}
      {res.shadow_analysis?.winter_solstice && (
        <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">동지 일영(그림자)</p>
            <p className="text-[10px] text-[var(--text-secondary)]">
              정오 태양고도 {res.shadow_analysis.noon_altitude_deg}° · 최대 그림자 {res.shadow_analysis.max_shadow_len_m}m
            </p>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {Object.entries(res.shadow_analysis.winter_solstice).map(([t, v]) => (
              <div key={t} className="rounded-lg bg-[var(--surface)] px-3 py-2 text-center">
                <p className="text-[10px] text-[var(--text-secondary)]">{t}</p>
                <p className="text-sm font-[1000] text-[var(--text-primary)]">
                  {v.shadow_len_m != null ? `${v.shadow_len_m}m` : "—"}
                </p>
                <p className="text-[9px] text-[var(--text-hint)]">고도 {v.solar_altitude_deg}°</p>
              </div>
            ))}
          </div>
          {res.shadow_analysis.note && (
            <p className="mt-2 text-[10px] text-[var(--text-hint)]">{res.shadow_analysis.note}</p>
          )}
        </div>
      )}
      {res.note && <p className="mt-2 text-[10px] text-[var(--text-hint)]">{res.note}</p>}
    </div>
  );
}

function Tile({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
      <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{label}</p>
      <p className={`mt-1 text-base font-[1000] ${accent ? "text-[var(--accent-strong)]" : "text-[var(--text-primary)]"}`}>{value}</p>
      {sub ? <p className="mt-0.5 text-[10px] text-[var(--text-secondary)]">{sub}</p> : null}
    </div>
  );
}
