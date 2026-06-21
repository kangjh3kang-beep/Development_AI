// 토지특성 foundation(부지 생명력) — SSOT siteAnalysis의 순수 파생 projection.
//
// 비전(land-vitality-foundational-analysis): 토지특성 분석 = 모든 분석의 1번·중심.
//   Stage A 현시점 토지특성(현실적 용적/건폐율·건축가능분류·제한사항) →
//   Stage B 미래 토지특성(개발방식별 조/종상향 가능성·재산정 한도).
//
// 설계 결정(SSOT 단일 writer 불변식): landProfile은 별도 store 슬롯/writer를 만들지 않고
//   siteAnalysis(land 노드가 단일 owner)에서 **결정론적으로 파생**한다. 항상 SSOT와 일관,
//   마이그레이션·중복 0, 순수함수라 전수 단위검증 가능. 다운스트림은 이 projection을 읽는다.
//
// 무날조(explainability-by-default): 미해소 정량은 0으로 지어내지 않고 value=null(표시단 "—")로 두고,
//   honestNote/disclaimer로 한계를 정직 고지한다. 각 정량엔 도출이유(basis)·법령근거(legalBasis) 동반.

import type {
  SiteAnalysisData,
  UpzoningScenarioData,
} from "@/store/useProjectContextStore";
import type { EvidenceItem } from "@/components/common/EvidencePanel";
import { DEVELOPABILITY_LABEL } from "@/lib/zoning-ssot";

/** 가능성 등급(종상향). */
export type LandFeasibility = "상" | "중" | "하";

// 가능성 등급 순위 — 작을수록 상위('상' > '중' > '하').
const FEASIBILITY_RANK: Record<LandFeasibility, number> = { 상: 0, 중: 1, 하: 2 };

// 용적률/건폐율 법정 근거(국토계획법) — 한국 법령 상수(날조 아님, URL은 없어 텍스트 칩 폴백).
const FAR_LEGAL_BASIS = "국토의 계획 및 이용에 관한 법률 제78조(용적률)";
const BCR_LEGAL_BASIS = "국토의 계획 및 이용에 관한 법률 제77조(건폐율)";

const UPZONING_DISCLAIMER =
  "예상치 — 도시·군관리계획 결정 및 인허가를 전제로 한 잠재 시나리오이며 실현을 보장하지 않습니다.";

/** 설명가능성 동반 단일 정량 항목 — 미해소면 value=null(표시단 "—"). */
export interface LandMetric {
  /** 표시 이름(통상어). */
  label: string;
  /** 값(미해소 null — 0 강제 금지). */
  value: number | null;
  /** 단위 ("%" | "m" | "㎡"). */
  unit: string;
  /** 도출 이유 한 줄(통상어). 없으면 null. */
  basis: string | null;
  /** 법령 근거 본문(있으면). 없으면 null. */
  legalBasis: string | null;
}

/** 현시점 제한사항(각 법령근거). */
export interface LandRestriction {
  /** 제한 항목명(통상어). */
  label: string;
  /** 상세(없으면 null). */
  detail: string | null;
  /** 영향도. */
  severity: "info" | "caution" | "blocker";
  /** 근거 법령/기준(없으면 null). */
  legalBasis: string | null;
}

/** 미래 상향 시나리오(개발방식/인센티브별). */
export interface LandUpzoningScenario {
  /** 시나리오 이름(예: "역세권 종상향", "종상향 잠재"). */
  label: string;
  /** 목표 용도지역(없으면 null). */
  targetZone: string | null;
  /** 가능성 등급(미해소 null). */
  feasibility: LandFeasibility | null;
  /** 재산정 용적률 한도(%) — 상단(미해소 null). */
  potentialFarHigh: number | null;
  /** 재산정 용적률 하단(%) — 없으면 null. */
  potentialFarLow: number | null;
  /** 도출 이유(없으면 null). */
  rationale: string | null;
  /** 근거 법령(없으면 null). */
  legalBasis: string | null;
}

/** Stage A — 현시점 토지특성. */
export interface LandStageA {
  zoneCode: string | null;
  zoneMixed: boolean;
  /** 현실적 용적률(실효 우선, 미산정 시 법정상한·근거로 구분). */
  far: LandMetric;
  /** 현실적 건폐율. */
  bcr: LandMetric;
  /** 건축가능분류(특이부지 게이트 → 통상어 라벨). */
  buildableCategory: {
    /** developability 코드(POSSIBLE|CONDITIONAL|...). 일반부지면 null. */
    code: string | null;
    /** 통상어 라벨("개발 가능" 등). */
    label: string;
    /** 도출 이유(특이부지 정직고지 등). 없으면 null. */
    rationale: string | null;
  };
  /** 제한사항(각 법령근거). */
  restrictions: LandRestriction[];
}

