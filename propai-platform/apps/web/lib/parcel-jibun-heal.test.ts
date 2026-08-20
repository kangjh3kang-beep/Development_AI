import { describe, expect, it, vi } from "vitest";

import {
  collectJibunHealTargets,
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

// ────────────────────────────────────────────────────────────────────────────
// 적대리뷰 HIGH — 대표점이 **날조를 만든다**.
// `geometryRepresentativePoint` 는 **경계상자 중심**이라 오목·부정형 필지에서는 폴리곤 **밖**에
// 떨어진다. 밖의 점으로 parcel-at-point 를 때리면 **이웃 필지**의 PNU·주소가 오고, 치유가
// 그걸 채택해 영속한다 — 이 모듈이 없애겠다 선언한 "조용한 오답" 그 자체.
// ★두 모집단(볼록 / 오목)이 **다른 결과**를 내야 한다. 같으면 가드를 지워도 통과한다.
// ────────────────────────────────────────────────────────────────────────────
describe("jibunHealAnchor — 대표점이 자기 폴리곤 밖이면 쓰지 않는다", () => {
  /** 볼록(사각형) — 경계상자 중심이 안에 있다. */
  const convex = {
    type: "Polygon",
    coordinates: [[
      [127.060, 37.170], [127.062, 37.170], [127.062, 37.172], [127.060, 37.172], [127.060, 37.170],
    ]],
  };
  /** 오목(U자) — 경계상자 중심이 **홈 안**, 즉 폴리곤 **밖**에 떨어진다. */
  const concave = {
    type: "Polygon",
    coordinates: [[
      [127.060, 37.170], [127.063, 37.170], [127.063, 37.173], [127.062, 37.173],
      [127.062, 37.171], [127.061, 37.171], [127.061, 37.173], [127.060, 37.173],
      [127.060, 37.170],
    ]],
  };

  it("볼록 필지 — 대표점이 안이므로 해석한다", () => {
    const anchor = jibunHealAnchor({ pnu: null, address: "경기도 오산시 내삼미동", geometry: convex });
    expect(anchor).not.toBeNull();
    expect(anchor!.lat).toBeCloseTo(37.171, 4);
    expect(anchor!.lon).toBeCloseTo(127.061, 4);
  });

  it("★오목 필지 — 대표점이 밖이므로 **해석하지 않는다**(이웃 필지 PNU 채택 차단)", () => {
    expect(jibunHealAnchor({ pnu: null, address: "경기도 오산시 내삼미동", geometry: concave })).toBeNull();
  });

  it("★두 모집단이 다른 결과다 — 같으면 가드를 지워도 통과한다", () => {
    const a = jibunHealAnchor({ pnu: null, address: "동단위", geometry: convex });
    const b = jibunHealAnchor({ pnu: null, address: "동단위", geometry: concave });
    expect(a).not.toBeNull();
    expect(b).toBeNull();
  });

  it("★오목 필지는 **요청 자체가 나가지 않는다**(대조군: 볼록은 나간다)", async () => {
    const resolve = vi.fn(async () => ({ pnu: "4137011000104400000", address: "이웃 필지 440" }));
    const parcels: HealableParcel[] = [
      { pnu: null, address: "동단위", geometry: concave },
      { pnu: null, address: "동단위", geometry: convex },
    ];
    expect(countJibunHealTargets(parcels)).toBe(1); // 공허 진리 가드
    const healed = await healParcelJibunByPoint(parcels, resolve);
    expect(resolve).toHaveBeenCalledTimes(1);
    expect(healed.map((h) => h.index)).toEqual([1]); // 볼록(index 1)만 치유
  });

  it("★MultiPolygon 경계도 링을 읽는다(못 읽으면 그 필지는 조용히 치유에서 빠진다)", () => {
    // 분할된 필지는 MultiPolygon 으로 온다. 이 분기가 죽으면 rings=[] 라 anchor 가 null 이 되고
    // **아무 오류 없이** 치유 대상에서 사라진다 — 조용한 기능 소실이라 락이 필요하다.
    const multi = {
      type: "MultiPolygon",
      coordinates: [[[
        [127.060, 37.170], [127.062, 37.170], [127.062, 37.172], [127.060, 37.172], [127.060, 37.170],
      ]]],
    };
    const anchor = jibunHealAnchor({ pnu: null, address: "경기도 오산시 내삼미동", geometry: multi });
    expect(anchor).not.toBeNull();
    expect(anchor!.lat).toBeCloseTo(37.171, 4);
  });

  it("경계 형식을 못 읽으면 쓰지 않는다(모르면 안 쓴다)", () => {
    expect(jibunHealAnchor({ pnu: null, address: "동단위", geometry: { type: "Point", coordinates: [1, 2] } })).toBeNull();
    expect(jibunHealAnchor({ pnu: null, address: "동단위", geometry: null })).toBeNull();
  });
});

// ────────────────────────────────────────────────────────────────────────────
// 백엔드 실측(2026-08-20, parcel_excel_service): 동 단위 주소 행은
//   `p["lat"]/p["lon"]` 을 **먼저 박고** 그 뒤 "번지 없이 동·읍·면 단위" 가드로 `p["pnu"]` 를
//   보류한다 → **PNU 는 비었는데 좌표는 77행이 전부 동 대표지점**일 수 있다.
// 그 좌표로 해석하면 77행이 전부 같은 필지를 받는다 — 이 모듈이 없애겠다 선언한 그 오답.
// ★서로 다른 필지가 같은 좌표를 가질 수 없다 → 겹치면 **파생 좌표**이므로 쓰지 않는다.
// ────────────────────────────────────────────────────────────────────────────
describe("좌표를 공유하는 필지는 좌표로 해석하지 않는다", () => {
  const SHARED = { lat: 37.17603283713923, lon: 127.06444331120568 }; // 실측 동 대표지점

  it("★같은 좌표를 가진 77행은 **한 건도** 대상이 아니다", () => {
    const parcels: HealableParcel[] = Array.from({ length: 77 }, () => ({
      pnu: null, address: "경기도 오산시 내삼미동", ...SHARED,
    }));
    // 공허 진리 가드: 좌표가 없어서 0인 게 아니다 — 앵커 자체는 전부 산출된다.
    expect(parcels.every((p) => jibunHealAnchor(p) !== null)).toBe(true);
    expect(countJibunHealTargets(parcels)).toBe(0);
  });

  it("★대조군: 좌표가 서로 다르면 전부 대상이다(두 모집단이 갈린다)", () => {
    const parcels: HealableParcel[] = Array.from({ length: 77 }, (_, i) => ({
      pnu: null, address: "경기도 오산시 내삼미동", lat: 37.17 + i / 10000, lon: 127.06,
    }));
    expect(countJibunHealTargets(parcels)).toBe(77);
  });

  it("★공유 좌표 행만 빠지고 고유 좌표 행은 남는다(전부 버리지 않는다)", () => {
    const parcels: HealableParcel[] = [
      { pnu: null, address: "동단위", ...SHARED },
      { pnu: null, address: "동단위", ...SHARED },
      { pnu: null, address: "동단위", lat: 37.9, lon: 127.9 },
    ];
    expect(collectJibunHealTargets(parcels).map((t) => t.index)).toEqual([2]);
  });

  it("★공유 좌표로는 **요청이 나가지 않는다**(대조군: 고유 좌표는 나간다)", async () => {
    const resolve = vi.fn(async () => ({ pnu: "4137011000101140001", address: "내삼미동 114-1" }));
    const healed = await healParcelJibunByPoint(
      [
        { pnu: null, address: "동단위", ...SHARED },
        { pnu: null, address: "동단위", ...SHARED },
        { pnu: null, address: "동단위", lat: 37.9, lon: 127.9 },
      ],
      resolve,
    );
    expect(resolve).toHaveBeenCalledTimes(1);
    expect(resolve).toHaveBeenCalledWith({ lat: 37.9, lon: 127.9 });
    expect(healed.map((h) => h.index)).toEqual([2]);
  });
});
