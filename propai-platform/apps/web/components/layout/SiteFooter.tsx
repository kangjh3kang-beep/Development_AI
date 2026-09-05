/**
 * 전자상거래법 표기 푸터 — **모든 화면 하단**에 사업자 식별정보를 노출한다.
 *
 * ★왜 전역인가 (2026-09-06 실측):
 *   네이버 로그인 검수가 **승인거부**(2026.05.13)됐고 반려 사유 중 하나가
 *   *「전자상거래 등에서의 소비자보호에 관한 법률에 따라 네이버 로그인을 적용할
 *   **모든 서비스 환경(PC/모바일 사이트 화면 하단 푸터)** 에 [대표자명, 사업자등록번호,
 *   통신판매업 신고번호]가 확인되도록」* 이었다.
 *
 *   실측 당시 상태:
 *     /ko (초기 화면)   사업자등록번호 0 · 대표자 0 · 통신판매업 0
 *     /ko/login         0 · 0 · 0
 *     /ko/legal/terms   1 · 1 · **0**
 *   ⇒ 값은 있었으나 **대시보드에만** 있었고, 검수자가 보는 **초기 화면·로그인 화면에는 없었다.**
 *   그리고 **통신판매업 신고번호는 코드 어디에도 없었다**(전수 0건).
 *
 * ★단일 출처로 둔다 — 대시보드 푸터가 따로 값을 들고 있으면 한쪽만 고쳐진다(§29 형제 분기).
 */

import Link from "next/link";

/** 사업자 식별정보 단일 출처. 여기만 고치면 전역이 따라온다. */
export const BUSINESS_INFO = {
  companyName: "사통팔땅",
  brand: "PropAI",
  representative: "강재희",
  businessNumber: "682-38-01463",
  /** ★전자상거래법 필수 표기. 2026-09-06 이전에는 이 값이 코드 어디에도 없었다. */
  mailOrderNumber: "제2026-경기광주-1245호",
  businessType: "도매 및 소매업",
  address: "경기도 광주시 회안대로 637-36",
  tel: "1666-0916",
  fax: "02-6305-0044",
} as const;

type SiteFooterProps = {
  locale: string;
  /** 대시보드처럼 이미 여백이 있는 곳에서 상단 마진을 줄이고 싶을 때 */
  compact?: boolean;
};

export function SiteFooter({ locale, compact = false }: SiteFooterProps) {
  const b = BUSINESS_INFO;
  return (
    <footer
      data-testid="site-footer"
      className={`${compact ? "mt-8" : "mt-16"} border-t border-[var(--line)] bg-[var(--surface-soft)] py-8 px-6`}
    >
      <div className="mx-auto max-w-6xl flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-1 text-xs text-[var(--text-tertiary)] leading-relaxed">
          <p className="text-[var(--text-secondary)]">
            {b.companyName} <span className="opacity-60">({b.brand})</span>
          </p>
          {/* ★전자상거래법 3종 — 검수가 보는 항목이다. 한 줄에 모아 놓치지 않게 한다. */}
          <p>
            대표자: {b.representative} | 사업자등록번호: {b.businessNumber}
          </p>
          <p>통신판매업 신고번호: {b.mailOrderNumber}</p>
          <p>
            업태: {b.businessType} | 소재지: {b.address}
          </p>
        </div>
        <div className="space-y-1 text-xs text-[var(--text-tertiary)]">
          <p>
            대표번호:{" "}
            <a
              href={`tel:${b.tel}`}
              className="text-[var(--text-secondary)] hover:text-[var(--accent-strong)]"
            >
              {b.tel}
            </a>
          </p>
          <p>팩스: {b.fax}</p>
          <p className="flex gap-3 pt-1">
            <Link
              href={`/${locale}/legal/terms`}
              className="text-[var(--text-secondary)] hover:text-[var(--accent-strong)]"
            >
              이용약관
            </Link>
            <Link
              href={`/${locale}/legal/privacy`}
              className="text-[var(--text-secondary)] hover:text-[var(--accent-strong)]"
            >
              개인정보처리방침
            </Link>
          </p>
          <p className="mt-2 text-[var(--text-hint)]">
            &copy; 2026 {b.companyName}. All rights reserved.
          </p>
        </div>
      </div>
    </footer>
  );
}
