"use client";

/**
 * 부동산 등기정보 분석 — 법무사·변호사 AI 권리분석.
 *
 * 주소 검색/프로젝트 연동 + (등기부 미연동 시) 등기부등본 텍스트 직접 입력 →
 * 소유정보·소유기간·매입금액·보유지분·가등기·압류·근저당·매도청구 가능여부 분석.
 * 토지 소유구분·특성(공부)도 함께 제공.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Card, CardContent } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { Locale } from "@/i18n/config";

type Land = {
  pnu?: string | null; owner_type?: string | null; land_category?: string | null;
  land_area_sqm?: number | null; official_price_per_sqm?: number | null; zone_type?: string | null;
};
type AI = {
  generated?: boolean;
  ownership?: { current_owner?: string; share?: string; acquisition_date?: string; acquisition_cause?: string; acquisition_price?: string; ownership_period?: string };
  provisional_registration?: { exists?: boolean | null; detail?: string };
  seizure?: Array<{ type?: string; holder?: string; detail?: string; date?: string }>;
  mortgage?: Array<{ max_claim?: string; mortgagee?: string; date?: string }>;
  other_rights?: string[];
  right_to_demand_sale?: { possible?: string; reason?: string };
  rights_analysis?: string;
  risks?: string[];
  safety_grade?: string;
  summary?: string;
};
type Result = { status: string; origin?: string; land?: Land | null; message?: string; ai?: AI | null;
  fetched?: { owner?: string; registry_office?: string; doc_title?: string; has_pdf?: boolean } | null };

const GRADE: Record<string, string> = {
  안전: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400",
  주의: "border-amber-500/30 bg-amber-500/10 text-amber-400",
  위험: "border-rose-500/30 bg-rose-500/10 text-rose-400",
};

export function RegistryAnalysisWorkspaceClient({ locale }: { locale: Locale }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const [addr, setAddr] = useState("");
  const [text, setText] = useState("");
  const [showText, setShowText] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<Result | null>(null);

  const run = useCallback(async (overrideAddr?: string) => {
    const target = (typeof overrideAddr === "string" ? overrideAddr : addr) || siteAnalysis?.address || "";
    if (!target && !text.trim()) { setError("주소를 선택하거나 등기부 내용을 입력하세요."); return; }
    setLoading(true); setError(""); setResult(null);
    try {
      const r = await apiClient.post<Result>("/registry/analyze", {
        body: { address: target || undefined, pnu: siteAnalysis?.pnu || undefined, registry_text: text.trim() || undefined },
        useMock: false, timeoutMs: 120000,
      });
      setResult(r);
    } catch {
      setError("등기 분석에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [addr, text, siteAnalysis]);

  // 토지조서 등에서 ?addr= 로 진입 시 자동 프리필 + 1회 실행
  const autoRan = useRef(false);
  useEffect(() => {
    if (autoRan.current || typeof window === "undefined") return;
    const p = new URLSearchParams(window.location.search).get("addr");
    if (p) { autoRan.current = true; setAddr(p); void run(p); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ai = result?.ai;
  const land = result?.land;
  const own = ai?.ownership || {};

  return (
    <div className="grid gap-6">
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <span className="text-2xl">📜</span>
            <div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">부동산 등기정보 분석</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                법무사·변호사 AI가 등기부등본을 분석해 소유정보·소유기간·매입금액·지분·가등기·압류·근저당·매도청구 가능여부를 제공합니다.
              </p>
            </div>
          </div>
          <div className="mt-5">
            <ProjectAddressInput value={addr} onChange={setAddr} label="분석 대상지 주소"
              placeholder="프로젝트를 선택하거나 주소를 검색/입력하세요" pickerLabel="분석 히스토리" disabled={loading} />
          </div>
          <div className="mt-3">
            <button onClick={() => setShowText((v) => !v)} className="text-[11px] font-semibold text-[var(--accent-strong)] hover:underline">
              {showText ? "− 등기부 직접 입력 닫기" : "+ 등기부등본 내용 직접 입력 (연동 미설정 시)"}
            </button>
            {showText && (
              <textarea value={text} onChange={(e) => setText(e.target.value)} rows={6} disabled={loading}
                placeholder="등기부등본 갑구·을구 내용을 붙여넣으세요 (소유권/근저당/압류 등). 연동(CODEF) 설정 시 주소만으로 자동 조회됩니다."
                className="mt-2 w-full rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] p-3 text-xs text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]" />
            )}
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button onClick={() => run()} disabled={loading}
              className="rounded-xl bg-[var(--accent-strong)] px-5 py-2.5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">
              {loading ? "등기 분석 중…" : "⚖ 등기 권리분석 실행"}
            </button>
            {error && <span className="text-xs font-semibold text-rose-500">{error}</span>}
          </div>
        </CardContent>
      </Card>

      {result && (
        <>
          {/* 토지 소유구분·특성(공부) — 항상 제공 */}
          {land && (
            <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="text-sm font-black text-[var(--accent-strong)]">🟫 토지 소유·특성 정보 (공부)</p>
                <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
                  {[
                    ["소유구분", land.owner_type || "-"],
                    ["지목", land.land_category || "-"],
                    ["용도지역", land.zone_type || "-"],
                    ["면적", land.land_area_sqm != null ? `${Math.round(land.land_area_sqm)}㎡` : "-"],
                    ["공시지가(㎡)", land.official_price_per_sqm ? `${Math.round(land.official_price_per_sqm).toLocaleString()}원` : "-"],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                      <p className="text-[11px] text-[var(--text-tertiary)]">{k}</p>
                      <p className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v}</p>
                    </div>
                  ))}
                </div>
                <p className="mt-2 text-[11px] text-[var(--text-hint)]">※ 소유자 성명·지분 등은 등기부 분석 결과를 참조하세요(공부상 소유구분만 표기).</p>
              </CardContent>
            </Card>
          )}

          {/* 등기부 미확보 안내 */}
          {result.status !== "ok" && (
            <Card className="rounded-[var(--radius-2xl)] border-amber-500/30 bg-amber-500/5 shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <p className="text-sm font-bold text-amber-400">⚙ 등기부 분석 안내</p>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">{result.message}</p>
                <p className="mt-2 text-[11px] text-[var(--text-hint)]">위의 "등기부등본 내용 직접 입력"으로 분석하거나, 등기부 API(CODEF) 설정을 완료하세요.</p>
              </CardContent>
            </Card>
          )}

          {/* 등기 권리분석(법무사·변호사 AI) */}
          {ai && (
            <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
              <CardContent className="p-6">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-black text-[var(--accent-strong)]">⚖ 등기 권리분석 (법무사·변호사 AI)</p>
                  {ai.safety_grade && (
                    <span className={`rounded-full border px-2.5 py-0.5 text-xs font-bold ${GRADE[ai.safety_grade] || "border-[var(--line-strong)] text-[var(--text-secondary)]"}`}>
                      안전성 {ai.safety_grade}
                    </span>
                  )}
                </div>
                {ai.summary && <p className="mt-2 text-sm leading-relaxed text-[var(--text-primary)]">{ai.summary}</p>}

                {/* 소유정보 */}
                <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {[
                    ["소유자", own.current_owner],
                    ["보유지분", own.share],
                    ["취득일", own.acquisition_date],
                    ["취득원인", own.acquisition_cause],
                    ["매입금액", own.acquisition_price],
                    ["보유기간", own.ownership_period],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3">
                      <p className="text-[11px] text-[var(--text-tertiary)]">{k}</p>
                      <p className="mt-0.5 text-sm font-bold text-[var(--text-primary)]">{v || "기재 없음"}</p>
                    </div>
                  ))}
                </div>

                {/* 권리 상태 */}
                <div className="mt-4 grid gap-3 md:grid-cols-2">
                  <RightBlock title="가등기" tone={ai.provisional_registration?.exists ? "rose" : "emerald"}
                    body={ai.provisional_registration?.exists ? (ai.provisional_registration?.detail || "있음") : "없음"} />
                  <RightBlock title="매도청구 가능여부" tone="sky"
                    body={`${ai.right_to_demand_sale?.possible || "-"}${ai.right_to_demand_sale?.reason ? ` — ${ai.right_to_demand_sale.reason}` : ""}`} />
                  <RightBlock title="압류·가압류·경매" tone={(ai.seizure?.length ?? 0) > 0 ? "rose" : "emerald"}
                    body={(ai.seizure?.length ?? 0) > 0 ? ai.seizure!.map((s) => `${s.type || ""} ${s.holder || ""} ${s.detail || ""}`).join(" / ") : "없음"} />
                  <RightBlock title="근저당 등 (을구)" tone={(ai.mortgage?.length ?? 0) > 0 ? "amber" : "emerald"}
                    body={(ai.mortgage?.length ?? 0) > 0 ? ai.mortgage!.map((m) => `채권최고액 ${m.max_claim || "-"} (${m.mortgagee || "-"})`).join(" / ") : "없음"} />
                </div>

                {ai.rights_analysis && (
                  <div className="mt-4">
                    <p className="text-xs font-bold text-[var(--text-primary)]">권리관계 종합 분석</p>
                    <p className="mt-1 text-sm leading-relaxed text-[var(--text-secondary)]">{ai.rights_analysis}</p>
                  </div>
                )}
                {(ai.risks?.length ?? 0) > 0 && (
                  <div className="mt-3">
                    <p className="text-xs font-bold text-rose-500">⚠ 권리 리스크</p>
                    <ul className="mt-1 space-y-0.5 text-xs text-[var(--text-secondary)]">
                      {ai.risks!.map((r, i) => <li key={i}>· {r}</li>)}
                    </ul>
                  </div>
                )}
                <p className="mt-3 text-[11px] text-[var(--text-hint)]">※ 본 분석은 참고용이며 법률자문이 아닙니다. 정확한 권리관계는 등기부등본 원본·전문가 확인이 필요합니다.</p>
              </CardContent>
            </Card>
          )}
        </>
      )}

      {/* 하단 서브메뉴: 토지조서 연동 */}
      <Card className="rounded-[var(--radius-2xl)] border-[var(--line)] shadow-[var(--shadow-sm)]">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5">
          <p className="text-xs text-[var(--text-secondary)]">📋 여러 필지의 소유·지분·매입가·계약/동의를 한눈에 관리하려면 토지조서로 이동하세요.</p>
          <Link href={`/${locale}/land-schedule`} className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-black text-white hover:opacity-90">
            토지조서 바로가기 →
          </Link>
        </CardContent>
      </Card>
    </div>
  );
}

function RightBlock({ title, body, tone }: { title: string; body: string; tone: string }) {
  const cls: Record<string, string> = {
    rose: "border-rose-500/30 text-rose-400", amber: "border-amber-500/30 text-amber-400",
    emerald: "border-emerald-500/30 text-emerald-400", sky: "border-sky-500/30 text-sky-400",
  };
  return (
    <div className={`rounded-xl border bg-[var(--surface-soft)] p-3 ${cls[tone] || "border-[var(--line)]"}`}>
      <p className="text-xs font-bold">{title}</p>
      <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">{body}</p>
    </div>
  );
}
