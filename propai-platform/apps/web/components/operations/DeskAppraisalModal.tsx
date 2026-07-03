"use client";

/**
 * 토지/복합 예상 시세 추정 상세 모달 — 5방법 비교 + 신뢰도 게이지 + 리포트 PDF.
 * 감정평가 아님(참고용). /api/v1/land-price/desk-appraisal(/pdf).
 */

import { useEffect, useRef, useState } from "react";
import { NumberInput } from "@/components/common/NumberInput";

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
const won = (v: number | null | undefined) => (v == null ? "—" : `${v.toLocaleString()}원`);

type Method = { method: string; unit_price: number; rationale: string };
type Result = {
  ok: boolean; message?: string;
  appraised_price_per_sqm: number; appraised_total_won: number | null; area_sqm: number | null;
  official_price_per_sqm?: number; pnu?: string | null;
  confidence: number; range_per_sqm: { low: number; high: number };
  cross_check?: { firms: number[]; mean: number; cv_pct: number; min: number; max: number; note: string };
  irregularity?: number | null; methods: Method[]; weight_note: string;
  road_side?: string | null; time_adjust?: number; time_adjust_basis?: string;
  building?: { building_value_won: number; rationale: string } | null; complex_total_won?: number | null;
  income?: { income_value_won: number; rationale: string } | null; income_total_won?: number | null;
  complex_note?: string | null; disclaimer: string;
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

export function DeskAppraisalModal({
  jibun, areaSqm, onClose, onApply,
}: {
  jibun: string; areaSqm: number | null;
  onClose: () => void; onApply: (totalWon: number) => void;
}) {
  const [official, setOfficial] = useState<string>("");
  const [gfa, setGfa] = useState<string>("");
  const [structure, setStructure] = useState("RC");
  const [year, setYear] = useState<string>("");
  const [rent, setRent] = useState<string>("");
  const [deposit, setDeposit] = useState<string>("");
  const [cap, setCap] = useState<string>("4.5");
  const [res, setRes] = useState<Result | null>(null);
  const [busy, setBusy] = useState<"" | "run" | "pdf" | "pptx" | "docx">("");
  const [err, setErr] = useState<string | null>(null);

  const body = () => ({
    address: jibun, area_sqm: areaSqm ?? undefined,
    official_price_per_sqm: official ? Number(official) : undefined,
    building_gfa_sqm: gfa ? Number(gfa) : undefined,
    building_structure: gfa ? structure : undefined,
    building_year_built: year ? Number(year) : undefined,
    monthly_rent_won: rent ? Number(rent) : undefined,
    deposit_won: deposit ? Number(deposit) : undefined,
    cap_rate: cap ? Number(cap) / 100 : undefined,
  });

  const run = async () => {
    if (!jibun.trim()) { setErr("지번이 없습니다. 토지조서에서 지번을 입력하세요."); return; }
    setBusy("run"); setErr(null);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      const r = await fetch(`${apiBase()}/land-price/desk-appraisal`, {
        method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body()),
      });
      if (!r.ok) { setErr(`서버 오류(${r.status}) — 잠시 후 다시 시도하세요.`); return; }
      const d = await r.json();
      if (d?.ok) setRes(d);
      else setErr((d?.message || "추정 실패") + " — 공시지가가 자동조회되지 않으면 위 ‘공시지가(원/㎡)’에 직접 입력 후 다시 실행하세요.");
    } catch { setErr("추정 요청 실패 — 네트워크 확인 후 다시 시도하세요."); } finally { setBusy(""); }
  };

  // 모달 진입 시 1회 자동 조회(지번 기반 실데이터). 실패 시 사용자가 공시지가 직접 입력 가능.
  const autoRan = useRef(false);
  useEffect(() => {
    if (autoRan.current) return;
    autoRan.current = true;
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 통합 보고서 생성엔진: PDF/PPT/Word 중 선택(같은 데이터·같은 디자인).
  const downloadReport = async (format: "pdf" | "pptx" | "docx") => {
    setBusy(format); setErr(null);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")) || "";
      // 화면에 확보된 공시지가·PNU·면적을 넘겨 재지오코딩 의존 제거(신뢰성)
      const pdfBody = {
        ...body(),
        pnu: res?.pnu ?? undefined,
        official_price_per_sqm: official ? Number(official) : (res?.official_price_per_sqm ?? undefined),
        area_sqm: areaSqm ?? res?.area_sqm ?? undefined,
      };
      const r = await fetch(`${apiBase()}/land-price/desk-appraisal/pdf?format=${format}`, {
        method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(pdfBody),
      });
      // 성공=바이너리. 실패=JSON(공시지가 미확인 등) → 정직 표기.
      if (!r.ok || (r.headers.get("content-type") || "").includes("json")) { setErr("리포트 생성 실패"); return; }
      const blob = await r.blob(); const url = URL.createObjectURL(blob);
      const a = document.createElement("a"); a.href = url; a.download = `토지예상가치추정_${jibun}.${format}`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { setErr("리포트 다운로드 실패"); } finally { setBusy(""); }
  };

  const inp = "h-9 w-full rounded-lg border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div className="max-h-[90vh] w-full max-w-3xl overflow-auto rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-start justify-between">
          <div>
            <h3 className="text-base font-bold text-[var(--text-primary)]">예상 시세 추정 (상세)</h3>
            <p className="text-xs text-[var(--text-secondary)]">{jibun}{areaSqm ? ` · ${areaSqm.toLocaleString()}㎡` : ""} — 감정평가 아님(참고용)</p>
          </div>
          <button onClick={onClose} className="text-[var(--text-tertiary)] hover:text-[var(--text-primary)]">✕</button>
        </div>

        {/* 입력 */}
        <div className="mt-4 grid grid-cols-2 gap-3 md:grid-cols-4">
          <label className="text-xs text-[var(--text-secondary)]">공시지가(원/㎡, 선택)<NumberInput className={`${inp} mt-1`} value={official === "" ? null : Number(official)} onChange={(n) => setOfficial(n != null ? String(n) : "")} placeholder="자동조회" /></label>
          <label className="text-xs text-[var(--text-secondary)]">건물 연면적(㎡)<NumberInput allowDecimal className={`${inp} mt-1`} value={gfa === "" ? null : Number(gfa)} onChange={(n) => setGfa(n != null ? String(n) : "")} placeholder="복합 시" /></label>
          <label className="text-xs text-[var(--text-secondary)]">구조<select className={`${inp} mt-1`} value={structure} onChange={(e) => setStructure(e.target.value)}>{["RC", "SRC", "철골", "조적", "목조"].map((s) => <option key={s} value={s}>{s}</option>)}</select></label>
          <label className="text-xs text-[var(--text-secondary)]">준공연도<input className={`${inp} mt-1`} type="number" value={year} onChange={(e) => setYear(e.target.value)} placeholder="예 2010" /></label>
          <label className="text-xs text-[var(--text-secondary)]">월 임대료(원)<NumberInput className={`${inp} mt-1`} value={rent === "" ? null : Number(rent)} onChange={(n) => setRent(n != null ? String(n) : "")} placeholder="수익환원 시" /></label>
          <label className="text-xs text-[var(--text-secondary)]">보증금(원)<NumberInput className={`${inp} mt-1`} value={deposit === "" ? null : Number(deposit)} onChange={(n) => setDeposit(n != null ? String(n) : "")} /></label>
          <label className="text-xs text-[var(--text-secondary)]">자본환원율(%)<input className={`${inp} mt-1`} type="number" value={cap} onChange={(e) => setCap(e.target.value)} /></label>
          <div className="flex items-end"><button onClick={run} disabled={busy !== ""} className="h-9 w-full rounded-lg bg-[var(--accent-strong)] text-sm font-bold text-white disabled:opacity-50">{busy === "run" ? "분석 중…" : "분석 시작"}</button></div>
        </div>

        {err && <p className="mt-3 text-xs font-semibold text-red-500">{err}</p>}
        {busy === "run" && !res && <p className="mt-3 text-xs text-[var(--text-secondary)]">실데이터 조회 중… (공시지가·실거래·시점수정)</p>}

        {res && (
          <div className="mt-5 space-y-4">
            {/* 채택가 + 신뢰도 게이지 */}
            <div className="rounded-xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-4">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-xs font-black uppercase tracking-widest text-[var(--text-hint)]">토지 예상 채택가</span>
                <span className="text-2xl font-[1000] text-[var(--accent-strong)]">{eok(res.appraised_total_won)}</span>
              </div>
              <p className="mt-0.5 text-xs text-[var(--text-secondary)]">{res.appraised_price_per_sqm?.toLocaleString()}원/㎡ · 범위 {res.range_per_sqm?.low?.toLocaleString()}~{res.range_per_sqm?.high?.toLocaleString()}</p>
              <div className="mt-2"><Gauge value={res.confidence} /></div>
            </div>

            {/* 방법별 */}
            <div>
              <p className="mb-1 text-xs font-bold text-[var(--text-secondary)]">산정방법별 추정</p>
              <div className="space-y-1.5">
                {(res.methods ?? []).map((m) => (
                  <div key={m.method} className="rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-[11px]">
                    <span className="font-bold text-[var(--text-primary)]">{m.method} {Math.round(m.unit_price).toLocaleString()}원/㎡</span>
                    <span className="text-[var(--text-tertiary)]"> — {m.rationale}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* 복수 시나리오 교차검증 */}
            {res.cross_check && (
              <div>
                <p className="mb-1 text-xs font-bold text-[var(--text-secondary)]">복수 시나리오 교차검증 (평균 {res.cross_check.mean.toLocaleString()}원/㎡ · CV {res.cross_check.cv_pct}%)</p>
                <div className="flex gap-1">
                  {(res.cross_check.firms ?? []).map((v, i) => (
                    <div key={i} className="flex-1 rounded bg-[var(--surface-soft)] px-1 py-1 text-center text-[10px] text-[var(--text-secondary)]">{Math.round(v / 1e4).toLocaleString()}만</div>
                  ))}
                </div>
              </div>
            )}

            {/* 복합/수익환원 */}
            {(res.building || res.income) && (
              <div className="grid gap-2 md:grid-cols-2">
                {res.building && (
                  <div className="rounded-lg border border-[var(--line)] p-3 text-[11px]">
                    <p className="font-bold text-[var(--text-primary)]">원가법 복합(토지+건물) {eok(res.complex_total_won)}</p>
                    <p className="mt-0.5 text-[var(--text-secondary)]">건물 {eok(res.building.building_value_won)} — {res.building.rationale}</p>
                  </div>
                )}
                {res.income && (
                  <div className="rounded-lg border border-[var(--line)] p-3 text-[11px]">
                    <p className="font-bold text-[var(--text-primary)]">수익환원법 {eok(res.income_total_won)}</p>
                    <p className="mt-0.5 text-[var(--text-secondary)]">{res.income.rationale}</p>
                  </div>
                )}
              </div>
            )}

            {/* 메타 */}
            <p className="text-[10px] text-[var(--text-hint)]">
              {res.time_adjust_basis ? `시점수정: ${res.time_adjust_basis} · ` : ""}{res.road_side ? `접도 ${res.road_side} · ` : ""}{res.weight_note}
            </p>
            <p className="text-[10px] text-[var(--text-hint)]">{res.disclaimer}</p>

            <div className="flex flex-wrap gap-2">
              {res.appraised_total_won != null && (
                <button onClick={() => { onApply(res.complex_total_won ?? res.appraised_total_won!); onClose(); }} className="h-9 rounded-lg bg-[var(--accent-strong)] px-4 text-sm font-bold text-white">매입예정가에 반영</button>
              )}
              {([["pdf", "PDF"], ["pptx", "PPT"], ["docx", "Word"]] as const).map(([fmt, label]) => (
                <button key={fmt} onClick={() => void downloadReport(fmt)} disabled={busy !== ""} className="h-9 rounded-lg border border-[var(--border)] px-4 text-sm font-semibold text-[var(--text-primary)] disabled:opacity-50">{busy === fmt ? `${label} 생성 중…` : `${label} ↓`}</button>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
