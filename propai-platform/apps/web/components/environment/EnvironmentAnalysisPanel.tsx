"use client";

/**
 * Flagship C-2 — 환경분석 패널(일조·조망·스카이라인).
 * 천문 근사식 태양궤적·약식 일영·정북 일조사선·8방위 개방도·스카이라인을 산출한다.
 *
 * ⚠ 약식 계산이며 정밀 일조분석/측량이 아니다. badges.note·basis를 그대로 노출한다
 *   (대기굴절·지형차폐·실측높이 미반영 — 할루시네이션 방지 철학).
 */

import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Compass, Landmark, Sun } from "lucide-react";
import { Card, CardContent } from "@propai/ui";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiClient } from "@/lib/api-client";
import {
  useAnalysisCache,
  analysisSignature,
  relativeKoreanTime,
} from "@/lib/use-analysis-cache";
import { AnalysisCacheStatus } from "@/components/common/AnalysisCacheStatus";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import type {
  EnvironmentResult,
  EnvironmentSeason,
  SkylinePosition,
  SolarGrade,
} from "./types";

const n0 = (v: number | null | undefined) =>
  v == null ? "—" : Math.round(v).toLocaleString();
const n1 = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: 1 });

/** 일조 등급 → 의미색 */
const GRADE_META: Record<SolarGrade, { color: string; bg: string; desc: string }> = {
  양호: { color: "#10b981", bg: "rgba(16,185,129,0.15)", desc: "동지 일조 ≥4h" },
  보통: { color: "#f59e0b", bg: "rgba(245,158,11,0.15)", desc: "동지 일조 2~4h" },
  불리: { color: "#ef4444", bg: "rgba(239,68,68,0.15)", desc: "동지 일조 <2h" },
};

/** 스카이라인 위치 → 의미색 */
const SKYLINE_META: Record<SkylinePosition, { color: string; bg: string; desc: string }> = {
  돌출: { color: "#f59e0b", bg: "rgba(245,158,11,0.15)", desc: "주변 대비 현저히 높음" },
  조화: { color: "#10b981", bg: "rgba(16,185,129,0.15)", desc: "주변 높이와 어울림" },
  매몰: { color: "#60a5fa", bg: "rgba(96,165,250,0.15)", desc: "주변 대비 낮음" },
};

const SEASONS: { key: EnvironmentSeason; label: string }[] = [
  { key: "winter", label: "동지" },
  { key: "summer", label: "하지" },
  { key: "equinox", label: "춘추분" },
];

const SEASON_LABEL: Record<EnvironmentSeason, string> = {
  winter: "동지",
  summer: "하지",
  equinox: "춘추분",
};

/** 지자체 조례 병행검토 결과(/regulation/analyze use_llm=false 부분 매핑). */
type OrdinanceLimit = {
  legal?: number | null;
  ordinance?: number | null;
  effective?: number | null;
  unit?: string;
};
type OrdinanceResult = {
  zone_type?: string | null;
  limits?: { bcr?: OrdinanceLimit; far?: OrdinanceLimit };
  hierarchy?: { level: string; items: { name: string; ref?: string; desc?: string }[] }[];
};

const lim0 = (v: number | null | undefined) =>
  v == null ? "—" : `${Math.round(v)}`;

