/**
 * ★계약 락 — 백엔드가 내보내는 인사이트가 화면에 **지표를 한 줄이라도 내는가**,
 *   그리고 폴백률 카드가 **사유**를 말하는가.
 *
 * ## 왜 이 락이 따로 필요한가 (2026-08-25 실측)
 *
 * 형제 락 `GrowthDashboard.catalog.test.ts` 는 타입 축을 촘촘히 잠근다 — 라벨·유령·
 * TS 유니온·`case` **존재**·NON_ACTIONABLE 까지. 그런데 그 락이 초록인 채로 두 결함이 살아 있었다:
 *
 *  1. `improvement_proposal` 은 `case` 가 있지만 `m.service`·`m.target` 을 읽는데
 *     백엔드 payload(`growth/improvement_agent.py:192`)에는 **둘 다 없다**
 *     → `rows.length === 0` → **`null` 반환**(카드에 지표가 한 줄도 안 뜬다).
 *  2. `fallback_rate` 는 `case` 가 있지만 #816 이 넣은 `reasons`·`top_reason` 을
 *     **참조하지 않는다** → 화면은 계속 "폴백률 80.77%" 만 말하고
 *     *무엇부터 고쳐야 하는지*는 말하지 않는다.
 *
 * ★교훈: **`case` 의 존재는 출력의 존재가 아니다.** 소스에서 `case "x":` 를 세는 검사는
 *   이 두 형태에 원리적으로 뚫린다 — 그래서 여기서는 **렌더 결과**를 본다(규율 §A-1·§A-3).
 *
 * ## 픽스처는 어디서 왔나
 *
 * 손으로 지어낸 모양이 아니라 **백엔드가 실제로 만드는 dict** 를 그대로 옮겼다
 * (`growth/analyzer.py` · `growth/improvement_agent.py` · `growth/healing_rules.py`).
 * 픽스처가 계약보다 좁으면 그 필드를 쓰는 코드가 테스트에서만 통과한다.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InsightMetrics } from "../GrowthDashboard";

type Ins = Parameters<typeof InsightMetrics>[0]["insight"];

function ins(insight_type: string, metrics_json: Record<string, unknown>): Ins {
  return {
    id: "t", insight_type, severity: "critical", metrics_json,
    narrative: null, recommended_action: null, status: "open",
    created_at: null, window_start: null, window_end: null,
  } as unknown as Ins;
}

/**
 * 백엔드가 실제로 내보내는 metrics_json (출처를 각 줄에 적는다 — 낡으면 추적 가능하게).
 * ★목록형이지만 **의도적**이다: 여기서 잠그는 것은 "키 전수"가 아니라 "행이 나오는가"다.
 *   키 전수 축은 아래 `it.todo` 로 부채를 드러내 둔다.
 */
const REAL_PAYLOADS: Record<string, Record<string, unknown>> = {
  // analyzer.py:_analyze_error_clusters
  error_cluster: { signature: "sig", route: "/api/v1/x", status_code: 503, count: 2349, per_hour: 97.9, sample: "raw error text" },
  // analyzer.py:_analyze_fallback_rate (#816 이 reasons·top_reason 추가)
  fallback_rate: { service: "site_analysis", fallback: 21, llm_call: 26, fallback_pct: 80.77, reasons: { timeout: 12, parse: 6, unlabeled: 3 }, top_reason: "timeout" },
  // analyzer.py:_analyze_quality_drop (**metrics 스프레드 포함)
  quality_drop: { service: "avm", verify_total: 50, fail: 12, warn: 3, feedback_total: 20, down: 8, fail_pct: 24.0, warn_pct: 6.0, down_pct: 40.0 },
  // analyzer.py:_analyze_latency_regression
  // ★`triggers`·`typical_p95`·`typical_windows` 를 **빠뜨리지 않는다** — 픽스처가 계약보다
  //   좁으면 그 필드를 쓰는 코드가 테스트에서만 통과한다(이 파일 머리말이 적어 둔 그 함정).
  latency_regression: { key: "/api/v1/y", p95_ms: 2200.0, samples: 40, baseline_p95: 2200.0, prev_baseline_p95: 900.0, triggers: ["ratio"], typical_p95: 1500.0, typical_windows: 9 },
  latency_baseline: { key: "/api/v1/y", p95_ms: 900.0, samples: 40, baseline_p95: 900.0, prev_baseline_p95: null },
  // analyzer.py:_analyze_recurring_verify_errors
  recurring_verify_error: { service: "legal", issue_type: "missing_citation", count: 40, per_hour: 1.7, high_count: 9 },
  // analyzer.py:_analyze_selection_contamination
  selection_contamination: { verdict: "multi_region", count: 4, max_spread_km: 15.86, malformed_rows: 0 },
  // healing_rules.py:_escalate
  heal_escalation: { action_type: "threshold_relax", trigger_key: "fallback:site_analysis", reason: "auto_heal_ineffective" },
  // healing_rules.py (service 를 **명시적으로 제외**하고 kind 를 싣는다)
  stale_reanalysis: { kind: "ledger_stale" },
  // improvement_agent.py:192 — ★service·target 이 없다(이 락이 지키는 그 사실)
  improvement_proposal: { source_insight_id: "i1", requires_approval: true, auto_merge: false, confidence: 0.62, affected_files: ["a.py", "b.py"], proposal: { title: "x" }, pr_status: "draft_only" },
  // improvement_agent.py:410
  prompt_candidate: { service: "avm", candidate_label: "v3", requires_approval: true, auto_adopt: false, confidence: 0.71, proposal: { title: "y" } },
};

