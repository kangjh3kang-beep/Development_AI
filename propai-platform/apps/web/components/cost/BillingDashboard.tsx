"use client";

/**
 * D2 — 기성고 EVM + 과다청구 이상탐지.
 *  ① 기성 청구 등록 폼: 회차·공종·계약액·청구액·진행률·기간(+선택 단가)
 *     → POST /api/v1/cost/{pid}/billing → 등록 후 목록·EVM 갱신, anomalies_triggered 즉시 경고.
 *  ② EVM 시각화: PV/EV/AC 누적 곡선(LineChart, curve[]) + SPI·CPI 배지(null→"산정불가", <0.9 경고색)
 *     + 계약총액 대비 누적청구 바.
 *  ③ 과다청구 이상탐지: anomalies[](high=빨강/warn=주황) 쉬운 설명.
 *  ④ 무결성: claims.ledger_hash(해시체인 변조탐지) + "검토 권장·확정 아님" 정직 배지.
 * GET /api/v1/cost/{pid}/billing. 추정치 — 전문 검토 권장.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import type {
  BillingAnomaly,
  BillingRegisterRequest,
  BillingRegisterResponse,
  BillingSummaryResponse,
} from "@/components/cost/cmTypes";

const fcls =
  "w-full rounded-lg border border-[var(--line-strong)] bg-[var(--surface-strong)] px-3 py-2 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]";

function eok(v?: number | null): string {
  if (v == null || isNaN(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "−" : "";
  if (abs >= 1e8) return `${sign}${(abs / 1e8).toFixed(2)}억`;
  if (abs >= 1e4) return `${sign}${Math.round(abs / 1e4).toLocaleString()}만`;
  return `${sign}${Math.round(abs).toLocaleString()}원`;
}

function pct(v?: number | null): string {
  if (v == null || isNaN(v)) return "—";
  return `${v.toFixed(1)}%`;
}

/** evidence(객체/문자/숫자) → 사람이 읽을 한 줄. */
function evidenceText(ev: BillingAnomaly["evidence"]): string {
  if (ev == null) return "";
  if (typeof ev === "string" || typeof ev === "number") return String(ev);
  return Object.entries(ev)
    .map(([k, val]) => `${k}: ${typeof val === "number" ? val.toLocaleString() : String(val)}`)
    .join(" · ");
}

const ANOMALY_LABEL: Record<string, string> = {
  unit_price_overclaim: "청구단가 과다",
  cumulative_over_contract: "누적청구 계약초과",
  low_spi: "일정 지연(SPI 저조)",
  low_cpi: "원가 초과(CPI 저조)",
  claim_surge: "청구액 급증",
};

function AnomalyRow({ a }: { a: BillingAnomaly }) {
  const high = a.level === "high";
  const ev = evidenceText(a.evidence);
  return (
    <div
      className={`rounded-xl border p-3.5 ${
        high
          ? "border-[var(--status-error)]/40 bg-[var(--status-error)]/10"
          : "border-[var(--status-warning)]/40 bg-[var(--status-warning)]/10"
      }`}
    >
      <div className="flex items-center gap-2">
        <span
          className={`rounded px-1.5 py-0.5 text-[10px] font-black ${
            high ? "bg-[var(--status-error)]/25 text-[var(--status-error)]" : "bg-[var(--status-warning)]/25 text-[var(--status-warning)]"
          }`}
        >
          {high ? "높음" : "주의"}
        </span>
        <span className="text-[13px] font-bold text-[var(--text-primary)]">
          {ANOMALY_LABEL[a.type] ?? a.type}
        </span>
      </div>
      <p className="mt-1.5 text-[13px] leading-relaxed text-[var(--text-secondary)]">{a.detail}</p>
      {ev && (
        <p className="mt-1 text-[11px] font-mono text-[var(--text-tertiary)]">근거 · {ev}</p>
      )}
    </div>
  );
}

