/**
 * 등록 증거 해석기 — **붕괴한 신호와 살아남은 신호**를 가르는지 직접 태운다.
 *
 * ★페이지 계약테스트(`multi-parcel/__tests__/CountMismatch.test.tsx`)와 **둘 다** 둔다.
 *   그쪽은 렌더까지 태우지만 스토어를 목으로 세우므로, 판정 자체의 경계값은 여기서 본다.
 */
import { describe, expect, it } from "vitest";
import {
  resolveRegistrationEvidence,
  shouldSuppressSingleParcelClaim,
} from "@/lib/multiparcel-registration-evidence";

const COLLAPSED = { parcelCount: 0, parcels: [] as unknown[] };

describe("resolveRegistrationEvidence", () => {
  it("★활성이 무너지고 스냅샷이 살아 있으면 **스냅샷**을 쓴다(이 함수의 존재 이유)", () => {
    const e = resolveRegistrationEvidence(COLLAPSED, { parcelCount: 2, parcels: [{}, {}] });
    expect(e).toEqual({ registeredCount: 2, source: "snapshot" });
  });

  it("★음성 짝 — 스냅샷도 단일이면 다필지로 보지 않는다", () => {
    // 활성은 위와 **똑같다**. 갈리는 것은 스냅샷뿐 — 두 모집단이 실제로 다른 값을 낸다.
    const e = resolveRegistrationEvidence(COLLAPSED, { parcelCount: 1, parcels: [] });
    expect(e.registeredCount).toBe(1);
    expect(shouldSuppressSingleParcelClaim(e, false)).toBe(false);
  });

  it("활성이 더 크면 활성을 쓴다(사용자가 방금 늘린 선택이 스냅샷보다 최신)", () => {
    const e = resolveRegistrationEvidence({ parcelCount: 3, parcels: [{}, {}, {}] }, { parcelCount: 2, parcels: [{}, {}] });
    expect(e).toEqual({ registeredCount: 3, source: "active" });
  });

  it("동수면 활성을 쓴다(스냅샷으로 뒷걸음질하지 않는다)", () => {
    const e = resolveRegistrationEvidence({ parcelCount: 2, parcels: [{}, {}] }, { parcelCount: 2, parcels: [{}, {}] });
    expect(e.source).toBe("active");
  });

  it("★`parcelCount` 가 없어도 **목록 길이**가 증거다(두 필드는 따로 무너진다)", () => {
    const e = resolveRegistrationEvidence(COLLAPSED, { parcels: [{}, {}] });
    expect(e).toEqual({ registeredCount: 2, source: "snapshot" });
  });

  it("★증거가 하나도 없으면 `0` 이 아니라 **`null`** 이다", () => {
    // 이 저장소 규율: 0 은 "필지가 0개"라는 **거짓 사실**이다. 모르면 모른다고 한다.
    expect(resolveRegistrationEvidence(null, null)).toEqual({ registeredCount: null, source: null });
    expect(resolveRegistrationEvidence(COLLAPSED, COLLAPSED)).toEqual({ registeredCount: null, source: null });
  });

  it("음수·NaN 같은 깨진 값은 증거로 세지 않는다", () => {
    expect(resolveRegistrationEvidence({ parcelCount: -3, parcels: [] }, null).registeredCount).toBeNull();
    expect(resolveRegistrationEvidence({ parcelCount: Number.NaN, parcels: [] }, null).registeredCount).toBeNull();
  });
});

describe("shouldSuppressSingleParcelClaim", () => {
  it("★등록 2 이상 + 화면은 단일 → 단언을 멈춘다", () => {
    expect(shouldSuppressSingleParcelClaim({ registeredCount: 2, source: "snapshot" }, false)).toBe(true);
  });

  it("★화면이 이미 다필지면 고지하지 않는다(중복 고지 방지)", () => {
    // 경계 양쪽을 한 쌍으로 건다 — 상한만 걸면 반대쪽이 무제한이 된다.
    expect(shouldSuppressSingleParcelClaim({ registeredCount: 2, source: "snapshot" }, true)).toBe(false);
  });

  it("★등록이 1이거나 모르면 종전 동작(위양성 방지)", () => {
    expect(shouldSuppressSingleParcelClaim({ registeredCount: 1, source: "active" }, false)).toBe(false);
    expect(shouldSuppressSingleParcelClaim({ registeredCount: null, source: null }, false)).toBe(false);
  });
});
