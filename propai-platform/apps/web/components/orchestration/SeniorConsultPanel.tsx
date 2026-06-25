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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle } from "lucide-react";

import { apiClient, ApiClientError } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { buildSeniorInputs, type SeniorInputSources } from "@/lib/senior/build-inputs";
import {
  MANUAL_INPUTS,
  coerceManualInputs,
  hasManualInputs,
  mergeSeniorInputs,
  type ManualValueMap,
} from "@/lib/senior/manual-inputs";

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

interface IracStepView {
  rule_id: string;
  issue: string;
  rule: string;
  basis: string;
  application: string;
  conclusion: string;
}

interface SeniorReasoningView {
  mode: string; // structured | llm
  irac_steps: IracStepView[];
  debate: { pro: string; con: string } | null;
  debate_result?: { pro?: string; con?: string } | null; // 적대 debate 실행 결과(use_llm 시)
  prompt: string;
  narrative: string | null;
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
  reasoning: SeniorReasoningView | null;
}

/* ── verdict/라벨 토큰 매핑(토큰만 — 하드코딩 색상 금지) ── */

const VERDICT_BADGE: Record<string, { label: string; token: string }> = {
  PASS: { label: "충족", token: "var(--status-success)" },
  WARN: { label: "경고", token: "var(--status-warning)" },
  BLOCK: { label: "차단", token: "var(--status-error)" },
};

function confidenceToken(label: string | null | undefined): string {
  if (typeof label !== "string") return "var(--status-warning)"; // 누락 시 보수(참고)
  if (label.includes("신뢰")) return "var(--status-success)";
  if (label.includes("보통")) return "var(--status-info)";
  return "var(--status-warning)"; // 참고(전문가 확인 필요)
}

