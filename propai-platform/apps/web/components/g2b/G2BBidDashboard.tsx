"use client";

import { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { writePreCheckHandoff } from "@/components/precheck/handoff";
import { G2BBidAnalysisModal } from "./G2BBidAnalysisModal";
import { G2BBidDetailModal } from "./G2BBidDetailModal";
import { G2BAwardStats } from "./G2BAwardStats";

/* ── 타입 ── */
type G2BBid = {
  id: string;
  bid_notice_no: string;
  bid_notice_nm: string;
  bid_type: string;
  category_tags: string[];
  org_name: string;
  org_type: string | null;
  estimated_price: number | null;
  bid_begin_dt: string | null;
  bid_close_dt: string | null;
  region_sido: string | null;
  status: string;
  award_rate: number | null;
  g2b_url: string | null;
  ai_risk_score: number | null;
  ai_recommended_bid_rate: number | null;
  ai_analysis_summary: string | null;
};

type DashboardStats = {
  total_active: number;
  closing_soon: number;
  avg_award_rate: number | null;
  ai_recommended_count: number;
  total_estimated_value: number | null;
};

type BidListResponse = {
  items: G2BBid[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
};

type AnalysisHistoryItem = {
  id: string;
  bid_id: string;
  bid_notice_no: string | null;
  bid_notice_nm: string | null;
  params: Record<string, unknown>;
  recommended_bid_rate: number | null;
  risk_score: number | null;
  expected_roi: number | null;
  summary: string | null;
  created_at: string | null;
};

/* ── 유틸리티 ── */
function formatKRW(v: number | null): string {
  if (v == null) return "-";
  if (v >= 1_0000_0000) return `${(v / 1_0000_0000).toFixed(1)}억원`;
  if (v >= 1_0000) return `${(v / 1_0000).toFixed(0)}만원`;
  return `${v.toLocaleString()}원`;
}

function daysUntil(dt: string | null): number | null {
  if (!dt) return null;
  const diff = new Date(dt).getTime() - Date.now();
  return Math.ceil(diff / (1000 * 60 * 60 * 24));
}

const BID_TYPES = ["전체", "공사", "용역", "물품"];
const REGIONS = ["전체", "서울", "경기", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"];
const PAGE_SIZES = [10, 20, 30, 50, 100];

/* 대분류별 색상(소분류 칩·카드 태그) — 차트 팔레트 토큰으로 카테고리 구분(하드코딩 색상 금지) */
const GROUP_COLOR: Record<string, string> = {
  "설계·감리": "text-[var(--chart-6)] bg-[var(--surface-strong)] border-[var(--line)]",
  "정비·도시개발": "text-[var(--chart-5)] bg-[var(--surface-strong)] border-[var(--line)]",
  "시공": "text-[var(--chart-1)] bg-[var(--surface-strong)] border-[var(--line)]",
  "자재·산업": "text-[var(--chart-3)] bg-[var(--surface-strong)] border-[var(--line)]",
};
function tagColor(tag: string, groups: Record<string, string[]>): string {
  for (const [g, subs] of Object.entries(groups)) {
    if (subs.includes(tag)) return GROUP_COLOR[g] || "text-[var(--text-secondary)] bg-[var(--surface-strong)] border-[var(--line)]";
  }
  return "text-[var(--text-secondary)] bg-[var(--surface-strong)] border-[var(--line)]";
}

/* ── 메인 컴포넌트 ── */
export default function G2BBidDashboard() {
  const router = useRouter();
  const { locale } = useParams() as { locale: string };
  const [tab, setTab] = useState<"bids" | "history" | "awards">("bids");
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [bids, setBids] = useState<G2BBid[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);

  // 카테고리
  const [groups, setGroups] = useState<Record<string, string[]>>({});
  const [activeGroup, setActiveGroup] = useState<string>("");

  // 필터
  const [keyword, setKeyword] = useState("");
  const [bidType, setBidType] = useState("전체");
  const [region, setRegion] = useState("전체");
  const [categoryTag, setCategoryTag] = useState("");
  const [closingSoon, setClosingSoon] = useState(false);

  // 모달
  const [selectedBid, setSelectedBid] = useState<G2BBid | null>(null);
  const [analysisCtx, setAnalysisCtx] = useState<{
    bidId: string;
    bidName?: string;
    initialResult?: Record<string, unknown> | null;
    initialForm?: Record<string, string>;
  } | null>(null);

  const fetchStats = useCallback(async () => {
    try {
      setStats(await apiClient.get<DashboardStats>("/g2b/dashboard"));
    } catch { /* noop */ }
  }, []);

  const fetchCategories = useCallback(async () => {
    try {
      const data = await apiClient.get<{ groups: Record<string, string[]> }>("/g2b/categories");
      setGroups(data.groups || {});
    } catch { /* noop */ }
  }, []);

  const fetchBids = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
      if (keyword) params.set("keyword", keyword);
      if (bidType !== "전체") params.set("bid_type", bidType);
      if (region !== "전체") params.set("region_sido", region);
      if (categoryTag) params.set("category_tag", categoryTag);
      if (closingSoon) params.set("closing_days", "7");

      const data = await apiClient.get<BidListResponse>(`/g2b/bids?${params}`);
      setBids(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch {
      setBids([]);
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, keyword, bidType, region, categoryTag, closingSoon]);

  useEffect(() => { fetchStats(); fetchCategories(); }, [fetchStats, fetchCategories]);
  useEffect(() => { if (tab === "bids") fetchBids(); }, [fetchBids, tab]);

  const resetPage = () => setPage(1);

  // ── 발굴(G2B) → 기획 핸드오프 ── 기존 PreCheck 핸드오프(sessionStorage)를 재사용해
  // projects/new가 주소(시도)·메모(공고명)를 선채움한다(consume 검증식 불변).
  // G2B 공고는 시도(region_sido)까지만 제공 → 정밀 주소는 생성 화면의 주소 검색으로 보강.
  // region_sido가 없으면 주소 시드가 불가능하므로 CTA를 노출하지 않는다.
  const createProjectFromBid = useCallback(
    (bid: G2BBid) => {
      const region = bid.region_sido?.trim();
      if (!region) return;
      writePreCheckHandoff({
        address: region,
        zoneType: null,
        areaSqm: null,
        pnu: null,
        bestMethod: null,
        bestMethodName: null,
        source: "g2b",
        memo: bid.bid_notice_nm || null,
      });
      router.push(`/${locale}/projects/new`);
    },
    [router, locale],
  );

  return (
    <div className="flex flex-col gap-6 pb-20">
      {/* ── 헤더 (커맨드센터) ── */}
      <div className="cc-bracketed relative flex items-center gap-3 overflow-hidden rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface-soft)] px-5 py-4 shadow-[var(--shadow-inner)]">
        <div className="cc-grid-bg opacity-50" />
        <i className="cc-bracket cc-bracket--tl" />
        <i className="cc-bracket cc-bracket--tr" />
        <i className="cc-bracket cc-bracket--bl" />
        <i className="cc-bracket cc-bracket--br" />
        <div className="relative z-10 h-11 w-11 rounded-2xl bg-gradient-to-br from-[var(--accent-strong)] to-[var(--accent)] flex items-center justify-center text-white text-lg">🏛</div>
        <div className="relative z-10">
          <div className="mb-1 flex items-center gap-2">
            <span className="cc-meta">G2B · PUBLIC BID CONTROL</span>
            <span className="cc-live"><i />LIVE</span>
          </div>
          <h1 className="text-2xl font-[1000] tracking-tight text-[var(--text-primary)]">공공입찰 분석</h1>
          <p className="text-xs text-[var(--text-secondary)]">나라장터(G2B) 부동산·건설 입찰/낙찰 AI 분석</p>
        </div>
      </div>

      {/* ── 통계 카드 (계기판 모듈) ── */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-5">
        {[
          { label: "진행 중 공고", value: stats?.total_active ?? 0, suffix: "건", color: "text-[var(--accent-strong)]" },
          { label: "마감 임박 (7일)", value: stats?.closing_soon ?? 0, suffix: "건", color: "text-[var(--status-warning)]" },
          { label: "평균 낙찰가율", value: stats?.avg_award_rate ? `${stats.avg_award_rate.toFixed(1)}` : "-", suffix: "%", color: "text-[var(--data-accent)]" },
          { label: "AI 추천 입찰", value: stats?.ai_recommended_count ?? 0, suffix: "건", color: "text-[var(--status-success)]" },
          { label: "총 추정가격", value: stats?.total_estimated_value ? formatKRW(stats.total_estimated_value) : "-", suffix: "", color: "text-[var(--accent-strong)]" },
        ].map((s, i) => (
          <div key={i} className="cc-panel cc-interactive p-3.5">
            <p className="cc-label mb-1.5">{s.label}</p>
            <p className={`cc-num text-xl font-[1000] tracking-tight ${s.color}`}>{s.value}<span className="text-xs font-bold ml-0.5">{s.suffix}</span></p>
          </div>
        ))}
      </div>

      {/* ── 탭 ── */}
      <div className="flex gap-1 rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] p-1 w-fit">
        {([["bids", "입찰 공고"], ["history", "분석 히스토리"], ["awards", "낙찰 통계"]] as const).map(([k, label]) => (
          <button
            key={k}
            onClick={() => setTab(k)}
            className={`rounded-lg px-4 py-2 text-xs font-bold transition-all ${
              tab === k ? "bg-[var(--accent-strong)] text-white shadow" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* ══════════ 입찰 공고 탭 ══════════ */}
      {tab === "bids" && (
        <>
          {/* 필터 (compact, 공간 최소화) */}
          <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 space-y-3">
            {/* 1행: 검색 + 업무구분 + 지역 + 마감임박 */}
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="text"
                placeholder="공고명 검색..."
                value={keyword}
                onChange={(e) => { setKeyword(e.target.value); resetPage(); }}
                className="flex-1 min-w-[180px] rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-3.5 py-2 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] outline-none focus:border-[var(--accent-strong)]"
              />
              <div className="flex gap-1">
                {BID_TYPES.map((t) => (
                  <button
                    key={t}
                    onClick={() => { setBidType(t); resetPage(); }}
                    className={`rounded-lg px-3 py-2 text-xs font-bold transition-all ${
                      bidType === t ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-strong)] text-[var(--text-secondary)] border border-[var(--line)]"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <select
                value={region}
                onChange={(e) => { setRegion(e.target.value); resetPage(); }}
                className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)] outline-none"
              >
                {REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
              </select>
              <button
                onClick={() => { setClosingSoon((v) => !v); resetPage(); }}
                className={`rounded-lg px-3 py-2 text-xs font-bold transition-all ${
                  closingSoon ? "bg-[var(--status-warning)] text-white" : "bg-[var(--surface-strong)] text-[var(--status-warning)] border border-[var(--status-warning)]/40"
                }`}
              >
                ⏰ 마감임박
              </button>
            </div>

            {/* 2행: 대분류 → 소분류 */}
            <div className="flex flex-wrap items-center gap-1.5">
              <button
                onClick={() => { setActiveGroup(""); setCategoryTag(""); resetPage(); }}
                className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all ${
                  !activeGroup && !categoryTag ? "bg-[var(--accent-strong)] text-white" : "bg-[var(--surface-strong)] text-[var(--text-secondary)] border border-[var(--line)]"
                }`}
              >
                전체
              </button>
              {Object.keys(groups).map((g) => (
                <button
                  key={g}
                  onClick={() => { setActiveGroup(activeGroup === g ? "" : g); }}
                  className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-all border ${
                    activeGroup === g ? "border-[var(--accent-strong)] text-[var(--accent-strong)] bg-[var(--accent-soft)]" : "border-[var(--line)] bg-[var(--surface-strong)] text-[var(--text-secondary)]"
                  }`}
                >
                  {g}
                </button>
              ))}
            </div>

            {/* 소분류 칩 (선택된 대분류만 노출 → 공간 최소화) */}
            {activeGroup && groups[activeGroup] && (
              <div className="flex flex-wrap gap-1.5 border-t border-[var(--line)] pt-3">
                {groups[activeGroup].map((sub) => (
                  <button
                    key={sub}
                    onClick={() => { setCategoryTag(categoryTag === sub ? "" : sub); resetPage(); }}
                    className={`rounded-full px-3 py-1 text-[11px] font-bold border transition-all ${
                      categoryTag === sub ? "bg-[var(--accent-strong)] text-white border-[var(--accent-strong)]" : tagColor(sub, groups)
                    }`}
                  >
                    {sub}
                  </button>
                ))}
              </div>
            )}

            {/* 결과 수 + page_size */}
            <div className="flex items-center justify-between border-t border-[var(--line)] pt-3">
              <span className="text-xs font-bold text-[var(--text-secondary)]">
                총 <span className="text-[var(--text-primary)]">{total.toLocaleString()}</span>건
                {categoryTag && <span className="ml-1 text-[var(--accent-strong)]">· {categoryTag}</span>}
              </span>
              <label className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-secondary)]">
                페이지당
                <select
                  value={pageSize}
                  onChange={(e) => { setPageSize(Number(e.target.value)); resetPage(); }}
                  className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2 py-1 text-xs font-bold text-[var(--text-primary)] outline-none"
                >
                  {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}개</option>)}
                </select>
              </label>
            </div>
          </div>

          {/* 입찰 리스트 */}
          {loading ? (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <div key={i} className="h-52 animate-pulse rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)]" />
              ))}
            </div>
          ) : bids.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-20 text-center">
              <span className="text-5xl mb-3">📋</span>
              <p className="text-base font-bold text-[var(--text-secondary)]">조건에 맞는 입찰 공고가 없습니다</p>
              <p className="text-sm text-[var(--text-hint)] mt-1">필터를 조정하거나 키워드를 변경해 보세요</p>
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {bids.map((bid) => (
                <BidCard
                  key={bid.id}
                  bid={bid}
                  groups={groups}
                  onClick={() => setSelectedBid(bid)}
                  onCreateProject={
                    bid.region_sido?.trim() ? () => createProjectFromBid(bid) : undefined
                  }
                />
              ))}
            </div>
          )}

          {/* 페이지네이션 */}
          {totalPages > 1 && (
            <div className="flex items-center justify-center gap-2">
              <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-30">이전</button>
              <span className="text-xs font-bold text-[var(--text-secondary)]">{page} / {totalPages}</span>
              <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-30">다음</button>
            </div>
          )}
        </>
      )}

      {/* ══════════ 분석 히스토리 탭 ══════════ */}
      {tab === "history" && (
        <AnalysisHistory
          onView={(item, result) =>
            setAnalysisCtx({ bidId: item.bid_id, bidName: item.bid_notice_nm || undefined, initialResult: result })
          }
          onReanalyze={(item) =>
            setAnalysisCtx({
              bidId: item.bid_id,
              bidName: item.bid_notice_nm || undefined,
              initialForm: paramsToForm(item.params),
            })
          }
        />
      )}

      {/* ══════════ 낙찰 통계 탭 ══════════ */}
      {tab === "awards" && (
        <G2BAwardStats bidType={bidType !== "전체" ? bidType : undefined} regionSido={region !== "전체" ? region : undefined} />
      )}

      {/* ── 상세 모달 (풍부한 공식 상세페이지급 + 하단 AI CTA) ── */}
      {selectedBid && (
        <G2BBidDetailModal
          seed={{
            id: selectedBid.id,
            bid_notice_no: selectedBid.bid_notice_no,
            bid_notice_nm: selectedBid.bid_notice_nm,
            bid_type: selectedBid.bid_type,
            org_name: selectedBid.org_name,
            org_type: selectedBid.org_type,
            estimated_price: selectedBid.estimated_price,
            bid_close_dt: selectedBid.bid_close_dt,
            region_sido: selectedBid.region_sido,
            status: selectedBid.status,
            award_rate: selectedBid.award_rate,
            g2b_url: selectedBid.g2b_url,
          }}
          onClose={() => setSelectedBid(null)}
          onAnalyze={(bidId, bidName) => {
            setAnalysisCtx({ bidId, bidName });
            setSelectedBid(null);
          }}
        />
      )}

      {/* ── AI 분석 모달 ── */}
      {analysisCtx && (
        <G2BBidAnalysisModal
          bidId={analysisCtx.bidId}
          bidName={analysisCtx.bidName}
          initialResult={(analysisCtx.initialResult as never) ?? null}
          initialForm={analysisCtx.initialForm}
          onClose={() => setAnalysisCtx(null)}
        />
      )}
    </div>
  );
}

