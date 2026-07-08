"use client";

/**
 * 대지지분(대지권) 분석 모달 — 공동주택/집합건물 호별 대지지분 + 토지조서 정합 검증.
 *
 * 토지조서는 '실토지면적' 확보가 목적. 한 필지에 공동주택·다세대·집합상가가 있으면
 * 각 세대(동·호)에 대지지분이 배정되므로 Σ세대 대지지분 = 대지(필지)면적이어야 정확하다.
 * 건축물대장 표제부(대지면적)+전유공용면적(호별 전유면적)으로 호별 대지지분을 전유 비례
 * 산정하고, 합계 정합을 검증한다. /api/v1/zoning/land-share.
 * 무목업: 전유부 무자료=토지/단독으로 정직 분기(is_aggregate=false).
 */

import { useEffect, useState } from "react";
import { AlertTriangle, Building2, CheckCircle2 } from "lucide-react";
import { apiV1BaseUrl } from "@/lib/api-client";
import { PYEONG_SQM } from "@/lib/formatters";

const py = (sqm: number | null | undefined) =>
  sqm == null ? "—" : `${(sqm / PYEONG_SQM).toLocaleString(undefined, { maximumFractionDigits: 2 })}평`;
const sm = (v: number | null | undefined) =>
  v == null ? "—" : `${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}㎡`;

type Unit = {
  dong: string; ho: string;
  exclusive_area_sqm: number; exclusive_pyeong: number;
  share_ratio: number; land_share_sqm: number; land_share_pyeong: number; purpose: string;
};
type Result = {
  is_aggregate: boolean; pnu?: string; address?: string; reason?: string;
  plat_area_sqm?: number | null; plat_area_pyeong?: number | null;
  unit_count?: number; title_unit_count?: number | null; total_exclusive_sqm?: number;
  building_name?: string; main_purpose?: string;
  units?: Unit[];
  validation?: {
    sum_land_share_sqm: number; plat_area_sqm: number;
    sum_match: boolean; count_match: boolean; count_note: string; reliable: boolean; method: string;
  };
};

export type LandShareUnit = {
  unit_label: string; dong: string; ho: string;
  exclusive_area_sqm: number; land_share_sqm: number; share_ratio: number; purpose: string;
};

