"use client";

/**
 * 관리자 결제·매출 관리.
 *
 * ## ★이 화면의 설계 원칙
 *
 * **매출과 「어긋난 건」을 같은 화면에 둔다.** 대시보드가 매출만 보여 주면, 사용자가
 * 돈을 내고 못 받은 건은 **아무도 안 본다.** 그래서 미해결 목록이 맨 위에 온다 —
 * 숫자가 0 일 때만 조용하다.
 *
 * ## 키 입력은 여기 없다
 *
 * 토스 API 키는 **기존 키 금고**(`ApiKeyManagementPanel` → 「결제(PG)」 그룹)에서 넣는다.
 * `secret_store.CATALOG` 에 항목을 추가했으므로 그 화면에 **자동으로** 나타난다.
 * ★같은 일을 하는 UI 를 두 개 만들면 반드시 갈라진다 — 이 저장소가 반복해 데인 형태다.
 */

import { useCallback, useEffect, useState } from "react";

import { apiClient } from "@/lib/api-client";

type Health = {
  configured: boolean;
  secret_key_present: boolean;
  client_key_present: boolean;
  test_mode: boolean | null;
  key_pairing_ok: boolean;
  payment_mode: string;
  simulated_payments_enabled: boolean;
  warnings: string[];
};

type Summary = {
  days: number;
  paid_count: number;
  gross_krw: number;
  refunded_krw: number;
  net_krw: number;
  refund_count: number;
  refund_rate_pct: number;
  avg_order_krw: number;
  pending_count: number;
  canceled_count: number;
  payer_count: number;
};

type DailyRow = { day: string; gross_krw: number; refunded_krw: number; net_krw: number; paid_count: number };
type ProviderRow = { provider: string; count: number; gross_krw: number };
type FailureRow = { code: string; count: number; sample: string | null };
type PayerRow = { email_masked: string; count: number; gross_krw: number; net_krw: number };
type Unresolved = {
  receipt_id: string;
  order_id: string | null;
  order_no: string | null;
  payment_key: string | null;
  event: string;
  amount_krw: number | null;
  toss_message: string | null;
  created_at: string | null;
};

type RecentOrder = {
  id: string;
  order_no: string;
  email_masked: string;
  amount_krw: number;
  refunded_krw: number;
  /** ★환불 가능액은 **서버가 계산해 준다** — 화면이 계산하면 두 곳이 갈린다. */
  refundable_krw: number;
  status: string;
  provider: string | null;
  paid_at: string | null;
};

type Revenue = {
  summary: Summary;
  daily: DailyRow[];
  by_provider: ProviderRow[];
  failure_reasons: FailureRow[];
  top_payers: PayerRow[];
  unresolved: Unresolved[];
  recent_orders: RecentOrder[];
};

const krw = (n: number | null | undefined) =>
  typeof n === "number" ? `${n.toLocaleString("ko-KR")}원` : "-";

/** ★미해결 이벤트가 **무엇을 뜻하는지** 관리자에게 말한다. 코드만 보여 주면 못 고친다. */
const UNRESOLVED_MEANING: Record<string, string> = {
  unknown: "승인 여부 미확정 — 돈이 움직였는지 알 수 없습니다. 재조회하세요.",
  apply_failed: "★결제는 됐는데 코인이 지급되지 않았습니다. 최우선 처리 대상입니다.",
};

