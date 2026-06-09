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
  service_fee_krw?: number;
  free_analysis_remaining?: number;
  free_analysis_quota?: number;
};

type Balance = {
  tier: string;
  tier_label: string;
  monthly_base_krw: number;
  monthly_base_remaining: number;
  topup_krw: number;
  topup_remaining: number;
  used_this_cycle_krw: number;
  markup_pct: number;
  cycle_start: string | null;
};

type Plan = { tier: string; label: string; fee_krw: number; included_budget_krw: number };

function PlansModal({ onClose }: { onClose: () => void }) {
  const [plans, setPlans] = useState<Plan[]>([]);
  useEffect(() => {
    apiClient.get<{ plans: Plan[] }>("/billing/plans", { useMock: false })
      .then((r) => setPlans(r.plans || [])).catch(() => { /* noop */ });
  }, []);
  const won2 = (n: number) => n.toLocaleString("ko-KR") + "원";
  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center bg-black/50 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-md rounded-2xl border border-[var(--line-strong)] bg-[var(--surface)] p-6 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-bold text-[var(--text-primary)]">구독 요금제</h3>
        <p className="mt-1 text-xs text-[var(--text-secondary)]">구독하면 토지분석·프로젝트 생성을 제한 없이 이용할 수 있습니다.</p>
        <div className="mt-4 space-y-2">
          {plans.map((p) => (
            <div key={p.tier} className="flex items-center justify-between rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3">
              <div>
                <p className="text-sm font-bold text-[var(--text-primary)]">{p.label}</p>
                <p className="text-[10px] text-[var(--text-hint)]">LLM 포함 {won2(p.included_budget_krw)}</p>
              </div>
              <span className="text-base font-black text-[var(--accent-strong)]">{won2(p.fee_krw)}<span className="text-[10px] text-[var(--text-hint)]">/월</span></span>
            </div>
          ))}
        </div>
        <p className="mt-4 text-center text-[11px] text-[var(--text-hint)]">구독 신청은 관리자에게 문의해 주세요. (등급 부여 후 즉시 적용)</p>
        <button onClick={onClose} className="mt-3 w-full rounded-xl border border-[var(--line-strong)] py-2.5 text-sm font-bold text-[var(--text-secondary)]">닫기</button>
      </div>
    </div>
  );
}

const TOPUP_PRESETS = [10000, 30000, 50000, 100000];
const won = (n?: number) => (n ?? 0).toLocaleString("ko-KR") + "원";

export function BillingMeter({ compact = false }: { compact?: boolean }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [loading, setLoading] = useState(true);
  const [authed, setAuthed] = useState(true);
  const [modalOpen, setModalOpen] = useState(false);
  const [topupAmount, setTopupAmount] = useState(30000);
  const [paying, setPaying] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [s, b] = await Promise.all([
        apiClient.get<Status>("/billing/status", { useMock: false }),
        apiClient.get<Balance>("/billing/balance", { useMock: false }).catch(() => null),
      ]);
      setStatus(s);
      setBalance(b);
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
      // 충전 후 잔액(월기본/충전) 갱신
      apiClient.get<Balance>("/billing/balance", { useMock: false }).then(setBalance).catch(() => { /* noop */ });
      setModalOpen(false);
    } catch {
      /* noop */
    } finally {
      setPaying(false);
    }
  };

  // 비로그인 또는 비구독(metered 아님)이면 미터 숨김
  if (!authed || loading || !status) return null;

  // 일반회원(무료 등급): 무료 토지분석 잔여 + 소진 시 구독 유도
  const isFreeTier = !status.metered && (status.free_analysis_quota ?? 0) > 0;
  if (!status.metered && !isFreeTier) return null;

  if (isFreeTier) {
    const quota = status.free_analysis_quota ?? 0;
    const remaining = status.free_analysis_remaining ?? 0;
    const used = Math.max(0, quota - remaining);
    const soaked = remaining <= 0;
    return (
      <>
        <div className={`rounded-xl border ${soaked ? "border-amber-500/40" : "border-[var(--line-strong)]"} bg-[var(--surface-soft)] ${compact ? "p-3" : "p-4"}`}>
          <div className="flex items-center justify-between gap-2 mb-2">
            <span className="text-xs font-bold text-[var(--text-secondary)]">● 일반회원 (무료)</span>
            <button onClick={() => setModalOpen(true)}
              className="rounded-lg bg-[var(--accent-strong)] px-2.5 py-1 text-[10px] font-bold text-white hover:opacity-90">
              {soaked ? "구독하기" : "요금제 보기"}
            </button>
          </div>
          <div className="h-2 w-full rounded-full bg-[var(--surface-muted)] overflow-hidden">
            <div className="h-full rounded-full transition-all" style={{ width: `${quota ? (used / quota) * 100 : 100}%`, backgroundColor: soaked ? "#f59e0b" : "var(--accent-strong)" }} />
          </div>
          <div className="mt-1.5 text-[10px] text-[var(--text-hint)]">
            {soaked
              ? <span className="text-amber-500 font-bold">무료 토지분석을 모두 사용했습니다 · 구독 시 계속 이용</span>
              : <span>무료 토지분석 잔여 <b className="text-[var(--text-secondary)]">{remaining}</b> / {quota}회</span>}
          </div>
        </div>
        {modalOpen && <PlansModal onClose={() => setModalOpen(false)} />}
      </>
    );
  }

  const pct = Math.min(100, status.usage_pct || 0);
  const barColor = status.blocked ? "#ef4444" : pct >= 80 ? "#f59e0b" : "var(--accent-strong)";
  // 코인 잔액(월기본 + 충전) — /billing/balance 실데이터. 소진 임박(85%+) 경고.
  const totalRemaining = balance
    ? (balance.monthly_base_remaining || 0) + (balance.topup_remaining || 0)
    : status.remaining_krw;
  const lowBalance = !status.blocked && pct >= 85;

  return (
    <>
      <div className={`rounded-xl border ${status.blocked || lowBalance ? "border-amber-500/40" : "border-[var(--line-strong)]"} bg-[var(--surface-soft)] ${compact ? "p-3" : "p-4"}`}>
        <div className="flex items-center justify-between gap-2 mb-2">
          <span className="flex items-center gap-1.5 text-xs font-bold text-[var(--text-secondary)]">
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
          <span>코인 {won(status.billed_krw)} 사용 / {won(status.budget_krw)}</span>
          <span className={status.blocked ? "text-red-500 font-bold" : lowBalance ? "text-amber-500 font-bold" : ""}>
            {status.blocked ? "코인 소진 · 추가결제" : `잔여 ${won(totalRemaining)}`}
          </span>
        </div>
        {balance && (
          <div className="mt-1 flex items-center justify-between text-[10px] text-[var(--text-hint)]">
            <span>월기본 잔여 {won(balance.monthly_base_remaining)}</span>
            <span>충전 잔여 {won(balance.topup_remaining)}</span>
          </div>
        )}
        {lowBalance && (
          <p className="mt-1 text-[10px] font-bold text-amber-500">코인 소진 임박 · 충전을 권장합니다</p>
        )}
        {(status.service_fee_krw ?? 0) > 0 && (
          <div className="mt-1 flex items-center justify-between text-[10px] text-[var(--text-hint)] border-t border-[var(--line)] pt-1">
            <span>서비스 사용료(분석·생성)</span>
            <span className="font-bold text-[var(--text-secondary)]">{won(status.service_fee_krw)}</span>
          </div>
        )}
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
