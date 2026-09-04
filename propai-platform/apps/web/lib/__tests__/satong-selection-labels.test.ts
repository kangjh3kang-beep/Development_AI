/**
 * 선택 필지 라벨 — 계획(순수)과 그리기(L 주입) (#954)
 *
 * ★이 파일이 존재하는 이유: 종전에는 이 로직이 `SatongMultiMap` 의 effect 안에 있어
 *   jsdom 에서 **한 줄도 실행되지 않았다**. 형제 `satong-layout-overlay` 가 같은 이유로
 *   먼저 추출됐고(그 파일 주석에 «변이 1550건 전부 통과» 실측이 있다), 여기도 같은 길을 간다.
 */
import { describe, expect, it, vi } from "vitest";

import {
  SATONG_LABEL_BUDGET,
  SATONG_LABEL_BUDGET_MID,
  SATONG_LABEL_BUDGET_NEAR,
} from "@/lib/satong-map-labels";
import {
  planSelectionLabels,
  renderSelectionLabels,
  type SelectionLabelFeature,
} from "@/lib/satong-selection-labels";

// ★스텁은 **실제 계약보다 좁으면 안 된다**(2026-09-04 실측: 좁은 스텁 탓에 새로 쓴
//   `satongLabelBudget` 이 undefined 가 되어 이 파일의 절반이 빨개졌다 — 이 저장소가
//   반복 기록한 «스텁도 계약이다» 그 형태). 원본을 펼치고 **부수효과가 있는 것만** 대체한다.
vi.mock("@/lib/satong-map-labels", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/satong-map-labels")>()),
  bindSatongLabel: vi.fn(),
}));

const F = (o: Partial<SelectionLabelFeature>): SelectionLabelFeature => ({
  address: "서울 동작구 상도동 211-434",
  pnu: "1159010200102110434",
  lat: 37.5,
  lon: 127.0,
  areaSqm: 100,
  ...o,
});

const plan = (o: Partial<Parameters<typeof planSelectionLabels>[0]>) =>
  planSelectionLabels({
    visible: true,
    budget: SATONG_LABEL_BUDGET,
    features: [F({})],
    representativePoint: () => null,
    shortLabel: (f) => f.address,
    ...o,
  });

describe("계획 — hidden 과 empty 를 가른다", () => {
  it("★visible:false 면 **필지가 있어도** hidden — 토글의 전부다", () => {
    expect(plan({ visible: false, features: [F({}), F({})] })).toEqual({ kind: "hidden" });
  });

  it("visible:true + 필지 0 은 empty — hidden 과 **다른 원인**이다", () => {
    expect(plan({ features: [] })).toEqual({ kind: "empty" });
  });

  it("★두 상태를 뭉치지 않는다 — 뭉치면 「껐는데 안 꺼짐」과 「데이터 없음」이 같은 모양", () => {
    expect(plan({ visible: false, features: [] }).kind).toBe("hidden");
  });

  it("좌표가 없고 대표점도 없으면 그 필지는 빠진다", () => {
    const p = plan({ features: [F({ lat: null, lon: null, geometry: {} })] });
    expect(p.kind).toBe("empty");
  });

  it("좌표가 없으면 주입된 대표점을 쓴다", () => {
    const p = plan({
      features: [F({ lat: null, lon: null, geometry: {} })],
      representativePoint: () => ({ lat: 1, lon: 2 }),
    });
    expect(p).toMatchObject({ kind: "each", anchors: [{ lat: 1, lon: 2 }] });
  });
});

