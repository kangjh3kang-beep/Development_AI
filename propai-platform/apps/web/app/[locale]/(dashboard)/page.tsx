import type { Metadata } from "next";
import { HomeGate } from "@/components/marketing/HomeGate";
import { LandingPage } from "@/components/marketing/LandingPage";
import { isValidLocale } from "@/i18n/config";

type DashboardPageProps = {
  params: Promise<{
    locale: string;
  }>;
};

// 랜딩(미인증 첫 화면) 기준 SEO 메타데이터.
export async function generateMetadata(): Promise<Metadata> {
  const title = "사통팔땅 — 부동산개발 전주기 AI 플랫폼";
  const description =
    "주소 하나로 사전검토부터 수지분석·설계·인허가까지. 부동산개발 전주기를 AI로 자동화하는 플랫폼, 사통팔땅.";
  return {
    title,
    description,
    openGraph: {
      title,
      description,
      type: "website",
      siteName: "사통팔땅",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
    },
  };
}

export default async function DashboardPage({ params }: DashboardPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  // 미인증=랜딩(Part A, SSR)·인증=DashboardHome(클라이언트 스왑). URL(/{locale})은 불변.
  return <HomeGate locale={locale} landing={<LandingPage locale={locale} />} />;
}
