/**
 * 한국 건축법규 로컬 계산 엔진.
 *
 * LLM 호출 없이 즉시 한국 건축법/국토계획법 기반
 * 건폐율, 용적률, 높이 제한, 개발 시나리오를 계산합니다.
 *
 * 법적 근거:
 * - 국토의 계획 및 이용에 관한 법률 시행령 제84조 (건폐율)
 * - 국토의 계획 및 이용에 관한 법률 시행령 제85조 (용적률)
 */

// ── 용도지역별 법적 한도 테이블 ──

type ZoningSpec = {
  name: string;
  buildingCoverageMax: number; // 건폐율 상한 (%)
  floorAreaRatioMax: number;   // 용적률 상한 (%)
  heightLimit: number | null;  // 높이 제한 (m), null = 제한 없음
  category: "주거" | "상업" | "공업" | "녹지" | "관리" | "농림" | "자연환경";
  devScenarios: Array<{ title: string; score: number; reason: string }>;
};

const ZONING_DB: Record<string, ZoningSpec> = {
  "제1종전용주거지역": {
    name: "제1종전용주거지역",
    buildingCoverageMax: 50,
    floorAreaRatioMax: 100,
    heightLimit: 12,
    category: "주거",
    devScenarios: [
      { title: "단독주택 개발", score: 85, reason: "전용주거지역 최적 용도, 저층 고급 단독주택 수요 높음" },
      { title: "타운하우스", score: 72, reason: "100% 이하 용적률로 저밀도 타운하우스 적합" },
      { title: "근린생활시설", score: 15, reason: "전용주거지역 내 근생 입지 극히 제한적" },
    ],
  },
  "제2종전용주거지역": {
    name: "제2종전용주거지역",
    buildingCoverageMax: 50,
    floorAreaRatioMax: 150,
    heightLimit: 18,
    category: "주거",
    devScenarios: [
      { title: "공동주택(연립)", score: 82, reason: "150% 용적률로 중저층 공동주택 최적" },
      { title: "단독주택", score: 78, reason: "저밀도 주거환경 유지 가능" },
      { title: "근린생활시설", score: 20, reason: "전용주거지역 내 상업시설 제한" },
    ],
  },
  "제1종일반주거지역": {
    name: "제1종일반주거지역",
    buildingCoverageMax: 60,
    floorAreaRatioMax: 200,
    heightLimit: 16,
    category: "주거",
    devScenarios: [
      { title: "다세대/다가구 주택", score: 88, reason: "200% 용적률로 4층 이하 다세대 최적" },
      { title: "근린생활시설(1종)", score: 65, reason: "주거지 편의시설 수요 존재" },
      { title: "원룸/오피스텔", score: 45, reason: "16m 높이제한으로 오피스텔 효율 낮음" },
    ],
  },
  "제2종일반주거지역": {
    name: "제2종일반주거지역",
    buildingCoverageMax: 60,
    floorAreaRatioMax: 250,
    heightLimit: null,
    category: "주거",
    devScenarios: [
      { title: "아파트 (15층 이하)", score: 90, reason: "250% 용적률로 중층 아파트 최적, 서울시 대부분 아파트 단지" },
      { title: "오피스텔", score: 75, reason: "역세권 입지 시 오피스텔 수익성 양호" },
      { title: "근린상가 복합", score: 68, reason: "1~2층 상가 + 상층부 주거 복합 가능" },
    ],
  },
  "제3종일반주거지역": {
    name: "제3종일반주거지역",
    buildingCoverageMax: 50,
    floorAreaRatioMax: 300,
    heightLimit: null,
    category: "주거",
    devScenarios: [
      { title: "고층 아파트", score: 92, reason: "300% 용적률로 20층 이상 고층 아파트 개발 최적" },
      { title: "주상복합", score: 85, reason: "저층 상업 + 고층 주거 복합개발 가능" },
      { title: "오피스텔 타워", score: 78, reason: "역세권 고밀도 오피스텔 수익성 높음" },
    ],
  },
  "준주거지역": {
    name: "준주거지역",
    buildingCoverageMax: 70,
    floorAreaRatioMax: 500,
    heightLimit: null,
    category: "주거",
    devScenarios: [
      { title: "주상복합 대단지", score: 95, reason: "500% 용적률로 대규모 주상복합 최적" },
      { title: "업무 + 주거 복합", score: 88, reason: "상업/업무/주거 혼합 용도 허용" },
      { title: "오피스텔 + 상가", score: 82, reason: "높은 용적률로 수익형 부동산 최적" },
    ],
  },
  "일반상업지역": {
    name: "일반상업지역",
    buildingCoverageMax: 80,
    floorAreaRatioMax: 1300,
    heightLimit: null,
    category: "상업",
    devScenarios: [
      { title: "오피스 빌딩", score: 90, reason: "1300% 용적률로 대형 오피스 빌딩 최적" },
      { title: "상업/판매시설", score: 88, reason: "상업지역 본래 용도, 유동인구 활용" },
      { title: "호텔/숙박시설", score: 75, reason: "관광/비즈니스 수요 지역에 적합" },
    ],
  },
  "근린상업지역": {
    name: "근린상업지역",
    buildingCoverageMax: 70,
    floorAreaRatioMax: 900,
    heightLimit: null,
    category: "상업",
    devScenarios: [
      { title: "근린생활시설 복합", score: 92, reason: "900% 용적률로 상가+오피스 복합 최적" },
      { title: "메디컬/교육 복합", score: 78, reason: "주거지 인접 의료/학원 수요 높음" },
      { title: "소형 오피스텔", score: 72, reason: "1~2인 가구 수요 지역에 적합" },
    ],
  },
  "준공업지역": {
    name: "준공업지역",
    buildingCoverageMax: 70,
    floorAreaRatioMax: 400,
    heightLimit: null,
    category: "공업",
    devScenarios: [
      { title: "지식산업센터", score: 95, reason: "준공업지역 대표 개발형태, 세제 혜택" },
      { title: "물류센터", score: 80, reason: "교통 접근성 좋은 위치에 적합" },
      { title: "아파트형 공장 + 근생", score: 70, reason: "업무/제조 + 편의시설 복합" },
    ],
  },
  "자연녹지지역": {
    name: "자연녹지지역",
    buildingCoverageMax: 20,
    floorAreaRatioMax: 100,
    heightLimit: null,
    category: "녹지",
    devScenarios: [
      { title: "전원주택", score: 60, reason: "20% 건폐율로 넓은 마당 확보, 전원생활" },
      { title: "체육/레저시설", score: 55, reason: "녹지지역 허용 용도, 수요 확인 필요" },
      { title: "종교시설", score: 50, reason: "녹지지역 허용 용도 중 하나" },
    ],
  },
  "보전녹지지역": {
    name: "보전녹지지역",
    buildingCoverageMax: 20,
    floorAreaRatioMax: 80,
    heightLimit: null,
    category: "녹지",
    devScenarios: [
      { title: "개발 제한 (보전 우선)", score: 10, reason: "보전녹지는 개발이 극히 제한됩니다" },
      { title: "농업/임업 시설", score: 40, reason: "1차산업 용도만 제한적 허용" },
      { title: "자연 체험시설", score: 25, reason: "생태관광 등 제한적 허용" },
    ],
  },
};

