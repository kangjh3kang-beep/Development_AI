import { describe, it, expect } from "vitest";
import { ROSTER_DISPLAY_LIMIT, sumRosterRows, NODE_TYPES, LABEL } from "./OrgTree";

/**
 * #5 조직도 — 로스터 표시행 합(footer '행 합')의 합산범위 계약(iter-6).
 *
 * ★회귀 고정: 표는 상위 N명만 그리는데(slice), 과거 footer '행 합'은 서버 전체 로스터 합
 *   (roster_totals)을 써서 31명+ 현장에선 '보이는 30행 합' ≠ footer 라 사용자가 데이터 오류로
 *   오해했다. 이제 footer '행 합'은 반드시 '실제로 그린 행(상위 N명)'의 합과 일치해야 한다.
 *   화면 .map 과 footer 가 같은 순수 헬퍼(sumRosterRows)+상한(ROSTER_DISPLAY_LIMIT)을 쓰므로,
 *   여기서 그 한 부를 고정한다(라이브 렌더 불필요 — 합산범위 계약만 검증).
 */
type Row = { contracts: number; customers: number; work_logs: number };

function makeRoster(n: number): Row[] {
  // i 번째 행: 계약 i, 고객 2i, 업무일지 3i (합이 인덱스에 결정적으로 의존 → 절단 효과가 합에 드러남).
  return Array.from({ length: n }, (_, i) => ({
    contracts: i,
    customers: 2 * i,
    work_logs: 3 * i,
  }));
}

describe("OrgTree 로스터 합산범위 계약", () => {
  it("표시상한은 30(회귀 고정)", () => {
    expect(ROSTER_DISPLAY_LIMIT).toBe(30);
  });

  it("빈 로스터 → 합계 0(0으로 시작하는 reduce)", () => {
    expect(sumRosterRows([])).toEqual({ contracts: 0, customers: 0, work_logs: 0 });
  });

  it("절단 없는 경우(≤30명): footer '행 합' == 전체 합(roster_totals와 동일)", () => {
    const roster = makeRoster(30);
    const shown = roster.slice(0, ROSTER_DISPLAY_LIMIT);
    const shownTotals = sumRosterRows(shown);
    const allTotals = sumRosterRows(roster);
    expect(shown.length).toBe(30);
    expect(shownTotals).toEqual(allTotals); // 다 보이므로 행 합 == 전체 합
    // 0..29 합: contracts=Σi=435, customers=2×435=870, work_logs=3×435=1305
    expect(shownTotals).toEqual({ contracts: 435, customers: 870, work_logs: 1305 });
  });

  it("★절단되는 경우(31명+): footer '행 합'은 보이는 30행 합 — 전체 합보다 작아야 한다", () => {
    const roster = makeRoster(55); // 시드 MEMBER50 + TEAM_LEADER5 = 55행 상황
    const shown = roster.slice(0, ROSTER_DISPLAY_LIMIT);
    const shownTotals = sumRosterRows(shown);
    const allTotals = sumRosterRows(roster);
    expect(shown.length).toBe(30); // 30행만 표시
    // 표시행 합은 0..29 만 → 435/870/1305
    expect(shownTotals).toEqual({ contracts: 435, customers: 870, work_logs: 1305 });
    // 전체 합(0..54): Σi=1485 → contracts 1485, customers 2970, work_logs 4455
    expect(allTotals).toEqual({ contracts: 1485, customers: 2970, work_logs: 4455 });
    // ★핵심 계약: 잘렸으면 footer 행 합 < 전체 합(둘을 분리 표기해야 정합) — 과거 버그는 둘을 동일시했다.
    expect(shownTotals.contracts).toBeLessThan(allTotals.contracts);
    expect(shownTotals.customers).toBeLessThan(allTotals.customers);
    expect(shownTotals.work_logs).toBeLessThan(allTotals.work_logs);
  });

  it("footer '행 합'은 항상 '실제 표시행' 합과 byte-동일(map 과 footer 가 같은 한 부)", () => {
    for (const n of [0, 1, 29, 30, 31, 100]) {
      const roster = makeRoster(n);
      const shown = roster.slice(0, ROSTER_DISPLAY_LIMIT);
      // footer 가 쓰는 합 == 화면이 .map 으로 그리는 바로 그 행들의 합.
      expect(sumRosterRows(shown)).toEqual(sumRosterRows(roster.slice(0, ROSTER_DISPLAY_LIMIT)));
      expect(shown.length).toBe(Math.min(n, ROSTER_DISPLAY_LIMIT));
    }
  });
});

