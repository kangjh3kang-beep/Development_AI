// 토지 활용성 극대화 + AI 현실최적조합 추천 — SSOT siteAnalysis의 순수 파생 엔진.
//
// 비전(land-vitality-foundational-analysis 특화기능): 방대한 법규·조례 종합으로 용적률 극대화·
//   기부채납 최소화 "근거+방안"을 산출하고, AI가 현실적 최적조합을 자동 추천(이론최대≠현실최적).
//   저확률·역효과(기부채납 과다·미확인 요건) 방안은 제외 사유와 함께 빼고, 사람은 검토·조정만.
//
// 설계(U2와 동일 원칙): 별도 store writer 없이 siteAnalysis에서 결정론적으로 파생(순수·전수검증).
//   토지특성 foundation(U2: 현재 실효/법정 용적률·종상향 잠재) 위에 인센티브 완화를 쌓는다.
//
// 무날조(explainability-by-default): 완화율은 "법정 완화율 상한"(citable)만 사용하고, 실제 적용은
//   조례·심의·중복적용 한도에 좌우됨을 honestNote로 고지. 가변(역세권/임대/지구단위)은 SSOT 신호가
//   없으면 수치 null·가능성 "미확인"으로 정직 표기(0/임의값 금지). 종상향 잠재 용적률은 SSOT 실값 사용.

import type { SiteAnalysisData } from "@/store/useProjectContextStore";
import type { EvidenceItem } from "@/components/common/EvidencePanel";
import { resolveFarPct } from "@/lib/zoning-ssot";

export type UtilFeasibility = "상" | "중" | "하" | "미확인";

export type IncentiveCategory =
  | "공개공지"
  | "녹색건축"
  | "지능형건축"
  | "장수명주택"
  | "역세권종상향"
  | "임대주택"
  | "지구단위";

/** 인센티브 방안 1건의 평가 결과(현실최적 채택 여부·사유 포함). */
export interface IncentiveOutcome {
  key: string;
  label: string;
  category: IncentiveCategory;
  /** 법정 완화율 상한(% of base FAR). 가변(미산정)이면 null. */
  maxBonusPct: number | null;
  /** 완화 용적률(%포인트). base×maxBonusPct/100 또는 종상향 잠재차. 미산정 null. */
  bonusFarPoints: number | null;
  /** 실현 가능성. */
  feasibility: UtilFeasibility;
  /** 기부채납/공공기여 동반 여부. */
  donationRequired: boolean;
  /** 현실최적 조합에 채택됐는가. */
  included: boolean;
  /** 포함/제외 사유(통상어). */
  reason: string;
  /** 근거 법령 본문. */
  legalBasis: string;
}

/** 활용성 극대화 산출 — 이론최대 vs 현실최적. */
export interface UtilizationResult {
  /** 완화 기준 용적률(법정상한 우선, 없으면 실효). */
  baseFar: number | null;
  /** 법정상한 용적률(%). */
  legalFar: number | null;
  /** 현재 실효 용적률(%). */
  currentEffectiveFar: number | null;
  /** 이론최대 용적률(적용 가능 전 방안 합산). */
  theoreticalMaxFar: number | null;
  /** 현실최적 용적률(채택 조합 합산). */
  realisticOptimalFar: number | null;
  /** 현실최적 상승률(%, (현실최적-base)/base). */
  realisticGainPct: number | null;
  /** 인센티브 방안 전체(included 플래그로 채택 구분). */
  incentives: IncentiveOutcome[];
  /** 현실최적이 기부채납 동반 방안을 포함하지 않음. */
  donationMinimized: boolean;
  /** 한계 정직 고지(조례·심의·중복적용 한도). */
  honestNote: string;
}

/** 유한 숫자만 통과. 미해소 null. */
function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

function toFeasibility(v: unknown): UtilFeasibility | null {
  if (typeof v !== "string") return null;
  const g = v.trim();
  return g === "상" || g === "중" || g === "하" ? g : null;
}

