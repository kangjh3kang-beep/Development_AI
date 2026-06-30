import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import {
  useProjectContextStore,
  addressTokenMismatch,
  purifyPollutedSnapshot,
  purifyPersistedContextState,
  type ProjectContextState,
  type CostData,
  type DesignData,
  type EsgData,
} from "@/store/useProjectContextStore";

/**
 * WP-15 — 필드 단위 provenance(manualFields) merge 가드 계약 (vitest 6케이스).
 *
 * 핵심 불변식(§2-1 merge 가드 규칙을 정답값으로 고정):
 *  - siteAnalysis(partial patch): auto 갱신은 user 플래그 필드를 patch에서 제거해
 *    수동값을 보존하고, 전 키 제거(빈 patch) 시 갱신·stamp를 생략한다.
 *  - costData(full replace): auto 교체 시 user 플래그 키의 이전값을 보존한다.
 *  - revertFieldToAuto 후에는 다음 auto 갱신부터 덮어쓰기를 재허용한다.
 *  - getFieldProvenance는 기록 없으면 null(= auto 취급).
 *  - manualFields는 ProjectSnapshot에 포함돼 프로젝트 전환 round-trip을 보존하고,
 *    구 스냅샷(필드 부재)은 ?? {} 폴백으로 복원된다.
 *  - meta 미전달 = "auto" — 기존 호출 무수정 하위호환.
 *
 * WP-V(하단 describe) — ProvenanceModule 확장(design/esg/tax):
 *  - designData: 기존 머지-보존 가드(비null 키만 덮어씀) 불변 + cost 동일 규칙 가산.
 *  - esgData: full replace에서 cost와 동일한 merge 가드.
 *  - tax: 전용 store 데이터 필드 없이 타입만 선등록(조회 null·revert no-op).
 */

function reset() {
  useProjectContextStore.setState({
    projectId: "p1",
    projectName: "테스트 프로젝트",
    projectStatus: "active",
    completedStages: [],
    currentStage: null,
    siteAnalysis: null,
    designData: null,
    feasibilityData: null,
    costData: null,
    esgData: null,
    complianceData: null,
    analysisResults: [],
    snapshots: {},
    updatedAt: {},
    analysisCache: {},
    manualFields: {},
  });
}

/** CostData full shape 헬퍼 — full replace 액션 시그니처상 전 키가 필요. */
function makeCost(partial: Partial<CostData>): CostData {
  return {
    totalConstructionCostWon: null,
    perSqmWon: null,
    perPyeongWon: null,
    abovegroundWon: null,
    undergroundWon: null,
    landscapeWon: null,
    directWon: null,
    indirectWon: null,
    rangeMinWon: null,
    rangeMaxWon: null,
    source: null,
    ...partial,
  };
}

