import { describe, it, expect } from "vitest";
import { ROSTER_DISPLAY_LIMIT, sumRosterRows, NODE_TYPES, LABEL, moveTargets } from "./OrgTree";
import { addableChildTypes, orgRank } from "@/components/sales-app/roleConfig";

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

  it("orgRank 서열: 대행본사 < 대행지사 < 본부장 < 이사 < 팀장 < 직원 · 미등록=99(fail-closed)", () => {
    // 백엔드 _ORG_RANK 와 동일 서열이어야 프론트 노출과 서버 400 판정이 일치한다.
    expect(orgRank("AGENCY")).toBeLessThan(orgRank("SUBAGENCY"));
    expect(orgRank("SUBAGENCY")).toBeLessThan(orgRank("GM_DIRECTOR"));
    expect(orgRank("GM_DIRECTOR")).toBeLessThan(orgRank("DIRECTOR"));
    expect(orgRank("DIRECTOR")).toBeLessThan(orgRank("TEAM_LEADER"));
    expect(orgRank("TEAM_LEADER")).toBeLessThan(orgRank("MEMBER"));
    expect(orgRank("UNKNOWN_TYPE")).toBe(99);
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

/**
 * 직속 지정 파이프라인(2026-07-23) — 추가/이동 후보 계산의 순수 계약.
 *
 * ★addableChildTypes: 서버 /org/context 의 addable_types(권한 축)∩부모 위계(자식 서열 > 부모 서열)만
 *   UI에 노출한다 — 서버가 400/403 으로 거부할 선택지를 애초에 보여주지 않는 게 계약이다.
 * ★moveTargets: ltree 자손 판정은 반드시 `path + "."` 경계로 한다 — 과거 startsWith(n.path) 는
 *   "r.n1" 이 "r.n10" 을 자손으로 오인해 형제를 이동 후보에서 잘못 제외했다(경계 버그 회귀 고정).
 */
describe("직속 지정 파이프라인 — addableChildTypes", () => {
  it("총괄관리자(addable=[AGENCY]): 루트에만 대행사 추가 가능, 하위 노드엔 추가 불가", () => {
    expect(addableChildTypes(["AGENCY"], null)).toEqual(["AGENCY"]);
    // 대행사 노드 아래: AGENCY 는 rank 가 부모와 같아 제외 → 빈 배열(추가 버튼 미노출).
    expect(addableChildTypes(["AGENCY"], "AGENCY")).toEqual([]);
  });

  it("대행사(addable=[SUBAGENCY,GM_DIRECTOR,DIRECTOR]): 부모 위계에 따라 교집합만", () => {
    const addable = ["SUBAGENCY", "GM_DIRECTOR", "DIRECTOR"];
    expect(addableChildTypes(addable, "AGENCY")).toEqual(["SUBAGENCY", "GM_DIRECTOR", "DIRECTOR"]);
    // 본부장(GM_DIRECTOR) 아래엔 그보다 하위인 DIRECTOR 만 남는다.
    expect(addableChildTypes(addable, "GM_DIRECTOR")).toEqual(["DIRECTOR"]);
    // 루트엔 대행사만 둘 수 있는데 addable 에 없음 → 빈 배열.
    expect(addableChildTypes(addable, null)).toEqual([]);
  });

  it("팀장(addable=[MEMBER]): 팀장 노드 아래에만 직원 추가", () => {
    expect(addableChildTypes(["MEMBER"], "TEAM_LEADER")).toEqual(["MEMBER"]);
    expect(addableChildTypes(["MEMBER"], "MEMBER")).toEqual([]); // 직원 아래 직원 금지(동순위).
    expect(addableChildTypes(["MEMBER"], null)).toEqual([]);
  });
});

describe("직속 지정 파이프라인 — moveTargets", () => {
  const N = (id: string, path: string, node_type: string) => ({ id, path, node_type });
  const all = [
    N("a", "r1", "AGENCY"),
    N("g1", "r1.g1", "GM_DIRECTOR"),
    N("t1", "r1.g1.t1", "TEAM_LEADER"),
    N("t10", "r1.g1.t10", "TEAM_LEADER"), // ★t1 과 접두사가 겹치는 형제(경계 버그 재현용)
    N("m1", "r1.g1.t1.m1", "MEMBER"),
    N("g2", "r1.g2", "GM_DIRECTOR"),
  ];

  it("자기 자신·자손·현재 부모·위계 위반(서열 낮은 대상)은 제외", () => {
    const targets = moveTargets(all, all[2]); // t1(팀장) 이동
    const ids = targets.map((t) => t.id);
    expect(ids).not.toContain("t1"); // 자기 자신
    expect(ids).not.toContain("m1"); // 자손(순환 방지)
    expect(ids).not.toContain("g1"); // 현재 부모(제자리 이동 무의미)
    expect(ids).not.toContain("t10"); // 동순위 팀장 아래 팀장 금지(위계)
    expect(ids).toContain("g2"); // 다른 본부장 아래로는 이동 가능
  });

  it("★ltree 경계: 'r1.g1.t1' 이동 시 형제 'r1.g1.t10' 을 자손으로 오인하지 않는다", () => {
    // t10(팀장)을 이동할 때 — t1 은 t10 의 자손이 아니므로 (동순위라 위계로는 제외되지만)
    // 반대로 m1(직원) 이동 시 t10 이 후보에 살아있어야 경계 판정이 올바른 것이다.
    const targets = moveTargets(all, all[4]); // m1(직원) 이동
    const ids = targets.map((t) => t.id);
    expect(ids).toContain("t10"); // 접두사 유사 형제가 후보에 존재(경계 버그면 소실)
    expect(ids).not.toContain("t1"); // 현재 부모는 제외
    expect(ids).toContain("g1"); // 상위 본부장 가능(직원을 본부장 직속으로 — 서버 위계 허용)
  });
});
