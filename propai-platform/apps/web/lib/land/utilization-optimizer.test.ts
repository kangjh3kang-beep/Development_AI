import { describe, it, expect } from "vitest";
import {
  optimizeUtilization,
  utilizationToEvidence,
} from "@/lib/land/utilization-optimizer";
import type { SiteAnalysisData } from "@/store/useProjectContextStore";

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

describe("optimizeUtilization — 게이트", () => {
  it("site가 없거나 기준 용적률(법정/실효)이 전혀 없으면 null", () => {
    expect(optimizeUtilization(null)).toBeNull();
    expect(optimizeUtilization(site({ address: "서울 강남" }))).toBeNull();
  });

  it("법정상한(nationalFarPct)이 있으면 결과를 만든다", () => {
    const r = optimizeUtilization(
      site({ zoneCode: "제2종일반주거지역", nationalFarPct: 250 }),
    );
    expect(r).not.toBeNull();
    expect(r!.baseFar).toBe(250);
    expect(r!.legalFar).toBe(250);
  });
});

describe("optimizeUtilization — 현실최적(기부채납 최소화)", () => {
  // ★F2 캡: base가 이미 법정상한(nationalFarPct=250)일 때 인센티브 합산은 법정상한 250으로 캡된다
  //   (백엔드 min(base+incentive, cap_far) 정합). 캡 여지를 보이기 위해 종상향 신호로 잠재상한을 올린 케이스는
  //   별도 describe에서 검증. 여기선 채택/제외 판정과 캡 동작을 함께 확인한다.
  const r = optimizeUtilization(
    site({ zoneCode: "제2종일반주거지역", nationalFarPct: 250, effectiveFarPct: 200 }),
  )!;

  it("개발자 통제·무기부 완화(공개공지·녹색건축·장수명)는 현실최적에 포함", () => {
    const included = r.incentives.filter((i) => i.included).map((i) => i.category);
    expect(included).toContain("공개공지");
    expect(included).toContain("녹색건축");
    expect(included).toContain("장수명주택"); // 주거지역
  });

  it("기부채납 동반·미확인 방안(임대·지구단위·역세권 미확인)은 현실최적에서 제외 + 사유", () => {
    const lease = r.incentives.find((i) => i.category === "임대주택")!;
    expect(lease.included).toBe(false);
    expect(lease.donationRequired).toBe(true);
    expect(lease.reason).toBeTruthy();
    const transit = r.incentives.find((i) => i.category === "역세권종상향")!;
    expect(transit.included).toBe(false); // upzoning 신호 없음 → 미확인
    expect(transit.feasibility).toBe("미확인");
  });

  it("현실최적은 기부채납 동반 방안을 포함하지 않아 donationMinimized=true", () => {
    expect(r.donationMinimized).toBe(true);
  });

  it("★F2 캡: base=법정상한(250)이면 채택 완화 합산이 법정상한 250으로 캡된다(오도방지)", () => {
    // 단순가산이면 base 250 + 공개공지 50 + 녹색 38 + 장수명 38 = 376이지만,
    // 법정상한 250 캡 적용 → realisticOptimalFar=250(백엔드 min(base+incentive, cap_far) 정합).
    expect(r.legalCapFar).toBe(250);
    expect(r.realisticOptimalFar).toBe(250);
  });

  it("★F2 캡: 이론최대도 법정상한 250으로 캡 + isCapped=true + 캡 전 단순가산치 보존", () => {
    expect(r.theoreticalMaxFar).toBe(250);
    expect(r.isCapped).toBe(true);
    // 캡 전 단순가산(uncapped)은 근거·오도방지 배지용으로 보존(250 초과).
    expect(r.theoreticalUncappedFar).toBeGreaterThan(250);
  });

  it("현재 실효 용적률(effective)을 별도 보존", () => {
    expect(r.currentEffectiveFar).toBe(200);
  });
});

describe("optimizeUtilization — 용도지역 적용성", () => {
  it("비주거(상업)에서는 장수명주택(공동주택 한정)을 제외하고 사유 표기", () => {
    const r = optimizeUtilization(
      site({ zoneCode: "일반상업지역", nationalFarPct: 800 }),
    )!;
    const longlife = r.incentives.find((i) => i.category === "장수명주택")!;
    expect(longlife.included).toBe(false);
    expect(longlife.reason).toContain("주거");
  });
});

