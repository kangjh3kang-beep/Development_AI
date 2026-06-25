"use client";

/**
 * D3 — 설계변경 사전예측 패널.
 *
 * 착공 전에 설계변경을 유발할 리스크(법규초과·필수요소 누락·정량 정합 모순)를
 * 미리 예측하고 보완방안(절감 포함)을 제시한다. 룰기반 우선, AI 보조(use_llm시).
 * POST /api/v1/design-risk/predict.
 *
 * 정직성: "사전예측·확정아님·전문가검토필요·3D clash 범위 외" 배지 항상 노출.
 */

import { useMemo, useState, type FormEvent } from "react";
import { ApiClientError, apiClient } from "@/lib/api-client";
import { useProjectContextStore } from "@/store/useProjectContextStore";
import { ProjectAddressInput } from "@/components/common/ProjectAddressInput";
import { NumberInput } from "@/components/common/NumberInput";
import type {
  DesignParamsInput,
  DesignRisk,
  DesignRiskPredictResponse,
} from "./types";

/* ── 카테고리/심각도 메타(의미색·토큰) ── */

const CATEGORY_META: Record<
  string,
  { label: string; cls: string; hint: string }
> = {
  법규초과: {
    label: "법규 초과",
    cls: "border-rose-500/30 bg-rose-500/10 text-rose-400",
    hint: "건폐율·용적률·높이 등 법정 한도를 넘었습니다.",
  },
  누락: {
    label: "필수 요소 누락",
    cls: "border-amber-500/30 bg-amber-500/10 text-amber-400",
    hint: "주차·계단·승강기 등 법정 필수 항목이 빠졌습니다.",
  },
  간섭정합: {
    label: "정합성 모순",
    cls: "border-violet-500/30 bg-violet-500/10 text-violet-300",
    hint: "면적·세대·높이 등 입력값 사이의 모순(정량 범위)입니다.",
  },
};

const SEVERITY_META: Record<
  string,
  { label: string; cls: string; icon: string }
> = {
  high: {
    label: "심각",
    cls: "border-rose-500/30 bg-rose-500/10 text-rose-400",
    icon: "●",
  },
  warn: {
    label: "주의",
    cls: "border-amber-500/30 bg-amber-500/10 text-amber-400",
    icon: "●",
  },
  info: {
    label: "참고",
    cls: "border-sky-500/30 bg-sky-500/10 text-sky-400",
    icon: "●",
  },
};

const CATEGORY_ORDER = ["법규초과", "누락", "간섭정합"] as const;
const SEVERITY_ORDER = ["high", "warn", "info"] as const;

function categoryMeta(key: string) {
  return (
    CATEGORY_META[key] ?? {
      label: key,
      cls: "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)]",
      hint: "",
    }
  );
}

function severityMeta(key: string) {
  return (
    SEVERITY_META[key] ?? {
      label: key,
      cls: "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)]",
      icon: "●",
    }
  );
}

function extractError(error: unknown): string {
  if (error instanceof ApiClientError) {
    if (error.status === 401 || error.status === 403) {
      return "분석을 위해 로그인이 필요합니다.";
    }
    return `API 요청 실패: 상태 ${error.status}`;
  }
  if (error instanceof Error) return error.message;
  return "설계변경 예측 요청에 실패했습니다.";
}

/* ── Component ── */

