import G2BBidDashboard from "@/components/g2b/G2BBidDashboard";
import { G2bEstimateSimPanel } from "@/components/g2b/G2bEstimateSimPanel";

export const metadata = {
  title: "공공입찰 (나라장터) | PropAI",
  description: "조달청 나라장터 입찰/낙찰 정보 조회 및 AI 입찰 분석",
};

export default function G2BPage() {
  return (
    <div className="space-y-8">
      <G2BBidDashboard />
      <G2bEstimateSimPanel />
    </div>
  );
}
