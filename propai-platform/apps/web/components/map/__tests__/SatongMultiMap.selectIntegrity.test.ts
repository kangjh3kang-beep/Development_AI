/**
 * WP-M2 선택 상태 SSOT + WP-M3 재조회 루프 제거 회귀 테스트.
 *
 * 근본: 칩바 "지적 12건"(selectedParcels) ↔ CTA "완료 1필지"(지도 staged)가 이원화돼,
 * 프로젝트 연결 시 autoStage가 기등록 필지를 staged에 재등록하며 "1필지 추가"가 떴다.
 * 여기서는 봉합의 공용 계약(parcelMembershipKey·CTA 이중표기 파생·selectionBoundaryReady)을 검증한다.
 */
import { describe, expect, it } from "vitest";

import {
  parcelMembershipKey,
  selectionBoundaryReady,
} from "@/components/map/SatongMultiMap";
import type { SatongMapFeature } from "@/lib/satong-map-layers";

describe("WP-M2 parcelMembershipKey — pnu 우선/주소 정규화 폴백", () => {
  it("pnu가 있으면 pnu(trim)를 키로 쓴다", () => {
    expect(parcelMembershipKey({ pnu: " 1111010100100560016 ", address: "무관" })).toBe(
      "1111010100100560016",
    );
  });

  it("pnu가 없으면 주소를 정규화(공백 축약)해 키로 쓴다", () => {
    expect(parcelMembershipKey({ pnu: null, address: "서울   종로구  청진동   56-16" })).toBe(
      "서울 종로구 청진동 56-16",
    );
  });

  it("pnu·주소가 모두 없으면 빈 문자열", () => {
    expect(parcelMembershipKey({ pnu: "", address: "" })).toBe("");
  });
});

describe("WP-M2 CTA 이중표기 파생(신규∖selected · 총=selected+신규)", () => {
  // 실제 컴포넌트 파생과 동일 공식을 공용 헬퍼로 재현해 게이트를 못박는다.
  const selectedKeys = (parcels: Array<{ pnu?: string | null; address?: string | null }>) =>
    new Set(parcels.map(parcelMembershipKey).filter(Boolean));
  const counts = (
    selected: Array<{ pnu?: string | null; address?: string | null }>,
    staged: Array<{ pnu?: string | null; address?: string | null }>,
  ) => {
    const keys = selectedKeys(selected);
    const newStaged = staged.filter((s) => !keys.has(parcelMembershipKey(s)));
    return { newCount: newStaged.length, totalCount: keys.size + newStaged.length };
  };

  const projectParcels = Array.from({ length: 12 }, (_, i) => ({
    pnu: `111101010010056${String(i).padStart(4, "0")}`,
    address: `청진동 56-${i}`,
  }));

  it("12필지 연결 직후 autoStage가 기등록 필지만 담으려 하면 신규 0 · 총 12", () => {
    // autoStage 대상 = 첫 필지(기등록). 멤버십 검사로 staged에서 제외되므로 staged=[].
    const { newCount, totalCount } = counts(projectParcels, []);
    expect(newCount).toBe(0);
    expect(totalCount).toBe(12);
  });

  it("신규 필지 1개를 지도에서 담으면 신규 1 · 총 13", () => {
    const staged = [{ pnu: "1111010100100999999", address: "신규필지 99" }];
    const { newCount, totalCount } = counts(projectParcels, staged);
    expect(newCount).toBe(1);
    expect(totalCount).toBe(13);
  });

  it("기등록 필지를 staged에 넣어도(잔존) 신규에서 제외돼 총이 부풀지 않는다", () => {
    const staged = [projectParcels[0]]; // 이미 selected에 있는 필지
    const { newCount, totalCount } = counts(projectParcels, staged);
    expect(newCount).toBe(0);
    expect(totalCount).toBe(12);
  });
});

describe("WP-M3 selectionBoundaryReady — 나대지 재조회 루프 제거", () => {
  const feat = (over: Partial<SatongMapFeature>): SatongMapFeature => ({
    id: over.pnu || over.address || "f",
    address: over.address || "필지",
    geometry: { type: "Polygon", coordinates: [] },
    ...over,
  });

  it("빈 선택은 준비되지 않음(false)", () => {
    expect(selectionBoundaryReady([])).toBe(false);
  });

  it("모든 필지가 geometry+연식을 가지면 준비 완료(true)", () => {
    expect(
      selectionBoundaryReady([feat({ buildingAgeYears: 30 }), feat({ buildingAgeYears: 12 })]),
    ).toBe(true);
  });

  it("★핵심: 나대지(연식 null)여도 ageStatus로 '조회 시도됨'이면 준비 완료 — 재조회 루프 차단", () => {
    expect(
      selectionBoundaryReady([
        feat({ buildingAgeYears: 30 }),
        feat({ buildingAgeYears: null, ageStatus: "no_building" }),
      ]),
    ).toBe(true);
  });

  it("연식·ageStatus가 모두 없으면(미조회) 준비 안 됨 → 경계 1회 조회 유도", () => {
    expect(
      selectionBoundaryReady([feat({ buildingAgeYears: null, ageStatus: null })]),
    ).toBe(false);
  });

  it("geometry가 없으면 준비 안 됨(경계 보강 필요)", () => {
    expect(
      selectionBoundaryReady([feat({ geometry: undefined, buildingAgeYears: 30 })]),
    ).toBe(false);
  });
});
