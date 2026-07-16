import { describe, expect, it } from "vitest";

import { formatDistance, haversineMeters, totalDistanceMeters } from "./satong-measure";

describe("satong-measure", () => {
  it("하버사인 — 위도 0.001도(≈111.2m) 검증(±1m)", () => {
    const d = haversineMeters({ lat: 37.3, lon: 127.08 }, { lat: 37.301, lon: 127.08 });
    expect(d).toBeGreaterThan(110);
    expect(d).toBeLessThan(112.5);
  });

  it("동일 점 거리 0, 점 2개 미만 누적 0", () => {
    const p = { lat: 37.3, lon: 127.08 };
    expect(haversineMeters(p, p)).toBe(0);
    expect(totalDistanceMeters([])).toBe(0);
    expect(totalDistanceMeters([p])).toBe(0);
  });

  it("누적 거리 = 구간 합(왕복 = 편도×2)", () => {
    const a = { lat: 37.3, lon: 127.08 };
    const b = { lat: 37.302, lon: 127.083 };
    const oneWay = haversineMeters(a, b);
    expect(totalDistanceMeters([a, b, a])).toBeCloseTo(oneWay * 2, 6);
  });

  it("표시 포맷 — m/km 경계·비정상 입력", () => {
    expect(formatDistance(532.4)).toBe("532m");
    expect(formatDistance(999.4)).toBe("999m");
    expect(formatDistance(1240)).toBe("1.24km");
    expect(formatDistance(-5)).toBe("0m");
    expect(formatDistance(Number.NaN)).toBe("0m");
  });
});
