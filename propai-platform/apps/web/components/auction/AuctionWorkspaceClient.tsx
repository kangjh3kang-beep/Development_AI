"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Button, Card, CardContent, Input } from "@propai/ui";
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
  analysisTitle: string;
  advisoryTitle: string;
  advisoryHint: string;
  analyzeAction: string;
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
  promptLabel: string;
  tokenRequirement: string;
  authError: string;
  opportunitiesLoadErrorTitle: string;
  opportunitiesLoadErrorDetail: string;
  sessionsLoadErrorTitle: string;
  sessionsLoadErrorDetail: string;
  retryAction: string;
};

const LABELS: Record<Locale, Labels> = {
  ko: {
    connectionTitle: "실시간 경공매 워크스페이스",
    connectionDescription:
      "G95 백엔드와 직접 연결해 경공매 분석 및 전략 자문 흐름을 통합 검증합니다.",
    connectionHint:
      "분석을 위해 로그인이 필요합니다.",
    opportunitiesTitle: "우선 검토 매물",
    opportunitiesEmpty: "저장된 경공매 분석 결과가 없습니다.",
    analysisTitle: "경공매 분석 실행",
    advisoryTitle: "전략 자문 챗봇",
    advisoryHint:
      "현재 매물의 실사 포인트와 입찰 전략을 AI와 연계하여 최적화합니다.",
    analyzeAction: "분석 실행",
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
    promptLabel: "자문 프롬프트 (예: 권익 관계 분석해줘)",
    tokenRequirement: "API 토큰을 연결하면 실시간 결과를 확인할 수 있습니다.",
    authError: "실시간 호출을 위해 API 인증이 필요합니다.",
    opportunitiesLoadErrorTitle: "경공매 목록 로드 실패",
    opportunitiesLoadErrorDetail:
      "저장된 경공매 분석 결과를 불러오지 못했습니다. 분석 실행 없이도 재시도할 수 있습니다.",
    sessionsLoadErrorTitle: "챗봇 세션 로드 실패",
    sessionsLoadErrorDetail:
      "기존 자문 세션을 불러오지 못했습니다. 새 세션을 생성하기 전에 다시 시도할 수 있습니다.",
    retryAction: "다시 시도",
  },
  en: {
    connectionTitle: "Live auction workspace",
    connectionDescription:
      "Validate the G95 backend in one surface across auction scoring and strategy advisory.",
    connectionHint:
      "Login required for analysis.",
    opportunitiesTitle: "Priority opportunities",
    opportunitiesEmpty: "No analyzed auction listings have been stored yet.",
    analysisTitle: "Run auction analysis",
    advisoryTitle: "Strategy advisory",
    advisoryHint:
      "Optimize diligence points and bidding strategies with AI insights.",
    analyzeAction: "Analyze",
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
    promptLabel: "Advisory prompt",
    tokenRequirement: "Connect an API token to view live results.",
    authError: "API authentication is required for live workspace calls.",
    opportunitiesLoadErrorTitle: "Auction opportunities unavailable",
    opportunitiesLoadErrorDetail:
      "Stored auction analyses failed to load. You can retry before running a fresh analysis.",
    sessionsLoadErrorTitle: "Chatbot sessions unavailable",
    sessionsLoadErrorDetail:
      "Stored advisory sessions failed to load. Retry before creating a new session.",
    retryAction: "Retry",
  },
  "zh-CN": {
    connectionTitle: "实时拍卖工作台",
    connectionDescription:
      "在一个页面中验证 G95 后端，包括拍卖评分与战略顾问咨询。",
    connectionHint:
      "分析需要登录。",
    opportunitiesTitle: "优先机会",
    opportunitiesEmpty: "尚未保存任何拍卖分析结果。",
    analysisTitle: "执行拍卖分析",
    advisoryTitle: "战略顾问",
    advisoryHint:
      "通过 AI 洞察优化尽调要点与竞标策略。",
    analyzeAction: "开始分析",
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
    promptLabel: "顾问提示",
    tokenRequirement: "连接 API token 后即可查看实时结果。",
    authError: "实时调用需要 API 身份认证。",
    opportunitiesLoadErrorTitle: "拍卖机会列表不可用",
    opportunitiesLoadErrorDetail:
      "无法加载已保存的拍卖分析结果，可在重新执行分析前先重试。",
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
  const labels = LABELS[locale] || LABELS["ko"];
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [latestReply, setLatestReply] = useState("");
  const [formError, setFormError] = useState("");
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSendingPrompt, setIsSendingPrompt] = useState(false);
  const [analysisResult, setAnalysisResult] =
    useState<AuctionListingResponse | null>(null);

  const [analysisForm, setAnalysisForm] = useState({
    caseNumber: "2026타경1024",
    courtName: "Seoul Central District Court",
    address: "Seoul Mapo-gu World Cup-ro 120",
    appraisedValue: "1200000000",
    minimumBid: "910000000",
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

  const sessionsQuery = useQuery({
    queryKey: ["chatbot", "sessions"],
    enabled: canUseLiveApi,
    queryFn: () => apiClient.get<ChatbotSessionResponse[]>("/chatbot/sessions"),
  });

  const opportunitiesQueryError = opportunitiesQuery.error
    ? extractErrorMessage(opportunitiesQuery.error, labels.authError)
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
    <section className="grid gap-8 font-sans">
      <Card className="rounded-[3.5rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-2xl)] overflow-hidden group">
        <CardContent className="p-10 lg:p-14 relative">
          <div className="absolute -right-20 -top-20 h-64 w-64 rounded-full bg-[var(--accent-strong)]/10 blur-[80px] transition-all duration-1000 group-hover:scale-150" />
          
          <div className="relative z-10 flex flex-wrap items-center gap-4">
            <span className="rounded-full border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-5 py-2 text-[10px] font-black uppercase tracking-[0.3em] text-[var(--accent-strong)] backdrop-blur-md">
              <span className="mr-2 inline-block h-2 w-2 rounded-full bg-[var(--accent-strong)] animate-pulse shadow-[var(--shadow-glow)]" />
              {labels.connectionTitle}
            </span>
            <span className="rounded-full border border-[var(--line-strong)] bg-[var(--surface-soft)] px-5 py-2 text-[10px] font-black uppercase tracking-[0.2em] text-[var(--text-hint)]">
              {runtimeConfig.mode === "live" ? "REAL-TIME ENGINE" : "HYBRID SIMULATION"}
            </span>
          </div>
          
          <h3 className="relative z-10 mt-8 text-4xl font-[1000] text-[var(--text-primary)] tracking-tighter leading-tight max-w-4xl">
            {labels.connectionDescription}
          </h3>
          <p className="relative z-10 mt-6 max-w-3xl text-lg font-medium leading-relaxed text-[var(--text-secondary)] italic underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
            {labels.connectionHint}
          </p>
          
          {!canUseLiveApi ? (
            <div className="relative z-10 mt-10 rounded-3xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-6 text-sm font-bold text-[var(--text-hint)] italic flex items-center gap-4">
              <div className="h-2 w-2 rounded-full bg-[var(--spot)]" />
              {labels.tokenRequirement}
            </div>
          ) : null}
          
          {formError ? (
            <div className="relative z-10 mt-8 rounded-3xl border border-[var(--spot)]/20 bg-[var(--spot)]/5 p-6 text-sm font-bold text-[var(--spot)] italic flex items-center gap-4">
              <div className="h-2 w-2 rounded-full bg-[var(--spot)] animate-ping" />
              {formError}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <div className="grid gap-8 xl:grid-cols-[1.2fr_0.8fr]">
        {/* --- Analysis Section --- */}
        <Card className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
          <CardContent className="p-10 lg:p-14">
            <div className="flex items-center justify-between gap-6 border-b border-[var(--line)] pb-8 mb-10">
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">
                  {labels.opportunitiesTitle}
                </p>
                <h4 className="mt-3 text-3xl font-[1000] text-[var(--text-primary)] tracking-tighter italic">
                  {labels.analysisTitle}<span className="text-[var(--accent-strong)]">.</span>
                </h4>
              </div>
              <div className="flex h-16 w-16 items-center justify-center rounded-[2rem] bg-[var(--accent-strong)]/10 text-[var(--accent-strong)] border border-[var(--accent-strong)]/20 shadow-[var(--shadow-glow)]">
                <span className="text-xl font-[1000]">{opportunitiesQuery.data?.length ?? 0}</span>
              </div>
            </div>

            <form className="grid gap-6" onSubmit={handleAnalyze}>
              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)] ml-4">{labels.caseNumberLabel}</label>
                  <Input
                    value={analysisForm.caseNumber}
                    className="h-16 rounded-[2rem] border-[var(--line-strong)] bg-[var(--surface-soft)] px-8 text-sm font-bold text-[var(--text-primary)] focus:ring-2 focus:ring-[var(--accent-strong)]/50 transition-all"
                    onChange={(event) =>
                      setAnalysisForm((current) => ({
                        ...current,
                        caseNumber: event.target.value,
                      }))
                    }
                  />
                </div>
                <div className="space-y-2">
                   <label className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)] ml-4">{labels.courtLabel}</label>
                  <Input
                    value={analysisForm.courtName}
                    className="h-16 rounded-[2rem] border-[var(--line-strong)] bg-[var(--surface-soft)] px-8 text-sm font-bold text-[var(--text-primary)]"
                    onChange={(event) =>
                      setAnalysisForm((current) => ({
                        ...current,
                        courtName: event.target.value,
                      }))
                    }
                  />
                </div>
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)] ml-4">{labels.addressLabel}</label>
                <Input
                  value={analysisForm.address}
                  className="h-16 rounded-[2rem] border-[var(--line-strong)] bg-[var(--surface-soft)] px-8 text-sm font-bold text-[var(--text-primary)]"
                  onChange={(event) =>
                    setAnalysisForm((current) => ({
                      ...current,
                      address: event.target.value,
                    }))
                  }
                />
              </div>
              <div className="grid gap-6 md:grid-cols-2">
                <div className="space-y-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)] ml-4">{labels.appraisedLabel}</label>
                  <Input
                    value={analysisForm.appraisedValue}
                    className="h-16 rounded-[2rem] border-[var(--line-strong)] bg-[var(--surface-soft)] px-8 text-sm font-bold text-[var(--text-primary)]"
                    onChange={(event) =>
                      setAnalysisForm((current) => ({
                        ...current,
                        appraisedValue: event.target.value,
                      }))
                    }
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)] ml-4">{labels.minimumBidLabel}</label>
                  <Input
                    value={analysisForm.minimumBid}
                    className="h-16 rounded-[2rem] border-[var(--line-strong)] bg-[var(--surface-soft)] px-8 text-sm font-bold text-[var(--text-primary)]"
                    onChange={(event) =>
                      setAnalysisForm((current) => ({
                        ...current,
                        minimumBid: event.target.value,
                      }))
                    }
                  />
                </div>
              </div>
              <Button 
                type="submit" 
                disabled={!canUseLiveApi || isAnalyzing}
                className="h-16 rounded-[2rem] bg-[var(--accent-strong)] text-white text-xs font-black uppercase tracking-[0.3em] shadow-[var(--shadow-glow)] hover:scale-[1.02] active:scale-95 transition-all mt-4"
              >
                {isAnalyzing ? `${labels.analyzeAction}...` : labels.analyzeAction}
              </Button>
            </form>

            <div className="mt-12 grid gap-6">
              {opportunitiesQuery.isLoading ? (
                <SkeletonLoader count={2} itemClassName="h-32 rounded-[2.5rem]" />
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
                <Card className="rounded-[3rem] border border-[var(--accent-strong)]/30 bg-[var(--surface-soft)] shadow-[var(--shadow-lg)] overflow-hidden motion-safe:animate-fade-in-up">
                  <CardContent className="p-8">
                    <div className="flex flex-wrap items-start justify-between gap-6 border-b border-[var(--line)] pb-6 mb-6">
                      <div className="space-y-1">
                        <p className="text-2xl font-[1000] text-[var(--text-primary)] tracking-tighter">
                          {analysisResult.case_number}
                        </p>
                        <p className="text-sm font-bold text-[var(--text-secondary)] italic">
                          {analysisResult.address}
                        </p>
                      </div>
                      <div className="rounded-2xl border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-6 py-3 text-sm font-black text-[var(--accent-strong)] shadow-[var(--shadow-glow)]">
                        {labels.scoreLabel}: {analysisResult.investment_score}
                      </div>
                    </div>
                    
                    <div className="grid gap-6 md:grid-cols-2">
                      <div className="space-y-1 p-5 rounded-2xl bg-[var(--surface-strong)] border border-[var(--line)] shadow-sm">
                        <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{labels.marginLabel}</p>
                        <p className="text-2xl font-[1000] text-[var(--text-primary)] tracking-tighter">
                          {formatCurrency(locale, analysisResult.expected_margin_krw)}
                        </p>
                      </div>
                      <div className="space-y-1 p-5 rounded-2xl bg-[var(--surface-strong)] border border-[var(--line)] shadow-sm">
                        <p className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">Max Recommended Bid</p>
                        <p className="text-2xl font-[1000] text-[var(--accent-strong)] tracking-tighter">
                          {formatCurrency(locale, analysisResult.recommended_max_bid_krw)}
                        </p>
                      </div>
                    </div>

                    <div className="mt-8 space-y-4">
                      <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">
                        {labels.diligenceLabel}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {analysisResult.diligence_flags.map((flag) => (
                          <span
                            key={flag}
                            className="rounded-full border border-[var(--line-strong)] bg-[var(--surface-strong)] px-5 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors shadow-sm"
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
                  className="rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-soft)]/50 shadow-none hover:bg-[var(--surface-soft)] transition-colors"
                >
                  <CardContent className="p-8">
                    <div className="flex flex-wrap items-center justify-between gap-6">
                      <div className="space-y-1">
                        <p className="text-xl font-[1000] text-[var(--text-primary)] tracking-tighter">
                          {listing.case_number}
                        </p>
                        <p className="text-xs font-bold text-[var(--text-secondary)] italic">
                          {listing.address}
                        </p>
                      </div>
                      <div className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-strong)] px-5 py-2 text-xs font-black text-[var(--text-secondary)]">
                        {labels.scoreLabel}: <span className="text-[var(--text-primary)]">{listing.investment_score}</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              ))}

              {!opportunitiesQuery.isLoading &&
              !opportunitiesQuery.isError &&
              !analysisResult &&
              !opportunitiesQuery.data?.length ? (
                <div className="py-20 text-center flex flex-col items-center gap-6">
                   <div className="h-16 w-16 rounded-3xl bg-[var(--surface-soft)] flex items-center justify-center text-[var(--text-hint)] grayscale opacity-50 border border-[var(--line)]">🏛️</div>
                   <p className="text-sm font-bold text-[var(--text-hint)] italic tracking-tight underline decoration-[var(--line)] decoration-2 underline-offset-8">
                    {labels.opportunitiesEmpty}
                  </p>
                </div>
              ) : null}
            </div>
          </CardContent>
        </Card>

        {/* --- Advisory Section --- */}
        <Card className="rounded-[4rem] border border-[var(--line-strong)] bg-[var(--surface-strong)] shadow-[var(--shadow-xl)] overflow-hidden">
          <CardContent className="p-10 lg:p-14 border-t-8 border-[var(--accent-strong)]">
            <div className="flex items-center justify-between gap-6 mb-8">
              <div>
                <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)]">
                  {labels.advisoryTitle}
                </p>
                <h4 className="mt-3 text-3xl font-[1000] text-[var(--text-primary)] tracking-tighter italic">
                  {labels.latestReplyTitle}<span className="text-[var(--accent-strong)]">.</span>
                </h4>
              </div>
              <div className="rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)] px-5 py-2 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
                {labels.sessionsLabel}: {sessionsQuery.data?.length ?? 0}
              </div>
            </div>

            <p className="text-sm font-medium leading-relaxed text-[var(--text-secondary)] mb-10 italic underline decoration-[var(--line-strong)] decoration-2 underline-offset-8">
              {labels.advisoryHint}
            </p>

            <form className="grid gap-6" onSubmit={handlePrompt}>
              <textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                className="min-h-[160px] w-full rounded-[2.5rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] px-8 py-6 text-sm font-bold text-[var(--text-primary)] outline-none focus:ring-4 focus:ring-[var(--accent-strong)]/30 transition-all resize-none placeholder:text-[var(--text-hint)]/50"
                placeholder={labels.promptLabel}
              />
              <button
                type="submit"
                disabled={!canUseLiveApi || isSendingPrompt}
                className="h-16 w-full rounded-[2rem] bg-[var(--accent-strong)] text-white text-xs font-black uppercase tracking-[0.3em] shadow-[var(--shadow-glow)] hover:scale-[1.02] active:scale-95 transition-all flex items-center justify-center gap-3 disabled:opacity-50"
              >
                {isSendingPrompt ? `${labels.sendAction}...` : (
                   <>
                     {labels.sendAction}
                     <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>
                   </>
                )}
              </button>
            </form>

            <AnimatePresence mode="wait">
              {latestReply && (
                <motion.div
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="mt-10"
                >
                  <div className="rounded-[3rem] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-8 shadow-[var(--shadow-lg)]">
                    <p className="text-sm font-medium leading-loose text-[var(--text-primary)] italic relative whitespace-pre-wrap">
                      <span className="text-4xl text-[var(--accent-strong)]/20 absolute -top-4 -left-4">"</span>
                      {latestReply}
                      <span className="text-4xl text-[var(--accent-strong)]/20 absolute -bottom-8 right-0">"</span>
                    </p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {sessionsQuery.isError ? (
              <div className="mt-8">
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
              <div className="mt-12 space-y-4">
                 <p className="text-[10px] font-black uppercase tracking-[0.4em] text-[var(--text-hint)] ml-4">Recent Strategy Sessions</p>
                <div className="grid gap-3">
                  {sessionsQuery.data.slice(0, 4).map((session) => (
                    <button
                      key={session.session_id}
                      type="button"
                      onClick={() => setActiveSessionId(session.session_id)}
                      className={`group rounded-[2rem] border p-6 text-left transition-all duration-300 ${
                        activeSessionId === session.session_id
                          ? "border-[var(--accent-strong)]/50 bg-[var(--accent-soft)] shadow-[var(--shadow-md)]"
                          : "border-[var(--line-strong)] bg-[var(--surface-soft)]/50 hover:bg-[var(--surface-soft)]"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-4">
                        <span className={`font-black tracking-tight transition-colors ${activeSessionId === session.session_id ? 'text-[var(--accent-strong)]' : 'text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]'}`}>
                          {session.title}
                        </span>
                        <span className="text-[10px] font-bold text-[var(--text-hint)] italic tabular-nums">
                          {formatDate(locale, session.last_activity_at)}
                        </span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