/** 주거계열(준주거 포함) 용도지역 여부 — 장수명주택·역세권·임대 적용성 판정. */
function isResidential(zoneCode: string | null): boolean {
  return !!zoneCode && zoneCode.includes("주거");
}

/** 인센티브 카탈로그(법령 완화 상한 — citable). 동적 평가(가능성·완화량)는 optimizeUtilization에서. */
interface IncentiveRule {
  key: string;
  label: string;
  category: IncentiveCategory;
  /** 고정 완화율 상한(% of base). 가변(역세권/임대/지구단위)이면 null. */
  fixedBonusPct: number | null;
  donationRequired: boolean;
  legalBasis: string;
  /** 적용 가능 용도지역 판정(true=적용 가능). */
  applies: (zoneCode: string | null) => boolean;
  /** 적용 불가 사유(라벨). */
  notApplicableReason: string;
  /** 기본 가능성(역세권은 SSOT 신호로 동적 산정 — 여기선 미사용). */
  baseFeasibility: UtilFeasibility;
}

const RULES: IncentiveRule[] = [
  {
    key: "open_space",
    label: "공개공지 설치",
    category: "공개공지",
    fixedBonusPct: 20, // 건축법 시행령 제27조의2: 용적률·높이 1.2배 이내 완화
    donationRequired: false, // 대지 내 공지 제공(소유권 기부채납 아님)
    legalBasis: "건축법 시행령 제27조의2(공개공지 등의 확보)",
    applies: () => true,
    notApplicableReason: "",
    baseFeasibility: "상",
  },
  {
    key: "green_building",
    label: "녹색건축 인증",
    category: "녹색건축",
    fixedBonusPct: 15, // 녹색건축물 조성 지원법 제15조: 인증 등급별 용적률·높이 완화(조례)
    donationRequired: false,
    legalBasis: "녹색건축물 조성 지원법 제15조(건축물에 대한 효율적인 에너지 관리와 녹색건축물 조성의 활성화)",
    applies: () => true,
    notApplicableReason: "",
    baseFeasibility: "상",
  },
  {
    key: "intelligent_building",
    label: "지능형건축물(IBS) 인증",
    category: "지능형건축",
    fixedBonusPct: 15, // 건축법 제65조의2: 용적률 100분의 115 이내 완화
    donationRequired: false,
    legalBasis: "건축법 제65조의2(지능형건축물의 인증)",
    applies: () => true,
    notApplicableReason: "",
    baseFeasibility: "중", // 인증 비용·심의 부담 → 현실최적 기본 제외
  },
  {
    key: "long_life_housing",
    label: "장수명주택 인증",
    category: "장수명주택",
    fixedBonusPct: 15, // 주택건설기준 등에 관한 규정 제65조의2: 일반 등급 이상 → 용적률·건폐율 100분의 115 이내 완화
    donationRequired: false,
    legalBasis: "주택건설기준 등에 관한 규정 제65조의2(일반 등급 이상, 100분의 115 이내)",
    applies: isResidential,
    notApplicableReason: "공동주택(주거지역) 한정",
    baseFeasibility: "상",
  },
  {
    key: "transit_upzoning",
    label: "역세권 활성화·종상향",
    category: "역세권종상향",
    fixedBonusPct: null, // 가변 — 종상향 잠재(SSOT upzoning)로 산정
    donationRequired: true, // 공공기여(기부채납) 동반
    legalBasis: "국토의 계획 및 이용에 관한 법률 / 지자체 역세권 활성화 사업 운영지침",
    applies: isResidential,
    notApplicableReason: "주거·준주거 한정",
    baseFeasibility: "미확인",
  },
  {
    key: "rental_housing",
    label: "임대주택 공급(공공기여형)",
    category: "임대주택",
    fixedBonusPct: null, // 가변
    donationRequired: true, // 임대분 제공(공공기여)
    legalBasis: "도시 및 주거환경정비법 / 지구단위계획 운영기준(임대주택 건설 시 용적률 완화)",
    applies: isResidential,
    notApplicableReason: "주거지역 한정",
    baseFeasibility: "중",
  },
  {
    key: "district_unit_plan",
    label: "지구단위계획 공공시설 제공",
    category: "지구단위",
    fixedBonusPct: null, // 가변
    donationRequired: true, // 공공시설 부지 제공(기부채납)
    legalBasis: "국토의 계획 및 이용에 관한 법률 제52조(지구단위계획의 내용)",
    applies: () => true,
    notApplicableReason: "",
    baseFeasibility: "미확인",
  },
];

