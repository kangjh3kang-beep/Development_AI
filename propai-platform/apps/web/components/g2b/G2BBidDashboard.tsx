"use client";

import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { apiClient } from "@/lib/api-client";
import { G2BBidAnalysisModal } from "./G2BBidAnalysisModal";

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
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

const BID_TYPES = ["전체", "공사", "용역", "물품"];
const REGIONS = ["전체", "서울", "경기", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"];

/* ── 메인 컴포넌트 ── */
export default function G2BBidDashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [bids, setBids] = useState<G2BBid[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [loading, setLoading] = useState(true);

  // 필터
  const [keyword, setKeyword] = useState("");
  const [bidType, setBidType] = useState("전체");
  const [region, setRegion] = useState("전체");
  const [selectedBid, setSelectedBid] = useState<G2BBid | null>(null);
  const [showAnalysis, setShowAnalysis] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const data = await apiClient.get<DashboardStats>("/g2b/dashboard");
      setStats(data);
    } catch { /* fallback */ }
  }, []);

  const fetchBids = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "20" });
      if (keyword) params.set("keyword", keyword);
      if (bidType !== "전체") params.set("bid_type", bidType);
      if (region !== "전체") params.set("region_sido", region);

      const data = await apiClient.get<BidListResponse>(`/g2b/bids?${params}`);
      setBids(data.items);
      setTotal(data.total);
      setTotalPages(data.total_pages);
    } catch {
      setBids([]);
    } finally {
      setLoading(false);
    }
  }, [page, keyword, bidType, region]);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { fetchBids(); }, [fetchBids]);

  return (
    <div className="flex flex-col gap-10 pb-20">
      {/* ── 헤더 ── */}
      <motion.div initial={{ opacity: 0, y: -10 }} animate={{ opacity: 1, y: 0 }} className="space-y-3">
        <div className="flex items-center gap-4">
          <div className="h-12 w-12 rounded-2xl bg-gradient-to-br from-[var(--accent-strong)] to-blue-600 flex items-center justify-center text-white text-xl">🏛</div>
          <div>
            <h1 className="text-3xl font-[1000] tracking-tight text-[var(--text-primary)]">공공입찰 인텔리전스</h1>
            <p className="text-sm text-[var(--text-secondary)]">나라장터(G2B) 부동산·건설 입찰/낙찰 AI 분석 대시보드</p>
          </div>
        </div>
      </motion.div>

      {/* ── 통계 카드 ── */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {[
          { label: "진행 중 공고", value: stats?.total_active ?? 0, suffix: "건", color: "text-[var(--accent-strong)]" },
          { label: "마감 임박 (48h)", value: stats?.closing_soon ?? 0, suffix: "건", color: "text-amber-400" },
          { label: "평균 낙찰가율", value: stats?.avg_award_rate ? `${stats.avg_award_rate.toFixed(1)}` : "-", suffix: "%", color: "text-blue-400" },
          { label: "AI 추천 입찰", value: stats?.ai_recommended_count ?? 0, suffix: "건", color: "text-emerald-400" },
          { label: "총 추정가격", value: stats?.total_estimated_value ? formatKRW(stats.total_estimated_value) : "-", suffix: "", color: "text-purple-400" },
        ].map((s, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 hover:border-[var(--accent-strong)]/30 transition-colors"
          >
            <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--text-hint)] mb-2">{s.label}</p>
            <p className={`text-2xl font-[1000] tracking-tight ${s.color}`}>{s.value}<span className="text-sm font-bold ml-1">{s.suffix}</span></p>
          </motion.div>
        ))}
      </div>

      {/* ── 필터 바 ── */}
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4">
        <input
          type="text"
          placeholder="공고명 검색..."
          value={keyword}
          onChange={(e) => { setKeyword(e.target.value); setPage(1); }}
          className="flex-1 min-w-[200px] rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-4 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-hint)] outline-none focus:border-[var(--accent-strong)]"
        />
        <div className="flex gap-2">
          {BID_TYPES.map((t) => (
            <button
              key={t}
              onClick={() => { setBidType(t); setPage(1); }}
              className={`rounded-xl px-4 py-2 text-xs font-bold transition-all ${
                bidType === t ? "bg-[var(--accent-strong)] text-white shadow-lg" : "bg-[var(--surface-strong)] text-[var(--text-secondary)] border border-[var(--line)] hover:border-[var(--accent-strong)]/30"
              }`}
            >
              {t}
            </button>
          ))}
        </div>
        <select
          value={region}
          onChange={(e) => { setRegion(e.target.value); setPage(1); }}
          className="rounded-xl border border-[var(--line)] bg-[var(--surface-strong)] px-4 py-2.5 text-xs font-bold text-[var(--text-secondary)] outline-none"
        >
          {REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <span className="text-xs font-bold text-[var(--text-hint)]">총 {total}건</span>
      </div>

      {/* ── 입찰 리스트 ── */}
      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="h-56 animate-pulse rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)]" />
          ))}
        </div>
      ) : bids.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <span className="text-6xl mb-4">📋</span>
          <p className="text-lg font-bold text-[var(--text-secondary)]">조건에 맞는 입찰 공고가 없습니다</p>
          <p className="text-sm text-[var(--text-hint)] mt-1">필터를 조정하거나 키워드를 변경해 보세요</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <AnimatePresence mode="popLayout">
            {bids.map((bid, i) => {
              const days = daysUntil(bid.bid_close_dt);
              const isUrgent = days !== null && days <= 2;
              return (
                <motion.div
                  key={bid.id}
                  layout
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  transition={{ delay: i * 0.03 }}
                  className={`group relative rounded-2xl border bg-[var(--surface-soft)] p-5 transition-all hover:-translate-y-1 hover:shadow-lg cursor-pointer ${
                    isUrgent ? "border-amber-500/50" : "border-[var(--line)] hover:border-[var(--accent-strong)]/30"
                  }`}
                  onClick={() => setSelectedBid(bid)}
                >
                  {/* 상단 태그 */}
                  <div className="flex items-center justify-between mb-3">
                    <span className="rounded-lg bg-[var(--accent-soft)] px-2.5 py-1 text-[10px] font-black text-[var(--accent-strong)]">{bid.bid_type}</span>
                    {isUrgent && <span className="rounded-lg bg-amber-500/20 px-2.5 py-1 text-[10px] font-black text-amber-400 animate-pulse">D-{days}</span>}
                    {bid.ai_risk_score != null && bid.ai_risk_score <= 30 && (
                      <span className="rounded-lg bg-emerald-500/20 px-2.5 py-1 text-[10px] font-black text-emerald-400">AI 추천</span>
                    )}
                  </div>

                  {/* 공고명 */}
                  <h3 className="text-sm font-bold text-[var(--text-primary)] line-clamp-2 mb-3 min-h-[2.5rem]">{bid.bid_notice_nm}</h3>

                  {/* 발주기관 */}
                  <p className="text-[11px] text-[var(--text-secondary)] mb-2">
                    <span className="font-bold">{bid.org_name}</span>
                    {bid.org_type && <span className="ml-1 text-[var(--text-hint)]">({bid.org_type})</span>}
                  </p>

                  {/* 금액 */}
                  {bid.estimated_price && (
                    <p className="text-lg font-[1000] text-[var(--text-primary)] tracking-tight mb-3">
                      {formatKRW(bid.estimated_price)}
                    </p>
                  )}

                  {/* 카테고리 태그 */}
                  {bid.category_tags.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-3">
                      {bid.category_tags.slice(0, 3).map((tag) => (
                        <span key={tag} className="rounded-md bg-[var(--surface-strong)] px-2 py-0.5 text-[9px] font-bold text-[var(--text-hint)]">{tag}</span>
                      ))}
                    </div>
                  )}

                  {/* 하단: 지역 + 마감일 */}
                  <div className="flex items-center justify-between pt-3 border-t border-[var(--line)]">
                    <span className="text-[10px] font-bold text-[var(--text-hint)]">{bid.region_sido || "전국"}</span>
                    {bid.bid_close_dt && (
                      <span className="text-[10px] font-bold text-[var(--text-hint)]">
                        마감 {new Date(bid.bid_close_dt).toLocaleDateString("ko-KR")}
                      </span>
                    )}
                  </div>

                  {/* 호버 시 액션 버튼 */}
                  <div className="absolute inset-x-0 bottom-0 flex gap-2 p-3 opacity-0 group-hover:opacity-100 transition-opacity">
                    {bid.g2b_url && (
                      <a
                        href={bid.g2b_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        className="flex-1 rounded-xl bg-[var(--accent-strong)] py-2 text-center text-[10px] font-black text-white uppercase tracking-widest hover:bg-[var(--accent-strong)]/80 transition-colors"
                      >
                        나라장터 바로가기 ↗
                      </a>
                    )}
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}

      {/* ── 페이지네이션 ── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-30">이전</button>
          <span className="text-xs font-bold text-[var(--text-hint)]">{page} / {totalPages}</span>
          <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={page >= totalPages} className="rounded-xl border border-[var(--line)] bg-[var(--surface-soft)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] disabled:opacity-30">다음</button>
        </div>
      )}

      {/* ── 상세 모달 ── */}
      <AnimatePresence>
        {selectedBid && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4"
            onClick={() => setSelectedBid(null)}
          >
            <motion.div
              initial={{ scale: 0.9, y: 30 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.9, y: 30 }}
              className="w-full max-w-2xl max-h-[80vh] overflow-y-auto rounded-3xl border border-[var(--line-strong)] bg-[var(--surface-strong)] p-8 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-start justify-between mb-6">
                <div className="space-y-2">
                  <span className="rounded-lg bg-[var(--accent-soft)] px-3 py-1 text-[10px] font-black text-[var(--accent-strong)]">{selectedBid.bid_type}</span>
                  <h2 className="text-xl font-[900] text-[var(--text-primary)]">{selectedBid.bid_notice_nm}</h2>
                </div>
                <button onClick={() => setSelectedBid(null)} className="text-[var(--text-hint)] hover:text-[var(--text-primary)] text-2xl">×</button>
              </div>

              <div className="grid gap-4 sm:grid-cols-2 mb-6">
                <InfoTile label="발주기관" value={selectedBid.org_name} />
                <InfoTile label="기관유형" value={selectedBid.org_type || "-"} />
                <InfoTile label="추정가격" value={formatKRW(selectedBid.estimated_price)} />
                <InfoTile label="지역" value={selectedBid.region_sido || "전국"} />
                <InfoTile label="입찰마감" value={selectedBid.bid_close_dt ? new Date(selectedBid.bid_close_dt).toLocaleString("ko-KR") : "-"} />
                <InfoTile label="공고번호" value={selectedBid.bid_notice_no} />
              </div>

              {selectedBid.ai_analysis_summary && (
                <div className="rounded-2xl bg-[var(--surface-soft)] border border-[var(--line)] p-5 mb-6">
                  <p className="text-[10px] font-black uppercase tracking-[0.3em] text-[var(--accent-strong)] mb-3">AI 분석 결과</p>
                  <pre className="text-xs text-[var(--text-secondary)] whitespace-pre-wrap font-sans leading-relaxed">{selectedBid.ai_analysis_summary}</pre>
                </div>
              )}

              <div className="flex gap-3">
                {selectedBid.g2b_url && (
                  <a
                    href={selectedBid.g2b_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-1 rounded-2xl bg-[var(--accent-strong)] py-3.5 text-center text-sm font-black text-white uppercase tracking-widest hover:bg-[var(--accent-strong)]/80 transition-colors"
                  >
                    나라장터에서 입찰하기 ↗
                  </a>
                )}
                <button
                  onClick={() => setShowAnalysis(true)}
                  className="flex-1 rounded-2xl border-2 border-[var(--accent-strong)] py-3.5 text-center text-sm font-black text-[var(--accent-strong)] uppercase tracking-widest hover:bg-[var(--accent-soft)] transition-colors"
                >
                  AI 정밀분석
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {showAnalysis && selectedBid && (
        <G2BBidAnalysisModal
          bidId={selectedBid.id}
          bidName={selectedBid.bid_notice_nm}
          onClose={() => setShowAnalysis(false)}
        />
      )}
    </div>
  );
}

function InfoTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-[var(--surface-soft)] border border-[var(--line)] p-3">
      <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--text-hint)] mb-1">{label}</p>
      <p className="text-sm font-bold text-[var(--text-primary)]">{value}</p>
    </div>
  );
}
