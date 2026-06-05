"use client";

/**
 * Flagship C-1 — 지형분석 패널(경사도·토공량·지형단면 프로파일).
 * 광역 DEM(수치표고)로 필지 격자 표고를 추정 → 경사도·토공량·지형단면을 산출한다.
 *
 * ⚠ EXPERIMENTAL: 검증된 정밀측량이 아니다. 표고소스·해상도·신뢰도를 정직 표기하고,
 *   소형필지+저해상도면 note로 한계를 명시한다(할루시네이션 방지 철학).
 */

import { useCallback, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiClient } from "@/lib/api-client";
import type {
  EarthworkBalance,
  SlopeClass,
  TerrainResult,
} from "./types";

const n0 = (v: number | null | undefined) =>
  v == null ? "—" : Math.round(v).toLocaleString();
const n1 = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: 1 });
const pct1 = (v: number | null | undefined) =>
  v == null ? "—" : `${v.toFixed(1)}%`;

/** 경사도 등급 → 의미색·설명 */
const SLOPE_META: Record<SlopeClass, { color: string; bg: string; desc: string }> = {
  평지: { color: "#10b981", bg: "rgba(16,185,129,0.15)", desc: "개발 용이 (<5%)" },
  완경사: { color: "#22c55e", bg: "rgba(34,197,94,0.15)", desc: "양호 (5~15%)" },
  경사: { color: "#f59e0b", bg: "rgba(245,158,11,0.15)", desc: "토공·옹벽 검토 (15~30%)" },
  급경사: { color: "#ef4444", bg: "rgba(239,68,68,0.15)", desc: "개발 제약 큼 (>30%)" },
};

const BALANCE_META: Record<EarthworkBalance, { color: string; bg: string }> = {
  절토우세: { color: "#f59e0b", bg: "rgba(245,158,11,0.15)" },
  성토우세: { color: "#60a5fa", bg: "rgba(96,165,250,0.15)" },
  균형: { color: "#10b981", bg: "rgba(16,185,129,0.15)" },
};

/** 16방위 한글 라벨 */
function aspectLabel(deg: number | null | undefined): string {
  if (deg == null) return "—";
  const dirs = ["북", "북동", "동", "남동", "남", "남서", "서", "북서"];
  const i = Math.round(((deg % 360) + 360) % 360 / 45) % 8;
  return `${dirs[i]} (${Math.round(deg)}°)`;
}

/** 사면 방향 나침반(SVG). 향(aspect) 방향으로 바늘 표시. */
function AspectCompass({ deg }: { deg: number | null | undefined }) {
  const has = deg != null;
  const rad = ((((deg ?? 0) % 360) + 360) % 360 - 90) * (Math.PI / 180);
  const cx = 28;
  const cy = 28;
  const r = 20;
  const x = cx + Math.cos(rad) * r;
  const y = cy + Math.sin(rad) * r;
  return (
    <svg width="56" height="56" viewBox="0 0 56 56" aria-label="사면 향(aspect)">
      <circle cx={cx} cy={cy} r={r + 3} fill="none" stroke="var(--line)" strokeWidth="1.5" />
      <text x={cx} y="9" textAnchor="middle" className="fill-[var(--text-hint)]" fontSize="8">N</text>
      <text x={cx} y="54" textAnchor="middle" className="fill-[var(--text-hint)]" fontSize="8">S</text>
      {has ? (
        <>
          <line x1={cx} y1={cy} x2={x} y2={y} stroke="var(--accent-strong)" strokeWidth="2.5" strokeLinecap="round" />
          <circle cx={x} cy={y} r="3" fill="var(--accent-strong)" />
        </>
      ) : (
        <text x={cx} y={cy + 3} textAnchor="middle" className="fill-[var(--text-hint)]" fontSize="9">N/A</text>
      )}
      <circle cx={cx} cy={cy} r="2.5" fill="var(--text-secondary)" />
    </svg>
  );
}

