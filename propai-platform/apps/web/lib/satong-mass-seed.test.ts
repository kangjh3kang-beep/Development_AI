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
      kind: "판상형", angleDeg: 25.3, floors: 15, areaSqm: 1000, now: NOW,
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
  const H = () => buildMassSeedHandoff({ pnu: "p1", address: "a1", kind: "판상형", floors: 15, areaSqm: 1000, now: NOW })!;

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

// ★PNU 는 **19자리 숫자**다. 종전 픽스처의 `"p1"`/`"p2"` 는 PNU 가 아니어서, 정체성 판정이
//   임의 문자열로도 동작한다는 사실을 가려 주고 있었다(픽스처가 결함을 숨긴 형태).
const P1 = "4137011000104670001";
const P2 = "4137011000104670002";

describe("massSeedAppliesTo — ★다른 필지의 선택을 조용히 적용하지 않는다", () => {
  const H = (over: Partial<{ pnu: string | null; address: string | null; areaSqm: number | null }> = {}) => ({
    pnu: P1, address: "a1", areaSqm: 1000, targetFloors: 15,
    optionLabel: "판상형 25°", savedAt: NOW, ...over,
  });
  const CUR = (over: Record<string, unknown> = {}) => ({ pnu: P1, address: "a1", areaSqm: 1000, ...over });

  it("같은 PNU·같은 면적이면 적용한다", () => {
    expect(massSeedAppliesTo(H(), CUR({ address: "다른주소" }))).toBe(true);
  });

  it("★PNU가 다르면 적용하지 않는다(주소가 같아 보여도 PNU가 우선)", () => {
    expect(massSeedAppliesTo(H(), CUR({ pnu: P2 }))).toBe(false);
  });

  // ────────────────────────────────────────────────────────────────────────
  // 2026-09-02 — PNU 칸의 상태는 **셋**이다: 유효 · 없음 · **오염**.
  //   종전 픽스처는 `"p1"`/`"p2"`(PNU 가 아닌 문자열)를 정체성으로 썼고, 코드도 참/거짓만
  //   봐서 **오염이 유효로 취급**됐다. 라이브 실측(2026-09-02, 292필지): 오염 5건 —
  //   `'◀ 전성결'`(성명) · `'store-rep-용인시 …'`(주소 파생 합성 id).
  //   ★오염은 「없음」으로 뭉개지 않는다 — 주소로 떨어뜨리면 동 단위 주소를 공유하는
  //   **서로 다른 필지**에 시드가 과잉 적용된다. 이 가드는 모르면 **미적용**이 옳다.
  // ────────────────────────────────────────────────────────────────────────
  it("★오염된 PNU 는 정체성이 아니다 — 주소가 같아도 적용하지 않는다(fail-closed)", () => {
    for (const dirty of ["◀ 전성결", "store-rep-a1", "p1", "413701100010467000"]) {
      // 수신측만 오염
      expect(massSeedAppliesTo(H(), CUR({ pnu: dirty }))).toBe(false);
      // 발신측만 오염
      expect(massSeedAppliesTo(H({ pnu: dirty }), CUR())).toBe(false);
      // 양쪽이 **같은 문자열로** 오염돼도 — 종전엔 `===` 로 참이 됐다
      expect(massSeedAppliesTo(H({ pnu: dirty }), CUR({ pnu: dirty }))).toBe(false);
    }
  });

  it("★대조군 — 「오염」과 「없음」은 다른 상태다(오염을 없음으로 뭉개면 이 대비가 무너진다)", () => {
    // 없음 → 주소로 판정해서 **적용된다**
    expect(massSeedAppliesTo(H({ pnu: null }), { address: "a1", areaSqm: 1000 })).toBe(true);
    // 오염 → 같은 주소인데도 **적용되지 않는다**
    expect(massSeedAppliesTo(H({ pnu: "store-rep-a1" }), { address: "a1", areaSqm: 1000 })).toBe(false);
  });

  it("PNU가 없으면 주소로 판정한다", () => {
    expect(massSeedAppliesTo(H({ pnu: null }), { address: "a1", areaSqm: 1000 })).toBe(true);
    expect(massSeedAppliesTo(H({ pnu: null }), { address: "a2", areaSqm: 1000 })).toBe(false);
  });

  it("★주소는 **정규화**해 비교한다 — 진입 경로마다 공백이 달라 무표시 위양성이 됐다(R1 MEDIUM-2)", () => {
    expect(
      massSeedAppliesTo(H({ pnu: null, address: "포항시  남구   대보리 산1-1 " }),
        { address: "포항시 남구 대보리 산1-1", areaSqm: 1000 }),
    ).toBe(true);
  });

  it("★양쪽 다 식별자가 없으면 **적용하지 않는다**(판정 불가를 낙관으로 흘리지 않는다)", () => {
    expect(massSeedAppliesTo(H({ pnu: null, address: null }), { areaSqm: 1000 })).toBe(false);
    expect(massSeedAppliesTo(H({ pnu: null, address: null }), CUR())).toBe(false);
  });

  it("★★면적이 다르면 적용하지 않는다 — 다필지 합산 부지에 단일필지 층수 오적용 차단(R1 HIGH-3)", () => {
    // 대표필지(parcels[0]) 주소는 일치하지만 설계 부지는 합산 면적이다.
    expect(massSeedAppliesTo(H({ areaSqm: 500 }), CUR({ areaSqm: 2000 }))).toBe(false);
    // 반올림·재계산 오차(2%)는 같은 부지로 본다(위양성 방지).
    expect(massSeedAppliesTo(H({ areaSqm: 1000 }), CUR({ areaSqm: 1015 }))).toBe(true);
  });

  it("★면적이 한쪽이라도 없으면 적용하지 않는다(다필지 여부 판정 불가 → 낙관 금지)", () => {
    expect(massSeedAppliesTo(H({ areaSqm: null }), CUR())).toBe(false);
    expect(massSeedAppliesTo(H(), CUR({ areaSqm: null }))).toBe(false);
  });

  it("인계가 없으면 false", () => {
    expect(massSeedAppliesTo(null, CUR())).toBe(false);
  });
});
