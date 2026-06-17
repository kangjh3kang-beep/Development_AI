"use client";

/**
 * 입지 인프라(POI) 카드 — Kakao Local 카테고리 반경검색.
 *
 * 주소/지번을 VWorld로 좌표화한 뒤, 좌표 반경 내 시설(지하철·학교·병원·약국·마트·
 * 편의점·은행·공공기관·문화·관광·음식·카페)을 정량 조사하고 접근성 점수를 보여준다.
 * 무목업: 키 미설정/조회 실패 시 정직 표기. opt-in 실행.
 */

import { useCallback, useState } from "react";
import { apiClient } from "@/lib/api-client";

type Cat = { label: string; count: number; nearest_m: number | null; unavailable?: boolean };
type Resp = {
  available: boolean;
  reason?: string;
  radius_m?: number;
  poi_accessibility_score?: number;
  categories?: Record<string, Cat>;
  geocoded_from?: string | null;
  coordinates?: { lat: number; lon: number };
};

const RADII = [500, 1000, 2000];

function scoreColor(s: number): string {
  if (s >= 80) return "text-emerald-400";
  if (s >= 60) return "text-[var(--accent-strong)]";
  if (s >= 40) return "text-amber-400";
  return "text-rose-400";
}

export function SiteInfraPoiCard({ address, className = "" }: { address?: string; className?: string }) {
  const [radius, setRadius] = useState(1000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<Resp | null>(null);

  const run = useCallback(async (r: number) => {
    if (!address?.trim()) { setError("주소를 먼저 선택하세요."); return; }
    setLoading(true); setError(""); setData(null);
    try {
      const res = await apiClient.post<Resp>("/site-score/poi-infra", {
        body: { address: address.trim(), radius_m: r },
        useMock: false, timeoutMs: 40000,
      });
      setData(res);
    } catch {
      setError("입지 인프라 조회에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [address]);

  return (
    <div className={`rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5 ${className}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-black text-[var(--text-primary)]">🏙 입지 인프라(POI) 분석</p>
          <p className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
            반경 내 교통·교육·의료·생활·금융·문화 시설을 Kakao Local로 정량 조사해 접근성을 평가합니다.
          </p>
        </div>
        <div className="flex items-center gap-1">
          {RADII.map((r) => (
            <button key={r} onClick={() => { setRadius(r); void run(r); }} disabled={loading}
              className={`rounded-lg border px-2.5 py-1 text-[11px] font-bold disabled:opacity-50 ${radius === r ? "border-[var(--accent-strong)]/40 bg-[var(--accent-soft)] text-[var(--accent-strong)]" : "border-[var(--line)] text-[var(--text-secondary)]"}`}>
              {r >= 1000 ? `${r / 1000}km` : `${r}m`}
            </button>
          ))}
          <button onClick={() => void run(radius)} disabled={loading || !address?.trim()}
            className="ml-1 rounded-lg bg-[var(--accent-strong)] px-3 py-1 text-[11px] font-black text-white hover:opacity-90 disabled:opacity-50">
            {loading ? "조사 중…" : data ? "다시" : "조사"}
          </button>
        </div>
      </div>

      {error && <p className="mt-2 text-xs font-semibold text-rose-500">{error}</p>}

      {data && !data.available && (
        <p className="mt-3 text-xs text-amber-500">⚠ {data.reason || "입지 인프라 데이터를 사용할 수 없습니다."}</p>
      )}

      {data && data.available && (
        <div className="mt-4 space-y-3">
          <div className="flex items-baseline gap-3">
            <span className="text-[11px] font-bold text-[var(--text-tertiary)]">POI 접근성 점수</span>
            <span className={`cc-num text-2xl font-black ${scoreColor(data.poi_accessibility_score ?? 0)}`}>
              {data.poi_accessibility_score ?? 0}
            </span>
            <span className="text-[11px] text-[var(--text-hint)]">/ 100 · 반경 {data.radius_m}m{data.geocoded_from ? ` · 좌표 ${data.geocoded_from}` : ""}</span>
          </div>
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-4">
            {Object.entries(data.categories ?? {}).map(([code, c]) => (
              <div key={code} className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1.5">
                <p className="text-[11px] font-bold text-[var(--text-primary)]">{c.label}</p>
                {c.unavailable ? (
                  <p className="text-[10px] text-[var(--text-tertiary)]">조회 불가</p>
                ) : (
                  <p className="text-[10px] text-[var(--text-secondary)]">
                    <b className="text-[var(--accent-strong)]">{c.count.toLocaleString()}</b>개
                    {c.nearest_m != null ? <span className="text-[var(--text-hint)]"> · 최근접 {c.nearest_m}m</span> : null}
                  </p>
                )}
              </div>
            ))}
          </div>
          <p className="text-[10px] text-[var(--text-hint)]">출처: Kakao Local 장소 카테고리 검색 · 좌표: VWorld 지오코딩</p>
        </div>
      )}
    </div>
  );
}