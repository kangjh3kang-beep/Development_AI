import { describe, expect, it } from "vitest";

import {
  clampClickMenuPosition,
  findFeatureAtPoint,
  pointInLeafletRings,
  shortJibunLabel,
} from "./satong-click-menu";

const CONTAINER = { width: 800, height: 600 };
const MENU = { width: 224, height: 180 };

describe("clampClickMenuPosition", () => {
  it("중앙 클릭 — 클릭점 아래 12px에 앵커", () => {
    const pos = clampClickMenuPosition({ x: 400, y: 200 }, CONTAINER, MENU);
    expect(pos).toEqual({ left: 400, top: 212 });
  });

  it("좌우 가장자리 — 메뉴 절반+여백 안쪽으로 클램프", () => {
    expect(clampClickMenuPosition({ x: 5, y: 200 }, CONTAINER, MENU).left).toBe(120);
    expect(clampClickMenuPosition({ x: 795, y: 200 }, CONTAINER, MENU).left).toBe(680);
  });

  it("하단 공간 부족 — 클릭점 위로 뒤집는다", () => {
    const pos = clampClickMenuPosition({ x: 400, y: 560 }, CONTAINER, MENU);
    expect(pos.top).toBe(560 - 12 - MENU.height);
  });

  it("상하 모두 좁아도 최소 여백(8px) 아래로는 안 내려간다", () => {
    const pos = clampClickMenuPosition({ x: 400, y: 100 }, { width: 800, height: 150 }, MENU);
    expect(pos.top).toBe(8);
  });
});

describe("shortJibunLabel", () => {
  it("전체 주소 → 동+지번 2토큰", () => {
    expect(shortJibunLabel("경기도 용인시 수지구 신봉동 56-16")).toBe("신봉동 56-16");
  });
  it("2토큰 이하 주소는 그대로, 빈 값은 폴백", () => {
    expect(shortJibunLabel("신봉동 886")).toBe("신봉동 886");
    expect(shortJibunLabel("886")).toBe("886");
    expect(shortJibunLabel("")).toBe("필지");
    expect(shortJibunLabel(null)).toBe("필지");
    expect(shortJibunLabel(undefined, "선택지")).toBe("선택지");
  });
});

describe("pointInLeafletRings / findFeatureAtPoint", () => {
  // 단순 사각 링(lat 37.30~37.31, lon 127.08~127.09)
  const square: Array<Array<[number, number]>> = [
    [
      [37.3, 127.08],
      [37.31, 127.08],
      [37.31, 127.09],
      [37.3, 127.09],
    ],
  ];

  it("내부/외부/짝홀(구멍) 판정", () => {
    expect(pointInLeafletRings(37.305, 127.085, square)).toBe(true);
    expect(pointInLeafletRings(37.32, 127.085, square)).toBe(false);
    const withHole: Array<Array<[number, number]>> = [
      ...square,
      [
        [37.303, 127.083],
        [37.307, 127.083],
        [37.307, 127.087],
        [37.303, 127.087],
      ],
    ];
    expect(pointInLeafletRings(37.305, 127.085, withHole)).toBe(false); // 구멍 안 = 외부
    expect(pointInLeafletRings(37.3015, 127.0815, withHole)).toBe(true); // 링과 구멍 사이
  });

  it("findFeatureAtPoint — 첫 매치 피처 반환, 무기하 피처는 건너뜀", () => {
    const features = [
      { address: "무기하", zoneType: null, rings: [] as Array<Array<[number, number]>> },
      { address: "신봉동 56-16", zoneType: "자연녹지지역", rings: square },
    ];
    const hit = findFeatureAtPoint(37.305, 127.085, features, (f) => f.rings);
    expect(hit?.address).toBe("신봉동 56-16");
    expect(findFeatureAtPoint(37.4, 127.2, features, (f) => f.rings)).toBeNull();
  });
});