describe("WP-15 provenance(manualFields) — merge 가드 계약", () => {
  // 구조적 최소 타입 — vi.spyOn 제네릭 오버로드의 ReturnType 추론 불안정 회피.
  let nowSpy: { mockRestore(): void } | null = null;

  beforeEach(() => {
    reset();
    // 타임스탬프 단조 증가를 결정적으로 보장(같은 ms 충돌 방지).
    let t = 1_000_000;
    nowSpy = vi.spyOn(Date, "now").mockImplementation(() => (t += 10));
  });

  afterEach(() => {
    nowSpy?.mockRestore();
    nowSpy = null;
  });

  it("케이스1: siteAnalysis — user 필드는 auto가 덮지 못하고, 나머지 키만 부분 반영(빈 patch면 stamp 생략)", () => {
    const s0 = useProjectContextStore.getState();
    s0.updateSiteAnalysis(
      { landAreaSqm: 500, zoneCode: "제2종일반주거지역" },
      { source: "auto" },
    );
    // 사용자 수정 → landAreaSqm을 user로 stamp
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 660 }, { source: "user" });

    // auto 갱신: user 키(landAreaSqm)는 제거되고 zoneCode만 부분 반영
    useProjectContextStore
      .getState()
      .updateSiteAnalysis(
        { landAreaSqm: 999, zoneCode: "제3종일반주거지역" },
        { source: "auto" },
      );
    const s1 = useProjectContextStore.getState();
    expect(s1.siteAnalysis?.landAreaSqm).toBe(660); // user 보존
    expect(s1.siteAnalysis?.zoneCode).toBe("제3종일반주거지역"); // auto 부분 반영

    // 전 키가 user 보호 대상(빈 patch) → 값·updatedAt stamp 모두 불변
    const stampBefore = s1.updatedAt.siteAnalysis;
    s1.updateSiteAnalysis({ landAreaSqm: 1 }, { source: "auto" });
    const s2 = useProjectContextStore.getState();
    expect(s2.siteAnalysis?.landAreaSqm).toBe(660);
    expect(s2.updatedAt.siteAnalysis).toBe(stampBefore);
  });

  it("케이스2: costData — full replace에서도 user 플래그 키의 이전값을 보존(변경된 비null 키만 stamp)", () => {
    const s0 = useProjectContextStore.getState();
    s0.updateCostData(
      makeCost({
        totalConstructionCostWon: 5_000_000_000,
        perSqmWon: 3_000_000,
        source: "overview",
      }),
      { source: "auto" },
    );
    // 사용자 수정: total만 변경(5e9→6e9). perSqmWon·source는 미변경 → stamp 대상 아님.
    useProjectContextStore.getState().updateCostData(
      makeCost({
        totalConstructionCostWon: 6_000_000_000,
        perSqmWon: 3_000_000,
        source: "overview",
      }),
      { source: "user" },
    );
    const afterUser = useProjectContextStore.getState();
    expect(
      afterUser.getFieldProvenance("cost", "totalConstructionCostWon")?.source,
    ).toBe("user");
    // 미변경 키·null 키는 user로 동결하지 않는다(자동 환류 무력화 방지)
    expect(afterUser.getFieldProvenance("cost", "perSqmWon")).toBeNull();
    expect(afterUser.getFieldProvenance("cost", "directWon")).toBeNull();

    // auto full replace → user 키만 이전값 보존, 나머지는 교체
    afterUser.updateCostData(
      makeCost({
        totalConstructionCostWon: 7_000_000_000,
        perSqmWon: 4_000_000,
        source: "bim",
      }),
      { source: "auto" },
    );
    const s1 = useProjectContextStore.getState();
    expect(s1.costData?.totalConstructionCostWon).toBe(6_000_000_000); // user 보존
    expect(s1.costData?.perSqmWon).toBe(4_000_000); // auto 교체
    expect(s1.costData?.source).toBe("bim"); // auto 교체
  });

  it("케이스3: revertFieldToAuto 후 다음 auto 갱신부터 덮어쓰기 재허용", () => {
    const s0 = useProjectContextStore.getState();
    s0.updateSiteAnalysis({ landAreaSqm: 500 }, { source: "auto" });
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 660 }, { source: "user" });

    // revert 전: auto 덮어쓰기 차단
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 999 }, { source: "auto" });
    expect(useProjectContextStore.getState().siteAnalysis?.landAreaSqm).toBe(
      660,
    );

    useProjectContextStore
      .getState()
      .revertFieldToAuto("siteAnalysis", "landAreaSqm");
    expect(
      useProjectContextStore
        .getState()
        .getFieldProvenance("siteAnalysis", "landAreaSqm"),
    ).toBeNull();

    // revert 후: auto 덮어쓰기 재허용
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 999 }, { source: "auto" });
    expect(useProjectContextStore.getState().siteAnalysis?.landAreaSqm).toBe(
      999,
    );
  });

  it("케이스4: getFieldProvenance — user stamp 반환, 기록 없으면 null(auto 갱신은 stamp하지 않음)", () => {
    const s0 = useProjectContextStore.getState();
    // 기록 없음 → null
    expect(s0.getFieldProvenance("siteAnalysis", "landAreaSqm")).toBeNull();

    // auto 갱신은 stamp하지 않음 → 여전히 null
    s0.updateSiteAnalysis({ landAreaSqm: 500 }, { source: "auto" });
    expect(
      useProjectContextStore
        .getState()
        .getFieldProvenance("siteAnalysis", "landAreaSqm"),
    ).toBeNull();

    // user 갱신 → {source:"user", updatedAt: epoch ms} stamp
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 660 }, { source: "user" });
    const prov = useProjectContextStore
      .getState()
      .getFieldProvenance("siteAnalysis", "landAreaSqm");
    expect(prov?.source).toBe("user");
    expect(typeof prov?.updatedAt).toBe("number");
    expect(prov?.updatedAt).toBeGreaterThan(0);
    // 다른 모듈/필드에는 전파되지 않음
    expect(
      useProjectContextStore
        .getState()
        .getFieldProvenance("cost", "totalConstructionCostWon"),
    ).toBeNull();
  });

  it("케이스5: 스냅샷 round-trip — 프로젝트 전환·복귀 시 manualFields 보존, 구 스냅샷(필드 부재)은 {} 폴백", () => {
    const s0 = useProjectContextStore.getState();
    s0.updateSiteAnalysis({ landAreaSqm: 500 }, { source: "auto" });
    useProjectContextStore
      .getState()
      .updateSiteAnalysis({ landAreaSqm: 660 }, { source: "user" });

    // p1 → p2(스냅샷 없음): manualFields는 빈 맵으로 초기화
    useProjectContextStore
      .getState()
      .setProject("p2", "다른 프로젝트", "active");
    const onP2 = useProjectContextStore.getState();
    expect(onP2.siteAnalysis).toBeNull();
    expect(
      onP2.getFieldProvenance("siteAnalysis", "landAreaSqm"),
    ).toBeNull();

    // p2 → p1 복귀: 값·provenance 함께 복원되고 merge 가드도 그대로 동작
    useProjectContextStore
      .getState()
      .setProject("p1", "테스트 프로젝트", "active");
    const back = useProjectContextStore.getState();
    expect(back.siteAnalysis?.landAreaSqm).toBe(660);
    expect(
      back.getFieldProvenance("siteAnalysis", "landAreaSqm")?.source,
    ).toBe("user");
    back.updateSiteAnalysis({ landAreaSqm: 999 }, { source: "auto" });
    expect(useProjectContextStore.getState().siteAnalysis?.landAreaSqm).toBe(
      660,
    );

    // 구 스냅샷 호환: manualFields 키가 없는 스냅샷도 ?? {} 폴백으로 복원(throw 없음)
    const legacySnapshots = {
      legacy: {
        siteAnalysis: {
          estimatedValue: null,
          landAreaSqm: 300,
          zoneCode: null,
          address: "구버전 저장 주소",
          pnu: null,
        },
        designData: null,
        feasibilityData: null,
        costData: null,
        esgData: null,
        complianceData: null,
        completedStages: [],
        currentStage: null,
        analysisResults: [],
        updatedAt: {},
        analysisCache: {},
        // manualFields 부재 — 구 영속 스냅샷 shape
      },
    } as unknown as ProjectContextState["snapshots"];
    useProjectContextStore.setState((state) => ({
      snapshots: { ...state.snapshots, ...legacySnapshots },
    }));
    useProjectContextStore
      .getState()
      .setProject("legacy", "구 프로젝트", "active");
    const onLegacy = useProjectContextStore.getState();
    expect(onLegacy.siteAnalysis?.landAreaSqm).toBe(300);
    expect(onLegacy.manualFields).toEqual({});
    expect(
      onLegacy.getFieldProvenance("siteAnalysis", "landAreaSqm"),
    ).toBeNull();
  });

  it("케이스6: meta 미전달 = auto — 기존 호출 무수정 하위호환(값 반영·stamp 없음·user 가드 준수)", () => {
    const s0 = useProjectContextStore.getState();
    // 기존 시그니처 그대로 호출 — 값은 반영되고 manualFields는 비어 있어야 한다.
    s0.updateSiteAnalysis({ landAreaSqm: 500, address: "서울시 송파구 1-1" });
    const s1 = useProjectContextStore.getState();
    expect(s1.siteAnalysis?.landAreaSqm).toBe(500);
    expect(s1.siteAnalysis?.address).toBe("서울시 송파구 1-1");
    expect(s1.getFieldProvenance("siteAnalysis", "landAreaSqm")).toBeNull();
    expect(s1.manualFields).toEqual({});
    expect(s1.updatedAt.siteAnalysis).toBeGreaterThan(0); // stamp는 정상 동작

    s1.updateCostData(
      makeCost({ totalConstructionCostWon: 5_000_000_000, source: "overview" }),
    );
    const s2 = useProjectContextStore.getState();
    expect(s2.costData?.totalConstructionCostWon).toBe(5_000_000_000);
    expect(
      s2.getFieldProvenance("cost", "totalConstructionCostWon"),
    ).toBeNull();

    // meta 미전달 호출은 auto로 취급 → user 플래그 필드를 덮지 못한다.
    s2.updateSiteAnalysis({ landAreaSqm: 660 }, { source: "user" });
    useProjectContextStore.getState().updateSiteAnalysis({ landAreaSqm: 999 });
    expect(useProjectContextStore.getState().siteAnalysis?.landAreaSqm).toBe(
      660,
    );
  });
});

