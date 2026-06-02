"use client";

/**
 * 인.허가분석 자동화 — AI 인허가 분석 시스템.
 *
 * 부지분석(용도지역·건폐율/용적률·면적) + 지자체 조례 + 상위법령을 종합하여
 * LLM(Claude)이 개발방식별 인허가 가능성·근거법령·문제점·해결방안을 분석한다.
 * 주소는 ProjectAddressInput으로 (1) 프로젝트 선택 (2) 카카오 검색 (3) 변경/추가 입력 모두 지원.
 */

import { useCallback, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { GlobalAddressSearch, type AddressEntry } from "@/components/common/GlobalAddressSearch";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { Locale } from "@/i18n/config";

type MethodResult = {
  method: string;
  possibility: "상" | "중" | "하" | string;
  score: number;
  key_laws: string[];
  issues: string[];
  solutions: string[];
};

type ParcelInfo = {
  address: string;
  zone_type?: string | null;
  max_far?: number | null;
  max_bcr?: number | null;
  land_area_sqm?: number | null;
};

type MultiParcel = {
  ai?: boolean;
  parcels: ParcelInfo[];
  blended_far?: number | null;
  optimal_far?: number | null;
  max_far?: number | null;
  far_rationale?: string;
  far_key_laws?: string[];
  integration_issues?: string[];
  integration_solutions?: string[];
};

type PermitAnalysis = {
  ai?: boolean;
  summary: string;
  methods: MethodResult[];
  recommendation: string;
  site?: {
    address?: string;
    zone_type?: string | null;
    max_bcr?: number | null;
    max_far?: number | null;
    land_area_sqm?: number | null;
  };
  multi_parcel?: MultiParcel;
};

const POSSIBILITY_STYLE: Record<string, string> = {
  상: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30",
  중: "bg-amber-500/15 text-amber-600 border-amber-500/30",
  하: "bg-rose-500/15 text-rose-600 border-rose-500/30",
};

export function PermitAiWorkspaceClient({ locale: _locale }: { locale: Locale }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const [addr, setAddr] = useState("");
  const [extra, setExtra] = useState<string[]>([]); // 다필지 추가 주소
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<PermitAnalysis | null>(null);

  const addParcel = useCallback(() => setExtra((p) => [...p, ""]), []);
  const removeParcel = useCallback((i: number) => setExtra((p) => p.filter((_, idx) => idx !== i)), []);
  const setParcel = useCallback(
    (i: number, v: string) => setExtra((p) => p.map((x, idx) => (idx === i ? v : x))),
    [],
  );

  const run = useCallback(async () => {
    const target = addr || siteAnalysis?.address || "";
    if (!target) {
      setError("주소를 먼저 선택하거나 입력하세요.");
      return;
    }
    const parcels = [target, ...extra.map((s) => s.trim()).filter(Boolean)];
    setLoading(true);
    setError("");
    setResult(null);
    try {
      const r = await apiClient.post<PermitAnalysis>("/permits/ai-analysis", {
        body: {
          address: target,
          pnu: siteAnalysis?.pnu || undefined,
          site: siteAnalysis?.address === target ? siteAnalysis : undefined,
          parcels: parcels.length > 1 ? parcels : undefined,
        },
        useMock: false,
        timeoutMs: 150000,
      });
      setResult(r);
    } catch {
      setError("인허가 AI 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [addr, extra, siteAnalysis]);

  const site = result?.site;

  return (
    <div className="grid gap-6">
      {/* Hero */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <span className="text-2xl">⚖️</span>
            <div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">인.허가분석 자동화</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                상위법령(국토계획법·건축법·주택법·도시개발법·공공주택특별법·도시정비법)과 도시·군관리계획,
                해당 지자체 조례를 종합해 개발방식별 인허가 가능성·문제점·해결방안을 AI로 분석합니다.
              </p>
            </div>
          </div>

          <div className="mt-5">
            <ProjectAddressInput
              value={addr}
              onChange={setAddr}
              label="분석 대상지 주소 (1필지)"
              placeholder="프로젝트를 선택하거나 주소를 검색/입력하세요"
              pickerLabel="분석 히스토리"
              disabled={loading}
            />
          </div>

          {/* 다필지(여러 필지) 추가 — 용도지역이 다른 토지 통합 개발 분석 */}
          {extra.map((p, i) => (
            <div key={i} className="mt-3">
              <div className="mb-1 flex items-center justify-between">
                <span className="text-xs font-bold uppercase tracking-widest text-[var(--text-tertiary)]">
                  추가 필지 {i + 2}
                </span>
                <button
                  onClick={() => removeParcel(i)}
                  disabled={loading}
                  className="text-[11px] font-semibold text-rose-500 hover:underline disabled:opacity-50"
                >
                  ✕ 제거
                </button>
              </div>
              <GlobalAddressSearch
                single
                initialAddress={p || undefined}
                placeholder="통합 개발할 필지 주소를 검색하세요"
                disabled={loading}
                onChange={(e: AddressEntry[]) => setParcel(i, e.length > 0 ? e[0].fullAddress : "")}
              />
            </div>
          ))}

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <button
              onClick={addParcel}
              disabled={loading}
              className="rounded-xl border border-dashed border-[var(--line-strong)] px-3.5 py-1.5 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] hover:text-[var(--accent-strong)] disabled:opacity-50"
            >
              ＋ 주소 추가 (다필지 통합 분석)
            </button>
            <span className="text-[11px] text-[var(--text-tertiary)]">
              {extra.length > 0
                ? `${extra.length + 1}개 필지 통합 — 용도지역이 다른 토지의 최적·최고 용적률을 함께 산정합니다`
                : "필지를 추가하면 통합 개발 시 최적 용적률을 분석합니다 (단일필지는 추가 없이 실행)"}
            </span>
          </div>

          <div className="mt-4 flex items-center gap-3">
            <button
              onClick={run}
              disabled={loading}
              className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "AI 분석 중… (최대 1분)" : "🤖 인허가 AI 분석 실행"}
            </button>
            {error && <span className="text-xs font-semibold text-rose-500">{error}</span>}
          </div>
        </CardContent>
      </Card>

      {/* 부지 요약 + 종합 */}
      {result && (
        <>
          <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <p className="text-sm font-bold text-[var(--accent-strong)]">부지 종합 인허가 환경</p>
                <span
                  className={`rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${
                    result.ai
                      ? "border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]"
                      : "border-[var(--line-strong)] text-[var(--text-tertiary)]"
                  }`}
                >
                  {result.ai ? "AI 분석" : "규칙기반 폴백"}
                </span>
              </div>
              <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">{result.summary}</p>
              {site && (
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                  {[
                    ["용도지역", site.zone_type || "-"],
                    ["건폐율 한도", site.max_bcr != null ? `${site.max_bcr}%` : "-"],
                    ["용적률 한도", site.max_far != null ? `${site.max_far}%` : "-"],
                    ["대지면적", site.land_area_sqm != null ? `${Math.round(site.land_area_sqm)}㎡` : "-"],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-2)] p-3">
                      <p className="text-[11px] text-[var(--text-tertiary)]">{k}</p>
                      <p className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v}</p>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* 다필지 통합 개발 — 최적·최고 용적률 산정 */}
          {result.multi_parcel && (
            <Card className="rounded-[var(--radius-2xl)] border-[var(--accent-strong)]/30 shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-black text-[var(--accent-strong)]">
                    🧩 다필지 통합 개발 · 최적 용적률 산정 ({result.multi_parcel.parcels.length}개 필지)
                  </p>
                  <span
                    className={`rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${
                      result.multi_parcel.ai
                        ? "border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/10 text-[var(--accent-strong)]"
                        : "border-[var(--line-strong)] text-[var(--text-tertiary)]"
                    }`}
                  >
                    {result.multi_parcel.ai ? "AI 산정" : "가중평균 기반"}
                  </span>
                </div>

                {/* 용적률 3종 */}
                <div className="mt-4 grid grid-cols-3 gap-3">
                  {[
                    ["법정 가중평균", result.multi_parcel.blended_far, "국토계획법 시행령 §84"],
                    ["최적 용적률", result.multi_parcel.optimal_far, "법정+통상 인센티브"],
                    ["최고 용적률", result.multi_parcel.max_far, "모든 상향수단 적용"],
                  ].map(([k, v, sub], idx) => (
                    <div
                      key={k as string}
                      className={`rounded-xl border p-3 text-center ${
                        idx === 1
                          ? "border-[var(--accent-strong)]/40 bg-[var(--accent-strong)]/10"
                          : "border-[var(--line)] bg-[var(--surface-2)]"
                      }`}
                    >
                      <p className="text-[11px] text-[var(--text-tertiary)]">{k as string}</p>
                      <p className="mt-0.5 text-lg font-black text-[var(--text-primary)]">
                        {v != null ? `${v}%` : "-"}
                      </p>
                      <p className="mt-0.5 text-[10px] text-[var(--text-tertiary)]">{sub as string}</p>
                    </div>
                  ))}
                </div>

                {/* 필지별 표 */}
                <div className="mt-4 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[var(--line)] text-[var(--text-tertiary)]">
                        <th className="py-1.5 text-left font-semibold">필지</th>
                        <th className="py-1.5 text-left font-semibold">용도지역</th>
                        <th className="py-1.5 text-right font-semibold">용적률한도</th>
                        <th className="py-1.5 text-right font-semibold">면적</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.multi_parcel.parcels.map((p, i) => (
                        <tr key={i} className="border-b border-[var(--line)]/50">
                          <td className="py-1.5 text-[var(--text-secondary)]">
                            {i + 1}. {p.address}
                          </td>
                          <td className="py-1.5 text-[var(--text-secondary)]">{p.zone_type || "미상"}</td>
                          <td className="py-1.5 text-right text-[var(--text-secondary)]">
                            {p.max_far != null ? `${p.max_far}%` : "-"}
                          </td>
                          <td className="py-1.5 text-right text-[var(--text-secondary)]">
                            {p.land_area_sqm != null ? `${Math.round(p.land_area_sqm)}㎡` : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {result.multi_parcel.far_rationale && (
                  <p className="mt-4 text-sm leading-relaxed text-[var(--text-secondary)]">
                    {result.multi_parcel.far_rationale}
                  </p>
                )}

                <div className="mt-4 grid gap-3 sm:grid-cols-2">
                  {(result.multi_parcel.integration_issues?.length ?? 0) > 0 && (
                    <div>
                      <p className="text-xs font-bold text-rose-500">⚠ 통합 인허가 문제점</p>
                      <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
                        {result.multi_parcel.integration_issues!.map((it, i) => (
                          <li key={i}>· {it}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(result.multi_parcel.integration_solutions?.length ?? 0) > 0 && (
                    <div>
                      <p className="text-xs font-bold text-emerald-600">✓ 해결방안</p>
                      <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
                        {result.multi_parcel.integration_solutions!.map((s, i) => (
                          <li key={i}>· {s}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                {(result.multi_parcel.far_key_laws?.length ?? 0) > 0 && (
                  <div className="mt-4">
                    <p className="text-xs font-bold text-[var(--accent-strong)]">근거 법령</p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      {result.multi_parcel.far_key_laws!.map((l, i) => (
                        <span key={i} className="rounded-md bg-[var(--surface-2)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                          {l}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* 개발방식별 카드 */}
          <div className="grid gap-4 lg:grid-cols-2">
            {[...result.methods]
              .sort((a, b) => (b.score || 0) - (a.score || 0))
              .map((m) => (
                <Card key={m.method} className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-sm)]">
                  <CardContent className="p-5">
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-black text-[var(--text-primary)]">{m.method}</p>
                      <span
                        className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${
                          POSSIBILITY_STYLE[m.possibility] || "border-[var(--line-strong)] text-[var(--text-secondary)]"
                        }`}
                      >
                        가능성 {m.possibility} · {m.score}점
                      </span>
                    </div>

                    <div className="mt-3 space-y-3 text-xs">
                      {m.key_laws?.length > 0 && (
                        <div>
                          <p className="font-bold text-[var(--accent-strong)]">근거 법령</p>
                          <div className="mt-1 flex flex-wrap gap-1.5">
                            {m.key_laws.map((l, i) => (
                              <span key={i} className="rounded-md bg-[var(--surface-2)] px-2 py-0.5 text-[var(--text-secondary)]">
                                {l}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      {m.issues?.length > 0 && (
                        <div>
                          <p className="font-bold text-rose-500">⚠ 문제점</p>
                          <ul className="mt-1 space-y-0.5 text-[var(--text-secondary)]">
                            {m.issues.map((it, i) => (
                              <li key={i}>· {it}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {m.solutions?.length > 0 && (
                        <div>
                          <p className="font-bold text-emerald-600">✓ 해결방안</p>
                          <ul className="mt-1 space-y-0.5 text-[var(--text-secondary)]">
                            {m.solutions.map((s, i) => (
                              <li key={i}>· {s}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
          </div>

          {/* 종합 권고 */}
          {result.recommendation && (
            <Card className="rounded-[var(--radius-2xl)] border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="text-sm font-black text-[var(--accent-strong)]">📌 종합 권고</p>
                <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{result.recommendation}</p>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