const HONEST_NOTE =
  "완화율은 법정 상한 기준이며 실제 적용은 지자체 조례·건축심의·중복적용 한도에 따라 달라질 수 있습니다. " +
  "역세권·지구단위 등 요건은 부지분석·조례 연동 후 정밀화됩니다.";

/**
 * SSOT siteAnalysis → 활용성 극대화(이론최대 vs 현실최적) 파생.
 * 기준 용적률(법정상한 우선, 없으면 실효)이 전혀 없으면 null(산정 불가).
 */
export function optimizeUtilization(
  site: SiteAnalysisData | null | undefined,
): UtilizationResult | null {
  if (!site) return null;
  // 기준 용적률(이론최대 산정 base) — 법정상한 우선(완화 보너스를 법정 기준으로 계산), 없으면
  // ★SSOT 읽기 통일: resolveFarPct(통합 > 실효 > 법정)로 폴백한다. 다필지에서는 단일유래
  //   nationalFarPct/effectiveFarPct가 store에서 제거(가드)되므로, 통합 실효(integratedFarEffPct)가
  //   baseFar의 진실원천이 된다(대표필지 자연녹지급 100% 오염 차단). 단일필지는 종전대로 법정우선(무회귀).
  const legalFar = num(site.nationalFarPct);
  // 현행 실효 용적률(표시·gain 산정용) — ★SSOT 읽기 통일: resolveFarPct(통합 > 실효 > 법정).
  //   다필지면 통합 실효가 단일 대표필지 실효를 대체한다.
  const currentEffectiveFar = resolveFarPct(site) ?? null;
  const baseFar = legalFar ?? currentEffectiveFar;
  if (baseFar == null) return null;

  const zoneCode = (site.zoneCode ?? "").trim() || null;
  const upHigh = num(site.upzoningPotentialFarHigh);
  const upTop = toFeasibility(site.upzoningFeasibilityTop);

  const incentives: IncentiveOutcome[] = RULES.map((rule) => {
    const applicable = rule.applies(zoneCode);

    // 완화량·가능성 산정(가변=역세권은 SSOT 종상향 신호 사용).
    let maxBonusPct: number | null;
    let bonusFarPoints: number | null;
    let feasibility: UtilFeasibility;

    if (rule.category === "역세권종상향") {
      if (upHigh != null && upHigh > baseFar) {
        bonusFarPoints = upHigh - baseFar;
        maxBonusPct = Math.round((bonusFarPoints / baseFar) * 100);
        feasibility = upTop ?? "중"; // 잠재 있음 + 등급 미상 → 보수적 중
      } else {
        bonusFarPoints = null;
        maxBonusPct = null;
        feasibility = "미확인"; // 종상향 신호 없음
      }
    } else if (rule.fixedBonusPct != null) {
      maxBonusPct = rule.fixedBonusPct;
      bonusFarPoints = Math.round((baseFar * rule.fixedBonusPct) / 100);
      feasibility = rule.baseFeasibility;
    } else {
      // 임대·지구단위 — 가변 완화(수치 미산정), 가능성은 기본값.
      maxBonusPct = null;
      bonusFarPoints = null;
      feasibility = rule.baseFeasibility;
    }

    // 적용 불가 용도지역이면 완화량 자체가 없다(0/임의값 금지) → 수치 null로 정규화.
    // (이론최대·현실최적 합산이 bonusFarPoints!=null만 보면 되도록 — reason 문자열 의존 제거.)
    if (!applicable) {
      maxBonusPct = null;
      bonusFarPoints = null;
    }

    // 현실최적 채택 판정(기부채납 최소화·가능성 가중).
    let included: boolean;
    let reason: string;
    if (!applicable) {
      included = false;
      reason = `${rule.notApplicableReason || "해당 용도 아님"} — 미적용`;
    } else if (rule.donationRequired) {
      if (feasibility === "상") {
        included = true;
        reason = "가능성 상 — 채택(기부채납·공공기여 동반)";
      } else {
        included = false;
        reason = `기부채납 동반·가능성 ${feasibility} — 현실최적 제외(기부채납 최소화)`;
      }
    } else {
      if (feasibility === "상") {
        included = true;
        reason = "개발자 선택·무기부 완화 — 채택";
      } else {
        included = false;
        reason = `가능성 ${feasibility}(비용·심의 부담) — 현실최적 제외`;
      }
    }

    return {
      key: rule.key,
      label: rule.label,
      category: rule.category,
      maxBonusPct,
      bonusFarPoints,
      feasibility,
      donationRequired: rule.donationRequired,
      included,
      reason,
      legalBasis: rule.legalBasis,
    };
  });

  // 합산(수치 산정된 완화만). 이론최대=적용 가능 전부, 현실최적=채택분.
  // bonusFarPoints는 적용 불가 시 null로 정규화돼 있어, null 여부만 보면 된다(견고).
  const theoMax =
    baseFar +
    incentives
      .filter((i) => i.bonusFarPoints != null)
      .reduce((s, i) => s + (i.bonusFarPoints ?? 0), 0);
  const realistic =
    baseFar +
    incentives
      .filter((i) => i.included && i.bonusFarPoints != null)
      .reduce((s, i) => s + (i.bonusFarPoints ?? 0), 0);

  const donationMinimized = !incentives.some(
    (i) => i.included && i.donationRequired,
  );
  const realisticGainPct =
    baseFar > 0 ? Math.round(((realistic - baseFar) / baseFar) * 100) : null;

  return {
    baseFar,
    legalFar,
    currentEffectiveFar,
    theoreticalMaxFar: theoMax,
    realisticOptimalFar: realistic,
    realisticGainPct,
    incentives,
    donationMinimized,
    honestNote: HONEST_NOTE,
  };
}

