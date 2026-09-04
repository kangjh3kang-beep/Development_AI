import { describe, expect, it } from "vitest";

import { formatAreaSqm, formatDistance, haversineMeters, polygonAreaSqm, totalDistanceMeters } from "./satong-measure";

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

  it("면적(I6) — 100m×100m 정사각 ≈ 10,000㎡(±1%)·점 3개 미만 0·회전순서 무관(절대값)", () => {
    // 위도 0.001°≈111.2m/경도는 cos(lat) 보정 — 약 100m 변을 위경도로 구성.
    const lat0 = 37.3;
    const dLat = 100 / 111_195; // ≈0.000899°
    const dLon = 100 / (111_195 * Math.cos((lat0 * Math.PI) / 180));
    const square = [
      { lat: lat0, lon: 127.08 },
      { lat: lat0 + dLat, lon: 127.08 },
      { lat: lat0 + dLat, lon: 127.08 + dLon },
      { lat: lat0, lon: 127.08 + dLon },
    ];
    const area = polygonAreaSqm(square);
    expect(area).toBeGreaterThan(9_900);
    expect(area).toBeLessThan(10_100);
    expect(polygonAreaSqm(square.slice(0, 2))).toBe(0);
    expect(polygonAreaSqm([...square].reverse())).toBeCloseTo(area, 6); // 방향 무관
  });

  it("면적 표시 포맷 — ㎡(평)·비정상 0㎡", () => {
    expect(formatAreaSqm(3305.785)).toBe("3,306㎡ (1000.0평)");
    expect(formatAreaSqm(0)).toBe("0㎡");
    expect(formatAreaSqm(Number.NaN)).toBe("0㎡");
  });

  it("표시 포맷 — m/km 경계·비정상 입력", () => {
    expect(formatDistance(532.4)).toBe("532m");
    expect(formatDistance(999.4)).toBe("999m");
    expect(formatDistance(1240)).toBe("1.24km");
    expect(formatDistance(-5)).toBe("0m");
    expect(formatDistance(Number.NaN)).toBe("0m");
  });
});
