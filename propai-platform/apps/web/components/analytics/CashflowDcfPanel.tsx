"use client";

/**
 * 수동 세부조정 · 다기간 DCF 월별 현금흐름(은행제출용) — 보조 도구.
 *
 * 위치: 투자수익성 워크플로우의 '보조' 단계(기본 접힘). 개략수지 base(RoughScenarioPanel)가
 * 이미 월별 DCF를 산출하므로, 이 패널은 그 결과를 손으로 세밀 조정하고 은행제출용 엑셀로
 * 내보내는 용도로만 강등 운용한다(동일 화면 DCF 2벌 과잉 해소).
 *
 * 무목업 원칙:
 *  (a) 토지비·공사비·분양수입은 store(개략수지/수지 SSOT)에서 파생·자동 프리필하고,
 *      store가 갱신되면 자동 재프리필한다(마운트 1회 캡처로 stale 되던 결함 제거).
 *  (b) 가짜 기본값(예전 180/400/100 하드코딩)을 만들지 않는다. 결측 축은 빈칸 + '수지 미산출'
 *      정직표기로 두고, 세 축이 채워져야 계산·엑셀 버튼이 활성화된다.
 *  (c) 값이 store(감정가·공사비·수지)에서 오면 그 출처 배지를 붙인다.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { DEFAULT_EQUITY_RATIO_PCT } from "@/lib/finance/leverage";

type Row = { month: number; phase: string; inflow: number; outflow: number; net: number; cumulative: number };
type Summary = {
  total_months: number; total_inflow: number; total_outflow: number; net_profit: number;
  profit_rate_pct: number; peak_negative_cashflow: number; equity_amount: number;
  bridge_loan_amount: number; pf_loan_amount: number; irr_annual_pct: number | null;
  npv_won: number; discount_rate_annual_pct: number;
};
type CashflowResult = { rows: Row[]; summary: Summary };

const eok = (won: number | null | undefined) =>
  won != null ? `${(won / 1e8).toLocaleString(undefined, { maximumFractionDigits: 1 })}억` : "—";

/** 원 → 억(소수1자리). 값 없거나 0 이하면 null(무목업 — 가짜 기본값 만들지 않음). */
const toEok = (won: number | null | undefined): number | null =>
  won != null && Number.isFinite(won) && won > 0 ? Math.round((won / 1e8) * 10) / 10 : null;

/** v2 절대 URL(엑셀 blob 다운로드용) — apiClient 규칙과 동일 호스트 매핑. */
function v2Url(path: string): string {
  if (typeof window !== "undefined") {
    const h = window.location.hostname;
    if (h === "4t8t.net" || h === "www.4t8t.net" || h.endsWith(".pages.dev") || h === "propai.kr")
      return `https://api.4t8t.net/api/v2${path}`;
    return `http://localhost:8000/api/v2${path}`;
  }
  return `https://api.4t8t.net/api/v2${path}`;
}

