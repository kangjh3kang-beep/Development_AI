/**
 * WP-M2 선택 상태 SSOT + WP-M3 재조회 루프 제거 회귀 테스트.
 *
 * 근본: 칩바 "지적 12건"(selectedParcels) ↔ CTA "완료 1필지"(지도 staged)가 이원화돼,
 * 프로젝트 연결 시 autoStage가 기등록 필지를 staged에 재등록하며 "1필지 추가"가 떴다.
 * 여기서는 봉합의 공용 계약(parcelMembershipKey·CTA 이중표기 파생·selectionBoundaryReady)을 검증한다.
 */
import { describe, expect, it } from "vitest";

import {
  isSameSpotAsAny,
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

  // ★리뷰(HIGH) 반영 — 무날조: 위 projectParcels는 전부 real pnu라 pnu/주소 키 이중성
  // (시드 필지 pnu 미확보 → 합성/주소 키 vs autoStage의 real pnu 키 불일치)을 가려 결함을
  // 은폐했다. 여기서는 실제 증상 그대로 pnu-less 시드 필지(주소만)를 섞어 재현하고, Shell의
  // healParcelPnu 치유(핵심 수정)를 거친 뒤에만 카운트가 정합됨을 못박는다.
  it("★HIGH: pnu 미확보 시드 필지는 real-pnu autoStage 결과와 키가 어긋나 유령 신규가 생긴다(치유 전)", () => {
    const seedParcels = [
      { pnu: null, address: "서울특별시 종로구 청진동 56-16" }, // 시드(엑셀/지오코딩) — pnu 미확보
      ...projectParcels.slice(1), // 나머지 11필지는 이미 real pnu 보유
    ];
    // autoStage가 focusTarget(=56-16의 좌표)을 재조회해 얻은 결과 — 같은 물리 필지지만 real pnu.
    const autoStageResult = { pnu: "1111010100100560016", address: "서울특별시 종로구 청진동 56-16" };
    const { newCount, totalCount } = counts(seedParcels, [autoStageResult]);
    // 버그 재현: pnu가 없던 시드 항목의 멤버십 키(=주소)와 autoStage 결과의 멤버십 키(=real pnu)가
    // 달라 "이미 등록됨"으로 인식되지 못하고 유령 신규 1건이 생긴다(총 13, 보고된 "1필지 추가" 증상).
    expect(newCount).toBe(1);
    expect(totalCount).toBe(13);
  });

  it("★HIGH 근치 검증: boundary가 돌려준 real pnu로 시드 pnu를 승격(healParcelPnu와 동일 규약: "
    + "기존값 우선, 없을 때만 채택)하면 신규 0 · 총 12로 정합된다", () => {
    const seedParcels = [
      { pnu: null as string | null, address: "서울특별시 종로구 청진동 56-16" },
      ...projectParcels.slice(1),
    ];
    const autoStageResult = { pnu: "1111010100100560016", address: "서울특별시 종로구 청진동 56-16" };
    // Shell.handleBoundaryEnriched가 하는 치유(healParcelPnu 규약)를 인라인으로 적용 — 주소로
    // 매칭해 pnu가 없던 항목만 real pnu로 승격한다. healParcelPnu 자체의 단위 검증은
    // components/precheck/__tests__/SatongMapShell.pnuHeal.test.ts 가 실제 export를 직접 import해
    // 별도로 수행한다(이 파일은 map↔precheck 역참조를 피하는 기존 의존 방향을 유지).
    const healed = seedParcels.map((p) =>
      p.address === autoStageResult.address
        ? { ...p, pnu: p.pnu || autoStageResult.pnu || null }
        : p,
    );
    const { newCount, totalCount } = counts(healed, [autoStageResult]);
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

describe("WP-M2 리뷰(HIGH) 방어선 — isSameSpotAsAny(autoStage 좌표 재조회 판정)", () => {
  it("동일 좌표(같은 float)면 근접으로 판정한다", () => {
    expect(isSameSpotAsAny(37.5665, 126.978, [{ lat: 37.5665, lon: 126.978 }])).toBe(true);
  });

  it("좁은 허용오차(기본 1e-5도≈1.1m) 안이면 근접으로 판정한다", () => {
    expect(isSameSpotAsAny(37.56650001, 126.97800001, [{ lat: 37.5665, lon: 126.978 }])).toBe(
      true,
    );
  });

  it("★인접한 다른 필지(수십m 이상 떨어짐)는 근접으로 오판하지 않는다", () => {
    // 위도 0.001도 ≈ 111m — 옆 필지로 충분히 먼 거리, 허용오차(1.1m)를 훌쩍 넘는다.
    expect(isSameSpotAsAny(37.5675, 126.978, [{ lat: 37.5665, lon: 126.978 }])).toBe(false);
  });

  it("좌표 없는 필지(lat/lon null)는 근접 후보에서 제외한다", () => {
    expect(isSameSpotAsAny(37.5665, 126.978, [{ lat: null, lon: null }])).toBe(false);
  });

  it("후보가 비어있으면 항상 false", () => {
    expect(isSameSpotAsAny(37.5665, 126.978, [])).toBe(false);
  });
});