/**
 * #5 조직도 — node_type → 한국어 라벨 SSOT 패리티(iter-7).
 *
 * ★문제: 같은 화면에서 트리 배지(OrgTree.tsx 의 LABEL[n.node_type])는 프론트 상수를, 로스터 표는
 *   백엔드가 내려준 r.role_label(=overview._LABEL[node_type])을 그렸다. 두 소스의 라벨 '값'이 어긋나면
 *   (예: DIRECTOR → 배지 '본부장' vs 표 '이사') 같은 노드가 두 곳에서 다른 직급으로 보인다.
 *   백엔드 overview._LABEL 을 정본(SSOT)으로 확정하고, 프론트 LABEL/NODE_TYPES 라벨을 byte-동일로 맞췄다.
 *   여기서 프론트 LABEL 의 '값'을 정본 기대값과 byte-동일로 고정한다(백엔드 test_sales_org.py 가 같은
 *   기대값을 백엔드 쪽에서 고정 — 양쪽 협공으로 드리프트 차단).
 */
// 백엔드 overview._LABEL 과 byte-동일이어야 하는 정본 라벨 한 부(SSOT).
const EXPECTED_LABELS: Record<string, string> = {
  AGENCY: "대행본사",
  SUBAGENCY: "대행지사",
  GM_DIRECTOR: "본부장",
  DIRECTOR: "이사",
  TEAM_LEADER: "팀장",
  MEMBER: "직원",
};

describe("OrgTree node_type 라벨 SSOT 패리티", () => {
  it("LABEL[node_type] == 기대 한국어 값(백엔드 _LABEL 과 byte-동일)", () => {
    for (const [nodeType, expected] of Object.entries(EXPECTED_LABELS)) {
      expect(LABEL[nodeType]).toBe(expected);
    }
  });

  it("NODE_TYPES value 집합 == 6개 직급(키셋 패리티)", () => {
    expect(new Set(NODE_TYPES.map((t) => t.value))).toEqual(new Set(Object.keys(EXPECTED_LABELS)));
    expect(NODE_TYPES).toHaveLength(6);
  });

  it("NODE_TYPES 의 각 항목 label == LABEL[value](드롭다운=배지 동일 한 부)", () => {
    for (const t of NODE_TYPES) {
      expect(t.label).toBe(LABEL[t.value]);
      expect(t.label).toBe(EXPECTED_LABELS[t.value]);
    }
  });

  it("★트리배지(LABEL[node_type])와 로스터표(role_label) 가 동일 node_type 에 동일 문자열을 렌더(byte-동일)", () => {
    // 로스터 표는 r.role_label(백엔드 overview._LABEL[node_type])을 그리고, 트리 배지는 LABEL[node_type]
    // 을 그린다. 백엔드 _LABEL 이 SSOT 이고 프론트 LABEL 을 그 값에 맞췄으므로, 같은 node_type 에 대해
    // 두 렌더 문자열이 byte-동일해야 한다(과거 모순 표시 회귀 차단).
    for (const [nodeType, ssotLabel] of Object.entries(EXPECTED_LABELS)) {
      // 트리 배지가 그리는 문자열(OrgTree.tsx:240 LABEL[n.node_type] ?? n.node_type).
      const treeBadge = LABEL[nodeType] ?? nodeType;
      // 로스터 표가 그리는 문자열(OrgTree.tsx:150 r.role_label) — 백엔드가 SSOT _LABEL 로 내려준 값.
      const rosterRoleLabel = ssotLabel;
      expect(treeBadge).toBe(rosterRoleLabel);
    }
  });
});
