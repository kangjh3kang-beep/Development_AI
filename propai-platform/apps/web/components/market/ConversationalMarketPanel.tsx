"use client";

/**
 * 대화형 시장분석 AI — 자연어 질의로 주변 실거래를 조회·요약한다.
 *
 * ★정직성 원칙(엄수): 가짜 데이터를 절대 만들지 않는다.
 *   - 모든 수치(평균·최저·최고·중앙값·건수·월별 추이)는 백엔드 /zoning/nearby-map가
 *     돌려준 '실제 국토부 실거래' 응답에서만 계산한다. (setTimeout·하드코딩·Math.random 제거)
 *   - 백엔드가 공공데이터 조회에 실패(fetch_failed)하면 "거래 0건"이 아니라 "조회 실패"로
 *     정직 표기한다. 실데이터가 없으면 가짜 수치·가짜 라벨을 만들지 않는다.
 *   - 출처(data_source)는 실응답 기준('live'|'unavailable')으로만 표기한다.
 *
 * 데이터 출처: NearbyTransactionsMap과 동일한 /zoning/nearby-map(카카오 지오코딩 + 국토부 실거래).
 * 질의의 지역 키워드(예: "강남", "수원 공급 현황")를 그대로 주소로 넘겨 조회한다.
 */

import { useState, useRef, useEffect, type FormEvent } from "react";
import { Button, Card } from "@propai/ui";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { apiClient } from "@/lib/api-client";
import type { NearbyMapPayload } from "@/components/map/NearbyTransactionsMap";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";

/* ── Types ── */

interface ChartPoint {
  month: string;
  avg_price_10k: number; // 만원, 해당 월 평균 거래가
  count: number;
}

interface MarketStats {
  avg_price_10k: number;
  min_price_10k: number;
  max_price_10k: number;
  median_price_10k: number;
  count: number;
}

/* 조회 결과(실데이터에서 계산된 것만). 데이터 미확보 시 stats=null. */
interface MarketResult {
  query: string;
  /** 'live' = 실거래 응답 사용, 'unavailable' = 공공데이터 미응답/무자료 */
  data_source: "live" | "unavailable";
  /** 백엔드가 채운 출처 라벨(있으면 그대로 표기, 없으면 미표시) */
  source_label?: string;
  /** 조회 중심 주소(백엔드 지오코딩 결과 우선) */
  center_address?: string;
  radius_m: number;
  months: number;
  total_count: number;
  stats: MarketStats | null;
  chart_data: ChartPoint[] | null;
  /** 정직 안내문(실패·무자료 시) */
  note?: string;
  timestamp: string;
}

interface ChatMessage {
  id: string;
  role: "user" | "ai";
  content: string;
  result?: MarketResult;
  timestamp: string;
}

/* ── Preset Queries ── */

const PRESET_QUERIES = [
  { label: "강남 실거래 추이", query: "강남" },
  { label: "서초 시세 현황", query: "서초" },
  { label: "수원 실거래", query: "수원" },
];

/* ── 응답 → 실통계/월별추이 계산(실데이터만 사용) ──
   nearby-map 응답의 매매 카테고리 deals(price_10k_won, deal_date)를 모아
   전체 통계와 월별 평균 추이를 만든다. 실거래가 없는 항목은 건너뛴다(가짜 0 금지). */