export function DesignChangePredictPanel({ projectId }: { projectId: string }) {
  const siteAnalysis = useProjectContextStore((s) => s.siteAnalysis);
  const designData = useProjectContextStore((s) => s.designData);

  const runtimeConfig = apiClient.getRuntimeConfig();
  const canUseLiveApi =
    runtimeConfig.mode === "live" || runtimeConfig.hasAccessToken;

  const [address, setAddress] = useState<string>(
    siteAnalysis?.address ?? "",
  );
  const [params, setParams] = useState<DesignParamsInput>(() => ({
    floors: designData?.floorCount ?? undefined,
    gfa: designData?.totalGfaSqm ?? undefined,
    bcr: designData?.bcr ?? undefined,
    far: designData?.far ?? undefined,
    height_m: undefined,
    parking: undefined,
    units: undefined,
  }));
  const [useLlm, setUseLlm] = useState(false);

  const [result, setResult] = useState<DesignRiskPredictResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>("");

  // 필터(선택)
  const [catFilter, setCatFilter] = useState<string | null>(null);
  const [sevFilter, setSevFilter] = useState<string | null>(null);

  function setParam(key: keyof DesignParamsInput, value: number | null) {
    setParams((prev) => ({ ...prev, [key]: value ?? undefined }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    const addr = address.trim();
    const pnu = siteAnalysis?.pnu ?? undefined;
    if (!addr && !pnu) {
      setError("주소(또는 부지분석 PNU)가 필요합니다.");
      return;
    }

    // 입력된 설계 파라미터만 전송(빈값 제외).
    const designParams: DesignParamsInput = {};
    (Object.keys(params) as (keyof DesignParamsInput)[]).forEach((k) => {
      const v = params[k];
      if (typeof v === "number" && Number.isFinite(v)) {
        designParams[k] = v;
      }
    });

    setLoading(true);
    try {
      const res = await apiClient.post<DesignRiskPredictResponse>(
        "/design-risk/predict",
        {
          useMock: false,
          body: {
            address: addr || undefined,
            pnu,
            project_id: projectId || undefined,
            design_params:
              Object.keys(designParams).length > 0 ? designParams : undefined,
            use_llm: useLlm,
          },
        },
      );
      setResult(res);
      setCatFilter(null);
      setSevFilter(null);
    } catch (err) {
      setError(extractError(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  const risks = useMemo<DesignRisk[]>(
    () => (result?.ok ? result.risks ?? [] : []),
    [result],
  );

  const filteredRisks = useMemo(
    () =>
      risks.filter(
        (r) =>
          (!catFilter || r.category === catFilter) &&
          (!sevFilter || r.severity === sevFilter),
      ),
    [risks, catFilter, sevFilter],
  );

  // 카테고리별 그룹(정렬 고정).
  const grouped = useMemo(() => {
    const groups: Record<string, DesignRisk[]> = {};
    for (const r of filteredRisks) {
      const key = String(r.category);
      (groups[key] ??= []).push(r);
    }
    const ordered: Array<[string, DesignRisk[]]> = [];
    for (const k of CATEGORY_ORDER) {
      if (groups[k]?.length) ordered.push([k, groups[k]]);
    }
    for (const k of Object.keys(groups)) {
      if (!CATEGORY_ORDER.includes(k as (typeof CATEGORY_ORDER)[number])) {
        ordered.push([k, groups[k]]);
      }
    }
    return ordered;
  }, [filteredRisks]);

  const summary = result?.ok ? result.summary : null;
  const aiRemedy = result?.ok ? result.ai_remedy : null;
  const okFalseError = result && !result.ok ? result.error : null;

  return (
    <section className="grid grid-cols-1 gap-6 min-w-0">
      {/* Header + Form */}
      <div className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-lg)]">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded-full bg-[var(--accent-soft)] px-4 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-[var(--accent-strong)]">
            설계변경 사전예측
          </span>
          <span className="rounded-full border border-[var(--line)] px-3 py-1 text-[10px] font-medium text-[var(--text-tertiary)]">
            {runtimeConfig.mode === "live" ? "LIVE" : "HYBRID"}
          </span>
        </div>
        <h3 className="mt-4 text-2xl font-bold text-[var(--text-primary)]">
          착공 전 설계변경 리스크 미리보기
        </h3>
        <p className="mt-2 max-w-3xl text-sm leading-7 text-[var(--text-secondary)]">
          법규 초과·필수요소 누락·정량 정합 모순을 사전에 잡아내고, 착공 전
          저비용으로 고치는 보완방안을 제시합니다. 착공 후 설계변경은 공사비·공기
          모두 크게 늘어납니다.
        </p>

        <form className="mt-5 grid gap-4" onSubmit={handleSubmit}>
          <ProjectAddressInput
            value={address}
            onChange={setAddress}
            label="주소 (필수)"
            placeholder="예) 서울특별시 강남구 테헤란로 152"
          />

          <details className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-4">
            <summary className="cursor-pointer text-sm font-semibold text-[var(--text-primary)]">
              설계 파라미터 (선택 — 입력 시 정밀 예측)
            </summary>
            <p className="mt-2 text-xs text-[var(--text-tertiary)]">
              부지분석·자동설계 값이 있으면 자동으로 채워집니다. 비워두면
              용도지역·층수 추정으로 보강합니다.
            </p>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <ParamField
                label="층수"
                value={params.floors}
                onChange={(n) => setParam("floors", n)}
              />
              <ParamField
                label="연면적 (㎡)"
                value={params.gfa}
                onChange={(n) => setParam("gfa", n)}
                allowDecimal
              />
              <ParamField
                label="건폐율 (%)"
                value={params.bcr}
                onChange={(n) => setParam("bcr", n)}
                allowDecimal
              />
              <ParamField
                label="용적률 (%)"
                value={params.far}
                onChange={(n) => setParam("far", n)}
                allowDecimal
              />
              <ParamField
                label="높이 (m)"
                value={params.height_m}
                onChange={(n) => setParam("height_m", n)}
                allowDecimal
              />
              <ParamField
                label="주차대수"
                value={params.parking}
                onChange={(n) => setParam("parking", n)}
              />
              <ParamField
                label="세대수"
                value={params.units}
                onChange={(n) => setParam("units", n)}
              />
            </div>
          </details>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex cursor-pointer items-center gap-2 text-sm text-[var(--text-secondary)]">
              <input
                type="checkbox"
                checked={useLlm}
                onChange={(e) => setUseLlm(e.target.checked)}
                className="h-4 w-4 accent-[var(--accent-strong)]"
              />
              AI 통합전략 포함 (느릴 수 있음)
            </label>
            <button
              type="submit"
              disabled={!canUseLiveApi || loading}
              className="rounded-[var(--radius-md)] bg-[var(--accent-strong)] px-6 py-2.5 text-sm font-bold text-white shadow-md transition-transform hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50"
            >
              {loading ? "예측 중..." : "설계변경 리스크 예측"}
            </button>
          </div>

          {!canUseLiveApi ? (
            <p className="rounded-[var(--radius-md)] border border-dashed border-[var(--line)] bg-[var(--surface-soft)] p-3 text-xs text-[var(--text-secondary)]">
              분석을 위해 로그인이 필요합니다.
            </p>
          ) : null}
          {error ? (
            <p className="rounded-[var(--radius-md)] border border-rose-500/30 bg-rose-500/10 p-3 text-sm text-rose-400">
              {error}
            </p>
          ) : null}
        </form>
      </div>

      {/* ok:false */}
      {okFalseError ? (
        <div className="rounded-[var(--radius-2xl)] border border-amber-500/30 bg-amber-500/10 p-6">
          <p className="text-sm font-semibold text-amber-400">예측 불가</p>
          <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
            {okFalseError}
          </p>
          {result?.badges?.note ? (
            <p className="mt-3 text-xs text-[var(--text-tertiary)]">
              {result.badges.note}
            </p>
          ) : null}
        </div>
      ) : null}

      {/* 결과 */}
      {result?.ok ? (
        <>
          {/* 요약 */}
          <div className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-strong)] p-6 shadow-[var(--shadow-lg)]">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h4 className="text-lg font-bold text-[var(--text-primary)]">
                예측 요약
              </h4>
              {result.zone_type ? (
                <span className="rounded-full border border-[var(--line)] px-3 py-1 text-xs text-[var(--text-secondary)]">
                  용도지역: {result.zone_type}
                </span>
              ) : null}
            </div>
            <div className="mt-4 flex flex-wrap gap-3">
              {SEVERITY_ORDER.map((sev) => {
                const meta = severityMeta(sev);
                const count = summary?.[sev] ?? 0;
                return (
                  <span
                    key={sev}
                    className={`flex items-center gap-2 rounded-full border px-4 py-1.5 text-sm font-bold ${meta.cls}`}
                  >
                    {meta.label} {count}건
                  </span>
                );
              })}
            </div>
            {summary?.total_predicted_impact_note ? (
              <p className="mt-4 rounded-[var(--radius-xl)] bg-[var(--surface-soft)] p-4 text-sm leading-7 text-[var(--text-secondary)]">
                {summary.total_predicted_impact_note}
              </p>
            ) : null}
          </div>

          {/* 필터 */}
          {risks.length > 0 ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--text-tertiary)]">
                필터
              </span>
              <FilterChip
                active={catFilter === null && sevFilter === null}
                onClick={() => {
                  setCatFilter(null);
                  setSevFilter(null);
                }}
                label="전체"
              />
              {CATEGORY_ORDER.filter((c) =>
                risks.some((r) => r.category === c),
              ).map((c) => (
                <FilterChip
                  key={`cat-${c}`}
                  active={catFilter === c}
                  onClick={() => setCatFilter(catFilter === c ? null : c)}
                  label={categoryMeta(c).label}
                />
              ))}
              {SEVERITY_ORDER.filter((s) =>
                risks.some((r) => r.severity === s),
              ).map((s) => (
                <FilterChip
                  key={`sev-${s}`}
                  active={sevFilter === s}
                  onClick={() => setSevFilter(sevFilter === s ? null : s)}
                  label={severityMeta(s).label}
                />
              ))}
            </div>
          ) : null}

          {/* 리스크 리스트(카테고리 그룹) */}
          {risks.length === 0 ? (
            <div className="rounded-[var(--radius-2xl)] border border-emerald-500/30 bg-emerald-500/10 p-6 text-sm leading-7 text-emerald-400">
              예측된 설계변경 리스크가 없습니다. (입력 범위 내 — 상세 설계 시 재검토
              권장)
            </div>
          ) : (
            <div className="grid gap-5">
              {grouped.map(([cat, items]) => {
                const meta = categoryMeta(cat);
                return (
                  <div key={cat} className="grid gap-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <span
                        className={`rounded-full border px-4 py-1.5 text-sm font-bold ${meta.cls}`}
                      >
                        {meta.label} · {items.length}건
                      </span>
                      {meta.hint ? (
                        <span className="text-xs text-[var(--text-tertiary)]">
                          {meta.hint}
                        </span>
                      ) : null}
                    </div>
                    <div className="grid gap-3">
                      {items.map((risk, i) => (
                        <RiskCard key={`${cat}-${i}`} risk={risk} />
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          {/* AI 통합전략 */}
          {aiRemedy ? (
            <div className="rounded-[var(--radius-2xl)] border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] p-6">
              <h4 className="text-lg font-bold text-[var(--accent-strong)]">
                AI 통합전략
              </h4>
              <div className="mt-4 grid gap-3">
                {aiRemedy.priority_actions ? (
                  <AiBlock
                    label="우선 조치"
                    value={aiRemedy.priority_actions}
                  />
                ) : null}
                {aiRemedy.savings_opportunity ? (
                  <AiBlock
                    label="절감 기회"
                    value={aiRemedy.savings_opportunity}
                  />
                ) : null}
                {aiRemedy.expert_review_note ? (
                  <AiBlock
                    label="전문가 검토 포인트"
                    value={aiRemedy.expert_review_note}
                  />
                ) : null}
              </div>
            </div>
          ) : null}

          {/* 정직성 배지 + 부족 데이터 */}
          <div className="rounded-[var(--radius-2xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-5">
            {result.badges?.note ? (
              <p className="flex items-start gap-2 text-xs leading-6 text-[var(--text-tertiary)]">
                <span aria-hidden>ⓘ</span>
                <span>{result.badges.note}</span>
              </p>
            ) : null}
            {result.badges?.data_basis ? (
              <p className="mt-1 text-xs text-[var(--text-tertiary)]">
                근거: {result.badges.data_basis}
              </p>
            ) : null}
            {result.data_gaps && result.data_gaps?.length > 0 ? (
              <div className="mt-3">
                <p className="text-xs font-semibold text-[var(--text-secondary)]">
                  부족·추정 데이터
                </p>
                <ul className="mt-1 list-disc pl-5 text-xs text-[var(--text-tertiary)]">
                  {(result.data_gaps ?? []).map((gap, i) => (
                    <li key={`gap-${i}`}>{gap}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {result.sources && result.sources?.length > 0 ? (
              <p className="mt-3 text-[10px] text-[var(--text-tertiary)]">
                출처: {result.sources.join(" · ")}
              </p>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}

/* ── Sub-components ── */

function ParamField({
  label,
  value,
  onChange,
  allowDecimal,
}: {
  label: string;
  value?: number;
  onChange: (n: number | null) => void;
  allowDecimal?: boolean;
}) {
  return (
    <label className="grid gap-1.5">
      <span className="text-xs font-medium text-[var(--text-secondary)]">
        {label}
      </span>
      <NumberInput
        value={value ?? null}
        onChange={onChange}
        allowDecimal={allowDecimal}
        placeholder={label}
        className="flex h-11 w-full rounded-[var(--radius-md)] border border-[var(--line)] bg-[var(--surface)] px-4 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--accent-strong)]"
      />
    </label>
  );
}

function RiskCard({ risk }: { risk: DesignRisk }) {
  const sev = severityMeta(String(risk.severity));
  return (
    <div className="rounded-[var(--radius-xl)] border border-[var(--line)] bg-[var(--surface-soft)] p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-bold text-[var(--text-primary)]">
            {risk.item}
          </p>
          {risk.current || risk.limit ? (
            <p className="mt-1 text-xs text-[var(--text-tertiary)]">
              {risk.current ? `현재 ${risk.current}` : ""}
              {risk.current && risk.limit ? " · " : ""}
              {risk.limit ? `한도 ${risk.limit}` : ""}
            </p>
          ) : null}
        </div>
        <span
          className={`shrink-0 rounded-full border px-3 py-1 text-[10px] font-bold ${sev.cls}`}
        >
          {sev.label}
        </span>
      </div>
      <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
        {risk.detail}
      </p>
      <div className="mt-3 rounded-[var(--radius-md)] border-l-2 border-[var(--accent-strong)] bg-[var(--surface)] p-3">
        <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--accent-strong)]">
          보완방안
        </p>
        <p className="mt-1 text-sm leading-7 text-[var(--text-primary)]">
          {risk.remedy}
        </p>
        {risk.est_impact ? (
          <p className="mt-2 text-xs text-[var(--text-tertiary)]">
            예상 영향(정성): {risk.est_impact}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function AiBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[var(--radius-md)] bg-[var(--surface-strong)] p-4">
      <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--accent-strong)]">
        {label}
      </p>
      <p className="mt-1 text-sm leading-7 text-[var(--text-secondary)] whitespace-pre-line">
        {value}
      </p>
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1 text-xs font-semibold transition-colors ${
        active
          ? "border-[var(--accent-strong)] bg-[var(--accent-soft)] text-[var(--accent-strong)]"
          : "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)] hover:border-[var(--accent-strong)]"
      }`}
    >
      {label}
    </button>
  );
}
