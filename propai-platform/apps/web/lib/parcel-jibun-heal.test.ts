import { describe, expect, it, vi } from "vitest";

import {
  countJibunHealTargets,
  healParcelJibunByPoint,
  jibunHealAnchor,
  type HealableParcel,
} from "./parcel-jibun-heal";

/** GeoJSON 폴리곤(대표점 계산용) — 좌표는 [lon, lat] 순서. */
const polygon = {
  type: "Polygon",
  coordinates: [[[127.06, 37.17], [127.07, 37.17], [127.07, 37.18], [127.06, 37.18], [127.06, 37.17]]],
};

// ── 네 모집단(★서로 **다른** 처방을 받아야 한다) ──
const withPnu: HealableParcel = { pnu: "4137011000104670001", address: "경기도 오산시 내삼미동" };
const withJibunAddress: HealableParcel = { pnu: null, address: "경기도 오산시 내삼미동 114-1" };
const withCoords: HealableParcel = { pnu: null, address: "경기도 오산시 내삼미동", lat: 37.1789, lon: 127.0611 };
const withGeometryOnly: HealableParcel = { pnu: null, address: "경기도 오산시 내삼미동", geometry: polygon };
const anchorless: HealableParcel = { pnu: null, address: "경기도 오산시 내삼미동" };
/** 실제 오염값: PNU 칸에 주소가 들어앉은 필지 — 앵커 없음과 **같은 취급**이어야 한다. */
const fakePnu: HealableParcel = { pnu: "경기도 오산시 내삼미동", address: "경기도 오산시 내삼미동" };

describe("jibunHealAnchor — 앵커 우선순위", () => {
  it("(A) 진짜 PNU 보유 → 치유 대상 아님", () => {
    expect(jibunHealAnchor(withPnu)).toBeNull();
  });

  it("(B) 주소에 지번 보유 → 치유 대상 아님", () => {
    expect(jibunHealAnchor(withJibunAddress)).toBeNull();
  });

  it("(C) 좌표 보유 → 그 좌표로 해석", () => {
    expect(jibunHealAnchor(withCoords)).toEqual({ lat: 37.1789, lon: 127.0611 });
  });

  it("(D) 경계만 보유 → 대표점을 **일시** 계산(영속 금지 — 반환값일 뿐 입력을 바꾸지 않는다)", () => {
    const point = jibunHealAnchor(withGeometryOnly);
    expect(point).not.toBeNull();
    expect(point!.lat).toBeCloseTo(37.175, 3);
    expect(point!.lon).toBeCloseTo(127.065, 3);
    expect(withGeometryOnly.lat).toBeUndefined(); // 입력에 좌표를 심지 않았다
  });

  it("★(E) 앵커가 동 단위 주소뿐 → null(지오코딩으로 채우지 않는다 — 무날조)", () => {
    expect(jibunHealAnchor(anchorless)).toBeNull();
  });

  it("★가짜 PNU 는 PNU 로 인정하지 않는다(좌표가 있으면 치유 대상)", () => {
    expect(jibunHealAnchor(fakePnu)).toBeNull(); // 좌표도 없으니 앵커 없음
    expect(jibunHealAnchor({ ...fakePnu, lat: 37.1, lon: 127.0 })).toEqual({ lat: 37.1, lon: 127.0 });
  });
});

describe("countJibunHealTargets — 이펙트 의존성(배열 아님)", () => {
  it("치유 대상만 센다", () => {
    expect(countJibunHealTargets([withPnu, withJibunAddress, withCoords, withGeometryOnly, anchorless])).toBe(2);
  });

  it("★치유가 성공하면 수가 줄어든다 — 그래서 이펙트 루프가 멈춘다", () => {
    const before = [withCoords, anchorless];
    const after = [{ ...withCoords, pnu: "4137011000104670001" }, anchorless];
    expect(countJibunHealTargets(before)).toBe(1);
    expect(countJibunHealTargets(after)).toBe(0);
  });
});