/**
 * 활용성 극대화 FAR 지표를 EvidencePanel 항목으로 변환(설명가능성 표준 재사용).
 * 미산정(null) 지표는 제외(가짜 0 금지).
 */
export function utilizationToEvidence(
  result: UtilizationResult | null | undefined,
): EvidenceItem[] {
  if (!result) return [];
  const includedLabels = result.incentives
    .filter((i) => i.included)
    .map((i) => i.label)
    .join(" + ");
  const out: EvidenceItem[] = [];
  if (result.legalFar != null) {
    out.push({
      label: "법정상한 용적률",
      value: `${result.legalFar}%`,
      basis: "용도지역 법정 용적률 상한",
      legalRef: { lawName: "국토의 계획 및 이용에 관한 법률 제78조(용적률)" },
    });
  }
  if (result.realisticOptimalFar != null) {
    out.push({
      label: "현실최적 용적률",
      value: `${result.realisticOptimalFar}%`,
      basis: includedLabels
        ? `법정 ${result.baseFar}% + 채택 완화(${includedLabels})`
        : `법정 ${result.baseFar}% 기준`,
      legalRef: null,
    });
  }
  if (result.theoreticalMaxFar != null) {
    out.push({
      label: "이론최대 용적률",
      value: `${result.theoreticalMaxFar}%`,
      basis: "적용 가능 전 완화방안 합산(중복적용 한도 미반영)",
      legalRef: null,
    });
  }
  return out;
}
