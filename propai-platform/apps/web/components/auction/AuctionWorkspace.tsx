"use client";

import { useEffect, useMemo, useState, type FormEvent } from "react";
import { AuctionItemsMap, type AuctionMapItem } from "@/components/auction/AuctionItemsMap";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Construction, Landmark, Map, Search, Trophy } from "lucide-react";
import { WorkspaceQueryErrorCard } from "@/components/analytics/WorkspaceQueryErrorCard";
import { SkeletonLoader } from "@/components/ui/SkeletonLoader";
import { AuctionMonitorPanel } from "@/components/auction/AuctionMonitorPanel";
import { ApiClientError, apiClient, resolveApiOrigin } from "@/lib/api-client";
import { analyzeRegistry } from "@/lib/registry-analyze";
import { writePreCheckHandoff } from "@/components/precheck/handoff";
import { useRouter } from "next/navigation";
import type { Locale } from "@/i18n/config";

// 백엔드 계약(prefix /api/v1/auction, 메인 인증 apiClient) — 무목업.
// 일부 필드는 온비드 비공개/미제공으로 null 가능 → 정직 표기("비공개"/"-").

type AuctionItem = {
  rank?: number | null;
  cltrMngNo?: string | null;
  // 상세조회 키(getInqRnkClg/검색 목록 제공) — snake_case
  cltr_mng_no?: string | null;
  pbct_cdtn_no?: string | null;
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
  est_win_low?: number | null;
  est_win_high?: number | null;
  // 조건검색(bid-results) 추가 필드
  fail_count?: number | null;
  win_rate?: number | null;
  win_price?: number | null;
  valid_bidder_count?: number | null;
  land_area?: number | null;
  bld_area?: number | null;
  pnu?: string | null;
};

// 상세 엔드포인트(GET /auction/detail) 응답
type AuctionPrevBid = {
  round?: number | null;
  min_bid?: number | null;
  opbd_dt?: string | null;
  result?: string | null;
  win_price?: number | null;
  win_rate?: number | null;
};

type AuctionDetail = {
  cltr_mng_no?: string | null;
  fail_count?: number | null;
  land_area?: number | null;
  bld_area?: number | null;
  win_rate?: number | null;
  win_price?: number | null;
  appraisal_price?: number | null;
  min_bid_price?: number | null;
  image_url?: string | null;
  prev_bids?: AuctionPrevBid[] | null;
  usage?: string | null;
  address?: string | null;
  status?: string | null;
  est_win?: number | null;
  est_win_low?: number | null;
  est_win_high?: number | null;
  est_win_detail?: string | null;
  // PNU 토지특성·항공뷰 보강(NED + VWorld)
  pnu?: string | null;
  zone_type?: string | null;
  land_category?: string | null;
  official_price_per_sqm?: number | null;
  land_area_source?: string | null;
  aerial_image_url?: string | null;
  lat?: number | null;
  lon?: number | null;
  // 공고 물건정보(getPbancCltrInf2) 보강
  property_type?: string | null;
  disposal_method?: string | null;
  usage_category?: string | null;
  pbanc_mng_no?: string | null;
  // 부동산 물건상세정보(getRlstDtlInf2) 보강 — 사진·이용현황·동영상·공고기관
  image_urls?: (string | null)[] | null;
  video_url?: string | null;
  usage_status?: string | null;
  location_desc?: string | null;
  org_name?: string | null;
  jibun_address?: string | null;
  // 입찰정보(getCltrBidInf2) — 입찰방법·보증금·잔대금·제출서류·제한
  bid_info?: {
    joint_bid?: string | null;
    proxy_bid?: string | null;
    e_guarantee?: string | null;
    deposit_alt_doc?: string | null;
    next_rank?: string | null;
    deposit?: string | null;
    balance_pay_method?: string | null;
    balance_pay_term?: string | null;
    bid_valid_criteria?: string | null;
    submit_docs?: string | null;
    qlfc_limit?: string | null;
    region_limit?: string | null;
    etc_limit?: string | null;
    notice?: string | null;
  } | null;
};

type AuctionDetailResponse = {
  item: AuctionDetail | null;
  data_source?: "onbid_live" | "unavailable" | string | null;
  reason?: string | null;
};