/** 안정 캐시키 — 키 삽입순서와 무관하게 정렬 직렬화(동일 inputs=동일 키). */
function seniorCacheKey(key: string, inputs: ManualValueMap | undefined): string {
  return `${key}|${inputs ? JSON.stringify(inputs, Object.keys(inputs).sort()) : ""}`;
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
  // ★읽기 소비만(store 쓰기 액션 미호출). 분석 데이터를 평가기 inputs로 자동 매핑한다.
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);
  const feasibilityData = useProjectContextStore((s) => s.feasibilityData);
  const sources = useMemo<SeniorInputSources>(
    () => ({ siteAnalysis, designData, feasibilityData }),
    [siteAnalysis, designData, feasibilityData],
  );

  const [agents, setAgents] = useState<SeniorAgentMeta[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [result, setResult] = useState<SeniorConsultation | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  // AI 종합 서술(LLM) 옵트인 — 기본 off(무과금·결정론). on 시 한도게이트(관리자 미설정=무료).
  const [useLlm, setUseLlm] = useState(false);
  // 수동 입력(전문 데이터) — 에이전트키 → 필드키 → 원문 문자열. 미입력은 빈문자열(=생략).
  //   ★무목업: store 자동산출 불가한 사용자 제공 사실(인수권리·동의율·건물감정가)을 '미입력'으로
  //   투명 표시하고, 입력되면 즉시 해당 정량 판정 활성. 비어있으면 평가기가 항목 생략(가정 0 금지).
  const [manualRaw, setManualRaw] = useState<Record<string, Record<string, string>>>({});
  // 캐시 키 = `${LLM여부}|${domain}|${inputs 시그니처}` — 입력/LLM옵션 바뀌면 재자문(stale 방지).
  const cacheRef = useRef<Record<string, SeniorConsultation>>({});
  // 현재 표시 결과의 캐시키(신선도 비교용) — store/수동 입력 변경 시 stale 안내.
  const [resultKey, setResultKey] = useState<string | null>(null);

  // store 자동매핑 + 수동 입력 병합(store 우선·SSOT). 없으면 undefined(프레임워크만).
  const mergedInputsFor = useCallback(
    (key: string): ManualValueMap | undefined =>
      mergeSeniorInputs(buildSeniorInputs(key, sources), coerceManualInputs(key, manualRaw[key])),
    [sources, manualRaw],
  );

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

  const consult = useCallback(
    async (key: string) => {
      setSelectedKey(key);
      setRunError(null);
      // store 자동매핑 + 수동 입력(전문 데이터) 병합(실재 값만·무목업). 없으면 프레임워크만.
      const inputs = mergedInputsFor(key);
      const cacheKey = `${useLlm ? "L" : "D"}|${seniorCacheKey(key, inputs)}`;
      const cached = cacheRef.current[cacheKey];
      if (cached) {
        setResult(cached);
        setResultKey(cacheKey);
        return;
      }
      setRunning(true);
      try {
        // FinCoT 추론(IRAC) 동반 요청 + 매핑된 정량 inputs(있으면) + AI 서술 옵트인.
        const context: { include_reasoning: true; inputs?: ManualValueMap } = {
          include_reasoning: true,
        };
        if (inputs) context.inputs = inputs;
        const body = { domain: key, context, use_llm: useLlm };
        const res = await apiClient.post<SeniorConsultation>("/senior/consult", {
          body,
          useMock: false,
        });
        cacheRef.current[cacheKey] = res;
        setResult(res);
        setResultKey(cacheKey);
      } catch (e) {
        setResult(null);
        setRunError(e instanceof ApiClientError ? e.message : "시니어 자문에 실패했습니다.");
      } finally {
        setRunning(false);
      }
    },
    [mergedInputsFor, useLlm],
  );

  // 표시 결과가 stale인가 — store·수동입력·LLM옵션이 바뀌어 현재 키가 표시 결과의 키와 다르면 true.
  // (자동 재실행 금지 정책 — 사용자에게 '다시 자문' 안내만 한다.)
  const stale = useMemo(() => {
    if (!selectedKey || !result || !resultKey) return false;
    const liveKey = `${useLlm ? "L" : "D"}|${seniorCacheKey(selectedKey, mergedInputsFor(selectedKey))}`;
    return liveKey !== resultKey;
  }, [selectedKey, result, resultKey, mergedInputsFor, useLlm]);

  return (
    <section className="grid gap-3">
      <div className="rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
        <p className="mb-1 text-sm font-bold text-[var(--text-primary)]">시니어 전문가 자문</p>
        <p className="mb-3 text-[11px] text-[var(--text-secondary)]">
          9개 분야 시니어(설계·회계·세무·도시계획·심의·BIM·금융·법무사·감정평가사)의 판단 프레임워크와 근거를 제시합니다.
          분석 수치가 연동되면 항목별 PASS/경고/차단 판정을 함께 보여줍니다. AI 보조이며 최종 책임은 면허 전문가입니다.
        </p>

        {/* AI 종합 서술 옵트인(기본 off·무과금). on 시 추론을 LLM이 자연어로 종합(관리자 미설정=무료). */}
        <label className="mb-3 flex w-fit cursor-pointer items-center gap-2 text-[11px] text-[var(--text-secondary)]">
          <input
            type="checkbox"
            checked={useLlm}
            onChange={(e) => setUseLlm(e.target.checked)}
            className="size-3.5 accent-[var(--accent-strong)]"
          />
          AI 종합 서술 포함(LLM) — 추론을 자연어로 종합. 미설정 시 무료·키 없으면 구조만 표시
        </label>

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

      {/* 추가 입력(전문 데이터) — store 자동산출 불가한 사용자 제공 사실(인수권리·동의율·건물감정가).
          ★무목업: 미입력은 '미입력'으로 투명 표시(가정 0 금지), 입력되면 즉시 정량 판정 활성. */}
      {selectedKey && hasManualInputs(selectedKey) && (
        <div className="rounded-[var(--radius-2xl)] border border-[var(--line-strong)] bg-[var(--surface-soft)] p-4">
          <p className="mb-1 text-xs font-bold text-[var(--text-primary)]">
            추가 입력 — 전문 데이터(미입력 시 해당 정량 판정 생략 · 입력 시 즉시 활성)
          </p>
          <p className="mb-3 text-[10px] text-[var(--text-tertiary)]">
            등기부 인수권리·조합 동의 현황·건물 감정가 등은 자동 수집 대상이 아닙니다. 값을 넣으면 인수율·동의율·종전평가
            판정이 바로 활성됩니다(없는 값을 가정하지 않는 무목업 원칙).
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            {MANUAL_INPUTS[selectedKey].map((f) => {
              const cur = manualRaw[selectedKey]?.[f.key] ?? "";
              const setVal = (val: string) =>
                setManualRaw((prev) => ({
                  ...prev,
                  [selectedKey]: { ...(prev[selectedKey] ?? {}), [f.key]: val },
                }));
              const selectOpts =
                f.kind === "boolean"
                  ? [
                      { value: "true", label: "예(동별 과반 충족)" },
                      { value: "false", label: "아니오" },
                    ]
                  : (f.options ?? []);
              return (
                <label key={f.key} className="grid min-w-0 gap-1">
                  <span className="text-[11px] font-semibold text-[var(--text-secondary)]">
                    {f.label}
                    {f.unit ? ` (${f.unit})` : ""}
                  </span>
                  {f.kind === "number" ? (
                    <input
                      type="number"
                      inputMode="decimal"
                      value={cur}
                      onChange={(e) => setVal(e.target.value)}
                      placeholder="미입력"
                      className="w-full min-w-0 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-card)] px-2.5 py-1.5 text-[12px] text-[var(--text-primary)]"
                    />
                  ) : (
                    <select
                      value={cur}
                      onChange={(e) => setVal(e.target.value)}
                      className="w-full min-w-0 rounded-lg border border-[var(--line-strong)] bg-[var(--surface-card)] px-2.5 py-1.5 text-[12px] text-[var(--text-primary)]"
                    >
                      <option value="">미입력</option>
                      {selectOpts.map((o) => (
                        <option key={o.value} value={o.value}>
                          {o.label}
                        </option>
                      ))}
                    </select>
                  )}
                  {f.hint && <span className="text-[10px] text-[var(--text-tertiary)]">{f.hint}</span>}
                </label>
              );
            })}
          </div>
          <button
            type="button"
            onClick={() => consult(selectedKey)}
            disabled={running}
            className="mt-3 rounded-lg border border-[var(--accent-strong)] bg-[color-mix(in_srgb,var(--accent-strong)_8%,transparent)] px-3 py-1.5 text-[11px] font-bold text-[var(--text-primary)] transition-colors hover:bg-[color-mix(in_srgb,var(--accent-strong)_14%,transparent)] disabled:opacity-50"
          >
            입력값으로 자문
          </button>
        </div>
      )}

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
              {/* 깨진 응답(confidence 누락) 방어 — 유한수일 때만 신뢰도 배지 렌더(NaN% 방지). */}
              {Number.isFinite(result.confidence) && (
                <Badge token={confidenceToken(result.confidence_label)}>
                  신뢰도 {Math.round(result.confidence * 100)}% · {result.confidence_label ?? "—"}
                </Badge>
              )}
              {result.overall_verdict && VERDICT_BADGE[result.overall_verdict] && (
                <Badge token={VERDICT_BADGE[result.overall_verdict].token}>
                  종합 {VERDICT_BADGE[result.overall_verdict].label}
                </Badge>
              )}
            </div>
          </div>

          {/* 신선도 안내 — 분석 데이터 변경 시 재자문 유도(자동 재실행 안 함). */}
          {stale && selectedKey && (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-[color-mix(in_srgb,var(--status-info)_36%,transparent)] bg-[color-mix(in_srgb,var(--status-info)_8%,transparent)] px-3 py-2">
              <span className="text-[11px] text-[var(--status-info)]">
                분석 데이터가 변경되었습니다 — 최신 수치로 다시 자문하세요.
              </span>
              <button
                type="button"
                onClick={() => consult(selectedKey)}
                disabled={running}
                className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-card)] px-2.5 py-1 text-[11px] font-bold text-[var(--text-primary)] transition-colors hover:border-[var(--accent-strong)] disabled:opacity-50"
              >
                다시 자문
              </button>
            </div>
          )}

          {/* 정량 판정(evaluations — 입력 연동 시·무목업으로 있을 때만) */}
          {result.evaluations && result.evaluations.length > 0 && (
            <div className="grid gap-1.5">
              <p className="text-xs font-bold text-[var(--text-primary)]">정량 판정</p>
              {result.evaluations.map((e) => {
                // 미지 verdict는 WARN으로 강등(BLOCK→WARN 오인) 대신 원문+중립색(정직).
                const badge = VERDICT_BADGE[e.verdict] ?? { label: e.verdict, token: "var(--text-tertiary)" };
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

          {/* FinCoT 추론(IRAC 체인) — include_reasoning 응답 시 */}
          {result.reasoning && result.reasoning.irac_steps.length > 0 && (
            <div className="grid gap-1.5">
              <p className="text-xs font-bold text-[var(--text-primary)]">
                추론 경로(IRAC)
                {result.reasoning.debate && (
                  <span className="ml-1.5 align-middle">
                    <Badge token="var(--status-info)">적대 검증 대상</Badge>
                  </span>
                )}
              </p>
              {/* LLM 서술(주입 시·없으면 결정론 구조만) */}
              {result.reasoning.narrative && (
                <p className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-soft)] px-3 py-2 text-[11px] text-[var(--text-secondary)]">
                  {result.reasoning.narrative}
                </p>
              )}
              <ol className="grid gap-1.5">
                {result.reasoning.irac_steps.map((s, i) => (
                  <li
                    key={s.rule_id}
                    className="rounded-lg border border-[var(--line-strong)] bg-[var(--surface-soft)] px-3 py-2"
                  >
                    <p className="text-[11px] font-semibold text-[var(--text-primary)]">
                      {i + 1}. 쟁점: {s.issue}
                    </p>
                    <p className="text-[10px] text-[var(--text-tertiary)]">규칙: {s.rule}</p>
                    <p className="text-[10px] text-[var(--text-tertiary)]">적용: {s.application}</p>
                    <p className="text-[10px] text-[var(--text-secondary)]">결론: {s.conclusion}</p>
                  </li>
                ))}
              </ol>
              {/* 적대 검증 결과(pro/con·use_llm 실행 시) */}
              {result.reasoning.debate_result &&
                (result.reasoning.debate_result.pro || result.reasoning.debate_result.con) && (
                  <div className="grid gap-1.5 sm:grid-cols-2">
                    {result.reasoning.debate_result.pro && (
                      <div className="rounded-lg border border-[color-mix(in_srgb,var(--status-success)_30%,transparent)] bg-[color-mix(in_srgb,var(--status-success)_6%,transparent)] px-3 py-2">
                        <p className="mb-0.5 text-[10px] font-bold text-[var(--status-success)]">적합 입장</p>
                        <p className="text-[10px] text-[var(--text-secondary)]">{result.reasoning.debate_result.pro}</p>
                      </div>
                    )}
                    {result.reasoning.debate_result.con && (
                      <div className="rounded-lg border border-[color-mix(in_srgb,var(--status-error)_30%,transparent)] bg-[color-mix(in_srgb,var(--status-error)_6%,transparent)] px-3 py-2">
                        <p className="mb-0.5 text-[10px] font-bold text-[var(--status-error)]">부적합/위험 입장</p>
                        <p className="text-[10px] text-[var(--text-secondary)]">{result.reasoning.debate_result.con}</p>
                      </div>
                    )}
                  </div>
                )}
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