/** 토공량 비교 바(절토/성토/순). max 기준 정규화. */
function VolumeBar({ label, value, color, max }: { label: string; value: number; color: string; max: number }) {
  const w = max > 0 ? Math.max(2, Math.min(100, Math.round((value / max) * 100))) : 0;
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <span className="text-[11px] text-[var(--text-tertiary)]">{label}</span>
        <span className="text-[11px] font-bold text-[var(--text-secondary)]">{n0(value)} m³</span>
      </div>
      <div className="mt-1 h-2 rounded-full bg-[var(--surface-strong)]">
        <div className="h-2 rounded-full" style={{ width: `${w}%`, background: color }} />
      </div>
    </div>
  );
}

export function TerrainAnalysisPanel({
  address,
  pnu,
}: {
  /** 상위 부지분석 화면에서 확보된 대상지 주소 */
  address?: string;
  pnu?: string | null;
}) {
  const [addr, setAddr] = useState(address ?? "");
  const [targetInput, setTargetInput] = useState("");
  const [bearingInput, setBearingInput] = useState("");
  const [res, setRes] = useState<TerrainResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const run = useCallback(async () => {
    const a = (addr || address || "").trim();
    if (!a && !pnu) {
      setErr("대상지 주소를 입력하세요.");
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const target = targetInput ? Number(targetInput.replace(/[^0-9.\-]/g, "")) : null;
      const bearing = bearingInput ? Number(bearingInput.replace(/[^0-9.\-]/g, "")) : null;
      const d = await apiClient.post<TerrainResult>("/terrain/analyze", {
        body: {
          address: a || null,
          pnu: pnu ?? null,
          target_level_m: target != null && !Number.isNaN(target) ? target : null,
          section_bearing_deg: bearing != null && !Number.isNaN(bearing) ? bearing : null,
        },
      });
      if (d?.ok) setRes(d);
      else {
        setRes(null);
        setErr(d?.message || "지형분석 실패 — 좌표·필지 또는 표고 데이터를 확보하지 못했습니다.");
      }
    } catch {
      setRes(null);
      setErr("분석 요청 실패 — 네트워크 확인 후 다시 시도하세요.");
    } finally {
      setBusy(false);
    }
  }, [addr, address, pnu, targetInput, bearingInput]);

  const inp =
    "h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

  const slope = res?.slope;
  const earth = res?.earthwork;
  const sec = res?.cross_section;
  const slopeMeta = slope ? SLOPE_META[slope.class] : null;
  const balMeta = earth ? BALANCE_META[earth.balance] : null;
  const volMax = earth ? Math.max(earth.cut_volume_m3, earth.fill_volume_m3, 1) : 1;
  const confPct = res?.confidence != null ? Math.round(res.confidence * 100) : null;

  const chartData =
    sec?.points?.map((p) => ({ dist: Math.round(p.dist_m), elev: Number(p.elev_m.toFixed(2)) })) ?? [];

  return (
    <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
      <CardContent className="p-6">
        <div className="flex items-center gap-3">
          <span className="text-2xl">⛰️</span>
          <div>
            <h2 className="flex items-center gap-2 text-base font-black text-[var(--text-primary)]">
              지형분석 (경사도·토공량·단면)
              <span className="rounded-full border border-violet-500/40 bg-violet-500/15 px-2 py-0.5 text-[10px] font-black tracking-widest text-violet-300">
                EXPERIMENTAL
              </span>
            </h2>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
              광역 수치표고(DEM)로 필지 지형을 근사 추정합니다. <b>참고용</b>이며 검증된 정밀측량이 아닙니다.
            </p>
          </div>
        </div>

        {/* 입력 */}
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <label className="min-w-[220px] flex-1 text-xs text-[var(--text-secondary)]">
            대상지 주소
            <input
              className={`${inp} mt-1`}
              value={addr}
              onChange={(e) => setAddr(e.target.value)}
              placeholder="지번/도로명 주소"
            />
          </label>
          <label className="w-32 text-xs text-[var(--text-secondary)]">
            계획고(m, 선택)
            <input
              className={`${inp} mt-1`}
              value={targetInput}
              onChange={(e) => setTargetInput(e.target.value)}
              placeholder="자동(평균)"
              inputMode="decimal"
            />
          </label>
          <label className="w-32 text-xs text-[var(--text-secondary)]">
            단면방위(°, 선택)
            <input
              className={`${inp} mt-1`}
              value={bearingInput}
              onChange={(e) => setBearingInput(e.target.value)}
              placeholder="자동(최대경사)"
              inputMode="numeric"
            />
          </label>
          <button
            onClick={() => void run()}
            disabled={busy}
            className="h-10 whitespace-nowrap rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50"
          >
            {busy ? "지형 분석 중…" : "⛰️ 지형 분석"}
          </button>
        </div>

        {err && (
          <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
            ⚠ {err}
          </p>
        )}

        {res?.ok && (
          <>
            {/* 표고 소스·메타 */}
            <div className="mt-5 flex flex-wrap items-center gap-2 text-[11px]">
              <span className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1 text-[var(--text-secondary)]">
                표고소스 <b className="text-[var(--text-primary)]">{res.elevation_source ?? "—"}</b>
              </span>
              <span className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1 text-[var(--text-secondary)]">
                해상도 <b className="text-[var(--text-primary)]">{res.resolution_m != null ? `${n1(res.resolution_m)}m` : "—"}</b>
              </span>
              <span className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1 text-[var(--text-secondary)]">
                표본 <b className="text-[var(--text-primary)]">{n0(res.sample_count)}</b>
              </span>
              {res.area_sqm != null && (
                <span className="rounded-full border border-[var(--line)] bg-[var(--surface-soft)] px-2.5 py-1 text-[var(--text-secondary)]">
                  면적 <b className="text-[var(--text-primary)]">{n0(res.area_sqm)}m²</b>
                </span>
              )}
              {confPct != null && (
                <span
                  className="rounded-full px-2.5 py-1 font-bold"
                  style={{
                    color: confPct >= 66 ? "#10b981" : confPct >= 33 ? "#f59e0b" : "#ef4444",
                    background:
                      confPct >= 66
                        ? "rgba(16,185,129,0.12)"
                        : confPct >= 33
                          ? "rgba(245,158,11,0.12)"
                          : "rgba(239,68,68,0.12)",
                  }}
                >
                  신뢰도 {confPct}%
                </span>
              )}
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-3">
              {/* ── 경사도 ── */}
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <p className="mb-3 text-[11px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                  경사도
                </p>
                <div className="flex items-center gap-3">
                  <AspectCompass deg={slope?.aspect_deg} />
                  <div className="flex-1">
                    {slope && slopeMeta && (
                      <span
                        className="inline-block rounded-full px-2.5 py-1 text-xs font-black"
                        style={{ color: slopeMeta.color, background: slopeMeta.bg }}
                      >
                        {slope.class}
                      </span>
                    )}
                    <p className="mt-1 text-[10px] text-[var(--text-hint)]">{slopeMeta?.desc}</p>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div className="rounded-lg bg-[var(--surface-muted)] p-2.5 text-center border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">평균경사</p>
                    <p className="text-sm font-black text-[var(--text-primary)]">{pct1(slope?.mean_pct)}</p>
                  </div>
                  <div className="rounded-lg bg-[var(--surface-muted)] p-2.5 text-center border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">최대경사</p>
                    <p className="text-sm font-black text-[var(--text-primary)]">{pct1(slope?.max_pct)}</p>
                  </div>
                  <div className="col-span-2 rounded-lg bg-[var(--surface-muted)] p-2.5 border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">사면 향(aspect)</p>
                    <p className="text-xs font-bold text-[var(--text-primary)]">{aspectLabel(slope?.aspect_deg)}</p>
                  </div>
                </div>
                {slope?.detail && (
                  <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-secondary)]">{slope.detail}</p>
                )}
              </div>

              {/* ── 토공량 ── */}
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-[11px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                    토공량
                  </p>
                  {earth && balMeta && (
                    <span
                      className="rounded-full px-2 py-0.5 text-[10px] font-black"
                      style={{ color: balMeta.color, background: balMeta.bg }}
                    >
                      {earth.balance}
                    </span>
                  )}
                </div>
                <div className="grid gap-3">
                  <VolumeBar label="절토(Cut)" value={earth?.cut_volume_m3 ?? 0} color="#f59e0b" max={volMax} />
                  <VolumeBar label="성토(Fill)" value={earth?.fill_volume_m3 ?? 0} color="#60a5fa" max={volMax} />
                </div>
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <div className="rounded-lg bg-[var(--surface-muted)] p-2.5 text-center border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">순 토공(Net)</p>
                    <p className="text-sm font-black text-[var(--text-primary)]">{n0(earth?.net_m3)} m³</p>
                  </div>
                  <div className="rounded-lg bg-[var(--surface-muted)] p-2.5 text-center border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">기준고</p>
                    <p className="text-sm font-black text-[var(--text-primary)]">{n1(earth?.base_level_m)} m</p>
                  </div>
                </div>
                {earth?.detail && (
                  <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-secondary)]">{earth.detail}</p>
                )}
              </div>

              {/* ── 지형단면 ── */}
              <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
                <div className="mb-3 flex items-center justify-between">
                  <p className="text-[11px] font-black uppercase tracking-widest text-[var(--text-tertiary)]">
                    지형단면
                  </p>
                  {sec && (
                    <span className="text-[10px] text-[var(--text-hint)]">
                      방위 {Math.round(sec.bearing_deg)}° · 길이 {n0(sec.length_m)}m
                    </span>
                  )}
                </div>
                <div className="h-40 w-full">
                  {chartData.length > 1 ? (
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
                        <defs>
                          <linearGradient id="terrainElev" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor="var(--accent-strong)" stopOpacity={0.5} />
                            <stop offset="100%" stopColor="var(--accent-strong)" stopOpacity={0.05} />
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                        <XAxis
                          dataKey="dist"
                          stroke="var(--text-hint)"
                          tick={{ fontSize: 9 }}
                          tickFormatter={(v) => `${v}m`}
                        />
                        <YAxis
                          stroke="var(--text-hint)"
                          tick={{ fontSize: 9 }}
                          domain={["dataMin - 1", "dataMax + 1"]}
                          tickFormatter={(v) => `${Math.round(Number(v))}`}
                        />
                        <Tooltip
                          contentStyle={{
                            background: "var(--surface-strong)",
                            border: "1px solid var(--line)",
                            borderRadius: 8,
                            fontSize: 11,
                          }}
                          labelStyle={{ color: "var(--text-secondary)" }}
                          formatter={(v) => [`${v as number} m`, "표고"]}
                          labelFormatter={(l) => `거리 ${l} m`}
                        />
                        <Area
                          type="monotone"
                          dataKey="elev"
                          stroke="var(--accent-strong)"
                          strokeWidth={2}
                          fill="url(#terrainElev)"
                        />
                      </AreaChart>
                    </ResponsiveContainer>
                  ) : (
                    <div className="flex h-full items-center justify-center text-[11px] text-[var(--text-hint)]">
                      단면 표본 부족
                    </div>
                  )}
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2">
                  <div className="rounded-lg bg-[var(--surface-muted)] p-2 text-center border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">최저</p>
                    <p className="text-xs font-bold text-blue-400">{n1(sec?.min_elev_m)}m</p>
                  </div>
                  <div className="rounded-lg bg-[var(--surface-muted)] p-2 text-center border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">최고</p>
                    <p className="text-xs font-bold text-red-400">{n1(sec?.max_elev_m)}m</p>
                  </div>
                  <div className="rounded-lg bg-[var(--surface-muted)] p-2 text-center border border-[var(--line)]">
                    <p className="text-[8px] font-black uppercase text-[var(--text-hint)]">고저차</p>
                    <p className="text-xs font-bold text-[var(--text-primary)]">{n1(sec?.relief_m)}m</p>
                  </div>
                </div>
              </div>
            </div>

            {/* note·sources */}
            {res.note && (
              <p className="mt-4 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-3 py-2 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                ℹ {res.note}
              </p>
            )}
            {res.sources && res.sources.length > 0 && (
              <p className="mt-2 text-[10px] text-[var(--text-hint)]">
                출처: {res.sources.join(" · ")}
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
