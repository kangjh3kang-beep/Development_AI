/**
 * 선택 필지 라벨 — 계획(순수)과 그리기(L 주입) (#954)
 *
 * ★이 파일이 존재하는 이유: 종전에는 이 로직이 `SatongMultiMap` 의 effect 안에 있어
 *   jsdom 에서 **한 줄도 실행되지 않았다**. 형제 `satong-layout-overlay` 가 같은 이유로
 *   먼저 추출됐고(그 파일 주석에 «변이 1550건 전부 통과» 실측이 있다), 여기도 같은 길을 간다.
 */
import { describe, expect, it, vi } from "vitest";

import {
  planSelectionLabels,
  renderSelectionLabels,
  type SelectionLabelFeature,
} from "@/lib/satong-selection-labels";

vi.mock("@/lib/satong-map-labels", () => ({ bindSatongLabel: vi.fn() }));

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
    rollup: false,
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
    const p = plan({ rollup: true, features: [F({}), F({ lat: 37.6, lon: 127.2 })] });
    expect(p.kind).toBe("rollup");
    expect(p.kind === "rollup" && p.anchors).toHaveLength(1);
    expect(p.kind === "rollup" && p.anchors[0].label).toBe("선택 2필지 · 200㎡");
  });

  it("★면적 결측이 하나라도 있으면 면적을 **표기하지 않는다**(부분합을 전체합처럼 보이지 않게)", () => {
    const p = plan({ rollup: true, features: [F({}), F({ lat: 37.6, lon: 127.2, areaSqm: null })] });
    expect(p.kind === "rollup" && p.anchors[0].label).toBe("선택 2필지");
  });

  it("줌아웃이어도 단일 필지는 개별 라벨(초기 진입 식별)", () => {
    expect(plan({ rollup: true, features: [F({})] }).kind).toBe("each");
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
