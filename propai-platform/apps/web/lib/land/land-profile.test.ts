import { describe, it, expect } from "vitest";
import { buildLandProfile, landProfileToEvidence } from "@/lib/land/land-profile";
import type { SiteAnalysisData } from "@/store/useProjectContextStore";

/** SiteAnalysisData 최소 기본값 + 부분 오버라이드 헬퍼. */
function site(partial: Partial<SiteAnalysisData> = {}): SiteAnalysisData {
  return {
    estimatedValue: null,
    landAreaSqm: null,
    zoneCode: null,
    address: null,
    pnu: null,
    ...partial,
  };
}

describe("buildLandProfile — 식별 게이트", () => {
  it("site가 null이면 null", () => {
    expect(buildLandProfile(null)).toBeNull();
    expect(buildLandProfile(undefined)).toBeNull();
  });

  it("주소·PNU·용도지역이 모두 없으면 null(표시할 토지특성 없음)", () => {
    expect(buildLandProfile(site())).toBeNull();
  });

  it("주소만 있어도 profile을 만든다", () => {
    const p = buildLandProfile(site({ address: "서울특별시 강남구 역삼동 737" }));
    expect(p).not.toBeNull();
    expect(p!.address).toBe("서울특별시 강남구 역삼동 737");
  });
});

describe("buildLandProfile — Stage A 현시점(무날조)", () => {
  it("용도지역 미확정(far 미해소)이면 far.value=null + honestNote 동반", () => {
    const p = buildLandProfile(site({ address: "서울특별시 강남구 역삼동 737" }))!;
    expect(p.stageA.far.value).toBeNull();
    expect(p.stageA.bcr.value).toBeNull();
    expect(p.honestNote).not.toBeNull();
  });

  it("주소만 있고 용도지역·용적률 미확보면 건축가능분류를 '개발 가능'으로 단정하지 않는다", () => {
    const p = buildLandProfile(site({ address: "서울특별시 강남구 역삼동 737" }))!;
    expect(p.stageA.buildableCategory.label).not.toBe("개발 가능");
    expect(p.stageA.buildableCategory.code).toBeNull();
  });

  it("실효 용적·건폐율이 있으면 실효값을 현실적 용적/건폐율로 쓰고 근거에 '실효' 표기", () => {
    const p = buildLandProfile(
      site({
        zoneCode: "제2종일반주거지역",
        effectiveFarPct: 200,
        effectiveBcrPct: 50,
        nationalFarPct: 250,
        nationalBcrPct: 60,
        farBasis: "지자체 조례 상한",
      }),
    )!;
    expect(p.stageA.far.value).toBe(200);
    expect(p.stageA.far.unit).toBe("%");
    expect(p.stageA.far.basis).toContain("실효");
    expect(p.stageA.far.basis).toContain("지자체 조례 상한");
    expect(p.stageA.bcr.value).toBe(50);
    expect(p.honestNote).toBeNull();
  });

  it("실효값이 없으면 법정상한으로 폴백하고 근거에 '법정상한' 표기(실효 오인 방지)", () => {
    const p = buildLandProfile(
      site({
        zoneCode: "제2종일반주거지역",
        effectiveFarPct: null,
        effectiveBcrPct: null,
        nationalFarPct: 250,
        nationalBcrPct: 60,
      }),
    )!;
    expect(p.stageA.far.value).toBe(250);
    expect(p.stageA.far.basis).toContain("법정상한");
    expect(p.stageA.bcr.value).toBe(60);
  });

  it("특이부지가 없으면 건축가능분류는 '개발 가능'(code=null)", () => {
    const p = buildLandProfile(site({ zoneCode: "제2종일반주거지역", effectiveFarPct: 200 }))!;
    expect(p.stageA.buildableCategory.code).toBeNull();
    expect(p.stageA.buildableCategory.label).toBe("개발 가능");
  });

  it("특이부지가 있으면 developability 라벨 + factors를 제한사항으로 전개", () => {
    const p = buildLandProfile(
      site({
        zoneCode: "자연녹지지역",
        effectiveFarPct: 80,
        effectiveBcrPct: 20,
        specialParcel: {
          isSpecial: true,
          developability: "CONDITIONAL",
          resolvable: "CONDITIONAL",
          factors: ["맹지(도로 미접)", "경사도 과다"],
          honest: "도로 확보 등 선행절차 전제",
        },
      }),
    )!;
    expect(p.stageA.buildableCategory.code).toBe("CONDITIONAL");
    expect(p.stageA.buildableCategory.label).toBe("조건부 가능");
    expect(p.stageA.buildableCategory.rationale).toBe("도로 확보 등 선행절차 전제");
    const labels = p.stageA.restrictions.map((r) => r.label);
    expect(labels).toContain("맹지(도로 미접)");
    expect(labels).toContain("경사도 과다");
    expect(p.stageA.restrictions.every((r) => r.severity === "caution")).toBe(true);
  });

  it("개발 불가(BLOCKED) 특이부지 제한은 severity=blocker", () => {
    const p = buildLandProfile(
      site({
        zoneCode: "보전관리지역",
        effectiveFarPct: 50,
        specialParcel: {
          isSpecial: true,
          developability: "BLOCKED",
          resolvable: "NO",
          factors: ["개발제한구역"],
          honest: null,
        },
      }),
    )!;
    expect(p.stageA.buildableCategory.label).toBe("개발 불가");
    expect(p.stageA.restrictions.every((r) => r.severity === "blocker")).toBe(true);
  });

  it("용도지역 혼재(zoneMixed)면 stageA.zoneMixed=true + 혼재 제한사항 추가", () => {
    const p = buildLandProfile(
      site({ zoneCode: "제2종일반주거지역", effectiveFarPct: 200, zoneMixed: true }),
    )!;
    expect(p.stageA.zoneMixed).toBe(true);
    expect(p.stageA.restrictions.some((r) => r.label.includes("혼재"))).toBe(true);
  });
});