function buildResult(query: string, payload: NearbyMapPayload | null): MarketResult {
  const now = new Date().toISOString();
  const radius_m = payload?.radius_m ?? 1000;
  const months = payload?.months?.length ?? 3;

  // 공공데이터 조회 실패(응답 실패 또는 주소→법정동코드 해석 실패) → 정직 표기(가짜 수치·라벨 생성 안 함).
  // ★주소 해석 실패(error)는 fetch_failed 플래그가 없어 '표본 0'으로 오표기되던 것을 '조회 실패'로 바로잡는다.
  const errMsg = (payload as { error?: string } | null)?.error;
  if (!payload || payload.fetch_failed || errMsg) {
    return {
      query,
      data_source: "unavailable",
      radius_m,
      months,
      total_count: 0,
      stats: null,
      chart_data: null,
      note:
        errMsg ||
        payload?.note ||
        "국토부 실거래 공공데이터가 일시적으로 응답하지 않습니다. 거래가 없는 것이 아니라 조회 실패이며, 잠시 후 다시 시도해 주세요.",
      timestamp: now,
    };
  }

  // 매매 카테고리(_trade)의 실제 거래만 수집
  const cats = payload.categories || {};
  const prices: number[] = []; // 만원, 개별 거래가(실값만)
  const monthBuckets: Record<string, { sum: number; n: number }> = {};

  for (const [key, cat] of Object.entries(cats)) {
    if (!key.endsWith("_trade")) continue;
    for (const g of cat.groups || []) {
      for (const d of g.deals || []) {
        const p = d.price_10k_won;
        if (typeof p !== "number" || p <= 0) continue; // 실거래가 없는 건은 제외(가짜 0 금지)
        prices.push(p);
        // 월별 버킷: deal_date에서 YYYY-MM 추출(없으면 추이에서 제외)
        const m = (d.deal_date || "").match(/(\d{4})\D+(\d{1,2})/);
        if (m) {
          const ym = `${m[1]}-${String(Number(m[2])).padStart(2, "0")}`;
          const b = monthBuckets[ym] || { sum: 0, n: 0 };
          b.sum += p;
          b.n += 1;
          monthBuckets[ym] = b;
        }
      }
    }
  }

  // 매매 카테고리 건수 합(범례 카운트 기준 — 표본 거래수와 별개)
  const total_count = Object.entries(cats)
    .filter(([k]) => k.endsWith("_trade"))
    .reduce((a, [, c]) => a + (c.count || 0), 0);

  // 실거래 표본이 전혀 없으면 통계/차트 미생성(정직 무자료)
  if (prices.length === 0) {
    return {
      query,
      data_source: payload.partial_failed ? "unavailable" : "live",
      source_label: payload.data_source,
      center_address: payload.center?.address,
      radius_m,
      months,
      total_count,
      stats: null,
      chart_data: null,
      note:
        payload.note ||
        "해당 지역·기간의 매매 실거래 표본이 없습니다(전월세 또는 인접 기간에는 있을 수 있음).",
      timestamp: now,
    };
  }

  // 통계(실값에서만 산출)
  const sorted = [...prices].sort((a, b) => a - b);
  const sum = sorted.reduce((s, v) => s + v, 0);
  const avg = Math.round(sum / sorted.length);
  const min = sorted[0];
  const max = sorted[sorted.length - 1];
  const mid = sorted.length % 2
    ? sorted[(sorted.length - 1) / 2]
    : Math.round((sorted[sorted.length / 2 - 1] + sorted[sorted.length / 2]) / 2);

  // 월별 추이(실거래가 있는 월만, 시간순 정렬)
  const chart_data: ChartPoint[] = Object.entries(monthBuckets)
    .map(([month, b]) => ({ month, avg_price_10k: Math.round(b.sum / b.n), count: b.n }))
    .sort((a, b) => a.month.localeCompare(b.month));

  return {
    query,
    data_source: "live",
    source_label: payload.data_source,
    center_address: payload.center?.address,
    radius_m,
    months,
    total_count,
    stats: {
      avg_price_10k: avg,
      min_price_10k: min,
      max_price_10k: max,
      median_price_10k: mid,
      count: prices.length,
    },
    chart_data: chart_data.length > 0 ? chart_data : null,
    note: payload.partial_failed ? "일부 유형은 공공데이터 미응답으로 누락되었을 수 있습니다." : undefined,
    timestamp: now,
  };
}

/* ── Sub-Components ── */

/* ── 통계 metric 타일(sa-di-tile, mono·tabular-nums) ── */
function MetricTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="sa-di-tile">
      <span className="sa-di-tile__label">{label}</span>
      <span className="sa-di-tile__value">{value}</span>
    </div>
  );
}

/* ── 월별 평균 거래가 막대 차트 ──
   차트 로직(높이 비율 계산)은 그대로. 색은 데이터 액센트 토큰으로만 표현. */
