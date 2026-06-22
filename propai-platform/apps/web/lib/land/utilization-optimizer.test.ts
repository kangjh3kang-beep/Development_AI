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

  it("현실최적 용적률 = base + 채택 완화 합(무날조 정수)", () => {
    // base 250 + 공개공지 20%(50) + 녹색 15%(38) + 장수명 15%(38) = 376
    // 장수명주택: 주택건설기준 등에 관한 규정 제65조의2(100분의 115) → +15%(250×0.15=37.5→38)
    expect(r.realisticOptimalFar).toBe(376);
  });

  it("이론최대 용적률 ≥ 현실최적(제외 방안까지 합산)", () => {
    expect(r.theoreticalMaxFar).toBeGreaterThan(r.realisticOptimalFar!);
    // 이론최대는 지능형건축(15%,38)도 합산 → 376 + 38 = 414
    expect(r.theoreticalMaxFar).toBe(414);
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

describe("utilizationToEvidence", () => {
  it("null이면 빈 배열", () => {
    expect(utilizationToEvidence(null)).toEqual([]);
  });

  it("FAR 지표(법정/이론최대/현실최적)를 EvidenceItem으로 변환", () => {
    const r = optimizeUtilization(site({ zoneCode: "제2종일반주거지역", nationalFarPct: 250 }));
    const items = utilizationToEvidence(r);
    const optimal = items.find((it) => it.label.includes("현실최적"));
    expect(optimal).toBeDefined();
    expect(optimal!.basis).toBeTruthy();
  });
});