/** 개방도 게이지(0~100). 반원형 SVG 아크. */
function OpennessGauge({ score }: { score: number }) {
  const clamped = Math.max(0, Math.min(100, score));
  const color = clamped >= 66 ? "#10b981" : clamped >= 33 ? "#f59e0b" : "#ef4444";
  // 반원: 180° 호. 좌(180°)→우(0°)
  const r = 46;
  const cx = 60;
  const cy = 60;
  const angle = Math.PI * (1 - clamped / 100); // 100→0rad(우), 0→π(좌)
  const ex = cx + Math.cos(angle) * r;
  const ey = cy - Math.sin(angle) * r;
  const arc = (frac: number, stroke: string, key: string) => {
    const a = Math.PI * (1 - frac);
    const x = cx + Math.cos(a) * r;
    const y = cy - Math.sin(a) * r;
    return (
      <path
        key={key}
        d={`M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${x} ${y}`}
        fill="none"
        stroke={stroke}
        strokeWidth="9"
        strokeLinecap="round"
      />
    );
  };
  return (
    <svg width="120" height="74" viewBox="0 0 120 74" aria-label={`개방도 ${clamped}점`}>
      {arc(1, "var(--surface-strong)", "track")}
      {arc(clamped / 100, color, "value")}
      <line x1={cx} y1={cy} x2={ex} y2={ey} stroke={color} strokeWidth="2.5" strokeLinecap="round" />
      <circle cx={cx} cy={cy} r="3.5" fill={color} />
      <text x={cx} y={cy - 12} textAnchor="middle" fontSize="20" fontWeight="900" fill="var(--text-primary)">
        {Math.round(clamped)}
      </text>
      <text x={cx} y={cy + 2} textAnchor="middle" fontSize="8" fill="var(--text-hint)">
        / 100
      </text>
    </svg>
  );
}

/** 높이 비교 바(대상 vs 이웃 평균/최고). max 기준 정규화. */
function HeightBar({ label, value, color, max }: { label: string; value: number; color: string; max: number }) {
  const w = max > 0 ? Math.max(2, Math.min(100, Math.round((value / max) * 100))) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] text-[var(--text-tertiary)]">{label}</span>
        <span className="text-[11px] font-bold text-[var(--text-secondary)]">{n1(value)} m</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-[var(--surface-strong)]">
        <div className="h-2 rounded-full" style={{ width: `${w}%`, background: color }} />
      </div>
    </div>
  );
}

/** 지자체 조례 병행검토 섹션. 건폐율·용적률(법정 vs 조례)·조례확인필요 배지를 표시.
 *  무자료/실패면 약식 안내 유지(무목업). */
