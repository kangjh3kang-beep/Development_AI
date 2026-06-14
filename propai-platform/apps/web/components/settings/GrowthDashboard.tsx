"use client";

/**
 * 자가성장 엔진 — 관리자 성장 분석 대시보드 (설계서 §5.2, Phase 2).
 *
 * GET  /growth/insights            → { items: GrowthInsight[], total } (관리자=전역 전체)
 * POST /growth/insights/{id}/ack   → { status: "acknowledged"|"dismissed", note? }
 *
 * 백엔드(apps/api/app/routers/growth.py)가 주기 배치로 platform_insights 를 산출하면
 * 이 화면이 소비한다. 무목업: 실 API만 사용하며, 수집/분석 데이터가 없으면 정직하게
 * "아직 축적 전"임을 표기한다(목업 금지). metrics_json 은 insight_type 별로 방어적
 * 렌더(필드가 없을 때 graceful)한다.
 */

import { useCallback, useEffect, useState } from "react";
import { Card, CardContent } from "@propai/ui";
import { apiClient, ApiClientError } from "@/lib/api-client";

/* ------------------------------------------------------------------ */
/*  백엔드 계약 (growth.py GrowthInsightOut 와 1:1)                     */
/* ------------------------------------------------------------------ */

type InsightSeverity = "info" | "warn" | "critical";

// 백엔드 enum 후보값(growth.py). 미래 신규 타입 대비해 string 도 수용한다.
type InsightStatus = "open" | "acknowledged" | "dismissed" | "acted" | (string & {});
type InsightType =
  | "error_cluster"
  | "fallback_rate"
  | "quality_drop"
  | "latency_regression"
  | "funnel"
  | "usage_pattern"
  | "churn_risk"
  | (string & {});

type GrowthInsight = {
  id: string;
  insight_type: InsightType;
  severity: string | null; // InsightSeverity | null
  status: InsightStatus;
  window_start: string | null;
  window_end: string | null;
  metrics_json: Record<string, unknown> | null;
  narrative: string | null;
  recommended_action: string | null;
  created_at: string | null;
};

type GrowthInsightList = { items: GrowthInsight[]; total: number };
type AckResult = { id: string; status: string };

/* ------------------------------------------------------------------ */
/*  표시 라벨·색상 (디자인 토큰 — 하드코딩 저대비 금지)                  */
/* ------------------------------------------------------------------ */

const TYPE_LABELS: Record<string, string> = {
  error_cluster: "오류 군집",
  fallback_rate: "폴백률",
  quality_drop: "품질 저하",
  latency_regression: "지연 회귀(p95)",
  funnel: "퍼널 이탈",
  usage_pattern: "사용 패턴",
  churn_risk: "이탈 위험",
};

const STATUS_LABELS: Record<string, string> = {
  open: "확인 필요",
  acknowledged: "확인됨",
  dismissed: "기각됨",
  acted: "조치됨",
};

const SEVERITY_LABELS: Record<string, string> = {
  critical: "심각",
  warn: "주의",
  info: "정보",
};

// severity → 토큰 기반 색상(테두리/배경/글자). 알 수 없는 값은 중립.
function severityClasses(severity: string | null): string {
  switch (severity) {
    case "critical":
      return "border-[rgba(220,38,38,0.4)] bg-[rgba(220,38,38,0.1)] text-[var(--status-error)]";
    case "warn":
      return "border-[rgba(217,119,6,0.4)] bg-[rgba(217,119,6,0.1)] text-[var(--spot)]";
    case "info":
      return "border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] text-[var(--accent-strong)]";
    default:
      return "border-[var(--line)] bg-[var(--surface-soft)] text-[var(--text-secondary)]";
  }
}

const SEVERITY_ORDER: InsightSeverity[] = ["critical", "warn", "info"];

/* ------------------------------------------------------------------ */
/*  metrics_json 방어적 헬퍼                                           */
/* ------------------------------------------------------------------ */

function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}
function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}
function pct(v: number | null): string {
  return v === null ? "-" : `${(v <= 1 ? v * 100 : v).toFixed(1)}%`;
}
function fmtDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

/* ------------------------------------------------------------------ */
/*  insight_type 별 metrics_json 렌더 (필드 없으면 graceful)            */
/* ------------------------------------------------------------------ */

