'use client';

import { useState, useMemo, useEffect } from "react";
import { motion } from "framer-motion";
import { AlertTriangle, Building2, Info, Landmark, Layers, Loader2, MapPin } from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { zoningToCode } from "@/lib/kr-building-regulations";

// 정북일조 단계후퇴 층별 프로파일(백엔드 north_step_profile 항목과 1:1).
type StepFloor = {
  floor: number;
  north_setback_m: number;
  inset_m: number;
  depth_m: number;
};

// 설계엔진 매스 산출 결과(seed-design 응답의 legal_max_mass / regional_typical_mass).
type MassResult = {
  building_width_m: number;
  building_depth_m: number;
  building_footprint_sqm: number;
  num_floors: number;
  floor_height_m: number;
  building_height_m: number;
  total_floor_area_sqm: number;
  bcr_pct: number;
  far_pct: number;
  applied_max_bcr_pct?: number | null;
  applied_max_far_pct?: number | null;
  binding_constraint?: string | null;
  sunlight_mode?: string | null;
  north_step_profile?: StepFloor[] | null;
};

type MassReference = {
  region: string;
  building_type: string;
  sample_count: number;
  median_bcr_pct: number;
  median_far_pct: number;
  median_floors: number;
  median_total_area_sqm?: number | null;
  source: string;
  note?: string | null;
};

type SeedDesignResponse = {
  region: string;
  legal_max_mass: MassResult | null;
  regional_typical_mass: MassResult | null;
  mass_reference: MassReference | null;
  applied_limit_source?: "site_analysis_effective_limits" | "engine_zone_defaults" | string;
  note?: string | null;
};

type Props = {
  address: string;
  landAreaSqm: number;
  /** 한글 용도지역명 또는 코드 — zoningToCode로 엔진 키 변환 */
  zoning: string;
  buildingUse: string;
  floorHeightM?: number;
  effectiveFarPct?: number | null;
  effectiveBcrPct?: number | null;
  /** 다른 주소의 잔류 분석 등으로 비활성화해야 할 때 */
  disabled?: boolean;
};

// 측면 단면 SVG — 정북일조 단계후퇴 실루엣을 층별 depth_m로 그린다(상부 북측 후퇴 가시화).
// north_step_profile이 없으면(상업/준공업 등 일조 비대상) 균일 박스로 폴백.
function StepElevation({ mass, accent }: { mass: MassResult; accent: string }) {
  const W = 150;
  const H = 120;
  const pad = 10;
  const profile = mass.north_step_profile?.length
    ? mass.north_step_profile
    : Array.from({ length: Math.max(1, mass.num_floors) }, (_, i) => ({
        floor: i + 1,
        north_setback_m: 0,
        inset_m: 0,
        depth_m: mass.building_depth_m,
      }));
  const maxDepth = Math.max(...profile.map((p) => p.depth_m), 1);
  const floors = profile.length;
  const floorH = (H - pad * 2) / Math.max(floors, 1);
  const scaleX = (W - pad * 2) / maxDepth;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`${floors}층 측면 단면`}>
      {/* 지표선 */}
      <line x1={pad} y1={H - pad} x2={W - pad} y2={H - pad} stroke="var(--line-strong)" strokeWidth="1" />
      {profile.map((p, idx) => {
        // 아래(1층)부터 위로 쌓기. 남측(좌)을 기준선으로 두고 북측(우)이 후퇴.
        const y = H - pad - (idx + 1) * floorH;
        const w = Math.max(2, p.depth_m * scaleX);
        return (
          <rect
            key={p.floor}
            x={pad}
            y={y + 0.5}
            width={w}
            height={floorH - 1}
            rx={1}
            fill={accent}
            fillOpacity={0.18 + (idx / Math.max(floors, 1)) * 0.12}
            stroke={accent}
            strokeWidth="0.8"
          />
        );
      })}
      {/* 남/북 방향 표시(일조 후퇴 이해용) */}
      <text x={pad} y={H - 1} fontSize="6" fill="var(--text-hint)">남</text>
      <text x={W - pad - 6} y={H - 1} fontSize="6" fill="var(--text-hint)">북(후퇴)</text>
    </svg>
  );
}

// 소수 1자리 반올림(표시용) — 백엔드가 라운딩하지 않은 부동소수를 줘도 깔끔히 표시.
function r1(v: number): string {
  return (Math.round(v * 10) / 10).toLocaleString();
}

function MetricRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs">
      <span className="text-[var(--text-hint)]">{label}</span>
      <span className="font-bold text-[var(--text-primary)] tabular-nums">{value}</span>
    </div>
  );
}

function MassCard({
  title,
  badge,
  icon,
  accent,
  mass,
  emptyNote,
}: {
  title: string;
  badge: string;
  icon: React.ReactNode;
  accent: string;
  mass: MassResult | null;
  emptyNote?: string;
}) {
  return (
    <div className="flex-1 min-w-0 rounded-2xl border border-[var(--line)] bg-[var(--surface-muted)] p-4">
      <div className="mb-3 flex items-center gap-2">
        <span style={{ color: accent }}>{icon}</span>
        <div className="min-w-0">
          <p className="truncate text-sm font-black text-[var(--text-primary)]">{title}</p>
          <p className="text-[10px] text-[var(--text-hint)]">{badge}</p>
        </div>
      </div>
      {mass ? (
        <>
          <StepElevation mass={mass} accent={accent} />
          <div className="mt-3 space-y-1.5">
            <MetricRow label="층수" value={`${mass.num_floors}층`} />
            <MetricRow label="용적률" value={`${r1(mass.far_pct)}%`} />
            <MetricRow label="건폐율" value={`${r1(mass.bcr_pct)}%`} />
            <MetricRow label="연면적" value={`${Math.round(mass.total_floor_area_sqm).toLocaleString()}㎡`} />
            <MetricRow label="건축면적" value={`${Math.round(mass.building_footprint_sqm).toLocaleString()}㎡`} />
            <MetricRow label="건물높이" value={`${r1(mass.building_height_m)}m`} />
          </div>
        </>
      ) : (
        <p className="py-6 text-center text-xs leading-relaxed text-[var(--text-hint)]">
          {emptyNote || "데이터 없음"}
        </p>
      )}
    </div>
  );
}

/**
 * 지역 실측 전형 vs 법정 최대 매스 비교 — seed-design 엔드포인트 연동(②).
 *
 * 왜(쉬운 설명): "법으로 지을 수 있는 최대 규모"와 "이 동네에서 실제로 지어온 전형 규모"를
 * 나란히 보여 준다. 전형 규모는 지역 건축물대장 실측 중앙값(건폐/용적/층수)을 설계엔진에
 * 시드해 만든 것이라, 과도한 법정 최대만 보고 무리한 사업을 잡는 일을 막아 준다.
 * 두 매스 모두 정북일조 단계후퇴(법 61조) 해석이라 같은 기준으로 공정 비교된다.
 */
