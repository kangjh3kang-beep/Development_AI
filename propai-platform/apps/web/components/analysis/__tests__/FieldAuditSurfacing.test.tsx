/**
 * W3 자가검증 표면화 회귀락 — 로직·배선·표면 3층.
 *
 * 이 화면이 잘못되면 사용자가 **틀린 안심**을 한다. 그래서 잠그는 것은 "무엇을 보여주나"가
 * 아니라 "무엇을 보여주면 안 되나"에 가깝다:
 *   - 지적이 섹션 매핑에서 빠져도 **조용히 사라지면 안 된다**(요약 카드로 올라와야 한다)
 *   - 실행된 규칙 수를 전수검사처럼 말하면 안 된다
 *   - "차단"·"검증됨" 같은 사실과 다른 말을 쓰면 안 된다(이 점검은 아무것도 막지 않는다)
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  readFieldAudit,
  findingsForSection,
  orphanIssues,
  SECTION_BY_CODE,
  ALWAYS_ON_CODES,
  RULE_INPUT_PATHS,
  type AuditFinding,
} from "@/lib/field-audit";

/* ── 목 (경로 기반 — 총 호출수 단언 금지) ── */

const routes = new Map<string, () => Promise<unknown>>();
const post = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>((path: string) => {
  const h = routes.get(path);
  return h ? h() : Promise.resolve({});
});
function onPost(path: string, handler: () => Promise<unknown>) {
  routes.set(path, handler);
}
const get = vi.fn<(path: string, opts?: unknown) => Promise<unknown>>(async () => ({
  providers: [],
}));

vi.mock("@/lib/api-client", () => ({
  apiClient: {
    post: (path: string, opts?: unknown) => post(path, opts),
    get: (path: string, opts?: unknown) => get(path, opts),
  },
  hasAccessToken: () => true,
  resolveApiOrigin: () => "http://localhost:8000",
  apiV1BaseUrl: () => "http://localhost:8000/api/v1",
  ApiClientError: class ApiClientError extends Error {},
}));
vi.mock("@/components/precheck/SatongMapShell", () => ({ SatongMapShell: () => null }));

import { ComprehensiveAnalysisPanel } from "@/components/analysis/ComprehensiveAnalysisPanel";
import { useProjectContextStore } from "@/store/useProjectContextStore";

const ADDRESS = "경북 포항시 남구 호미곶면 대보리 산1-1";

/** 라이브 프로덕션 응답에서 그대로 가져온 finding(2026-08-02 실측). */
const LIVE_METHODOLOGY: AuditFinding = {
  code: "MARKET_PRICE_METHODOLOGY",
  severity: "P2",
  panel: "시세",
  field: "land_prices.estimated_market_per_sqm",
  expected: "실거래로 교차검증된 시세",
  observed: "공시지가×보정계수 추정(실거래 미검증)",
  rule_id: "MARKET_PRICE_METHODOLOGY",
  tier: "B",
  note: "표시 토지 시세는 공시지가 기반 추정입니다",
};

const G2_ISSUE: AuditFinding = {
  code: "G2_SCHOOL_POI_DEDUP",
  severity: "P1",
  panel: "입지",
  field: "school_count",
  expected: 1,
  observed: 5,
  rule_id: "G2_SCHOOL_POI_DEDUP",
  tier: "A",
  note: "학교 POI 과카운트",
};

function resultWith(findings: AuditFinding[], extra: Record<string, unknown> = {}) {
  return {
    address: ADDRESS,
    zone_type: "보전관리지역",
    land_area_sqm: 152826,
    location: { education: { school_count: 5 } },
    land_prices: { official_price_per_sqm: 2820 },
    ai_interpretation: null,
    ai_interpretation_status: { status: "deferred", reason: "다음 단계" },
    field_audit: {
      is_valid: true,
      findings,
      metadata: { enabled: true, rules_registered: 8, rules_executed: 8 },
      coverage: {},
    },
    ...extra,
  };
}

/* ────────────────────────────────────────────────────────────────
 * 1층 — 로직
 * ──────────────────────────────────────────────────────────────── */