describe("계획 — 줌 롤업", () => {
  it("줌아웃 + 다필지는 집계 칩 1개로 접는다", () => {
    const p = plan({ budget: 0, features: [F({}), F({ lat: 37.6, lon: 127.2 })] });
    expect(p.kind).toBe("rollup");
    expect(p.kind === "rollup" && p.anchors).toHaveLength(1);
    expect(p.kind === "rollup" && p.anchors[0].label).toBe("선택 2필지 · 200㎡");
  });

  it("★면적 결측이 하나라도 있으면 면적을 **표기하지 않는다**(부분합을 전체합처럼 보이지 않게)", () => {
    const p = plan({ budget: 0, features: [F({}), F({ lat: 37.6, lon: 127.2, areaSqm: null })] });
    expect(p.kind === "rollup" && p.anchors[0].label).toBe("선택 2필지");
  });

  it("줌아웃이어도 단일 필지는 개별 라벨(초기 진입 식별)", () => {
    expect(plan({ budget: 0, features: [F({})] }).kind).toBe("each");
  });

  it("줌인은 다필지여도 개별 라벨", () => {
    const p = plan({ features: [F({}), F({ lat: 37.6, lon: 127.2 })] });
    expect(p.kind).toBe("each");
    expect(p.kind === "each" && p.anchors).toHaveLength(2);
  });
});