export function CashflowDcfPanel() {
  const projectId = useProjectContextStore((s) => s.projectId);
  const cost = useProjectContextStore((s) => s.costData);
  const feas = useProjectContextStore((s) => s.feasibilityData);
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const setEquityRatioPct = useProjectContextStore((s) => s.setEquityRatioPct);

  // ★store(개략수지/수지 SSOT)에서 파생한 프리필값(억). 없으면 null(무목업).
  const derivedLandEok = useMemo(() => toEok(site?.estimatedValue), [site?.estimatedValue]);
  const derivedConEok = useMemo(
    () => toEok(cost?.totalConstructionCostWon ?? feas?.totalCostWon),
    [cost?.totalConstructionCostWon, feas?.totalCostWon],
  );
  const derivedRevEok = useMemo(() => toEok(feas?.totalRevenueWon), [feas?.totalRevenueWon]);

  // 각 파생값의 출처 라벨(무목업 배지용) — 실데이터가 어디서 왔는지 정직 표기.
  const landSource = derivedLandEok != null ? "부지 감정가 연동" : null;
  const conSource =
    cost?.totalConstructionCostWon != null && cost.totalConstructionCostWon > 0
      ? "공사비 정밀 연동"
      : feas?.totalCostWon != null && feas.totalCostWon > 0
        ? "수지 총사업비 연동"
        : null;
  const revSource = derivedRevEok != null ? "수지 매출 연동" : null;

  // 편집 가능한 로컬 상태(억). 초기값은 파생값, 이후 store가 바뀌면 useEffect로 자동 재프리필.
  const [landEok, setLandEok] = useState<number | null>(derivedLandEok);
  const [conEok, setConEok] = useState<number | null>(derivedConEok);
  const [revEok, setRevEok] = useState<number | null>(derivedRevEok);
  // ★수동수정 보호(dirty) — 사용자가 직접 고친 필드는 같은 프로젝트 내 업스트림 갱신으로 덮어쓰지 않는다.
  //   (예전: 무조건 재프리필 → 손으로 넣은 매입가·공사비가 재분석 순간 날아감). 프로젝트 전환 시 초기화.
  const dirtyRef = useRef({ land: false, con: false, rev: false });

  // 프로젝트 전환: dirty 해제 + 새 프로젝트 파생값으로 강제 프리필(이전 프로젝트 편집값 잔존 방지).
  useEffect(() => {
    dirtyRef.current = { land: false, con: false, rev: false };
    setLandEok(derivedLandEok);
    setConEok(derivedConEok);
    setRevEok(derivedRevEok);
    // 프로젝트 id 기준으로만 리셋(파생값은 아래 개별 effect가 담당) —
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  // 같은 프로젝트 내 자동 재프리필 — 사용자가 손대지 않은 필드만 store 변경을 따라간다(stale 해소).
  useEffect(() => { if (!dirtyRef.current.land) setLandEok(derivedLandEok); }, [derivedLandEok]);
  useEffect(() => { if (!dirtyRef.current.con) setConEok(derivedConEok); }, [derivedConEok]);
  useEffect(() => { if (!dirtyRef.current.rev) setRevEok(derivedRevEok); }, [derivedRevEok]);

  // 입력창 편집용 setter — 수정 순간 dirty 표시(수동 우선).
  const editLand = (n: number | null) => { dirtyRef.current.land = true; setLandEok(n); };
  const editCon = (n: number | null) => { dirtyRef.current.con = true; setConEok(n); };
  const editRev = (n: number | null) => { dirtyRef.current.rev = true; setRevEok(n); };

  // 공정 가정치(편집 가능) — 착공~준공/분양시작/할인율. 부동산개발 표준 가정 기본값(가짜 매출·원가 아님).
  const [conMonths, setConMonths] = useState(24);
  const [saleStart, setSaleStart] = useState(6);
  // ★자기자본(%)는 로컬이 아니라 SSOT(feasibilityData.equityRatioPct)를 읽/쓴다 —
  //  투자수익성 요약 카드와 동일 슬롯을 공유해 여기서 바꾸면 요약도 즉시 반영된다(기본 10%).
  const equityPct = feas?.equityRatioPct ?? DEFAULT_EQUITY_RATIO_PCT;
  const setEquityPct = (n: number) => setEquityRatioPct(n);
  const [discPct, setDiscPct] = useState(6);

  const [open, setOpen] = useState(false); // 보조 도구 — 기본 접힘
  const [result, setResult] = useState<CashflowResult | null>(null);
  const [busy, setBusy] = useState<"" | "calc" | "excel">("");
  const [error, setError] = useState<string | null>(null);

  // ★무목업 계산 게이트 — 핵심 3축(토지비·공사비·분양수입)이 모두 채워져야 계산한다.
  const canCalc = landEok != null && conEok != null && revEok != null;

  const body = () => ({
    land_cost_won: (landEok ?? 0) * 1e8,
    construction_cost_won: (conEok ?? 0) * 1e8,
    total_revenue_won: (revEok ?? 0) * 1e8,
    construction_months: conMonths,
    sale_start_month: saleStart,
    equity_ratio: equityPct / 100,
    discount_rate_annual: discPct / 100,
  });

  const calc = async () => {
    if (!canCalc) return;
    setBusy("calc"); setError(null);
    try {
      const r = await apiClient.postV2<CashflowResult>("/feasibility/cashflow", { body: body() });
      setResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "현금흐름 산정 실패");
    } finally { setBusy(""); }
  };

  const downloadExcel = async () => {
    if (!canCalc) return;
    setBusy("excel"); setError(null);
    try {
      const token = (typeof window !== "undefined" && localStorage.getItem("propai_access_token")?.trim()) || "";
      const res = await fetch(v2Url("/feasibility/cashflow/excel"), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify(body()),
      });
      if (!res.ok) throw new Error(`다운로드 실패 (${res.status})`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url; a.download = "propai_cashflow_dcf.xlsx";
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "엑셀 다운로드 실패");
    } finally { setBusy(""); }
  };

  const s = result?.summary;
  const numCls = "h-9 w-full rounded-lg border border-[var(--line)] bg-[var(--surface)] px-3 text-sm text-[var(--text-primary)]";

  // 핵심 3축(연동·nullable) — 출처배지 또는 '수지 미산출' 정직표기.
  const linkedFields: Array<{ label: string; val: number | null; set: (n: number | null) => void; source: string | null }> = [
    { label: "토지비(억)", val: landEok, set: editLand, source: landSource },
    { label: "공사비(억)", val: conEok, set: editCon, source: conSource },
    { label: "분양수입(억)", val: revEok, set: editRev, source: revSource },
  ];
  // 공정 가정치(non-null) — 기간·자기자본·할인율.
  const processFields: Array<{ label: string; val: number; set: (n: number) => void }> = [
    { label: "공사기간(월)", val: conMonths, set: setConMonths },
    { label: "분양시작(월)", val: saleStart, set: setSaleStart },
    { label: "자기자본(%)", val: equityPct, set: setEquityPct },
    { label: "할인율(%)", val: discPct, set: setDiscPct },
  ];

  return (
    <Card>
      <CardContent className="p-6 space-y-5">
        {/* 접이식 헤더(기본 접힘) — 은행제출용 수동 세부조정 보조임을 명시 */}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="flex w-full items-center justify-between gap-3 text-left"
        >
          <div>
            <div className="mb-1 flex items-center gap-3">
              <span className="cc-meta">DCF · MANUAL FINE-TUNING</span>
              {s && <span className="cc-live"><i />COMPUTED</span>}
            </div>
            <h3 className="text-base font-bold text-[var(--text-primary)]">수동 세부조정 · 다기간 DCF (은행제출용)</h3>
            <p className="mt-0.5 text-xs text-[var(--text-secondary)]">개략수지 결과를 세부 조정·엑셀 내보내기. 필요할 때만 펼쳐 사용하세요.</p>
          </div>
          <span className="shrink-0 text-sm font-semibold text-[var(--accent-strong)]">{open ? "▾ 닫기" : "▸ 열기"}</span>
        </button>

        {open && (
          <>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              {linkedFields.map(({ label, val, set, source }) => (
                <label key={label} className="text-xs text-[var(--text-secondary)]">
                  {label}
                  <input
                    type="number"
                    className={`${numCls} mt-1`}
                    value={val ?? ""}
                    placeholder="수지 미산출"
                    onChange={(e) => set(e.target.value === "" ? null : Number(e.target.value))}
                  />
                  {source ? (
                    <span className="sa-chip sa-chip--accent mt-1 inline-block" title={`데이터 출처: ${source}`}>{source}</span>
                  ) : val == null ? (
                    <span className="sa-chip sa-chip--warning mt-1 inline-block" title="개략수지/수지가 아직 산출되지 않았습니다">수지 미산출</span>
                  ) : null}
                </label>
              ))}
              {processFields.map(({ label, val, set }) => (
                <label key={label} className="text-xs text-[var(--text-secondary)]">
                  {label}
                  <input type="number" className={`${numCls} mt-1`} value={val}
                    onChange={(e) => set(Number(e.target.value))} />
                </label>
              ))}
            </div>

            {!canCalc && (
              <p className="text-xs font-semibold text-[var(--status-warning)]">
                토지비·공사비·분양수입이 채워져야 계산합니다. 위 개략수지를 먼저 생성하거나 값을 직접 입력하세요.
              </p>
            )}

            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={calc} disabled={busy !== "" || !canCalc}
                className="h-9 rounded-lg bg-[var(--accent-strong)] px-4 text-sm font-bold text-white disabled:opacity-50">
                {busy === "calc" ? "산정 중…" : "현금흐름 계산"}
              </button>
              <button type="button" onClick={downloadExcel} disabled={busy !== "" || !canCalc}
                className="h-9 rounded-lg border border-[var(--line)] px-4 text-sm font-semibold text-[var(--text-primary)] disabled:opacity-50">
                {busy === "excel" ? "생성 중…" : "엑셀 다운로드 ↓"}
              </button>
            </div>

            {error && <p className="text-xs font-semibold text-[var(--status-error)]">{error}</p>}

            {s && (
              <>
                <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  <Tile label="IRR(연)" value={s.irr_annual_pct != null ? `${s.irr_annual_pct}%` : "산정불가"} accent />
                  <Tile label={`NPV(할인 ${s.discount_rate_annual_pct}%)`} value={eok(s.npv_won)} />
                  <Tile label="순이익" value={eok(s.net_profit)} sub={`수익률 ${s.profit_rate_pct}%`} />
                  <Tile label="최대 자금소요(peak)" value={eok(s.peak_negative_cashflow)} sub={`자기자본 ${eok(s.equity_amount)}`} />
                </div>

                <div className="max-h-[360px] overflow-auto rounded-xl border border-[var(--line)]">
                  <table className="w-full text-xs">
                    <thead className="sticky top-0 bg-[var(--surface-soft)]">
                      <tr className="text-[var(--text-hint)]">
                        {["월", "단계", "유입", "유출", "순현금", "누적"].map((h) => (
                          <th key={h} className="px-3 py-2 text-right font-bold first:text-left">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result!.rows.map((r) => (
                        <tr key={r.month} className="border-t border-[var(--line)]">
                          <td className="px-3 py-1.5 text-[var(--text-secondary)]">{r.month}</td>
                          <td className="px-3 py-1.5 text-[var(--text-secondary)]">{r.phase}</td>
                          <td className="cc-num px-3 py-1.5 text-right text-[var(--text-primary)]">{r.inflow ? eok(r.inflow) : "-"}</td>
                          <td className="cc-num px-3 py-1.5 text-right text-[var(--text-primary)]">{r.outflow ? eok(r.outflow) : "-"}</td>
                          <td className="cc-num px-3 py-1.5 text-right font-semibold"
                            style={{ color: r.net < 0 ? "var(--status-error)" : "var(--status-success)" }}>{eok(r.net)}</td>
                          <td className="cc-num px-3 py-1.5 text-right"
                            style={{ color: r.cumulative < 0 ? "var(--status-error)" : "var(--text-primary)" }}>{eok(r.cumulative)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Tile({ label, value, sub, accent }: { label: string; value: string; sub?: string; accent?: boolean }) {
  return (
    <div className="cc-panel cc-bracketed cc-interactive px-4 py-3">
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--br" />
      <div className="cc-grid-bg opacity-25" />
      <div className="relative">
        <p className="cc-label">{label}</p>
        <p className={`cc-num mt-1 text-lg font-[1000] ${accent ? "cc-num--data" : "text-[var(--text-primary)]"}`}>{value}</p>
        {sub ? <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">{sub}</p> : null}
      </div>
    </div>
  );
}
