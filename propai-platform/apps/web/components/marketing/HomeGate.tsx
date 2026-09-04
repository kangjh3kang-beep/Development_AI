"use client";

import type { ReactNode } from "react";
import dynamic from "next/dynamic";
import { useIsAuthenticated } from "@/hooks/useIsAuthenticated";

/**
 * 홈 콘텐츠 인증 분기 스위치(클라이언트).
 *  • 인증 판정은 `useIsAuthenticated`(단일 소스) 공유 — `DashboardChromeGate`
 *    (레이아웃 크롬 표시 여부 분기)와 동일한 훅을 사용해 판정 로직이 두 곳에
 *    중복되지 않는다.
 *  • 서버는 항상 랜딩을 렌더(SEO)하고, 클라이언트 마운트 시 토큰이 감지되면
 *    DashboardHome으로 즉시 스왑한다.
 *  • 한계: 인증 사용자에겐 랜딩 첫 페인트가 아주 짧게 보일 수 있다(플래시).
 *  • DashboardHome은 지도 등 무거운 클라이언트 의존을 포함하므로 ssr:false로
 *    지연 로드해 미인증 방문자에겐 로드되지 않게 한다.
 */
const DashboardHome = dynamic(
  () => import("@/components/dashboard/DashboardHome").then((m) => m.DashboardHome),
  { ssr: false },
);

export function HomeGate({ locale, landing }: { locale: string; landing: ReactNode }) {
  const authed = useIsAuthenticated();

  if (authed) {
    return <DashboardHome locale={locale} />;
  }
  return <>{landing}</>;
}