describe("readFieldAudit — 판정 로직", () => {
  it("field_audit 키가 없으면 '없음'이지 '이상 없음'이 아니다", () => {
    const v = readFieldAudit({ address: ADDRESS });
    expect(v.state).toBe("unavailable");
    expect(v.issues).toEqual([]);
  });

  it("상시 방법론 고지는 '확인 필요' 카운터에서 빠진다", () => {
    const v = readFieldAudit(resultWith([LIVE_METHODOLOGY]));
    expect(v.state).toBe("ran");
    // ★이게 깨지면 모든 보고서가 항상 '확인 필요 1건 이상'이 되어 경고가 무의미해진다.
    expect(v.issues).toHaveLength(0);
    expect(v.notes.map((f) => f.code)).toEqual(["MARKET_PRICE_METHODOLOGY"]);
  });

  it("실제 이상은 카운터에 들어가고 심각도 높은 순으로 정렬된다", () => {
    const p0: AuditFinding = { ...G2_ISSUE, code: "G1_PROTECTION_ZONE_RISK_FLOOR", severity: "P0" };
    const v = readFieldAudit(resultWith([G2_ISSUE, LIVE_METHODOLOGY, p0]));
    expect(v.issues.map((f) => f.severity)).toEqual(["P0", "P1"]);
    expect(v.hasHold).toBe(true);
  });

  it("규칙이 볼 자료가 없으면 '적용'이 아니라 '미판정'으로 센다", () => {
    // ★백엔드 rules_executed는 규칙이 아무 일도 안 해도 올라간다. 그 숫자를 그대로 보여주면
    //   자료 수집이 실패할수록 화면이 깨끗해 보인다. 그래서 프론트가 입력 존재를 직접 본다.
    const v = readFieldAudit(resultWith([]));
    const applied = v.ruleStatuses.filter((r) => r.applicability === "applied").map((r) => r.ruleId);
    expect(applied).toContain("MARKET_PRICE_METHODOLOGY"); // land_prices 있음
    expect(applied).toContain("G2_SCHOOL_POI_DEDUP"); // location.education.school_count 있음
    expect(applied).not.toContain("PROV_UNKNOWN_SOURCE"); // provenance 없음 → 미판정
  });

  it("★수집이 전면 실패한 보고서는 '적용'이 거의 없어야 한다(빈 컨테이너를 자료로 세지 않는다)", () => {
    // ★분석 응답은 수집이 실패해도 컨테이너를 빈 채로 항상 채워 넣는다. 키 존재만 세면
    //   자료가 하나도 없는 보고서가 "5개 적용됨"으로 보여서, 이 화면이 없애려던 착시
    //   (부실할수록 깨끗해 보임)가 그대로 되살아난다. R1 적대검증이 실측으로 잡아낸 결함.
    const empty = {
      effective_far: {},
      land_prices: {},
      sale_prices: [],
      development_plans: { land_use_regulations: [] },
      location: { education: { schools: [], school_count: 0 } },
      field_audit: {
        is_valid: true,
        findings: [],
        metadata: { enabled: true, rules_registered: 8, rules_executed: 8 },
        coverage: {},
      },
    };
    const v = readFieldAudit(empty);
    const applied = v.ruleStatuses.filter((r) => r.applicability === "applied").map((r) => r.ruleId);
    // school_count 0은 정상 수집값이라 '적용'이 맞다(학교가 실제로 없는 필지). 나머지는 전부 미판정.
    expect(applied).toEqual(["G2_SCHOOL_POI_DEDUP"]);
  });

  it("섹션 매핑이 없는 지적은 버려지지 않고 요약으로 올라온다", () => {
    const unknown: AuditFinding = { ...G2_ISSUE, code: "FUTURE_RULE_X", rule_id: "FUTURE_RULE_X" };
    const v = readFieldAudit(resultWith([unknown]));
    expect(v.unmappedCodes).toEqual(["FUTURE_RULE_X"]);
    expect(orphanIssues(v).map((f) => f.code)).toEqual(["FUTURE_RULE_X"]);
    // 어느 섹션에도 붙지 않는다(엉뚱한 섹션에 끼워넣지도 않는다).
    expect(findingsForSection(v, "location").issues).toEqual([]);
  });

  it("등재된 모든 규칙은 섹션 매핑과 입력 경로를 둘 다 갖는다", () => {
    // 백엔드에 규칙을 추가하고 프론트 등재를 잊으면 런타임에는 요약으로 승격되지만(위 테스트),
    // 개발 단계에서 먼저 알아채도록 여기서 대조한다.
    for (const ruleId of Object.keys(RULE_INPUT_PATHS)) {
      expect(RULE_INPUT_PATHS[ruleId].length).toBeGreaterThan(0);
    }
    for (const code of Object.keys(SECTION_BY_CODE)) {
      expect(typeof SECTION_BY_CODE[code]).toBe("string");
    }
    // 상시 고지 코드는 반드시 섹션이 있어야 각주가 제자리에 붙는다.
    for (const code of ALWAYS_ON_CODES) {
      expect(SECTION_BY_CODE[code], `${code} 섹션 매핑 누락`).toBeTruthy();
    }
  });
});

