"use client";

/**
 * 구독 사용량 미터 + 추가결제(충전) 모달.
 *
 * /billing/status로 등급·사용량(실지급액 원)·한도·차단여부를 표시하고,
 * 한도 소진(차단) 또는 사용자가 충전을 누르면 추가결제(시뮬) 모달로 한도를 충전한다.
 * (할증·실원가·환율 등 내부 정책은 노출하지 않음 — 백엔드가 실지급액만 반환)
 */

import { useCallback, useEffect, useState } from "react";
import { apiClient, ApiClientError } from "@/lib/api-client";

type Status = {
  tier: string;
  tier_label: string;
  metered: boolean;
  fee_krw: number;
  included_budget_krw: number;
  budget_krw: number;
  billed_krw: number;
  remaining_krw: number;
  usage_pct: number;
  blocked: boolean;
};

const TOPUP_PRESETS = [10000, 30000, 50000, 100000];
const won = (n?: number) => (n ?? 0).toLocaleString("ko-KR") + "원";

export function BillingMeter({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [loading, setLoading] = useState(true);
  const [authed, setAuthed] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [topupAmount, setTopupAmount] = useState(30000);
  const [paying, setPaying] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const s = await apiClient.get<Status>("/billing/status", { useMock: false });
      setStatus(s);
      setAuthed(true);
    } catch (e) {
      if (e instanceof ApiClientError && (e.status === 401 || e.status === 403)) setAuthed(false);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleTopup = async () => {
    setPaying(true);
    try {
      const s = await apiClient.post<Status>("/billing/topup", {
        body: { amount_krw: topupAmount },
        useMock: false,
      });
      setStatus(s);
      setModalOpen(false);
    } catch {
      /* noop */
    } finally {
      setPaying(false);
    }
  };

  // 비로그인 또는 비구독(metered 아님)이면 미터 숨김
  if (!authed || loading || !status || !status.metered) return null;

  const pct = Math.min(100, status.usage_pct || 0);
  const barColor = status.blocked ? "#ef4444" : pct >= 80 ? "#f59e0b" : "var(--accent-strong)";

  return (
    <>
      <div className={`rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] ${compact ? "p-3" : "p-4"}`}>
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="text-xs font-bold text-[var(--text-secondary)]">
            <span className="text-[var(--accent-strong)]">●</span> {status.tier_label} 구독
          </span>
          <button
            onClick={() => setModalOpen(true)}
            className="rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 text-[10px] font-bold text-white hover:opacity-90"
          >
            추가결제
          </button>
        </div>
        <div className="h-2 w-full rounded-full bg-[var(--surface-muted)] overflow-hidden">
          <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: barColor }} />
        </div>
        <div className="mt-1.5 flex items-center justify-between text-[10px] text-[var(--text-hint)]">
          <span>사용 {won(status.billed_krw)} / {won(status.budget_krw)}</span>
          <span className={status.blocked ? "text-red-500 font-bold" : ""}>
            {status.blocked ? "한도 소진 · 추가결제 필요" : `잔여 ${won(status.remaining_krw)}`}
          </span>
        </div>
      </div>

      {modalOpen && (
        <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={() => !paying && setModalOpen(false)}>
          <div className="w-full max-w-sm rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-bold text-[var(--text-primary)]">추가결제 (LLM 충전)</h3>
            <p className="mt-1 text-xs text-[var(--text-secondary)]">
              {status.tier_label} 구독 · 현재 잔여 {won(status.remaining_krw)}. 충전 금액을 선택하세요.
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2">
              {TOPUP_PRESETS.map((amt) => (
                <button key={amt} onClick={() => setTopupAmount(amt)}
                  className={`rounded-xl border px-3 py-3 text-sm font-bold transition-all ${topupAmount === amt ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]" : "border-[var(--line)] text-[var(--text-secondary)]"}`}>
                  {won(amt)}
                </button>
              ))}
            </div>
            <div className="mt-5 flex items-center justify-between rounded-xl bg-[var(--surface-soft)] px-4 py-3">
              <span className="text-sm font-medium text-[var(--text-secondary)]">실 결제금액</span>
              <span className="text-xl font-black text-[var(--text-primary)]">{won(topupAmount)}</span>
            </div>
            <div className="mt-4 flex gap-2">
              <button onClick={() => setModalOpen(false)} disabled={paying}
                className="flex-1 rounded-xl border border-[var(--line-strong)] py-3 text-sm font-bold text-[var(--text-secondary)]">
                취소
              </button>
              <button onClick={handleTopup} disabled={paying}
                className="flex-[2] rounded-xl bg-gradient-to-r from-[var(--accent-strong)] to-[#085d73] py-3 text-sm font-black text-white disabled:opacity-50">
                {paying ? "결제 처리 중..." : `${won(topupAmount)} 결제하기`}
              </button>
            </div>
            <p className="mt-3 text-center text-[10px] text-[var(--text-hint)]">결제 시 한도가 즉시 충전되어 서비스를 계속 이용할 수 있습니다.</p>
          </div>
        </div>
      )}
    </>
  );
}