/** Stage B — 미래 토지특성. */
export interface LandStageB {
  /** 개발방식/인센티브별 상향 시나리오. */
  scenarios: LandUpzoningScenario[];
  /** 종합 최상 가능성 등급(시나리오 중 best, 없으면 null). */
  topFeasibility: LandFeasibility | null;
  /** 잠재 최대 용적률(%) — 시나리오 중 최고(없으면 null). */
  potentialFarHigh: number | null;
  /** 예상치 고지(미확정·전제). */
  disclaimer: string;
}

/** 토지특성 foundation — Stage A 현시점 + Stage B 미래(SSOT siteAnalysis 파생). */
export interface LandProfile {
  /** 분석 대상 주소(없으면 null). */
  address: string | null;
  stageA: LandStageA;
  stageB: LandStageB;
  /** 미해소/한계 전반 고지(데이터 부족 시). 없으면 null. */
  honestNote: string | null;
}

/** 유한 숫자만 통과(NaN/Infinity/비숫자 제거). 미해소 시 null. */
function num(v: unknown): number | null {
  return typeof v === "number" && Number.isFinite(v) ? v : null;
}

/** 가능성 등급 문자열을 검증된 LandFeasibility로 좁힌다(공백 정규화). 미일치 시 null. */
function toFeasibility(v: unknown): LandFeasibility | null {
  if (typeof v !== "string") return null;
  const g = v.trim();
  return g === "상" || g === "중" || g === "하" ? g : null;
}

/** Stage A 현실적 용적/건폐율 — 실효 우선, 없으면 법정상한 폴백(근거로 구분). */
function resolveMetric(
  label: string,
  effective: number | null,
  national: number | null,
  legalBasis: string,
  farBasis: string | null,
): LandMetric {
  if (effective != null) {
    const basis = farBasis ? `실효 ${label} · ${farBasis}` : `실효 ${label}`;
    return { label, value: effective, unit: "%", basis, legalBasis };
  }
  if (national != null) {
    return {
      label,
      value: national,
      unit: "%",
      basis: "법정상한 (실효 미산정 — 조례·계획 확인 필요)",
      legalBasis,
    };
  }
  return { label, value: null, unit: "%", basis: null, legalBasis };
}

/** 특이부지 factors[]·zoneMixed → 제한사항 목록. */
function buildRestrictions(site: SiteAnalysisData): LandRestriction[] {
  const out: LandRestriction[] = [];
  const sp = site.specialParcel;
  if (sp?.isSpecial) {
    const severity: LandRestriction["severity"] =
      sp.developability === "BLOCKED" ? "blocker" : "caution";
    for (const f of sp.factors ?? []) {
      const label = (f ?? "").toString().trim();
      if (label) out.push({ label, detail: null, severity, legalBasis: null });
    }
  }
  if (site.zoneMixed) {
    out.push({
      label: "용도지역 혼재",
      detail: "2개 이상 용도지역이 섞인 부지 — 면적가중·분리검토 필요",
      severity: "caution",
      legalBasis: null,
    });
  }
  return out;
}

/** SSOT upzoning 집계/per-scenario → Stage B 미래 시나리오. */
function buildStageB(site: SiteAnalysisData): LandStageB {
  const scenarios: LandUpzoningScenario[] = [];
  const raw = site.upzoningScenarios;
  if (Array.isArray(raw) && raw.length > 0) {
    for (const s of raw) {
      scenarios.push(mapScenario(s));
    }
  } else {
    // per-scenario 부재 → 집계값(상한 용적·최상 가능성)으로 단일 요약 시나리오.
    const high = num(site.upzoningPotentialFarHigh);
    const top = toFeasibility(site.upzoningFeasibilityTop);
    if (high != null || top != null) {
      scenarios.push({
        label: "종상향 잠재",
        targetZone: null,
        feasibility: top,
        potentialFarHigh: high,
        potentialFarLow: null,
        rationale: null,
        legalBasis: null,
      });
    }
  }

  // 집계: 최상 가능성(rank 최소) + 최대 잠재 용적률.
  let topFeasibility: LandFeasibility | null = null;
  let bestRank = Number.POSITIVE_INFINITY;
  let potentialFarHigh: number | null = null;
  for (const s of scenarios) {
    if (s.feasibility != null && FEASIBILITY_RANK[s.feasibility] < bestRank) {
      bestRank = FEASIBILITY_RANK[s.feasibility];
      topFeasibility = s.feasibility;
    }
    if (s.potentialFarHigh != null) {
      potentialFarHigh =
        potentialFarHigh == null
          ? s.potentialFarHigh
          : Math.max(potentialFarHigh, s.potentialFarHigh);
    }
  }

  return { scenarios, topFeasibility, potentialFarHigh, disclaimer: UPZONING_DISCLAIMER };
}