/** DesignData full shape 헬퍼 — 액션 시그니처상 필수 키 전부 필요. */
function makeDesign(partial: Partial<DesignData>): DesignData {
  return {
    totalGfaSqm: null,
    floorCount: null,
    buildingType: null,
    bcr: null,
    far: null,
    ...partial,
  };
}

/** EsgData full shape 헬퍼 — full replace 액션 시그니처상 전 키가 필요. */
function makeEsg(partial: Partial<EsgData>): EsgData {
  return {
    embodiedCarbonKg: null,
    operationalCarbonKg: null,
    totalCarbonPerSqm: null,
    ...partial,
  };
}

describe("WP-V provenance 모듈 확장(design/esg/tax) — merge 가드 계약", () => {
  let nowSpy: { mockRestore(): void } | null = null;

  beforeEach(() => {
    reset();
    let t = 2_000_000;
    nowSpy = vi.spyOn(Date, "now").mockImplementation(() => (t += 10));
  });

  afterEach(() => {
    nowSpy?.mockRestore();
    nowSpy = null;
  });

  it("케이스7: designData — 기존 머지-보존 가드 불변 + auto가 user 필드 안덮음(변경된 비null 키만 stamp)", () => {
    const s0 = useProjectContextStore.getState();
    // meta 미전달(기존 호출) — 값 반영, manualFields stamp 없음(하위호환)
    s0.updateDesignData(
      makeDesign({ totalGfaSqm: 1000, floorCount: 10, unitCount: 20 }),
    );
    const s1 = useProjectContextStore.getState();
    expect(s1.designData?.totalGfaSqm).toBe(1000);
    expect(s1.getFieldProvenance("design", "totalGfaSqm")).toBeNull();
    expect(s1.manualFields).toEqual({});
    expect(s1.updatedAt.design).toBeGreaterThan(0); // stamp는 정상 동작

    // 기존 머지-보존 가드 불변: null 키는 기존 구체값을 덮지 않는다
    s1.updateDesignData(makeDesign({ totalGfaSqm: 1200 }));
    const s2 = useProjectContextStore.getState();
    expect(s2.designData?.totalGfaSqm).toBe(1200);
    expect(s2.designData?.floorCount).toBe(10); // null이 기존 구체값 안덮음
    expect(s2.designData?.unitCount).toBe(20);

    // user 수정: totalGfaSqm만 변경 → 해당 키만 stamp(미변경·null 키 동결 금지)
    s2.updateDesignData(makeDesign({ totalGfaSqm: 1500, floorCount: 10 }), {
      source: "user",
    });
    const afterUser = useProjectContextStore.getState();
    expect(afterUser.getFieldProvenance("design", "totalGfaSqm")?.source).toBe(
      "user",
    );
    expect(afterUser.getFieldProvenance("design", "floorCount")).toBeNull(); // 미변경
    expect(afterUser.getFieldProvenance("design", "bcr")).toBeNull(); // null 키

    // auto 갱신: user 키(totalGfaSqm)는 보존, 나머지는 반영
    afterUser.updateDesignData(
      makeDesign({ totalGfaSqm: 9999, floorCount: 12 }),
      { source: "auto" },
    );
    const s3 = useProjectContextStore.getState();
    expect(s3.designData?.totalGfaSqm).toBe(1500); // user 보존
    expect(s3.designData?.floorCount).toBe(12); // auto 반영
    expect(s3.designData?.unitCount).toBe(20); // 머지-보존 가드 여전히 동작

    // revertFieldToAuto 후 다음 auto 갱신부터 덮어쓰기 재허용
    s3.revertFieldToAuto("design", "totalGfaSqm");
    useProjectContextStore
      .getState()
      .updateDesignData(makeDesign({ totalGfaSqm: 9999 }), { source: "auto" });
    expect(useProjectContextStore.getState().designData?.totalGfaSqm).toBe(
      9999,
    );
  });

  it("케이스8: esgData — full replace에서 user 플래그 키의 이전값 보존(cost 동일 규칙) + meta 미전달 하위호환", () => {
    const s0 = useProjectContextStore.getState();
    // meta 미전달(기존 호출) — full replace 동작 불변, stamp 없음(하위호환)
    s0.updateEsgData(
      makeEsg({ embodiedCarbonKg: 100_000, totalCarbonPerSqm: 350 }),
    );
    const s1 = useProjectContextStore.getState();
    expect(s1.esgData?.embodiedCarbonKg).toBe(100_000);
    expect(s1.getFieldProvenance("esg", "embodiedCarbonKg")).toBeNull();
    expect(s1.manualFields).toEqual({});
    expect(s1.updatedAt.esg).toBeGreaterThan(0);

    // user 수정: totalCarbonPerSqm만 변경 → 해당 키만 stamp
    s1.updateEsgData(
      makeEsg({ embodiedCarbonKg: 100_000, totalCarbonPerSqm: 300 }),
      { source: "user" },
    );
    const afterUser = useProjectContextStore.getState();
    expect(
      afterUser.getFieldProvenance("esg", "totalCarbonPerSqm")?.source,
    ).toBe("user");
    expect(afterUser.getFieldProvenance("esg", "embodiedCarbonKg")).toBeNull(); // 미변경
    expect(
      afterUser.getFieldProvenance("esg", "operationalCarbonKg"),
    ).toBeNull(); // null 키

    // auto full replace: user 키만 이전값 보존, 나머지는 교체
    afterUser.updateEsgData(
      makeEsg({
        embodiedCarbonKg: 120_000,
        operationalCarbonKg: 50_000,
        totalCarbonPerSqm: 999,
      }),
      { source: "auto" },
    );
    const s2 = useProjectContextStore.getState();
    expect(s2.esgData?.totalCarbonPerSqm).toBe(300); // user 보존
    expect(s2.esgData?.embodiedCarbonKg).toBe(120_000); // auto 교체
    expect(s2.esgData?.operationalCarbonKg).toBe(50_000); // auto 교체

    // revertFieldToAuto 후 다음 auto 갱신부터 덮어쓰기 재허용
    s2.revertFieldToAuto("esg", "totalCarbonPerSqm");
    useProjectContextStore
      .getState()
      .updateEsgData(makeEsg({ totalCarbonPerSqm: 999 }), { source: "auto" });
    expect(useProjectContextStore.getState().esgData?.totalCarbonPerSqm).toBe(
      999,
    );
  });

  it("케이스9: tax — ProvenanceModule 타입 선등록(전용 데이터 필드 없음): 조회 null·revert no-op", () => {
    const s0 = useProjectContextStore.getState();
    // "tax"가 ProvenanceModule 유니온에 포함돼야 아래 호출이 타입체크를 통과한다.
    expect(s0.getFieldProvenance("tax", "acquisitionTaxWon")).toBeNull();
    // 기록 없는 필드의 revert는 no-op(throw·상태 변경 없음)
    s0.revertFieldToAuto("tax", "acquisitionTaxWon");
    const s1 = useProjectContextStore.getState();
    expect(s1.getFieldProvenance("tax", "acquisitionTaxWon")).toBeNull();
    expect(s1.manualFields).toEqual({});
  });
});

