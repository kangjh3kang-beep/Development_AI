import { describe, it, expect } from "vitest";
import {
  summarizeMarketViewport,
  marketOffscreenNote,
  type MarketViewportBounds,
} from "./satong-market-viewport";

/** 라이브 실측 좌표(2026-09-04 · 남양주 화도읍). 상업이 중심 근처, 아파트가 원거리. */
const APT = [
  { lat: 37.65592, lon: 127.3024 },  // 신명스카이뷰그린
  { lat: 37.65822, lon: 127.30318 }, // 중흥S클래스
  { lat: 37.65467, lon: 127.29805 }, // 마석힐즈파크푸르지오
  { lat: 37.65002, lon: 127.31876 }, // 그랜드힐(2차)
];
const COMMERCIAL = [
  { lat: 37.65064, lon: 127.30574 }, // 창현리 736-1
  { lat: 37.65196, lon: 127.31309 }, // 마석우리 92-4
];
const PLAN = [
  { type: "apt", groups: APT },
  { type: "commercial", groups: COMMERCIAL },
];

/** z15 상당 — 6개 전부 담는 넓은 경계(라이브에서 6/6 화면 안이었다). */
const WIDE: MarketViewportBounds = { south: 37.63, west: 127.28, north: 37.67, east: 127.33 };
/** z17 상당 — 중심 좁은 경계. 라이브에서 상업 1개만 남았다. */
const TIGHT: MarketViewportBounds = { south: 37.6505, west: 127.31, north: 37.6535, east: 127.316 };

describe("summarizeMarketViewport", () => {
  it("★L1 두 모집단 — 화면 안은 세지 않고 화면 밖만 센다(두 값이 달라야 배선이 잠긴다)", () => {
    const s = summarizeMarketViewport(PLAN, TIGHT);
    expect(s.total).toBe(6);
    // 이 픽스처는 inView 와 outside 가 **다른 값**이다. 같으면 배선을 끊어도 통과한다.
    expect(s.inView).toBe(1);
    expect(s.outside).toBe(5);
    expect(s.inView).not.toBe(s.outside);
    // 합이 총수를 이룬다(사라지는 마커가 없다).
    expect((s.inView ?? 0) + (s.outside ?? 0) + s.indeterminate).toBe(s.total);
  });

  it("★L1b 넓은 경계에서는 화면 밖이 0 — 같은 함수가 두 모집단을 정말 가른다", () => {
    const s = summarizeMarketViewport(PLAN, WIDE);
    expect(s.inView).toBe(6);
    expect(s.outside).toBe(0);
    expect(marketOffscreenNote(s)).toBe("");
  });

  it("★L2 「모름」은 0이 아니라 null — 못 잰 것이 「이상 없음」으로 읽히면 안 된다", () => {
    for (const bad of [
      null,
      undefined,
      { south: 37.6, west: 127.3, north: 37.5, east: 127.4 },      // south > north (뒤집힘)
      { south: 37.6, west: 127.4, north: 37.7, east: 127.3 },      // west > east (경도 래핑)
      { south: NaN, west: 127.3, north: 37.7, east: 127.4 },       // 비유한수
    ] as (MarketViewportBounds | null | undefined)[]) {
      const s = summarizeMarketViewport(PLAN, bad);
      expect(s.outside).toBeNull();
      expect(s.inView).toBeNull();
      expect(s.outside).not.toBe(0); // ★0 으로 폴백하면 이 단언이 죽는다
      expect(marketOffscreenNote(s)).toBe("");
      expect(s.total).toBe(6);       // 총수는 여전히 말한다(침묵하지 않는다)
    }
  });

  it("★L3 경계는 네 방향 모두 — 한쪽만 걸면 반대쪽이 무제한이 된다", () => {
    const box: MarketViewportBounds = { south: 0, west: 0, north: 10, east: 10 };
    const dirs = {
      north: { lat: 20, lon: 5 },
      south: { lat: -20, lon: 5 },
      east: { lat: 5, lon: 20 },
      west: { lat: 5, lon: -20 },
    };
    for (const [name, pt] of Object.entries(dirs)) {
      const s = summarizeMarketViewport([{ type: "t", groups: [pt] }], box);
      expect(`${name}:${s.outside}`).toBe(`${name}:1`);
    }
    // 대조군 — 한가운데는 반드시 화면 안(검사기 생존 증명)
    expect(summarizeMarketViewport([{ type: "t", groups: [{ lat: 5, lon: 5 }] }], box).outside).toBe(0);
  });

  it("★L4 유형을 차별하지 않는다 — 이번 결함이 「아파트 문제」로 오독됐다", () => {
    // 같은 좌표를 유형만 바꿔 넣으면 결과가 같아야 한다.
    const asApt = summarizeMarketViewport([{ type: "apt", groups: APT }], TIGHT);
    const asLand = summarizeMarketViewport([{ type: "land", groups: APT }], TIGHT);
    expect(asLand.outside).toBe(asApt.outside);
    expect(asApt.outsideByType).toEqual({ apt: 4 });
    expect(asLand.outsideByType).toEqual({ land: 4 });
  });

  it("★L5 경계 위 좌표는 화면 안으로 센다(경계 양방향)", () => {
    const box: MarketViewportBounds = { south: 0, west: 0, north: 10, east: 10 };
    const corners = [
      { lat: 0, lon: 0 }, { lat: 10, lon: 10 }, { lat: 0, lon: 10 }, { lat: 10, lon: 0 },
    ];
    const s = summarizeMarketViewport([{ type: "t", groups: corners }], box);
    expect(s.outside).toBe(0);
    expect(s.inView).toBe(4);
  });

  it("좌표가 유한수가 아니면 어느 쪽으로도 세지 않고 indeterminate 로 분리한다", () => {
    const s = summarizeMarketViewport(
      [{ type: "t", groups: [{ lat: 5, lon: 5 }, { lat: null, lon: 5 }, { lat: NaN, lon: 5 }] }],
      { south: 0, west: 0, north: 10, east: 10 },
    );
    expect(s.total).toBe(3);
    expect(s.inView).toBe(1);
    expect(s.outside).toBe(0);
    expect(s.indeterminate).toBe(2);
  });

  it("빈 계획은 조용히 0 — 고지 문구도 없다", () => {
    const s = summarizeMarketViewport([], WIDE);
    expect(s.total).toBe(0);
    expect(marketOffscreenNote(s)).toBe("");
  });
});

describe("marketOffscreenNote", () => {
  it("화면 밖이 있을 때만 말하고, 수를 그대로 싣는다", () => {
    const s = summarizeMarketViewport(PLAN, TIGHT);
    const note = marketOffscreenNote(s);
    expect(note).toContain("5");          // ★값이 실린다(라벨만이 아니라)
    expect(note).toContain("화면 밖");
  });
});