// ── 용도지역명 정규화(SSOT) ──
//
// 부지분석(siteAnalysis.zoneCode)은 NED 토지특성(prposArea1Nm)·도시계획 등에서
// "일반상업", "제2종일반주거", 공백/괄호 포함 등 변형 표기가 들어올 수 있다.
// ZONING_DB 키는 정식 명칭("일반상업지역" 등)이라 변형 표기는 조회 실패 → 250%
// 기본값 폴백(용적률 환각)으로 이어진다. 모든 조회의 단일 정규화 게이트.
export function normalizeZoning(zoning?: string | null): string | null {
  const raw = (zoning || "").toString().trim();
  if (!raw) return null;
  // 정식 키 직매칭(공백/괄호 잡음 제거 후 포함 검사)
  const cleaned = raw.replace(/\s+/g, "");
  for (const key of Object.keys(ZONING_DB)) {
    if (cleaned === key || cleaned.includes(key)) return key;
  }
  // "지역" 접미사 누락 변형 보정(예: "일반상업"→"일반상업지역")
  for (const key of Object.keys(ZONING_DB)) {
    const stem = key.replace(/지역$/, "");
    if (cleaned === stem || cleaned.includes(stem)) return key;
  }
  // 단축코드(AutoDesignPanel 계열) 보정
  const codeMap: Record<string, string> = {
    "1R": "제1종일반주거지역",
    "2R": "제2종일반주거지역",
    "3R": "제3종일반주거지역",
    QR: "준주거지역",
    GC: "일반상업지역",
    NC: "근린상업지역",
    QI: "준공업지역",
  };
  if (codeMap[cleaned]) return codeMap[cleaned];
  return null;
}

// ── 주소에서 용도지역 추론 ──

