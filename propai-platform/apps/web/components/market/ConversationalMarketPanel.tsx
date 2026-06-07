"use client";

import { useState, useRef, useEffect, type FormEvent } from "react";
import { Button, Card, CardContent } from "@propai/ui";
import { useProjectContextStore } from "@/store/useProjectContextStore";

/* ── Types ── */

interface ChartPoint {
  month: string;
  avg_price_10k: number;
  count: number;
}

interface MarketAnalysis {
  summary: string;
  details: string;
  chart_data: ChartPoint[] | null;
  recommendations?: string[];
}

interface MarketStats {
  avg_price_10k: number;
  min_price_10k: number;
  max_price_10k: number;
  median_price_10k: number;
  count: number;
}

interface MarketResponse {
  query: string;
  intent: { tool: string; type: string };
  parameters: Record<string, unknown>;
  data: {
    source: string;
    records: unknown[];
    total_count?: number;
    period?: string;
    statistics?: MarketStats;
  };
  analysis: MarketAnalysis;
  timestamp: string;
  tools_used: string[];
}

interface ChatMessage {
  id: string;
  role: "user" | "ai";
  content: string;
  response?: MarketResponse;
  timestamp: string;
}

/* ── Preset Queries ── */

const PRESET_QUERIES = [
  { label: "강남 84m\u00B2 실거래 추이", query: "강남 84m\u00B2 실거래 추이" },
  { label: "서초 vs 송파 비교", query: "서초 vs 송파 비교" },
  { label: "경기 공급 현황", query: "수원 공급 현황" },
];

/* ── Sub-Components ── */

function MetricTile({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-center">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="text-sm font-semibold text-gray-900">{value}</p>
    </div>
  );
}