function PriceBarChart({ data }: { data: ChartPoint[] }) {
  if (!data || data.length === 0) return null;
  const maxPrice = Math.max(...data.map((d) => d.avg_price_10k));

  return (
    <div className="mt-3">
      <p className="sa-di-eyebrow mb-2">월별 평균 거래가 (만원)</p>
      <div className="flex items-end gap-1" style={{ height: 120 }}>
        {data.map((d) => {
          const heightPct = maxPrice > 0 ? (d.avg_price_10k / maxPrice) * 100 : 0;
          return (
            <div key={d.month} className="flex flex-1 flex-col items-center gap-1">
              <span className="cc-num text-[10px] text-[var(--text-tertiary)]">
                {d.avg_price_10k.toLocaleString()}
              </span>
              <div
                className="w-full rounded-t transition-all"
                style={{ height: `${heightPct}%`, minHeight: 4, background: "var(--data-accent)" }}
                title={`${d.month}: ${d.avg_price_10k.toLocaleString()}만원 (${d.count}건)`}
              />
              <span className="cc-num text-[10px] text-[var(--text-hint)]">{d.month}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AIResponseCard({ result }: { result: MarketResult }) {
  const stats = result.stats;

  // 데이터 미확보 → 정직 안내(가짜 수치·차트 표시 안 함)
  if (result.data_source === "unavailable" || !stats) {
    return (
      <div className="space-y-2">
        <p className="text-sm leading-relaxed text-[var(--text-primary)]">
          &ldquo;{result.query}&rdquo; 지역의 실거래 데이터를 표시할 수 없습니다.
        </p>
        <div className="rounded-[var(--radius-sm)] border border-amber-400/40 bg-amber-500/10 px-3 py-2 text-xs text-[var(--text-secondary)]">
          ⚠️ {result.note || "실거래 데이터를 확보하지 못했습니다."}
        </div>
      </div>
    );
  }

  // 84㎡ 환산 평당가(실거래 평균에서 — 참고 표기)
  const summaryText =
    `"${result.query}" 주변 반경 ${(result.radius_m / 1000).toFixed(1)}km · 최근 ${result.months}개월 ` +
    `매매 실거래 ${stats.count.toLocaleString()}건 기준, 평균 거래가는 ${stats.avg_price_10k.toLocaleString()}만원입니다 ` +
    `(최저 ${stats.min_price_10k.toLocaleString()} ~ 최고 ${stats.max_price_10k.toLocaleString()}만원).`;

  // 산출 근거(EvidencePanel) — 모든 항목이 실응답 실값에서 옴(가짜 0 금지)
  const evidence: EvidenceItem[] = [
    {
      label: "데이터 출처",
      value: result.source_label || "국토부 실거래(/zoning/nearby-map)",
      basis: "VWorld/카카오 지오코딩 + 국토교통부 실거래 공공데이터",
    },
    {
      label: "표본 거래수",
      value: `${stats.count.toLocaleString()}건`,
      basis: `반경 ${(result.radius_m / 1000).toFixed(1)}km · 최근 ${result.months}개월 매매`,
    },
    {
      label: "평균 거래가",
      value: `${stats.avg_price_10k.toLocaleString()}만원`,
      basis: "표본 거래가 산술평균(만원)",
    },
    {
      label: "중앙값",
      value: `${stats.median_price_10k.toLocaleString()}만원`,
      basis: "표본 거래가 정렬 후 중앙값",
    },
  ];
  if (result.center_address) {
    evidence.unshift({ label: "조회 중심지", value: result.center_address, basis: "지오코딩 좌표 중심" });
  }

  return (
    <div className="space-y-3">
      {/* 요약(실데이터 기반 서술) */}
      <p className="text-sm leading-relaxed text-[var(--text-primary)]">{summaryText}</p>

      {/* 통계 타일(헤어라인 metric 그리드) */}
      <div className="sa-di-tiles sa-di-tiles--4">
        <MetricTile label="평균 거래가" value={`${stats.avg_price_10k.toLocaleString()}만`} />
        <MetricTile label="최저가" value={`${stats.min_price_10k.toLocaleString()}만`} />
        <MetricTile label="최고가" value={`${stats.max_price_10k.toLocaleString()}만`} />
        <MetricTile label="표본 건수" value={`${stats.count}건`} />
      </div>

      {/* 막대 차트(월별 실거래가 있는 달만) */}
      {result.chart_data && <PriceBarChart data={result.chart_data} />}

      {/* 산출 근거(공용 EvidencePanel) — 산식·출처 트레이스 */}
      <EvidencePanel title="산출 근거" items={evidence} defaultOpen={false} />

      {/* 부분 실패 안내(일부 유형 누락 가능성) */}
      {result.note && (
        <p className="text-[11px] text-[var(--text-hint)]">⚠️ {result.note}</p>
      )}

      {/* 출처 메타 */}
      <p className="text-[11px] text-[var(--text-hint)]">
        출처: {result.source_label || "국토교통부 실거래(공공데이터)"} · 조회 {new Date(result.timestamp).toLocaleString("ko-KR")}
      </p>
    </div>
  );
}

/* ── Main Component ── */

export default function ConversationalMarketPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const addAnalysisResult = useProjectContextStore((s) => s.addAnalysisResult);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const sendQuery = async (query: string) => {
    if (!query.trim() || loading) return;

    const userMsg: ChatMessage = {
      id: `u-${Date.now()}`,
      role: "user",
      content: query,
      timestamp: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      // ★실제 백엔드 호출 — 질의의 지역 키워드를 그대로 주소로 넘겨 실거래를 조회.
      //   NearbyTransactionsMap과 동일한 엔드포인트/스키마 사용(가짜 시뮬레이션 제거).
      const payload = await apiClient.post<NearbyMapPayload>("/zoning/nearby-map", {
        body: { address: query.trim(), radius_m: 1000, months: 6 },
        useMock: false,
        timeoutMs: 90000,
      });
      const result = buildResult(query.trim(), payload);
      const aiMsg: ChatMessage = {
        id: `a-${Date.now()}`,
        role: "ai",
        content:
          result.data_source === "live" && result.stats
            ? `${result.query} 실거래 분석 완료`
            : result.note || "실거래 데이터를 확보하지 못했습니다.",
        result,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch (e) {
      // 호출 실패 → 정직 표기(가짜 데이터 생성 안 함)
      const msg = e instanceof Error ? e.message : "주변 실거래 조회 실패";
      const errMsg: ChatMessage = {
        id: `e-${Date.now()}`,
        role: "ai",
        content: `시장 데이터 조회 중 오류가 발생했습니다(${msg}). 잠시 후 다시 시도해주세요.`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errMsg]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendQuery(input);
  };

  // 프로젝트에 적용 — 실데이터(stats 존재)만 영속. 무자료/실패는 적용 불가(하류 오염 방지).
  const applyToProject = (result: MarketResult) => {
    if (result.data_source !== "live" || !result.stats) return;
    addAnalysisResult({
      module: "market-ai",
      completedAt: result.timestamp,
      summary: {
        query: result.query,
        data_source: result.data_source, // 실응답 기준 출처 표기
        source_label: result.source_label,
        center_address: result.center_address,
        radius_m: result.radius_m,
        months: result.months,
        statistics: result.stats,
        chart_data: result.chart_data,
      },
    });
  };

  return (
    <Card className="flex h-[600px] flex-col">
      {/* 헤더 — 대화형 시장분석 AI */}
      <div className="border-b border-[var(--line)] px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="sa-di-eyebrow">CONVERSATIONAL · MARKET AI</span>
          <span className="cc-live"><i />LIVE</span>
        </div>
        <h3 className="mt-1 text-base font-semibold text-[var(--text-primary)]">
          대화형 시장분석 AI
        </h3>
        <p className="text-xs text-[var(--text-secondary)]">
          지역명을 입력하면 국토부 실거래(반경 1km·최근 6개월)를 조회·분석합니다
        </p>
      </div>

      {/* 프리셋 빠른질문 버튼(헤어라인 토큰 칩) */}
      <div className="flex gap-2 border-b border-[var(--line)] px-4 py-2">
        {PRESET_QUERIES.map((pq) => (
          <button
            key={pq.label}
            type="button"
            onClick={() => sendQuery(pq.query)}
            disabled={loading}
            className="sa-di-token disabled:opacity-50"
          >
            {pq.label}
          </button>
        ))}
      </div>

      {/* 대화 메시지 */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <p className="sa-di-empty">
              지역명(예: 강남, 수원 영통)을 입력하거나 위의 프리셋 버튼을 클릭하세요
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-[var(--radius-sm)] px-4 py-3 ${
                msg.role === "user"
                  ? "bg-[var(--accent-strong)] text-white"
                  : "border border-[var(--line)] bg-[var(--surface)]"
              }`}
            >
              {msg.role === "user" ? (
                <p className="text-sm">{msg.content}</p>
              ) : msg.result ? (
                <div className="space-y-2">
                  <AIResponseCard result={msg.result} />
                  {/* 실데이터일 때만 '프로젝트에 적용' 노출(무자료/실패는 영속 금지) */}
                  {msg.result.data_source === "live" && msg.result.stats && (
                    <Button
                      variant="secondary"
                      size="sm"
                      className="mt-2 text-xs"
                      onClick={() => applyToProject(msg.result!)}
                    >
                      프로젝트에 적용
                    </Button>
                  )}
                </div>
              ) : (
                <p className="text-sm text-[var(--text-secondary)]">{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-[var(--radius-sm)] border border-[var(--line)] bg-[var(--surface)] px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 animate-bounce rounded-full bg-[var(--data-accent)]" />
                <div
                  className="h-2 w-2 animate-bounce rounded-full bg-[var(--data-accent)]"
                  style={{ animationDelay: "0.1s" }}
                />
                <div
                  className="h-2 w-2 animate-bounce rounded-full bg-[var(--data-accent)]"
                  style={{ animationDelay: "0.2s" }}
                />
                <span className="ml-2 text-xs text-[var(--text-hint)]">실거래 데이터 수집·분석 중...</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* 입력 */}
      <form onSubmit={handleSubmit} className="border-t border-[var(--line)] px-4 py-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="예: 강남, 수원 영통, 서울 송파"
            disabled={loading}
            className="flex-1 rounded-[var(--radius-sm)] border border-[var(--line-strong)] bg-[var(--surface)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-strong)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-strong)] disabled:opacity-60"
          />
          <Button type="submit" disabled={loading || !input.trim()} size="sm">
            전송
          </Button>
        </div>
      </form>
    </Card>
  );
}