export function SeedDesignMassComparison({
  address,
  landAreaSqm,
  zoning,
  buildingUse,
  floorHeightM,
  effectiveFarPct,
  effectiveBcrPct,
  disabled,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SeedDesignResponse | null>(null);

  const zoneCode = useMemo(() => zoningToCode(zoning), [zoning]);
  const canFetch = !disabled && !!address && landAreaSqm > 0;
  // 미지원/미인식 용도지역 → 백엔드가 기본값 기준으로 추정함을 정직 고지.
  const zoneFallback = !zoneCode && !!zoning;

  // 부지(주소/용도지역/면적) 전환 시 이전 결과를 비워 stale 표시 방지(다른 주소의 매스 잔류 차단).
  useEffect(() => {
    setData(null);
    setError(null);
  }, [address, zoning, landAreaSqm]);

  async function handleFetch() {
    if (!canFetch) return;
    setLoading(true);
    setError(null);
    try {
      const body: Record<string, unknown> = {
        address,
        land_area_sqm: landAreaSqm,
        building_use: buildingUse,
      };
      // 한글→엔진 키 변환 성공 시에만 전달(실패 시 백엔드 기본값에 위임 — 잘못된 한글 주입 방지).
      if (zoneCode) body.zone_code = zoneCode;
      if (floorHeightM && floorHeightM > 0) body.floor_height_m = floorHeightM;
      if (effectiveFarPct && effectiveFarPct > 0) body.effective_far_pct = effectiveFarPct;
      if (effectiveBcrPct && effectiveBcrPct > 0) body.effective_bcr_pct = effectiveBcrPct;
      const res = await apiClient.post<SeedDesignResponse>("/mass-templates/seed-design", { body });
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "전형 매스 조회 실패");
    } finally {
      setLoading(false);
    }
  }

  const ref = data?.mass_reference ?? null;
  const usesEffectiveLimits = data?.applied_limit_source === "site_analysis_effective_limits";

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-3xl border border-[var(--line-strong)] p-6"
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="cc-label text-[var(--text-secondary)]">REGIONAL TYPOLOGY</span>
          </div>
          <h2 className="mt-1 text-lg font-black text-[var(--text-primary)]">법정 최대 vs 지역 실측 전형</h2>
          <p className="mt-1 flex items-center gap-1 text-xs text-[var(--text-hint)]">
            <MapPin className="size-3" aria-hidden />
            {address || "주소 없음"}
            {zoneCode ? ` · ${zoning}(${zoneCode})` : zoning ? ` · ${zoning}` : ""}
          </p>
        </div>
        <button
          onClick={handleFetch}
          disabled={!canFetch || loading}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full bg-gradient-to-r from-blue-600 to-cyan-600 px-4 py-2 text-xs font-black text-white shadow transition-all hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : <Layers className="size-3.5" aria-hidden />}
          {loading ? "조회 중…" : data ? "다시 조회" : "전형 매스 비교"}
        </button>
      </div>

      {!canFetch && !data && (
        <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3.5 py-2.5 text-xs text-[var(--text-hint)]">
          {disabled
            ? "현 프로젝트 주소와 부지분석이 일치해야 비교할 수 있습니다."
            : "주소와 대지면적이 있어야 비교할 수 있습니다(부지분석을 먼저 실행하세요)."}
        </p>
      )}

      {/* 미지원 용도지역 정직 고지(M1) — 엔진 키가 없어 기본(제2종 일반주거) 기준으로 추정됨. */}
      {zoneFallback && (
        <p className="mb-3 inline-flex items-start gap-1.5 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3.5 py-2.5 text-[11px] leading-relaxed text-amber-500">
          <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          이 용도지역({zoning})은 설계엔진 코드가 없어 <b className="mx-0.5">기본(제2종 일반주거)</b> 기준으로 추정합니다 — 실제 한도와 다를 수 있습니다.
        </p>
      )}

      {error && (
        <p className="inline-flex items-center gap-1.5 rounded-xl border border-red-500/20 bg-red-500/10 px-3.5 py-2.5 text-xs font-bold text-red-400">
          <AlertTriangle className="size-3.5" aria-hidden />
          {error}
        </p>
      )}

      {data && (
        <div className="space-y-4">
          <div className="flex flex-col gap-4 sm:flex-row">
            <MassCard
              title="적용 한도 최대"
              badge={usesEffectiveLimits ? "조례·계획 실효 한도 반영" : "법정/엔진 한도 기준"}
              icon={<Landmark className="size-4" aria-hidden />}
              accent="#34d399"
              mass={data.legal_max_mass}
              emptyNote="법정 한도 산출 불가"
            />
            <MassCard
              title="지역 실측 전형"
              badge={ref ? `${ref.region} ${ref.building_type} 실측 중앙값` : "지역 실측 시드"}
              icon={<Building2 className="size-4" aria-hidden />}
              accent="#60a5fa"
              mass={data.regional_typical_mass}
              emptyNote="이 지역 같은 종류 실측 매스가 아직 없습니다(법정 최대만 제공)."
            />
          </div>

          {ref && (
            <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3.5 py-3 text-[11px] leading-relaxed text-[var(--text-hint)]">
              <p className="font-bold text-[var(--text-secondary)]">
                시드 출처(근거): {ref.region} · {ref.building_type} · 실측 {ref.sample_count.toLocaleString()}개 표본
              </p>
              <p className="mt-1">
                중앙값 — 건폐율 {r1(ref.median_bcr_pct)}% · 용적률 {r1(ref.median_far_pct)}% · 층수 {r1(ref.median_floors)}층
                {ref.median_total_area_sqm ? ` · 연면적 ${Math.round(ref.median_total_area_sqm).toLocaleString()}㎡` : ""}
              </p>
              <p className="mt-1 text-[var(--text-tertiary)]">{ref.source}</p>
            </div>
          )}

          {data.note && (
            <p className="text-[10px] leading-relaxed text-[var(--text-tertiary)]">{data.note}</p>
          )}
        </div>
      )}
    </motion.div>
  );
}
