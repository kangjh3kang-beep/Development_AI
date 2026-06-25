"use client";

/**
 * SeniorConsultPanel — 시니어 전문가 자문(7도메인) 소비 UI.
 *
 * 설계: SeniorOrchestrator는 결정론 서버 오라클이다. DAG 노드(NodeId)가 아니라 도메인을 '소비'한다.
 * PersonaPanel과 동형으로 OrchestratorPanel 안의 별도 view 표면으로 분리(plan 엔진 무영향).
 *   - GET  /senior/agents   → 도메인 목록(고위험·성숙도)
 *   - POST /senior/consult  → 선택 도메인 자문(SeniorConsultation: 판단프레임워크·근거·신뢰도·정량판정)
 *
 * ★경계: 읽기 소비만(store 재기록 0). 결과는 로컬 state. 무목업(present만 렌더·미확보 정직표기).
 *   결정론·무과금. 정량 판정(evaluations)은 분석수치 연동 후 표시(v1은 판단 프레임워크 중심).
 * 색상은 토큰만(하드코딩 금지)·한국어.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { apiClient, ApiClientError } from "@/lib/api-client";

/* ── 백엔드 계약(읽기 전용 타입·to_dict 정합) ── */

interface SeniorAgentMeta {
  key: string;
  name_ko: string;
  high_risk: boolean;
  maturity: string;
  rule_count: number;
}

interface DecisionRuleView {
  rule_id: string;
  condition: string;
  judgment: string;
  basis: string;
  tradeoff: string;
  exception?: string;
  reasoning_blueprint?: string;
}

interface RuleEvaluationView {
  rule_id: string;
  label: string;
  value: number | null;
  unit: string;
  verdict: string; // PASS | WARN | BLOCK
  threshold: string;
  basis: string;
  detail: string;
}

interface SeniorConsultation {
  agent_key: string;
  name_ko: string;
  maturity: string;
  decision_framework: DecisionRuleView[];
  checklist: string[];
  risk_warnings: string[];
  confidence: number;
  confidence_label: string;
  needs_expert_review: boolean;
  high_risk: boolean;
  citations: string[];
  license_gate: string;
  honest_notes: string[];
  evaluations: RuleEvaluationView[];
  overall_verdict: string | null;
}

/* ── verdict/라벨 토큰 매핑(토큰만 — 하드코딩 색상 금지) ── */

const VERDICT_BADGE: Record<string, { label: string; token: string }> = {
  PASS: { label: "충족", token: "var(--status-success)" },
  WARN: { label: "경고", token: "var(--status-warning)" },
  BLOCK: { label: "차단", token: "var(--status-error)" },
};

function confidenceToken(label: string): string {
  if (label.includes("신뢰")) return "var(--status-success)";
  if (label.includes("보통")) return "var(--status-info)";
  return "var(--status-warning)"; // 참고(전문가 확인 필요)
}

function Badge({ token, children }: { token: string; children: React.ReactNode }) {
  return (
    <span
      className="rounded-full px-2 py-0.5 text-[10px] font-semibold"
      style={{
        color: token,
        background: `color-mix(in srgb, ${token} 14%, transparent)`,
        border: `1px solid color-mix(in srgb, ${token} 38%, transparent)`,
      }}
    >
      {children}
    </span>
  );
}

/* ── 메인 패널 ── */

