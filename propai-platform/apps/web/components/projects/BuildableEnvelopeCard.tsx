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
  daylight_ceiling_floors?: number; note?: string; error?: string;
};

const eok = (sqm: number) => `${sqm.toLocaleString()}㎡`;

export function BuildableEnvelopeCard() {
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const design = useProjectContextStore((s) => s.designData);
  const [res, setRes] = useState<Envelope | null>(null);

  const area = site?.landAreaSqm ?? null;
  const zone = site?.zoneCode ?? "";

  useEffect(() => {
    if (!area || area <= 0) { setRes(null); return; }
    let cancelled = false;
    apiClient.post<Envelope>("/site-score/envelope", {
      body: { land_area_sqm: area, zone, floor_height_m: 3.0 },
    }).then((r) => { if (!cancelled) setRes(r); }).catch(() => { if (!cancelled) setRes(null); });
    return () => { cancelled = true; };
  }, [area, zone]);

  if (!area || !res || res.error) return null;

  const lossBinding = res.binding === "정북일조";

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-bold text-[var(--text-primary)]">빌더블 인벨로프 (정북일조)</h4>
          <p className="text-[11px] text-[var(--text-secondary)]">{zone || "용도지역 미상"} · 대지 {eok(area)}</p>
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

      {design?.totalGfaSqm != null && (
        <p className="mt-3 text-[11px] text-[var(--text-secondary)]">
          현재 설계 연면적 {eok(Math.round(design.totalGfaSqm))} / 건축가능 {eok(res.effective_gfa_sqm)}
          {design.totalGfaSqm > res.effective_gfa_sqm ? " — ⚠ 한도 초과 검토" : " — 한도 내"}
        </p>
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