describe("★그리기 — 이전 레이어 정리가 계획과 **무관하게 항상 먼저**", () => {
  const L = () => {
    const marker = { addTo: vi.fn(() => ({ bindTooltip: vi.fn() })) };
    const group = { remove: vi.fn(), addTo: vi.fn(function (this: unknown) { return group; }) };
    return {
      L: { layerGroup: vi.fn(() => group), circleMarker: vi.fn(() => marker) },
      group,
      marker,
    };
  };

  it("hidden 이어도 이전 레이어를 지운다 — 「끄면 낡은 라벨이 남는」 결함의 락", () => {
    const prev = { remove: vi.fn() };
    const { L: fake } = L();
    const out = renderSelectionLabels({ L: fake, map: {}, previousLayer: prev, plan: { kind: "hidden" } });
    expect(prev.remove).toHaveBeenCalledTimes(1);
    expect(out).toBeNull();
    // ★그리지도 않았다(두 모집단 중 한쪽).
    expect(fake.layerGroup).not.toHaveBeenCalled();
  });

  it("★대칭 — 켜져 있으면 실제로 그린다(위 단언이 「항상 안 그림」으로 만족되지 않게)", () => {
    const prev = { remove: vi.fn() };
    const { L: fake, group } = L();
    const out = renderSelectionLabels({
      L: fake, map: {}, previousLayer: prev,
      plan: { kind: "each", anchors: [{ lat: 1, lon: 2, label: "가" }, { lat: 3, lon: 4, label: "나" }] },
    });
    expect(prev.remove).toHaveBeenCalledTimes(1);
    expect(fake.circleMarker).toHaveBeenCalledTimes(2);
    expect(out).toBe(group);
  });

  it("L 이나 map 이 없으면(jsdom) 그리지 않고 정리만 한다", () => {
    const prev = { remove: vi.fn() };
    expect(renderSelectionLabels({ L: null, map: {}, previousLayer: prev, plan: { kind: "each", anchors: [{ lat: 1, lon: 2, label: "가" }] } })).toBeNull();
    expect(prev.remove).toHaveBeenCalledTimes(1);
  });

  it("이전 레이어 remove 가 던져도 그리기는 진행된다", () => {
    const prev = { remove: vi.fn(() => { throw new Error("boom"); }) };
    const { L: fake, group } = L();
    expect(renderSelectionLabels({ L: fake, map: {}, previousLayer: prev, plan: { kind: "each", anchors: [{ lat: 1, lon: 2, label: "가" }] } })).toBe(group);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
describe("★개수 롤업 — 신고의 본체(206필지가 지도를 덮는다)", () => {
  const many = (n: number) =>
    Array.from({ length: n }, (_, i) => F({ lat: 37 + i * 1e-4, lon: 127 + i * 1e-4 }));

  it("★버짓을 **넘으면** 접는다 — 사용자 신고 그 자체", () => {
    // z=17 버짓 64 < 206
    const p = plan({ budget: SATONG_LABEL_BUDGET, features: many(206) });
    expect(p.kind).toBe("rollup");
    expect(p.kind === "rollup" && p.anchors).toHaveLength(1);
    expect(p.kind === "rollup" && p.anchors[0].label).toContain("선택 206필지");
  });

  it("★버짓 **이하면 접지 않는다** — 두 번째 모집단(대다수 선택은 동작 무변화)", () => {
    const p = plan({ budget: SATONG_LABEL_BUDGET, features: many(10) });
    expect(p.kind).toBe("each");
    expect(p.kind === "each" && p.anchors).toHaveLength(10);
  });

  it("★경계를 **양방향으로** 잰다 — 정확히 버짓이면 접지 않고, 하나 더면 접는다", () => {
    const b = SATONG_LABEL_BUDGET;
    expect(plan({ budget: SATONG_LABEL_BUDGET, features: many(b) }).kind).toBe("each");
    expect(plan({ budget: SATONG_LABEL_BUDGET, features: many(b + 1) }).kind).toBe("rollup");
  });

  it("★버짓 값에 따라 판정이 달라진다 — 세 대역 전부", () => {
    // 세 버짓이 서로 달라야 이 단언이 의미를 갖는다(공허 방지).
    expect(new Set([SATONG_LABEL_BUDGET_MID, SATONG_LABEL_BUDGET, SATONG_LABEL_BUDGET_NEAR]).size).toBe(3);
    const n = Math.floor((SATONG_LABEL_BUDGET_MID + SATONG_LABEL_BUDGET) / 2);
    expect(plan({ budget: SATONG_LABEL_BUDGET_MID, features: many(n) }).kind).toBe("rollup");
    expect(plan({ budget: SATONG_LABEL_BUDGET, features: many(n) }).kind).toBe("each");
    const m = Math.floor((SATONG_LABEL_BUDGET + SATONG_LABEL_BUDGET_NEAR) / 2);
    expect(plan({ budget: SATONG_LABEL_BUDGET, features: many(m) }).kind).toBe("rollup");
    expect(plan({ budget: SATONG_LABEL_BUDGET_NEAR, features: many(m) }).kind).toBe("each");
    // ★버짓을 **줌에서 파생하는 것**은 호출부의 계약이다 — 그 축은 컴포넌트 테스트가 잠근다
    //   (satong-selection-label-toggle.test.tsx · «컴포넌트가 넘긴 버짓이 자기 줌의 파생값인가»).
  });

  it("★★세는 것은 「피처」가 아니라 **「좌표가 풀린 피처」**다(리뷰 minor-1)", () => {
    // 두 모집단을 가른다: 좌표가 없고 대표점도 없는 피처는 라벨을 못 단다.
    //   features 8개 중 실제 앵커는 3개 → 버짓 5 를 **넘지 않는다** = each.
    //   `args.features.length` 로 세면 8 > 5 라 rollup 이 되어 이 단언이 죽는다.
    const withCoords = many(3);
    const noCoords = Array.from({ length: 5 }, () => F({ lat: null, lon: null, geometry: {} }));
    const p = plan({ budget: 5, features: [...withCoords, ...noCoords], representativePoint: () => null });
    expect(p.kind).toBe("each");
    expect(p.kind === "each" && p.anchors).toHaveLength(3);
  });

  it("★종전 줌 롤업 경로는 그대로 발화한다(회귀 아님)", () => {
    // z<15 는 버짓 0 이라 개수 축으로도 접히지만, rollup 플래그 경로 자체를 확인한다.
    const p = plan({ budget: 0, features: many(2) });
    expect(p.kind).toBe("rollup");
  });

  it("★단일 필지는 어느 줌에서도 개별 라벨(초기 진입 식별 — PR#329 의도 보존)", () => {
    expect(plan({ budget: 0, features: many(1) }).kind).toBe("each");
    expect(plan({ budget: 0, features: many(1) }).kind).toBe("each");
  });

  it("★토글이 개수보다 **먼저** 판정된다 — 껐으면 몇 필지든 hidden", () => {
    expect(plan({ visible: false, budget: SATONG_LABEL_BUDGET, features: many(206) })).toEqual({ kind: "hidden" });
  });
});