describe("healParcelJibunByPoint — 세 모집단이 **다른 결과**를 낸다", () => {
  it("★좌표 보유만 해석되고, 앵커 없는 필지는 **요청 자체가 나가지 않는다**", async () => {
    const resolve = vi.fn(async () => ({
      pnu: "4137011000104400000",
      address: "경기도 오산시 내삼미동 440",
    }));
    const parcels = [withPnu, withJibunAddress, withCoords, anchorless];

    const healed = await healParcelJibunByPoint(parcels, resolve);

    // 공허 진리 가드: 치유 대상이 실제로 존재했는가.
    expect(countJibunHealTargets(parcels)).toBe(1);
    expect(resolve).toHaveBeenCalledTimes(1);
    expect(resolve).toHaveBeenCalledWith({ lat: 37.1789, lon: 127.0611 });
    // ★날조 금지 경계: 동 단위 주소 필지의 좌표(=없음)로는 어떤 요청도 만들지 않는다.
    expect(healed).toEqual([{ index: 2, pnu: "4137011000104400000", address: "경기도 오산시 내삼미동 440" }]);
  });

  it("★서버가 필지를 특정하지 못하면(PNU 없음/형식 아님) 지어내지 않는다", async () => {
    const noPnu = vi.fn(async () => ({ pnu: null, address: "경기도 오산시 내삼미동" }));
    expect(await healParcelJibunByPoint([withCoords], noPnu)).toEqual([]);

    const badPnu = vi.fn(async () => ({ pnu: "내삼미동", address: "경기도 오산시 내삼미동" }));
    expect(await healParcelJibunByPoint([withCoords], badPnu)).toEqual([]);

    const nothing = vi.fn(async () => null);
    expect(await healParcelJibunByPoint([withCoords], nothing)).toEqual([]);
  });

  it("한 필지의 실패가 나머지를 막지 않는다", async () => {
    const a = { pnu: null, address: "동단위", lat: 1, lon: 1 };
    const b = { pnu: null, address: "동단위", lat: 2, lon: 2 };
    const resolve = vi.fn(async (p: { lat: number; lon: number }) => {
      if (p.lat === 1) throw new Error("네트워크 실패");
      return { pnu: "4137011000104400000", address: "경기도 오산시 내삼미동 440" };
    });
    const healed = await healParcelJibunByPoint([a, b], resolve);
    expect(healed).toEqual([{ index: 1, pnu: "4137011000104400000", address: "경기도 오산시 내삼미동 440" }]);
  });

  it("★동시 요청 상한(4)을 지킨다 — 실제 신고 프로젝트가 77필지다", async () => {
    let inFlight = 0;
    let peak = 0;
    const parcels: HealableParcel[] = Array.from({ length: 77 }, (_, i) => ({
      pnu: null,
      address: "경기도 오산시 내삼미동",
      lat: 37 + i / 1000,
      lon: 127 + i / 1000,
    }));
    const resolve = vi.fn(async () => {
      inFlight += 1;
      peak = Math.max(peak, inFlight);
      await new Promise((r) => setTimeout(r, 1));
      inFlight -= 1;
      return { pnu: "4137011000104400000", address: "경기도 오산시 내삼미동 440" };
    });

    // 공허 진리 가드: 상한을 넘길 수 있는 만큼의 대상이 실제로 있는가.
    expect(countJibunHealTargets(parcels)).toBe(77);
    const healed = await healParcelJibunByPoint(parcels, resolve, { limit: 4 });
    expect(healed).toHaveLength(77);
    expect(resolve).toHaveBeenCalledTimes(77);
    expect(peak).toBeLessThanOrEqual(4);
    expect(peak).toBe(4); // 상한을 실제로 채웠다(1개씩 직렬 처리로 통과하는 공허한 초록 차단)
  });

  it("취소되면 남은 요청을 보내지 않는다", async () => {
    let cancelled = false;
    const parcels: HealableParcel[] = Array.from({ length: 20 }, (_, i) => ({
      pnu: null, address: "동단위", lat: 37 + i / 1000, lon: 127,
    }));
    const resolve = vi.fn(async () => {
      cancelled = true; // 첫 응답 직후 취소
      return { pnu: "4137011000104400000", address: null };
    });
    await healParcelJibunByPoint(parcels, resolve, { limit: 1, isCancelled: () => cancelled });
    expect(resolve).toHaveBeenCalledTimes(1);
  });
});
