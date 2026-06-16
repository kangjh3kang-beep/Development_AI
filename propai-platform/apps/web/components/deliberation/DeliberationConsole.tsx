"use client";

/**
 * 심의분석 라이브 콘솔 — 플랫폼 프런트 ↔ 심의분석 엔진(propai-review) /analyze 배선.
 *
 * 원시 입력(JSON) → 엔진 11계층 분석 → 구획 보고서/판정/공학지표/유사사례/정성 렌더.
 * 엔진 URL은 NEXT_PUBLIC_DELIBERATION_ENGINE_URL(기본 http://localhost:8801). 미연결 시 정직 안내.
 */

import { useState } from "react";

// || (??가 아니라) — 빈 문자열/미설정 모두 기본값으로. 항상 절대 URL이어야 fetch 파싱 가능.
const ENGINE_URL =
  process.env.NEXT_PUBLIC_DELIBERATION_ENGINE_URL || "http://localhost:8801";

type Finding = {
  rule_id: string;
  verdict: string;
  measured_value: number | null;
  limit_value: number | null;
  basis_article: string | null;
  requires_committee: boolean;
};
type SimMetric = {
  metric_id: string;
  value: number | null;
  unit: string;
  status: string;
  flags: string[];
};
type Qual = { item: string | null; status: string; grade: string | null; citation: { rubric_item: string } | null };
type AnalysisResult = {
  input_hash: string;
  snapshot_id: string;
  preflight: { blocked: boolean; assumed_fields: string[] } | null;
  legal_quantities: { variable_id: string; value: number | null; status: string }[];
  findings: Finding[];
  sim_metrics: SimMetric[];
  precedent: { status: string; n: number; distribution: Record<string, number> | null } | null;
  qualitative: Qual[];
  report: { sections: Record<string, { item_id: string }[]> };
  skipped: string[];
};

const SAMPLE = {
  pnu: "1111010100100000002",
  application_date: "2026-01-01",
  axis_date: "2026-01-01",
  drawing: { scale_text: "1:100" },
  calc_targets: [
    {
      target: "building_area",
      payload: { outer_area: 600.0 },
      elements: [{ semantic_type: "PILOTIS", area: 100.0, confidence: 0.95 }],
    },
  ],
  rules: [
    {
      rule: {
        rule_id: "far_limit",
        comparator: "<=",
        basis_article: "국토계획법 시행령",
        relaxations: [{ relaxation_id: "far_relax", prerequisite_rule_id: "public_space" }],
      },
      measured: 250.0,
      limit: 200.0,
      relaxation_states: { public_space: "MET" },
      confidence: 0.9,
    },
    {
      rule: { rule_id: "height_limit", comparator: "<=", basis_article: "건축법 시행령" },
      measured: 30.0,
      limit: 20.0,
      confidence: 0.9,
    },
  ],
  sim_inputs: {
    sunlight: { latitude: 37.5, building_height: 30.0, adjacent_distance: 12.0, geom_confidence: 0.9 },
    parking: { turn_radius: 5.0, geom_confidence: 0.9 },
  },
  issue: "FAR_DISPUTE",
  corpus: Array.from({ length: 6 }, (_, i) => ({
    case_id: "c" + i,
    source: "의결서-" + i,
    decision_type: i === 2 ? "APPROVED" : "CONDITIONAL",
    issue_labels: ["FAR_DISPUTE"],
    conditions: ["공개공지 확대"],
  })),
  mirror_rules: [{ ref: "건축법 시행령", effective_date: "2025-01-01" }],
  citations: [{ ref: "건축법 시행령" }],
  qual_facts: [
    { feature: "경관조화", candidate_rubric: "경관 심의기준 3.1", mapping_confidence: 0.9, compatibility: 0.8, criterion_exists: true },
  ],
};

const STATUS_CLASS: Record<string, string> = {
  CONFIRMED: "var(--status-success)",
  COMPLIANT: "var(--status-success)",
  NEEDS_REVIEW: "var(--status-warning)",
  CONDITIONAL: "var(--status-warning)",
  BLOCKED: "var(--status-error)",
  NON_COMPLIANT: "var(--status-error)",
};

function Tag({ value }: { value: string }) {
  const color = STATUS_CLASS[value] ?? "var(--text-tertiary)";
  return (
    <span
      className="rounded-full border px-2 py-0.5 text-[11px] font-bold"
      style={{ color, borderColor: color }}
    >
      {value}
    </span>
  );
}

