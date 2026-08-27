"use client";

/**
 * 자가성장 엔진 — 관리자 성장 분석 대시보드 (설계서 §5.2, Phase 2).
 *
 * GET  /growth/insights            → { items: GrowthInsight[], total } (관리자=전역 전체)
 * POST /growth/insights/{id}/ack   → { status: "acknowledged"|"dismissed", note? }
 *
 * [Phase 3 추가] 자가치유 현황(설계서 §6.1):
 * GET  /growth/heal-log            → { actions: HealAction[], active_flags: ActiveFlag[], total }
 * POST /growth/heal/{id}/rollback  → { action_id, rolled_back, setting_key, detail }
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
/**
 * ★백엔드 카탈로그(`apps/api/app/services/growth/insight_types.py`)와 **1:1**.
 *
 * 종전엔 이 목록이 7종이었는데 백엔드는 **11종**을 내보내고 있었고, 그 7종 중
 * `funnel`·`usage_pattern`·`churn_risk` **3종은 백엔드가 한 번도 안 내보내는 유령**이었다.
 * 결과: **7종이 라벨 없이 raw 문자열**로 떴다 — 그중 `heal_escalation` 은
 * *"자동치유가 반복 발화했는데 효과가 없다 · 사람 점검 필요"* 라는 **critical** 이다.
 * (규율 §A-4 — 사람이 센 목록이 곧 상한이 된다. 실제로 목록 7 vs 실제 11.)
 *
 * 두 목록이 다시 갈라지면 `GrowthDashboard.catalog.test.ts` 가 잡는다.
 */
type InsightType =
  | "error_cluster"
  | "fallback_rate"
  | "quality_drop"
  | "recurring_verify_error"
  | "latency_regression"
  | "latency_baseline"
  | "selection_contamination"
  | "stale_reanalysis"
  | "heal_escalation"
  | "improvement_proposal"
  | "prompt_candidate"
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

type GrowthInsightList = {
  items: GrowthInsight[];
  total: number;
  /** severity → 건수. **서버가 필터 전체에 대해** 센 값(조치대상만·비조치 타입 제외).
   *  ★`items` 는 `limit` 으로 잘리지만 이 값은 **안 잘린다** — 그래서 집계는 이것을 쓴다. */
  actionable_counts?: Partial<Record<InsightSeverity, number>>;
};
type AckResult = { id: string; status: string };

/* ------------------------------------------------------------------ */
/*  표시 라벨·색상 (디자인 토큰 — 하드코딩 저대비 금지)                  */
/* ------------------------------------------------------------------ */

const TYPE_LABELS: Record<string, string> = {
  error_cluster: "오류 군집",
  fallback_rate: "폴백률",
  quality_drop: "품질 저하",
  recurring_verify_error: "검증오류 재발",
  latency_regression: "지연 회귀(p95)",
  latency_baseline: "지연 기준선(기록)",
  selection_contamination: "선택 오염 관측",
  stale_reanalysis: "재분석 제안",
  heal_escalation: "자동치유 무효(사람 점검)",
  improvement_proposal: "개선 제안",
  prompt_candidate: "프롬프트 후보",
};

/**
 * **조치 대상이 아닌** 타입 — "확인 필요"로 세면 진짜 신호가 묻힌다.
 * ★`latency_baseline` 은 회귀가 **아닌** 기록이다(2026-08-23 에 2,059건이 쌓여
 *   실제 조치 대상 critical 57 + warn 352 를 가렸다).
 */
const NON_ACTIONABLE_TYPES = new Set(["latency_baseline"]);

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
      return "border-[rgba(217,119,6,0.4)] bg-[rgba(217,119,6,0.1)] text-[var(--status-warning)]";
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
/**
 * LLM 실패 **사유 코드 → 한글**.
 *
 * 원천은 백엔드 `app/services/ai/llm_failure.py` 의 `classify_failure` 가 내는 값이고,
 * `unlabeled` 은 `analyzer.py` 가 **사유가 안 실린 이벤트**에 붙이는 값이다.
 * 갈리면 `GrowthDashboard.catalog.test.ts` 의 사유 라벨 축이 잡는다 — 라벨이 없으면
 * #808 과 **같은 얼굴**(영문 raw 노출)이 된다.
 *
 * ★모르는 코드는 **감추지 않고 원문 그대로** 보여준다. 숨기면 분포 합이 틀어지고,
 *   "새 실패 유형이 생겼다"는 가장 중요한 신호가 조용히 사라진다.
 */
