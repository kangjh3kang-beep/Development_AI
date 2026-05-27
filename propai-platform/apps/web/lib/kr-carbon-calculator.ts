/**
 * 한국 건물 탄소 배출량 / ZEB / G-SEED 계산기
 * 자재 내재탄소 + 운영탄소 + 시공탄소 → ZEB 등급 판정
 */

// ── 자재별 GWP (kgCO2eq/kg) ──
const MATERIAL_GWP: Record<string, number> = {
  concrete: 0.13,
  rebar: 1.46,
  steel: 2.0,
  glass: 1.44,
  insulation: 3.3,
  aluminum: 8.24,
  brick: 0.24,
  wood: 0.46,
  copper: 3.83,
  plastic: 3.14,
};

// ── 에너지 배출 계수 ──
const ENERGY_FACTORS = {
  electricity_kgCO2_per_kWh: 0.4594,
  gas_kgCO2_per_m3: 2.176,
  district_heating_kgCO2_per_kWh: 0.0584,
};

// ── 건물 용도별 기본 에너지 사용량 (kWh/m²/년) ──
const ENERGY_USE_INTENSITY: Record<string, { electricity: number; gas: number }> = {
  apartment: { electricity: 75, gas: 45 },
  office: { electricity: 150, gas: 30 },
  commercial: { electricity: 200, gas: 25 },
  officetel: { electricity: 120, gas: 35 },
  hospital: { electricity: 250, gas: 60 },
};

// ── 자재별 건물 m²당 사용량 (kg/m²) ──
const MATERIAL_PER_SQM: Record<string, number> = {
  concrete: 800,
  rebar: 60,
  steel: 25,
  glass: 15,
  insulation: 5,
  aluminum: 3,
  brick: 30,
};

// ── ZEB 등급 기준 (에너지 자립률 %) ──
const ZEB_GRADES = [
  { grade: 1, label: "ZEB 1등급", minRate: 100 },
  { grade: 2, label: "ZEB 2등급", minRate: 80 },
  { grade: 3, label: "ZEB 3등급", minRate: 60 },
  { grade: 4, label: "ZEB 4등급", minRate: 40 },
  { grade: 5, label: "ZEB 5등급", minRate: 20 },
];

// ── 인터페이스 ──
export interface CarbonInput {
  /** 연면적 (m²) */
  totalFloorArea: number;
  /** 건물 용도 */
  buildingUse: string;
  /** 건물 수명 (년, 기본 50년) */
  buildingLifespan?: number;
  /** 커스텀 자재 목록 (지정 시 기본 자재 대체) */
  customMaterials?: Array<{ name: string; weightKg: number; gwp?: number }>;
  /** 태양광 설치 용량 (kW) */
  solarCapacity?: number;
  /** 지열 설치 용량 (kW) */
  geothermalCapacity?: number;
  /** 단열 강화 여부 */
  enhancedInsulation?: boolean;
  /** 고효율 설비 적용 여부 */
  highEfficiencyEquipment?: boolean;
}

export interface MaterialCarbon {
  name: string;
  weightKg: number;
  gwp: number;
  totalCO2: number;
}

export interface CarbonResult {
  /** 자재 내재탄소 (kgCO2eq) */
  embodiedCarbon: {
    materials: MaterialCarbon[];
    total: number;
    perSqm: number;
  };
  /** 연간 운영탄소 (kgCO2eq/년) */
  operationalCarbon: {
    electricity: number;
    gas: number;
    total: number;
    perSqm: number;
  };
  /** 시공 탄소 (kgCO2eq) */
  constructionCarbon: number;
  /** 생애주기 총 탄소 (kgCO2eq) */
  lifecycleTotal: number;
  /** 생애주기 m²당 탄소 (kgCO2eq/m²) */
  lifecyclePerSqm: number;
  /** ZEB 평가 */
  zeb: {
    energySelfSufficiency: number;
    grade: number;
    label: string;
    solarGeneration: number;
    geothermalSaving: number;
  };
  /** 에너지 절감 제안 */
  recommendations: Array<{
    action: string;
    savingKgCO2: number;
    costGrade: "low" | "medium" | "high";
    priority: number;
  }>;
  /** G-SEED 예상 점수 (100점 만점) */
  gseedScore: number;
  gseedGrade: string;
}

/**
 * 탄소 배출량 계산
 */
