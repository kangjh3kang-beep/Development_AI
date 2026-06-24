"use client";

/**
 * 쉬운 규제안내서 카드 — GET /api/v1/permits/guide?facility_type=.
 * 시설물(건축물 용도)별 인허가 절차(계획·인허가 / 공사 / 사용·신고) + 관련법령(law.go.kr verified)
 * + 제출서류. 토지이음 '규제안내서'의 법령엔진 연계판. 주택류는 주택법 절차 추가.
 */

import { useEffect, useState } from "react";
import { FileText, ExternalLink, ChevronRight } from "lucide-react";
import { apiClient } from "@/lib/api-client";

type LegalRef = { key: string; law_name: string; article?: string | null; desc?: string; url?: string | null; url_status?: string };
type Stage = {
  stage: string; basic_desc: string[];
  procedures: { name: string; desc: string }[];
  legal_refs: LegalRef[]; documents: string[];
};
type Guide = { facility_type: string; group: string; stages: Stage[]; basis?: string; note?: string; error?: string };

const FACILITIES = [
  "단독주택", "다세대주택", "아파트", "연립주택",
  "제1종 근린생활시설", "제2종 근린생활시설", "업무시설", "판매시설", "공장",
];

export function PermitGuideCard({ defaultFacility = "단독주택" }: { defaultFacility?: string }) {
  const [facility, setFacility] = useState(defaultFacility);
  const [guide, setGuide] = useState<Guide | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    apiClient.get<Guide>(`/permits/guide?facility_type=${encodeURIComponent(facility)}`, { useMock: false })
      .then((g) => { if (alive) setGuide(g); })
      .catch(() => { if (alive) setGuide(null); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [facility]);

  return (
    <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="inline-flex items-center gap-1.5 text-sm font-black text-[var(--text-primary)]">
          <FileText className="size-4 text-[var(--accent-strong)]" aria-hidden /> 쉬운 규제안내서 · 인허가 절차
        </p>
        <select value={facility} onChange={(e) => setFacility(e.target.value)}
          className="rounded-lg border border-[var(--line)] bg-[var(--surface)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-primary)]">
          {FACILITIES.map((f) => <option key={f} value={f}>{f}</option>)}
        </select>
      </div>

      {loading && <p className="mt-3 text-xs text-[var(--text-hint)]">인허가 절차 로딩…</p>}
      {!loading && guide && !guide.error && (
        <>
          <div className="mt-3 space-y-2.5">
            {guide.stages.map((s, i) => (
              <div key={s.stage} className="rounded-xl border border-[var(--line)] bg-[var(--surface)] p-3">
                <p className="inline-flex items-center gap-1 text-xs font-black text-[var(--text-primary)]">
                  <span className="grid size-4 place-items-center rounded-full bg-[var(--accent-strong)] text-[10px] font-black text-white">{i + 1}</span>
                  {s.stage}
                </p>
                {/* 절차 */}
                <ul className="mt-1.5 space-y-1">
                  {s.procedures.map((p) => (
                    <li key={p.name} className="flex items-start gap-1 text-[11px] leading-relaxed text-[var(--text-secondary)]">
                      <ChevronRight className="mt-0.5 size-3 shrink-0 text-[var(--accent-strong)]" aria-hidden />
                      <span><b className="text-[var(--text-primary)]">{p.name}</b> — {p.desc}</span>
                    </li>
                  ))}
                </ul>
                {/* 관련 법령(verified 링크) */}
                {s.legal_refs.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {s.legal_refs.map((r) => {
                      const label = `${r.law_name}${r.article ? ` ${r.article}` : ""}`;
                      return r.url && r.url_status === "verified" ? (
                        <a key={r.key} href={r.url} target="_blank" rel="noopener noreferrer"
                          className="inline-flex items-center gap-0.5 rounded-md border border-[var(--accent-strong)]/30 bg-[var(--accent-strong)]/5 px-1.5 py-0.5 text-[10px] font-bold text-[var(--accent-strong)] hover:bg-[var(--accent-strong)]/10">
                          {label} <ExternalLink className="size-2.5" aria-hidden />
                        </a>
                      ) : (
                        <span key={r.key} className="rounded-md border border-[var(--line)] px-1.5 py-0.5 text-[10px] text-[var(--text-tertiary)]">{label}</span>
                      );
                    })}
                  </div>
                )}
                {/* 제출서류 */}
                {s.documents.length > 0 && (
                  <p className="mt-1.5 text-[10px] text-[var(--text-hint)]">제출서류: {s.documents.join(" · ")}</p>
                )}
              </div>
            ))}
          </div>
          {guide.note && <p className="mt-2 text-[10px] leading-relaxed text-[var(--text-hint)]">{guide.note}</p>}
        </>
      )}
    </div>
  );
}