const REASON_LABELS: Record<string, string> = {
  timeout: "타임아웃",
  parse: "응답 파싱 실패",
  shape: "구조 불일치",
  network: "네트워크",
  rate_limit: "호출 한도",
  overloaded: "공급자 과부하",
  auth: "인증·잔액",
  content_filter: "정책 거부",
  bad_request: "요청 거부",
  other: "그 외",
  // ★"미분류"는 그 자체가 결함 신호다 — 쓰기 경로가 사유를 안 싣고 있다는 뜻이라,
  //   감추거나 0으로 뭉개면 "사유가 도착했다"는 착시가 생긴다.
  unlabeled: "사유 미분류(계측 누락)",
};

function reasonLabel(code: string): string {
  return REASON_LABELS[code] ?? code;
}

/** `{timeout: 12, parse: 6}` → `"타임아웃 12 · 응답 파싱 실패 6"`(많은 순 · 상위 N + 나머지 종수). */
function fmtReasons(v: unknown, top = 4): string | null {
  if (!v || typeof v !== "object" || Array.isArray(v)) return null;
  const pairs = Object.entries(v as Record<string, unknown>)
    .map(([k, n]) => [k, typeof n === "number" && Number.isFinite(n) ? n : 0] as const)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  if (pairs.length === 0) return null;
  const head = pairs.slice(0, top).map(([k, n]) => `${reasonLabel(k)} ${n.toLocaleString("ko-KR")}`);
  // ★잘라낸 몫을 **말한다** — 안 적으면 상위 N 종이 전부인 줄로 읽는다(묵시적 상한 금지).
  const rest = pairs.length - head.length;
  return rest > 0 ? `${head.join(" · ")} 외 ${rest}종` : head.join(" · ");
}

function fmtDate(iso: string | null): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "-" : d.toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}

/* ------------------------------------------------------------------ */
/*  insight_type 별 metrics_json 렌더 (필드 없으면 graceful)            */
/* ------------------------------------------------------------------ */

/**
 * ★테스트를 위해 내보낸다(소비처는 이 파일 안뿐).
 *
 * 왜: 이 함수의 실패 형태는 **"case 는 있는데 rows 가 비어 `null` 을 반환"** 이라,
 * 소스에서 `case "x":` 존재만 검사하면 **초록으로 통과한다**(실제로 `improvement_proposal`
 * 이 그 상태였다 — 2026-08-25). 렌더 결과를 봐야만 잡힌다(규율 §A-1·A-3).
 */