/* ════════════ WP-D — SSOT 오염 차단: 주소 토큰 검증·정화 마이그레이션 ════════════
   진단된 오염 사슬: 활성 프로젝트와 무관한 주소 검색 결과가 updateSiteAnalysis →
   withSnap으로 스냅샷 영속 → 전환 시 복원 → 서버 푸시로 고착.
   계약: (a) 핵심 토큰(시군구·법정동·번지)이 "명백히" 불일치할 때만 오염 판정 —
   표기 차이(도로명/지번 혼용·행정동 숫자)와 비교 불능은 오염 아님(과차단 금지).
   (b) 정화는 siteAnalysis·파생 designData만 null화하고 그 외(공사비·수지 등) 보존.
   (c) persist migrate(version 1)가 hydrate 시 purifyPersistedContextState를 적용. */

describe("WP-D SSOT 오염 차단 — 주소 토큰 검증·정화 마이그레이션", () => {
  it("케이스10: addressTokenMismatch — 시군구·번지 명백 불일치만 true, 표기차이·비교불능은 false", () => {
    // 명백 불일치: 다른 시군구(서울 강남구 ↔ 성남 분당구)
    expect(
      addressTokenMismatch(
        "서울특별시 강남구 역삼동 737",
        "경기도 성남시 분당구 정자동 178-1",
      ),
    ).toBe(true);
    // 같은 법정동, 다른 번지
    expect(
      addressTokenMismatch(
        "서울특별시 강남구 역삼동 737",
        "서울특별시 강남구 역삼동 12-3",
      ),
    ).toBe(true);
    // 도로명 ↔ 지번(같은 시군구, 동 토큰 한쪽 부재) → 불일치 아님(오탐 방지)
    expect(
      addressTokenMismatch(
        "서울특별시 강남구 테헤란로 152",
        "서울특별시 강남구 역삼동 737",
      ),
    ).toBe(false);
    // 행정동 숫자 정규화(역삼1동 ↔ 역삼동) + 시도 축약 → 불일치 아님
    expect(
      addressTokenMismatch(
        "서울 강남구 역삼1동 737",
        "서울특별시 강남구 역삼동 737",
      ),
    ).toBe(false);
    // 동일 주소 → 불일치 아님
    expect(
      addressTokenMismatch(
        "서울특별시 강남구 역삼동 737",
        "서울특별시 강남구 역삼동 737",
      ),
    ).toBe(false);
    // 비교 불능(null·빈 문자열·토큰 추출 실패) → 불일치 아님(과차단 금지)
    expect(addressTokenMismatch(null, "서울특별시 강남구 역삼동 737")).toBe(false);
    expect(addressTokenMismatch("서울특별시 강남구 역삼동 737", undefined)).toBe(false);
    expect(addressTokenMismatch("", "")).toBe(false);
  });

  it("케이스11: purifyPollutedSnapshot — siteAnalysis·designData null 정화 + 단계/stamp/provenance 정리, 그 외 보존·원본 불변", () => {
    const snap = {
      siteAnalysis: { address: "경기도 성남시 분당구 정자동 178-1", landAreaSqm: 500 },
      designData: { totalGfaSqm: 1000 },
      feasibilityData: { totalCostWon: 1 },
      costData: { totalConstructionCostWon: 5 },
      completedStages: ["site-analysis", "design", "feasibility"],
      currentStage: "design",
      analysisResults: [{ module: "m", completedAt: "t", summary: {} }],
      updatedAt: { siteAnalysis: 1, design: 2, cost: 3 },
      analysisCache: { terrain: { signature: "s", data: 1, at: 1 } },
      manualFields: {
        siteAnalysis: { landAreaSqm: { source: "user", updatedAt: 1 } },
        cost: { totalConstructionCostWon: { source: "user", updatedAt: 2 } },
      },
    };
    const purified = purifyPollutedSnapshot(snap as unknown as Record<string, unknown>);
    // 오염 필드·파생만 정화
    expect(purified.siteAnalysis).toBeNull();
    expect(purified.designData).toBeNull();
    expect(purified.completedStages).toEqual(["feasibility"]);
    expect(purified.updatedAt).toEqual({ cost: 3 });
    expect(purified.manualFields).toEqual({
      cost: { totalConstructionCostWon: { source: "user", updatedAt: 2 } },
    });
    // 그 외 필드(공사비·수지·분석이력·캐시)는 보존
    expect(purified.costData).toEqual({ totalConstructionCostWon: 5 });
    expect(purified.feasibilityData).toEqual({ totalCostWon: 1 });
    expect(purified.analysisResults).toHaveLength(1);
    expect(purified.analysisCache).toEqual(snap.analysisCache);
    // 원본 불변(정화된 사본 반환)
    expect(snap.siteAnalysis).not.toBeNull();
    expect(snap.completedStages).toEqual(["site-analysis", "design", "feasibility"]);
    expect(snap.updatedAt).toEqual({ siteAnalysis: 1, design: 2, cost: 3 });
  });

  it("케이스12: purifyPersistedContextState(migrate 본체) — 토큰 불일치 스냅샷·live만 정화, 비교불능·무오염은 참조 보존", () => {
    const polluted = {
      siteAnalysis: { address: "경기도 성남시 분당구 정자동 178-1", landAreaSqm: 1 },
      designData: { totalGfaSqm: 9 },
      completedStages: ["site-analysis", "design"],
      updatedAt: { siteAnalysis: 1, design: 2 },
      manualFields: {},
    };
    const clean = {
      siteAnalysis: { address: "서울특별시 강남구 역삼동 737", landAreaSqm: 2 },
      designData: null,
      completedStages: [],
      updatedAt: {},
      manualFields: {},
    };
    const noRecord = {
      siteAnalysis: { address: "부산광역시 해운대구 우동 1408" },
      designData: { totalGfaSqm: 3 },
      completedStages: ["site-analysis"],
      updatedAt: {},
      manualFields: {},
    };
    const persisted = {
      projectId: "p-polluted",
      // live 필드도 동일 오염(스냅샷과 같은 무관 주소)
      siteAnalysis: { address: "경기도 성남시 분당구 정자동 178-1" },
      designData: { totalGfaSqm: 9 },
      completedStages: ["site-analysis", "design"],
      updatedAt: { siteAnalysis: 1, design: 2 },
      manualFields: {},
      snapshots: {
        "p-polluted": polluted,
        "p-clean": clean,
        "p-norecord": noRecord,
      },
    };
    const addressOf = {
      "p-polluted": "서울특별시 강남구 역삼동 737",
      "p-clean": "서울특별시 강남구 역삼동 737",
      // p-norecord: 프로젝트 레코드 주소 없음 → 비교 불능 → 보존
    };
    const out = purifyPersistedContextState(
      persisted as unknown as Record<string, unknown>,
      addressOf,
    );
    const snaps = out.snapshots as Record<string, Record<string, unknown>>;
    // 오염 스냅샷: siteAnalysis·designData 정화 + 단계 제거
    expect(snaps["p-polluted"].siteAnalysis).toBeNull();
    expect(snaps["p-polluted"].designData).toBeNull();
    expect(snaps["p-polluted"].completedStages).toEqual([]);
    // 무오염·비교불능 스냅샷: 참조 그대로 보존(무변경)
    expect(snaps["p-clean"]).toBe(clean);
    expect(snaps["p-norecord"]).toBe(noRecord);
    // live 필드(현재 활성 프로젝트)도 동일 기준 정화
    expect(out.siteAnalysis).toBeNull();
    expect(out.designData).toBeNull();
    expect(out.completedStages).toEqual([]);
    expect(out.updatedAt).toEqual({});

    // 오염이 전혀 없으면 원본 참조를 그대로 반환(무변경 보장 — migrate 부작용 없음)
    const allClean = {
      projectId: "p-clean",
      siteAnalysis: { address: "서울특별시 강남구 역삼동 737" },
      snapshots: { "p-clean": clean },
    };
    expect(
      purifyPersistedContextState(
        allClean as unknown as Record<string, unknown>,
        addressOf,
      ),
    ).toBe(allClean);
  });

  it("케이스13: setProject 동일 id 재바인딩 — 현 프로젝트 주소와 다른 live 분석·설계 파생값을 즉시 정화", () => {
    reset();
    useProjectContextStore.setState((state) => ({
      ...state,
      projectId: "p1",
      siteAnalysis: {
        estimatedValue: null,
        landAreaSqm: 500,
        zoneCode: "제2종일반주거지역",
        address: "경기도 성남시 분당구 정자동 178-1",
        pnu: null,
      },
      designData: makeDesign({ totalGfaSqm: 1500, floorCount: 8, far: 300 }),
      completedStages: ["site-analysis", "design", "cost"],
      updatedAt: { siteAnalysis: 1, design: 2, cost: 3, decisionBrief: 4 },
      manualFields: {
        siteAnalysis: { landAreaSqm: { source: "user", updatedAt: 1 } },
        design: { floorCount: { source: "user", updatedAt: 2 } },
        cost: { totalConstructionCostWon: { source: "user", updatedAt: 3 } },
      },
    }));

    useProjectContextStore
      .getState()
      .setProject("p1", "테스트 프로젝트", "active", "서울특별시 강남구 역삼동 737");

    const s = useProjectContextStore.getState();
    expect(s.siteAnalysis).toMatchObject({
      address: "서울특별시 강남구 역삼동 737",
      landAreaSqm: null,
      zoneCode: null,
    });
    expect(s.designData).toBeNull();
    expect(s.completedStages).toEqual(["cost"]);
    expect(s.updatedAt).toEqual({ cost: 3 });
    expect(s.manualFields.siteAnalysis).toBeUndefined();
    expect(s.manualFields.design).toBeUndefined();
    expect(s.manualFields.cost).toEqual({
      totalConstructionCostWon: { source: "user", updatedAt: 3 },
    });
    expect(s.snapshots.p1?.designData).toBeNull();
    expect(s.snapshots.p1?.siteAnalysis?.address).toBe("서울특별시 강남구 역삼동 737");
  });
});
