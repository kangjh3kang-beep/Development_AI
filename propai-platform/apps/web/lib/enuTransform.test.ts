import { describe, it, expect } from "vitest";
import { enuXZ, ringToEnu, boundsEnu } from "./enuTransform";

// 원점(필지중심) 샘플 — 서울 근방
const LON0 = 127.0;
const LAT0 = 37.5;

describe("enuXZ — WGS84→ENU(백엔드 _enu_xz 1:1)", () => {
  it("원점은 [0,0]", () => {
    expect(enuXZ(LON0, LAT0, LON0, LAT0)).toEqual([0, 0]);
  });

  it("경도 +0.001° → 동쪽 +x(위도압축 cos(lat0) 반영), z≈0", () => {
    const [x, z] = enuXZ(LON0 + 0.001, LAT0, LON0, LAT0);
    // 0.001 * 111320 * cos(37.5°) ≈ 88.316 m (백엔드 _enu_xz와 동일)
    expect(x).toBeCloseTo(88.316, 2);
    expect(x).toBeGreaterThan(0);
    expect(z).toBeCloseTo(0, 6);
  });

  it("위도 +0.001° → 북쪽은 −z(남=+z, Three.js 우수좌표), x≈0", () => {
    const [x, z] = enuXZ(LON0, LAT0 + 0.001, LON0, LAT0);
    expect(z).toBeCloseTo(-111.32, 2);
    expect(z).toBeLessThan(0);
    expect(x).toBeCloseTo(0, 6);
  });
});

describe("ringToEnu — ring[(lon,lat)]→ENU[[x,z]] 소수3자리", () => {
  it("ring을 ENU로 변환(소수 3자리·백엔드 _ring_to_enu 정합)", () => {
    const ring: [number, number][] = [
      [LON0, LAT0],
      [LON0 + 0.001, LAT0],
      [LON0, LAT0 + 0.001],
    ];
    const out = ringToEnu(ring, LON0, LAT0);
    expect(out).toHaveLength(3);
    expect(out[0]).toEqual([0, 0]);
    expect(out[1][0]).toBeCloseTo(88.316, 2);
    // 소수 3자리 반올림 보장(결정론)
    out.forEach(([x, z]) => {
      expect(Math.round(x * 1000) / 1000).toBe(x);
      expect(Math.round(z * 1000) / 1000).toBe(z);
    });
  });

  it("빈 입력은 빈 배열(throw 없음)", () => {
    expect(ringToEnu([], LON0, LAT0)).toEqual([]);
  });

  it("무효 좌표는 건너뛴다(가짜 점 금지)", () => {
    const ring = [
      [Number.NaN, LAT0],
      [LON0, LAT0],
    ] as [number, number][];
    expect(ringToEnu(ring, LON0, LAT0)).toEqual([[0, 0]]);
  });
});

describe("boundsEnu — ENU 점들의 bbox(footprint 스케일·카메라 프레이밍)", () => {
  it("점들의 min/max", () => {
    expect(boundsEnu([[0, 0], [10, -5], [-3, 8]])).toEqual({
      minX: -3,
      minZ: -5,
      maxX: 10,
      maxZ: 8,
    });
  });
  it("빈 입력은 null(가짜 bbox 금지)", () => {
    expect(boundsEnu([])).toBeNull();
  });
});
