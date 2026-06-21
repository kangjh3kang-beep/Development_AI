"use client";

/**
 * 정북일조 빌더블 인벨로프 카드(프로퍼티 주입형) — 인허가/설계 화면 공용.
 * /api/v1/site-score/envelope 호출 → 건축가능 최대 연면적·현실 층수·일조 손실률 + 동지 일영(그림자).
 * 한국 정북일조(건축법 시행령 §86)를 정량화 — 글로벌 툴이 모르는 차별점.
 */

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { adaptEvidence, type BackendEvidence, type BackendLegalRef } from "@/lib/evidence/adaptEvidence";

type Shadow = {
  winter_solstice?: Record<string, { solar_altitude_deg: number; shadow_len_m: number | null }>;
  noon_altitude_deg?: number; max_shadow_len_m?: number; note?: string;
};
type Envelope = {
  applies_north_light: boolean; binding: string; daylight_loss_pct: number;
  far_gfa_sqm: number; effective_gfa_sqm: number; max_floors: number; max_height_m: number;
  daylight_ceiling_m?: number; min_building_spacing_m?: number; min_building_spacing_blank_wall_m?: number;
  far_pct?: number; bcr_pct?: number; zone?: string;
  geometry_source?: string; road_side?: string; shadow_analysis?: Shadow; note?: string; error?: string;
  // 백엔드가 evidence/legal_refs를 반환하면 우선 사용(현재 미반환 → 프론트 산식 트레이스로 폴백).
  evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[];
};

const sqm = (v: number) => `${Math.round(v).toLocaleString()}㎡`;