export function DeliberationConsole() {
  const [input, setInput] = useState(JSON.stringify(SAMPLE, null, 2));
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [ms, setMs] = useState<number | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    let body: unknown;
    try {
      body = JSON.parse(input);
    } catch (e) {
      setError("입력 JSON 파싱 오류: " + (e as Error).message);
      setLoading(false);
      return;
    }
    try {
      const t0 = performance.now();
      const res = await fetch(`${ENGINE_URL}/api/v1/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      setMs(Math.round(performance.now() - t0));
      if (!res.ok) {
        setError(`HTTP ${res.status}: ${await res.text()}`);
      } else {
        setResult((await res.json()) as AnalysisResult);
      }
    } catch (e) {
      setError(
        `엔진 미연결(${ENGINE_URL}). 엔진을 먼저 구동하세요 — propai-review에서 ` +
          `uvicorn app.main:app --port 8801. (${(e as Error).message})`,
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="cc-panel cc-bracketed relative overflow-hidden rounded-[var(--radius-2xl)] p-6">
      <i className="cc-bracket cc-bracket--tl" />
      <i className="cc-bracket cc-bracket--tr" />
      <i className="cc-bracket cc-bracket--bl" />
      <i className="cc-bracket cc-bracket--br" />
      <div className="relative z-10 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-black text-[var(--text-primary)]">라이브 심의분석 콘솔</h2>
        <span className="cc-meta text-[var(--text-tertiary)]">ENGINE · {ENGINE_URL}</span>
      </div>
      <p className="relative z-10 mt-1 text-xs text-[var(--text-secondary)]">
        원시 입력 → 엔진 11계층(Preflight·법정산정·판정·공학시뮬·유사사례·검증·정성·게이팅·리포트) → 구획 보고서.
        결정론·근거추적·무음 오판 0.
      </p>

      <div className="relative z-10 mt-4 grid gap-4 lg:grid-cols-2">
        <div>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            spellCheck={false}
            className="h-72 w-full rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-3 font-mono text-[11px] text-[var(--text-primary)]"
          />
          <div className="mt-2 flex items-center gap-3">
            <button
              onClick={run}
              disabled={loading}
              className="rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-sm font-black text-white disabled:opacity-50"
            >
              {loading ? "분석 중…" : "심의분석 실행"}
            </button>
            <button
              onClick={() => setInput(JSON.stringify(SAMPLE, null, 2))}
              className="rounded-xl border border-[var(--line)] px-3 py-2 text-xs text-[var(--text-secondary)]"
            >
              샘플 복원
            </button>
            {ms !== null && !error && <span className="text-xs text-[var(--text-tertiary)]">완료 {ms}ms</span>}
          </div>
        </div>

        <div className="min-h-72 rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-3 text-sm">
          {error && <p className="whitespace-pre-wrap text-xs text-[var(--status-error)]">{error}</p>}
          {!error && !result && <p className="text-xs text-[var(--text-tertiary)]">분석을 실행하면 결과가 표시됩니다.</p>}
          {result && (
            <div className="space-y-3">
              <div className="text-[11px] text-[var(--text-tertiary)]">
                input_hash <code className="text-[var(--accent-strong)]">{result.input_hash.slice(0, 16)}…</code> · snapshot {result.snapshot_id}
              </div>
              <div>
                <div className="cc-label text-[var(--text-tertiary)]">최종 구획(L5/L6)</div>
                {Object.entries(result.report.sections)
                  .filter(([, v]) => v.length)
                  .map(([k, v]) => (
                    <div key={k} className="mt-1 flex items-center gap-2">
                      <Tag value={k} />
                      <span className="text-xs text-[var(--text-secondary)]">{v.map((i) => i.item_id).join(", ")}</span>
                    </div>
                  ))}
              </div>
              <div>
                <div className="cc-label text-[var(--text-tertiary)]">판정(R3)</div>
                {result.findings.map((f) => (
                  <div key={f.rule_id} className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                    <span className="font-semibold text-[var(--text-primary)]">{f.rule_id}</span>
                    <Tag value={f.verdict} />
                    <span className="text-[var(--text-tertiary)]">
                      {f.measured_value ?? "-"}/{f.limit_value ?? "-"} · {f.basis_article ?? "-"}
                      {f.requires_committee ? " · 위원확인" : ""}
                    </span>
                  </div>
                ))}
              </div>
              <div>
                <div className="cc-label text-[var(--text-tertiary)]">공학지표(L3-B)</div>
                {result.sim_metrics.map((m) => (
                  <div key={m.metric_id} className="mt-1 flex flex-wrap items-center gap-2 text-xs">
                    <span className="text-[var(--text-secondary)]">{m.metric_id}</span>
                    <span className="text-[var(--text-primary)]">{m.value ?? "-"} {m.unit}</span>
                    {m.flags.map((fl) => (
                      <Tag key={fl} value={fl} />
                    ))}
                  </div>
                ))}
              </div>
              <div className="text-xs text-[var(--text-secondary)]">
                <span className="cc-label text-[var(--text-tertiary)]">유사사례(L4)</span>{" "}
                {result.precedent ? (
                  <>
                    <Tag value={result.precedent.status} /> n={result.precedent.n}{" "}
                    {JSON.stringify(result.precedent.distribution ?? {})}
                  </>
                ) : (
                  "없음"
                )}
              </div>
              <div className="text-xs text-[var(--text-secondary)]">
                <span className="cc-label text-[var(--text-tertiary)]">정성(L3-C)</span>{" "}
                {result.qualitative.map((q) => (
                  <span key={q.item ?? Math.random()} className="mr-2">
                    {q.item} <Tag value={q.status} /> {q.grade}
                  </span>
                ))}
              </div>
              {result.skipped.length > 0 && (
                <div className="text-[11px] text-[var(--text-tertiary)]">미수행 계층: {result.skipped.join(" · ")}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
