"use client";

import { useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import type { Locale } from "@/i18n/config";

type ContractorResponse = {
  contractor_id: string;
  company_name: string;
  category: string;
  specialties: string[];
  address: string | null;
  rating: number | null;
};

type ContractorRecommendationItem = {
  contractor_id: string;
  company_name: string;
  category: string;
  specialties: string[];
  rating: number | null;
  match_score: number;
  reasons: string[];
};

type ContractorRecommendationResponse = {
  category: string;
  recommendations: ContractorRecommendationItem[];
};

type Labels = {
  contractorsTitle: string;
  recommendationsTitle: string;
  contractorsEmpty: string;
  specialtiesLabel: string;
  regionLabel: string;
  recommendAction: string;
  contractorsLoadErrorTitle: string;
  contractorsLoadErrorDetail: string;
  retryAction: string;
  authError: string;
  scoreLabel: string;
};

const LABELS: Record<string, Labels> = {
  ko: {
    contractorsTitle: "지능형 시공사 매칭",
    recommendationsTitle: "최적 협력사 추천",
    contractorsEmpty: "등록된 협력사가 없습니다.",
    specialtiesLabel: "필요 공종 (예: 전기, 인테리어)",
    regionLabel: "권역 (예: 강남구)",
    recommendAction: "추천 시공사 조회",
    contractorsLoadErrorTitle: "협력사 데이터 로드 실패",
    contractorsLoadErrorDetail: "네트워크 상태를 확인하거나 다시 시도해주세요.",
    retryAction: "다시 시도",
    authError: "실시간 데이터를 확인하려면 인증이 필요합니다.",
    scoreLabel: "매칭 점수",
  },
  en: {
    contractorsTitle: "Contractor Intelligence",
    recommendationsTitle: "Optimum Partner Recommendations",
    contractorsEmpty: "No contractors available.",
    specialtiesLabel: "Required Specialties (e.g., MEP, Interior)",
    regionLabel: "Region (e.g., Mapo)",
    recommendAction: "Match Contractors",
    contractorsLoadErrorTitle: "Failed to load contractors",
    contractorsLoadErrorDetail: "Check your connection and try again.",
    retryAction: "Retry",
    authError: "Authentication required for live matching.",
    scoreLabel: "Match Score",
  },
};

function extractErrorMessage(error: unknown, authMessage: string) {
  `;
  }
  return error instanceof Error ? error.message : "Request failed";
}

export function ContractorIntelligence({ locale }: { locale: Locale }) {
  const labels = LABELS[locale] || LABELS["en"];
  const runtimeConfig = ({ mode: "local" as string, hasAccessToken: false });
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [isRecommending, setIsRecommending] = useState(false);
  const [recommendations, setRecommendations] = useState<ContractorRecommendationItem[]>([]);
  const [formError, setFormError] = useState("");

  const [form, setForm] = useState({
    category: "general_contractor",
    specialties: "mep, interior",
    regionHint: "",
  });

  const contractorsQuery = useQuery({
    queryKey: ["contractors", "active"],
    enabled: canUseLiveApi,
    queryFn: () => (async () => ({} as ContractorResponse[]))(),
  });

  const contractorsQueryError = contractorsQuery.error
    ? extractErrorMessage(contractorsQuery.error, labels.authError)
    : "";

  async function handleRecommend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setIsRecommending(true);

    try {
      const result = await (async () => ({} as ContractorRecommendationResponse))()
              .map((s) => s.trim())
              .filter(Boolean),
            region_hint: form.regionHint || null,
            max_results: 5,
          },
        }
      );
      setRecommendations(result.recommendations);
    } catch (error) {
      setFormError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsRecommending(false);
    }
  }

  return (
    <Card className="overflow-hidden rounded-[var(--radius-2xl)] border-none bg-[var(--surface-strong)] shadow-[var(--shadow-xl)]">
      <CardContent className="p-8">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              {labels.contractorsTitle}
            </p>
            <h4 className="mt-2 text-2xl font-bold text-[var(--text-primary)]">
              {labels.recommendationsTitle}
            </h4>
          </div>
          <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold text-[var(--accent-strong)]">
            {contractorsQuery.data?.length ?? 0} Active Partners
          </span>
        </div>

        <form className="mt-8 grid gap-4 lg:grid-cols-4" onSubmit={handleRecommend}>
          <Select
            value={form.category}
            onValueChange={(val) => setForm((prev) => ({ ...prev, category: val }))}
            options={[
              { value: "general_contractor", label: "General Contractor" },
              { value: "sub_contractor", label: "Sub Contractor" },
              { value: "design_firm", label: "Design Firm" },
            ]}
          />
          <Input
            value={form.specialties}
            onChange={(e) => setForm((prev) => ({ ...prev, specialties: e.target.value }))}
            placeholder={labels.specialtiesLabel}
          />
          <Input
            value={form.regionHint}
            onChange={(e) => setForm((prev) => ({ ...prev, regionHint: e.target.value }))}
            placeholder={labels.regionLabel}
          />
          <Button type="submit" disabled={!canUseLiveApi || isRecommending}>
            {isRecommending ? "Matching..." : labels.recommendAction}
          </Button>
        </form>

        {formError && (
          <div className="mt-4 rounded-xl bg-red-50 p-4 text-sm text-red-600">
            {formError}
          </div>
        )}

        <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {recommendations.length > 0 ? (
            recommendations.map((item) => (
              <Card key={item.contractor_id} className="bg-[var(--surface-soft)] border-none transition-transform hover:scale-[1.02]">
                <CardContent className="p-6">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h5 className="font-bold text-[var(--text-primary)]">{item.company_name}</h5>
                      <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">
                        {item.reasons.join(" · ")}
                      </p>
                    </div>
                    <div className="flex flex-col items-end">
                      <span className="text-xl font-bold text-[var(--accent-strong)]">{item.match_score}</span>
                      <span className="text-[10px] text-[var(--text-tertiary)] uppercase">{labels.scoreLabel}</span>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))
          ) : contractorsQuery.isLoading ? (
            <SkeletonLoader count={3} itemClassName="h-32" />
          ) : contractorsQuery.isError ? (
            <div className="col-span-full">
              <WorkspaceQueryErrorCard
                title={labels.contractorsLoadErrorTitle}
                description={labels.contractorsLoadErrorDetail}
                message={contractorsQueryError}
                actionLabel={labels.retryAction}
                onRetry={() => void contractorsQuery.refetch()}
              />
            </div>
          ) : contractorsQuery.data?.length === 0 ? (
            <p className="col-span-full py-8 text-center text-sm text-[var(--text-tertiary)]">
              {labels.contractorsEmpty}
            </p>
          ) : (
            contractorsQuery.data?.map((c) => (
              <Card key={c.contractor_id} className="bg-[var(--surface-soft)] border-none">
                <CardContent className="p-6 text-center">
                  <h5 className="font-bold text-[var(--text-primary)]">{c.company_name}</h5>
                  <p className="mt-1 text-xs text-[var(--text-secondary)]">{c.category}</p>
                </CardContent>
              </Card>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  );
}