/** SPI/CPI 배지: null→"산정불가", <0.9 경고색. */
function IndexBadge({ label, value, hint }: { label: string; value: number | null; hint: string }) {
  const naN = value == null;
  const warn = !naN && value < 0.9;
  return (
    <div
      className={`flex-1 rounded-2xl border p-4 ${
        naN
          ? "border-[var(--line-strong)] bg-[var(--surface-strong)]"
          : warn
            ? "border-[var(--status-error)]/40 bg-[var(--status-error)]/10"
            : "border-[var(--status-success)]/35 bg-[var(--status-success)]/10"
      }`}
    >
      <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{label}</p>
      <p
        className={`mt-1 text-2xl font-[1000] ${
          naN ? "text-[var(--text-tertiary)]" : warn ? "text-[var(--status-error)]" : "text-[var(--status-success)]"
        }`}
      >
        {naN ? "산정불가" : value.toFixed(2)}
      </p>
      <p className="mt-1 text-[11px] text-[var(--text-secondary)]">
        {naN ? "기준값(PV/AC)이 0이라 산정할 수 없습니다." : warn ? `${hint} · 주의` : hint}
      </p>
    </div>
  );
}

interface ClaimForm {
  round: string;
  work_type: string;
  contract_amount: string;
  claimed_amount: string;
  progress_pct: string;
  period: string;
  unit_price: string;
  contract_unit_price: string;
}

const EMPTY_FORM: ClaimForm = {
  round: "1",
  work_type: "골조",
  contract_amount: "",
  claimed_amount: "",
  progress_pct: "",
  period: "",
  unit_price: "",
  contract_unit_price: "",
};

