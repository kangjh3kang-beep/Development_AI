"use client";

import { useMemo, useState, type FormEvent } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { ApiClientError, apiClient } from "@/lib/api-client";
import type { Locale } from "@/i18n/config";

// 백엔드 계약(prefix /api/v1/auction, 메인 인증 apiClient) — 무목업.
// 일부 필드는 온비드 비공개/미제공으로 null 가능 → 정직 표기("비공개"/"-").

type AuctionItem = {
  rank?: number | null;
  cltrMngNo?: string | null;
  address?: string | null;
  usage?: string | null;
  appraisal_price?: number | null;
  min_bid_price?: number | null;
  discount_rate?: number | null;
  status?: string | null;
  thumbnail?: string | null;
  bid_start?: string | null;
  bid_end?: string | null;
  est_win?: number | null;
  // 조건검색(bid-results) 추가 필드
  fail_count?: number | null;
  win_rate?: number | null;
  win_price?: number | null;
  valid_bidder_count?: number | null;
  land_area?: number | null;
  bld_area?: number | null;
};

type RankingResponse = {
  items: AuctionItem[];
  page?: number;
  page_size?: number;
  total?: number | null;
  data_source?: string | null;
};

type BidResultsResponse = {
  items: AuctionItem[];
  page?: number;
  total?: number | null;
  data_source?: string | null;
  note?: string | null;
};

type MyAuctionProject = {
  project_id?: string | null;
  project_name?: string | null;
  address?: string | null;
  items: AuctionItem[];
};

type MyAuctionResponse = {
  projects: MyAuctionProject[];
  combined: AuctionItem[];
  data_source?: string | null;
  note?: string | null;
};

type SavedFilter = {
  filter_id: string;
  name: string;
  params: Record<string, string>;
  created_at?: string | null;
};

type BidFilters = {
  sido: string;
  prpt: string;
  usage: string;
  fail_min: string;
  fail_max: string;
  apsl_min: string;
  apsl_max: string;
  lowbid_min: string;
  lowbid_max: string;
  land_min: string;
  land_max: string;
  pbct_stat: "" | "fail" | "win";
};

const EMPTY_FILTERS: BidFilters = {
  sido: "",
  prpt: "",
  usage: "",
  fail_min: "",
  fail_max: "",
  apsl_min: "",
  apsl_max: "",
  lowbid_min: "",
  lowbid_max: "",
  land_min: "",
  land_max: "",
  pbct_stat: "",
};

type TabId = "my" | "search" | "ranking";
type RankingBy = "views" | "interest" | "min_bid" | "discount_rate";

const TABS: { id: TabId; label: string; hint: string }[] = [
  { id: "my", label: "내 경공매", hint: "관리 토지·프로젝트와 연동된 물건" },
  { id: "search", label: "조건검색", hint: "지역·종류·유찰·금액 조건 검색" },
  { id: "ranking", label: "전국 순위", hint: "조회수·관심·최저가·할인율 정렬" },
];

const RANKING_OPTIONS: { id: RankingBy; label: string }[] = [
  { id: "views", label: "조회수" },
  { id: "interest", label: "관심" },
  { id: "min_bid", label: "최저가" },
  { id: "discount_rate", label: "할인율" },
];

const SIDO_OPTIONS = [
  "",
  "서울특별시",
  "부산광역시",
  "대구광역시",
  "인천광역시",
  "광주광역시",
  "대전광역시",
  "울산광역시",
  "세종특별자치시",
  "경기도",
  "강원특별자치도",
  "충청북도",
  "충청남도",
  "전북특별자치도",
  "전라남도",
  "경상북도",
  "경상남도",
  "제주특별자치도",
];

const USAGE_OPTIONS = ["", "아파트", "오피스텔", "상가", "토지", "주택", "공장", "기타"];

function formatCurrency(locale: Locale, value: number | null | undefined) {
  if (value == null) return "-";
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "KRW",
    maximumFractionDigits: 0,
  }).format(value);
}

function formatPercent(value: number | null | undefined) {
  if (value == null) return "-";
  return `${value.toFixed(1)}%`;
}