describe("buildLandProfile — Stage B 미래(종상향 시나리오)", () => {
  it("집계값만 있으면(per-scenario 부재) '종상향 잠재' 단일 시나리오로 요약", () => {
    const p = buildLandProfile(
      site({
        zoneCode: "준주거지역",
        effectiveFarPct: 400,
        upzoningPotentialFarHigh: 600,
        upzoningFeasibilityTop: "중",
      }),
    )!;
    expect(p.stageB.scenarios).toHaveLength(1);
    expect(p.stageB.scenarios[0].label).toContain("종상향");
    expect(p.stageB.scenarios[0].potentialFarHigh).toBe(600);
    expect(p.stageB.scenarios[0].feasibility).toBe("중");
    expect(p.stageB.topFeasibility).toBe("중");
    expect(p.stageB.potentialFarHigh).toBe(600);
    expect(p.stageB.disclaimer).toBeTruthy();
  });

  it("per-scenario(upzoningScenarios)가 있으면 각 시나리오로 전개하고 최상 가능성/최대 용적률 집계", () => {
    const p = buildLandProfile(
      site({
        zoneCode: "준주거지역",
        effectiveFarPct: 400,
        upzoningScenarios: [
          {
            path: "준주거 → 일반상업",
            targetZone: "일반상업지역",
            feasibility: "중",
            expectedFarLowPct: 400,
            expectedFarHighPct: 600,
            legalBasis: "국토계획법 시행령 제30조",
            rationale: "역세권 입지",
          },
          {
            path: "역세권 활성화 종상향",
            targetZone: "준주거지역",
            feasibility: "상",
            expectedFarLowPct: null,
            expectedFarHighPct: 500,
            legalBasis: "역세권 활성화 지침",
            rationale: "승강장 250m 이내",
          },
        ],
      }),
    )!;
    expect(p.stageB.scenarios).toHaveLength(2);
    expect(p.stageB.topFeasibility).toBe("상"); // 상 > 중
    expect(p.stageB.potentialFarHigh).toBe(600); // max(600, 500)
    const s0 = p.stageB.scenarios[0];
    expect(s0.label).toBe("준주거 → 일반상업");
    expect(s0.targetZone).toBe("일반상업지역");
    expect(s0.legalBasis).toBe("국토계획법 시행령 제30조");
  });

  it("종상향 데이터가 전혀 없으면 시나리오 빈 배열·집계 null", () => {
    const p = buildLandProfile(site({ zoneCode: "제2종일반주거지역", effectiveFarPct: 200 }))!;
    expect(p.stageB.scenarios).toEqual([]);
    expect(p.stageB.topFeasibility).toBeNull();
    expect(p.stageB.potentialFarHigh).toBeNull();
  });
});

describe("buildLandProfile — 결정론", () => {
  it("동일 입력은 항상 동일 출력(deep equal)", () => {
    const input = site({
      address: "서울특별시 강남구 역삼동 737",
      zoneCode: "준주거지역",
      effectiveFarPct: 400,
      effectiveBcrPct: 60,
      upzoningPotentialFarHigh: 600,
      upzoningFeasibilityTop: "상",
    });
    expect(buildLandProfile(input)).toEqual(buildLandProfile(input));
  });
});

describe("landProfileToEvidence", () => {
  it("null이면 빈 배열", () => {
    expect(landProfileToEvidence(null)).toEqual([]);
  });

  it("해소된 정량(far/bcr)을 EvidenceItem으로 변환(미해소 항목 제외)", () => {
    const p = buildLandProfile(
      site({
        zoneCode: "제2종일반주거지역",
        effectiveFarPct: 200,
        effectiveBcrPct: 50,
        farBasis: "지자체 조례 상한",
      }),
    );
    const items = landProfileToEvidence(p);
    const farItem = items.find((it) => it.label.includes("용적률"));
    expect(farItem).toBeDefined();
    expect(String(farItem!.value)).toBe("200%");
    expect(farItem!.basis).toBeTruthy();
  });

  it("미해소(far/bcr null·분석 전)면 근거 항목을 만들지 않는다(가짜 0/단정 금지)", () => {
    const p = buildLandProfile(site({ address: "서울특별시 강남구 역삼동 737" }));
    expect(landProfileToEvidence(p)).toEqual([]);
  });
});
