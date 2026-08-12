import type { Metadata } from "next";
import { QuickSalesSurveyClient } from "@/components/market/QuickSalesSurveyClient";

export const metadata: Metadata = {
  title: "간편 분양성 조사 — 사통팔땅",
  description:
    "지번 하나로 주변시세·계획 고시 시설·입지·분양사례를 한 화면에 모아 봅니다. 수요 축(경쟁률·미분양)은 데이터원 미연동으로 포함하지 않습니다.",
};

export default function QuickSurveyPage() {
  return <QuickSalesSurveyClient />;
}