export function calculateCarbonEmission(input: CarbonInput): CarbonResult {
  const area = input.totalFloorArea;
  const lifespan = input.buildingLifespan ?? 50;
  const use = input.buildingUse;

  // ── 1. 자재 내재탄소 ──
  let materials: MaterialCarbon[];
  if (input.customMaterials && input.customMaterials.length > 0) {
    materials = input.customMaterials.map((m) => ({
      name: m.name,
      weightKg: m.weightKg,
      gwp: m.gwp ?? MATERIAL_GWP[m.name] ?? 1.0,
      totalCO2: Math.round(m.weightKg * (m.gwp ?? MATERIAL_GWP[m.name] ?? 1.0)),
    }));
  } else {
    materials = Object.entries(MATERIAL_PER_SQM).map(([name, kgPerSqm]) => {
      const weight = Math.round(area * kgPerSqm);
      const gwp = MATERIAL_GWP[name] ?? 1.0;
      return { name, weightKg: weight, gwp, totalCO2: Math.round(weight * gwp) };
    });
  }
  const embodiedTotal = materials.reduce((s, m) => s + m.totalCO2, 0);

  // ── 2. 운영탄소 (연간) ──
  const eui = ENERGY_USE_INTENSITY[use] ?? ENERGY_USE_INTENSITY.apartment;
  let elecFactor = 1.0;
  let gasFactor = 1.0;
  if (input.enhancedInsulation) { elecFactor *= 0.85; gasFactor *= 0.7; }
  if (input.highEfficiencyEquipment) { elecFactor *= 0.8; gasFactor *= 0.85; }

  const elecKWh = area * eui.electricity * elecFactor;
  const gasM3 = area * eui.gas * gasFactor / 10.5; // kWh → m³ (1m³ ≈ 10.5 kWh)
  const elecCO2 = Math.round(elecKWh * ENERGY_FACTORS.electricity_kgCO2_per_kWh);
  const gasCO2 = Math.round(gasM3 * ENERGY_FACTORS.gas_kgCO2_per_m3);
  const opTotal = elecCO2 + gasCO2;

  // ── 3. 시공탄소 (연면적 기반 추정) ──
  const constructionCarbon = Math.round(area * 50); // 약 50 kgCO2/m²

  // ── 4. 생애주기 ──
  const lifecycleTotal = embodiedTotal + opTotal * lifespan + constructionCarbon;
  const lifecyclePerSqm = area > 0 ? Math.round(lifecycleTotal / area) : 0;

  // ── 5. ZEB 평가 ──
  const solarGen = (input.solarCapacity ?? 0) * 1200; // kW × 1200시간/년
  const geothermalSaving = (input.geothermalCapacity ?? 0) * 3000; // kW × COP 3.0 × 1000시간
  const totalEnergyUse = elecKWh + gasM3 * 10.5;
  const renewableEnergy = solarGen + geothermalSaving;
  const selfSufficiency = totalEnergyUse > 0 ? Math.min(100, (renewableEnergy / totalEnergyUse) * 100) : 0;

  let zebGrade = 0;
  let zebLabel = "ZEB 미달";
  for (const z of ZEB_GRADES) {
    if (selfSufficiency >= z.minRate) {
      zebGrade = z.grade;
      zebLabel = z.label;
      break;
    }
  }

  // ── 6. 절감 제안 ──
  const recommendations: CarbonResult["recommendations"] = [];
  if (!input.solarCapacity || input.solarCapacity < area * 0.1 / 3) {
    const suggestedKW = Math.round(area * 0.1 / 3);
    recommendations.push({
      action: `태양광 ${suggestedKW}kW 설치 (연간 ${(suggestedKW * 1200 * 0.4594).toLocaleString()} kgCO2 절감)`,
      savingKgCO2: Math.round(suggestedKW * 1200 * 0.4594),
      costGrade: "high", priority: 1,
    });
  }
  if (!input.enhancedInsulation) {
    recommendations.push({
      action: "패시브하우스 수준 단열 강화 (냉난방 에너지 30% 절감)",
      savingKgCO2: Math.round(opTotal * 0.2),
      costGrade: "medium", priority: 2,
    });
  }
  if (!input.highEfficiencyEquipment) {
    recommendations.push({
      action: "고효율 공조기 및 LED 조명 적용 (전력 20% 절감)",
      savingKgCO2: Math.round(elecCO2 * 0.2),
      costGrade: "low", priority: 3,
    });
  }
  if (!input.geothermalCapacity) {
    recommendations.push({
      action: "지열 히트펌프 설치 (가스 사용 50% 대체)",
      savingKgCO2: Math.round(gasCO2 * 0.5),
      costGrade: "high", priority: 4,
    });
  }

  // ── 7. G-SEED 점수 (간이 추정) ──
  let gseedScore = 40; // 기본 점수
  if (input.enhancedInsulation) gseedScore += 15;
  if (input.highEfficiencyEquipment) gseedScore += 10;
  if (selfSufficiency >= 20) gseedScore += 10;
  if (selfSufficiency >= 40) gseedScore += 5;
  if (selfSufficiency >= 60) gseedScore += 5;
  if ((input.solarCapacity ?? 0) > 0) gseedScore += 5;
  if ((input.geothermalCapacity ?? 0) > 0) gseedScore += 5;
  gseedScore = Math.min(100, gseedScore);

  const gseedGrade = gseedScore >= 80 ? "최우수 (그린1등급)"
    : gseedScore >= 70 ? "우수 (그린2등급)"
    : gseedScore >= 60 ? "우량 (그린3등급)"
    : gseedScore >= 50 ? "일반 (그린4등급)"
    : "미인증";

  return {
    embodiedCarbon: { materials, total: embodiedTotal, perSqm: area > 0 ? Math.round(embodiedTotal / area) : 0 },
    operationalCarbon: { electricity: elecCO2, gas: gasCO2, total: opTotal, perSqm: area > 0 ? Math.round(opTotal / area) : 0 },
    constructionCarbon,
    lifecycleTotal,
    lifecyclePerSqm,
    zeb: { energySelfSufficiency: Math.round(selfSufficiency * 10) / 10, grade: zebGrade, label: zebLabel, solarGeneration: Math.round(solarGen), geothermalSaving: Math.round(geothermalSaving) },
    recommendations,
    gseedScore,
    gseedGrade,
  };
}