/** UpzoningScenarioData(SSOT) → LandUpzoningScenario(표시형). */
function mapScenario(s: UpzoningScenarioData): LandUpzoningScenario {
  const label =
    (s.path ?? "").trim() ||
    (s.targetZone ?? "").trim() ||
    "종상향 시나리오";
  return {
    label,
    targetZone: (s.targetZone ?? "").trim() || null,
    feasibility: toFeasibility(s.feasibility),
    potentialFarHigh: num(s.expectedFarHighPct),
    potentialFarLow: num(s.expectedFarLowPct),
    rationale: (s.rationale ?? "").trim() || null,
    legalBasis: (s.legalBasis ?? "").trim() || null,
  };
}

/**
 * SSOT siteAnalysis → LandProfile 파생(결정론·무날조).
 * site가 없거나 식별정보(주소/PNU/용도지역)가 전혀 없으면 null(표시할 토지특성 없음).
 */
export function buildLandProfile(
  site: SiteAnalysisData | null | undefined,
): LandProfile | null {
  if (!site) return null;
  const address = (site.address ?? "").trim() || null;
  const pnu = (site.pnu ?? "").trim() || null;
  const zoneCode = (site.zoneCode ?? "").trim() || null;
  if (!address && !pnu && !zoneCode) return null;

  const far = resolveMetric(
    "용적률",
    num(site.effectiveFarPct),
    num(site.nationalFarPct),
    FAR_LEGAL_BASIS,
    (site.farBasis ?? "").trim() || null,
  );
  const bcr = resolveMetric(
    "건폐율",
    num(site.effectiveBcrPct),
    num(site.nationalBcrPct),
    BCR_LEGAL_BASIS,
    (site.farBasis ?? "").trim() || null,
  );

  const sp = site.specialParcel;
  let buildableCategory: LandStageA["buildableCategory"];
  if (sp?.isSpecial) {
    buildableCategory = {
      code: sp.developability ?? null,
      label:
        (sp.developability && DEVELOPABILITY_LABEL[sp.developability]) ||
        "검토 필요",
      rationale: (sp.honest ?? "").trim() || null,
    };
  } else if (far.value != null || zoneCode != null) {
    // 용도지역/용적률이 확인된 일반 부지 — 개발 가능.
    buildableCategory = { code: null, label: "개발 가능", rationale: null };
  } else {
    // 분석 전(주소만 확보) — 단정하지 않는다(거짓 양성 '개발 가능' 금지).
    buildableCategory = {
      code: null,
      label: "분석 전",
      rationale: "용도지역 분석 후 확정",
    };
  }

  const stageA: LandStageA = {
    zoneCode,
    zoneMixed: site.zoneMixed === true,
    far,
    bcr,
    buildableCategory,
    restrictions: buildRestrictions(site),
  };

  const stageB = buildStageB(site);

  // 현실적 용적률조차 미해소면(용도지역 미확정 등) 한계를 정직 고지(상태별 정확 문구).
  const honestNote =
    far.value == null
      ? zoneCode
        ? "용도지역은 확인됐으나 실효 용적률이 아직 산정되지 않았습니다. 부지분석을 완료하면 자동 갱신됩니다."
        : "용도지역·실효 용적률이 확정되지 않아 현시점 토지특성을 정밀 산정하지 못했습니다. 부지분석을 완료하면 자동 갱신됩니다."
      : null;

  return { address, stageA, stageB, honestNote };
}

/**
 * Stage A 정량을 EvidencePanel 항목으로 변환(설명가능성 표준 재사용).
 * 미해소(value=null) 정량은 제외(가짜 0 표시 금지). 건축가능분류는 정성 항목으로 포함.
 */
export function landProfileToEvidence(
  profile: LandProfile | null | undefined,
): EvidenceItem[] {
  if (!profile) return [];
  const out: EvidenceItem[] = [];
  for (const m of [profile.stageA.far, profile.stageA.bcr]) {
    if (m.value == null) continue;
    out.push({
      label: m.label,
      value: `${m.value}${m.unit}`,
      basis: m.basis,
      legalRef: m.legalBasis ? { lawName: m.legalBasis } : null,
    });
  }
  // 건축가능분류는 확정된 경우만 근거에 포함('분석 전' 단정 금지).
  const bc = profile.stageA.buildableCategory;
  if (bc.label !== "분석 전") {
    out.push({
      label: "건축가능분류",
      value: bc.label,
      basis: bc.rationale,
      legalRef: null,
    });
  }
  return out;
}
