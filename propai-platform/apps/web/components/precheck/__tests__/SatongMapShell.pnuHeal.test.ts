/**
 * WP-M2 리뷰(HIGH) 근치 회귀 테스트 — pnu/주소 키 이중성 승격(healParcelPnu).
 *
 * 근본(적대 리뷰 지적): 시드 필지(엑셀/지오코딩)는 pnu 미확보 상태로 selectedParcels 에 들어와
 * 멤버십 키가 주소가 된다. autoStage(/zoning/parcel-at-point)는 항상 real 19자리 pnu 를 반환하므로
 * 키가 갈려 "기등록 필지 vs 신규 staged"가 어긋나고("지적 12 ↔ 완료 1추가"), boundary 보강이
 * 도착해도 종전 handleBoundaryEnriched 병합이 기존 pnu 를 그대로 유지해(치유 없음) mergeSatongMapFeatures
 * 기반 "지적 N건" 칩도 같은 물리 필지를 2건으로 쪼갰다. healParcelPnu 는 이 치유를 한 곳(handleBoundaryEnriched)
 * 에서 수행하는 공용 계약이다 — 여기서는 그 실제 export를 직접 검증한다(재구현·마스킹 없음).
 */
import { describe, expect, it } from "vitest";

import { parcelMembershipKey } from "@/components/map/SatongMultiMap";

import { healParcelPnu } from "../SatongMapShell";

describe("healParcelPnu — 기존 pnu 우선, 없을 때만 boundary real pnu로 승격", () => {
  it("기존 pnu가 있으면 그대로 보존한다(real→real 덮어쓰기 금지 — 무날조)", () => {
    expect(healParcelPnu("1111010100100560016", "9999999999999999999")).toBe(
      "1111010100100560016",
    );
  });

  it("기존 pnu가 없으면(null) boundary real pnu로 승격한다", () => {
    expect(healParcelPnu(null, "1111010100100560016")).toBe("1111010100100560016");
  });

  it("기존 pnu가 빈 문자열이어도 boundary real pnu로 승격한다", () => {
    expect(healParcelPnu("", "1111010100100560016")).toBe("1111010100100560016");
  });

  it("둘 다 없으면 null(가짜 pnu 날조 금지)", () => {
    expect(healParcelPnu(null, undefined)).toBeNull();
    expect(healParcelPnu(undefined, null)).toBeNull();
  });
});

describe("★HIGH 근치 통합 검증 — healParcelPnu 적용 전/후 선택 SSOT 멤버십 정합", () => {
  // handleBoundaryEnriched와 동일한 두 단계를 실제 export(healParcelPnu·parcelMembershipKey)로
  // 재현한다: ① 주소로 boundary feature 매칭 ② pnu 필드를 healParcelPnu로 승격.
  const projectParcels = Array.from({ length: 12 }, (_, i) => ({
    pnu: i === 0 ? null : `111101010010056${String(i).padStart(4, "0")}`,
    address: i === 0 ? "서울특별시 종로구 청진동 56-16" : `청진동 56-${i}`,
  })); // 첫 필지만 시드(엑셀/지오코딩) — pnu 미확보, 나머지 11건은 이미 real pnu 보유.

  const boundaryFeature = { pnu: "1111010100100560016", address: "서울특별시 종로구 청진동 56-16" };

  it("치유 전: 시드 필지의 멤버십 키(주소)와 boundary/autoStage의 real pnu 키가 어긋난다", () => {
    const seedKey = parcelMembershipKey(projectParcels[0]); // pnu=null → 주소 키
    const realKey = parcelMembershipKey(boundaryFeature); // pnu 존재 → real pnu 키
    expect(seedKey).not.toBe(realKey); // 버그의 근본 — 같은 물리 필지인데 키가 다름
  });

  it("치유 후: handleBoundaryEnriched와 동일한 주소매칭+healParcelPnu 승격을 거치면 키가 수렴한다", () => {
    const healed = projectParcels.map((p) => {
      if (p.address.trim() !== boundaryFeature.address.trim()) return p;
      return { ...p, pnu: healParcelPnu(p.pnu, boundaryFeature.pnu) };
    });
    const healedSeedKey = parcelMembershipKey(healed[0]);
    const realKey = parcelMembershipKey(boundaryFeature);
    expect(healedSeedKey).toBe(realKey); // 수렴 — 이후 autoStage/CTA/merge 카운트가 모두 정합

    // 부가 검증: 이미 real pnu였던 나머지 11건은 승격 대상이 아니므로 무변화(원본 보존).
    for (let i = 1; i < 12; i += 1) {
      expect(healed[i].pnu).toBe(projectParcels[i].pnu);
    }
  });
});