/* ── 입찰 카드 (가독성 강화) ── */
function BidCard({
  bid,
  groups,
  onClick,
  onCreateProject,
}: {
  bid: G2BBid;
  groups: Record<string, string[]>;
  onClick: () => void;
  /** 발굴 → 기획 CTA. region_sido 미제공 공고는 undefined → 버튼 비노출 */
  onCreateProject?: () => void;
}) {
  const days = daysUntil(bid.bid_close_dt);
  const dday =
    days == null ? null : days < 0 ? "마감" : days === 0 ? "D-DAY" : `D-${days}`;
  const ddayStyle =
    days == null ? "" :
    days < 0 ? "bg-[var(--surface-strong)] text-[var(--text-hint)]" :
    days <= 3 ? "bg-[var(--status-error)]/20 text-[var(--status-error)] animate-pulse" :
    days <= 7 ? "bg-[var(--status-warning)]/20 text-[var(--status-warning)]" :
    "bg-[var(--surface-strong)] text-[var(--text-secondary)]";
  const isRecommended = bid.ai_risk_score != null && bid.ai_risk_score <= 30;

  return (
    // CTA 버튼을 품기 위해 button → div[role=button] (button 중첩은 invalid HTML).
    // 키보드 접근성(Enter/Space)은 onKeyDown으로 유지.
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      className="group cursor-pointer text-left rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4 transition-all hover:-translate-y-0.5 hover:border-[var(--accent-strong)]/40 hover:shadow-lg"
    >
      {/* 상단: 업무구분 + D-day */}
      <div className="flex items-center justify-between mb-2.5">
        <span className="rounded-md bg-[var(--accent-soft)] px-2 py-0.5 text-[10px] font-black text-[var(--accent-strong)]">{bid.bid_type}</span>
        <div className="flex items-center gap-1.5">
          {isRecommended && <span className="rounded-md bg-[var(--status-success)]/20 px-2 py-0.5 text-[10px] font-black text-[var(--status-success)]">AI추천</span>}
          {dday && <span className={`rounded-md px-2 py-0.5 text-[10px] font-black ${ddayStyle}`}>{dday}</span>}
        </div>
      </div>

      {/* 공고명 */}
      <h3 className="text-[15px] font-bold text-[var(--text-primary)] leading-snug line-clamp-2 min-h-[2.6rem] mb-2.5">
        {bid.bid_notice_nm}
      </h3>

      {/* 추정가격(강조) */}
      <p className="cc-num text-xl font-[1000] text-[var(--accent-strong)] tracking-tight mb-3">
        {formatKRW(bid.estimated_price)}
      </p>

      {/* 정보 행 */}
      <div className="space-y-1.5 text-xs mb-3">
        <div className="flex justify-between gap-2">
          <span className="text-[var(--text-hint)]">발주기관</span>
          <span className="font-semibold text-[var(--text-secondary)] truncate text-right">{bid.org_name}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-[var(--text-hint)]">지역 · 마감</span>
          <span className="font-semibold text-[var(--text-secondary)] text-right">
            {bid.region_sido || "전국"}
            {bid.bid_close_dt && ` · ${new Date(bid.bid_close_dt).toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" })}`}
          </span>
        </div>
      </div>

      {/* 카테고리 태그(색상 구분) */}
      {bid.category_tags?.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-3 border-t border-[var(--line)]">
          {bid.category_tags.slice(0, 4).map((tag) => (
            <span key={tag} className={`rounded-md border px-1.5 py-0.5 text-[10px] font-bold ${tagColor(tag, groups)}`}>{tag}</span>
          ))}
        </div>
      )}

      {/* ── 이 공고로 프로젝트 생성(발굴 → 기획) ── region_sido 미제공 시 비노출 */}
      {onCreateProject ? (
        <div className="mt-3 border-t border-[var(--line)] pt-3">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onCreateProject();
            }}
            title="공고 지역(시도)·공고명을 새 프로젝트 화면에 선채움합니다. 정밀 주소는 생성 화면의 주소 검색으로 보강하세요."
            className="w-full rounded-lg border border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] px-3 py-1.5 text-[11px] font-black text-[var(--accent-strong)] transition-colors hover:bg-[var(--accent-soft)]/70"
          >
            🏗️ 이 공고로 프로젝트 생성
          </button>
        </div>
      ) : null}
    </div>
  );
}