export function LandShareModal({
  jibun, pnu, onClose, onApplyArea, onExpandUnits,
}: {
  jibun: string; pnu?: string | null;
  onClose: () => void;
  onApplyArea: (platAreaSqm: number) => void;
  /** 세대별로 토지조서에 펼쳐 반영(부모 필지 보존·하단에 세대행 중첩 배열) — 실별 대지지분·전유면적을 행으로 기록 */
  onExpandUnits?: (units: LandShareUnit[], buildingName: string) => void;
}) {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true); setError(null);
      try {
        const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
        const res = await fetch(`${apiV1BaseUrl()}/zoning/land-share`, {
          method: "POST",
          headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
          body: JSON.stringify(pnu && pnu.length >= 19 ? { pnu } : { address: jibun }),
        });
        const d: Result = await res.json();
        if (!cancelled) setData(d);
      } catch {
        if (!cancelled) setError("대지지분 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [jibun, pnu]);

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="max-h-[88vh] w-full max-w-3xl overflow-y-auto rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface)] p-6 shadow-[var(--shadow-lg)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="inline-flex items-center gap-1.5 cc-label text-[var(--accent-strong)]"><Building2 className="size-4" aria-hidden />대지지분(대지권) 분석</p>
            <h2 className="mt-1 text-base font-black text-[var(--text-primary)]">{jibun}</h2>
            <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
              건축물대장(표제부·전유공용면적) 기반 세대별 대지지분 — Σ세대 대지지분 = 대지면적 정합 검증
            </p>
          </div>
          <button onClick={onClose} className="shrink-0 text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">✕</button>
        </div>

        {loading && <p className="mt-6 text-sm text-[var(--text-secondary)]">건축물대장 조회 중…</p>}
        {error && <p className="mt-6 text-sm text-[var(--status-error)]">{error}</p>}

        {!loading && !error && data && !data.is_aggregate && (
          <div className="mt-5 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 text-sm leading-relaxed text-[var(--text-secondary)]">
            <p className="font-bold text-[var(--text-primary)]">집합건물(공동주택·다세대·집합상가)이 아닙니다.</p>
            <p className="mt-1">{data.reason || "전유부 미확인 — 토지(나대지)·단독건물입니다."}</p>
            {data.plat_area_sqm != null && (
              <p className="mt-2">필지(대지)면적: <b className="text-[var(--text-primary)]">{sm(data.plat_area_sqm)}</b> ({py(data.plat_area_sqm)}) — 이 면적 자체가 실토지면적입니다(세대 대지지분 분할 없음).</p>
            )}
          </div>
        )}

        {!loading && !error && data && data.is_aggregate && (
          <>
            {/* 요약 + 정합 검증 */}
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                ["대지면적(실토지)", `${sm(data.plat_area_sqm)}`],
                ["세대수(전유부)", `${data.unit_count ?? 0}호${data.title_unit_count ? ` / 표제부 ${data.title_unit_count}` : ""}`],
                ["전유면적 합(공용제외)", `${sm(data.total_exclusive_sqm)}`],
                ["건물용도", data.main_purpose || "—"],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                  <p className="cc-label">{k}</p>
                  <p className="cc-num mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v}</p>
                </div>
              ))}
            </div>

            {data.validation && (
              <div className={`mt-4 rounded-xl border px-4 py-3 text-xs leading-relaxed ${
                data.validation.reliable
                  ? "border-[var(--status-success)]/30 bg-[color-mix(in_srgb,var(--status-success)_10%,transparent)] text-[var(--status-success)]"
                  : "border-[var(--status-warning)]/30 bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)] text-[var(--status-warning)]"
              }`}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <span className="flex items-center gap-2">
                    <span>{data.validation.reliable ? <CheckCircle2 className="size-4" aria-hidden /> : <AlertTriangle className="size-4" aria-hidden />}</span>
                    <span>
                      {/* 합계 일치는 비례배분이라 정의상 성립 → '배분 완료'로 정직 표기(정확성 증명 아님) */}
                      Σ세대 대지지분 <b>{sm(data.validation.sum_land_share_sqm)}</b> = 대지면적 <b>{sm(data.validation.plat_area_sqm)}</b> 비례배분 완료
                    </span>
                  </span>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    {onExpandUnits && (data.units?.length ?? 0) > 0 && (
                      <button
                        onClick={() => {
                          const us: LandShareUnit[] = (data.units || []).map((u) => ({
                            unit_label: [u.dong, u.ho].filter(Boolean).join(" "),
                            dong: u.dong, ho: u.ho,
                            exclusive_area_sqm: u.exclusive_area_sqm, land_share_sqm: u.land_share_sqm,
                            share_ratio: u.share_ratio, purpose: u.purpose,
                          }));
                          onExpandUnits(us, data.building_name || "");
                          onClose();
                        }}
                        title="현재 필지 행을 세대별 행으로 펼쳐 토지조서에 반영(각 행=동·호·세대면적·대지지분). Σ대지지분=실토지면적"
                        className="rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-black text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]"
                      >
                        세대별 펼쳐 반영
                      </button>
                    )}
                    {data.plat_area_sqm != null && data.plat_area_sqm > 0 && (
                      <button
                        onClick={() => { onApplyArea(data.plat_area_sqm as number); onClose(); }}
                        className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-black text-white hover:opacity-90"
                      >
                        실토지면적으로 반영
                      </button>
                    )}
                  </div>
                </div>
                {/* 실제로 실패할 수 있는 교차검증: 표제부 세대수 vs 전유부 호수 */}
                <p className="mt-1.5 flex items-start gap-1.5 border-t border-current/15 pt-1.5 opacity-90">
                  <span>{data.validation.count_match ? <CheckCircle2 className="size-3.5 shrink-0" aria-hidden /> : <AlertTriangle className="size-3.5 shrink-0" aria-hidden />}</span>
                  <span>{data.validation.count_note}</span>
                </p>
              </div>
            )}

            {/* 호별 대지지분 표 */}
            <div className="mt-4 overflow-x-auto rounded-xl border border-[var(--line)]">
              <table className="w-full min-w-[560px] text-[11px]">
                <thead>
                  <tr className="border-b border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-tertiary)]">
                    {["#", "동", "호", "전유면적", "지분율", "대지지분(㎡)", "대지지분(평)", "용도"].map((h) => (
                      <th key={h} className="px-2 py-2 text-left font-semibold whitespace-nowrap">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(data.units || []).map((u, i) => (
                    <tr key={`${u.dong}-${u.ho}-${i}`} className="border-b border-[var(--line)]/50">
                      <td className="px-2 py-1 text-[var(--text-tertiary)]">{i + 1}</td>
                      <td className="px-2 py-1">{u.dong || "—"}</td>
                      <td className="px-2 py-1 font-bold text-[var(--text-primary)]">{u.ho || "—"}</td>
                      <td className="px-2 py-1">{sm(u.exclusive_area_sqm)}</td>
                      <td className="px-2 py-1">{(u.share_ratio * 100).toFixed(3)}%</td>
                      <td className="px-2 py-1 font-bold text-[var(--accent-strong)]">{sm(u.land_share_sqm)}</td>
                      <td className="px-2 py-1">{py(u.land_share_sqm)}</td>
                      <td className="px-2 py-1 text-[var(--text-secondary)]">{u.purpose || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <p className="mt-3 text-[11px] leading-relaxed text-[var(--text-hint)]">
              ※ {data.validation?.method || "전유면적 비례 산정(area-weighted)"} 정확한 대지권비율(분모/분자)은 등기부 대지권등록부에서 확인하세요.
            </p>
          </>
        )}
      </div>
    </div>
  );
}