describe("★계약 — 인사이트 카드가 지표를 실제로 낸다", () => {
  it("픽스처가 비어 있지 않다(공허한 초록 방지)", () => {
    // ★단언 **앞에** 둔다 — 픽스처가 비면 아래 전수 루프가 0회 돌고 공허하게 참이 된다(§A-2).
    expect(Object.keys(REAL_PAYLOADS).length).toBeGreaterThanOrEqual(11);
  });

  it.each(Object.keys(REAL_PAYLOADS))(
    "%s — 백엔드 실제 payload 로 렌더하면 지표가 최소 한 줄 나온다",
    (type) => {
      const { container } = render(<InsightMetrics insight={ins(type, REAL_PAYLOADS[type])} />);
      // `rows.length === 0` 이면 컴포넌트가 `null` 을 반환한다 — 그때 container 가 빈다.
      expect(
        container.textContent?.trim(),
        `${type}: 지표가 한 줄도 안 뜬다(case 는 있는데 payload 키가 안 맞는다)`,
      ).toBeTruthy();
    },
  );

  /* ------------------------------------------------------------------ *
   * ★지연 카드가 **어느 축이 울렸는지** 말한다 — 소비처 0 을 끝낸 자리의 락
   *
   *   절대편차 **단독** 발화는 화면에 `p95 33,000ms / 기준선 23,524ms` = **1.40배**로
   *   나간다. 비율 임계는 1.5배이므로 **임계 미만인 수치 옆에 `warn`** 이 붙는다 —
   *   축을 말하지 않으면 사람이 왜 울렸는지 알 방법이 없다(진단 불가는 장애다).
   *
   *   ★백엔드만 고치고 이 락이 없으면 **프론트를 통째로 되돌려도 전부 초록**이다.
   *     그것이 이 저장소가 반복해 데인 형태다("몇 개 층에 넣었나").
   * ------------------------------------------------------------------ */
  const latencyWith = (over: Record<string, unknown>) =>
    ins("latency_regression", { ...REAL_PAYLOADS.latency_regression, ...over });

  it("★두 모집단 — 비율 단독과 절대편차 단독이 **서로 다른** 축을 말한다", () => {
    // 한쪽만 단언하면 "항상 같은 문구를 붙이는 구현"이 통과한다.
    const r = render(<InsightMetrics insight={latencyWith({ triggers: ["ratio"] })} />);
    // ★**라벨을 정확 일치로** 단언한다 — 값만 보면 라벨을 지우는 변이가 생존한다(실측).
    expect(screen.getByText("발화 축")).toBeTruthy();
    expect(r.container.textContent).toContain("비율(기준선 대비)");
    expect(r.container.textContent).not.toContain("절대편차");
    r.unmount();

    const a = render(<InsightMetrics insight={latencyWith({ triggers: ["absolute"] })} />);
    expect(screen.getByText("발화 축")).toBeTruthy();
    expect(a.container.textContent).toContain("절대편차(평소값 대비)");
    expect(a.container.textContent).not.toContain("비율(기준선 대비)");
  });

  it("★평소값이 **실린다** — 키만 있고 값이 안 실리는 것을 막는다", () => {
    render(<InsightMetrics insight={latencyWith({ triggers: ["absolute"], typical_p95: 23524.0 })} />);
    // ★★`toContain("평소값")` 은 **공허했다** — 축 라벨 `절대편차(평소값 대비)` 가
    //   그 부분문자열을 이미 갖고 있어, 평소값 **행을 통째로 지워도 초록**이었다(실측).
    //   내가 쓴 문구가 내 단언을 무력화한 것 — 라벨은 **정확 일치 노드**로 본다.
    expect(screen.getByText("평소값")).toBeTruthy();
    expect(screen.getByText("23,524ms")).toBeTruthy();
  });

  it("★「모름」을 **0ms 로 위장하지 않는다** — 평소가 0ms 인 경로라는 관측이 되어 버린다", () => {
    render(
      <InsightMetrics insight={latencyWith({ triggers: ["absolute"], typical_p95: null, typical_windows: 2 })} />,
    );
    expect(screen.getByText(/판정 불가\(이력 2건\)/)).toBeTruthy();
    // ★부분문자열로 보지 않는다 — `not.toContain("0ms")` 는 같은 카드의 **`2,200ms`**
    //   안의 `0ms` 를 집어 **정상 렌더를 위반으로 신고**한다(실측으로 걸렸다).
    //   값 노드와 **정확히 일치**하는지로 판정한다.
    expect(screen.queryByText("0ms")).toBeNull();
    // 양성 대조군 — 조회기가 살아 있는지(값 노드를 실제로 집을 수 있는지) 먼저 증명한다.
    expect(screen.getByText("2,200ms")).toBeTruthy();
  });

  it("음성 대조군 — 발화가 아니면(`triggers` 빈 목록) 축 행이 **없다**", () => {
    // 이것이 없으면 "항상 축 행을 그리는 구현"이 위 락을 전부 통과한다.
    const { container } = render(<InsightMetrics insight={latencyWith({ triggers: [] })} />);
    expect(container.textContent).not.toContain("발화 축");
  });

  it("모르는 축 코드는 **감추지 않고 원문 그대로** — 새 축이 조용히 사라지는 것을 막는다", () => {
    const { container } = render(<InsightMetrics insight={latencyWith({ triggers: ["brand_new_axis"] })} />);
    expect(container.textContent).toContain("brand_new_axis");
  });

  it("★폴백률 카드가 **사유**를 말한다 — 이게 없으면 무엇부터 고칠지 모른다", () => {
    render(<InsightMetrics insight={ins("fallback_rate", REAL_PAYLOADS.fallback_rate)} />);
    expect(screen.getByText("최다 사유")).toBeTruthy();
    expect(screen.getByText("타임아웃")).toBeTruthy();            // top_reason 이 한글로
    expect(screen.getByText("사유 분포")).toBeTruthy();
    // 많은 순 + 미분류를 감추지 않는다.
    expect(screen.getByText(/타임아웃 12 · 응답 파싱 실패 6 · 사유 미분류\(계측 누락\) 3/)).toBeTruthy();
  });

  it("★사유 코드를 **영문 raw 로 흘리지 않는다** — #808 과 같은 얼굴이 되지 않게", () => {
    render(<InsightMetrics insight={ins("fallback_rate", { ...REAL_PAYLOADS.fallback_rate, top_reason: "content_filter" })} />);
    expect(screen.getByText("정책 거부")).toBeTruthy();
    expect(screen.queryByText("content_filter")).toBeNull();
  });

  it("모르는 사유 코드는 **감추지 않고** 원문 그대로 보인다", () => {
    // 감추면 분포 합이 틀어지고 "새 실패 유형"이라는 가장 중요한 신호가 사라진다.
    render(<InsightMetrics insight={ins("fallback_rate", { ...REAL_PAYLOADS.fallback_rate, top_reason: "brand_new_kind" })} />);
    expect(screen.getByText("brand_new_kind")).toBeTruthy();
  });

  it("★사유가 아직 없으면 그 두 줄은 나오지 않는다 — 없는 것을 지어내지 않는다", () => {
    // 배포 전(#816 미반영) 응답 형태. 특이도: 이 락이 '항상 참'이 아님을 보인다.
    const { container } = render(
      <InsightMetrics insight={ins("fallback_rate", { service: "site_analysis", fallback: 21, llm_call: 26, fallback_pct: 80.77 })} />,
    );
    expect(container.textContent).toContain("폴백률");
    expect(container.textContent).not.toContain("최다 사유");
    expect(container.textContent).not.toContain("사유 분포");
  });

  it("★improvement_proposal 이 **payload 에서 온** 값을 낸다 — 상수 행이 공허함을 가리지 못하게", () => {
    // ★변이로 발견한 구멍(2026-08-25): 이 분기에는 무조건 push 되는 상수 행
    //   (`반영: 사람 승인 필요`)이 있어서, payload 키를 **전부 못 읽어도**
    //   "행이 최소 한 줄"은 참이 된다. 실제로 `m.confidence` 를 깨는 변이가 **생존했다.**
    //   그래서 여기서는 **payload 에서 파생된 값**을 각각 못 박는다.
    render(<InsightMetrics insight={ins("improvement_proposal", REAL_PAYLOADS.improvement_proposal)} />);
    expect(screen.getByText("신뢰도")).toBeTruthy();
    expect(screen.getByText("62.0%")).toBeTruthy();        // confidence 0.62
    expect(screen.getByText("영향 파일")).toBeTruthy();
    expect(screen.getByText("2개")).toBeTruthy();           // affected_files 길이
    expect(screen.getByText("PR 상태")).toBeTruthy();
    // ★2026-08-27: 종전엔 raw `draft_only` 를 단언했는데, 그건 **결함을 기대값으로 고정**한
    //   것이었다 — 라이브 53/53 이 `artifact_only` 인 채 영문으로 떴다(#808 과 같은 얼굴).
    //   라벨로 바꾸되 **이 테스트의 원래 의도(값이 payload 에서 온다)를 약화시키지 않는다**:
    //   고정 문구를 단언하면 상수 행이 그것을 흉내낼 수 있으므로, **두 payload 가 서로 다른
    //   라벨을 낸다**를 같은 실행에서 확인한다.
    expect(screen.getByText("PR 준비됨(봇 대기)")).toBeTruthy();   // draft_only
    // 안전 정보(자동 머지 없음)도 함께 — 이것만으로는 위 구멍을 못 막으므로 마지막에 둔다.
    expect(screen.getByText(/사람 승인 필요/)).toBeTruthy();
  });

  it("★PR 상태가 **payload 에 따라 갈린다** — 상수 문구가 아니다", () => {
    // 두 모집단: 같은 타입인데 pr_status 만 다르면 화면 문구가 달라야 한다.
    const a = render(
      <InsightMetrics
        insight={ins("improvement_proposal", {
          ...REAL_PAYLOADS.improvement_proposal, pr_status: "draft_only",
        })}
      />,
    );
    const t1 = a.container.textContent ?? "";
    a.unmount();
    const b = render(
      <InsightMetrics
        insight={ins("improvement_proposal", {
          ...REAL_PAYLOADS.improvement_proposal, pr_status: "artifact_only",
        })}
      />,
    );
    const t2 = b.container.textContent ?? "";
    expect(t1).not.toBe(t2);
    // ★라이브 53/53 이 이 값이다 — 운영자가 "왜 PR 이 없나"를 화면에서 알 수 있어야 한다.
    expect(t2).toContain("토큰 없음");
    // ★모르는 코드는 감추지 않고 원문 그대로(새 상태 신호를 숨기지 않는다).
    const c = render(
      <InsightMetrics
        insight={ins("improvement_proposal", {
          ...REAL_PAYLOADS.improvement_proposal, pr_status: "brand_new_state",
        })}
      />,
    );
    expect(c.container.textContent).toContain("brand_new_state");
    c.unmount();
    b.unmount();
  });

  it("★prompt_candidate 도 payload 에서 온 값을 낸다 — 두 타입은 payload 가 다르다", () => {
    // 한 분기로 묶여 있던 시절 `m.target` 을 읽어 **둘 다** 대상을 못 그렸다.
    render(<InsightMetrics insight={ins("prompt_candidate", REAL_PAYLOADS.prompt_candidate)} />);
    expect(screen.getByText("후보")).toBeTruthy();
    expect(screen.getByText("v3")).toBeTruthy();            // candidate_label
    expect(screen.getByText("71.0%")).toBeTruthy();         // confidence 0.71
  });

  it.todo(
    "★부채 — metrics_json **키 전수 커버리지** 축은 아직 잠기지 않았다. " +
    "설계: insight_types.py 에 METRICS_KEYS 를 선언(SSOT 확장)하고, 파이썬 테스트가 analyzer " +
    "함수들을 **실제로 호출**해 나온 키셋과 대조한다(정규식 0줄 — `**metrics` 스프레드와 " +
    "`insight_type_for_latency(sev)` 같은 함수호출 타입명도 자동으로 잡힌다). 그다음 이 파일이 " +
    "그 선언을 읽어 각 case 가 참조하는지 본다. 면제는 사유 필수 + **죽은 면제는 실패**. " +
    "★정규식 파서로 하려다 접었다 — 시험 삼아 짠 파서가 latency 2종을 통째로 놓치고 " +
    "quality_drop 의 `**metrics` 스프레드 키 3개도 못 봐서, '미참조 12건'이라는 " +
    "**위음성 목록**을 만들었다(test_insight_type_catalog.py 가 이미 같은 대가를 치렀다).",
  );
});
