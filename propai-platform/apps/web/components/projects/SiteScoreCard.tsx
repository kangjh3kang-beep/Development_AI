"use client";

/**
 * PropAI SiteScore — 설명가능 학습형 입지 점수(베팅 C).
 * 컨텍스트(부지 분석)를 /api/v1/site-score 로 보내 0~100 점수 + 피처별 기여도를 표시.
 * 1차 자가학습: 연구기반 사전가중(GIS-MCDA·15분도시). 데이터 누적 시 ML 학습으로 강화.
 */

import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { EvidencePanel, type EvidenceItem } from "@/components/common/EvidencePanel";
import { adaptEvidence, type BackendEvidence, type BackendLegalRef } from "@/lib/evidence/adaptEvidence";

type Factor = { key: string; name: string; raw: unknown; normalized: number; effective_weight: number; contribution: number; note: string };
type ScoreResult = {
  score: number | null; grade: string | null; factors: Factor[]; weight_basis?: string;
  covered?: number; total_features?: number; calibrated?: boolean; message?: string;
  // 백엔드가 evidence/legal_refs를 반환하면 우선 사용(있으면 그것 우선·없으면 factor 산식 트레이스로 폴백).
  evidence?: BackendEvidence[]; legal_refs?: BackendLegalRef[];
};

/**
 * 입지 점수 산출 근거(EvidencePanel) — 백엔드 evidence가 있으면 우선,
 * 없으면 응답 factor(가중치·정규화값·기여도)로 산식 트레이스를 만든다(가짜값/가짜URL 0).
 * 점수 = Σ(정규화값 × 가중치) → 지표별 기여도로 한 줄씩 근거를 보여준다.
 */
function buildSiteScoreEvidence(r: ScoreResult): EvidenceItem[] {
  const backend = adaptEvidence(r.evidence, r.legal_refs);
  if (backend.length > 0) return backend;

  const items: EvidenceItem[] = [];
  if (r.score != null) {
    items.push({
      label: "입지 총점",
      value: `${r.score}/100점${r.grade ? ` (${r.grade})` : ""}`,
      basis: `지표별 (정규화값 × 가중치) 기여도 합산${r.calibrated ? " · 지역보정 적용" : ""}`,
    });
  }
  // 지표별 기여도: 점수 = Σ(정규화값 × 가중치). 각 지표의 산식을 한 줄씩 보여준다.
  for (const f of r.factors ?? []) {
    if (!f || !f.name) continue;
    const weightPct = Math.round((f.effective_weight ?? 0) * 100);
    items.push({
      label: f.name,
      value: `+${f.contribution}점`,
      basis: `정규화 ${Math.round(f.normalized ?? 0)}점 × 가중치 ${weightPct}%${f.note ? ` · ${f.note}` : ""}`,
    });
  }
  if (r.weight_basis) {
    items.push({
      label: "가중치 근거",
      value: `${r.covered ?? "—"}/${r.total_features ?? "—"}개 지표`,
      basis: r.weight_basis,
    });
  }
  return items;
}

const GRADE_CLR: Record<string, string> = {
  "A+": "text-emerald-500", A: "text-emerald-500", "B+": "text-sky-500",
  B: "text-sky-500", C: "text-amber-500", D: "text-red-500",
};

export function SiteScoreCard() {
  const site = useProjectContextStore((s) => s.siteAnalysis);
  const [res, setRes] = useState<ScoreResult | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!site) { setRes(null); return; }
    const context: Record<string, unknown> = {
      zone_type: site.zoneCode ?? undefined,
      // ★단위 계약: official_price_per_sqm 은 '원/㎡'만 허용. estimatedValue 는 총액(원)이라
      //   폴백에 쓰면 단위 불일치(총액을 단가로 오입력)라 제거 — 단가 미확보 시 정직하게 undefined.
      official_price_per_sqm: site.officialPrices?.[0]?.pricePerSqm ?? undefined,
      infrastructure: site.infrastructure ?? undefined,
      pnu: site.pnu ?? undefined,
    };
    let cancelled = false;
    setLoading(true);
    apiClient.post<ScoreResult>("/site-score", { body: { context } })
      .then((r) => { if (!cancelled) setRes(r); })
      .catch(() => { if (!cancelled) setRes(null); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [site?.zoneCode, site?.pnu, site?.officialPrices?.[0]?.pricePerSqm]);

  if (!site) return null;
  if (loading && !res) return <div className="h-24 animate-pulse rounded-2xl bg-[var(--surface-soft)]" />;
  if (!res || res.score == null) return null;

  const gradeCls = GRADE_CLR[res.grade || "C"] || "text-[var(--text-primary)]";

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface)] p-5">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-bold text-[var(--text-primary)]" title="교통·학교·시세를 종합한 위치 점수(100점 만점)">입지 점수(100점)</h4>
          <p className="text-[11px] text-[var(--text-secondary)]">
            연구기반 1차 학습 가중 · {res.covered}/{res.total_features}개 지표{res.calibrated ? " · 지역보정" : ""}
          </p>
        </div>
        <div className="text-right">
          <span className={`text-3xl font-[1000] ${gradeCls}`}>{res.score}</span>
          <span className="ml-1 text-sm font-black text-[var(--text-secondary)]">/100</span>
          <span className={`ml-2 rounded-full bg-[var(--surface-soft)] px-2 py-0.5 text-xs font-black ${gradeCls}`}>{res.grade}</span>
        </div>
      </div>

      <div className="mt-4 space-y-2">
        {(res.factors ?? []).map((f) => (
          <div key={f.key}>
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-[var(--text-secondary)]">{f.name} <span className="text-[var(--text-tertiary)]">· {f.note}</span></span>
              <span className="font-bold text-[var(--text-primary)]">+{f.contribution}</span>
            </div>
            <div className="mt-1 h-1.5 w-full rounded-full bg-[var(--surface-soft)]">
              <div className="h-full rounded-full bg-[var(--accent-strong)]" style={{ width: `${Math.min(100, f.normalized)}%` }} />
            </div>
          </div>
        ))}
      </div>
      {res.weight_basis && <p className="mt-3 text-[10px] text-[var(--text-hint)]">{res.weight_basis}</p>}

      {/* 산출 근거(EvidencePanel) — 점수 = Σ(정규화값 × 가중치) 산식을 지표별로 한 줄씩.
          ★법령 URL은 백엔드 get_legal_refs 출력만(프론트 URL 조립 금지) — 미반환 시 basis 텍스트만. */}
      <EvidencePanel className="mt-3" items={buildSiteScoreEvidence(res)} title="입지 점수 산출 근거" />
    </div>
  );
}
