/**
 * 매스 시드 인계(W4) — 페이로드 생성·저장·판정의 **정직 계약**을 잠근다.
 *
 * 이 모듈이 틀리면 사용자는 "지도에서 고른 대로 설계가 시작됐다"고 믿는데 실제로는
 * ①아무것도 안 넘어갔거나 ②**다른 필지**의 선택이 넘어간다. 후자가 특히 위험하다 —
 * 화면은 정상으로 보이고 숫자만 틀린다.
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  MASS_SEED_MAX_AGE_MS,
  SATONG_MASS_SEED_KEY,
  buildMassSeedHandoff,
  massSeedAppliesTo,
  readMassSeedHandoff,
  writeMassSeedHandoff,
} from "@/lib/satong-mass-seed";

const NOW = 1_800_000_000_000;

beforeEach(() => {
  window.sessionStorage.clear();
});

describe("buildMassSeedHandoff — 없는 값을 만들지 않는다", () => {
  it("층수가 있으면 페이로드를 만든다(라벨은 종류+각도)", () => {
    const h = buildMassSeedHandoff({
      pnu: "4711135022200010001", address: "포항시 남구 호미곶면 대보리 산1-1",
      kind: "판상형", angleDeg: 25.3, floors: 15, now: NOW,
    });
    expect(h).not.toBeNull();
    expect(h!.targetFloors).toBe(15);
    expect(h!.optionLabel).toBe("판상형 25°");
    expect(h!.pnu).toBe("4711135022200010001");
  });

  it("★층수가 없거나 유효하지 않으면 만들지 않는다(빈 인계로 수신측을 헛돌게 하지 않는다)", () => {
    const base = { pnu: "p", address: "a", kind: "판상형", angleDeg: 0, now: NOW };
    expect(buildMassSeedHandoff({ ...base, floors: null })).toBeNull();
    expect(buildMassSeedHandoff({ ...base, floors: 0 })).toBeNull();
    expect(buildMassSeedHandoff({ ...base, floors: -2 })).toBeNull();
    expect(buildMassSeedHandoff({ ...base, floors: Number.NaN })).toBeNull();
  });

  it("각도가 없으면 라벨에 각도를 지어내지 않는다", () => {
    const h = buildMassSeedHandoff({ kind: "탑상형", angleDeg: null, floors: 12, now: NOW });
    expect(h!.optionLabel).toBe("탑상형");
  });

  it("종류가 비면 '배치안'으로만 표기한다(빈 문자열 라벨 금지)", () => {
    const h = buildMassSeedHandoff({ kind: "  ", angleDeg: null, floors: 12, now: NOW });
    expect(h!.optionLabel).toBe("배치안");
  });

  it("층수는 정수로 반올림한다(엔진 시드는 층 단위)", () => {
    expect(buildMassSeedHandoff({ kind: "판상형", floors: 14.6, now: NOW })!.targetFloors).toBe(15);
  });
});

describe("write/read — 만료·파손은 조용히 되살리지 않는다", () => {
  const H = () => buildMassSeedHandoff({ pnu: "p1", address: "a1", kind: "판상형", floors: 15, now: NOW })!;

  it("저장한 것을 그대로 읽는다", () => {
    writeMassSeedHandoff(H());
    expect(readMassSeedHandoff(NOW)).toMatchObject({ targetFloors: 15, pnu: "p1" });
  });

  it("★신선도 한도를 넘기면 null — 한참 전 선택이 뒤늦게 설계에 꽂히면 조용한 오도가 된다", () => {
    writeMassSeedHandoff(H());
    expect(readMassSeedHandoff(NOW + MASS_SEED_MAX_AGE_MS - 1)).not.toBeNull();
    expect(readMassSeedHandoff(NOW + MASS_SEED_MAX_AGE_MS + 1)).toBeNull();
  });

  it("형태가 깨졌거나 JSON이 아니면 null(던지지 않는다)", () => {
    window.sessionStorage.setItem(SATONG_MASS_SEED_KEY, "not-json");
    expect(readMassSeedHandoff(NOW)).toBeNull();
    window.sessionStorage.setItem(SATONG_MASS_SEED_KEY, JSON.stringify({ targetFloors: 0, optionLabel: "x", savedAt: NOW }));
    expect(readMassSeedHandoff(NOW)).toBeNull();
    window.sessionStorage.setItem(SATONG_MASS_SEED_KEY, JSON.stringify({ nope: 1 }));
    expect(readMassSeedHandoff(NOW)).toBeNull();
  });

  it("null 저장은 제거다(인계 취소)", () => {
    writeMassSeedHandoff(H());
    writeMassSeedHandoff(null);
    expect(readMassSeedHandoff(NOW)).toBeNull();
  });
});

describe("massSeedAppliesTo — ★다른 필지의 선택을 조용히 적용하지 않는다", () => {
  const H = (over: Partial<{ pnu: string | null; address: string | null }> = {}) => ({
    pnu: "p1", address: "a1", targetFloors: 15, optionLabel: "판상형 25°", savedAt: NOW, ...over,
  });

  it("같은 PNU면 적용한다", () => {
    expect(massSeedAppliesTo(H(), { pnu: "p1", address: "다른주소" })).toBe(true);
  });

  it("★PNU가 다르면 적용하지 않는다(주소가 같아 보여도 PNU가 우선)", () => {
    expect(massSeedAppliesTo(H(), { pnu: "p2", address: "a1" })).toBe(false);
  });

  it("PNU가 없으면 주소로 판정한다", () => {
    expect(massSeedAppliesTo(H({ pnu: null }), { address: "a1" })).toBe(true);
    expect(massSeedAppliesTo(H({ pnu: null }), { address: "a2" })).toBe(false);
  });

  it("★양쪽 다 식별자가 없으면 **적용하지 않는다**(판정 불가를 낙관으로 흘리지 않는다)", () => {
    expect(massSeedAppliesTo(H({ pnu: null, address: null }), {})).toBe(false);
    expect(massSeedAppliesTo(H({ pnu: null, address: null }), { pnu: "p1", address: "a1" })).toBe(false);
  });

  it("인계가 없으면 false", () => {
    expect(massSeedAppliesTo(null, { pnu: "p1" })).toBe(false);
  });
});