export function BillingDashboard({ projectId: projectIdProp }: { projectId?: string }) {
  const ctxProjectId = useProjectContextStore((s) => s.projectId);
  const projectId = projectIdProp || ctxProjectId || "default";

  const [summary, setSummary] = useState<BillingSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const [form, setForm] = useState<ClaimForm>(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);
  const [formErr, setFormErr] = useState("");
  const [triggered, setTriggered] = useState<BillingAnomaly[] | null>(null);

  const setField = useCallback((patch: Partial<ClaimForm>) => {
    setForm((p) => ({ ...p, ...patch }));
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setErr("");
    try {
      const r = await apiClient.get<BillingSummaryResponse>(`/cost/${projectId}/billing`, {
        useMock: false,
        timeoutMs: 30000,
      });
      setSummary(r);
      if (!r.ok) setErr("기성·EVM 데이터를 불러오지 못했습니다.");
    } catch {
      setErr("기성·EVM 데이터 조회에 실패했습니다.");
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const submit = useCallback(async () => {
    const round = Number(form.round);
    const contract = Number(form.contract_amount);
    const claimed = Number(form.claimed_amount);
    const progress = Number(form.progress_pct);
    if (!round || round <= 0) {
      setFormErr("회차를 입력하세요.");
      return;
    }
    if (!contract || contract <= 0 || !claimed || claimed <= 0) {
      setFormErr("계약액·청구액을 입력하세요.");
      return;
    }
    if (!form.period.trim()) {
      setFormErr("청구 기간을 입력하세요(예: 2026-06).");
      return;
    }
    const body: BillingRegisterRequest = {
      round,
      work_type: form.work_type.trim() || "기타",
      contract_amount: contract,
      claimed_amount: claimed,
      progress_pct: isNaN(progress) ? 0 : progress,
      period: form.period.trim(),
    };
    if (form.unit_price) body.unit_price = Number(form.unit_price);
    if (form.contract_unit_price) body.contract_unit_price = Number(form.contract_unit_price);

    setSubmitting(true);
    setFormErr("");
    setTriggered(null);
    try {
      const r = await apiClient.post<BillingRegisterResponse>(`/cost/${projectId}/billing`, {
        body: body as unknown as Record<string, unknown>,
        useMock: false,
        timeoutMs: 45000,
      });
      if (!r.ok) {
        setFormErr("기성 등록에 실패했습니다.");
        return;
      }
      setTriggered(r.anomalies_triggered ?? []);
      setForm((p) => ({ ...EMPTY_FORM, round: String(round + 1), work_type: p.work_type }));
      await load();
    } catch {
      setFormErr("기성 등록 요청에 실패했습니다.");
    } finally {
      setSubmitting(false);
    }
  }, [form, projectId, load]);

  const noData = summary?.badges?.data === "no_data" || (summary?.ok && summary.claims?.length === 0);

  const evm = summary?.evm;
  const cumClaimed = useMemo(
    () => (summary ? (summary.claims ?? []).reduce((s, c) => s + (c.claimed_amount || 0), 0) : 0),
    [summary],
  );
  const overContract =
    summary && summary.contract_total > 0 && cumClaimed > summary.contract_total;
  const claimRatio =
    summary && summary.contract_total > 0
      ? Math.min((cumClaimed / summary.contract_total) * 100, 100)
      : 0;

  const curve = evm?.curve ?? [];

  return (
    <section className="grid gap-5">
      <div>
        <h2 className="text-xl font-black text-[var(--text-primary)]">기성·성과측정(EVM) (기성고 관리 + 과다청구 탐지)</h2>
        <p className="mt-1 text-sm text-[var(--text-secondary)]">
          회차별 기성 청구를 등록하면 <b className="text-[var(--text-primary)]">PV·EV·AC 누적 곡선</b>과{" "}
          <b className="text-[var(--text-primary)]">SPI·CPI</b>로 일정·원가 성과를 추적하고, 청구단가 이탈·계약초과 등{" "}
          <b className="text-[var(--text-primary)]">과다청구 이상</b>을 자동 경고합니다.
        </p>
      </div>

      {/* 정직성 배지 */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded bg-[var(--status-warning)]/15 px-2 py-0.5 text-[10px] font-bold text-[var(--status-warning)]">검토 권장 · 확정 아님</span>
        {summary?.badges?.unit_price_source && (
          <span className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">
            단가출처: {summary.badges.unit_price_source}
          </span>
        )}
        {summary?.badges?.note && (
          <span className="rounded bg-[var(--surface-muted)] px-2 py-0.5 text-[10px] font-bold text-[var(--text-tertiary)]">
            {summary.badges.note}
          </span>
        )}
      </div>

      {/* 기성 청구 등록 폼 */}
      <div className="grid gap-4 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
        <h3 className="text-sm font-black text-[var(--text-primary)]">기성 청구 등록</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">회차</span>
            <input value={form.round} onChange={(e) => setField({ round: e.target.value })} inputMode="numeric" className={fcls} placeholder="1" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">공종</span>
            <input value={form.work_type} onChange={(e) => setField({ work_type: e.target.value })} className={fcls} placeholder="골조" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">계약액(원)</span>
            <input value={form.contract_amount} onChange={(e) => setField({ contract_amount: e.target.value })} inputMode="decimal" className={fcls} placeholder="예: 5000000000" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">청구액(원)</span>
            <input value={form.claimed_amount} onChange={(e) => setField({ claimed_amount: e.target.value })} inputMode="decimal" className={fcls} placeholder="예: 500000000" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">진행률(%)</span>
            <input value={form.progress_pct} onChange={(e) => setField({ progress_pct: e.target.value })} inputMode="decimal" className={fcls} placeholder="예: 10" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">청구 기간</span>
            <input value={form.period} onChange={(e) => setField({ period: e.target.value })} className={fcls} placeholder="2026-06" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">청구단가(선택)</span>
            <input value={form.unit_price} onChange={(e) => setField({ unit_price: e.target.value })} inputMode="decimal" className={fcls} placeholder="(선택)" />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-[11px] font-semibold text-[var(--text-secondary)]">계약단가(선택)</span>
            <input value={form.contract_unit_price} onChange={(e) => setField({ contract_unit_price: e.target.value })} inputMode="decimal" className={fcls} placeholder="(선택)" />
          </label>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={submit}
            disabled={submitting}
            className="rounded-xl bg-[var(--accent-strong)] px-7 py-2.5 text-sm font-black text-white shadow-[var(--shadow-glow)] hover:opacity-90 disabled:opacity-50"
          >
            {submitting ? "등록 중…" : "기성 청구 등록"}
          </button>
          {formErr && <span className="text-xs font-semibold text-[var(--status-error)]">{formErr}</span>}
        </div>

        {/* 등록 즉시 트리거된 경고 */}
        {triggered && (
          <div className="grid gap-2">
            {triggered.length === 0 ? (
              <p className="rounded-lg bg-[var(--status-success)]/10 px-3 py-2 text-[12px] font-semibold text-[var(--status-success)]">
                ✓ 등록 완료 — 즉시 탐지된 이상 청구가 없습니다.
              </p>
            ) : (
              <>
                <p className="text-[12px] font-bold text-[var(--status-error)]">이번 청구에서 탐지된 이상 {triggered.length}건</p>
                {triggered.map((a, i) => (
                  <AnomalyRow key={i} a={a} />
                ))}
              </>
            )}
          </div>
        )}
      </div>

      {loading && (
        <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-6 text-center text-sm text-[var(--text-tertiary)]">
          기성·EVM 데이터를 불러오는 중…
        </p>
      )}
      {err && !loading && (
        <p className="rounded-xl border border-[var(--status-error)]/30 bg-[var(--status-error)]/10 px-4 py-3 text-sm font-semibold text-[var(--status-error)]">{err}</p>
      )}

      {summary && !loading && !err && noData && (
        <p className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-6 text-center text-sm text-[var(--text-tertiary)]">
          등록된 기성 청구가 없습니다. 위 폼에서 1회차 기성을 등록하면 EVM 곡선·성과지표가 나타납니다.
        </p>
      )}

      {summary && !loading && !err && !noData && evm && (
        <>
          {/* EVM 요약 + 지표 */}
          <div className="grid gap-3 lg:grid-cols-3">
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">계획가치 PV</p>
              <p className="mt-1 text-xl font-[1000] text-[var(--text-primary)]">{eok(evm.pv)}</p>
            </div>
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">달성가치 EV</p>
              <p className="mt-1 text-xl font-[1000] text-[var(--accent-strong)]">{eok(evm.ev)}</p>
            </div>
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
              <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">실투입 AC</p>
              <p className="mt-1 text-xl font-[1000] text-[var(--text-primary)]">{eok(evm.ac)}</p>
            </div>
          </div>

          <div className="flex flex-col gap-3 sm:flex-row">
            <IndexBadge label="SPI · 일정성과" value={evm.spi} hint="1.0 이상이면 일정대로 진행 중" />
            <IndexBadge label="CPI · 원가성과" value={evm.cpi} hint="1.0 이상이면 예산 내 진행 중" />
          </div>

          {/* 계약총액 대비 누적청구 바 */}
          <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
            <div className="flex items-baseline justify-between">
              <h3 className="text-sm font-black text-[var(--text-primary)]">계약총액 대비 누적청구</h3>
              <span className={`text-[12px] font-bold ${overContract ? "text-[var(--status-error)]" : "text-[var(--text-secondary)]"}`}>
                {eok(cumClaimed)} / {eok(summary.contract_total)} ({pct(summary.contract_total > 0 ? (cumClaimed / summary.contract_total) * 100 : null)})
              </span>
            </div>
            <div className="mt-2 h-3 w-full overflow-hidden rounded-full bg-[var(--surface-strong)]">
              <div
                className={`h-full rounded-full ${overContract ? "bg-[var(--status-error)]" : "bg-[var(--accent-strong)]"}`}
                style={{ width: `${claimRatio}%` }}
              />
            </div>
            {overContract && (
              <p className="mt-2 text-[12px] font-semibold text-[var(--status-error)]">
                누적청구가 계약총액을 초과했습니다 — 정산·계약변경 검토가 필요합니다.
              </p>
            )}
          </div>

          {/* PV/EV/AC 누적 곡선 */}
          {curve.length > 0 && (
            <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
              <h3 className="mb-4 text-sm font-black text-[var(--text-primary)]">EVM 누적 곡선 (회차별 PV·EV·AC)</h3>
              <div style={{ width: "100%", height: 280 }}>
                <ResponsiveContainer>
                  <LineChart data={curve} margin={{ top: 12, right: 16, left: 8, bottom: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" />
                    <XAxis
                      dataKey="round"
                      tick={{ fontSize: 11, fill: "var(--text-tertiary)" }}
                      tickFormatter={(v: number) => `${v}회차`}
                    />
                    <YAxis
                      tickFormatter={(v: number) => `${(v / 1e8).toFixed(0)}억`}
                      tick={{ fontSize: 11, fill: "var(--text-tertiary)" }}
                      width={48}
                    />
                    <Tooltip
                      contentStyle={{
                        background: "var(--surface-strong)",
                        border: "1px solid var(--line-strong)",
                        borderRadius: 12,
                        fontSize: 12,
                      }}
                      labelFormatter={(v) => `${v}회차`}
                      formatter={(val, name) => [eok(Number(val)), String(name).toUpperCase()]}
                    />
                    <Line type="monotone" dataKey="pv" name="PV" stroke="var(--text-tertiary)" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="ev" name="EV" stroke="var(--accent-strong)" strokeWidth={2.5} dot={false} />
                    <Line type="monotone" dataKey="ac" name="AC" stroke="var(--status-error)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <div className="mt-2 flex flex-wrap gap-4 text-[11px] font-semibold text-[var(--text-tertiary)]">
                <span className="flex items-center gap-1.5"><i className="inline-block h-2 w-3 rounded-sm" style={{ background: "var(--text-tertiary)" }} /> PV 계획가치</span>
                <span className="flex items-center gap-1.5"><i className="inline-block h-2 w-3 rounded-sm" style={{ background: "var(--accent-strong)" }} /> EV 달성가치</span>
                <span className="flex items-center gap-1.5"><i className="inline-block h-2 w-3 rounded-sm" style={{ background: "var(--status-error)" }} /> AC 실투입</span>
              </div>
            </div>
          )}

          {/* 과다청구 이상탐지 */}
          <div className="grid gap-3 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-5">
            <h3 className="text-sm font-black text-[var(--text-primary)]">과다청구 이상탐지</h3>
            {summary.anomalies?.length === 0 ? (
              <p className="rounded-lg bg-[var(--status-success)]/10 px-3 py-2.5 text-[13px] font-semibold text-[var(--status-success)]">
                ✓ 현재 탐지된 과다청구·이상 징후가 없습니다.
              </p>
            ) : (
              <div className="grid gap-2">
                {(summary.anomalies ?? []).map((a, i) => (
                  <AnomalyRow key={i} a={a} />
                ))}
              </div>
            )}
          </div>

          {/* 청구 내역 + 무결성(해시) */}
          <div className="overflow-hidden rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)]">
            <div className="flex items-center justify-between px-5 py-3">
              <h3 className="text-sm font-black text-[var(--text-primary)]">회차별 청구 내역</h3>
              <span className="text-[10px] font-bold text-[var(--text-tertiary)]">해시체인 적재 = 변조탐지</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[12px]">
                <thead>
                  <tr className="border-y border-[var(--line)] label-caps text-[var(--text-tertiary)]">
                    <th className="px-4 py-2 font-bold">회차</th>
                    <th className="px-4 py-2 font-bold">공종</th>
                    <th className="px-4 py-2 font-bold">기간</th>
                    <th className="px-4 py-2 text-right font-bold">계약액</th>
                    <th className="px-4 py-2 text-right font-bold">청구액</th>
                    <th className="px-4 py-2 text-right font-bold">진행률</th>
                    <th className="px-4 py-2 font-bold">무결성(해시)</th>
                  </tr>
                </thead>
                <tbody>
                  {(summary.claims ?? []).map((c, i) => (
                    <tr key={i} className="border-b border-[var(--line)] transition-colors last:border-0 hover:bg-[var(--accent-strong)]/5">
                      <td className="px-4 py-2 font-bold text-[var(--text-primary)]">{c.round}회</td>
                      <td className="px-4 py-2 text-[var(--text-secondary)]">{c.work_type}</td>
                      <td className="px-4 py-2 text-[var(--text-tertiary)]">{c.period}</td>
                      <td className="px-4 py-2 text-right font-mono text-[var(--text-secondary)]">{eok(c.contract_amount)}</td>
                      <td className="px-4 py-2 text-right font-mono font-bold text-[var(--text-primary)]">{eok(c.claimed_amount)}</td>
                      <td className="px-4 py-2 text-right font-mono text-[var(--text-secondary)]">{pct(c.progress_pct)}</td>
                      <td className="px-4 py-2">
                        {c.ledger_hash ? (
                          <span className="rounded bg-[var(--status-success)]/15 px-1.5 py-0.5 font-mono text-[10px] text-[var(--status-success)]" title={c.ledger_hash}>
                            {c.ledger_hash.slice(0, 10)}…
                          </span>
                        ) : (
                          <span className="text-[10px] text-[var(--text-tertiary)]">미적재</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