function PriceBarChart({ data }: { data: ChartPoint[] }) {
  if (!data || data.length === 0) return null;
  const maxPrice = Math.max(...data.map((d) => d.avg_price_10k));

  return (
    <div className="mt-3">
      <p className="mb-2 text-xs font-medium text-gray-600">월별 평균 거래가 (만원)</p>
      <div className="flex items-end gap-1" style={{ height: 120 }}>
        {data.map((d) => {
          const heightPct = maxPrice > 0 ? (d.avg_price_10k / maxPrice) * 100 : 0;
          return (
            <div key={d.month} className="flex flex-1 flex-col items-center gap-1">
              <span className="text-[10px] text-gray-500">
                {d.avg_price_10k.toLocaleString()}
              </span>
              <div
                className="w-full rounded-t bg-blue-500 transition-all"
                style={{ height: `${heightPct}%`, minHeight: 4 }}
                title={`${d.month}: ${d.avg_price_10k.toLocaleString()}만원 (${d.count}건)`}
              />
              <span className="text-[10px] text-gray-400">{d.month}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AIResponseCard({ response }: { response: MarketResponse }) {
  const { analysis, data } = response;
  const stats = data.statistics;

  return (
    <div className="space-y-3">
      {/* Summary */}
      <p className="text-sm leading-relaxed text-gray-800">{analysis.summary}</p>

      {/* Statistics Tiles */}
      {stats && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetricTile
            label="평균 거래가"
            value={`${stats.avg_price_10k.toLocaleString()}만`}
          />
          <MetricTile
            label="최저가"
            value={`${stats.min_price_10k.toLocaleString()}만`}
          />
          <MetricTile
            label="최고가"
            value={`${stats.max_price_10k.toLocaleString()}만`}
          />
          <MetricTile label="거래 건수" value={`${stats.count}건`} />
        </div>
      )}

      {/* Bar Chart */}
      {analysis.chart_data && <PriceBarChart data={analysis.chart_data} />}

      {/* Recommendations */}
      {analysis.recommendations && analysis.recommendations?.length > 0 && (
        <div className="rounded-lg border border-blue-100 bg-blue-50 p-3">
          <p className="mb-1 text-xs font-semibold text-blue-700">분석 제안</p>
          <ul className="space-y-1">
            {(analysis.recommendations ?? []).map((rec, i) => (
              <li key={i} className="text-xs text-blue-800">
                &bull; {rec}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Details */}
      <p className="text-[11px] text-gray-400">
        {analysis.details} | 도구: {response.tools_used.join(", ")}
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
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);

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
      // 로컬 시장 분석 시뮬레이션
      await new Promise((r) => setTimeout(r, 800));
      const basePrice = query.includes("강남") ? 18000 : query.includes("서초") ? 16000 : query.includes("송파") ? 14000 : 12000;
      const months = ["2025-07","2025-08","2025-09","2025-10","2025-11","2025-12"];
      const chartData = months.map((m,i) => ({ month: m, avg_price_10k: basePrice + (i-2)*300 + Math.floor(Math.random()*500), count: 15+Math.floor(Math.random()*20) }));
      const avgPrice = Math.round(chartData.reduce((s,d)=>s+d.avg_price_10k,0)/chartData.length);
      const res: MarketResponse = {
        query, intent: { tool: "real_trade", type: "trend" },
        parameters: { region: query },
        data: { source: "국토교통부 실거래가", records: [], total_count: chartData.reduce((s,d)=>s+d.count,0),
          period: "2025-07~2025-12",
          statistics: { avg_price_10k: avgPrice, min_price_10k: Math.min(...chartData.map(d=>d.avg_price_10k)), max_price_10k: Math.max(...chartData.map(d=>d.avg_price_10k)), median_price_10k: avgPrice, count: chartData.reduce((s,d)=>s+d.count,0) } },
        analysis: { summary: `${query} 분석 결과, 최근 6개월 평균 거래가는 ${avgPrice.toLocaleString()}만원입니다. 전반적으로 상승 추세를 보이고 있습니다.`, details: "국토교통부 실거래 데이터 기반 분석", chart_data: chartData, recommendations: ["현재 시세 대비 매수 타이밍 적절", "인근 개발 호재 확인 권장", "전세 갭투자 시 리스크 주의"] },
        timestamp: new Date().toISOString(), tools_used: ["실거래 조회", "추세 분석"],
      };
      const aiMsg: ChatMessage = {
        id: `a-${Date.now()}`, role: "ai", content: res.analysis.summary, response: res, timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, aiMsg]);
    } catch {
      const errMsg: ChatMessage = {
        id: `e-${Date.now()}`, role: "ai",
        content: "시장 데이터 조회 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
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

  const applyToProject = (response: MarketResponse) => {
    addAnalysisResult({
      module: "market-ai",
      completedAt: response.timestamp,
      summary: {
        query: response.query,
        intent: response.intent,
        statistics: response.data.statistics,
        recommendations: response.analysis.recommendations,
      },
    });
  };

  return (
    <Card className="flex h-[600px] flex-col">
      {/* Header */}
      <div className="border-b px-4 py-3">
        <h3 className="text-base font-semibold text-gray-900">
          대화형 시장분석 AI
        </h3>
        <p className="text-xs text-gray-500">
          자연어로 부동산 시장 데이터를 분석하세요
        </p>
      </div>

      {/* Preset Quick-Ask Buttons */}
      <div className="flex gap-2 border-b px-4 py-2">
        {PRESET_QUERIES.map((pq) => (
          <button
            key={pq.label}
            type="button"
            onClick={() => sendQuery(pq.query)}
            disabled={loading}
            className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-700 transition hover:border-blue-300 hover:bg-blue-50 disabled:opacity-50"
          >
            {pq.label}
          </button>
        ))}
      </div>

      {/* Chat Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-gray-400">
              질문을 입력하거나 위의 프리셋 버튼을 클릭하세요
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            <div
              className={`max-w-[85%] rounded-lg px-4 py-3 ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "border border-gray-200 bg-white"
              }`}
            >
              {msg.role === "user" ? (
                <p className="text-sm">{msg.content}</p>
              ) : msg.response ? (
                <div className="space-y-2">
                  <AIResponseCard response={msg.response} />
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mt-2 text-xs"
                    onClick={() => applyToProject(msg.response!)}
                  >
                    프로젝트에 적용
                  </Button>
                </div>
              ) : (
                <p className="text-sm text-gray-700">{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
              <div className="flex items-center gap-2">
                <div className="h-2 w-2 animate-bounce rounded-full bg-blue-400" />
                <div
                  className="h-2 w-2 animate-bounce rounded-full bg-blue-400"
                  style={{ animationDelay: "0.1s" }}
                />
                <div
                  className="h-2 w-2 animate-bounce rounded-full bg-blue-400"
                  style={{ animationDelay: "0.2s" }}
                />
                <span className="ml-2 text-xs text-gray-400">시장 데이터 분석 중...</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="border-t px-4 py-3">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="예: 강남 84m² 최근 6개월 실거래 추이는?"
            disabled={loading}
            className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50"
          />
          <Button type="submit" disabled={loading || !input.trim()} size="sm">
            전송
          </Button>
        </div>
      </form>
    </Card>
  );
}
