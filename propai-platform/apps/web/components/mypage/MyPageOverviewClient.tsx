"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";
import { ENTRY_TYPE_LABELS, MyPageShell, formatKrw } from "./MyPageShell";

type Balance = {
  tier: string;
  tier_label: string;
  unlimited?: boolean;
  monthly_base_krw: number;
  monthly_base_remaining: number;
  topup_krw: number;
  topup_remaining: number;
  used_this_cycle_krw: number;
  cycle_start: string | null;
};

type LedgerItem = {
  created_at: string | null;
  entry_type: string;
  amount_krw: number;
  description: string | null;
};

type Profile = { name: string; email: string; email_verified?: boolean };

export function MyPageOverviewClient({ locale }: { locale: Locale }) {
  const [balance, setBalance] = useState<Balance | null>(null);
  const [recent, setRecent] = useState<LedgerItem[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  // ★오류를 '0원/빈 상태'로 위장하지 않도록 각 카드의 로드 실패를 명시 표기(성장루프 MEDIUM 수렴).
  const [balanceError, setBalanceError] = useState(false);
  const [recentError, setRecentError] = useState(false);
  const [profileError, setProfileError] = useState(false);

  useEffect(() => {
    let active = true;
    const run = async () => {
      // 실패해도 페이지 골격은 유지(각 카드가 개별 폴백) — Promise.allSettled.
      const [b, l, p] = await Promise.allSettled([
        apiClient.get<Balance>("/billing/balance", { useMock: false }),
        apiClient.get<{ items: LedgerItem[] }>("/billing/ledger?limit=5", { useMock: false }),
        apiClient.get<Profile>("/auth/me", { useMock: false }),
      ]);
      if (!active) return;
      if (b.status === "fulfilled") setBalance(b.value);
      else setBalanceError(true);
      if (l.status === "fulfilled") setRecent(l.value.items ?? []);
      else setRecentError(true);
      if (p.status === "fulfilled") setProfile(p.value);
      else setProfileError(true);
      setLoading(false);
    };
    void run();
    return () => {
      active = false;
    };
  }, []);

  const totalRemaining =
    (balance?.monthly_base_remaining ?? 0) + (balance?.topup_remaining ?? 0);
  // 잔액 부족 경고 휴리스틱: 이번 사이클 사용액의 20% 미만 또는 5천원 미만(과금 등급 한정).
  const lowBalance =
    !!balance &&
    !balance.unlimited &&
    totalRemaining < Math.max(5_000, (balance.used_this_cycle_krw ?? 0) * 0.2);

  return (
    <MyPageShell
      locale={locale}
      title="내 계정 요약"
      description="잔여 코인과 최근 이용 내역을 한눈에 확인합니다."
    >
      {lowBalance ? (
        <div
          role="status"
          className="mb-5 rounded-[var(--radius-xl)] border border-[rgba(217,119,6,0.35)] bg-[rgba(217,119,6,0.12)] px-5 py-3.5 text-sm text-[rgb(146,64,14)]"
        >
          잔여 코인이 최근 사용량 대비 부족합니다. 분석이 중단되지 않도록{" "}
          <Link href={`/${locale}/mypage/coins`} className="font-semibold underline underline-offset-2">
            코인을 충전
          </Link>
          해 주세요.
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-3">
        {/* 잔여 코인 — 월기본/충전 분리 표시(산출근거 동반) */}
        <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5 md:col-span-2">
          <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">잔여 코인</h2>
          {balanceError ? (
            <p role="status" className="mt-2 text-sm font-semibold text-[rgb(146,64,14)]">
              잔액을 불러오지 못했습니다. 잠시 후 새로고침해 주세요.
            </p>
          ) : balance?.unlimited ? (
            <p className="mt-2 text-2xl font-bold text-[var(--text-primary)]">무제한</p>
          ) : (
            <p className="mt-2 text-2xl font-bold text-[var(--text-primary)]">
              {loading ? "…" : formatKrw(totalRemaining)}
            </p>
          )}
          {/* 오류·로딩 중엔 '0원' 분해·산출근거를 감춰 잘못된 수치를 사실처럼 보이지 않게 한다
              (balance 로드 완료 후에만 표시). unlimited(비과금) 등급은 '무제한' 헤드라인과
              모순되는 유한 분해를 감춘다(성장루프 LOW 수렴). */}
          {!balanceError && balance && !balance.unlimited ? (
            <>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-[var(--radius-lg)] bg-[var(--surface)] px-3.5 py-2.5">
                  <dt className="text-[var(--text-tertiary)]">월기본 잔여</dt>
                  <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                    {formatKrw(balance?.monthly_base_remaining)}
                    <span className="ml-1 text-xs font-normal text-[var(--text-tertiary)]">
                      / {formatKrw(balance?.monthly_base_krw)}
                    </span>
                  </dd>
                </div>
                <div className="rounded-[var(--radius-lg)] bg-[var(--surface)] px-3.5 py-2.5">
                  <dt className="text-[var(--text-tertiary)]">충전 잔여</dt>
                  <dd className="mt-0.5 font-semibold text-[var(--text-primary)]">
                    {formatKrw(balance?.topup_remaining)}
                  </dd>
                </div>
              </dl>
              <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
                산출근거: 잔여 = 월기본 잔여 + 충전 잔여. 사용 시 월기본이 먼저 차감되고, 부족분이
                충전 잔액에서 차감됩니다. 이번 사이클 사용액 {formatKrw(balance?.used_this_cycle_krw)}.
              </p>
            </>
          ) : null}
          <div className="mt-4 flex gap-2">
            <Link
              href={`/${locale}/mypage/coins`}
              className="rounded-full bg-[var(--accent-strong)] px-4 py-2 text-sm font-semibold text-white transition hover:opacity-90"
            >
              코인 충전
            </Link>
            <Link
              href={`/${locale}/mypage/usage`}
              className="rounded-full border border-[var(--line)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] transition hover:bg-[var(--surface)]"
            >
              사용내역 보기
            </Link>
          </div>
        </section>

        {/* 프로필 요약 */}
        <section className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
          <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">내 프로필</h2>
          {profileError ? (
            <p role="status" className="mt-2 text-sm font-semibold text-[rgb(146,64,14)]">
              프로필을 불러오지 못했습니다.
            </p>
          ) : (
            <>
              <p className="mt-2 text-lg font-bold text-[var(--text-primary)]">
                {profile?.name ?? (loading ? "…" : "회원")}
              </p>
              <p className="mt-0.5 break-all text-sm text-[var(--text-secondary)]">{profile?.email}</p>
              {/* 프로필 로드 완료 후에만 인증/등급을 단정 표기(허위 '미인증' 방지). */}
              {profile ? (
                <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                  {profile.email_verified ? "이메일 인증 완료" : "이메일 미인증"}
                  {balance?.tier_label ? ` · 등급 ${balance.tier_label}` : ""}
                </p>
              ) : null}
            </>
          )}
          <Link
            href={`/${locale}/mypage/profile`}
            className="mt-4 inline-block rounded-full border border-[var(--line)] px-4 py-2 text-sm font-semibold text-[var(--text-primary)] transition hover:bg-[var(--surface)]"
          >
            프로필 관리
          </Link>
        </section>
      </div>

      {/* 최근 코인내역 5건 */}
      <section className="mt-4 rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-5">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-[var(--text-tertiary)]">최근 코인내역</h2>
          <Link
            href={`/${locale}/mypage/coins`}
            className="text-xs font-semibold text-[var(--accent-strong)] underline-offset-2 hover:underline"
          >
            전체 보기
          </Link>
        </div>
        {recentError ? (
          <p role="status" className="mt-3 text-sm text-[rgb(146,64,14)]">
            최근 내역을 불러오지 못했습니다.
          </p>
        ) : recent.length === 0 ? (
          <p className="mt-3 text-sm text-[var(--text-tertiary)]">
            {loading ? "불러오는 중…" : "아직 코인 이용 내역이 없습니다."}
          </p>
        ) : (
          <ul className="mt-3 divide-y divide-[var(--line)]">
            {recent.map((item, i) => (
              <li key={`${item.created_at}-${i}`} className="flex items-center justify-between py-2.5 text-sm">
                <div>
                  <p className="font-medium text-[var(--text-primary)]">
                    {ENTRY_TYPE_LABELS[item.entry_type] ?? item.entry_type}
                  </p>
                  <p className="text-xs text-[var(--text-tertiary)]">
                    {item.description ?? ""}{" "}
                    {item.created_at ? new Date(item.created_at).toLocaleString("ko-KR") : ""}
                  </p>
                </div>
                <span
                  className={`font-semibold ${
                    item.amount_krw >= 0 ? "text-emerald-600" : "text-[var(--text-primary)]"
                  }`}
                >
                  {item.amount_krw >= 0 ? "+" : ""}
                  {formatKrw(item.amount_krw)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </MyPageShell>
  );
}
