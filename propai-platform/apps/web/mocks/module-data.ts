export type ParcelStatus = "available" | "review" | "restricted";
export type RiskLevel = "stable" | "watch" | "warning";
export type FloorPlanStatus = "recommended" | "draft" | "review";
export type InspectionStatus = "ready" | "pending" | "offline";
export type BimElementStatus = "ready" | "review" | "blocked";
export type DroneSeverity = "low" | "medium" | "high";
export type AgentStepStatus = "completed" | "active" | "waiting";
export type AgentConnectionStatus = "connected" | "reconnecting" | "idle";
export type EscrowState =
  | "funded"
  | "review"
  | "release-ready"
  | "disputed";

export type ParcelShape = {
  id: string;
  label: string;
  areaSqm: number;
  owner: string;
  status: ParcelStatus;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type FloorPlanDraft = {
  id: string;
  name: string;
  summary: string;
  areaLabel: string;
  prompt: string;
  status: FloorPlanStatus;
  rooms: string[];
};

export type ReportSection = {
  id: string;
  title: string;
  content: string;
};

export type CollaborationMember = {
  id: string;
  name: string;
  role: string;
  color: string;
  x: number;
  y: number;
};

export type AvmComparable = {
  id: string;
  title: string;
  amount: number;
  distance: string;
  change: string;
};

export type AvmSnapshot = {
  estimate: number;
  changeRate: string;
  confidence: string;
  comparables: AvmComparable[];
};

export type JeonseRiskFactor = {
  id: string;
  label: string;
  level: RiskLevel;
  detail: string;
};

export type JeonseRiskSnapshot = {
  score: number;
  grade: string;
  summary: string;
  factors: JeonseRiskFactor[];
};

export type TaxScenario = {
  acquisitionPrice: number;
  salePrice: number;
  deductibleCost: number;
  holdingYears: number;
};

export type InspectionItem = {
  id: string;
  title: string;
  status: InspectionStatus;
  detail: string;
};

export type BimModelLayer = {
  id: string;
  label: string;
  level: string;
  heightMeters: number;
  footprintWidth: number;
  footprintDepth: number;
  tint: string;
};

export type BimQuantityItem = {
  id: string;
  name: string;
  category: string;
  quantity: number;
  unit: string;
  progress: string;
  status: BimElementStatus;
};

export type BimSnapshot = {
  layers: BimModelLayer[];
  quantities: BimQuantityItem[];
  xrReady: boolean;
};

export type DroneDefect = {
  id: string;
  title: string;
  severity: DroneSeverity;
  zone: string;
  confidence: number;
  x: number;
  y: number;
  detail: string;
};

export type DroneSnapshot = {
  capturedAt: string;
  completionRate: string;
  riskSummary: string;
  defects: DroneDefect[];
};

export type AgentStage = {
  id: string;
  title: string;
  status: AgentStepStatus;
  detail: string;
  updatedAt: string;
};

export type AgentSnapshot = {
  connection: AgentConnectionStatus;
  lastEventAt: string;
  stages: AgentStage[];
};

export type EscrowEvent = {
  id: string;
  title: string;
  time: string;
};

export type EscrowSnapshot = {
  state: EscrowState;
  balance: number;
  feeBps: number;
  expiresAt: string;
  milestone: string;
  subcontractor: string;
  contractAddress: string;
  transactionHash: string;
  events: EscrowEvent[];
};

export type ModuleSnapshot = {
  parcels: ParcelShape[];
  floorPlans: FloorPlanDraft[];
  reportSections: ReportSection[];
  collaborationMembers: CollaborationMember[];
  avm: AvmSnapshot;
  jeonseRisk: JeonseRiskSnapshot;
  taxScenario: TaxScenario;
  inspectionItems: InspectionItem[];
  bim: BimSnapshot;
  drone: DroneSnapshot;
  agent: AgentSnapshot;
  escrow: EscrowSnapshot;
};

const sampleProjectModules: ModuleSnapshot = {
  parcels: [
    {
      id: "parcel-a",
      label: "A-12",
      areaSqm: 421.8,
      owner: "성수개발 컨소시엄",
      status: "available",
      x: 8,
      y: 16,
      width: 28,
      height: 32,
    },
    {
      id: "parcel-b",
      label: "A-13",
      areaSqm: 356.2,
      owner: "개인 소유",
      status: "review",
      x: 40,
      y: 12,
      width: 24,
      height: 36,
    },
    {
      id: "parcel-c",
      label: "A-14",
      areaSqm: 488.4,
      owner: "프로퍼티 홀딩스",
      status: "available",
      x: 16,
      y: 54,
      width: 34,
      height: 24,
    },
    {
      id: "parcel-d",
      label: "A-15",
      areaSqm: 275.6,
      owner: "권리분석 필요",
      status: "restricted",
      x: 56,
      y: 52,
      width: 22,
      height: 26,
    },
  ],
  floorPlans: [
    {
      id: "plan-core",
      name: "도심 복합형 기본안",
      summary: "1층 상업시설과 상부 코리빙을 결합한 기본 조합입니다.",
      areaLabel: "연면적 8,420㎡",
      prompt: "성수동 복합개발, 저층 상업시설, 중층 코워킹, 상층 코리빙, 남향 채광 강화",
      status: "recommended",
      rooms: ["상업시설", "공용 라운지", "코워킹", "주거 유닛"],
    },
    {
      id: "plan-courtyard",
      name: "중정형 조망 강화안",
      summary: "중정과 테라스를 확장해 체류 시간을 늘리는 대안입니다.",
      areaLabel: "연면적 8,180㎡",
      prompt: "중정형 매스, 공용 테라스 확대, 복층 커뮤니티, 일조 최적화",
      status: "draft",
      rooms: ["중정", "리테일", "테라스", "주거 유닛"],
    },
    {
      id: "plan-office",
      name: "업무 비중 확대안",
      summary: "오피스 비중을 높여 임대수익 안정성을 강화한 시나리오입니다.",
      areaLabel: "연면적 8,760㎡",
      prompt: "업무시설 중심, 저층 리테일 축소, 지식산업형 오피스, 모듈형 평면",
      status: "review",
      rooms: ["리테일", "오피스", "회의실", "서비스 코어"],
    },
  ],
  reportSections: [
    {
      id: "section-1",
      title: "사업성 요약",
      content:
        "대상지는 역세권 접근성이 우수하고, 근린생활시설과 소형 주거 복합 비율이 시장 수요와 부합합니다. 현재 권리관계 검토가 필요한 필지가 일부 존재해 인허가 전 단계에서 협상 순서를 조정하는 것이 필요합니다.",
    },
    {
      id: "section-2",
      title: "설계 제안",
      content:
        "중정형 기본안은 채광과 체류 경험 측면에서 우위가 있습니다. 다만 업무 비중 확대안이 수익 안정성 지표에서는 더 높게 나타나므로, 금융 모듈과 연계한 민감도 비교가 다음 작업으로 적절합니다.",
    },
    {
      id: "section-3",
      title: "권장 액션",
      content:
        "권리분석이 필요한 필지부터 우선 협상 대상으로 지정하고, 설계 프롬프트에 코워킹 면적 상한을 반영해 2차 시안을 생성하는 것이 적합합니다. 병행해서 에스크로 연계 조건 정의서를 정리해야 합니다.",
    },
  ],
  collaborationMembers: [
    {
      id: "member-1",
      name: "서윤",
      role: "설계 PM",
      color: "#0e7490",
      x: 22,
      y: 28,
    },
    {
      id: "member-2",
      name: "민재",
      role: "사업성 분석",
      color: "#d97706",
      x: 64,
      y: 42,
    },
    {
      id: "member-3",
      name: "하린",
      role: "권리분석",
      color: "#13212f",
      x: 48,
      y: 68,
    },
  ],
  avm: {
    estimate: 128000000000,
    changeRate: "+3.6%",
    confidence: "78%",
    comparables: [
      {
        id: "comp-1",
        title: "성수 근린복합 A",
        amount: 121000000000,
        distance: "420m",
        change: "+2.8%",
      },
      {
        id: "comp-2",
        title: "성수 업무시설 B",
        amount: 132500000000,
        distance: "760m",
        change: "+4.1%",
      },
      {
        id: "comp-3",
        title: "뚝섬 리테일 C",
        amount: 126400000000,
        distance: "1.1km",
        change: "+3.4%",
      },
    ],
  },
  jeonseRisk: {
    score: 24,
    grade: "낮음",
    summary:
      "전세가율과 거래량 흐름이 안정적이며, 인근 공급 충격도 제한적입니다.",
    factors: [
      {
        id: "factor-1",
        label: "전세가율",
        level: "stable",
        detail: "실거래 대비 전세 비율이 58% 수준으로 안정권입니다.",
      },
      {
        id: "factor-2",
        label: "권리관계",
        level: "watch",
        detail: "일부 필지의 근저당 이력 확인이 추가로 필요합니다.",
      },
      {
        id: "factor-3",
        label: "공급 충격",
        level: "stable",
        detail: "반경 2km 내 대규모 신규 공급이 제한적입니다.",
      },
    ],
  },
  taxScenario: {
    acquisitionPrice: 9200000000,
    salePrice: 12800000000,
    deductibleCost: 420000000,
    holdingYears: 3,
  },
  inspectionItems: [
    {
      id: "inspection-1",
      title: "오프라인 체크리스트 동기화",
      status: "ready",
      detail: "최종 점검표 템플릿이 준비되어 현장 태블릿에 내려받을 수 있습니다.",
    },
    {
      id: "inspection-2",
      title: "드론 사진 업로드",
      status: "pending",
      detail: "서버 업로드 엔드포인트 대기 상태로 로컬 보관 모드만 활성화되어 있습니다.",
    },
    {
      id: "inspection-3",
      title: "현장 네트워크 백업",
      status: "offline",
      detail: "지하층 구간은 오프라인 배너와 재시도 안내를 우선 표출합니다.",
    },
  ],
  bim: {
    layers: [
      {
        id: "layer-base",
        label: "Podium Retail",
        level: "B1 ~ 2F",
        heightMeters: 12,
        footprintWidth: 42,
        footprintDepth: 28,
        tint: "#d97706",
      },
      {
        id: "layer-office",
        label: "Coworking Office",
        level: "3F ~ 6F",
        heightMeters: 16,
        footprintWidth: 36,
        footprintDepth: 24,
        tint: "#0e7490",
      },
      {
        id: "layer-living",
        label: "Co-living Tower",
        level: "7F ~ 14F",
        heightMeters: 28,
        footprintWidth: 30,
        footprintDepth: 20,
        tint: "#13212f",
      },
    ],
    quantities: [
      {
        id: "qty-1",
        name: "외벽 커튼월",
        category: "Facade",
        quantity: 1840,
        unit: "㎡",
        progress: "도면 정합 82%",
        status: "ready",
      },
      {
        id: "qty-2",
        name: "철근 콘크리트",
        category: "Structure",
        quantity: 2460,
        unit: "㎥",
        progress: "산출 검토 74%",
        status: "review",
      },
      {
        id: "qty-3",
        name: "계단실 방화문",
        category: "Safety",
        quantity: 36,
        unit: "EA",
        progress: "사양 확인 필요",
        status: "blocked",
      },
      {
        id: "qty-4",
        name: "세대 내부 마감",
        category: "Interior",
        quantity: 612,
        unit: "실",
        progress: "옵션 비교 68%",
        status: "review",
      },
    ],
    xrReady: false,
  },
  drone: {
    capturedAt: "2026-03-18T07:40:00+09:00",
    completionRate: "78%",
    riskSummary: "옥상 방수 구간과 북측 외벽 조인트에서 추가 점검이 필요합니다.",
    defects: [
      {
        id: "defect-1",
        title: "옥상 방수 분리",
        severity: "high",
        zone: "Roof / Zone A",
        confidence: 94,
        x: 68,
        y: 22,
        detail: "빗물 유입 가능성이 높아 즉시 보수 우선순위로 분류되었습니다.",
      },
      {
        id: "defect-2",
        title: "북측 패널 이격",
        severity: "medium",
        zone: "North Facade / Zone C",
        confidence: 81,
        x: 34,
        y: 48,
        detail: "패널 조인트 간격이 기준보다 넓어 재측정이 필요합니다.",
      },
      {
        id: "defect-3",
        title: "주차장 바닥 균열",
        severity: "low",
        zone: "B1 Parking / Zone D",
        confidence: 73,
        x: 54,
        y: 76,
        detail: "초기 균열로 보이며 경과 관찰 대상입니다.",
      },
    ],
  },
  agent: {
    connection: "reconnecting",
    lastEventAt: "2026-03-18T07:36:00+09:00",
    stages: [
      {
        id: "stage-1",
        title: "토지 데이터 수집",
        status: "completed",
        detail: "필지와 권리분석 기초 데이터 수집이 끝났습니다.",
        updatedAt: "2026-03-18T07:05:00+09:00",
      },
      {
        id: "stage-2",
        title: "규제 요약 생성",
        status: "completed",
        detail: "인허가 선행조건과 규제 체크포인트를 정리했습니다.",
        updatedAt: "2026-03-18T07:14:00+09:00",
      },
      {
        id: "stage-3",
        title: "설계 프롬프트 조정",
        status: "active",
        detail: "코워킹 면적과 공용 커뮤니티 비율을 다시 계산 중입니다.",
        updatedAt: "2026-03-18T07:36:00+09:00",
      },
      {
        id: "stage-4",
        title: "사업성 재계산",
        status: "waiting",
        detail: "설계 시안 갱신 이후 자동 실행됩니다.",
        updatedAt: "2026-03-18T07:36:00+09:00",
      },
      {
        id: "stage-5",
        title: "에스크로 조건 정리",
        status: "waiting",
        detail: "하도급 직불 조건 해시가 확정되면 이어집니다.",
        updatedAt: "2026-03-18T07:36:00+09:00",
      },
      {
        id: "stage-6",
        title: "보고서 스트리밍",
        status: "waiting",
        detail: "금융 결과가 반영된 뒤 최종 문안이 생성됩니다.",
        updatedAt: "2026-03-18T07:36:00+09:00",
      },
      {
        id: "stage-7",
        title: "검토 요청 전송",
        status: "waiting",
        detail: "전체 파이프라인 종료 후 이해관계자에게 전달됩니다.",
        updatedAt: "2026-03-18T07:36:00+09:00",
      },
    ],
  },
  escrow: {
    state: "review",
    balance: 1860000000,
    feeBps: 30,
    expiresAt: "2026-04-02T18:00:00+09:00",
    milestone: "구조 검토 완료 후 1차 대금 집행",
    subcontractor: "성수 구조엔지니어링",
    contractAddress: "0x3Fa2...92De",
    transactionHash: "0x9a1f...4c8e",
    events: [
      {
        id: "escrow-event-1",
        title: "에스크로 생성",
        time: "2026-03-18T06:42:00+09:00",
      },
      {
        id: "escrow-event-2",
        title: "자금 예치 완료",
        time: "2026-03-18T06:58:00+09:00",
      },
      {
        id: "escrow-event-3",
        title: "검토 상태 전환",
        time: "2026-03-18T07:22:00+09:00",
      },
    ],
  },
};

const riverFrontModules: ModuleSnapshot = {
  ...sampleProjectModules,
  avm: {
    estimate: 146000000000,
    changeRate: "+1.9%",
    confidence: "71%",
    comparables: [
      {
        id: "comp-r-1",
        title: "여의도 상업용지 A",
        amount: 142000000000,
        distance: "680m",
        change: "+1.2%",
      },
      {
        id: "comp-r-2",
        title: "강변 복합개발 B",
        amount: 151400000000,
        distance: "1.4km",
        change: "+2.5%",
      },
      {
        id: "comp-r-3",
        title: "업무복합 시설 C",
        amount: 145800000000,
        distance: "980m",
        change: "+1.7%",
      },
    ],
  },
  jeonseRisk: {
    score: 46,
    grade: "보통",
    summary:
      "시장 유동성은 양호하지만 규제 변화에 따른 민감도가 높아 관찰이 필요합니다.",
    factors: [
      {
        id: "factor-r-1",
        label: "전세가율",
        level: "watch",
        detail: "대형 면적대 거래량이 줄어 변동성 점검이 필요합니다.",
      },
      {
        id: "factor-r-2",
        label: "규제 민감도",
        level: "warning",
        detail: "세금 및 용도규제 변경 시 수익성 변동폭이 큽니다.",
      },
      {
        id: "factor-r-3",
        label: "공급 충격",
        level: "stable",
        detail: "단기 신규 공급은 제한적입니다.",
      },
    ],
  },
};

const smartYardModules: ModuleSnapshot = {
  ...sampleProjectModules,
  reportSections: [
    {
      id: "smart-1",
      title: "현장 점검 요약",
      content:
        "부지 접근성은 양호하지만 야적장 구간의 배수 상태 확인이 우선입니다. 오프라인 점검 모드에서 체크리스트와 사진 메타데이터를 함께 저장하도록 설계하는 것이 적절합니다.",
    },
    {
      id: "smart-2",
      title: "운영 권고",
      content:
        "드론 촬영 구간과 지상 점검 구간을 분리해 기록해야 합니다. 네트워크 불안정 구간에서는 동기화 지연 안내와 재연결 상태를 명확하게 보여줘야 합니다.",
    },
  ],
  inspectionItems: [
    {
      id: "smart-inspection-1",
      title: "비행 전 점검 체크",
      status: "ready",
      detail: "배터리, 비행 금지구역, 날씨 조건 검수가 완료되었습니다.",
    },
    {
      id: "smart-inspection-2",
      title: "하자 좌표 저장",
      status: "pending",
      detail: "현장 좌표 저장은 로컬 큐까지만 연결되어 있습니다.",
    },
    {
      id: "smart-inspection-3",
      title: "네트워크 재연결 안내",
      status: "offline",
      detail: "지하 창고 구간에서는 오프라인 배너와 저장 성공 토스트가 우선 노출됩니다.",
    },
  ],
  drone: {
    capturedAt: "2026-03-17T15:10:00+09:00",
    completionRate: "64%",
    riskSummary: "야적장 배수로와 창고 지붕 접합부에 추가 비행 점검이 필요합니다.",
    defects: [
      {
        id: "smart-defect-1",
        title: "배수로 침하",
        severity: "medium",
        zone: "Yard / Zone B",
        confidence: 88,
        x: 44,
        y: 34,
        detail: "집중호우 시 배수 장애 가능성이 있어 현장 재측정이 필요합니다.",
      },
      {
        id: "smart-defect-2",
        title: "지붕 접합부 균열",
        severity: "high",
        zone: "Warehouse Roof / Zone E",
        confidence: 92,
        x: 72,
        y: 18,
        detail: "누수 가능성이 있어 방수 보수 우선순위가 높습니다.",
      },
    ],
  },
};

const moduleSnapshots: Record<string, ModuleSnapshot> = {
  "sample-project": sampleProjectModules,
  "river-front": riverFrontModules,
  "smart-yard": smartYardModules,
};

export function getMockModuleSnapshot(projectId: string) {
  return moduleSnapshots[projectId] ?? sampleProjectModules;
}