describe("optimizeUtilization — 역세권 종상향(SSOT 신호)", () => {
  it("upzoning 신호(가능성 상 + 잠재 용적률)가 있으면 역세권을 현실최적에 포함하되 기부채납 표기", () => {
    const r = optimizeUtilization(
      site({
        zoneCode: "준주거지역",
        nationalFarPct: 400,
        upzoningPotentialFarHigh: 600,
        upzoningFeasibilityTop: "상",
      }),
    )!;
    const transit = r.incentives.find((i) => i.category === "역세권종상향")!;
    expect(transit.feasibility).toBe("상");
    expect(transit.included).toBe(true);
    expect(transit.donationRequired).toBe(true);
    expect(transit.bonusFarPoints).toBe(200); // 600 - 400
    // 기부채납 동반 방안이 채택됐으므로 donationMinimized=false(정직)
    expect(r.donationMinimized).toBe(false);
  });
});

describe("optimizeUtilization — 결정론·정직", () => {
  it("동일 입력은 동일 출력", () => {
    const input = site({ zoneCode: "준주거지역", nationalFarPct: 400, effectiveFarPct: 400 });
    expect(optimizeUtilization(input)).toEqual(optimizeUtilization(input));
  });

  it("honestNote(조례·심의·중복적용 한도 한계)를 항상 동반", () => {
    const r = optimizeUtilization(site({ zoneCode: "준주거지역", nationalFarPct: 400 }))!;
    expect(r.honestNote).toBeTruthy();
  });
});

describe("optimizeUtilization — F2 법정상한 캡(자연녹지 150→100)", () => {
  // ★사용자 지적 라이브 시나리오: 자연녹지 법정 100% 필지 + 인센티브 → 캡 없이 150% 강조가 오도.
  const r = optimizeUtilization(
    site({ zoneCode: "자연녹지지역", nationalFarPct: 100, effectiveFarPct: 100 }),
  )!;

  it("법정상한 캡=100(용도지역 법정상한)", () => {
    expect(r.legalCapFar).toBe(100);
  });

  it("이론최대·현실최적이 법정상한 100으로 캡(150 아님) + isCapped=true", () => {
    expect(r.theoreticalMaxFar).toBe(100);
    expect(r.realisticOptimalFar).toBe(100);
    expect(r.isCapped).toBe(true);
    // 캡 전 단순가산치는 100 초과(공개공지 등 완화 합산) — 보존.
    expect(r.theoreticalUncappedFar).toBeGreaterThan(100);
  });

  it("캡됐으므로 현실최적 상향률은 0%(base 대비 순증 없음·정직)", () => {
    expect(r.realisticGainPct).toBe(0);
  });
});

describe("optimizeUtilization — F5 층수 바인딩 강등(녹지)", () => {
  const r = optimizeUtilization(
    site({ zoneCode: "자연녹지지역", nationalFarPct: 100 }),
  )!;

  it("floorBound=true(녹지)이고 honestNote에 층수완화 선행 고지 포함", () => {
    expect(r.floorBound).toBe(true);
    expect(r.honestNote).toContain("층수완화");
  });

  it("적용 가능·완화량 있는 인센티브(공개공지 등)는 가능성 한 단계 강등 + 층수 caveat", () => {
    const openSpace = r.incentives.find((i) => i.category === "공개공지")!;
    // 원래 '상' → 층수바인딩 강등 → '중'
    expect(openSpace.feasibility).toBe("중");
    expect(openSpace.reason).toContain("층수완화");
  });

  it("비바인딩 용도지역(주거)은 강등 없음(무회귀)", () => {
    const r2 = optimizeUtilization(
      site({ zoneCode: "제3종일반주거지역", nationalFarPct: 300 }),
    )!;
    expect(r2.floorBound).toBe(false);
    const openSpace2 = r2.incentives.find((i) => i.category === "공개공지")!;
    expect(openSpace2.feasibility).toBe("상");
  });
});

describe("utilizationToEvidence", () => {
  it("null이면 빈 배열", () => {
    expect(utilizationToEvidence(null)).toEqual([]);
  });

  it("FAR 지표(법정/이론상 상한/현실최적)를 EvidenceItem으로 변환", () => {
    const r = optimizeUtilization(site({ zoneCode: "제2종일반주거지역", nationalFarPct: 250 }));
    const items = utilizationToEvidence(r);
    const optimal = items.find((it) => it.label.includes("현실최적"));
    expect(optimal).toBeDefined();
    expect(optimal!.basis).toBeTruthy();
  });

  it("U2: 이론상 상한 라벨 사용 + 캡 시 근거에 법정상한 캡 명시", () => {
    const r = optimizeUtilization(site({ zoneCode: "자연녹지지역", nationalFarPct: 100 }));
    const items = utilizationToEvidence(r);
    const theo = items.find((it) => it.label.includes("이론상 상한"));
    expect(theo).toBeDefined();
    expect(theo!.basis).toContain("법정상한");
  });
});
