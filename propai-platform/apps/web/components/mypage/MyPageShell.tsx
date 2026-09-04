"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import type { Locale } from "@/i18n/config";

/**
 * 마이페이지 공통 셸 — 제목 + 섹션 탭(라우트 링크).
 * 탭 순서·경로는 나비 SSOT(route-registry의 my 섹션)와 일치시킨다. 탭 라벨은 좁은 탭 UI에 맞게
 * 축약형을 쓰므로 registry 라벨(예: '내 계정 요약')과 문구가 다를 수 있다(경로가 정합의 기준).
 */
const TABS: Array<{ href: string; label: string; exact?: boolean }> = [
  { href: "/mypage", label: "요약", exact: true },
  { href: "/mypage/coins", label: "코인·결제" },
  { href: "/mypage/usage", label: "사용내역" },
  { href: "/mypage/profile", label: "프로필" },
  { href: "/mypage/privacy", label: "개인정보·약관" },
  { href: "/account", label: "계정 보안" },
];

export function MyPageShell({
  locale,
  title,
  description,
  children,
}: {
  locale: Locale;
  title: string;
  description: string;
  children: ReactNode;
}) {
  const pathname = usePathname() ?? "";

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-8">
      <p className="text-[11px] font-bold uppercase tracking-[0.18em] text-[var(--accent-strong)]">
        마이페이지
      </p>
      <h1 className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{title}</h1>
      <p className="mt-1.5 text-sm leading-6 text-[var(--text-secondary)]">{description}</p>

      <nav aria-label="마이페이지 섹션" className="mt-5 overflow-x-auto">
        <ul className="flex min-w-max gap-1 border-b border-[var(--line)]">
          {TABS.map((tab) => {
            const href = `/${locale}${tab.href}`;
            const active = tab.exact ? pathname === href : pathname.startsWith(href);
            return (
              <li key={tab.href}>
                <Link
                  href={href}
                  aria-current={active ? "page" : undefined}
                  className={`inline-block rounded-t-[var(--radius-md)] px-3.5 py-2 text-sm font-semibold transition ${
                    active
                      ? "border-b-2 border-[var(--accent-strong)] text-[var(--accent-strong)]"
                      : "text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  {tab.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      <div className="mt-6">{children}</div>
    </main>
  );
}

/** 금액 표시(원) — 통상어·천단위 구분. */
export function formatKrw(value: number | null | undefined): string {
  return `${Math.round(Number(value ?? 0)).toLocaleString("ko-KR")}원`;
}

/** 원장/주문 구분 라벨(통상어) — API entry_type/status를 사용자 언어로. */
export const ENTRY_TYPE_LABELS: Record<string, string> = {
  topup: "코인 충전",
  order_paid: "코인 충전(주문)",
  service_fee: "서비스 사용료",
  monthly_grant: "월기본 코인 지급",
  tier_change: "등급 변경",
  admin_adjust: "관리자 조정",
  llm_usage: "AI 분석 사용",
};

export const ORDER_STATUS_LABELS: Record<string, string> = {
  pending: "결제 대기",
  paid: "충전 완료",
  canceled: "취소됨",
  failed: "실패",
};