function OrdinanceSection({ data }: { data: OrdinanceResult | null }) {
  const bcr = data?.limits?.bcr;
  const far = data?.limits?.far;
  const hasLimits =
    bcr?.legal != null || bcr?.ordinance != null || far?.legal != null || far?.ordinance != null;
  // 조례 강화(법정과 조례 한도가 다름)이면 조례확인필요
  const needsCheck =
    (bcr?.ordinance != null && bcr.ordinance !== bcr.legal) ||
    (far?.ordinance != null && far.ordinance !== far.legal);
  const ordHier = data?.hierarchy?.find((h) => h.level === "지자체 조례");

  return (
    <div className="mt-4 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
      <div className="mb-2 flex items-center justify-between">
        <p className="flex items-center gap-2 text-[11px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
          <Landmark className="size-3.5 shrink-0" aria-hidden /> 지자체 조례 병행검토
        </p>
        {needsCheck && (
          <span className="rounded-full border border-amber-500/40 bg-amber-500/15 px-2.5 py-1 text-[10px] font-black text-amber-300">
            조례 확인 필요
          </span>
        )}
      </div>

      {hasLimits ? (
        <>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] p-2.5">
              <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">건폐율 (법정 / 조례)</p>
              <p className="text-sm font-black text-[var(--text-primary)]">
                {lim0(bcr?.legal)}% <span className="text-[var(--text-hint)]">/</span>{" "}
                <span className={needsCheck ? "text-amber-300" : undefined}>{lim0(bcr?.ordinance)}%</span>
              </p>
            </div>
            <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] p-2.5">
              <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">용적률 (법정 / 조례)</p>
              <p className="text-sm font-black text-[var(--text-primary)]">
                {lim0(far?.legal)}% <span className="text-[var(--text-hint)]">/</span>{" "}
                <span className={needsCheck ? "text-amber-300" : undefined}>{lim0(far?.ordinance)}%</span>
              </p>
            </div>
          </div>
          {ordHier?.items && ordHier.items?.length > 0 && (
            <ul className="mt-2 space-y-0.5">
              {(ordHier.items ?? []).map((it, i) => (
                <li key={i} className="text-[10px] leading-relaxed text-[var(--text-hint)]">
                  • <b className="text-[var(--text-secondary)]">{it.name}</b>
                  {it.desc ? ` — ${it.desc}` : ""}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-secondary)]">
            정북 일조사선·높이 등은 본 환경분석의 약식 검토이며, 위 지자체 조례 한도와 병행 확인이 필요합니다.
          </p>
        </>
      ) : (
        <p className="text-[11px] leading-relaxed text-[var(--text-secondary)]">
          조례 한도 자료를 확보하지 못했습니다. 본 환경분석(정북 일조사선 등)은 약식이며 지자체 조례·완화규정을 별도 확인하세요.
        </p>
      )}
    </div>
  );
}

/**
 * 환경분석 산출 근거(EvidencePanel) — 응답(일조·조망·스카이라인) 수치로 산식 트레이스를 만든다.
 * 백엔드가 evidence/legal_refs를 반환하지 않는 약식 분석이라 basis 텍스트만 구성한다
 * (가짜값/가짜URL 0 · 법령 URL 프론트 조립 금지). 값이 없는 항목은 추가하지 않는다(빈행 방지).
 */
function buildEnvironmentEvidence(r: EnvironmentResult): EvidenceItem[] {
  const items: EvidenceItem[] = [];
  const solar = r.solar;
  const view = r.view;
  const skyline = r.skyline;

  if (solar) {
    const seasonLabel = solar.season_label ?? SEASON_LABEL[solar.season ?? "winter"];
    const hours = solar.sunlight_hours ?? solar.sunlight_hours_winter;
    if (hours != null) {
      items.push({
        label: `${seasonLabel} 일조시간`,
        value: `${n1(hours)}h (${solar.grade})`,
        basis: `천문 근사식 태양궤적으로 9~15시 약식 일조시간 산출 → ${GRADE_META[solar.grade]?.desc ?? ""}`,
      });
    }
    if (solar.north_setback?.applies) {
      items.push({
        label: "정북 일조사선 이격",
        value: `${n1(solar.north_setback.required_m)}m`,
        basis: solar.north_setback.detail || "정북 인접대지경계선 일조사선 기준 이격",
      });
    }
  }
  if (view) {
    items.push({
      label: "조망 개방도",
      value: `${Math.round(view.openness_score)}점`,
      basis: `8방위 개방도 평가 · 주변 가림 비율 ${n1(view.blocked_ratio_pct)}%`,
    });
  }
  if (skyline) {
    items.push({
      label: "스카이라인",
      value: skyline.position,
      basis: `대상 ${n1(skyline.subject_height_m)}m vs 주변 평균 ${n1(skyline.neighbor_avg_m)}m·최고 ${n1(skyline.neighbor_max_m)}m 비교`,
    });
  }
  return items;
}

export function EnvironmentAnalysisPanel({
  address,
  pnu,
}: {
  /** 상위 부지분석 화면에서 확보된 대상지 주소 */
  address?: string;
  pnu?: string | null;
}) {
  const [addr, setAddr] = useState(address ?? "");
  const [floorsInput, setFloorsInput] = useState("");
  const [heightInput, setHeightInput] = useState("");
  const [season, setSeason] = useState<EnvironmentSeason>("winter");
  const [res, setRes] = useState<EnvironmentResult | null>(null);
  const [ordinance, setOrdinance] = useState<OrdinanceResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  // 계절 자동 재요청 시 무한루프 방지(직전 요청 계절 기록)
  const lastSeasonRef = useRef<EnvironmentSeason | null>(null);

  // 영속 캐시: 주소·PNU·층수·높이·계절 불변이면 검증된 결과(환경+조례) 재사용,
  // 바뀌면 재분석 제안. (계절 토글은 기존 자동재요청 유지 — 명시적 사용자 조작)
  const signature = analysisSignature(
    (addr || address || "").trim(),
    pnu,
    floorsInput,
    heightInput,
    season,
  );
  const {
    cached,
    isFresh,
    isStale,
    at,
    save,
  } = useAnalysisCache<{ res: EnvironmentResult; ordinance: OrdinanceResult | null }>(
    "environment",
    signature,
  );
  const restoredRef = useRef(false);
  useEffect(() => {
    if (!res && cached?.res && !restoredRef.current) {
      restoredRef.current = true;
      lastSeasonRef.current = season;
      setRes(cached.res);
      setOrdinance(cached.ordinance ?? null);
    }
  }, [res, cached, season]);

  const run = useCallback(async () => {
    const a = (addr || address || "").trim();
    if (!a && !pnu) {
      setErr("대상지 주소를 입력하세요.");
      return;
    }
    setBusy(true);
    setErr(null);
    lastSeasonRef.current = season;
    try {
      const floors = floorsInput ? Number(floorsInput.replace(/[^0-9.\-]/g, "")) : null;
      const height = heightInput ? Number(heightInput.replace(/[^0-9.\-]/g, "")) : null;
      const designParams =
        (floors != null && !Number.isNaN(floors)) || (height != null && !Number.isNaN(height))
          ? {
              floors: floors != null && !Number.isNaN(floors) ? floors : null,
              height_m: height != null && !Number.isNaN(height) ? height : null,
            }
          : null;
      const d = await apiClient.post<EnvironmentResult>("/environment/analyze", {
        body: {
          address: a || null,
          pnu: pnu ?? null,
          design_params: designParams,
          season,
        },
      });
      if (d?.ok) {
        setRes(d);
        // 지자체 조례 병행검토(use_llm=false·동반 1회). 실패/무자료면 약식 안내 유지.
        let reg: OrdinanceResult | null = null;
        if (a) {
          try {
            reg = await apiClient.post<OrdinanceResult>("/regulation/analyze", {
              body: { address: a, pnu: pnu ?? null, use_llm: false },
            });
          } catch {
            reg = null;
          }
        }
        setOrdinance(reg);
        save({ res: d, ordinance: reg }); // 검증된 결과 영속 → 재방문 시 재사용
      } else {
        setRes(null);
        setOrdinance(null);
        setErr(d?.message || "환경분석 실패 — 좌표·필지 또는 주변 데이터를 확보하지 못했습니다.");
      }
    } catch {
      setRes(null);
      setErr("분석 요청 실패 — 네트워크 확인 후 다시 시도하세요.");
    } finally {
      setBusy(false);
    }
  }, [addr, address, pnu, floorsInput, heightInput, season, save]);

  // 계절 변경 자동 재요청: 이미 분석결과(res)가 있을 때만(첫 분석 전 자동실행 금지).
  // lastSeasonRef로 직전 요청 계절과 비교해 중복/무한루프 방지.
  useEffect(() => {
    if (!res || busy) return;
    if (lastSeasonRef.current === season) return;
    void run();
  }, [season, res, busy, run]);

  const inp =
    "h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

  const solar = res?.solar;
  const view = res?.view;
  const skyline = res?.skyline;
  const gradeMeta = solar ? GRADE_META[solar.grade] : null;
  const skyMeta = skyline ? SKYLINE_META[skyline.position] : null;
  // 선택 계절 라벨/일조시간(백엔드 season_label·sunlight_hours 우선, 구버전 winter 폴백)
  const solarSeasonLabel =
    solar?.season_label ?? SEASON_LABEL[solar?.season ?? season];
  const solarSunlightHours =
    solar?.sunlight_hours ?? solar?.sunlight_hours_winter;

  // 태양궤적: 지평선 위(고도>0)만 표기
  const sunData =
    solar?.sun_positions
      ?.filter((p) => p.altitude_deg > -2)
      .map((p) => ({
        hour: p.hour,
        alt: Number(p.altitude_deg.toFixed(1)),
        az: Math.round(p.azimuth_deg),
      })) ?? [];

  const skyMax = skyline ? Math.max(skyline.subject_height_m, skyline.neighbor_max_m, 1) : 1;

  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
      <CardContent className="p-6">
        <div className="flex items-center gap-3">
          <Sun className="size-7 shrink-0 text-amber-500" aria-hidden />
          <div>
            <h2 className="flex items-center gap-2 text-base font-black text-[var(--text-primary)]">
              환경분석 (일조·조망·스카이라인)
              <span className="rounded-full border border-amber-500/40 bg-amber-500/15 px-2 py-0.5 text-[10px] font-black tracking-widest text-amber-300">
                약식
              </span>
            </h2>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              천문 근사식 태양궤적·약식 일영·정북 일조사선으로 환경을 추정합니다. <b>참고용</b>이며 정밀 일조분석/측량이 아닙니다.
            </p>
          </div>
        </div>

        {/* 입력 */}
        <div className="mt-4 flex flex-wrap items-end gap-2">
          {/* bare input 은 주소검색 자체가 안 되는 결함 — 전 모듈 표준 ProjectAddressInput 으로 통일.
              ★writeToContext={false} 필수: 이 패널은 상위 부지분석 주소를 받아 쓰는 탐색용 보조면이라,
                여기 검색이 활성 프로젝트 SSOT(address·pnu·zoneCode·조례)를 덮으면 안 된다
                (BulkParcelBatchPanel 의 single+writeToContext=false 쌍 관례). */}
          <ProjectAddressInput
            value={addr}
            onChange={setAddr}
            label="대상지 주소"
            placeholder="지번/도로명 주소"
            className="min-w-[200px] flex-1"
            hideProjectPicker
            single
            writeToContext={false}
          />
          <label className="w-24 text-xs text-[var(--text-secondary)]">
            층수(선택)
            <input
              className={`${inp} mt-1`}
              value={floorsInput}
              onChange={(e) => setFloorsInput(e.target.value)}
              placeholder="자동"
              inputMode="numeric"
            />
          </label>
          <label className="w-28 text-xs text-[var(--text-secondary)]">
            높이(m, 선택)
            <input
              className={`${inp} mt-1`}
              value={heightInput}
              onChange={(e) => setHeightInput(e.target.value)}
              placeholder="자동"
              inputMode="decimal"
            />
          </label>
          <div className="text-xs text-[var(--text-secondary)]">
            계절
            <div className="mt-1 inline-flex overflow-hidden rounded-lg border border-[var(--line)]">
              {SEASONS.map((s) => (
                <button
                  key={s.key}
                  type="button"
                  onClick={() => setSeason(s.key)}
                  className={`px-3 py-2 text-xs font-bold transition-colors ${
                    season === s.key
                      ? "bg-[var(--accent-strong)] text-white"
                      : "bg-[var(--surface-strong)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {s.label}
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={() => void run()}
            disabled={busy}
            className="inline-flex h-10 items-center justify-center gap-1.5 whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "환경 분석 중…" : (<><Sun className="size-4" aria-hidden />환경 분석</>)}
          </button>
        </div>

        {err && (
          <p className="mt-3 inline-flex items-baseline gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            <AlertTriangle className="size-3.5 self-center shrink-0" aria-hidden /> {err}
          </p>
        )}

        <AnalysisCacheStatus
          isFresh={isFresh && !!res}
          isStale={isStale && !!res}
          at={at}
          relativeLabel={relativeKoreanTime(at)}
          onRerun={() => void run()}
          busy={busy}
          rerunLabel="재분석"
        />

        {res?.ok && (
          <>
            {/* 메타 */}
            <div className="mt-5 flex flex-wrap items-center gap-2 text-[11px]">
              {res.zone_type && (
                <span className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1 text-[var(--text-secondary)]">
                  용도지역 <b className="text-[var(--text-primary)]">{res.zone_type}</b>
                </span>
              )}
              {res.subject?.height_m != null && (
                <span className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1 text-[var(--text-secondary)]">
                  대상높이 <b className="text-[var(--text-primary)]">{n1(res.subject.height_m)}m</b>
                </span>
              )}
              {res.subject?.neighbor_count != null && (
                <span className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1 text-[var(--text-secondary)]">
                  주변필지 <b className="text-[var(--text-primary)]">{n0(res.subject.neighbor_count)}</b>
                </span>
              )}
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-3">
              {/* ── 일조 ── */}
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-[11px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                    일조
                  </p>
                  {solar && gradeMeta && (
                    <span
                      className="rounded-full px-2.5 py-1 text-xs font-black"
                      style={{ color: gradeMeta.color, background: gradeMeta.bg }}
                    >
                      {solar.grade}
                    </span>
                  )}
                </div>

                {/* 태양궤적(시간축 고도 곡선) */}
                <div className="h-36 w-full">
                  {sunData.length > 1 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={sunData} margin={{ top: 4, right: 6, bottom: 0, left: -20 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                        <XAxis
                          dataKey="hour"
                          stroke="var(--text-hint)"
                          tick={{ fontSize: 9 }}
                          tickFormatter={(v) => `${v}시`}
                        />
                        <YAxis
                          stroke="var(--text-hint)"
                          tick={{ fontSize: 9 }}
                          domain={[0, "dataMax + 5"]}
                          tickFormatter={(v) => `${Math.round(Number(v))}°`}
                        />
                        <ReferenceLine y={0} stroke="var(--line-strong)" strokeDasharray="2 2" />
                        <Tooltip
                          contentStyle={{
                            background: "var(--surface-strong)",
                            border: "1px solid var(--line)",
                            borderRadius: 8,
                            fontSize: 11,
                          }}
                          labelStyle={{ color: "var(--text-secondary)" }}
                          formatter={(v, _name, item) => [
                            `고도 ${v as number}° · 방위 ${(item?.payload as { az?: number })?.az ?? "—"}°`,
                            "태양",
                          ]}
                          labelFormatter={(l) => `${l}시`}
                        />
                        <Line
                          type="monotone"
                          dataKey="alt"
                          stroke="#f59e0b"
                          strokeWidth={2.5}
                          dot={{ r: 2, fill: "#f59e0b" }}
                          activeDot={{ r: 4 }}
                        />
                      </LineChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex h-full items-center justify-center text-[11px] text-[var(--text-hint)]">
                      태양궤적 표본 부족
                    </div>
                  )}
                </div>
                <p className="mt-1 text-center text-[9px] text-[var(--text-hint)]">시간축 태양고도(°) 궤적</p>

                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div className="rounded-lg bg-[var(--surface-muted)] p-2.5 text-center border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">{solarSeasonLabel} 일조시간</p>
                    <p className="text-sm font-black text-[var(--text-primary)]">
                      {n1(solarSunlightHours)} h
                    </p>
                  </div>
                  <div className="rounded-lg bg-[var(--surface-muted)] p-2.5 text-center border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">등급</p>
                    <p className="text-sm font-black" style={{ color: gradeMeta?.color }}>
                      {solar?.grade ?? "—"}
                    </p>
                  </div>
                </div>

                {/* 정북 일조사선 */}
                <div className="mt-3 rounded-lg border border-[var(--line)] bg-[var(--surface-muted)] p-2.5">
                  <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">정북 일조사선</p>
                  {solar?.north_setback?.applies ? (
                    <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                      <b className="text-[var(--text-primary)]">
                        이격 {n1(solar.north_setback.required_m)}m
                      </b>{" "}
                      · {solar.north_setback.detail}
                    </p>
                  ) : (
                    <p className="mt-0.5 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                      {solar?.north_setback?.detail || "상업지역 등 미적용"}
                    </p>
                  )}
                </div>

                {solar?.summary && (
                  <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-secondary)]">{solar.summary}</p>
                )}
              </div>

              {/* ── 조망 ── */}
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <p className="mb-3 text-[11px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                  조망
                </p>
                <div className="flex flex-col items-center">
                  <OpennessGauge score={view?.openness_score ?? 0} />
                  <p className="mt-1 text-[9px] text-[var(--text-hint)]">개방도 (높을수록 트임)</p>
                </div>
                <div className="mt-3 rounded-lg bg-[var(--surface-muted)] p-2.5 text-center border border-[var(--line)]">
                  <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">가림 비율</p>
                  <p className="text-sm font-black text-[var(--text-primary)]">{n1(view?.blocked_ratio_pct)}%</p>
                </div>
                <div className="mt-3">
                  <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">트인 방향</p>
                  <div className="mt-1.5 flex flex-wrap gap-1.5">
                    {view?.best_directions && view.best_directions?.length > 0 ? (
                      (view.best_directions ?? []).map((d, i) => (
                        <span
                          key={`${d}-${i}`}
                          className="inline-flex items-center gap-1 rounded-full border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-bold text-emerald-300"
                        >
                          <Compass className="size-3 shrink-0" aria-hidden /> {d}
                        </span>
                      ))
                    ) : (
                      <span className="text-[11px] text-[var(--text-hint)]">트인 방향 없음(주변 가림)</span>
                    )}
                  </div>
                </div>
                {view?.summary && (
                  <p className="mt-3 text-[10px] leading-relaxed text-[var(--text-secondary)]">{view.summary}</p>
                )}
              </div>

              {/* ── 스카이라인 ── */}
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-[11px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                    스카이라인
                  </p>
                  {skyline && skyMeta && (
                    <span
                      className="rounded-full px-2.5 py-1 text-xs font-black"
                      style={{ color: skyMeta.color, background: skyMeta.bg }}
                    >
                      {skyline.position}
                    </span>
                  )}
                </div>
                <p className="text-[10px] text-[var(--text-hint)]">{skyMeta?.desc}</p>
                <div className="mt-3 grid gap-3">
                  <HeightBar
                    label="대상 건물"
                    value={skyline?.subject_height_m ?? 0}
                    color="var(--accent-strong)"
                    max={skyMax}
                  />
                  <HeightBar
                    label="주변 평균"
                    value={skyline?.neighbor_avg_m ?? 0}
                    color="#60a5fa"
                    max={skyMax}
                  />
                  <HeightBar
                    label="주변 최고"
                    value={skyline?.neighbor_max_m ?? 0}
                    color="#a78bfa"
                    max={skyMax}
                  />
                </div>
                {skyline?.summary && (
                  <p className="mt-3 text-[10px] leading-relaxed text-[var(--text-secondary)]">{skyline.summary}</p>
                )}
              </div>
            </div>

            {/* 정직성 배지(note·basis)·sources */}
            {res.badges?.note && (
              <p className="mt-4 inline-flex items-baseline gap-1.5 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] leading-relaxed text-amber-200/90">
                <AlertTriangle className="size-3.5 self-center shrink-0" aria-hidden /> {res.badges.note}
              </p>
            )}
            {res.badges?.basis && res.badges.basis?.length > 0 && (
              <ul className="mt-2 space-y-0.5">
                {(res.badges.basis ?? []).map((b, i) => (
                  <li key={i} className="text-[10px] leading-relaxed text-[var(--text-hint)]">
                    • {b}
                  </li>
                ))}
              </ul>
            )}
            {res.sources && res.sources?.length > 0 && (
              <p className="mt-2 text-[10px] text-[var(--text-hint)]">출처: {res.sources.join(" · ")}</p>
            )}

            {/* 산출 근거(EvidencePanel) — 일조·조망·스카이라인 수치의 산식을 한 줄씩(가짜값/가짜URL 0).
                약식 분석이라 basis 텍스트만(법령 URL 프론트 조립 금지). 빈 items면 미렌더. */}
            <EvidencePanel className="mt-3" items={buildEnvironmentEvidence(res)} title="환경분석 산출 근거" />

            {/* ── 지자체 조례 병행검토 ── */}
            <OrdinanceSection data={ordinance} />
          </>
        )}
      </CardContent>
    </Card>
  );
}