// 시니어 자문은 도메인 단위 결정론(projectId 등 컨텍스트 불필요) — props 없음(자족 컴포넌트).
export function SeniorConsultPanel() {
  const [agents, setAgents] = useState<SeniorAgentMeta[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [result, setResult] = useState<SeniorConsultation | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const cacheRef = useRef<Record<string, SeniorConsultation>>({});

  // GET /senior/agents — 마운트 1회.
  useEffect(() => {
    let alive = true;
    apiClient
      .get<{ agents: SeniorAgentMeta[] }>("/senior/agents", { useMock: false })
      .then((r) => {
        if (!alive) return;
        setAgents(r?.agents ?? []);
      })
      .catch((e) => {
        if (!alive) return;
        setListError(
          e instanceof ApiClientError ? e.message : "시니어 에이전트 목록을 불러오지 못했습니다.",
        );
        setAgents([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  const consult = useCallback(async (key: string) => {
    setSelectedKey(key);
    setRunError(null);
    const cached = cacheRef.current[key];
    if (cached) {
      setResult(cached);
      return;
    }
    setRunning(true);
    try {
      const res = await apiClient.post<SeniorConsultation>("/senior/consult", {
        body: { domain: key },
        useMock: false,
      });
      cacheRef.current[key] = res;
      setResult(res);
    } catch (e) {
      setResult(null);
      setRunError(e instanceof ApiClientError ? e.message : "시니어 자문에 실패했습니다.");
    } finally {
      setRunning(false);
    }
  }, []);

  return (
    <section className="grid gap-3">
      <div className="rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
        <p className="mb-1 text-sm font-bold text-[var(--text-primary)]">시니어 전문가 자문</p>
        <p className="mb-3 text-[11px] text-[var(--text-secondary)]">
          7개 분야 시니어(설계·회계·세무·도시계획·심의·BIM·금융)의 판단 프레임워크와 근거를 제시합니다.
          분석 수치가 연동되면 항목별 PASS/경고/차단 판정을 함께 보여줍니다. AI 보조이며 최종 책임은 면허 전문가입니다.
        </p>

        {listError && <p className="mb-2 text-[11px] text-[var(--status-error)]">{listError}</p>}
        {agents === null && !listError && (
          <p className="text-[11px] text-[var(--text-tertiary)]">시니어 목록 불러오는 중…</p>
        )}
        {agents && agents.length > 0 && (
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {agents.map((a) => {
              const active = selectedKey === a.key;
              return (
                <button
                  key={a.key}
                  type="button"
                  onClick={() => consult(a.key)}
                  className={`rounded-xl border p-3 text-left transition-colors ${
                    active
                      ? "border-[var(--accent-strong)] bg-[color-mix(in_srgb,var(--accent-strong)_8%,transparent)]"
                      : "border-[var(--line-strong)] bg-[var(--surface-card)] hover:border-[var(--accent-strong)]"
                  }`}
                >
                  <span className="flex items-center justify-between gap-2">
                    <span className="text-sm font-bold text-[var(--text-primary)]">{a.name_ko}</span>
                    {a.high_risk && <Badge token="var(--status-warning)">고위험</Badge>}
                  </span>
                  <span className="mt-1 block text-[10px] text-[var(--text-tertiary)]">
                    판단규칙 {a.rule_count}개 · {a.maturity}
                  </span>
                </button>
              );
            })}
          </div>
        )}
        {running && (
          <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">시니어 자문 분석 중…</p>
        )}
        {runError && <p className="mt-2 text-[11px] text-[var(--status-error)]">{runError}</p>}
      </div>

      {result && (
        <div className="grid gap-3 rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-card)] p-4">
          {/* 헤더: 이름 + 성숙도 + 신뢰도 + 종합판정 */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-bold text-[var(--text-primary)]">{result.name_ko}</span>
              <Badge token="var(--text-tertiary)">{result.maturity}</Badge>
              {result.high_risk && <Badge token="var(--status-warning)">고위험 도메인</Badge>}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <Badge token={confidenceToken(result.confidence_label)}>
                신뢰도 {Math.round(result.confidence * 100)}% · {result.confidence_label}
              </Badge>
              {result.overall_verdict && VERDICT_BADGE[result.overall_verdict] && (
                <Badge token={VERDICT_BADGE[result.overall_verdict].token}>
                  종합 {VERDICT_BADGE[result.overall_verdict].label}
                </Badge>
              )}
            </div>
          </div>

          {/* 정량 판정(evaluations — 입력 연동 시·무목업으로 있을 때만) */}
          {result.evaluations && result.evaluations.length > 0 && (
            <div className="grid gap-1.5">
              <p className="text-xs font-bold text-[var(--text-primary)]">정량 판정</p>
              {result.evaluations.map((e) => {
                const badge = VERDICT_BADGE[e.verdict] ?? VERDICT_BADGE.WARN;
                return (
                  <div
                    key={e.rule_id}
                    className="flex items-start justify-between gap-2 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-soft)] px-3 py-2"
                  >
                    <div className="min-w-0">
                      <p className="text-[12px] font-semibold text-[var(--text-primary)]">
                        {e.label}
                        {e.value != null && (
                          <span className="ml-1 text-[var(--text-secondary)]">
                            {e.value}
                            {e.unit}
                          </span>
                        )}
                      </p>
                      <p className="text-[10px] text-[var(--text-tertiary)]">{e.detail}</p>
                      <p className="text-[10px] text-[var(--text-tertiary)]">기준 {e.threshold}</p>
                    </div>
                    <Badge token={badge.token}>{badge.label}</Badge>
                  </div>
                );
              })}
            </div>
          )}

          {/* 판단 프레임워크(decision_framework — 근거·트레이드오프 동반) */}
          {result.decision_framework && result.decision_framework.length > 0 && (
            <div className="grid gap-1.5">
              <p className="text-xs font-bold text-[var(--text-primary)]">판단 프레임워크(근거 동반)</p>
              {result.decision_framework.map((r) => (
                <div
                  key={r.rule_id}
                  className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-soft)] px-3 py-2"
                >
                  <p className="text-[12px] font-semibold text-[var(--text-primary)]">{r.judgment}</p>
                  <p className="mt-0.5 text-[10px] text-[var(--text-tertiary)]">근거: {r.basis}</p>
                  <p className="text-[10px] text-[var(--text-tertiary)]">트레이드오프: {r.tradeoff}</p>
                  {r.exception && (
                    <p className="text-[10px] text-[var(--text-tertiary)]">예외: {r.exception}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* 실패모드(시니어가 의심하는 리스크) */}
          {result.risk_warnings && result.risk_warnings.length > 0 && (
            <div className="rounded-xl border border-[color-mix(in_srgb,var(--status-warning)_30%,transparent)] bg-[color-mix(in_srgb,var(--status-warning)_8%,transparent)] p-3">
              <p className="mb-1 inline-flex items-center gap-1.5 text-[11px] font-bold text-[var(--status-warning)]">
                <AlertTriangle className="size-3.5" aria-hidden />
                주의 실패모드
              </p>
              <ul className="grid gap-0.5">
                {result.risk_warnings.map((w, i) => (
                  <li key={i} className="text-[11px] text-[var(--text-secondary)]">
                    · {w}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 정직 고지 */}
          {result.honest_notes && result.honest_notes.length > 0 && (
            <div className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-soft)] p-3">
              <p className="mb-1 text-[11px] font-bold text-[var(--text-primary)]">정직 고지</p>
              <ul className="grid gap-0.5">
                {result.honest_notes.map((n, i) => (
                  <li key={i} className="text-[11px] text-[var(--text-secondary)]">
                    · {n}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 근거(citations) */}
          {result.citations && result.citations.length > 0 && (
            <div className="grid gap-1">
              <p className="text-xs font-bold text-[var(--text-primary)]">근거 출처</p>
              <div className="flex flex-wrap gap-1.5">
                {result.citations.map((c, i) => (
                  <span
                    key={i}
                    className="rounded-full border border-[var(--line-strong)] bg-[var(--surface-card)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)]"
                  >
                    {c}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* 면허 책임 게이트 */}
          <p className="border-t border-[var(--line-strong)] pt-2 text-[10px] text-[var(--text-tertiary)]">
            {result.license_gate}
          </p>
        </div>
      )}
    </section>
  );
}
