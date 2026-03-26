"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, Input, Select } from "@propai/ui";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

type AuctionListingResponse = {
  listing_id: string;
  case_number: string;
  court_name: string;
  address: string;
  property_type: string;
  minimum_bid_krw: number;
  investment_score: number;
  discount_ratio: number;
  market_gap_ratio: number;
  recommended_max_bid_krw: number;
  expected_margin_krw: number;
  diligence_flags: string[];
};

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

type ChatbotSessionResponse = {
  session_id: string;
  domain: string;
  title: string;
  message_count: number;
  total_tokens: number;
  last_activity_at: string;
};

type ChatbotReplyResponse = {
  session: ChatbotSessionResponse;
  assistant_message: {
    content: string;
  };
};

type Labels = {
  connectionTitle: string;
  connectionDescription: string;
  connectionHint: string;
  opportunitiesTitle: string;
  opportunitiesEmpty: string;
  contractorsTitle: string;
  contractorsEmpty: string;
  analysisTitle: string;
  recommendationsTitle: string;
  advisoryTitle: string;
  advisoryHint: string;
  analyzeAction: string;
  recommendAction: string;
  sendAction: string;
  latestReplyTitle: string;
  scoreLabel: string;
  marginLabel: string;
  diligenceLabel: string;
  sessionsLabel: string;
  caseNumberLabel: string;
  courtLabel: string;
  addressLabel: string;
  appraisedLabel: string;
  minimumBidLabel: string;
  specialtiesLabel: string;
  regionLabel: string;
  promptLabel: string;
  tokenRequirement: string;
  authError: string;
  opportunitiesLoadErrorTitle: string;
  opportunitiesLoadErrorDetail: string;
  contractorsLoadErrorTitle: string;
  contractorsLoadErrorDetail: string;
  sessionsLoadErrorTitle: string;
  sessionsLoadErrorDetail: string;
  retryAction: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    connectionTitle: "실시간 경공매 워크스페이스",
    connectionDescription:
      "G95 백엔드와 직접 연결해 경공매 분석, 시공사 추천, 자문 챗봇 흐름을 한 화면에서 검증합니다.",
    connectionHint:
      "실 API 호출에는 `NEXT_PUBLIC_API_ACCESS_TOKEN` 또는 `localStorage.propai_access_token` 이 필요합니다.",
    opportunitiesTitle: "우선 검토 매물",
    opportunitiesEmpty: "저장된 경공매 분석 결과가 없습니다.",
    contractorsTitle: "활성 협력사 네트워크",
    contractorsEmpty: "등록된 활성 협력사가 없습니다.",
    analysisTitle: "경공매 분석 실행",
    recommendationsTitle: "시공사 추천",
    advisoryTitle: "자문 챗봇",
    advisoryHint:
      "입력한 프롬프트는 `chatbot -> auction -> contractors` 운영 흐름 검증용으로 저장됩니다.",
    analyzeAction: "분석 실행",
    recommendAction: "추천 조회",
    sendAction: "자문 요청",
    latestReplyTitle: "최신 자문 응답",
    scoreLabel: "투자 점수",
    marginLabel: "예상 마진",
    diligenceLabel: "실사 포인트",
    sessionsLabel: "세션",
    caseNumberLabel: "사건번호",
    courtLabel: "법원",
    addressLabel: "주소",
    appraisedLabel: "감정가(원)",
    minimumBidLabel: "최저입찰가(원)",
    specialtiesLabel: "필요 공종",
    regionLabel: "권역 힌트",
    promptLabel: "자문 프롬프트",
    tokenRequirement: "API 토큰을 연결하면 실시간 결과를 확인할 수 있습니다.",
    authError: "실시간 호출을 위해 API 인증이 필요합니다.",
    opportunitiesLoadErrorTitle: "경공매 목록 로드 실패",
    opportunitiesLoadErrorDetail:
      "저장된 경공매 분석 결과를 불러오지 못했습니다. 분석 실행 없이도 재시도할 수 있습니다.",
    contractorsLoadErrorTitle: "협력사 네트워크 로드 실패",
    contractorsLoadErrorDetail:
      "활성 협력사 목록을 불러오지 못했습니다. 추천 실행 전에도 재시도할 수 있습니다.",
    sessionsLoadErrorTitle: "챗봇 세션 로드 실패",
    sessionsLoadErrorDetail:
      "기존 자문 세션을 불러오지 못했습니다. 새 세션을 생성하기 전에 다시 시도할 수 있습니다.",
    retryAction: "다시 시도",
  },
  en: {
    connectionTitle: "Live auction workspace",
    connectionDescription:
      "Validate the G95 backend in one surface across auction scoring, contractor recommendations, and advisory chat.",
    connectionHint:
      "Live API calls require `NEXT_PUBLIC_API_ACCESS_TOKEN` or `localStorage.propai_access_token`.",
    opportunitiesTitle: "Priority opportunities",
    opportunitiesEmpty: "No analyzed auction listings have been stored yet.",
    contractorsTitle: "Active contractor network",
    contractorsEmpty: "No active contractors are registered yet.",
    analysisTitle: "Run auction analysis",
    recommendationsTitle: "Contractor recommendations",
    advisoryTitle: "Advisory chatbot",
    advisoryHint:
      "Prompts are stored through the operational `chatbot -> auction -> contractors` validation flow.",
    analyzeAction: "Analyze",
    recommendAction: "Recommend",
    sendAction: "Send prompt",
    latestReplyTitle: "Latest advisory response",
    scoreLabel: "Investment score",
    marginLabel: "Expected margin",
    diligenceLabel: "Diligence flags",
    sessionsLabel: "Sessions",
    caseNumberLabel: "Case number",
    courtLabel: "Court",
    addressLabel: "Address",
    appraisedLabel: "Appraised value (KRW)",
    minimumBidLabel: "Minimum bid (KRW)",
    specialtiesLabel: "Required specialties",
    regionLabel: "Region hint",
    promptLabel: "Advisory prompt",
    tokenRequirement: "Connect an API token to view live results.",
    authError: "API authentication is required for live workspace calls.",
    opportunitiesLoadErrorTitle: "Auction opportunities unavailable",
    opportunitiesLoadErrorDetail:
      "Stored auction analyses failed to load. You can retry before running a fresh analysis.",
    contractorsLoadErrorTitle: "Contractor network unavailable",
    contractorsLoadErrorDetail:
      "Active contractor records failed to load. You can retry before requesting recommendations.",
    sessionsLoadErrorTitle: "Chatbot sessions unavailable",
    sessionsLoadErrorDetail:
      "Stored advisory sessions failed to load. Retry before creating a new session.",
    retryAction: "Retry",
  },
  "zh-CN": {
    connectionTitle: "实时拍卖工作台",
    connectionDescription:
      "在一个页面中验证 G95 后端，包括拍卖评分、承包商推荐和顾问聊天。",
    connectionHint:
      "实时 API 调用需要 `NEXT_PUBLIC_API_ACCESS_TOKEN` 或 `localStorage.propai_access_token`。",
    opportunitiesTitle: "优先机会",
    opportunitiesEmpty: "尚未保存任何拍卖分析结果。",
    contractorsTitle: "活跃合作网络",
    contractorsEmpty: "尚未注册活跃承包商。",
    analysisTitle: "执行拍卖分析",
    recommendationsTitle: "承包商推荐",
    advisoryTitle: "顾问聊天",
    advisoryHint:
      "输入的提示会通过 `chatbot -> auction -> contractors` 运营链路保存。",
    analyzeAction: "开始分析",
    recommendAction: "获取推荐",
    sendAction: "发送请求",
    latestReplyTitle: "最新顾问回复",
    scoreLabel: "投资评分",
    marginLabel: "预计利润",
    diligenceLabel: "尽调重点",
    sessionsLabel: "会话",
    caseNumberLabel: "案件编号",
    courtLabel: "法院",
    addressLabel: "地址",
    appraisedLabel: "评估价（韩元）",
    minimumBidLabel: "最低投标价（韩元）",
    specialtiesLabel: "所需专业",
    regionLabel: "区域提示",
    promptLabel: "顾问提示",
    tokenRequirement: "连接 API token 后即可查看实时结果。",
    authError: "实时调用需要 API 身份认证。",
    opportunitiesLoadErrorTitle: "拍卖机会列表不可用",
    opportunitiesLoadErrorDetail:
      "无法加载已保存的拍卖分析结果，可在重新执行分析前先重试。",
    contractorsLoadErrorTitle: "合作网络不可用",
    contractorsLoadErrorDetail:
      "无法加载活跃承包商记录，可在请求推荐前先重试。",
    sessionsLoadErrorTitle: "聊天会话不可用",
    sessionsLoadErrorDetail:
      "无法加载已有顾问会话，可在新建会话前先重试。",
    retryAction: "重试",
  },
};