function inferZoningFromAddress(address: string): string {
  const addr = address.toLowerCase();
  // 상업 중심지역 키워드
  if (/강남|역삼|삼성|서초|명동|종로|을지로|여의도|광화문/.test(addr)) {
    return "일반상업지역";
  }
  if (/홍대|건대|신촌|이태원|합정|상수|연남/.test(addr)) {
    return "근린상업지역";
  }
  // 주거 밀집 지역
  if (/잠실|송파|마포|용산|성수|왕십리|한남/.test(addr)) {
    return "제3종일반주거지역";
  }
  if (/아파트|단지/.test(addr)) {
    return "제2종일반주거지역";
  }
  // 산업 지역
  if (/구로|가산|금천|성수|문래/.test(addr)) {
    return "준공업지역";
  }
  // 경기도/외곽
  if (/의정부|파주|양주|포천|가평|연천/.test(addr)) {
    return "제2종일반주거지역";
  }
  if (/수원|성남|분당|판교|용인|화성|평택/.test(addr)) {
    return "제2종일반주거지역";
  }
  // 기본값
  return "제2종일반주거지역";
}

// ── 토지 특성 추론 ──

type LandCharacteristic = {
  label: string;
  value: string;
  status: "safe" | "warning" | "danger";
};

function inferLandCharacteristics(address: string, zoning: ZoningSpec): LandCharacteristic[] {
  const isUrban = zoning.category === "주거" || zoning.category === "상업" || zoning.category === "공업";
  return [
    {
      label: "경사도",
      value: isUrban ? "5° 이하 (평탄)" : "10° 내외 (경사)",
      status: isUrban ? "safe" : "warning",
    },
    {
      label: "접도 상태",
      value: isUrban ? "6m 이상 도로 접면" : "4m 도로 접면",
      status: "safe",
    },
    {
      label: "지형",
      value: isUrban ? "평지 (정형)" : "구릉지 (부정형)",
      status: isUrban ? "safe" : "warning",
    },
    {
      label: "높이 제한",
      value: zoning.heightLimit ? `${zoning.heightLimit}m (법적)` : "별도 제한 없음",
      status: zoning.heightLimit && zoning.heightLimit <= 16 ? "warning" : "safe",
    },
  ];
}

// ── 메인 분석 함수 ──

export type LocalAnalysisResult = {
  zoningName: string;
  zoningCategory: string;
  buildingCoverageMax: number;
  floorAreaRatioMax: number;
  heightLimit: number | null;
  characteristics: LandCharacteristic[];
  scenarios: Array<{ title: string; score: number; reason: string }>;
  summary: string;
};

export function analyzeLocally(address: string, pnu?: string): LocalAnalysisResult {
  const zoningKey = inferZoningFromAddress(address);
  const zoning = ZONING_DB[zoningKey] || ZONING_DB["제2종일반주거지역"];
  const characteristics = inferLandCharacteristics(address, zoning);

  const heightStr = zoning.heightLimit ? `${zoning.heightLimit}m` : "별도 제한 없음";

  return {
    zoningName: zoning.name,
    zoningCategory: zoning.category,
    buildingCoverageMax: zoning.buildingCoverageMax,
    floorAreaRatioMax: zoning.floorAreaRatioMax,
    heightLimit: zoning.heightLimit,
    characteristics,
    scenarios: zoning.devScenarios,
    summary: `${address}은(는) ${zoning.name}(${zoning.category}지역)에 해당합니다. ` +
      `건폐율 ${zoning.buildingCoverageMax}% 이하, 용적률 ${zoning.floorAreaRatioMax}% 이하, ` +
      `높이 제한 ${heightStr}이 적용됩니다. ` +
      `최적 개발 시나리오는 "${zoning.devScenarios[0].title}" (적합도 ${zoning.devScenarios[0].score}%)입니다.`,
  };
}

/**
 * 용적률 기반 최대 연면적 계산
 */
export function calcMaxGrossArea(landArea: number, zoning: string): number {
  const key = normalizeZoning(zoning);
  const spec = key ? ZONING_DB[key] : null;
  if (!spec) return landArea * 2.5; // 기본 250%
  return landArea * (spec.floorAreaRatioMax / 100);
}

/**
 * 주차 대수 산정 (주차장법 기준 간이 계산)
 */
export function calcParkingRequired(grossArea: number, buildingUse: string): number {
  // 주차장법 시행령 별표1 간이 적용
  const ratios: Record<string, number> = {
    "공동주택": 85,   // 85㎡당 1대
    "업무시설": 100,  // 100㎡당 1대
    "근린생활시설": 134, // 134㎡당 1대
    "숙박시설": 100,
    "판매시설": 100,
    "교육연구시설": 150,
  };
  const ratio = ratios[buildingUse] || 100;
  return Math.ceil(grossArea / ratio);
}

/**
 * 용도지역 목록 반환 (UI 드롭다운용)
 */
export function getZoningList(): Array<{ key: string; name: string; category: string }> {
  return Object.entries(ZONING_DB).map(([key, spec]) => ({
    key,
    name: spec.name,
    category: spec.category,
  }));
}

/**
 * 용도지역 상세 정보 조회
 */
export function getZoningSpec(zoning: string): ZoningSpec | null {
  const key = normalizeZoning(zoning);
  return key ? ZONING_DB[key] || null : null;
}