/* ── params(JSON) → 폼 프리필 ── */
function paramsToForm(params: Record<string, unknown>): Record<string, string> {
  const s = (k: string) => (params[k] != null ? String(params[k]) : "");
  return {
    total_gfa_sqm: s("total_gfa_sqm"),
    floor_count_above: s("floor_count_above"),
    structure_type: s("structure_type"),
    building_type_override: s("building_type_override"),
    target_margin_pct: s("target_margin_pct") || "5",
  };
}

/* ── 분석 히스토리 ── */
function AnalysisHistory({
  onView,
  onReanalyze,
}: {
  onView: (item: AnalysisHistoryItem, result: Record<string, unknown>) => void;
  onReanalyze: (item: AnalysisHistoryItem) => void;
}) {
  const [items, setItems] = useState<AnalysisHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiClient.get<{ items: AnalysisHistoryItem[] }>("/g2b/analyses?page_size=100");
      setItems(data.items || []);
    } catch {
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const view = async (item: AnalysisHistoryItem) => {
    setBusy(item.id);
    try {
      const detail = await apiClient.get<{ result: Record<string, unknown> }>(`/g2b/analyses/${item.id}`);
      onView(item, detail.result || {});
    } catch { /* noop */ } finally { setBusy(null); }
  };

  const remove = async (item: AnalysisHistoryItem) => {
    if (!confirm("이 분석 내역을 삭제하시겠습니까?")) return;
    setBusy(item.id);
    try {
      await apiClient.delete(`/g2b/analyses/${item.id}`);
      setItems((prev) => prev.filter((x) => x.id !== item.id));
    } catch { /* noop */ } finally { setBusy(null); }
  };

  if (loading) return <div className="text-sm text-[var(--text-hint)] py-8 text-center">분석 히스토리 로딩 중…</div>;
  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <span className="text-5xl mb-3">🗂️</span>
        <p className="text-base font-bold text-[var(--text-secondary)]">저장된 분석 내역이 없습니다</p>
        <p className="text-sm text-[var(--text-hint)] mt-1">입찰 공고에서 AI 정밀분석을 실행하면 여기에 자동 저장됩니다</p>
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      {items.map((item) => (
        <div key={item.id} className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-bold text-[var(--text-primary)] truncate">{item.bid_notice_nm || item.bid_notice_no || "분석"}</p>
              <p className="text-[11px] text-[var(--text-hint)] mt-0.5">
                {item.created_at ? new Date(item.created_at).toLocaleString("ko-KR") : ""}
              </p>
            </div>
            <div className="flex shrink-0 gap-1.5">
              <button onClick={() => view(item)} disabled={busy === item.id} className="rounded-lg bg-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-bold text-white hover:opacity-90 disabled:opacity-50">재조회</button>
              <button onClick={() => onReanalyze(item)} className="rounded-lg border border-[var(--accent-strong)] px-3 py-1.5 text-[11px] font-bold text-[var(--accent-strong)] hover:bg-[var(--accent-soft)]">편집 재분석</button>
              <button onClick={() => remove(item)} disabled={busy === item.id} className="rounded-lg border border-[var(--status-error)]/40 px-3 py-1.5 text-[11px] font-bold text-[var(--status-error)] hover:bg-[var(--status-error)]/10 disabled:opacity-50">삭제</button>
            </div>
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <HistStat label="추천 투찰가율" value={item.recommended_bid_rate != null ? `${item.recommended_bid_rate.toFixed(1)}%` : "-"} />
            <HistStat label="예상 ROI" value={item.expected_roi != null ? `${item.expected_roi.toFixed(1)}%` : "-"} />
            <HistStat label="리스크" value={item.risk_score != null ? `${item.risk_score.toFixed(0)}점` : "-"} />
          </div>
        </div>
      ))}
    </div>
  );
}

function HistStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] p-2.5 text-center">
      <p className="text-[10px] text-[var(--text-hint)]">{label}</p>
      <p className="cc-num text-sm font-black text-[var(--text-primary)] mt-0.5">{value}</p>
    </div>
  );
}