type AuctionWorkspaceClientProps = {
  locale: Locale;
};

function formatCurrency(locale: string, value: number) {
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatDate(locale: string, value: string) {
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function extractErrorMessage(error: unknown, authMessage: string) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return authMessage;
    }

    return `API request failed with status ${error.status}.`;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Request failed.";
}

export function AuctionWorkspaceClient({
  locale,
}: AuctionWorkspaceClientProps) {
  const labels = LABELS[locale];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [latestReply, setLatestReply] = useState("");
  const [formError, setFormError] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isRecommending, setIsRecommending] = useState(false);
  const [isSendingPrompt, setIsSendingPrompt] = useState(false);
  const [analysisResult, setAnalysisResult] =
    useState<AuctionListingResponse | null>(null);
  const [recommendations, setRecommendations] = useState<
    ContractorRecommendationItem[]
  >([]);

  const [analysisForm, setAnalysisForm] = useState({
    caseNumber: "2026타경1024",
    courtName: "Seoul Central District Court",
    address: "Seoul Mapo-gu World Cup-ro 120",
    appraisedValue: "1200000000",
    minimumBid: "910000000",
  });
  const [recommendationForm, setRecommendationForm] = useState({
    category: "general_contractor",
    specialties: "mep, interior",
    regionHint: "Mapo",
  });
  const [prompt, setPrompt] = useState(
    locale === "ko"
      ? "이 경공매 물건의 핵심 실사 포인트와 입찰 전략을 정리해줘."
      : locale === "zh-CN"
        ? "请整理这个拍卖项目的关键尽调点与竞标策略。"
        : "Summarize the key diligence points and bidding strategy for this auction asset.",
  );

  const opportunitiesQuery = useQuery({
    queryKey: ["auction", "opportunities"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<AuctionListingResponse[]>("/auction/opportunities?limit=5"),
  });

  const contractorsQuery = useQuery({
    queryKey: ["contractors", "active"],
    enabled: canUseLiveApi,
    queryFn: () =>
      apiClient.get<ContractorResponse[]>("/contractors/active?limit=6"),
  });

  const sessionsQuery = useQuery({
    queryKey: ["chatbot", "sessions"],
    enabled: canUseLiveApi,
    queryFn: () => apiClient.get<ChatbotSessionResponse[]>("/chatbot/sessions"),
  });
  const opportunitiesQueryError = opportunitiesQuery.error
    ? extractErrorMessage(opportunitiesQuery.error, labels.authError)
    : "";
  const contractorsQueryError = contractorsQuery.error
    ? extractErrorMessage(contractorsQuery.error, labels.authError)
    : "";
  const sessionsQueryError = sessionsQuery.error
    ? extractErrorMessage(sessionsQuery.error, labels.authError)
    : "";

  useEffect(() => {
    if (!activeSessionId && sessionsQuery.data?.length) {
      setActiveSessionId(sessionsQuery.data[0].session_id);
    }
  }, [activeSessionId, sessionsQuery.data]);

  async function handleAnalyze(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setIsAnalyzing(true);

    try {
      const result = await apiClient.post<AuctionListingResponse>(
        "/auction/analyze",
        {
          body: {
            auction_type: "court_auction",
            case_number: analysisForm.caseNumber,
            court_name: analysisForm.courtName,
            address: analysisForm.address,
            property_type: "mixed_use",
            appraised_value_krw: Number(analysisForm.appraisedValue),
            minimum_bid_krw: Number(analysisForm.minimumBid),
            bid_count: 1,
            occupancy_status: "unknown",
            senior_lien_exists: false,
            expected_repair_cost_krw: 35000000,
            nearby_market_price_krw: Number(analysisForm.appraisedValue) * 1.04,
          },
        },
      );
      setAnalysisResult(result);
      await opportunitiesQuery.refetch();
    } catch (error) {
      setFormError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsAnalyzing(false);
    }
  }

  async function handleRecommend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setIsRecommending(true);

    try {
      const result = await apiClient.post<ContractorRecommendationResponse>(
        "/contractors/recommend",
        {
          body: {
            category: recommendationForm.category,
            required_specialties: recommendationForm.specialties
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
            region_hint: recommendationForm.regionHint || null,
            max_results: 5,
          },
        },
      );
      setRecommendations(result.recommendations);
    } catch (error) {
      setFormError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsRecommending(false);
    }
  }

  async function handlePrompt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError("");
    setIsSendingPrompt(true);

    try {
      let sessionId = activeSessionId;

      if (!sessionId) {
        const session = await apiClient.post<ChatbotSessionResponse>(
          "/chatbot/sessions",
          {
            body: {
              domain: "investment",
              title:
                locale === "ko"
                  ? "경공매 자문"
                  : locale === "zh-CN"
                    ? "拍卖顾问"
                    : "Auction advisory",
              model_name: "claude-sonnet-4-5",
            },
          },
        );
        sessionId = session.session_id;
        setActiveSessionId(sessionId);
        await sessionsQuery.refetch();
      }

      const reply = await apiClient.post<ChatbotReplyResponse>(
        "/chatbot/messages",
        {
          body: {
            session_id: sessionId,
            content: prompt,
          },
        },
      );
      setLatestReply(reply.assistant_message.content);
    } catch (error) {
      setFormError(extractErrorMessage(error, labels.authError));
    } finally {
      setIsSendingPrompt(false);
    }
  }

  return (
    <section className="grid gap-6">
      <Card className="rounded-[2rem] bg-[var(--surface-strong)] shadow-[0_20px_60px_rgba(19,33,47,0.08)]">
        <CardContent className="p-8">
          <div className="flex flex-wrap items-center gap-3">
            <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
              {labels.connectionTitle}
            </span>
            <span className="rounded-full border border-[var(--line)] px-4 py-2 text-xs font-medium text-[rgba(19,33,47,0.7)]">
              {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
            </span>
          </div>
          <h3 className="mt-5 text-3xl font-bold text-[var(--foreground)]">
            {labels.connectionDescription}
          </h3>
          <p className="mt-4 max-w-3xl text-sm leading-8 text-[rgba(19,33,47,0.72)]">
            {labels.connectionHint}
          </p>
          {!canUseLiveApi ? (
            <div className="mt-6 rounded-[1.5rem] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-5 text-sm leading-7 text-[rgba(19,33,47,0.72)]">
              {labels.tokenRequirement}
            </div>
          ) : null}
          {formError ? (
            <div className="mt-6 rounded-[1.5rem] border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-5 text-sm leading-7 text-[var(--spot)]">
              {formError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                  {labels.opportunitiesTitle}
                </p>
                <h4 className="mt-2 text-xl font-semibold text-[var(--foreground)]">
                  {labels.analysisTitle}
                </h4>
              </div>
              <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                {opportunitiesQuery.data?.length ?? 0}
              </span>
            </div>
            <form className="mt-5 grid gap-3" onSubmit={handleAnalyze}>
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  value={analysisForm.caseNumber}
                  onChange={(event) =>
                    setAnalysisForm((current) => ({
                      ...current,
                      caseNumber: event.target.value,
                    }))
                  }
                  placeholder={labels.caseNumberLabel}
                />
                <Input
                  value={analysisForm.courtName}
                  onChange={(event) =>
                    setAnalysisForm((current) => ({
                      ...current,
                      courtName: event.target.value,
                    }))
                  }
                  placeholder={labels.courtLabel}
                />
              </div>
              <Input
                value={analysisForm.address}
                onChange={(event) =>
                  setAnalysisForm((current) => ({
                    ...current,
                    address: event.target.value,
                  }))
                }
                placeholder={labels.addressLabel}
              />
              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  value={analysisForm.appraisedValue}
                  onChange={(event) =>
                    setAnalysisForm((current) => ({
                      ...current,
                      appraisedValue: event.target.value,
                    }))
                  }
                  placeholder={labels.appraisedLabel}
                />
                <Input
                  value={analysisForm.minimumBid}
                  onChange={(event) =>
                    setAnalysisForm((current) => ({
                      ...current,
                      minimumBid: event.target.value,
                    }))
                  }
                  placeholder={labels.minimumBidLabel}
                />
              </div>
              <Button type="submit" disabled={!canUseLiveApi || isAnalyzing}>
                {isAnalyzing ? `${labels.analyzeAction}...` : labels.analyzeAction}
              </Button>
            </form>
            <div className="mt-6 grid gap-3">
              {opportunitiesQuery.isLoading ? (
                <SkeletonLoader count={2} itemClassName="h-28" />
              ) : null}
              {opportunitiesQuery.isError ? (
                <WorkspaceQueryErrorCard
                  title={labels.opportunitiesLoadErrorTitle}
                  description={labels.opportunitiesLoadErrorDetail}
                  message={opportunitiesQueryError}
                  actionLabel={labels.retryAction}
                  onRetry={() => {
                    void opportunitiesQuery.refetch();
                  }}
                />
              ) : null}
              {analysisResult ? (
                <Card className="rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none">
                  <CardContent className="p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--foreground)]">
                          {analysisResult.case_number}
                        </p>
                        <p className="mt-2 text-sm leading-6 text-[rgba(19,33,47,0.68)]">
                          {analysisResult.address}
                        </p>
                      </div>
                      <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                        {labels.scoreLabel}: {analysisResult.investment_score}
                      </span>
                    </div>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <p className="text-sm text-[rgba(19,33,47,0.72)]">
                        {labels.marginLabel}:{" "}
                        {formatCurrency(locale, analysisResult.expected_margin_krw)}
                      </p>
                      <p className="text-sm text-[rgba(19,33,47,0.72)]">
                        Max bid:{" "}
                        {formatCurrency(locale, analysisResult.recommended_max_bid_krw)}
                      </p>
                    </div>
                    <div className="mt-4">
                      <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                        {labels.diligenceLabel}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        {analysisResult.diligence_flags.map((flag) => (
                          <span
                            key={flag}
                            className="rounded-full border border-[var(--line)] px-3 py-1 text-xs font-medium text-[rgba(19,33,47,0.7)]"
                          >
                            {flag}
                          </span>
                        ))}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ) : null}
              {opportunitiesQuery.data?.map((listing) => (
                <Card
                  key={listing.listing_id}
                  className="rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none"
                >
                  <CardContent className="p-5">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-[var(--foreground)]">
                          {listing.case_number}
                        </p>
                        <p className="mt-2 text-sm leading-6 text-[rgba(19,33,47,0.68)]">
                          {listing.address}
                        </p>
                      </div>
                      <span className="rounded-full bg-[rgba(19,33,47,0.06)] px-3 py-1 text-xs font-medium text-[rgba(19,33,47,0.72)]">
                        {labels.scoreLabel}: {listing.investment_score}
                      </span>
                    </div>
                  </CardContent>
                </Card>
              ))}
              {!opportunitiesQuery.isLoading &&
              !opportunitiesQuery.isError &&
              !analysisResult &&
              !opportunitiesQuery.data?.length ? (
                <p className="text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                  {labels.opportunitiesEmpty}
                </p>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-6">
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                    {labels.contractorsTitle}
                  </p>
                  <h4 className="mt-2 text-xl font-semibold text-[var(--foreground)]">
                    {labels.recommendationsTitle}
                  </h4>
                </div>
                <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                  {contractorsQuery.data?.length ?? 0}
                </span>
              </div>
              <form className="mt-5 grid gap-3" onSubmit={handleRecommend}>
                <Select
                  value={recommendationForm.category}
                  onValueChange={(value) =>
                    setRecommendationForm((current) => ({
                      ...current,
                      category: value,
                    }))
                  }
                  options={[
                    { value: "general_contractor", label: "General contractor" },
                    { value: "sub_contractor", label: "Sub contractor" },
                    { value: "design_firm", label: "Design firm" },
                  ]}
                />
                <Input
                  value={recommendationForm.specialties}
                  onChange={(event) =>
                    setRecommendationForm((current) => ({
                      ...current,
                      specialties: event.target.value,
                    }))
                  }
                  placeholder={labels.specialtiesLabel}
                />
                <Input
                  value={recommendationForm.regionHint}
                  onChange={(event) =>
                    setRecommendationForm((current) => ({
                      ...current,
                      regionHint: event.target.value,
                    }))
                  }
                  placeholder={labels.regionLabel}
                />
                <Button type="submit" variant="secondary" disabled={!canUseLiveApi || isRecommending}>
                  {isRecommending
                    ? `${labels.recommendAction}...`
                    : labels.recommendAction}
                </Button>
              </form>
              <div className="mt-6 grid gap-3">
                {contractorsQuery.isError ? (
                  <WorkspaceQueryErrorCard
                    title={labels.contractorsLoadErrorTitle}
                    description={labels.contractorsLoadErrorDetail}
                    message={contractorsQueryError}
                    actionLabel={labels.retryAction}
                    onRetry={() => {
                      void contractorsQuery.refetch();
                    }}
                  />
                ) : null}
                {recommendations.map((item) => (
                  <Card
                    key={item.contractor_id}
                    className="rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none"
                  >
                    <CardContent className="p-5">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="text-sm font-semibold text-[var(--foreground)]">
                            {item.company_name}
                          </p>
                          <p className="mt-2 text-sm leading-6 text-[rgba(19,33,47,0.68)]">
                            {item.reasons.join(" · ")}
                          </p>
                        </div>
                        <span className="rounded-full bg-[rgba(14,116,144,0.1)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                          {item.match_score}
                        </span>
                      </div>
                    </CardContent>
                  </Card>
                ))}
                {contractorsQuery.isLoading ? (
                  <SkeletonLoader count={2} itemClassName="h-24" />
                ) : null}
                {!recommendations.length && contractorsQuery.data?.length ? (
                  contractorsQuery.data.map((contractor) => (
                    <Card
                      key={contractor.contractor_id}
                      className="rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none"
                    >
                      <CardContent className="p-5">
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold text-[var(--foreground)]">
                              {contractor.company_name}
                            </p>
                            <p className="mt-2 text-sm leading-6 text-[rgba(19,33,47,0.68)]">
                              {contractor.specialties.join(", ") || contractor.category}
                            </p>
                          </div>
                          <span className="rounded-full bg-[rgba(19,33,47,0.06)] px-3 py-1 text-xs font-medium text-[rgba(19,33,47,0.72)]">
                            {contractor.rating ?? "-"}
                          </span>
                        </div>
                      </CardContent>
                    </Card>
                  ))
                ) : null}
                {!contractorsQuery.isLoading &&
                !contractorsQuery.isError &&
                !recommendations.length &&
                !contractorsQuery.data?.length ? (
                  <p className="text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                    {labels.contractorsEmpty}
                  </p>
                ) : null}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-[rgba(19,33,47,0.5)]">
                    {labels.advisoryTitle}
                  </p>
                  <h4 className="mt-2 text-xl font-semibold text-[var(--foreground)]">
                    {labels.latestReplyTitle}
                  </h4>
                </div>
                <span className="rounded-full bg-[var(--surface-soft)] px-3 py-1 text-xs font-medium text-[var(--accent-strong)]">
                  {labels.sessionsLabel}: {sessionsQuery.data?.length ?? 0}
                </span>
              </div>
              <p className="mt-4 text-sm leading-7 text-[rgba(19,33,47,0.68)]">
                {labels.advisoryHint}
              </p>
              <form className="mt-5 grid gap-3" onSubmit={handlePrompt}>
                <textarea
                  value={prompt}
                  onChange={(event) => setPrompt(event.target.value)}
                  className="min-h-28 rounded-[1.5rem] border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-3 text-sm text-[var(--foreground)] outline-none"
                  placeholder={labels.promptLabel}
                />
                <Button type="submit" disabled={!canUseLiveApi || isSendingPrompt}>
                  {isSendingPrompt ? `${labels.sendAction}...` : labels.sendAction}
                </Button>
              </form>
              {latestReply ? (
                <Card className="mt-5 rounded-[1.5rem] bg-[var(--surface-soft)] shadow-none">
                  <CardContent className="p-5">
                    <p className="text-sm leading-7 text-[rgba(19,33,47,0.76)]">
                      {latestReply}
                    </p>
                  </CardContent>
                </Card>
              ) : null}
              {sessionsQuery.isError ? (
                <div className="mt-5">
                  <WorkspaceQueryErrorCard
                    title={labels.sessionsLoadErrorTitle}
                    description={labels.sessionsLoadErrorDetail}
                    message={sessionsQueryError}
                    actionLabel={labels.retryAction}
                    onRetry={() => {
                      void sessionsQuery.refetch();
                    }}
                  />
                </div>
              ) : null}
              {sessionsQuery.data?.length ? (
                <div className="mt-5 grid gap-2">
                  {sessionsQuery.data.slice(0, 3).map((session) => (
                    <button
                      key={session.session_id}
                      type="button"
                      onClick={() => setActiveSessionId(session.session_id)}
                      className={`rounded-[1.25rem] px-4 py-3 text-left text-sm transition ${
                        activeSessionId === session.session_id
                          ? "bg-[rgba(14,116,144,0.12)] text-[var(--accent-strong)]"
                          : "bg-[var(--surface-soft)] text-[rgba(19,33,47,0.72)]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-semibold">{session.title}</span>
                        <span className="text-xs">
                          {formatDate(locale, session.last_activity_at)}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
    </section>
  );
}
