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
import { EvidencePanel } from "@/components/common/EvidencePanel";
import { adaptEvidence, type BackendEvidence, type BackendLegalRef } from "@/lib/evidence/adaptEvidence";

type Cat = { label: string; count: number; nearest_m: number | null; unavailable?: boolean };
type Resp = {
  available: boolean;
  reason?: string;
  radius_m?: number;
  poi_accessibility_score?: number;
  integrated_location_score?: number | null;
  score_basis?: string;
  transit_time?: { to?: string; driving_min?: number; distance_m?: number } | null;
  // 고속도로 접근성 대표값(선형 도로 → 최근접 IC/톨게이트 거리). 미가용 시 null(정직).
  highway_access?: { nearest_m?: number; via?: string; basis?: string } | null;
  categories?: Record<string, Cat>;
  geocoded_from?: string | null;
  coordinates?: { lat: number; lon: number };
  // 전역정책 Phase0: 근거·법령링크·신선도(백엔드 build_evidence_block 출력 — additive).
  evidence?: BackendEvidence[];
  legal_refs?: BackendLegalRef[];
  provenance?: { name?: string }[];
};

const RADII = [500, 1000, 2000];

// 카테고리 → 그룹 묶음(가독성). 카테고리가 많아져 그룹(교통/생활/공공/여가)으로 나눠 보여준다.
//   백엔드 신규 키워드그룹(KW_*) 포함. 미정의 코드는 '기타' 그룹으로 폴백(누락 없이 표시).
const POI_GROUPS: { key: string; label: string; codes: string[] }[] = [
  { key: "transit", label: "교통", codes: ["SW8", "KW_TRAINSTATION", "KW_BUSTERMINAL", "KW_HIGHWAY_IC", "KW_TOLLGATE"] },
  { key: "life", label: "생활", codes: ["MT1", "KW_DEPT", "CS2", "BK9", "HP8", "PM9", "FD6", "CE7"] },
  { key: "public", label: "공공·교육", codes: ["SC4", "AC5", "PO3", "KW_GOVOFFICE"] },
  { key: "leisure", label: "여가·문화", codes: ["PARK", "CT1", "KW_THEATER", "KW_GYM", "KW_GOLF", "AT4"] },
];

function scoreColor(s: number): string {
  if (s >= 80) return "text-emerald-400";
  if (s >= 60) return "text-[var(--accent-strong)]";
  if (s >= 40) return "text-amber-400";
  return "text-rose-400";
}