/* ────────────────────────────────────────────────────────────────
 * 2층 — 배선 + 3층 — 표면 (실제 패널 렌더)
 * ──────────────────────────────────────────────────────────────── */

async function runAnalysis() {
  useProjectContextStore.setState({
    siteAnalysis: { address: ADDRESS, zoneCode: "보전관리지역" } as never,
  });
  render(<ComprehensiveAnalysisPanel />);
  const btn = await screen.findByRole("button", { name: /종합 분석 시작/ });
  await waitFor(() => expect(btn).not.toBeDisabled());
  await userEvent.click(btn);
}

beforeEach(() => {
  post.mockClear();
  routes.clear();
  onPost("/site-score/poi-infra", async () => ({ score: 60 }));
  onPost("/development-methods/scenarios", async () => ({}));
  useProjectContextStore.setState({ siteAnalysis: null } as never);
});

describe("배선 — 패널이 자가검증 결과를 실제로 렌더한다", () => {
  it("실제 이상이 있으면 사용자 언어 문장이 화면에 나온다", async () => {
    onPost("/analysis/comprehensive", async () => resultWith([G2_ISSUE]));
    await runAnalysis();
    // ★백엔드 note 원문("dedup_school_cluster SSOT 대조 위반")이 아니라 프론트 카피가 나와야 한다.
    await waitFor(() =>
      expect(screen.getByText(/주변 학교 수가 실제보다 많게 집계/)).toBeTruthy(),
    );
    expect(screen.queryByText(/dedup_school_cluster/)).toBeNull();
  });

  it("★상시 방법론 각주가 해당 섹션 안에 실제로 렌더된다(배선 잠금)", async () => {
    // ★현재 프로덕션에서 실제로 발화하는 건 상시 고지 2종이 사실상 전부다. 즉 이게 이 기능의
    //   유일한 실산출물인데, R1 적대검증에서 **섹션 배선 7곳을 전부 지워도 테스트가 그린**이었다.
    onPost("/analysis/comprehensive", async () => resultWith([LIVE_METHODOLOGY]));
    await runAnalysis();
    // 3. 토지 주변시세 섹션을 펼친다(각주는 그 숫자 옆에서 읽어야 의미가 있다).
    const section = await screen.findByRole("button", { name: /토지 주변시세/ });
    await userEvent.click(section);
    await waitFor(() =>
      expect(screen.getByText(/토지 시세는 실거래가 아니라 공시지가에 계수를 곱한 추정치/)).toBeTruthy(),
    );
    // 상시 고지는 '확인 필요' 카운터에 들어가지 않는다.
    expect(screen.getByText(/점검 규칙이 잡아낸 이상 항목은 없습니다/)).toBeTruthy();
  });

  it("★섹션 매핑이 없는 지적도 화면에 실제로 보인다(무음 드롭 금지 — 표면 잠금)", async () => {
    // 헬퍼 단위테스트만으로는 부족하다: R1에서 요약카드가 매핑된 지적만 렌더하도록 변이해도
    // 전 테스트가 통과했다(미래 규칙이 화면에서 조용히 사라지는 결함이 생존).
    const unknown: AuditFinding = {
      ...G2_ISSUE,
      code: "FUTURE_RULE_X",
      rule_id: "FUTURE_RULE_X",
      note: "미래 규칙이 낸 점검 원문",
    };
    onPost("/analysis/comprehensive", async () => resultWith([unknown]));
    await runAnalysis();
    await waitFor(() => expect(screen.getByText(/미래 규칙이 낸 점검 원문/)).toBeTruthy());
    expect(screen.getByText(/쉬운 설명이 준비되지 않아/)).toBeTruthy();
  });

  it("★규칙이 하나도 안 돌았으면 '이상 없음'이 아니라 그 사실을 먼저 말한다", async () => {
    // 등록이 무성으로 깨지면 백엔드는 field_audit을 붙이되 rules_registered:0으로 정직 보고한다.
    // 화면이 그 0을 무시하면 "규칙 8개 중 7개 적용 · 이상 없음"이라는 가장 위험한 거짓 안심이
    // 된다(적대검증 실측). 이 저장소가 배포 가드로 잡으려던 바로 그 상태다.
    onPost("/analysis/comprehensive", async () => ({
      ...resultWith([]),
      field_audit: {
        is_valid: true,
        findings: [],
        metadata: { enabled: true, rules_registered: 0, rules_executed: 0 },
        coverage: {},
      },
    }));
    await runAnalysis();
    await waitFor(() =>
      expect(screen.getByText(/점검 규칙이 하나도 실행되지 않았습니다/)).toBeTruthy(),
    );
    // 적용/미판정 수치를 그대로 보여주면 안 된다.
    expect(screen.queryByText(/판단할 자료가/)).toBeNull();
    expect(screen.queryByText(/점검 규칙이 잡아낸 이상 항목은 없습니다/)).toBeNull();
  });

  it("★규칙 전체가 롤백돼 등록만 있고 실행이 0이어도 같은 경고가 뜬다", async () => {
    // ★이 조합(registered 8 / executed 0)이 현실적으로 더 흔하다 — 운영에서
    //   FIELD_AUDIT_DISABLED_RULES로 규칙을 전부 끄면 등록 수는 그대로고 실행만 0이 된다.
    //   위 테스트 픽스처가 '둘 다 0'이라 두 조건 중 하나만 남겨도 통과하는 구멍이 있었다.
    onPost("/analysis/comprehensive", async () => ({
      ...resultWith([]),
      field_audit: {
        is_valid: true,
        findings: [],
        metadata: { enabled: true, rules_registered: 8, rules_executed: 0 },
        coverage: {},
      },
    }));
    await runAnalysis();
    await waitFor(() =>
      expect(screen.getByText(/점검 규칙이 하나도 실행되지 않았습니다/)).toBeTruthy(),
    );
    expect(screen.queryByText(/판단할 자료가/)).toBeNull();
    // 더 약한 '범위 축소' 문구로 대체되지 않는다(강한 경고가 우선).
    expect(screen.queryByText(/점검 범위가 평소보다 줄었습니다/)).toBeNull();
  });

  it("★등록이 0인데 실행 수만 남아 있어도 경고가 뜬다(반대 이접항)", async () => {
    onPost("/analysis/comprehensive", async () => ({
      ...resultWith([]),
      field_audit: {
        is_valid: true,
        findings: [],
        metadata: { enabled: true, rules_registered: 0, rules_executed: 8 },
        coverage: {},
      },
    }));
    await runAnalysis();
    await waitFor(() =>
      expect(screen.getByText(/점검 규칙이 하나도 실행되지 않았습니다/)).toBeTruthy(),
    );
  });

  it("자가검증 정보가 없으면 '없음'을 밝히고 이상 없음으로 위장하지 않는다", async () => {
    const { field_audit: _omit, ...noAudit } = resultWith([]);
    onPost("/analysis/comprehensive", async () => noAudit);
    await runAnalysis();
    await waitFor(() => expect(screen.getByText(/자가검증 정보 없음/)).toBeTruthy());
  });
});