function formatText(value: string | null | undefined) {
  if (value == null || value === "") return "-";
  return value;
}

function formatBidPrice(value: number | null | undefined, locale: Locale) {
  // 백엔드가 "비공개"를 null로 표기 → 정직하게 "비공개" 노출.
  if (value == null) return "비공개";
  return formatCurrency(locale, value);
}

function extractErrorMessage(error: unknown) {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return "실시간 조회를 위해 로그인(메인 인증)이 필요합니다.";
    }
    return `요청이 실패했습니다 (HTTP ${error.status}).`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "온비드 데이터를 불러오지 못했습니다. API 키 연결을 확인하세요.";
}

function buildSearchParams(params: Record<string, string | number | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "" || value === null) continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

type AuctionWorkspaceProps = {
  locale: Locale;
};

export function AuctionWorkspace({ locale }: AuctionWorkspaceProps) {
  const queryClient = useQueryClient();
  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi = runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [activeTab, setActiveTab] = useState<TabId>("my");
  const [rankingBy, setRankingBy] = useState<RankingBy>("views");

  // 조건검색: 입력 폼과 실제 적용 필터를 분리(검색 버튼 클릭 시 적용).
  const [filterForm, setFilterForm] = useState<BidFilters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<BidFilters | null>(null);
  const [saveName, setSaveName] = useState("");
  const [saveError, setSaveError] = useState("");

  const [selected, setSelected] = useState<AuctionItem | null>(null);

  // --- 탭 A: 내 경공매 ---
  const myQuery = useQuery({
    queryKey: ["auction", "my"],
    enabled: canUseLiveApi && activeTab === "my",
    queryFn: () =>
      apiClient.get<MyAuctionResponse>("/auction/my?group_by=project"),
  });

  // --- 탭 B: 조건검색 ---
  const bidResultsQuery = useQuery({
    queryKey: ["auction", "bid-results", appliedFilters],
    enabled: canUseLiveApi && activeTab === "search" && appliedFilters !== null,
    queryFn: () => {
      const f = appliedFilters as BidFilters;
      const qs = buildSearchParams({
        sido: f.sido,
        prpt: f.prpt,
        usage: f.usage,
        fail_min: f.fail_min,
        fail_max: f.fail_max,
        apsl_min: f.apsl_min,
        apsl_max: f.apsl_max,
        lowbid_min: f.lowbid_min,
        lowbid_max: f.lowbid_max,
        land_min: f.land_min,
        land_max: f.land_max,
        pbct_stat: f.pbct_stat,
      });
      return apiClient.get<BidResultsResponse>(`/auction/bid-results${qs}`);
    },
  });

  // 저장 조건 CRUD
  const filtersQuery = useQuery({
    queryKey: ["auction", "filters"],
    enabled: canUseLiveApi && activeTab === "search",
    queryFn: () => apiClient.get<SavedFilter[]>("/auction/filters"),
  });

  const saveFilterMutation = useMutation({
    mutationFn: (payload: { name: string; params: Record<string, string> }) =>
      apiClient.post<SavedFilter>("/auction/filters", { body: payload }),
    onSuccess: () => {
      setSaveName("");
      setSaveError("");
      void queryClient.invalidateQueries({ queryKey: ["auction", "filters"] });
    },
    onError: (error) => {
      setSaveError(extractErrorMessage(error));
    },
  });

  const deleteFilterMutation = useMutation({
    mutationFn: (filterId: string) =>
      apiClient.delete<void>(`/auction/filters/${filterId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["auction", "filters"] });
    },
  });

  // --- 탭 C: 전국 순위 ---
  const rankingQuery = useQuery({
    queryKey: ["auction", "ranking", rankingBy],
    enabled: canUseLiveApi && activeTab === "ranking",
    queryFn: () =>
      apiClient.get<RankingResponse>(
        `/auction/ranking${buildSearchParams({ by: rankingBy, page: 1, page_size: 30 })}`,
      ),
  });

  const filtersDirty = useMemo(
    () => Object.values(filterForm).some((v) => v !== ""),
    [filterForm],
  );

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAppliedFilters({ ...filterForm });
  }

  function handleSaveFilter() {
    if (!saveName.trim()) {
      setSaveError("저장할 조건 이름을 입력하세요.");
      return;
    }
    const params: Record<string, string> = {};
    for (const [key, value] of Object.entries(filterForm)) {
      if (value) params[key] = value;
    }
    saveFilterMutation.mutate({ name: saveName.trim(), params });
  }

  function applySavedFilter(filter: SavedFilter) {
    const next: BidFilters = { ...EMPTY_FILTERS };
    for (const [key, value] of Object.entries(filter.params)) {
      if (key in next) {
        (next as Record<string, string>)[key] = String(value);
      }
    }
    setFilterForm(next);
    setAppliedFilters(next);
  }

  return (
    <section className="space-y-6 p-6 font-sans">
      <motion.div
        initial={{ y: -16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="space-y-1"
      >
        <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
          경매·공매
        </h1>
        <p className="text-sm text-[var(--text-secondary)]">
          온비드(getInqRnkClg·getCltrBidRsltList2) 실데이터 기반. 감정가·낙찰가능가는
          추정치이며 가정이 포함됩니다. 온비드 비공개 항목은 정직하게 &quot;비공개&quot;로
          표기합니다.
        </p>
      </motion.div>

      {!canUseLiveApi ? (
        <div className="rounded-2xl border border-dashed border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-5 text-sm font-semibold text-[var(--text-hint)]">
          실시간 온비드 조회를 위해 로그인이 필요합니다. (메인 인증)
        </div>
      ) : null}

      {/* Tabs */}
      <div
        role="tablist"
        aria-label="경매·공매 탭"
        className="flex flex-wrap gap-2 border-b border-[var(--line)] pb-px"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`rounded-t-2xl px-5 py-3 text-sm font-bold transition-colors ${
              activeTab === tab.id
                ? "bg-[var(--accent-strong)] text-white shadow-[var(--shadow-glow)]"
                : "bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <p className="-mt-3 text-xs text-[var(--text-hint)]">
        {TABS.find((t) => t.id === activeTab)?.hint}
      </p>

      {/* --- 탭 A: 내 경공매 --- */}
      {activeTab === "my" ? (
        <div className="space-y-5">
          {myQuery.isLoading ? (
            <SkeletonLoader count={2} itemClassName="h-40 rounded-3xl" />
          ) : null}
          {myQuery.isError ? (
            <WorkspaceQueryErrorCard
              title="내 경공매 로드 실패"
              description="관리 토지·프로젝트와 온비드 물건 매칭 결과를 불러오지 못했습니다."
              message={extractErrorMessage(myQuery.error)}
              actionLabel="다시 시도"
              onRetry={() => void myQuery.refetch()}
            />
          ) : null}

          {myQuery.data ? (
            <>
              {myQuery.data.note ? (
                <p className="rounded-xl bg-[var(--surface-soft)] px-4 py-3 text-xs font-medium text-[var(--text-hint)]">
                  {myQuery.data.note}
                </p>
              ) : null}

              {myQuery.data.combined.length ? (
                <div className="rounded-3xl border border-[var(--accent-strong)]/30 bg-[var(--surface-strong)] p-6">
                  <p className="mb-4 text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-hint)]">
                    통합 보드 · 전체 {myQuery.data.combined.length}건
                  </p>
                  <AuctionTable
                    items={myQuery.data.combined}
                    locale={locale}
                    variant="results"
                    onSelect={setSelected}
                  />
                </div>
              ) : null}

              {myQuery.data.projects.length ? (
                <div className="space-y-4">
                  {myQuery.data.projects.map((project, idx) => (
                    <div
                      key={project.project_id ?? `project-${idx}`}
                      className="rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-soft)]/40 p-6"
                    >
                      <div className="mb-4">
                        <p className="text-lg font-black tracking-tight text-[var(--text-primary)]">
                          {formatText(project.project_name)}
                        </p>
                        <p className="text-xs text-[var(--text-secondary)]">
                          {formatText(project.address)}
                        </p>
                      </div>
                      <AuctionTable
                        items={project.items}
                        locale={locale}
                        variant="results"
                        onSelect={setSelected}
                      />
                    </div>
                  ))}
                </div>
              ) : !myQuery.data.combined.length ? (
                <EmptyState message="관리 토지 중 경공매 진행 물건이 없습니다." />
              ) : null}
            </>
          ) : null}
        </div>
      ) : null}

      {/* --- 탭 B: 조건검색 --- */}
      {activeTab === "search" ? (
        <div className="space-y-6">
          <form
            onSubmit={handleSearch}
            className="rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-soft)]/40 p-6"
          >
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <FieldSelect
                label="지역(시도)"
                value={filterForm.sido}
                options={SIDO_OPTIONS}
                onChange={(v) => setFilterForm((f) => ({ ...f, sido: v }))}
              />
              <FieldSelect
                label="종류(용도)"
                value={filterForm.usage}
                options={USAGE_OPTIONS}
                onChange={(v) => setFilterForm((f) => ({ ...f, usage: v }))}
              />
              <FieldInput
                label="물건명 키워드(prpt)"
                value={filterForm.prpt}
                onChange={(v) => setFilterForm((f) => ({ ...f, prpt: v }))}
              />
              <FieldRange
                label="유찰횟수"
                minValue={filterForm.fail_min}
                maxValue={filterForm.fail_max}
                onMin={(v) => setFilterForm((f) => ({ ...f, fail_min: v }))}
                onMax={(v) => setFilterForm((f) => ({ ...f, fail_max: v }))}
              />
              <FieldRange
                label="감정가(원)"
                minValue={filterForm.apsl_min}
                maxValue={filterForm.apsl_max}
                onMin={(v) => setFilterForm((f) => ({ ...f, apsl_min: v }))}
                onMax={(v) => setFilterForm((f) => ({ ...f, apsl_max: v }))}
              />
              <FieldRange
                label="최저입찰가(원)"
                minValue={filterForm.lowbid_min}
                maxValue={filterForm.lowbid_max}
                onMin={(v) => setFilterForm((f) => ({ ...f, lowbid_min: v }))}
                onMax={(v) => setFilterForm((f) => ({ ...f, lowbid_max: v }))}
              />
              <FieldRange
                label="면적(㎡)"
                minValue={filterForm.land_min}
                maxValue={filterForm.land_max}
                onMin={(v) => setFilterForm((f) => ({ ...f, land_min: v }))}
                onMax={(v) => setFilterForm((f) => ({ ...f, land_max: v }))}
              />
              <FieldSelect
                label="입찰결과"
                value={filterForm.pbct_stat}
                options={["", "fail", "win"]}
                optionLabels={{ "": "전체", fail: "유찰", win: "낙찰" }}
                onChange={(v) =>
                  setFilterForm((f) => ({
                    ...f,
                    pbct_stat: v as BidFilters["pbct_stat"],
                  }))
                }
              />
            </div>

            <div className="mt-5 flex flex-wrap items-center gap-3">
              <button
                type="submit"
                disabled={!canUseLiveApi}
                className="rounded-2xl bg-[var(--accent-strong)] px-6 py-3 text-sm font-black text-white shadow-[var(--shadow-glow)] transition-transform hover:scale-[1.02] active:scale-95 disabled:opacity-50"
              >
                조건 검색
              </button>
              <button
                type="button"
                onClick={() => {
                  setFilterForm(EMPTY_FILTERS);
                  setAppliedFilters(null);
                }}
                className="rounded-2xl border border-[var(--line-strong)] px-5 py-3 text-sm font-bold text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
              >
                초기화
              </button>

              <div className="ml-auto flex items-center gap-2">
                <input
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder="조건 저장 이름"
                  disabled={!filtersDirty}
                  className="w-40 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50 disabled:opacity-50"
                />
                <button
                  type="button"
                  onClick={handleSaveFilter}
                  disabled={
                    !canUseLiveApi || !filtersDirty || saveFilterMutation.isPending
                  }
                  className="rounded-xl border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-4 py-2 text-sm font-bold text-[var(--accent-strong)] transition-colors hover:bg-[var(--accent-soft)]/70 disabled:opacity-50"
                >
                  {saveFilterMutation.isPending ? "저장 중..." : "조건 저장"}
                </button>
              </div>
            </div>
            {saveError ? (
              <p className="mt-2 text-xs font-bold text-[var(--spot)]">{saveError}</p>
            ) : null}
          </form>

          {/* 저장 조건 목록 */}
          {filtersQuery.data?.length ? (
            <div className="flex flex-wrap gap-2">
              {filtersQuery.data.map((filter) => (
                <span
                  key={filter.filter_id}
                  className="inline-flex items-center gap-2 rounded-full border border-[var(--line-strong)] bg-[var(--surface-soft)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)]"
                >
                  <button
                    type="button"
                    onClick={() => applySavedFilter(filter)}
                    className="hover:text-[var(--accent-strong)]"
                  >
                    {filter.name}
                  </button>
                  <button
                    type="button"
                    aria-label={`${filter.name} 삭제`}
                    onClick={() => deleteFilterMutation.mutate(filter.filter_id)}
                    className="text-[var(--text-hint)] hover:text-[var(--spot)]"
                  >
                    ✕
                  </button>
                </span>
              ))}
            </div>
          ) : null}

          {/* 결과 */}
          {appliedFilters === null ? (
            <EmptyState message="조건을 설정하고 검색을 실행하세요." />
          ) : bidResultsQuery.isLoading ? (
            <SkeletonLoader count={3} itemClassName="h-20 rounded-2xl" />
          ) : bidResultsQuery.isError ? (
            <WorkspaceQueryErrorCard
              title="조건검색 로드 실패"
              description="온비드 조건검색 결과를 불러오지 못했습니다."
              message={extractErrorMessage(bidResultsQuery.error)}
              actionLabel="다시 시도"
              onRetry={() => void bidResultsQuery.refetch()}
            />
          ) : bidResultsQuery.data ? (
            <div className="space-y-3">
              {bidResultsQuery.data.note ? (
                <p className="rounded-xl bg-[var(--surface-soft)] px-4 py-3 text-xs font-medium text-[var(--text-hint)]">
                  {bidResultsQuery.data.note}
                </p>
              ) : null}
              {bidResultsQuery.data.items.length ? (
                <AuctionTable
                  items={bidResultsQuery.data.items}
                  locale={locale}
                  variant="results"
                  onSelect={setSelected}
                />
              ) : (
                <EmptyState message="조건에 맞는 온비드 물건이 없습니다." />
              )}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* --- 탭 C: 전국 순위 --- */}
      {activeTab === "ranking" ? (
        <div className="space-y-5">
          <div className="flex flex-wrap gap-2">
            {RANKING_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setRankingBy(opt.id)}
                className={`rounded-full px-4 py-2 text-xs font-bold transition-colors ${
                  rankingBy === opt.id
                    ? "bg-[var(--accent-strong)] text-white"
                    : "border border-[var(--line-strong)] bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {rankingQuery.isLoading ? (
            <SkeletonLoader count={4} itemClassName="h-20 rounded-2xl" />
          ) : null}
          {rankingQuery.isError ? (
            <WorkspaceQueryErrorCard
              title="전국 순위 로드 실패"
              description="온비드 부동산 순위 데이터를 불러오지 못했습니다."
              message={extractErrorMessage(rankingQuery.error)}
              actionLabel="다시 시도"
              onRetry={() => void rankingQuery.refetch()}
            />
          ) : null}
          {rankingQuery.data ? (
            rankingQuery.data.items.length ? (
              <div className="space-y-3">
                {rankingQuery.data.items.map((item, idx) => (
                  <button
                    type="button"
                    key={item.cltrMngNo ?? `rank-${idx}`}
                    onClick={() => setSelected(item)}
                    className="flex w-full items-center gap-4 rounded-2xl border border-[var(--line-strong)] bg-[var(--surface-soft)]/50 p-4 text-left transition-colors hover:bg-[var(--surface-soft)]"
                  >
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-strong)]/10 text-sm font-black text-[var(--accent-strong)]">
                      {item.rank ?? idx + 1}
                    </span>
                    {item.thumbnail ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={item.thumbnail}
                        alt=""
                        className="h-12 w-12 shrink-0 rounded-lg object-cover"
                      />
                    ) : (
                      <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg bg-[var(--surface-muted)] text-[var(--text-hint)]">
                        🏛️
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-bold text-[var(--text-primary)]">
                        {formatText(item.address)}
                      </p>
                      <p className="text-xs text-[var(--text-secondary)]">
                        {formatText(item.usage)} · {formatText(item.status)}
                      </p>
                    </div>
                    <div className="hidden shrink-0 text-right sm:block">
                      <p className="text-xs text-[var(--text-hint)]">감정가</p>
                      <p className="text-sm font-bold text-[var(--text-primary)]">
                        {formatCurrency(locale, item.appraisal_price)}
                      </p>
                    </div>
                    <div className="hidden shrink-0 text-right sm:block">
                      <p className="text-xs text-[var(--text-hint)]">할인율</p>
                      <p className="text-sm font-bold text-[var(--accent-strong)]">
                        {formatPercent(item.discount_rate)}
                      </p>
                    </div>
                    <div className="shrink-0 text-right">
                      <p className="text-xs text-[var(--text-hint)]">최저입찰가</p>
                      <p className="text-sm font-bold text-[var(--text-primary)]">
                        {formatBidPrice(item.min_bid_price, locale)}
                      </p>
                    </div>
                  </button>
                ))}
                {rankingQuery.data.data_source ? (
                  <p className="text-right text-[10px] text-[var(--text-hint)]">
                    출처: {rankingQuery.data.data_source}
                  </p>
                ) : null}
              </div>
            ) : (
              <EmptyState message="온비드 순위 데이터가 없습니다. API 키 연결을 확인하세요." />
            )
          ) : null}
        </div>
      ) : null}

      {/* 상세 모달 */}
      {selected ? (
        <DetailModal item={selected} locale={locale} onClose={() => setSelected(null)} />
      ) : null}
    </section>
  );
}

function AuctionTable({
  items,
  locale,
  variant,
  onSelect,
}: {
  items: AuctionItem[];
  locale: Locale;
  variant: "results";
  onSelect: (item: AuctionItem) => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-[var(--line)] text-left text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
            <th className="py-3 pr-4">주소</th>
            <th className="py-3 pr-4">용도</th>
            <th className="py-3 pr-4 text-right">감정가</th>
            <th className="py-3 pr-4 text-right">최저입찰가</th>
            <th className="py-3 pr-4 text-right">유찰</th>
            <th className="py-3 pr-4 text-right">낙찰가율</th>
            <th className="py-3 pr-4 text-right">낙찰가능가(추정)</th>
            <th className="py-3 pr-4">상태</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, idx) => (
            <tr
              key={item.cltrMngNo ?? `${variant}-${idx}`}
              onClick={() => onSelect(item)}
              className="cursor-pointer border-b border-[var(--line)]/60 transition-colors hover:bg-[var(--surface-soft)]/60"
            >
              <td className="max-w-[220px] truncate py-3 pr-4 font-bold text-[var(--text-primary)]">
                {formatText(item.address)}
              </td>
              <td className="py-3 pr-4 text-[var(--text-secondary)]">
                {formatText(item.usage)}
              </td>
              <td className="py-3 pr-4 text-right text-[var(--text-primary)]">
                {formatCurrency(locale, item.appraisal_price)}
              </td>
              <td className="py-3 pr-4 text-right text-[var(--text-primary)]">
                {formatBidPrice(item.min_bid_price, locale)}
              </td>
              <td className="py-3 pr-4 text-right text-[var(--text-secondary)]">
                {item.fail_count == null ? "-" : `${item.fail_count}회`}
              </td>
              <td className="py-3 pr-4 text-right text-[var(--text-secondary)]">
                {formatPercent(item.win_rate)}
              </td>
              <td className="py-3 pr-4 text-right font-bold text-[var(--accent-strong)]">
                {item.est_win == null ? "-" : `${formatCurrency(locale, item.est_win)}`}
              </td>
              <td className="py-3 pr-4 text-[var(--text-secondary)]">
                {formatText(item.status)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DetailModal({
  item,
  locale,
  onClose,
}: {
  item: AuctionItem;
  locale: Locale;
  onClose: () => void;
}) {
  const rows: { label: string; value: string }[] = [
    { label: "물건관리번호", value: formatText(item.cltrMngNo) },
    { label: "주소", value: formatText(item.address) },
    { label: "용도", value: formatText(item.usage) },
    { label: "감정가", value: formatCurrency(locale, item.appraisal_price) },
    { label: "최저입찰가", value: formatBidPrice(item.min_bid_price, locale) },
    { label: "할인율", value: formatPercent(item.discount_rate) },
    {
      label: "유찰횟수",
      value: item.fail_count == null ? "-" : `${item.fail_count}회`,
    },
    { label: "낙찰가율", value: formatPercent(item.win_rate) },
    { label: "낙찰가격", value: formatBidPrice(item.win_price, locale) },
    {
      label: "유효입찰자수",
      value: item.valid_bidder_count == null ? "-" : `${item.valid_bidder_count}명`,
    },
    {
      label: "토지면적",
      value: item.land_area == null ? "-" : `${item.land_area}㎡`,
    },
    {
      label: "건물면적",
      value: item.bld_area == null ? "-" : `${item.bld_area}㎡`,
    },
    {
      label: "낙찰가능가(추정)",
      value: item.est_win == null ? "-" : `${formatCurrency(locale, item.est_win)} (예상)`,
    },
    { label: "입찰상태", value: formatText(item.status) },
    { label: "입찰기간", value: `${formatText(item.bid_start)} ~ ${formatText(item.bid_end)}` },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="dialog"
      aria-modal="true"
      onClick={onClose}
    >
      <div
        className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-2xl)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <h3 className="text-xl font-black tracking-tight text-[var(--text-primary)]">
            물건 상세
          </h3>
          <button
            type="button"
            onClick={onClose}
            aria-label="닫기"
            className="rounded-full border border-[var(--line)] px-3 py-1 text-sm text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            ✕
          </button>
        </div>
        <dl className="space-y-2">
          {rows.map((row) => (
            <div
              key={row.label}
              className="flex items-center justify-between gap-4 border-b border-[var(--line)]/50 py-2"
            >
              <dt className="text-xs font-bold text-[var(--text-hint)]">{row.label}</dt>
              <dd className="text-right text-sm font-medium text-[var(--text-primary)]">
                {row.value}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-[10px] text-[var(--text-hint)]">
          감정가·낙찰가능가는 추정치이며 가정이 포함됩니다. 온비드 비공개 항목은
          &quot;비공개&quot;로 표기합니다.
        </p>
      </div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-hint)] opacity-60">
        🏛️
      </span>
      <p className="text-sm font-bold text-[var(--text-hint)]">{message}</p>
    </div>
  );
}

function FieldInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
        {label}
      </span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
      />
    </label>
  );
}

function FieldSelect({
  label,
  value,
  options,
  optionLabels,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  optionLabels?: Record<string, string>;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="cursor-pointer appearance-none rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
      >
        {options.map((opt) => (
          <option key={opt || "all"} value={opt}>
            {optionLabels?.[opt] ?? (opt === "" ? "전체" : opt)}
          </option>
        ))}
      </select>
    </label>
  );
}

function FieldRange({
  label,
  minValue,
  maxValue,
  onMin,
  onMax,
}: {
  label: string;
  minValue: string;
  maxValue: string;
  onMin: (value: string) => void;
  onMax: (value: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">
        {label}
      </span>
      <div className="flex items-center gap-2">
        <input
          type="number"
          inputMode="numeric"
          value={minValue}
          onChange={(e) => onMin(e.target.value)}
          placeholder="최소"
          className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
        />
        <span className="text-[var(--text-hint)]">~</span>
        <input
          type="number"
          inputMode="numeric"
          value={maxValue}
          onChange={(e) => onMax(e.target.value)}
          placeholder="최대"
          className="w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-strong)]/50"
        />
      </div>
    </div>
  );
}