export function SiteInfraPoiCard({ address, context, className = "" }: { address?: string; context?: Record<string, unknown>; className?: string }) {
  const [radius, setRadius] = useState(1000);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [data, setData] = useState<Resp | null>(null);

  const run = useCallback(async (r: number) => {
    if (!address?.trim()) { setError("주소를 먼저 선택하세요."); return; }
    setLoading(true); setError(""); setData(null);
    try {
      const res = await apiClient.post<Resp>("/site-score/poi-infra", {
        body: { address: address.trim(), radius_m: r, ...(context ? { context } : {}) },
        useMock: false, timeoutMs: 40000,
      });
      setData(res);
    } catch {
      setError("입지 인프라 조회에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setLoading(false);
    }
  }, [address, context]);

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
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            {data.integrated_location_score != null && (
              <span className="flex items-baseline gap-1.5">
                <span className="text-[11px] font-bold text-[var(--text-tertiary)]">통합 입지점수</span>
                <span className={`cc-num text-2xl font-black ${scoreColor(data.integrated_location_score)}`}>{data.integrated_location_score}</span>
                <span className="text-[10px] text-[var(--text-hint)]">/100</span>
              </span>
            )}
            <span className="flex items-baseline gap-1.5">
              <span className="text-[11px] font-bold text-[var(--text-tertiary)]">POI 접근성</span>
              <span className={`cc-num text-xl font-black ${scoreColor(data.poi_accessibility_score ?? 0)}`}>{data.poi_accessibility_score ?? 0}</span>
            </span>
            {data.transit_time?.driving_min != null && (
              <span className="text-[11px] text-[var(--text-secondary)]">🚇 {data.transit_time.to} 차량 <b className="text-[var(--accent-strong)]">{data.transit_time.driving_min}분</b></span>
            )}
            {data.highway_access?.nearest_m != null && (
              <span className="text-[11px] text-[var(--text-secondary)]" title={data.highway_access.basis}>
                🛣 고속도로 {data.highway_access.via ?? "IC"} <b className="text-[var(--accent-strong)]">{data.highway_access.nearest_m.toLocaleString()}m</b>
              </span>
            )}
            <span className="text-[10px] text-[var(--text-hint)]">반경 {data.radius_m}m{data.geocoded_from ? ` · 좌표 ${data.geocoded_from}` : ""}{data.score_basis ? ` · ${data.score_basis}` : ""}</span>
          </div>

          {/* 카테고리를 그룹(교통/생활/공공·교육/여가·문화)으로 묶어 표시 — 카테고리가 많아져
              가독성 위해 그룹핑. 값 없는 카테고리(count 0·미조회)는 DataField 규칙대로 렌더하지 않는다
              ('—'/'분석 전' 금지). 조회 자체가 불가한 항목만 정직하게 '조회 불가'로 표기. */}
          {(() => {
            const cats = data.categories ?? {};
            const used = new Set<string>();
            const groups = POI_GROUPS.map((g) => {
              const entries = g.codes
                .map((code) => [code, cats[code]] as const)
                .filter(([code, c]) => {
                  if (!c) return false;
                  used.add(code);
                  return c.unavailable || c.count > 0; // 값 있거나 정직고지('조회 불가')만 표시
                });
              return { ...g, entries };
            });
            // 그룹에 안 잡힌 잔여 카테고리는 '기타'로 폴백(누락 없이 광범위 표시).
            const rest = Object.entries(cats).filter(
              ([code, c]) => !used.has(code) && c && (c.unavailable || c.count > 0),
            );
            const all = rest.length > 0 ? [...groups, { key: "etc", label: "기타", codes: [], entries: rest }] : groups;
            return (
              <div className="space-y-3">
                {all.filter((g) => g.entries.length > 0).map((g) => (
                  <div key={g.key}>
                    <p className="mb-1 text-[10px] font-black uppercase tracking-widest text-[var(--text-hint)]">{g.label}</p>
                    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-4">
                      {g.entries.map(([code, c]) => (
                        <div key={code} className="rounded-lg border border-[var(--line)] bg-[var(--surface-strong)] px-2.5 py-1.5">
                          <p className="text-[11px] font-bold text-[var(--text-primary)]">{c!.label}</p>
                          {c!.unavailable ? (
                            <p className="text-[10px] text-[var(--text-tertiary)]">조회 불가</p>
                          ) : (
                            <p className="text-[10px] text-[var(--text-secondary)]">
                              <b className="text-[var(--accent-strong)]">{c!.count.toLocaleString()}</b>개
                              {c!.nearest_m != null ? <span className="text-[var(--text-hint)]"> · 최근접 {c!.nearest_m}m</span> : null}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            );
          })()}
          <p className="text-[10px] text-[var(--text-hint)]">출처: Kakao Local 장소 카테고리 검색 · 좌표: VWorld 지오코딩</p>

          {/* 산출 근거 + 법령 원문(EvidencePanel) — adaptEvidence로 legal_ref_key 조인.
              url_status=pending이면 LegalRefChip이 텍스트 폴백(가짜 링크 0). */}
          {(() => {
            const items = adaptEvidence(data.evidence, data.legal_refs);
            return items.length > 0 ? <EvidencePanel items={items} title="입지점수 산출 근거" /> : null;
          })()}
        </div>
      )}
    </div>
  );
}