export function PaymentAdminPanel() {
  const [health, setHealth] = useState<Health | null>(null);
  const [rev, setRev] = useState<Revenue | null>(null);
  const [days, setDays] = useState(30);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const [h, r] = await Promise.all([
        apiClient.get<Health>("/billing/admin/payments/health", { useMock: false }),
        apiClient.get<Revenue>(`/billing/admin/payments/revenue?days=${days}`, { useMock: false }),
      ]);
      setHealth(h);
      setRev(r);
    } catch (e) {
      // ★조회 실패를 '데이터 없음'으로 위장하지 않는다.
      const detail = (e as { payload?: { detail?: unknown } })?.payload?.detail;
      setError(typeof detail === "string" ? detail : "결제 관리 정보를 불러오지 못했습니다.");
    }
  }, [days]);

  useEffect(() => {
    void load();
  }, [load]);

  const reconcile = async (orderId: string) => {
    setBusy(true);
    setNotice(null);
    try {
      const r = await apiClient.post<{ action: string }>(
        `/billing/admin/payments/${orderId}/reconcile`,
        { useMock: false },
      );
      setNotice(`정합성 회복: ${r.action}`);
      await load();
    } catch (e) {
      const detail = (e as { payload?: { detail?: unknown } })?.payload?.detail;
      setNotice(typeof detail === "string" ? detail : "재조회에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const refund = async (o: RecentOrder) => {
    const reason = window.prompt(
      `주문 ${o.order_no}(${o.email_masked}) 환불 사유 — **미사용분만** 환불됩니다(주문 미환불 잔액 ${krw(o.refundable_krw)})`,
    );
    if (!reason || reason.trim().length < 2) return;
    setBusy(true);
    setNotice(null);
    try {
      const r = await apiClient.post<{
        refunded_krw: number;
        unrefundable_consumed_krw?: number;
      }>(`/billing/admin/orders/${o.id}/refund`, {
        body: { reason: reason.trim() },
        useMock: false,
      });
      const consumed = r.unrefundable_consumed_krw ?? 0;
      // ★관리자에게도 **왜 이만큼인지** 말한다(미사용분만 정책).
      setNotice(
        consumed > 0
          ? `미사용분 ${krw(r.refunded_krw)} 환불 · 사용분 ${krw(consumed)} 은 환불 대상이 아닙니다.`
          : `${krw(r.refunded_krw)} 환불 처리했습니다.`,
      );
      await load();
    } catch (e) {
      // ★사유를 버리지 않는다 — 관리자가 무엇이 막혔는지 알아야 다음 조치를 정한다.
      const d = (e as { payload?: { detail?: unknown } })?.payload?.detail;
      const msg =
        d && typeof d === "object"
          ? `${(d as { message?: string }).message ?? ""} ${(d as { remediation?: string }).remediation ?? ""}`.trim()
          : typeof d === "string"
            ? d
            : "환불에 실패했습니다.";
      setNotice(msg);
    } finally {
      setBusy(false);
    }
  };

  /** 계좌이체 등 오프라인 입금 확인 후 관리자가 직접 지급한다(`provider="manual"`). */
  const manualConfirm = async (o: RecentOrder) => {
    if (!window.confirm(`주문 ${o.order_no}(${krw(o.amount_krw)})을 입금 확인 처리할까요?`)) return;
    setBusy(true);
    setNotice(null);
    try {
      await apiClient.post(`/billing/admin/orders/${o.id}/confirm`, { useMock: false });
      setNotice(`주문 ${o.order_no} 을 수동 확정했습니다.`);
      await load();
    } catch (e) {
      const d = (e as { payload?: { detail?: unknown } })?.payload?.detail;
      setNotice(typeof d === "string" ? d : "수동 확정에 실패했습니다.");
    } finally {
      setBusy(false);
    }
  };

  const s = rev?.summary;
  const maxDaily = Math.max(1, ...(rev?.daily ?? []).map((d) => d.gross_krw));

  return (
    <div className="space-y-4">
      {error ? (
        <p role="alert" className="rounded-lg bg-[rgba(220,38,38,0.1)] p-3 text-sm text-[var(--status-error)]">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p role="status" className="rounded-lg bg-[var(--surface-strong)] p-3 text-sm">
          {notice}
        </p>
      ) : null}

      {/* ── 연동 상태 ────────────────────────────────────────────── */}
      <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">결제 연동 상태</h2>
        {health ? (
          <>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Stat label="결제 경로" value={health.payment_mode} />
              <Stat label="클라이언트 키" value={health.client_key_present ? "설정됨" : "없음"} />
              <Stat label="시크릿 키" value={health.secret_key_present ? "설정됨" : "없음"} />
              <Stat
                label="환경"
                value={health.test_mode === null ? "-" : health.test_mode ? "테스트" : "라이브"}
              />
            </dl>
            {health.warnings.length > 0 ? (
              <ul className="mt-3 space-y-1" data-testid="payment-warnings">
                {health.warnings.map((w) => (
                  <li key={w} className="rounded bg-[rgba(217,119,6,0.12)] px-3 py-2 text-xs text-[var(--status-warning)]">
                    {w}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-xs text-[var(--status-success)]">경고 없음.</p>
            )}
            <p className="mt-3 text-xs text-[var(--text-tertiary)]">
              API 키는 <strong>설정 &gt; API 키 &gt; 「결제(PG)」</strong> 에서 등록·변경합니다.
            </p>
          </>
        ) : (
          <p className="mt-3 text-sm text-[var(--text-tertiary)]">불러오는 중…</p>
        )}
      </section>

      {/* ── ★미해결(돈과 산출물이 어긋난 건) — 매출보다 위 ────────── */}
      <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
        <h2 className="text-base font-semibold text-[var(--text-primary)]">
          확인이 필요한 결제{" "}
          <span className="text-sm font-normal text-[var(--text-tertiary)]">
            ({rev?.unresolved.length ?? 0}건)
          </span>
        </h2>
        {!rev ? (
          <p className="mt-3 text-sm text-[var(--text-tertiary)]">불러오는 중…</p>
        ) : rev.unresolved.length === 0 ? (
          <p className="mt-3 text-sm text-[var(--status-success)]">
            어긋난 결제가 없습니다.
          </p>
        ) : (
          <ul className="mt-3 space-y-2" data-testid="unresolved-list">
            {rev.unresolved.map((u) => (
              <li key={u.receipt_id} className="rounded-lg border border-[var(--line)] p-3">
                <div className="flex flex-wrap items-baseline gap-x-3 text-sm">
                  <span className="font-mono text-xs">{u.order_no ?? u.order_id ?? "-"}</span>
                  <span className="font-semibold text-[var(--status-warning)]">
                    {UNRESOLVED_MEANING[u.event] ?? u.event}
                  </span>
                  <span>{krw(u.amount_krw)}</span>
                  <span className="text-xs text-[var(--text-tertiary)]">
                    {u.created_at ? new Date(u.created_at).toLocaleString("ko-KR") : ""}
                  </span>
                </div>
                {u.toss_message ? (
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">{u.toss_message}</p>
                ) : null}
                {u.order_id ? (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void reconcile(u.order_id as string)}
                    className="mt-2 rounded-full border border-[var(--accent-strong)] px-3 py-1 text-xs font-semibold text-[var(--accent-strong)] disabled:opacity-50"
                  >
                    토스에 재조회해 바로잡기
                  </button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* ── 매출 ────────────────────────────────────────────────── */}
      <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-base font-semibold text-[var(--text-primary)]">매출</h2>
          <div className="flex gap-1">
            {[7, 30, 90, 365].map((d) => (
              <button
                key={d}
                type="button"
                onClick={() => setDays(d)}
                className={`rounded-full px-3 py-1 text-xs font-semibold ${
                  days === d
                    ? "bg-[var(--accent-strong)] text-white"
                    : "border border-[var(--line)] text-[var(--text-tertiary)]"
                }`}
              >
                {d}일
              </button>
            ))}
          </div>
        </div>
        {s ? (
          <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4" data-testid="revenue-summary">
            <Stat label="총 결제" value={krw(s.gross_krw)} />
            {/* ★환불을 뺀 순매출 — 이 한 줄이 이 화면의 존재 이유다. */}
            <Stat label="순매출" value={krw(s.net_krw)} strong />
            <Stat label="환불" value={`${krw(s.refunded_krw)} (${s.refund_rate_pct}%)`} />
            <Stat label="결제 건수" value={`${s.paid_count}건 · ${s.payer_count}명`} />
            <Stat label="평균 결제액" value={krw(s.avg_order_krw)} />
            <Stat label="미결제 주문" value={`${s.pending_count}건`} />
            <Stat label="취소된 주문" value={`${s.canceled_count}건`} />
            <Stat label="환불 건수" value={`${s.refund_count}건`} />
          </dl>
        ) : null}

        {rev && rev.daily.length > 0 ? (
          <div className="mt-5">
            <h3 className="text-sm font-semibold text-[var(--text-secondary)]">일별 추이</h3>
            <div className="mt-2 flex h-24 items-end gap-[2px] overflow-x-auto">
              {rev.daily.map((d) => (
                <div
                  key={d.day}
                  title={`${d.day} · 총 ${krw(d.gross_krw)} · 순 ${krw(d.net_krw)}`}
                  className="min-w-[4px] flex-1 rounded-t bg-[var(--accent-strong)]"
                  style={{ height: `${Math.max(2, (d.gross_krw / maxDaily) * 100)}%` }}
                />
              ))}
            </div>
          </div>
        ) : null}

        {rev && rev.by_provider.length > 0 ? (
          <div className="mt-5">
            <h3 className="text-sm font-semibold text-[var(--text-secondary)]">결제 경로별</h3>
            <ul className="mt-2 space-y-1 text-sm">
              {rev.by_provider.map((p) => (
                <li key={p.provider} className="flex justify-between">
                  <span
                    className={
                      // ★프로덕션에서 simulated 가 0 이 아니면 **무료 충전 경로가 열려 있다.**
                      p.provider === "simulated" ? "font-semibold text-[var(--status-error)]" : ""
                    }
                  >
                    {p.provider}
                    {p.provider === "simulated" ? " ★결제 없이 충전됨" : ""}
                  </span>
                  <span>
                    {p.count}건 · {krw(p.gross_krw)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {rev && rev.failure_reasons.length > 0 ? (
          <div className="mt-5">
            <h3 className="text-sm font-semibold text-[var(--text-secondary)]">실패 사유 상위</h3>
            <ul className="mt-2 space-y-1 text-sm">
              {rev.failure_reasons.map((f) => (
                <li key={f.code} className="flex flex-wrap justify-between gap-2">
                  <span className="font-mono text-xs">{f.code}</span>
                  <span className="text-xs text-[var(--text-tertiary)]">{f.sample}</span>
                  <span>{f.count}건</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}

        {rev && rev.recent_orders.length > 0 ? (
          <div className="mt-5" data-testid="recent-orders">
            <h3 className="text-sm font-semibold text-[var(--text-secondary)]">
              최근 결제 · 환불 집행
            </h3>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[620px] text-sm">
                <thead>
                  <tr className="border-b border-[var(--line)] text-left text-xs text-[var(--text-tertiary)]">
                    <th className="py-2 pr-3 font-medium">주문번호</th>
                    <th className="py-2 pr-3 font-medium">사용자</th>
                    <th className="py-2 pr-3 font-medium">결제</th>
                    <th className="py-2 pr-3 font-medium">환불</th>
                    <th className="py-2 pr-3 font-medium">상태</th>
                    <th className="py-2 font-medium">처리</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--line)]">
                  {rev.recent_orders.map((o) => (
                    <tr key={o.id}>
                      <td className="py-2 pr-3 font-mono text-xs">{o.order_no}</td>
                      <td className="py-2 pr-3 font-mono text-xs">{o.email_masked}</td>
                      <td className="py-2 pr-3">{krw(o.amount_krw)}</td>
                      <td className="py-2 pr-3">
                        {o.refunded_krw > 0 ? krw(o.refunded_krw) : "-"}
                      </td>
                      <td className="py-2 pr-3 text-xs">{o.status}</td>
                      <td className="py-2">
                        {/* ★토스 결제이고 환불 가능액이 남았을 때만 — 죽은 버튼을 만들지 않는다. */}
                        {o.status === "pending" ? (
                          // ★계좌이체 입금 확인 — 종전에도 API 는 있었으나 화면이 없었다.
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void manualConfirm(o)}
                            className="rounded-full border border-[var(--accent-strong)] px-3 py-1 text-xs font-semibold text-[var(--accent-strong)] disabled:opacity-50"
                          >
                            입금 확인
                          </button>
                        ) : o.provider === "toss" && o.refundable_krw > 0 ? (
                          <button
                            type="button"
                            disabled={busy}
                            onClick={() => void refund(o)}
                            className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-semibold text-[var(--text-secondary)] disabled:opacity-50"
                          >
                            환불
                          </button>
                        ) : (
                          <span className="text-xs text-[var(--text-tertiary)]">-</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {rev && rev.top_payers.length > 0 ? (
          <div className="mt-5">
            <h3 className="text-sm font-semibold text-[var(--text-secondary)]">상위 결제 사용자</h3>
            <ul className="mt-2 space-y-1 text-sm">
              {rev.top_payers.map((u) => (
                <li key={u.email_masked} className="flex justify-between">
                  <span className="font-mono text-xs">{u.email_masked}</span>
                  <span>
                    {u.count}건 · 순 {krw(u.net_krw)}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>
    </div>
  );
}

function Stat({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="rounded-lg bg-[var(--surface)] p-3">
      <dt className="text-xs text-[var(--text-tertiary)]">{label}</dt>
      <dd
        className={`mt-1 ${strong ? "text-lg font-bold text-[var(--accent-strong)]" : "text-sm font-semibold text-[var(--text-primary)]"}`}
      >
        {value}
      </dd>
    </div>
  );
}