function InsightMetrics({ insight }: { insight: GrowthInsight }) {
  const m = insight.metrics_json ?? {};
  const rows: { label: string; value: string }[] = [];

  switch (insight.insight_type) {
    case "fallback_rate": {
      // 백엔드 키(analyzer.py): service / fallback_pct / llm_call.
      const service = str(m.service);
      const rate = num(m.fallback_pct ?? m.fallback_rate ?? m.rate);
      const total = num(m.llm_call ?? m.total ?? m.count);
      if (service) rows.push({ label: "서비스", value: service });
      if (rate !== null) rows.push({ label: "폴백률", value: pct(rate) });
      if (total !== null) rows.push({ label: "호출 수", value: total.toLocaleString("ko-KR") });
      break;
    }
    case "error_cluster": {
      const route = str(m.route);
      const status = num(m.status_code ?? m.status);
      const count = num(m.count ?? m.errors);
      if (route) rows.push({ label: "경로", value: route });
      if (status !== null) rows.push({ label: "상태코드", value: String(status) });
      if (count !== null) rows.push({ label: "발생 수", value: count.toLocaleString("ko-KR") });
      break;
    }
    case "quality_drop": {
      // 백엔드 키(analyzer.py): service / fail_pct / down_pct.
      const service = str(m.service);
      const failPct = num(m.fail_pct);
      const downPct = num(m.down_pct);
      if (service) rows.push({ label: "서비스", value: service });
      if (failPct !== null) rows.push({ label: "검증 실패율", value: pct(failPct) });
      if (downPct !== null) rows.push({ label: "피드백 부정율", value: pct(downPct) });
      break;
    }
    case "latency_regression": {
      // 백엔드 키(analyzer.py): key(route|service) / p95_ms / prev_baseline_p95.
      const p95 = num(m.p95_ms ?? m.p95);
      const baseline = num(m.prev_baseline_p95 ?? m.baseline_ms ?? m.baseline);
      const key = str(m.key ?? m.route);
      if (key) rows.push({ label: "경로", value: key });
      if (p95 !== null) rows.push({ label: "p95 지연", value: `${Math.round(p95).toLocaleString("ko-KR")}ms` });
      if (baseline !== null) rows.push({ label: "기준선", value: `${Math.round(baseline).toLocaleString("ko-KR")}ms` });
      break;
    }
    case "funnel": {
      const step = str(m.step);
      const dropoff = num(m.dropoff_rate ?? m.dropoff);
      if (step) rows.push({ label: "단계", value: step });
      if (dropoff !== null) rows.push({ label: "이탈률", value: pct(dropoff) });
      break;
    }
    case "usage_pattern": {
      const pattern = str(m.pattern ?? m.label);
      const count = num(m.count);
      if (pattern) rows.push({ label: "패턴", value: pattern });
      if (count !== null) rows.push({ label: "빈도", value: count.toLocaleString("ko-KR") });
      break;
    }
    case "churn_risk": {
      const risk = num(m.risk_score ?? m.score);
      const segment = str(m.segment);
      if (segment) rows.push({ label: "세그먼트", value: segment });
      if (risk !== null) rows.push({ label: "위험도", value: pct(risk) });
      break;
    }
    default:
      break;
  }

  if (rows.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
      {rows.map((r) => (
        <span key={r.label} className="text-[var(--text-hint)]">
          {r.label}{" "}
          <span className="cc-num font-bold text-[var(--text-secondary)]">{r.value}</span>
        </span>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  메인 컴포넌트                                                       */
/* ------------------------------------------------------------------ */

export function GrowthDashboard() {
  const [insights, setInsights] = useState<GrowthInsight[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [authed, setAuthed] = useState(true);
  const [error, setError] = useState("");
  const [actingId, setActingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await apiClient.get<GrowthInsightList>(
        "/growth/insights?sort=severity&limit=200",
        { useMock: false },
      );
      setInsights(res.items ?? []);
      setTotal(res.total ?? 0);
      setAuthed(true);
    } catch (e) {
      if (e instanceof ApiClientError && (e.status === 401 || e.status === 403)) {
        setAuthed(false);
      } else {
        setError("성장 인사이트를 불러오지 못했습니다.");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // acknowledge / dismiss — 낙관적 갱신(실패 시 롤백).
  const ack = useCallback(
    async (id: string, status: "acknowledged" | "dismissed") => {
      const prev = insights;
      setActingId(id);
      setInsights((cur) => cur.map((it) => (it.id === id ? { ...it, status } : it)));
      try {
        await apiClient.post<AckResult>(`/growth/insights/${id}/ack`, {
          useMock: false,
          body: { status },
        });
      } catch {
        // 실패 시 원복하고 안내.
        setInsights(prev);
        setError("인사이트 상태 변경에 실패했습니다.");
      } finally {
        setActingId(null);
      }
    },
    [insights],
  );

  /* ---- 로딩 ---- */
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          {[1, 2, 3].map((n) => (
            <div key={n} className="h-28 animate-pulse rounded-2xl bg-[var(--surface-soft)]" />
          ))}
        </div>
        {[1, 2, 3].map((n) => (
          <div key={n} className="h-20 animate-pulse rounded-2xl bg-[var(--surface-soft)]" />
        ))}
      </div>
    );
  }

  /* ---- 권한 없음(401/403) ---- */
  if (!authed) {
    return (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-secondary)]">
        성장 분석은 플랫폼 총괄관리자만 열람할 수 있습니다.
      </div>
    );
  }

  /* ---- 오류 ---- */
  if (error && insights.length === 0) {
    return (
      <div className="rounded-2xl border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-8 text-center text-sm text-[var(--spot)]">
        {error}
      </div>
    );
  }

  /* ---- 파생 통계 ---- */
  const openInsights = insights.filter((it) => it.status === "open");
  const severityCounts: Record<InsightSeverity, number> = { critical: 0, warn: 0, info: 0 };
  for (const it of openInsights) {
    if (it.severity === "critical" || it.severity === "warn" || it.severity === "info") {
      severityCounts[it.severity] += 1;
    }
  }

  // 서비스별 폴백률(최신 fallback_rate 인사이트에서 집계).
  const fallbackRows = insights
    .filter((it) => it.insight_type === "fallback_rate")
    .map((it) => {
      const m = it.metrics_json ?? {};
      return {
        id: it.id,
        service: str(m.service) ?? "전체",
        rate: num(m.fallback_pct ?? m.fallback_rate ?? m.rate),
        severity: it.severity,
      };
    })
    .filter((r) => r.rate !== null)
    .sort((a, b) => (b.rate ?? 0) - (a.rate ?? 0))
    .slice(0, 8);

  // 오류 군집 top-N.
  const errorClusters = insights
    .filter((it) => it.insight_type === "error_cluster")
    .map((it) => {
      const m = it.metrics_json ?? {};
      return {
        id: it.id,
        route: str(m.route) ?? "-",
        status: num(m.status_code ?? m.status),
        count: num(m.count ?? m.errors) ?? 0,
        severity: it.severity,
      };
    })
    .sort((a, b) => b.count - a.count)
    .slice(0, 8);

  const hasAny = insights.length > 0;

  return (
    <div className="space-y-6">
      {/* 비치명 오류(목록은 있으나 ack 실패 등) 인라인 표기 */}
      {error && (
        <div className="rounded-xl border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] px-4 py-2.5 text-xs text-[var(--spot)]">
          {error}
        </div>
      )}

      {/* 요약 카드 — severity별 열린 인사이트 */}
      <div className="grid gap-4 sm:grid-cols-3">
        {SEVERITY_ORDER.map((sev) => (
          <div key={sev} className="cc-panel cc-bracketed">
            <div className="cc-grid-bg opacity-40" />
            <i className="cc-bracket cc-bracket--tl" />
            <i className="cc-bracket cc-bracket--br" />
            <div className="cc-panel__body relative z-10">
              <p className="cc-label">{SEVERITY_LABELS[sev]} · 열린 인사이트</p>
              <p
                className={`cc-num mt-3 text-3xl font-[900] ${
                  sev === "critical"
                    ? "text-[var(--status-error)]"
                    : sev === "warn"
                      ? "text-[var(--spot)]"
                      : "text-[var(--accent-strong)]"
                }`}
              >
                {severityCounts[sev]}
              </p>
            </div>
          </div>
        ))}
      </div>

      {/* 데이터 미축적 — 정직 표기(목업 금지) */}
      {!hasAny && (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-sm font-medium text-[var(--text-secondary)]">
              아직 수집·분석된 성장 인사이트가 없습니다.
            </p>
            <p className="mt-1.5 text-xs text-[var(--text-hint)]">
              Phase 1 텔레메트리가 배포되어 이벤트가 축적되고, 주기 배치 분석이 인사이트를
              산출하면 여기에 표시됩니다. (오류 군집·폴백률·품질 저하·지연 회귀·퍼널·이탈 위험)
            </p>
          </CardContent>
        </Card>
      )}

      {hasAny && (
        <>
          {/* 서비스별 폴백률 + 오류 군집 top-N */}
          {(fallbackRows.length > 0 || errorClusters.length > 0) && (
            <div className="grid gap-4 lg:grid-cols-2">
              {fallbackRows.length > 0 && (
                <Card>
                  <CardContent className="p-6">
                    <p className="cc-label">서비스별 폴백률</p>
                    <div className="mt-4 space-y-3">
                      {fallbackRows.map((r) => {
                        const display = (r.rate ?? 0) <= 1 ? (r.rate ?? 0) * 100 : (r.rate ?? 0);
                        return (
                          <div key={r.id} className="space-y-1">
                            <div className="flex items-center justify-between text-sm">
                              <span className="font-medium text-[var(--text-primary)]">{r.service}</span>
                              <span className="cc-num text-[var(--text-secondary)]">{display.toFixed(1)}%</span>
                            </div>
                            <div className="h-2 overflow-hidden rounded-full bg-[var(--surface-soft)]">
                              <div
                                className={`h-full rounded-full transition-all duration-500 ${
                                  r.severity === "critical"
                                    ? "bg-[var(--status-error)]"
                                    : r.severity === "warn"
                                      ? "bg-[var(--spot)]"
                                      : "bg-[var(--accent-strong)]"
                                }`}
                                style={{ width: `${Math.min(display, 100)}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </CardContent>
                </Card>
              )}

              {errorClusters.length > 0 && (
                <Card>
                  <CardContent className="p-6">
                    <p className="cc-label">오류 군집 (Top {errorClusters.length})</p>
                    <div className="mt-4 overflow-x-auto">
                      <table className="w-full text-sm">
                        <thead>
                          <tr className="text-left text-[10px] uppercase tracking-[0.12em] text-[var(--text-hint)]">
                            <th className="pb-2 font-bold">경로</th>
                            <th className="pb-2 font-bold">상태</th>
                            <th className="pb-2 text-right font-bold">발생 수</th>
                          </tr>
                        </thead>
                        <tbody>
                          {errorClusters.map((c) => (
                            <tr key={c.id} className="border-t border-[var(--line)]">
                              <td className="py-2 font-medium text-[var(--text-primary)] truncate max-w-[16rem]">{c.route}</td>
                              <td className="py-2 text-[var(--text-secondary)]">{c.status ?? "-"}</td>
                              <td className="py-2 text-right cc-num font-bold text-[var(--text-primary)]">
                                {c.count.toLocaleString("ko-KR")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </CardContent>
                </Card>
              )}
            </div>
          )}

          {/* 인사이트 목록 (severity 정렬 — 서버 sort=severity) */}
          <Card>
            <CardContent className="p-6">
              <div className="flex items-center justify-between">
                <p className="cc-label">인사이트 목록</p>
                <span className="text-xs text-[var(--text-hint)]">총 {total.toLocaleString("ko-KR")}건</span>
              </div>
              <div className="mt-4 space-y-3">
                {insights.map((it) => {
                  const isOpen = it.status === "open";
                  const busy = actingId === it.id;
                  return (
                    <div
                      key={it.id}
                      className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4"
                    >
                      <div className="flex flex-wrap items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span
                              className={`rounded-md border px-2 py-0.5 text-[11px] font-bold ${severityClasses(it.severity)}`}
                            >
                              {SEVERITY_LABELS[it.severity ?? ""] ?? it.severity ?? "미분류"}
                            </span>
                            <span className="text-sm font-bold text-[var(--text-primary)]">
                              {TYPE_LABELS[it.insight_type] ?? it.insight_type}
                            </span>
                            <span className="rounded-md bg-[var(--surface-muted)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-tertiary)]">
                              {STATUS_LABELS[it.status] ?? it.status}
                            </span>
                          </div>
                          {it.narrative && (
                            <p className="mt-2 text-sm text-[var(--text-secondary)]">{it.narrative}</p>
                          )}
                          <InsightMetrics insight={it} />
                          {it.recommended_action && (
                            <p className="mt-2 text-xs text-[var(--text-hint)]">
                              <span className="font-bold text-[var(--accent-strong)]">권장 조치</span>{" "}
                              {it.recommended_action}
                            </p>
                          )}
                          <p className="mt-2 text-[11px] text-[var(--text-hint)]">
                            <span className="cc-num">{fmtDate(it.created_at)}</span>
                            {(it.window_start || it.window_end) && (
                              <>
                                {" · 구간 "}
                                <span className="cc-num">
                                  {fmtDate(it.window_start)} ~ {fmtDate(it.window_end)}
                                </span>
                              </>
                            )}
                          </p>
                        </div>

                        {isOpen && (
                          <div className="flex shrink-0 gap-2">
                            <button
                              onClick={() => ack(it.id, "acknowledged")}
                              disabled={busy}
                              className="rounded-xl bg-[var(--accent-strong)] px-3 py-2 text-xs font-bold text-white transition-all hover:brightness-110 disabled:opacity-50"
                            >
                              {busy ? "처리 중…" : "확인"}
                            </button>
                            <button
                              onClick={() => ack(it.id, "dismissed")}
                              disabled={busy}
                              className="rounded-xl border border-[var(--line-strong)] bg-[var(--surface-muted)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)] transition-all hover:text-[var(--text-primary)] disabled:opacity-50"
                            >
                              기각
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