export function InsightMetrics({ insight }: { insight: GrowthInsight }) {
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
      // ★이 두 줄이 이 카드의 **존재 이유**다. "폴백률 80.77%" 만으로는 절단인지 스키마
      //   위반인지 인증·잔액인지 모르고, 그 셋은 처방이 전혀 다르다.
      //   ★`fallback`·`signature` 등 다른 백엔드 키를 여기 더하지 않은 것은 의도다 —
      //     `_rule_narrative`(analyzer.py)가 이미 산문으로 말하고 그 문장은 이 카드 바로
      //     아래에 렌더된다(:1040). 같은 값을 두 번 적으면 카드만 길어진다.
      const top = str(m.top_reason);
      if (top) rows.push({ label: "최다 사유", value: reasonLabel(top) });
      const dist = fmtReasons(m.reasons);
      if (dist) rows.push({ label: "사유 분포", value: dist });
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
    case "recurring_verify_error": {
      // 백엔드 키(analyzer.py): service / issue_type / per_hour / count / high_count.
      const service = str(m.service);
      const issue = str(m.issue_type);
      const perHour = num(m.per_hour);
      const count = num(m.count);
      if (service) rows.push({ label: "서비스", value: service });
      if (issue) rows.push({ label: "오류 유형", value: issue });
      if (perHour !== null) rows.push({ label: "시간당", value: `${perHour.toLocaleString("ko-KR")}건` });
      if (count !== null) rows.push({ label: "총 검출", value: count.toLocaleString("ko-KR") });
      break;
    }
    case "latency_baseline": {
      // ★회귀가 아닌 **기록**이다 — 조치 대상이 아니라는 것이 이 화면의 핵심 정보다.
      const key = str(m.key ?? m.route);
      const p95 = num(m.p95_ms ?? m.p95);
      if (key) rows.push({ label: "경로", value: key });
      if (p95 !== null) rows.push({ label: "p95 지연", value: `${Math.round(p95).toLocaleString("ko-KR")}ms` });
      rows.push({ label: "성격", value: "회귀 아님(기준선 기록)" });
      break;
    }
    case "selection_contamination": {
      // 백엔드 키(analyzer.py): verdict / count / max_spread_km / malformed_rows.
      const verdict = str(m.verdict);
      const count = num(m.count);
      const spread = num(m.max_spread_km);
      const malformed = num(m.malformed_rows);
      if (verdict) {
        rows.push({
          label: "판정",
          value: verdict === "malformed" ? "주소 아닌 값 혼입" : "서로 다른 지역 혼합",
        });
      }
      if (count !== null) rows.push({ label: "관측", value: `${count.toLocaleString("ko-KR")}건` });
      // ★좌표가 없으면 **미상**이다 — 0km 로 쓰면 "붙어 있다"는 거짓이 된다.
      rows.push({
        label: "최대 이격",
        value: spread !== null ? `${spread.toLocaleString("ko-KR")}km` : "미상(좌표 없음)",
      });
      if (malformed !== null && malformed > 0) {
        rows.push({ label: "문제 행", value: `${malformed.toLocaleString("ko-KR")}행` });
      }
      if (verdict === "multi_region") {
        // ★캠페인 결정: 원거리 묶음은 **후보지 비교라는 정당한 사용**일 수 있다.
        rows.push({ label: "참고", value: "후보지 비교면 정상" });
      }
      break;
    }
    case "stale_reanalysis": {
      const service = str(m.service);
      const reason = str(m.kind ?? m.reason);
      if (service) rows.push({ label: "서비스", value: service });
      if (reason) rows.push({ label: "사유", value: reason });
      break;
    }
    case "heal_escalation": {
      // 백엔드 키(healing_rules._escalate): action_type / trigger_key / reason.
      const action = str(m.action_type);
      const trigger = str(m.trigger_key);
      if (action) rows.push({ label: "조치 유형", value: action });
      if (trigger) rows.push({ label: "트리거", value: trigger });
      rows.push({ label: "상태", value: "자동치유 무효 — 사람 점검 필요" });
      break;
    }
    case "improvement_proposal": {
      // ★실측 결함(2026-08-25): 이 분기는 `m.service`·`m.target` 을 읽는데 백엔드 payload
      //   (`growth/improvement_agent.py:192`)에는 **둘 다 없다** — source_insight_id /
      //   requires_approval / auto_merge / confidence / affected_files / proposal / pr_status.
      //   그래서 rows 가 빈 채로 `null` 이 반환돼 **지표가 한 줄도 안 떴다**.
      //   기존 카탈로그 락은 `case` 의 **존재**만 봐서 이 상태가 초록이었다.
      const conf = num(m.confidence);
      const files = Array.isArray(m.affected_files) ? m.affected_files.length : null;
      const prStatus = str(m.pr_status);
      if (conf !== null) rows.push({ label: "신뢰도", value: pct(conf) });
      if (files !== null) rows.push({ label: "영향 파일", value: `${files.toLocaleString("ko-KR")}개` });
      if (prStatus) rows.push({ label: "PR 상태", value: prStatus });
      // ★자동 머지가 **꺼져 있다**는 사실이 이 카드의 안전 정보다 — 사람 승인 없이는
      //   아무것도 반영되지 않는다는 것을 화면이 말해야 한다.
      rows.push({ label: "반영", value: "사람 승인 필요(자동 머지 없음)" });
      break;
    }
    case "prompt_candidate": {
      // 백엔드 키(improvement_agent.py:410): service / candidate_label / confidence /
      //                                     requires_approval / auto_adopt / proposal.
      const service = str(m.service);
      const label = str(m.candidate_label ?? m.target ?? m.key);
      const conf = num(m.confidence);
      if (service) rows.push({ label: "서비스", value: service });
      if (label) rows.push({ label: "후보", value: label });
      if (conf !== null) rows.push({ label: "신뢰도", value: pct(conf) });
      rows.push({ label: "반영", value: "사람 승인 필요(자동 채택 없음)" });
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

/* ================================================================== */
/*  Phase 3 — 자가치유(heal) 현황                                      */
/*  백엔드 계약: growth.py HealActionOut / ActiveFlagOut / HealLogOut  */
/* ================================================================== */

type HealActionType =
  | "threshold_relax"
  | "cache_warm"
  | "stale_reanalysis"
  | "circuit_observe"
  | (string & {});

// growth.py HealActionOut 와 1:1. action_id 등 다수 nullable, ttl_expires_at 은 string|null.
type HealAction = {
  action_id: string | null;
  action_type: HealActionType | null;
  severity: string | null;
  service: string | null;
  rollbackable: boolean;
  setting_key: string | null;
  ttl_expires_at: string | null;
  params: Record<string, unknown> | null;
  created_at: string | null;
};

// growth.py ActiveFlagOut 와 1:1. value 는 object|null, updated_by 는 string|null.
type ActiveFlag = {
  key: string;
  scope: string;
  /** ★dict 만이 아니다 — `growth_last_run.*` 워터마크는 ISO **문자열**이다.
   *  백엔드가 종전에 문자열을 `null` 로 삼켜 「축이 도는가」를 못 보게 했다. */
  value: Record<string, unknown> | string | number | boolean | null;
  ttl_expires_at: string | null;
  updated_by: string | null;
};

type HealLog = { actions: HealAction[]; active_flags: ActiveFlag[]; total: number };
type RollbackResult = {
  action_id: string;
  rolled_back: boolean;
  setting_key: string | null;
  detail: string | null;
};

// action_type → 아이콘(이모지 대신 단순 글리프)·라벨. 미지정/미래값은 graceful.
const HEAL_TYPE_META: Record<string, { icon: string; label: string; advisoryOnly?: boolean }> = {
  threshold_relax: { icon: "⊟", label: "임계 완화" },
  cache_warm: { icon: "≈", label: "캐시 예열" },
  stale_reanalysis: { icon: "↻", label: "재분석 제안", advisoryOnly: true },
  circuit_observe: { icon: "◎", label: "서킷 관찰" },
};

function healTypeMeta(t: string | null) {
  return (t && HEAL_TYPE_META[t]) || { icon: "•", label: t ?? "미분류" };
}

// 활성 플래그 TTL 남은시간 사람친화 표기. NULL=영구, 과거=만료.
function ttlRemaining(iso: string | null): string {
  if (!iso) return "영구";
  const ms = new Date(iso).getTime() - Date.now();
  if (Number.isNaN(ms)) return "-";
  if (ms <= 0) return "만료됨";
  const min = Math.floor(ms / 60000);
  if (min < 60) return `${min}분 남음`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}시간 ${min % 60}분 남음`;
  return `${Math.floor(hr / 24)}일 ${hr % 24}시간 남음`;
}

// params 객체를 "키 값 · 키 값" 요약(최대 4개). 중첩/긴 값은 절단.
function summarizeParams(
  p: Record<string, unknown> | string | number | boolean | null,
): string {
  if (p === null || p === undefined) return "";
  // ★스칼라(문자열 워터마크 등)는 **그대로 보여 준다** — 종전엔 이 값이 백엔드에서
  //   null 로 삼켜져 화면에 아무것도 안 나왔다.
  if (typeof p !== "object") return String(p);
  const parts: string[] = [];
  for (const [k, v] of Object.entries(p)) {
    if (parts.length >= 4) break;
    let val: string;
    if (v === null || v === undefined) continue;
    else if (typeof v === "object") val = JSON.stringify(v);
    else val = String(v);
    if (val.length > 24) val = `${val.slice(0, 24)}…`;
    parts.push(`${k} ${val}`);
  }
  return parts.join(" · ");
}

function HealSection() {
  const [actions, setActions] = useState<HealAction[]>([]);
  const [flags, setFlags] = useState<ActiveFlag[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [authed, setAuthed] = useState(true);
  const [error, setError] = useState("");
  const [rollingId, setRollingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await apiClient.get<HealLog>("/growth/heal-log?limit=200", {
        useMock: false,
      });
      setActions(res.actions ?? []);
      setFlags(res.active_flags ?? []);
      setTotal(res.total ?? 0);
      setAuthed(true);
    } catch (e) {
      if (e instanceof ApiClientError && (e.status === 401 || e.status === 403)) {
        setAuthed(false);
      } else {
        setError("자가치유 현황을 불러오지 못했습니다.");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 롤백 — POST 후 권위 있는 상태로 refetch(낙관적 제거 후 실패 시 refetch 가 원복).
  const rollback = useCallback(
    async (actionId: string) => {
      setRollingId(actionId);
      setError("");
      try {
        const res = await apiClient.post<RollbackResult>(
          `/growth/heal/${encodeURIComponent(actionId)}/rollback`,
          { useMock: false },
        );
        if (!res.rolled_back) {
          setError(res.detail || "롤백이 적용되지 않았습니다.");
        }
      } catch (e) {
        if (e instanceof ApiClientError && e.status === 404) {
          setError("해당 heal 액션을 찾을 수 없습니다.");
        } else {
          setError("롤백에 실패했습니다.");
        }
      } finally {
        setRollingId(null);
        await load(); // 활성 플래그·로그를 서버 권위 상태로 재동기화.
      }
    },
    [load],
  );

  /* ---- 로딩 ---- */
  if (isLoading) {
    return (
      <div className="space-y-4">
        <div className="h-24 animate-pulse rounded-2xl bg-[var(--surface-soft)]" />
        {[1, 2, 3].map((n) => (
          <div key={n} className="h-16 animate-pulse rounded-2xl bg-[var(--surface-soft)]" />
        ))}
      </div>
    );
  }

  /* ---- 권한 없음(401/403) ---- */
  if (!authed) {
    return (
      <div className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-8 text-center text-sm text-[var(--text-secondary)]">
        자가치유 현황은 플랫폼 총괄관리자만 열람할 수 있습니다.
      </div>
    );
  }

  /* ---- 오류(전체 로드 실패) ---- */
  if (error && actions.length === 0 && flags.length === 0) {
    return (
      <div className="rounded-2xl border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-8 text-center text-sm text-[var(--status-warning)]">
        {error}
      </div>
    );
  }

  const hasAny = actions.length > 0 || flags.length > 0;

  return (
    <div className="space-y-6">
      {/* 비치명 오류(롤백 실패 등) 인라인 표기 */}
      {error && (
        <div className="rounded-xl border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] px-4 py-2.5 text-xs text-[var(--status-warning)]">
          {error}
        </div>
      )}

      {/* 데이터 미축적 — 정직 표기(목업 금지) */}
      {!hasAny && (
        <Card>
          <CardContent className="p-8 text-center">
            <p className="text-sm font-medium text-[var(--text-secondary)]">
              자가치유 조치 없음 — 장애 발생 시 자동 기록
            </p>
            <p className="mt-1.5 text-xs text-[var(--text-hint)]">
              임계 완화·캐시 예열·서킷 관찰 등의 자동 조치가 발생하면 여기에 이력과
              현재 활성 플래그가 표시됩니다. (재분석은 제안만 하며 자동 실행하지 않습니다)
            </p>
          </CardContent>
        </Card>
      )}

      {/* 현재 활성 플래그 — TTL·롤백 */}
      {flags.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <p className="cc-label">현재 활성 플래그</p>
              <span className="text-xs text-[var(--text-hint)]">
                {flags.length.toLocaleString("ko-KR")}건 적용 중
              </span>
            </div>
            <div className="mt-4 space-y-3">
              {flags.map((f) => {
                // 이 플래그를 만든 rollbackable heal 액션 중 가장 최근 것을 매칭(setting_key === f.key).
                const owner = actions.find(
                  (a) => a.rollbackable && a.setting_key === f.key && a.action_id,
                );
                const expired = (() => {
                  if (!f.ttl_expires_at) return false;
                  const t = new Date(f.ttl_expires_at).getTime();
                  return !Number.isNaN(t) && t <= Date.now();
                })();
                const busy = owner?.action_id != null && rollingId === owner.action_id;
                return (
                  <div
                    key={`${f.scope}:${f.key}`}
                    className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-bold text-[var(--text-primary)] break-all">
                            {f.key}
                          </span>
                          <span className="rounded-md bg-[var(--surface-muted)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-tertiary)]">
                            {f.scope}
                          </span>
                          <span
                            className={`rounded-md border px-2 py-0.5 text-[11px] font-bold ${
                              expired
                                ? "border-[var(--line)] bg-[var(--surface-muted)] text-[var(--text-hint)]"
                                : "border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] text-[var(--accent-strong)]"
                            }`}
                          >
                            {ttlRemaining(f.ttl_expires_at)}
                          </span>
                        </div>
                        {f.value && summarizeParams(f.value) && (
                          <p className="mt-2 text-xs text-[var(--text-hint)]">
                            <span className="cc-num text-[var(--text-secondary)]">
                              {summarizeParams(f.value)}
                            </span>
                          </p>
                        )}
                        {f.updated_by && (
                          <p className="mt-1 text-[11px] text-[var(--text-hint)]">
                            적용 주체 {f.updated_by}
                          </p>
                        )}
                      </div>
                      {owner?.action_id && (
                        <button
                          onClick={() => rollback(owner.action_id as string)}
                          disabled={busy}
                          className="shrink-0 rounded-xl border border-[var(--line-strong)] bg-[var(--surface-muted)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)] transition-all hover:text-[var(--text-primary)] disabled:opacity-50"
                        >
                          {busy ? "롤백 중…" : "롤백"}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* 치유 액션 로그 */}
      {actions.length > 0 && (
        <Card>
          <CardContent className="p-6">
            <div className="flex items-center justify-between">
              <p className="cc-label">치유 액션 로그</p>
              <span className="text-xs text-[var(--text-hint)]">총 {total.toLocaleString("ko-KR")}건</span>
            </div>
            <div className="mt-4 space-y-3">
              {actions.map((a, idx) => {
                const meta = healTypeMeta(a.action_type);
                const params = summarizeParams(a.params);
                const busy = a.action_id != null && rollingId === a.action_id;
                return (
                  <div
                    key={a.action_id ?? `${a.action_type}-${a.created_at}-${idx}`}
                    className="rounded-2xl border border-[var(--line)] bg-[var(--surface-soft)] p-4"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded-md border px-2 py-0.5 text-[11px] font-bold ${severityClasses(a.severity)}`}
                          >
                            {SEVERITY_LABELS[a.severity ?? ""] ?? a.severity ?? "미분류"}
                          </span>
                          <span className="text-sm font-bold text-[var(--text-primary)]">
                            <span className="mr-1.5 text-[var(--text-tertiary)]">{meta.icon}</span>
                            {meta.label}
                          </span>
                          {a.service && (
                            <span className="rounded-md bg-[var(--surface-muted)] px-2 py-0.5 text-[11px] font-medium text-[var(--text-tertiary)]">
                              {a.service}
                            </span>
                          )}
                          {meta.advisoryOnly && (
                            <span className="rounded-md border border-[var(--accent-strong)]/30 bg-[var(--accent-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--accent-strong)]">
                              제안(자동실행 안 함)
                            </span>
                          )}
                        </div>
                        {a.setting_key && (
                          <p className="mt-2 text-xs text-[var(--text-hint)]">
                            설정 키{" "}
                            <span className="cc-num font-bold text-[var(--text-secondary)] break-all">
                              {a.setting_key}
                            </span>
                          </p>
                        )}
                        {params && (
                          <p className="mt-1 text-xs text-[var(--text-hint)]">
                            <span className="cc-num text-[var(--text-secondary)]">{params}</span>
                          </p>
                        )}
                        <p className="mt-2 text-[11px] text-[var(--text-hint)]">
                          <span className="cc-num">{fmtDate(a.created_at)}</span>
                          {a.ttl_expires_at && (
                            <>
                              {" · TTL "}
                              <span className="cc-num">{ttlRemaining(a.ttl_expires_at)}</span>
                            </>
                          )}
                        </p>
                      </div>
                      {a.rollbackable && a.action_id && (
                        <button
                          onClick={() => rollback(a.action_id as string)}
                          disabled={busy}
                          className="shrink-0 rounded-xl border border-[var(--line-strong)] bg-[var(--surface-muted)] px-3 py-2 text-xs font-bold text-[var(--text-secondary)] transition-all hover:text-[var(--text-primary)] disabled:opacity-50"
                        >
                          {busy ? "롤백 중…" : "롤백"}
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  메인 컴포넌트                                                       */

/* ------------------------------------------------------------------ */
/* 효과기 발화 — 선언(effector_reach) × 실측(platform_events)            */
/* ------------------------------------------------------------------ */

type EffectorRow = {
  key: string;
  declared_reach: string | null;
  total: number;
  last_fired_at: string | null;
  hours_since: number | null;
  state: string;
  evidence?: string;
  missing?: string;
};

type EffectorStatus = {
  effectors: EffectorRow[];
  undeclared: EffectorRow[];
  dormant_hours: number;
  telemetry_since?: string;
  summary: {
    declared: number;
    never_fired: number;
    dormant: number;
    active: number;
    undeclared: number;
    product_reaching_declared: number;
    product_reaching_active: number;
    product_reaching_max_hours_since: number | null;
    product_reaching_never_fired: number;
  };
};

/** ★상태 라벨 — 백엔드 `ALL_STATES` 와 1:1. 갈리면 화면에 영문 raw 가 뜬다. */
export const EFFECTOR_STATE_LABELS: Record<string, string> = {
  never_fired: "★한 번도 발화 없음",
  dormant: "휴면",
  active: "발화 중",
  undeclared: "표에 없음(선언 누락)",
};

/** `reach` 가 무엇을 뜻하는지 — 코드만 아는 말을 화면에 그대로 내지 않는다. */
const REACH_LABELS: Record<string, string> = {
  product: "제품에 닿음",
  self: "성장엔진 자기자신만",
  none: "읽는 곳 없음",
};

function EffectorSection() {
  const [data, setData] = useState<EffectorStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await apiClient.get<EffectorStatus>("/growth/effectors", { useMock: false });
      setData(res);
    } catch (e) {
      // ★조회 실패를 '효과기 없음'으로 위장하지 않는다.
      const d = (e as { payload?: { detail?: unknown } })?.payload?.detail;
      setError(typeof d === "string" ? d : "효과기 발화 현황을 불러오지 못했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (isLoading) {
    return <p className="text-sm text-[var(--text-tertiary)]">불러오는 중…</p>;
  }
  if (error) {
    return (
      <p role="alert" className="rounded-lg bg-[rgba(220,38,38,0.1)] p-3 text-sm text-[var(--status-error)]">
        {error}
      </p>
    );
  }
  if (!data) return null;

  const s = data.summary;
  return (
    <div className="space-y-4" data-testid="effector-firing">
      {/* ★가장 중요한 한 줄 — 선언과 실제가 갈리는가. */}
      <div className="rounded-xl border border-[var(--line)] bg-[var(--surface-muted)] p-4">
        <p className="text-sm text-[var(--text-primary)]">
          제품에 닿는 효과기{" "}
          <strong>{s.product_reaching_active}</strong> / {s.product_reaching_declared} 발화 중
          {s.product_reaching_max_hours_since !== null ? (
            // ★임계 없는 사실 — 라벨(휴면/발화중)에 동의하지 않을 수 있게 원값을 보여 준다.
            <span className="text-[var(--text-tertiary)]">
              {" "}· 최장 침묵 {s.product_reaching_max_hours_since.toLocaleString("ko-KR")}시간
            </span>
          ) : null}
        </p>
        <p className="mt-1 text-xs text-[var(--text-tertiary)]">
          선언 {s.declared}종 · 발화 중 {s.active} · 휴면 {s.dormant} ·{" "}
          <span className={s.never_fired > 0 ? "font-semibold text-[var(--status-warning)]" : ""}>
            한 번도 없음 {s.never_fired}
          </span>
          {/* ★과대주장 방지 — 「한 번도 없음」이 **무엇에 대해** 0건인지 밝힌다. */}
          {data.telemetry_since ? (
            <span data-testid="telemetry-since"> ({data.telemetry_since} 계측 시작 이후)</span>
          ) : null}
          {s.undeclared > 0 ? (
            <span className="font-semibold text-[var(--status-error)]">
              {" "}· ★표에 없는 액션 {s.undeclared}
            </span>
          ) : null}
          {" "}· 휴면 기준 {data.dormant_hours}시간
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-sm">
          <thead>
            <tr className="border-b border-[var(--line)] text-left text-xs text-[var(--text-tertiary)]">
              <th className="py-2 pr-3 font-medium">효과기</th>
              <th className="py-2 pr-3 font-medium">선언된 도달범위</th>
              <th className="py-2 pr-3 font-medium">발화</th>
              <th className="py-2 pr-3 font-medium">최근</th>
              <th className="py-2 font-medium">상태</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--line)]">
            {[...data.effectors, ...data.undeclared].map((r) => (
              <tr key={r.key} data-testid={`effector-row-${r.key}`}>
                <td className="py-2 pr-3 font-mono text-xs text-[var(--text-primary)]">{r.key}</td>
                <td className="py-2 pr-3 text-xs">
                  {r.declared_reach ? REACH_LABELS[r.declared_reach] ?? r.declared_reach : "—"}
                </td>
                <td className="py-2 pr-3">{r.total.toLocaleString("ko-KR")}건</td>
                <td className="py-2 pr-3 text-xs text-[var(--text-tertiary)]">
                  {/* ★라벨과 함께 **원값**을 낸다. */}
                  {r.hours_since !== null
                    ? `${r.hours_since.toLocaleString("ko-KR")}시간 전`
                    : "—"}
                </td>
                <td className="py-2">
                  <span
                    data-testid={`effector-state-${r.key}`}
                    className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                      r.state === "active"
                        ? "bg-[rgba(13,148,136,0.12)] text-[rgb(15,118,110)]"
                        : r.state === "never_fired" || r.state === "undeclared"
                          ? "bg-[rgba(220,38,38,0.12)] text-[var(--status-error)]"
                          : "bg-[rgba(217,119,6,0.12)] text-[rgb(146,64,14)]"
                    }`}
                  >
                    {EFFECTOR_STATE_LABELS[r.state] ?? r.state}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="text-xs leading-5 text-[var(--text-tertiary)]">
        ★발화 0건이 곧 결함은 아닙니다 — 「읽는 곳 없음」인 효과기가 영원히 발화하지 않는 것이
        정상일 수 있습니다. 이 표는 <strong>사실과 판단 근거</strong>를 줄 뿐이고 판단은 사람이 합니다.
        <br />
        ★「한 번도 발화 없음」은 <strong>세 가지를 구별하지 못합니다</strong> — ①조건이 아직 안 맞음
        ②정상이라 발생할 일이 없었음 ③구조적으로 발화 불가(배선 결함). 처방이 서로 다르므로
        0건을 보면 <strong>그 효과기의 경로를 직접 따라가야</strong> 합니다.
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */

type GrowthTab = "insights" | "heal" | "effectors";

export function GrowthDashboard() {
  const [tab, setTab] = useState<GrowthTab>("insights");
  const [insights, setInsights] = useState<GrowthInsight[]>([]);
  const [total, setTotal] = useState(0);
  // ★서버가 준 집계. `insights` 는 `limit=200` 으로 잘리지만 이 값은 안 잘린다.
  const [actionableCounts, setActionableCounts] =
    useState<Partial<Record<InsightSeverity, number>> | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [authed, setAuthed] = useState(true);
  const [error, setError] = useState("");
  const [actingId, setActingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const res = await apiClient.get<GrowthInsightList>(
        // ★`status=open` — 서버 필터를 쓴다(5종이 이미 있는데 화면이 하나도 안 썼다).
        //   종전엔 **이미 확인/기각한 항목이 200칸의 슬롯을 먹고** 미처리 항목을 밀어냈다
        //   (라이브 실측 2026-08-26: critical 79칸 중 5건이 acknowledged).
        "/growth/insights?sort=severity&status=open&limit=200",
        { useMock: false },
      );
      setInsights(res.items ?? []);
      setTotal(res.total ?? 0);
      setActionableCounts(res.actionable_counts ?? null);
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

  /* ---- 인사이트 탭 본문 렌더 ---- */
  const renderInsights = () => {
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
      <div className="rounded-2xl border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] p-8 text-center text-sm text-[var(--status-warning)]">
        {error}
      </div>
    );
  }

  /* ---- 파생 통계 ---- */
  // ★"확인 필요" 집계에서 **조치 대상이 아닌 타입은 뺀다.**
  //   2026-08-23 실측: `latency_regression` 2,059건 중 최신 6건이 전부 회귀가 아니었고
  //   `status=open` 2,248건이 실제 조치 대상(critical 57 + warn 352)을 **가렸다**.
  //   지금은 회귀가 아닌 것이 `latency_baseline` 으로 분리되므로, 그것을 세지 않는다.
  const openInsights = insights.filter(
    (it) => it.status === "open" && !NON_ACTIONABLE_TYPES.has(it.insight_type),
  );
  // ★★집계는 **서버가 준 값**을 쓴다 — 이 페이지(`limit=200`)를 세지 않는다.
  //   【왜 바꿨나 · 라이브 실측 2026-08-26】라이브 분포가 critical 79 · warn 476 · info 2,544 라
  //   `sort=severity&limit=200` 응답은 `critical 79 + warn 121` 로 채워지고 **info 는 0행** 온다.
  //   그래서 이 카드가 warn 을 **476이 아니라 121**로 보여 줬다(**74% 과소계상**). 즉
  //   **페이지 크기가 집계를 결정**하고 있었다 — 집계가 아니라 표본이었다.
  //   서버는 같은 술어로 `limit` 없이 센다(`GrowthInsightList.actionable_counts`).
  //   ★폴백은 종전 방식(페이지 집계)이다. 서버가 값을 안 주는 구버전 응답에서도 화면이 죽지
  //     않게 하되, **그 경우 값이 과소일 수 있다**는 것을 여기 적어 둔다.
  const serverCounts = actionableCounts;
  const severityCounts: Record<InsightSeverity, number> = { critical: 0, warn: 0, info: 0 };
  if (serverCounts) {
    severityCounts.critical = serverCounts.critical ?? 0;
    severityCounts.warn = serverCounts.warn ?? 0;
    severityCounts.info = serverCounts.info ?? 0;
  } else {
    for (const it of openInsights) {
      if (it.severity === "critical" || it.severity === "warn" || it.severity === "info") {
        severityCounts[it.severity] += 1;
      }
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
        <div className="rounded-xl border border-[rgba(217,119,6,0.28)] bg-[rgba(217,119,6,0.08)] px-4 py-2.5 text-xs text-[var(--status-warning)]">
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
                      ? "text-[var(--status-warning)]"
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
                                      ? "bg-[var(--status-warning)]"
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
                {/* ★★절단을 **말한다**. 종전엔 `총 N건` 만 띄우고 200행만 그려서, 나머지가
                    잘렸다는 사실이 화면 어디에도 없었다(라이브 실측 2026-08-26: 열림 3,083건 중
                    200행 → **warn 355건이 조용히 사라짐**). 숫자 둘의 괴리가 유일한 단서였고
                    그것도 읽는 사람이 스스로 이어 붙여야 했다. 이제 문장으로 말한다. */}
                <span className="text-xs text-[var(--text-hint)]">
                  {insights.length < total
                    ? `열림 ${total.toLocaleString("ko-KR")}건 중 ${insights.length.toLocaleString("ko-KR")}건 표시 — 나머지는 목록에 없습니다`
                    : `열림 ${total.toLocaleString("ko-KR")}건`}
                </span>
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
  };

  /* ---- 탭 래퍼: 인사이트(기존) / 자가치유(Phase 3) ---- */
  const tabBtn = (key: GrowthTab) =>
    tab === key
      ? "rounded-xl bg-[var(--accent-strong)] px-4 py-2 text-xs font-bold text-white"
      : "rounded-xl border border-[var(--line-strong)] bg-[var(--surface-muted)] px-4 py-2 text-xs font-bold text-[var(--text-secondary)] transition-all hover:text-[var(--text-primary)]";

  return (
    <div className="space-y-6">
      <div className="flex gap-2">
        <button type="button" onClick={() => setTab("insights")} className={tabBtn("insights")}>
          성장 인사이트
        </button>
        <button type="button" onClick={() => setTab("heal")} className={tabBtn("heal")}>
          자가치유 현황
        </button>
        {/* ★「닿는다」는 선언과 「발화했다」는 사실을 대조하는 자리. */}
        <button type="button" onClick={() => setTab("effectors")} className={tabBtn("effectors")}>
          효과기 발화
        </button>
      </div>
      {tab === "insights" ? (
        renderInsights()
      ) : tab === "heal" ? (
        <HealSection />
      ) : (
        <EffectorSection />
      )}
    </div>
  );
}