export function SolarEnvelopeCard({
  address, pnu, zone, landAreaSqm, farLimitPct, bcrLimitPct,
}: {
  address?: string | null; pnu?: string | null; zone?: string | null; landAreaSqm?: number | null;
  // 실효 용적률/건폐율(부지분석 SSOT) — 있으면 백엔드 기본값 폴백을 회피(정확성). 없으면 미전달(가짜값 금지).
  farLimitPct?: number | null; bcrLimitPct?: number | null;
}) {
  const [res, setRes] = useState<Envelope | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if ((!landAreaSqm || landAreaSqm <= 0) && !pnu) { setRes(null); return; }
    let alive = true;
    setLoading(true);
    apiClient.post<Envelope>("/site-score/envelope", {
      body: {
        land_area_sqm: landAreaSqm ?? 0, zone: zone ?? "", pnu: pnu ?? undefined, floor_height_m: 3.0,
        far_limit_pct: farLimitPct ?? undefined,
        bcr_limit_pct: bcrLimitPct ?? undefined,
      },
      useMock: false, timeoutMs: 45000,
    }).then((r) => { if (alive) setRes(r); })
      .catch(() => { if (alive) setRes(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [pnu, zone, landAreaSqm, farLimitPct, bcrLimitPct]);

  if (loading) {
    return (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5 text-xs text-[var(--text-hint)]">
        일조권·건축가능 볼륨 분석 중…
      </div>
    );
  }
  if (!res || res.error) return null;
  const lossBinding = res.binding === "정북일조";
  // 추정값 경고: 실효 용적률을 못 줘서 백엔드 기본값(추정 폴백)에 의존했을 때는 zone 유무와
  // 무관하게 '추정값'임을 항상 정직히 표기한다(과소경고 방지). 문구만 zone 유무로 분기한다.
  const usedFallback = farLimitPct == null;
  const zoneEmpty = !zone || !zone.trim();
  const fallbackLabel = zoneEmpty
    ? "⚠ 용도지역 미확정 — 추정값(신뢰도 낮음)"
    : "⚠ 용도지역 기본값 추정 — 실효 용적률 미산정(신뢰도 낮음)";

  // 산출 근거(EvidencePanel) — 백엔드 evidence가 있으면 우선, 없으면 응답 수치로 산식 트레이스 구성.
  // ★법령 URL은 백엔드 get_legal_refs 출력만(프론트 URL 조립 금지) — 미반환 구간은 basis 텍스트만.
  const backendEvidence = adaptEvidence(res.evidence, res.legal_refs);
  const areaForBasis = landAreaSqm ?? 0;
  const evidenceItems: EvidenceItem[] = backendEvidence.length > 0 ? backendEvidence : [
    {
      label: "건축가능 연면적",
      value: sqm(res.effective_gfa_sqm),
      basis: `대지면적 ${sqm(areaForBasis)} × 용적률 ${res.far_pct ?? "—"}%${lossBinding ? " → 정북일조 한도 적용(min)" : ""}`,
    },
    {
      label: "용적률 허용 연면적",
      value: sqm(res.far_gfa_sqm),
      basis: `대지면적 ${sqm(areaForBasis)} × 용적률 ${res.far_pct ?? "—"}%${usedFallback ? " · 용도지역 기본값(추정)" : " · 실효 용적률"}`,
    },
    {
      label: "현실 최고층",
      value: `${res.max_floors}층`,
      basis: `건축가능 연면적 ÷ (대지면적 × 건폐율 ${res.bcr_pct ?? "—"}%) ≈ 층수`,
    },
    {
      label: "정북일조 천장",
      value: res.daylight_ceiling_m != null ? `${res.daylight_ceiling_m}m` : "—",
      basis: res.applies_north_light
        ? "정북 인접대지경계선 정북일조 사선(건축법 시행령 §86) 적분 최고선"
        : "정북일조 미적용 용도(사선 제한 없음)",
    },
    {
      label: "일조 손실률",
      value: `${res.daylight_loss_pct}%`,
      basis: lossBinding ? "(용적률 허용 − 일조 한도) ÷ 용적률 허용" : "일조 한도 ≥ 용적률 한도 → 손실 없음",
    },
  ];

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-bold text-[var(--text-primary)]">일조권 · 건축가능 볼륨 (정북일조)</h4>
          <p className="text-[11px] text-[var(--text-secondary)]">
            {zone || "용도지역 미상"}{landAreaSqm ? ` · 대지 ${sqm(landAreaSqm)}` : ""}
            {res.geometry_source ? ` · ${res.geometry_source}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          {usedFallback && (
            <span
              className="rounded-full bg-amber-500/10 px-2.5 py-1 text-[11px] font-black text-amber-600"
              title="실효 용적률이 산정되지 않아 용도지역 기본값으로 추정한 결과입니다. 부지분석(용도지역·실효 용적률)을 완료하면 실제값으로 재계산됩니다."
            >
              {fallbackLabel}
            </span>
          )}
          <span className={`rounded-full px-2.5 py-1 text-xs font-black ${lossBinding ? "bg-amber-500/10 text-amber-600" : "bg-emerald-500/10 text-emerald-600"}`}>
            한도: {res.binding}
          </span>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="건축가능 연면적" value={sqm(res.effective_gfa_sqm)} sub={`용적률한도 ${sqm(res.far_gfa_sqm)}`} accent />
        <Tile label="현실 최고층" value={`${res.max_floors}층`} sub={`약 ${res.max_height_m}m`} />
        <Tile label="정북일조 천장" value={res.daylight_ceiling_m != null ? `${res.daylight_ceiling_m}m` : "—"} sub={res.applies_north_light ? "사선 최고선" : "미적용 용도"} />
        <Tile label="일조 손실률" value={`${res.daylight_loss_pct}%`} sub={lossBinding ? "용적률 대비 손실" : "여유"} accent={lossBinding} />
      </div>

      {res.shadow_analysis?.winter_solstice && (
        <div className="mt-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
          <div className="flex items-center justify-between">
            <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">동지 일영(그림자)</p>
            <p className="text-[10px] text-[var(--text-secondary)]">
              정오 고도 {res.shadow_analysis.noon_altitude_deg}° · 최대 그림자 {res.shadow_analysis.max_shadow_len_m}m
            </p>
          </div>
          <div className="mt-2 grid grid-cols-3 gap-2">
            {Object.entries(res.shadow_analysis.winter_solstice).map(([t, v]) => (
              <div key={t} className="rounded-lg bg-[var(--surface)] px-3 py-2 text-center">
                <p className="text-[10px] text-[var(--text-secondary)]">{t}</p>
                <p className="text-sm font-[1000] text-[var(--text-primary)]">{v.shadow_len_m != null ? `${v.shadow_len_m}m` : "—"}</p>
                <p className="text-[9px] text-[var(--text-hint)]">고도 {v.solar_altitude_deg}°</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {(res.min_building_spacing_m || res.road_side) && (
        <p className="mt-2 text-[11px] text-[var(--text-secondary)]">
          {res.min_building_spacing_m ? `동간 채광거리(공동주택) 권고 ${res.min_building_spacing_m}m(0.8H)·무창벽 ${res.min_building_spacing_blank_wall_m}m` : ""}
          {res.road_side ? `${res.min_building_spacing_m ? " · " : ""}접도: ${res.road_side}` : ""}
        </p>
      )}
      {res.note && <p className="mt-2 text-[10px] text-[var(--text-hint)]">{res.note}</p>}

      {/* 산출 근거(EvidencePanel) — 응답 수치로 산식 트레이스 구성(가짜값/가짜URL 0).
          용적률·일조 한도 산식을 한 줄씩 보여 "왜 이 연면적·층수인가?"에 답한다. */}
      <EvidencePanel className="mt-3" items={evidenceItems} title="일조·건축가능 볼륨 산출 근거" />
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
