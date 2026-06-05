"use client";

/**
 * 예상 시세 추정 보고서 — 감정평가서 스타일 전체 화면 + PDF 다운로드.
 * 공개데이터(공시지가·실거래·R-ONE 통계) 자동 서칭 → 4방법 + 교차검증 보고서.
 * ⚠ 정식 감정평가서가 아닌 참고용 추정 리포트(법적 효력 없음).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { NumberInput } from "@/components/common/NumberInput";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type { Locale } from "@/i18n/config";

function apiBase(): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr")
      return "https://api.4t8t.net/api/v1";
  }
  return "/api/proxy";
}

const eok = (v: number | null | undefined) =>
  v == null ? "—" : `${(v / 1e8).toLocaleString(undefined, { maximumFractionDigits: 2 })}억`;
const won = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v).toLocaleString()}원`);

type Method = { method: string; unit_price: number; rationale: string };
type Stat = { source?: string; pct?: number; basis?: string; rate?: number; factor?: number } | null;
type Result = {
  ok: boolean; message?: string;
  appraised_price_per_sqm: number; appraised_total_won: number | null; area_sqm: number | null;
  official_price_per_sqm?: number; pnu?: string | null;
  subject?: {
    land_category?: string | null; zone_type?: string | null; zone_type_2?: string | null;
    land_use_situation?: string | null; terrain_height?: string | null; terrain_form?: string | null;
    official_price_year?: number | null;
  };
  confidence: number; range_per_sqm: { low: number; high: number };
  cross_check?: { firms: number[]; mean: number; cv_pct: number; min: number; max: number; note: string };
  irregularity?: number | null; methods: Method[]; weight_note: string;
  road_side?: string | null; time_adjust?: number; time_adjust_basis?: string; source?: string; base_year?: number;
  building?: { building_value_won: number; rationale: string } | null; complex_total_won?: number | null;
  income?: { income_value_won: number; rationale: string } | null; income_total_won?: number | null;
  complex_note?: string | null;
  market_stats?: { rone_available?: boolean; cap_rate?: Stat; jeonse_conversion_rate?: Stat; housing_time_adjust?: Stat };
  disclaimer: string;
};

function Gauge({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 80 ? "#10b981" : pct >= 60 ? "#3b82f6" : pct >= 45 ? "#f59e0b" : "#ef4444";
  return (
    <div className="flex items-center gap-3">
      <div className="relative h-3 flex-1 rounded-full bg-[var(--surface-strong)]">
        <div className="absolute inset-y-0 left-0 rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="text-sm font-[1000]" style={{ color }}>{pct}%</span>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex border-b border-[var(--line)]/60 last:border-0">
      <div className="w-32 shrink-0 bg-[var(--surface-soft)] px-3 py-2 text-[11px] font-bold text-[var(--text-tertiary)]">{k}</div>
      <div className="flex-1 px-3 py-2 text-xs text-[var(--text-primary)]">{v ?? "—"}</div>
    </div>
  );
}

function Section({ no, title, children }: { no: string; title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="mb-2 flex items-center gap-2 text-sm font-black text-[var(--text-primary)]">
        <span className="rounded bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-black text-[var(--accent-strong)]">{no}</span>
        {title}
      </h2>
      {children}
    </section>
  );
}

export function DeskAppraisalReportClient({ locale }: { locale: Locale }) {
  void locale;
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const projectName = useProjectContextStore((s) => s.projectName);

  const [addr, setAddr] = useState(siteAnalysis?.address || "");
  const [showAdv, setShowAdv] = useState(false);
  const [official, setOfficial] = useState<number | null>(null);
  const [gfa, setGfa] = useState<number | null>(null);
  const [structure, setStructure] = useState("RC");
  const [year, setYear] = useState<string>("");
  const [rent, setRent] = useState<number | null>(null);
  const [deposit, setDeposit] = useState<number | null>(null);
  const [cap, setCap] = useState<string>("");
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState<"" | "run" | "pdf">("");
  const [err, setErr] = useState<string | null>(null);
  const [ranAddr, setRanAddr] = useState("");

  const today = useRef<string>("");
  if (!today.current) {
    const d = new Date();
    today.current = `${d.getFullYear()}. ${String(d.getMonth() + 1).padStart(2, "0")}. ${String(d.getDate()).padStart(2, "0")}`;
  }

  const body = useCallback(() => ({
    address: addr.trim(),
    official_price_per_sqm: official ?? undefined,
    building_gfa_sqm: gfa ?? undefined,
    building_structure: gfa ? structure : undefined,
    building_year_built: year ? Number(year) : undefined,
    monthly_rent_won: rent ?? undefined,
    deposit_won: deposit ?? undefined,
    cap_rate: cap ? Number(cap) / 100 : undefined,
  }), [addr, official, gfa, structure, year, rent, deposit, cap]);

  const run = useCallback(async () => {
    if (!addr.trim()) { setErr("대상지 주소(지번)를 입력하세요."); return; }
    setBusy("run"); setErr(null);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const r = await fetch(`${apiBase()}/land-price/desk-appraisal`, {
        method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body()),
      });
      if (!r.ok) { setErr(`서버 오류(${r.status}) — 잠시 후 다시 시도하세요.`); return; }
      const d = await r.json();
      if (d?.ok) { setRes(d); setRanAddr(addr.trim()); }
      else setErr((d?.message || "추정 실패") + " — 공시지가가 자동조회되지 않으면 ‘상세 입력’에서 공시지가를 직접 입력 후 다시 실행하세요.");
    } catch { setErr("추정 요청 실패 — 네트워크 확인 후 다시 시도하세요."); } finally { setBusy(""); }
  }, [addr, body]);

  const downloadPdf = useCallback(async () => {
    setBusy("pdf"); setErr(null);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const r = await fetch(`${apiBase()}/land-price/desk-appraisal/pdf`, {
        method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body()),
      });
      if (!r.ok || !(r.headers.get("content-type") || "").includes("pdf")) { setErr("리포트 PDF 생성 실패"); return; }
      const blob = await r.blob(); const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `예상시세추정보고서_${ranAddr || addr}.pdf`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { setErr("리포트 다운로드 실패"); } finally { setBusy(""); }
  }, [body, addr, ranAddr]);

  // 프로젝트 부지 주소가 있으면 진입 시 자동 채움(실행은 사용자 클릭)
  useEffect(() => {
    if (!addr && siteAnalysis?.address) setAddr(siteAnalysis.address);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siteAnalysis?.address]);

  const inp = "h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 text-sm text-[var(--text-primary)] outline-none";
  const subj = res?.subject || {};
  const ms = res?.market_stats || {};

  return (
    <div className="grid gap-6">
      {/* 입력 카드 */}
      <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
        <CardContent className="p-6">
          <div className="flex items-center gap-3">
            <span className="text-2xl">📑</span>
            <div>
              <h1 className="text-lg font-black text-[var(--text-primary)]">예상 시세 추정 보고서</h1>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                공시지가·실거래·R-ONE 통계를 자동 서칭해 4방법(공시지가기준·거래사례·원가·수익환원)으로 추정 → 보고서·PDF. <b>정식 감정평가 아님(참고용).</b>
              </p>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-end gap-2">
            <div className="min-w-[280px] flex-1">
              <ProjectAddressInput value={addr} onChange={setAddr} label="대상지 주소(지번)" placeholder="지번 주소 검색" pickerLabel="분석 히스토리" />
            </div>
            <button onClick={() => void run()} disabled={busy !== ""}
              className="h-10 rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">
              {busy === "run" ? "서칭·분석 중…" : "🔎 서칭·분석 실행"}
            </button>
            <button onClick={() => setShowAdv((v) => !v)}
              className="h-10 rounded-xl border border-[var(--line-strong)] px-4 text-xs font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)]">
              {showAdv ? "상세 입력 닫기" : "상세 입력(건물·임대·공시지가)"}
            </button>
          </div>

          {showAdv && (
            <div className="mt-3 grid grid-cols-2 gap-3 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-3 md:grid-cols-4">
              <label className="text-xs text-[var(--text-secondary)]">공시지가(원/㎡, 선택)<NumberInput className={`${inp} mt-1`} value={official} onChange={setOfficial} placeholder="자동조회" /></label>
              <label className="text-xs text-[var(--text-secondary)]">건물 연면적(㎡)<NumberInput allowDecimal className={`${inp} mt-1`} value={gfa} onChange={setGfa} placeholder="복합 시" /></label>
              <label className="text-xs text-[var(--text-secondary)]">구조<select className={`${inp} mt-1`} value={structure} onChange={(e) => setStructure(e.target.value)}>{["RC", "SRC", "철골", "조적", "목조"].map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
              <label className="text-xs text-[var(--text-secondary)]">준공연도<input className={`${inp} mt-1`} type="number" value={year} onChange={(e) => setYear(e.target.value)} placeholder="예 2010" /></label>
              <label className="text-xs text-[var(--text-secondary)]">월 임대료(원)<NumberInput className={`${inp} mt-1`} value={rent} onChange={setRent} placeholder="수익환원 시" /></label>
              <label className="text-xs text-[var(--text-secondary)]">보증금(원)<NumberInput className={`${inp} mt-1`} value={deposit} onChange={setDeposit} /></label>
              <label className="text-xs text-[var(--text-secondary)]">자본환원율(%)<input className={`${inp} mt-1`} type="number" value={cap} onChange={(e) => setCap(e.target.value)} placeholder="미입력 시 R-ONE/기본" /></label>
            </div>
          )}

          {err && <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">⚠ {err}</p>}
        </CardContent>
      </Card>

      {/* 보고서 본문 */}
      {res && (
        <Card className="rounded-[var(--radius-2xl)] shadow-[var(--shadow-md)]">
          <CardContent className="p-7">
            {/* 표지 헤더 */}
            <div className="flex flex-wrap items-start justify-between gap-3 border-b-2 border-[var(--accent-strong)]/40 pb-4">
              <div>
                <p className="text-[11px] font-bold tracking-widest text-[var(--accent-strong)]">PROPAI · 사통팔땅</p>
                <h2 className="mt-1 text-xl font-[1000] text-[var(--text-primary)]">예상 시세 추정 보고서</h2>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">{ranAddr}{res.area_sqm ? ` · ${res.area_sqm.toLocaleString()}㎡` : ""}{projectName ? ` · ${projectName}` : ""}</p>
              </div>
              <div className="text-right">
                <span className="inline-block rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-[10px] font-bold text-amber-400">참고용 · 감정평가 아님</span>
                <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">작성일 {today.current}</p>
                <p className="text-[11px] text-[var(--text-tertiary)]">출처 {res.source || "공개데이터"}</p>
              </div>
            </div>

            {/* I. 평가 결론 */}
            <Section no="Ⅰ" title="평가 결론">
              <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-5">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-xs font-black uppercase tracking-widest text-[var(--text-hint)]">토지 예상 채택가</span>
                  <span className="text-3xl font-[1000] text-[var(--accent-strong)]">{eok(res.appraised_total_won)}</span>
                </div>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  단가 {res.appraised_price_per_sqm.toLocaleString()}원/㎡ · 신뢰구간 {won(res.range_per_sqm.low)} ~ {won(res.range_per_sqm.high)}/㎡
                </p>
                <div className="mt-3 flex items-center gap-3">
                  <span className="text-[11px] font-bold text-[var(--text-tertiary)]">신뢰도</span>
                  <div className="flex-1"><Gauge value={res.confidence} /></div>
                </div>
                {(res.complex_total_won || res.income_total_won) && (
                  <p className="mt-2 text-[11px] text-[var(--text-secondary)]">
                    {res.complex_total_won ? `원가법 복합(토지+건물) ${eok(res.complex_total_won)}` : ""}
                    {res.complex_total_won && res.income_total_won ? " · " : ""}
                    {res.income_total_won ? `수익환원법 ${eok(res.income_total_won)}` : ""}
                  </p>
                )}
              </div>
            </Section>

            {/* II. 대상물건 표시 */}
            <Section no="Ⅱ" title="대상물건 표시">
              <div className="grid gap-0 overflow-hidden rounded-xl border border-[var(--line)] md:grid-cols-2">
                <div className="border-r border-[var(--line)]/60">
                  <Row k="소재지" v={ranAddr} />
                  <Row k="지목" v={subj.land_category} />
                  <Row k="용도지역" v={[subj.zone_type, subj.zone_type_2].filter(Boolean).join(" / ")} />
                  <Row k="이용상황" v={subj.land_use_situation} />
                </div>
                <div>
                  <Row k="면적" v={res.area_sqm ? `${res.area_sqm.toLocaleString()}㎡ (약 ${Math.round((res.area_sqm) / 3.305785).toLocaleString()}평)` : "—"} />
                  <Row k="개별공시지가" v={res.official_price_per_sqm ? `${res.official_price_per_sqm.toLocaleString()}원/㎡` : "—"} />
                  <Row k="접도/형상" v={`${res.road_side || "—"} / ${res.irregularity != null ? `부정형도 ${(res.irregularity * 100).toFixed(0)}%` : "—"}`} />
                  <Row k="지세" v={[subj.terrain_height, subj.terrain_form].filter(Boolean).join(" / ")} />
                </div>
              </div>
            </Section>

            {/* III. 가격 산정방법별 */}
            <Section no="Ⅲ" title="가격 산정방법별 추정">
              <div className="overflow-hidden rounded-xl border border-[var(--line)]">
                <table className="w-full text-[11px]">
                  <thead><tr className="bg-[var(--surface-strong)] text-[var(--text-tertiary)]">
                    <th className="px-3 py-2 text-left font-bold">산정방법</th>
                    <th className="px-3 py-2 text-right font-bold">추정 단가(/㎡)</th>
                    <th className="px-3 py-2 text-left font-bold">근거</th>
                  </tr></thead>
                  <tbody>
                    {res.methods.map((m) => (
                      <tr key={m.method} className="border-t border-[var(--line)]/60 align-top">
                        <td className="px-3 py-2 font-bold text-[var(--text-primary)] whitespace-nowrap">{m.method}</td>
                        <td className="px-3 py-2 text-right font-bold text-[var(--accent-strong)] whitespace-nowrap">{Math.round(m.unit_price).toLocaleString()}</td>
                        <td className="px-3 py-2 text-[var(--text-secondary)] leading-relaxed">{m.rationale}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-1.5 text-[11px] text-[var(--text-hint)]">{res.weight_note}</p>
            </Section>

            {/* IV. 복수 시나리오 교차검증 */}
            {res.cross_check && (
              <Section no="Ⅳ" title={`복수 시나리오 교차검증 (평균 ${res.cross_check.mean.toLocaleString()}원/㎡ · 편차 CV ${res.cross_check.cv_pct}%)`}>
                <div className="flex gap-1.5">
                  {res.cross_check.firms.map((v, i) => (
                    <div key={i} className="flex-1 rounded-lg border border-[var(--line)] bg-[var(--surface-soft)] px-1 py-2 text-center">
                      <p className="text-[9px] text-[var(--text-hint)]">시나리오{i + 1}</p>
                      <p className="text-[11px] font-bold text-[var(--text-secondary)]">{Math.round(v / 1e4).toLocaleString()}만</p>
                    </div>
                  ))}
                </div>
                <p className="mt-1.5 text-[11px] text-[var(--text-hint)]">{res.cross_check.note}</p>
              </Section>
            )}

            {/* V. 복합·수익 가치 */}
            {(res.building || res.income) && (
              <Section no="Ⅴ" title="복합·수익 가치(참고)">
                <div className="grid gap-2 md:grid-cols-2">
                  {res.building && (
                    <div className="rounded-lg border border-[var(--line)] p-3 text-[11px]">
                      <p className="font-bold text-[var(--text-primary)]">원가법 복합(토지+건물) {eok(res.complex_total_won)}</p>
                      <p className="mt-0.5 text-[var(--text-secondary)] leading-relaxed">{res.building.rationale}</p>
                    </div>
                  )}
                  {res.income && (
                    <div className="rounded-lg border border-[var(--line)] p-3 text-[11px]">
                      <p className="font-bold text-[var(--text-primary)]">수익환원법 {eok(res.income_total_won)}</p>
                      <p className="mt-0.5 text-[var(--text-secondary)] leading-relaxed">{res.income.rationale}</p>
                    </div>
                  )}
                </div>
                {res.complex_note && <p className="mt-1.5 text-[11px] text-[var(--text-hint)]">{res.complex_note}</p>}
              </Section>
            )}

            {/* VI. 시점수정·시장통계 근거 */}
            <Section no="Ⅵ" title="시점수정·시장통계 근거">
              <ul className="space-y-1 text-[11px] text-[var(--text-secondary)]">
                {res.time_adjust_basis && <li>· 시점수정: {res.time_adjust_basis}</li>}
                {ms.cap_rate?.source === "R-ONE" && <li>· 자본환원율(R-ONE 실측): {ms.cap_rate.pct}% {ms.cap_rate.basis ? `— ${ms.cap_rate.basis}` : ""}</li>}
                {ms.jeonse_conversion_rate?.source === "R-ONE" && <li>· 전월세전환율(R-ONE 실측): {ms.jeonse_conversion_rate.pct}%</li>}
                {ms.housing_time_adjust?.source === "R-ONE" && <li>· 주택가격지수 누적변동: {ms.housing_time_adjust.factor}</li>}
                {!ms.rone_available && <li className="text-[var(--text-hint)]">· 시장통계: R-ONE 통계표 미설정 구간은 근사값 적용(관리자 설정 시 실데이터 전환).</li>}
              </ul>
            </Section>

            {/* VII. 면책 */}
            <Section no="Ⅶ" title="면책">
              <p className="text-[11px] leading-relaxed text-[var(--text-hint)]">{res.disclaimer}</p>
            </Section>

            {/* 액션 */}
            <div className="mt-6 flex flex-wrap gap-2 border-t border-[var(--line)] pt-4">
              <button onClick={() => void downloadPdf()} disabled={busy !== ""}
                className="h-10 rounded-xl bg-[var(--accent-strong)] px-5 text-sm font-black text-white hover:opacity-90 disabled:opacity-50">
                {busy === "pdf" ? "PDF 생성 중…" : "📄 보고서 PDF 다운로드"}
              </button>
              <button onClick={() => void run()} disabled={busy !== ""}
                className="h-10 rounded-xl border border-[var(--line-strong)] px-4 text-sm font-bold text-[var(--text-secondary)] hover:border-[var(--accent-strong)] disabled:opacity-50">
                ↻ 다시 분석
              </button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