describe("표면 — 사실과 다른 말을 쓰지 않는다", () => {
  it("점검 범위를 닫는 문장이 항상 있다(지적 0건이어도)", async () => {
    onPost("/analysis/comprehensive", async () => resultWith([]));
    await runAnalysis();
    await waitFor(() =>
      expect(screen.getByText(/지적이 없다고 해서 모든 숫자가 맞다는 뜻은 아닙니다/)).toBeTruthy(),
    );
    // AI 서술문이 점검 대상이 아님을 명시(사용자가 가장 열심히 읽는 부분이라 필수).
    expect(screen.getByText(/AI가 쓴 해석 문장/)).toBeTruthy();
  });

  it("'차단'·'검증됨'·'N% 검증' 같은 사실과 다른 표기를 쓰지 않는다", async () => {
    onPost("/analysis/comprehensive", async () =>
      resultWith([{ ...G2_ISSUE, severity: "P0", code: "G1_PROTECTION_ZONE_RISK_FLOOR" }]),
    );
    await runAnalysis();
    await waitFor(() => expect(screen.getByText(/플랫폼 자체 점검 결과/)).toBeTruthy());

    // ★이 점검은 관측 전용이라 실제로 아무것도 막지 않는다. P0에도 "차단"이라 쓰면 거짓이다.
    expect(screen.queryByText(/차단/)).toBeNull();
    expect(screen.queryByText(/검증됨/)).toBeNull();
    // 커버리지 비율을 낼 근거가 백엔드에 없다(coverage는 항상 비어 있음).
    expect(screen.queryByText(/% 검증/)).toBeNull();
    // 대신 P0는 "사용 보류 권고"로 말한다.
    expect(screen.getByText(/사용 보류 권고/)).toBeTruthy();

    // ★접힌 설명문 안까지 확인한다 — 열지 않으면 그 안에 "차단"을 써도 검출되지 않는다.
    await userEvent.click(screen.getByRole("button", { name: /점검이 어떻게 쓰이는지/ }));
    await waitFor(() => expect(screen.getByText(/관찰해 알려주기만 합니다/)).toBeTruthy());
    expect(screen.queryByText(/차단/)).toBeNull();
    expect(screen.queryByText(/검증됨/)).toBeNull();
  });
});