// 등기부등본 권리분석 결과(/registry/analyze) — 경매 상세 인라인 표시용 부분 타입
type RegistryAnalysisResult = {
  status?: string;
  message?: string;
  ai?: {
    ownership?: {
      current_owner?: string;
      share?: string;
      acquisition_date?: string;
      acquisition_price?: string;
      ownership_period?: string;
    };
    provisional_registration?: { exists?: boolean | null; detail?: string };
    seizure?: Array<{ type?: string; holder?: string; detail?: string; date?: string }>;
    mortgage?: Array<{ max_claim?: string; mortgagee?: string; date?: string }>;
    other_rights?: string[];
    rights_analysis?: string;
    risks?: string[];
  } | null;
  fetched?: { has_pdf?: boolean; pdf_url?: string | null } | null;
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
  { id: "ranking", label: "전국 순위", hint: "조회수·관심·최저가·할인율 정렬" },
  { id: "search", label: "조건검색", hint: "지역·종류·유찰·금액 조건 검색" },
  { id: "my", label: "내 경공매", hint: "관리 토지·프로젝트와 연동된 물건" },
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

  const [activeTab, setActiveTab] = useState<TabId>("ranking");
  const [rankingBy, setRankingBy] = useState<RankingBy>("views");

  // 조건검색: 입력 폼과 실제 적용 필터를 분리(검색 버튼 클릭 시 적용).
  const [filterForm, setFilterForm] = useState<BidFilters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<BidFilters | null>(null);
  const [saveName, setSaveName] = useState("");
  const [saveError, setSaveError] = useState("");

  const [selected, setSelected] = useState<AuctionItem | null>(null);
  // 전국 조건검색 결과 보기 모드: 목록(표) / 지도(지역별 물건 위치 마커).
  const [searchView, setSearchView] = useState<"list" | "map">("list");
  // 전국 순위 결과 보기 모드: 목록(랭킹카드) / 지도(지역별 물건 위치 마커).
  const [rankingView, setRankingView] = useState<"list" | "map">("list");

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
        className="cc-bracketed relative overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] p-6 shadow-[var(--shadow-inner)]"
      >
        <div className="cc-grid-bg opacity-50" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10 space-y-1">
          <div className="mb-1.5 flex items-center gap-2">
            <span className="cc-meta">AUCTION · ONBID INTEL</span>
            {canUseLiveApi ? <span className="cc-live"><i />LIVE</span> : <span className="cc-chip-data">STANDBY</span>}
          </div>
          <h1 className="text-3xl font-black tracking-tight text-[var(--text-primary)]">
            경매·공매
          </h1>
          <p className="text-sm text-[var(--text-secondary)]">
            온비드(getInqRnkClg·getCltrBidRsltList2) 실데이터 기반. 감정가·낙찰가능가는
            추정치이며 가정이 포함됩니다. 온비드 비공개 항목은 정직하게 &quot;비공개&quot;로
            표기합니다.
          </p>
        </div>
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
          {/* 경·공매 모니터링 센터: 관심대상 3방법 등록 + 관심대상별 매칭결과 + 수동실행 */}
          <AuctionMonitorPanel locale={locale} canUseLiveApi={canUseLiveApi} />

          {/* 프로젝트 연동 보드(기존): 관리 토지·프로젝트와 온비드 물건 매칭 */}
          <div className="border-t border-[var(--line)] pt-5">
            <h2 className="mb-1 text-lg font-black tracking-tight text-[var(--text-primary)]">
              프로젝트 연동 물건
            </h2>
            <p className="mb-4 text-xs text-[var(--text-hint)]">
              관리 중인 프로젝트·토지와 연동된 진행 물건을 프로젝트별로 모아 보여줍니다.
            </p>
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

              {(myQuery.data.combined ?? []).length ? (
                <div className="rounded-3xl border border-[var(--accent-strong)]/30 bg-[var(--surface-strong)] p-6">
                  <p className="sa-di-eyebrow mb-4">
                    통합 보드 · 전체 {(myQuery.data.combined ?? []).length}건
                  </p>
                  <AuctionTable
                    items={myQuery.data.combined ?? []}
                    locale={locale}
                    variant="results"
                    onSelect={setSelected}
                  />
                </div>
              ) : null}

              {(myQuery.data.projects ?? []).length ? (
                <div className="space-y-4">
                  {(myQuery.data.projects ?? []).map((project, idx) => (
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
              ) : !(myQuery.data.combined ?? []).length ? (
                <EmptyState message="관리 토지 중 경공매 진행 물건이 없습니다. 토지조서에 토지를 등록하면 자동 모니터링됩니다." />
              ) : null}
            </>
          ) : null}
          </div>
        </div>
      ) : null}

      {/* --- 탭 B: 조건검색 --- */}
      {activeTab === "search" ? (
        <div className="space-y-6">
          <p className="inline-flex flex-wrap items-baseline gap-1.5 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]/40 px-4 py-3 text-xs leading-relaxed text-[var(--text-secondary)]">
            <Search className="size-4 self-center shrink-0" aria-hidden /> 내 조건(지역·종류·유찰횟수·감정가·최저입찰가·면적)에 부합하는 경·공매 물건을 <strong className="text-[var(--text-primary)]">실시간으로 찾아</strong> 제공합니다. 조건을 저장하면 매칭 물건을 지속 추적합니다.
          </p>
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
          {Array.isArray(filtersQuery.data) && filtersQuery.data?.length ? (
            <div className="flex flex-wrap gap-2">
              {(filtersQuery.data ?? []).map((filter) => (
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
              {(bidResultsQuery.data.items ?? []).length ? (
                <div className="space-y-3">
                  {/* 목록/지도 보기 토글 — 지도는 물건을 지역별 위치 마커로 표시 */}
                  <div className="flex items-center justify-end gap-1">
                    {(["list", "map"] as const).map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => setSearchView(v)}
                        className={`rounded-lg border px-3 py-1.5 text-xs font-bold transition-colors ${
                          searchView === v
                            ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                            : "border-[var(--line)] text-[var(--text-secondary)] hover:border-[var(--text-tertiary)]"
                        }`}
                      >
                        {v === "list" ? "목록" : (<span className="inline-flex items-center gap-1.5"><Map className="size-3.5" aria-hidden />지도</span>)}
                      </button>
                    ))}
                  </div>
                  {searchView === "map" ? (
                    <AuctionItemsMap
                      items={(bidResultsQuery.data.items ?? []).map((it): AuctionMapItem => ({
                        key: it.cltr_mng_no ?? it.cltrMngNo ?? it.address ?? "",
                        address: it.address,
                        usage: it.usage,
                        min_bid_price: it.min_bid_price,
                        discount_rate: it.discount_rate,
                        fail_count: it.fail_count,
                        status: it.status,
                      }))}
                      onSelect={(key) => {
                        const found = (bidResultsQuery.data?.items ?? []).find(
                          (it) => (it.cltr_mng_no ?? it.cltrMngNo ?? it.address) === key,
                        );
                        if (found) setSelected(found);
                      }}
                    />
                  ) : (
                    <AuctionTable items={bidResultsQuery.data.items ?? []} locale={locale} variant="results" onSelect={setSelected} />
                  )}
                </div>
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
          <p className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)]/40 px-4 py-3 text-xs leading-relaxed text-[var(--text-secondary)]">
            <Trophy className="mr-1 inline size-4 align-text-bottom" aria-hidden />전국 공매 부동산을 <strong className="text-[var(--text-primary)]">조회수·관심·최저가·할인율</strong> 순으로 보여줍니다. 온비드는 진행중 물건의 <strong className="text-[var(--text-primary)]">최저입찰가를 비공개</strong>하므로, 감정가(실데이터)와 <strong className="text-[var(--text-primary)]">예상낙찰가·예상할인(추정)</strong>으로 저가 기회를 안내합니다.
          </p>
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
            (rankingQuery.data.items ?? []).length ? (
              <div className="space-y-3">
                {/* 목록/지도 보기 토글 — 순위 물건을 지역별 위치 마커로 표시(주소 기반) */}
                <div className="flex items-center justify-end gap-1">
                  {(["list", "map"] as const).map((v) => (
                    <button
                      key={v}
                      type="button"
                      onClick={() => setRankingView(v)}
                      className={`rounded-lg border px-3 py-1.5 text-xs font-bold transition-colors ${
                        rankingView === v
                          ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                          : "border-[var(--line)] text-[var(--text-secondary)] hover:border-[var(--text-tertiary)]"
                      }`}
                    >
                      {v === "list" ? "목록" : (<span className="inline-flex items-center gap-1.5"><Map className="size-3.5" aria-hidden />지도</span>)}
                    </button>
                  ))}
                </div>
                {rankingView === "map" ? (
                  <AuctionItemsMap
                    items={(rankingQuery.data.items ?? []).map((it): AuctionMapItem => ({
                      key: it.cltr_mng_no ?? it.cltrMngNo ?? it.address ?? "",
                      address: it.address,
                      usage: it.usage,
                      min_bid_price: it.est_win ?? it.min_bid_price,
                      discount_rate: it.discount_rate,
                      fail_count: it.fail_count,
                      status: it.status,
                    }))}
                    onSelect={(key) => {
                      const found = (rankingQuery.data?.items ?? []).find(
                        (it) => (it.cltr_mng_no ?? it.cltrMngNo ?? it.address) === key,
                      );
                      if (found) setSelected(found);
                    }}
                  />
                ) : (
                  <>
                {(rankingQuery.data.items ?? []).map((item, idx) => (
                  <button
                    type="button"
                    key={item.cltrMngNo ?? `rank-${idx}`}
                    onClick={() => setSelected(item)}
                    className="sa-di-block flex w-full items-center gap-4 p-4 text-left"
                  >
                    {/* 순위 배지 — 데이터 액센트 칩(블록 아이콘 톤과 통일) */}
                    <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--data-accent-line)] bg-[var(--data-accent-soft)] font-mono text-sm font-bold tabular-nums text-[var(--data-accent)]">
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
                        <Landmark className="size-6" aria-hidden />
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
                    {/* 우측 핵심 지표 — 온비드가 최저입찰가를 비공개하므로, 감정가(실)와
                        감정가 기반 예상낙찰가/예상할인(추정·is_estimate)으로 정직 안내한다. */}
                    {(() => {
                      // 예상할인율 = 1 − 예상낙찰가/감정가(둘 다 있을 때). 실 할인율이 있으면 우선.
                      const ap = item.appraisal_price ?? null;
                      const ew = item.est_win ?? null;
                      const realDisc = item.discount_rate ?? null;
                      const estDisc =
                        realDisc != null
                          ? realDisc
                          : ap && ew
                            ? Math.round((1 - ew / ap) * 100)
                            : null;
                      return (
                        <>
                          <div className="hidden shrink-0 flex-col items-end gap-0.5 sm:flex">
                            <span className="sa-di-eyebrow">감정가</span>
                            <span className="font-mono text-sm font-bold tabular-nums text-[var(--text-primary)]">
                              {formatCurrency(locale, ap)}
                            </span>
                          </div>
                          <div className="hidden shrink-0 flex-col items-end gap-0.5 sm:flex">
                            <span className="sa-di-eyebrow">{realDisc != null ? "할인율" : "예상할인"}</span>
                            <span className="font-mono text-sm font-bold tabular-nums text-[var(--data-accent)]">
                              {estDisc != null ? `${realDisc != null ? "" : "~"}${estDisc}%` : "-"}
                            </span>
                          </div>
                          <div className="flex shrink-0 flex-col items-end gap-0.5">
                            <span className="sa-di-eyebrow">{ew ? "예상낙찰가" : "최저입찰가"}</span>
                            <span className="font-mono text-sm font-bold tabular-nums text-[var(--text-primary)]">
                              {ew ? formatCurrency(locale, ew) : formatBidPrice(item.min_bid_price, locale)}
                            </span>
                          </div>
                        </>
                      );
                    })()}
                  </button>
                ))}
                {rankingQuery.data.data_source ? (
                  <p className="text-right text-[10px] text-[var(--text-hint)]">
                    출처: {rankingQuery.data.data_source}
                  </p>
                ) : null}
                  </>
                )}
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
  // 물건 목록 → 정밀 데이터 테이블(sa-di-table). 숫자열은 .sa-di-num(우측·mono·tabular).
  return (
    <div className="overflow-x-auto">
      <table className="sa-di-table min-w-[720px]">
        <thead>
          <tr>
            <th>주소</th>
            <th>용도</th>
            <th className="sa-di-num">감정가</th>
            <th className="sa-di-num">최저입찰가</th>
            <th className="sa-di-num">유찰</th>
            <th className="sa-di-num">낙찰가율</th>
            <th className="sa-di-num">낙찰가능가(추정)</th>
            <th>상태</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, idx) => (
            <tr
              key={item.cltrMngNo ?? `${variant}-${idx}`}
              onClick={() => onSelect(item)}
              className="cursor-pointer"
            >
              <td className="max-w-[220px] truncate font-bold">
                {formatText(item.address)}
              </td>
              <td className="text-[var(--text-secondary)]">
                {formatText(item.usage)}
              </td>
              <td className="sa-di-num">
                {formatCurrency(locale, item.appraisal_price)}
              </td>
              <td className="sa-di-num">
                {formatBidPrice(item.min_bid_price, locale)}
              </td>
              <td className="sa-di-num text-[var(--text-secondary)]">
                {item.fail_count == null ? "-" : `${item.fail_count}회`}
              </td>
              <td className="sa-di-num text-[var(--text-secondary)]">
                {formatPercent(item.win_rate)}
              </td>
              {/* 낙찰가능가(추정)는 핵심 KPI → 데이터 액센트로 강조 */}
              <td className="sa-di-num text-[var(--data-accent)]">
                {item.est_win == null ? "-" : `${formatCurrency(locale, item.est_win)}`}
              </td>
              <td className="text-[var(--text-secondary)]">
                {formatText(item.status)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// 숫자 가드: 유한 숫자만 통과(NaN/Infinity/문자 → null).
function safeNumber(value: unknown): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value;
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
  // 목록 아이템에 상세조회 키가 있으면 /auction/detail 실조회로 보강.
  const cltrMngNo = item.cltr_mng_no ?? item.cltrMngNo ?? null;
  const pbctCdtnNo = item.pbct_cdtn_no ?? null;
  const itemPnu = item.pnu ?? null;
  const canFetchDetail = Boolean(cltrMngNo && pbctCdtnNo);

  const detailQuery = useQuery({
    queryKey: ["auction", "detail", cltrMngNo, pbctCdtnNo, itemPnu],
    enabled: canFetchDetail,
    queryFn: () =>
      apiClient.get<AuctionDetailResponse>(
        `/auction/detail${buildSearchParams({
          cltr_mng_no: cltrMngNo ?? "",
          pbct_cdtn_no: pbctCdtnNo ?? "",
          // ONBID가 토지면적/이미지를 안 주면 PNU로 NED 토지특성·항공뷰 보강.
          ...(itemPnu ? { pnu: itemPnu } : {}),
        })}`,
      ),
  });

  const detail = detailQuery.data?.item ?? null;
  const detailUnavailable =
    detailQuery.data != null && detailQuery.data.data_source === "unavailable";

  // 목록값 우선 + 상세로 보강(상세 우선, 없으면 목록값).
  const pick = <T,>(detailVal: T | null | undefined, listVal: T | null | undefined): T | null =>
    detailVal != null ? detailVal : listVal ?? null;

  const cltrMngNoVal = pick(detail?.cltr_mng_no, cltrMngNo);
  const addressVal = pick(detail?.address, item.address);
  const usageVal = pick(detail?.usage, item.usage);
  const statusVal = pick(detail?.status, item.status);
  const appraisalVal = pick(safeNumber(detail?.appraisal_price), item.appraisal_price);
  const minBidVal = pick(safeNumber(detail?.min_bid_price), item.min_bid_price);
  const failCountVal = pick(safeNumber(detail?.fail_count), item.fail_count);
  const winRateVal = pick(safeNumber(detail?.win_rate), item.win_rate);
  const winPriceVal = pick(safeNumber(detail?.win_price), item.win_price);
  const landAreaVal = pick(safeNumber(detail?.land_area), item.land_area);
  const bldAreaVal = pick(safeNumber(detail?.bld_area), item.bld_area);

  // est_win: 숫자 가드 → NaN 방지. 상세 우선, 목록 폴백, 둘 다 없으면 null(추정 불가).
  const estWinVal = pick(safeNumber(detail?.est_win), safeNumber(item.est_win));
  const estWinLow = safeNumber(detail?.est_win_low);
  const estWinHigh = safeNumber(detail?.est_win_high);
  const imageUrl = detail?.image_url && detail.image_url.trim() ? detail.image_url : null;
  // 온비드 물건사진이 없으면(나대지 등) PNU 기반 실제 항공뷰(VWorld)로 대체 제공.
  const aerialUrl =
    !imageUrl && detail?.aerial_image_url
      ? `${resolveApiOrigin()}${detail.aerial_image_url}`
      : null;
  // 갤러리: 온비드 물건사진 전체(보통 3~4장). 없으면 단일 image_url 폴백.
  const galleryImages = (() => {
    const arr = (detail?.image_urls ?? []).filter(
      (u): u is string => typeof u === "string" && u.trim().length > 0,
    );
    if (arr.length) return arr;
    return imageUrl ? [imageUrl] : [];
  })();
  const [imgIdx, setImgIdx] = useState(0);
  const safeImgIdx = Math.min(imgIdx, Math.max(0, galleryImages.length - 1));
  const mainImage = galleryImages[safeImgIdx] ?? null;
  // 이미지 확대(라이트박스) 열림 여부 — 메인 사진을 누르면 전체화면으로 크게 본다.
  const [zoomOpen, setZoomOpen] = useState(false);
  const prevBids = Array.isArray(detail?.prev_bids) ? detail!.prev_bids! : [];

  // 라이트박스에서 키보드로 닫기(Esc)·좌우 이동(←/→) 지원.
  useEffect(() => {
    if (!zoomOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoomOpen(false);
      else if (e.key === "ArrowRight") setImgIdx((i) => Math.min(i + 1, galleryImages.length - 1));
      else if (e.key === "ArrowLeft") setImgIdx((i) => Math.max(i - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomOpen, galleryImages.length]);

  // ── 사안별 미제공 사유(데이터 신뢰도) ──
  const isLandOnly = /대지|토지|임야|전|답|잡종지|나대지/.test(
    `${usageVal ?? ""}${detail?.land_category ?? ""}`,
  );
  const inProgress = /진행|입찰중|예정/.test(statusVal ?? "");
  const minBidText =
    minBidVal != null
      ? formatBidPrice(minBidVal, locale)
      : inProgress
        ? "비공개 (입찰 진행 중 — 온비드 미공개)"
        : "비공개 (온비드 미제공)";
  const discountText =
    item.discount_rate != null
      ? formatPercent(item.discount_rate)
      : "유찰 이력 없음 / 온비드 미제공";
  const landAreaText =
    landAreaVal != null
      ? `${landAreaVal}㎡${detail?.land_area_source ? " · 토지대장(NED)" : ""}`
      : "온비드·공부 미제공";
  const bldAreaText =
    bldAreaVal != null
      ? `${bldAreaVal}㎡`
      : isLandOnly
        ? "해당없음 (나대지·토지 — 건물 없음)"
        : "온비드 미제공";

  // ── 등기부등본 권리분석(경매↔등기 시너지) ──
  const router = useRouter();
  const [regBusy, setRegBusy] = useState(false);
  const [regResult, setRegResult] = useState<RegistryAnalysisResult | null>(null);
  const [regErr, setRegErr] = useState<string | null>(null);
  const [regProgress, setRegProgress] = useState<string>("");
  const runRegistry = async () => {
    const addr = typeof addressVal === "string" ? addressVal.trim() : "";
    if (!addr && !itemPnu) {
      setRegErr("주소·PNU 정보가 없어 권리분석을 할 수 없습니다.");
      return;
    }
    setRegBusy(true);
    setRegErr(null);
    setRegProgress("등기부 발급·분석을 시작합니다…");
    try {
      const r = await analyzeRegistry<RegistryAnalysisResult>(
        { address: addr || undefined, pnu: itemPnu ?? undefined },
        setRegProgress,
      );
      setRegResult(r);
    } catch (e) {
      setRegErr(extractErrorMessage(e));
    } finally {
      setRegBusy(false);
    }
  };

  // ── 발굴(경매) → 기획 핸드오프 ── 기존 PreCheck 핸드오프(sessionStorage)를 그대로
  // 재사용해 projects/new가 주소·용도지역·면적·PNU를 선채움한다(consume 검증식 불변).
  // 주소가 없는 물건은 부지분석 시드가 불가능하므로 CTA 자체를 노출하지 않는다.
  const projectAddress =
    typeof addressVal === "string" && addressVal.trim() ? addressVal.trim() : null;
  const startProjectFromItem = () => {
    if (!projectAddress) return;
    const memoParts = ["온비드 경매 물건"];
    if (cltrMngNoVal) memoParts.push(`물건관리번호 ${cltrMngNoVal}`);
    if (usageVal) memoParts.push(usageVal);
    writePreCheckHandoff({
      address: projectAddress,
      zoneType: detail?.zone_type ?? null,
      areaSqm: landAreaVal,
      pnu: itemPnu ?? detail?.pnu ?? null,
      bestMethod: null,
      bestMethodName: null,
      source: "auction",
      memo: memoParts.join(" · "),
    });
    router.push(`/${locale}/projects/new`);
  };

  // ── 상세 속성을 '단락(섹션)'으로 분류한다 ──
  // 예전엔 모든 항목이 한 덩어리로 나열돼 무엇이 어떤 묶음인지 알기 어려웠다.
  // 이제 ①물건 개요 ②토지·건물 ③입찰·진행 3개 단락으로 나눠, 각 단락에 작은 제목(eyebrow)을 단다.
  // (감정가·최저입찰가·유찰횟수·낙찰가능가는 위쪽 큰 숫자 타일에 이미 있으므로 여기선 중복 제외.)
  type Row = { label: string; value: string };
  const rowGroups: { key: string; eyebrow: string; title: string; rows: Row[] }[] = [
    {
      key: "identity",
      eyebrow: "OVERVIEW",
      title: "물건 개요",
      rows: [
        { label: "물건관리번호", value: formatText(cltrMngNoVal) },
        { label: "주소", value: formatText(addressVal) },
        { label: "용도", value: formatText(detail?.usage_category ?? usageVal) },
        ...(detail?.property_type ? [{ label: "재산유형", value: detail.property_type }] : []),
        ...(detail?.disposal_method ? [{ label: "처분방식", value: detail.disposal_method }] : []),
        ...(detail?.org_name ? [{ label: "공고기관", value: detail.org_name }] : []),
      ],
    },
    {
      key: "land",
      eyebrow: "LAND · BUILDING",
      title: "토지·건물 현황",
      rows: [
        ...(detail?.zone_type ? [{ label: "용도지역", value: detail.zone_type }] : []),
        ...(detail?.official_price_per_sqm
          ? [{ label: "공시지가(㎡당)", value: formatCurrency(locale, detail.official_price_per_sqm) }]
          : []),
        { label: "토지면적", value: landAreaText },
        { label: "건물면적", value: bldAreaText },
        ...(detail?.usage_status ? [{ label: "이용상태", value: detail.usage_status }] : []),
        ...(detail?.location_desc ? [{ label: "위치·주위환경", value: detail.location_desc }] : []),
      ],
    },
    {
      key: "bid",
      eyebrow: "BID · PROGRESS",
      title: "입찰·진행",
      rows: [
        { label: "할인율", value: discountText },
        { label: "낙찰가율", value: formatPercent(winRateVal) },
        { label: "낙찰가격", value: formatBidPrice(winPriceVal, locale) },
        {
          label: "유효입찰자수",
          value: item.valid_bidder_count == null ? "-" : `${item.valid_bidder_count}명`,
        },
        {
          label: "낙찰가능가(추정)",
          value:
            estWinVal == null
              ? "추정 불가"
              : estWinLow != null && estWinHigh != null
                ? `${formatCurrency(locale, estWinVal)} (예상 · ${formatCurrency(
                    locale,
                    estWinLow,
                  )}~${formatCurrency(locale, estWinHigh)})`
                : `${formatCurrency(locale, estWinVal)} (예상)`,
        },
        { label: "입찰상태", value: formatText(statusVal) },
        { label: "입찰기간", value: `${formatText(item.bid_start)} ~ ${formatText(item.bid_end)}` },
      ],
    },
  ].map((g) => ({ ...g, rows: g.rows.filter((r) => r.value && r.value !== "-") }))
    .filter((g) => g.rows.length > 0);

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

        {/* 물건 이미지 갤러리: 온비드 물건사진 전체(메인+썸네일) → 없으면 항공뷰(VWorld) 대체.
            전체가 보이도록 object-contain + 반응형(letterbox). */}
        <div className="mb-4">
          <div className="relative flex aspect-[4/3] max-h-80 w-full items-center justify-center overflow-hidden rounded-2xl border border-[var(--line)] bg-black/40">
            {mainImage ? (
              <>
                {/* 메인 사진을 누르면 전체화면 확대(라이트박스)로 크게 본다. */}
                <button
                  type="button"
                  onClick={() => setZoomOpen(true)}
                  className="group flex h-full w-full cursor-zoom-in items-center justify-center"
                  aria-label="사진 확대해서 보기"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {/* max-h/max-w로 '원본 크기까지만' 표시 — h-full w-full로 강제 채우면 지적도 같은
                      저해상도 원본이 과하게 확대돼 뭉개진다(깨짐의 근본원인). 작은 이미지는 또렷하게
                      가운데 정렬되고, 큰 이미지만 컨테이너에 맞춰 줄어든다(레터박스). */}
                  <img
                    src={mainImage}
                    alt={`물건 사진 ${safeImgIdx + 1}`}
                    className="max-h-full max-w-full object-contain transition-transform duration-200 group-hover:scale-[1.02]"
                  />
                </button>
                {/* 확대 안내 아이콘(우상단) */}
                <span className="pointer-events-none absolute right-2 top-2 inline-flex items-center gap-1 rounded-md bg-black/55 px-2 py-0.5 text-[10px] font-bold text-white">
                  <Search className="size-3 shrink-0" aria-hidden /> 클릭하면 확대
                </span>
                {galleryImages.length > 1 ? (
                  <span className="pointer-events-none absolute bottom-1.5 right-2 rounded bg-black/55 px-2 py-0.5 text-[10px] font-bold text-white">
                    {safeImgIdx + 1} / {galleryImages.length}
                  </span>
                ) : null}
              </>
            ) : aerialUrl ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={aerialUrl} alt="대상지 항공뷰" className="max-h-full max-w-full object-contain" />
                <span className="absolute bottom-1.5 right-2 rounded bg-black/55 px-2 py-0.5 text-[10px] font-bold text-white">
                  항공뷰 (VWorld) · 온비드 물건사진 미제공
                </span>
              </>
            ) : (
              <span className="text-xs font-bold text-[var(--text-hint)]">
                {detailQuery.isLoading
                  ? "이미지 불러오는 중…"
                  : "이미지 없음 (온비드·항공뷰 미제공)"}
              </span>
            )}
          </div>
          {/* 썸네일 스트립(2장 이상) — 클릭 시 메인 전환 */}
          {galleryImages.length > 1 ? (
            <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
              {galleryImages.map((src, i) => (
                <button
                  key={`${src}-${i}`}
                  type="button"
                  onClick={() => setImgIdx(i)}
                  className={`flex h-14 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg border-2 bg-black/30 transition-all ${
                    i === safeImgIdx
                      ? "border-[var(--accent-strong)]"
                      : "border-[var(--line)] opacity-70 hover:opacity-100"
                  }`}
                  aria-label={`사진 ${i + 1} 보기`}
                >
                  {/* object-contain으로 썸네일도 잘리지 않게 전체를 보여준다(지적도 등 도면이 일부만
                      잘려 보이던 문제 해결). 배경은 은은한 어둠으로 레터박스 처리. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={src} alt={`썸네일 ${i + 1}`} className="max-h-full max-w-full object-contain" />
                </button>
              ))}
            </div>
          ) : null}
        </div>

        {/* ── 이미지 확대 라이트박스 ── 메인 사진 클릭 시 전체화면으로 크게 본다.
            배경/✕ 클릭·Esc로 닫고, 사진이 여러 장이면 ‹ › 또는 ←/→ 로 넘긴다. */}
        {zoomOpen && mainImage ? (
          <div
            className="fixed inset-0 z-[70] flex items-center justify-center bg-black/90 p-4"
            role="dialog"
            aria-modal="true"
            aria-label="물건 사진 확대 보기"
            onClick={() => setZoomOpen(false)}
          >
            {/* 닫기 */}
            <button
              type="button"
              onClick={() => setZoomOpen(false)}
              className="absolute right-4 top-4 flex h-10 w-10 items-center justify-center rounded-full bg-white/10 text-xl font-bold text-white transition hover:bg-white/20"
              aria-label="닫기"
            >
              ✕
            </button>
            {/* 이전 사진 */}
            {galleryImages.length > 1 ? (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setImgIdx((i) => Math.max(i - 1, 0)); }}
                disabled={safeImgIdx === 0}
                className="absolute left-3 flex h-12 w-12 items-center justify-center rounded-full bg-white/10 text-2xl text-white transition hover:bg-white/20 disabled:opacity-30"
                aria-label="이전 사진"
              >
                ‹
              </button>
            ) : null}
            {/* 확대 이미지 — 화면을 넘지 않게 contain. 클릭이 배경으로 전파돼 닫히지 않도록 stopPropagation. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={mainImage}
              alt={`물건 사진 확대 ${safeImgIdx + 1}`}
              onClick={(e) => e.stopPropagation()}
              className="max-h-[90vh] max-w-[92vw] object-contain"
            />
            {/* 다음 사진 */}
            {galleryImages.length > 1 ? (
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); setImgIdx((i) => Math.min(i + 1, galleryImages.length - 1)); }}
                disabled={safeImgIdx >= galleryImages.length - 1}
                className="absolute right-3 flex h-12 w-12 items-center justify-center rounded-full bg-white/10 text-2xl text-white transition hover:bg-white/20 disabled:opacity-30"
                aria-label="다음 사진"
              >
                ›
              </button>
            ) : null}
            {/* 매수(번호) 표시 */}
            <span className="absolute bottom-5 left-1/2 -translate-x-1/2 rounded-full bg-white/10 px-3 py-1 text-xs font-bold text-white">
              {safeImgIdx + 1} / {galleryImages.length}
            </span>
          </div>
        ) : null}

        {detail?.video_url ? (
          <a
            href={detail.video_url}
            target="_blank"
            rel="noopener noreferrer"
            className="mb-3 inline-flex items-center gap-1.5 text-[11px] font-bold text-[var(--accent-strong)] underline"
          >
            ▶ 물건 동영상 보기 (온비드)
          </a>
        ) : null}

        {/* 상세조회 상태 안내(정직) */}
        {canFetchDetail && detailQuery.isLoading ? (
          <p className="mb-3 rounded-xl bg-[var(--surface-soft)] px-4 py-2 text-[11px] font-bold text-[var(--text-hint)]">
            온비드 상세 정보를 불러오는 중…
          </p>
        ) : null}
        {canFetchDetail && detailQuery.isError ? (
          <p className="mb-3 rounded-xl bg-[var(--surface-soft)] px-4 py-2 text-[11px] font-bold text-[var(--spot)]">
            상세 불러오기 실패 — 목록 기준 정보만 표시합니다. (
            {extractErrorMessage(detailQuery.error)})
          </p>
        ) : null}
        {detailUnavailable ? (
          <p className="mb-3 rounded-xl bg-[var(--surface-soft)] px-4 py-2 text-[11px] font-bold text-[var(--text-hint)]">
            온비드 상세 미제공{detailQuery.data?.reason ? ` — ${detailQuery.data.reason}` : ""}. 목록
            기준 정보만 표시합니다.
          </p>
        ) : null}

        {/* 핵심 수치 4종 → metric tile(mono). 감정가·낙찰가능가만 액센트 강조 */}
        <div className="sa-di-tiles sa-di-tiles--4 mb-4">
          <div className="sa-di-tile sa-di-tile--accent">
            <span className="sa-di-tile__label">감정가</span>
            <span className="sa-di-tile__value">{formatCurrency(locale, appraisalVal)}</span>
          </div>
          <div className="sa-di-tile">
            <span className="sa-di-tile__label">최저입찰가</span>
            <span className="sa-di-tile__value">{minBidText}</span>
          </div>
          <div className="sa-di-tile">
            <span className="sa-di-tile__label">유찰횟수</span>
            <span className="sa-di-tile__value">
              {failCountVal == null ? "비공개" : `${failCountVal}회`}
            </span>
          </div>
          <div className="sa-di-tile sa-di-tile--accent">
            <span className="sa-di-tile__label">낙찰가능가(추정)</span>
            <span className="sa-di-tile__value">
              {estWinVal == null ? "추정 불가" : formatCurrency(locale, estWinVal)}
            </span>
          </div>
        </div>

        {/* 상세 속성 → '단락별'로 묶어 표시. 각 단락은 작은 제목(eyebrow) + 라벨↔값 로우. */}
        <div className="space-y-4">
          {rowGroups.map((group) => (
            <section key={group.key} className="sa-di-sub">
              <p className="sa-di-eyebrow mb-2">
                {group.eyebrow}
                <span className="ml-1.5 text-[var(--text-secondary)]">· {group.title}</span>
              </p>
              <dl className="sa-di-rows">
                {group.rows.map((row) => (
                  <div key={row.label} className="sa-di-row">
                    <dt className="sa-di-row__label">{row.label}</dt>
                    <dd className="sa-di-row__value">{row.value}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>

        {/* 회차별 입찰내역(prev_bids) */}
        {prevBids.length ? (
          <div className="sa-di-sub mt-5">
            <p className="sa-di-eyebrow mb-2">회차별 입찰내역</p>
            <div className="overflow-x-auto">
              <table className="sa-di-table min-w-[460px]">
                <thead>
                  <tr>
                    <th>회차</th>
                    <th>개찰일</th>
                    <th className="sa-di-num">최저입찰가</th>
                    <th>결과</th>
                    <th className="sa-di-num">낙찰가</th>
                    <th className="sa-di-num">낙찰가율</th>
                  </tr>
                </thead>
                <tbody>
                  {prevBids.map((b, idx) => (
                    <tr key={`${b.round ?? idx}-${b.opbd_dt ?? idx}`}>
                      <td className="font-bold">
                        {b.round == null ? "-" : `${b.round}회`}
                      </td>
                      <td className="text-[var(--text-secondary)]">
                        {formatText(b.opbd_dt)}
                      </td>
                      <td className="sa-di-num">
                        {formatBidPrice(safeNumber(b.min_bid), locale)}
                      </td>
                      <td className="text-[var(--text-secondary)]">
                        {formatText(b.result)}
                      </td>
                      <td className="sa-di-num">
                        {formatBidPrice(safeNumber(b.win_price), locale)}
                      </td>
                      <td className="sa-di-num text-[var(--text-secondary)]">
                        {formatPercent(safeNumber(b.win_rate))}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        ) : null}

        {/* ── 입찰정보 (getCltrBidInf2) ── */}
        {detail?.bid_info ? (
          <div className="sa-di-sub mt-5">
            <p className="sa-di-eyebrow mb-2">입찰정보</p>
            {/* 입찰방법 칩 — 가능=액센트 토큰, 불가=흐린 off 토큰(취소선) */}
            <div className="mb-3 flex flex-wrap gap-1.5">
              {([
                ["공동입찰", detail.bid_info.joint_bid],
                ["대리입찰", detail.bid_info.proxy_bid],
                ["전자보증서", detail.bid_info.e_guarantee],
                ["보증금 대체서류", detail.bid_info.deposit_alt_doc],
                ["차순위 신청", detail.bid_info.next_rank],
              ] as [string, string | null | undefined][])
                .filter(([, v]) => v)
                .map(([label, v]) => (
                  <span
                    key={label}
                    className={`sa-di-token ${v === "가능" ? "sa-di-token--accent" : "sa-di-token--off"}`}
                  >
                    {label} {v === "가능" ? "✓" : "✕"}
                  </span>
                ))}
            </div>
            {/* 입찰 세부 → 라벨↔값 데이터 로우(긴 텍스트는 줄바꿈 허용) */}
            <dl className="sa-di-rows">
              {([
                ["입찰보증금", detail.bid_info.deposit],
                ["잔대금 납부방법", detail.bid_info.balance_pay_method],
                ["잔대금 납부기한", detail.bid_info.balance_pay_term],
                ["입찰 성립기준", detail.bid_info.bid_valid_criteria],
                ["제출서류", detail.bid_info.submit_docs],
                ["자격 제한", detail.bid_info.qlfc_limit],
                ["지역 제한", detail.bid_info.region_limit],
                ["기타 제한", detail.bid_info.etc_limit],
                ["유의사항", detail.bid_info.notice],
              ] as [string, string | null | undefined][])
                .filter(([, v]) => v)
                .map(([label, v]) => (
                  <div key={label} className="sa-di-row">
                    <dt className="sa-di-row__label">{label}</dt>
                    <dd
                      className="sa-di-row__value max-w-[68%] whitespace-pre-line"
                      style={{ fontFamily: "inherit", fontWeight: 500, color: "var(--text-primary)" }}
                    >
                      {v}
                    </dd>
                  </div>
                ))}
            </dl>
          </div>
        ) : null}

        {/* ── 등기부등본 권리분석(경매↔등기 시너지) ── */}
        <div className="mt-5 rounded-2xl border border-[var(--accent-strong)]/25 bg-[var(--accent-strong)]/5 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="min-w-0">
              <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]"><Search className="size-4 shrink-0" aria-hidden /> 등기부등본 권리분석</p>
              <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
                말소기준권리·인수권리·근저당·압류·가등기를 AI(법무사·변호사 관점)가 분석합니다.
              </p>
              <p className="mt-0.5 text-[11px] font-bold text-[var(--accent-strong)]">
                권리분석 건당 2,000원 (동일 물건 재조회는 무료)
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <button
                type="button"
                onClick={runRegistry}
                disabled={regBusy}
                className="h-9 rounded-lg bg-[var(--accent-strong)] px-4 text-xs font-black text-white hover:opacity-90 disabled:opacity-50"
              >
                {regBusy ? "분석 중…" : "권리분석 실행"}
              </button>
              <button
                type="button"
                onClick={() => router.push(`/${locale}/registry-analysis`)}
                className="h-9 rounded-lg border border-[var(--line-strong)] px-3 text-xs font-bold text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                등기부등본 열람
              </button>
            </div>
          </div>

          {regBusy && regProgress ? (
            <p className="mt-3 text-[11px] font-bold text-[var(--text-hint)]">{regProgress}</p>
          ) : null}
          {regErr ? (
            <p className="mt-3 rounded-lg bg-[var(--surface-soft)] px-3 py-2 text-[11px] font-bold text-[var(--spot)]">
              {regErr}
            </p>
          ) : null}

          {regResult?.ai ? (
            <div className="mt-3 space-y-2 text-xs">
              {regResult.ai.ownership?.current_owner ? (
                <RegRow label="소유자" value={`${regResult.ai.ownership.current_owner}${regResult.ai.ownership.share ? ` (${regResult.ai.ownership.share})` : ""}`} />
              ) : null}
              {regResult.ai.mortgage?.length ? (
                <RegRow
                  label="근저당"
                  value={regResult.ai.mortgage
                    .map((m) => `${m.mortgagee ?? ""} ${m.max_claim ?? ""}`.trim())
                    .filter(Boolean)
                    .join(" · ")}
                />
              ) : null}
              {regResult.ai.seizure?.length ? (
                <RegRow
                  label="압류·가압류"
                  value={regResult.ai.seizure
                    .map((s) => `${s.type ?? ""} ${s.holder ?? ""}`.trim())
                    .filter(Boolean)
                    .join(" · ")}
                />
              ) : null}
              {regResult.ai.provisional_registration?.exists ? (
                <RegRow label="가등기" value={regResult.ai.provisional_registration.detail || "있음"} />
              ) : null}
              {regResult.ai.rights_analysis ? (
                <div className="rounded-lg bg-[var(--surface-soft)] px-3 py-2">
                  <p className="sa-di-eyebrow mb-1">권리분석</p>
                  <p className="leading-5 text-[var(--text-primary)]">{regResult.ai.rights_analysis}</p>
                </div>
              ) : null}
              {regResult.ai.risks?.length ? (
                <div className="rounded-lg border border-[var(--spot)]/30 bg-[var(--spot)]/10 px-3 py-2">
                  <p className="sa-di-eyebrow mb-1 !text-[var(--spot)]">위험요소</p>
                  <ul className="list-disc space-y-0.5 pl-4 text-[var(--text-primary)]">
                    {regResult.ai.risks.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {regResult.fetched?.pdf_url ? (
                <a
                  href={regResult.fetched.pdf_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block text-[11px] font-bold text-[var(--accent-strong)] underline"
                >
                  등기부등본 PDF 열기
                </a>
              ) : null}
            </div>
          ) : regResult && !regResult.ai ? (
            <p className="mt-3 text-[11px] text-[var(--text-hint)]">
              {regResult.message || "등기 권리분석 결과가 없습니다(연동 미설정 또는 무자료)."}
            </p>
          ) : null}
        </div>

        {/* ── 이 물건으로 프로젝트 생성(발굴 → 기획) ── 주소 미제공 물건은 비노출 */}
        {projectAddress ? (
          <div className="mt-3 rounded-2xl border border-[var(--accent-strong)]/25 bg-[var(--accent-strong)]/5 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="min-w-0">
                <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
                  <Construction className="size-4 shrink-0" aria-hidden /> 이 물건으로 프로젝트 생성
                </p>
                <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
                  주소·용도지역·면적을 새 프로젝트 화면에 선채움합니다. 면적·용도지역이
                  미제공이면 생성 화면에서 주소 검색으로 보강됩니다.
                </p>
              </div>
              <button
                type="button"
                onClick={startProjectFromItem}
                className="h-9 shrink-0 rounded-lg bg-[var(--accent-strong)] px-4 text-xs font-black text-white hover:opacity-90"
              >
                프로젝트 생성
              </button>
            </div>
          </div>
        ) : null}

        <p className="mt-4 text-[10px] text-[var(--text-hint)]">
          감정가·낙찰가능가는 추정치이며 가정이 포함됩니다. 온비드 비공개 항목은
          &quot;비공개&quot;로 표기합니다.
        </p>
      </div>
    </div>
  );
}

function RegRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start justify-between gap-3 border-b border-[var(--line)]/50 py-1.5">
      <span className="shrink-0 text-[var(--text-hint)]">{label}</span>
      <span className="text-right font-medium text-[var(--text-primary)]">{value || "-"}</span>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-hint)] opacity-60">
        <Landmark className="size-7" aria-hidden />
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
