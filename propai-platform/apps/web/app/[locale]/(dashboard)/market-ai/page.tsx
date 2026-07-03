import ConversationalMarketPanel from "@/components/market/ConversationalMarketPanel";
import { isValidLocale } from "@/i18n/config";

type MarketAiPageProps = {
  params: Promise<{ locale: string }>;
};

// 대화형 시장분석 AI — 자연어 질의로 /zoning/nearby-map(카카오 지오코딩 + 국토부 실거래) 를 조회해
// 평균·최저·최고·중앙값·월별 추이를 계산·차트화하는 자족형 채팅 패널을 마운트한다.
// (그동안 컴포넌트만 존재하고 라우트가 없어 orphan 이던 것을 전용 라우트로 배선 — 무목업·실API.)
export default async function MarketAiPage({ params }: MarketAiPageProps) {
  const { locale } = await params;

  if (!isValidLocale(locale)) {
    return null;
  }

  return (
    <div className="grid grid-cols-1 gap-6 min-w-0">
      <ConversationalMarketPanel />
    </div>
  );
}
