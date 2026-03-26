import type { Locale } from "@/i18n/config";
import type {
  AgentConnectionStatus,
  AgentStepStatus,
  BimElementStatus,
  DroneSeverity,
  EscrowState,
  FloorPlanStatus,
  InspectionStatus,
  ParcelStatus,
  RiskLevel,
} from "@/mocks/module-data";

type LocaleCopy = {
  design: {
    workspaceTitle: string;
    workspaceDescription: string;
    previewTitle: string;
    generatorTitle: string;
    generatorDescription: string;
    promptLabel: string;
    uploadLabel: string;
    generateLabel: string;
    referenceIdle: string;
    referenceReady: string;
    optionsTitle: string;
      statusLabels: Record<FloorPlanStatus, string>;
      statusTitle: string;
      areaLabel: string;
      roomsLabel: string;
      collaborationTitle: string;
    collaborationDescription: string;
  };
  finance: {
    overviewTitle: string;
    avmTitle: string;
    estimateLabel: string;
    changeRateLabel: string;
    confidenceLabel: string;
    comparablesTitle: string;
    riskTitle: string;
    scoreLabel: string;
    summaryLabel: string;
    factorsTitle: string;
    factorLabels: Record<RiskLevel, string>;
  };
  bim: {
    workspaceTitle: string;
    viewerTitle: string;
    viewerDescription: string;
    xrReadyLabel: string;
    xrFallbackLabel: string;
    quantityTitle: string;
    categoryLabel: string;
    quantityLabel: string;
    progressLabel: string;
    statusLabels: Record<BimElementStatus, string>;
  };
  drone: {
    heatmapTitle: string;
    heatmapDescription: string;
    capturedAtLabel: string;
    completionLabel: string;
    riskSummaryLabel: string;
    legendTitle: string;
    defectsTitle: string;
    severityLabels: Record<DroneSeverity, string>;
  };
  agent: {
    timelineTitle: string;
    timelineDescription: string;
    connectionTitle: string;
    reconnectLabel: string;
    updatedAtLabel: string;
    connectionLabels: Record<AgentConnectionStatus, string>;
    statusLabels: Record<AgentStepStatus, string>;
  };
  blockchain: {
    escrowTitle: string;
    escrowDescription: string;
    balanceLabel: string;
    feeLabel: string;
    expiresAtLabel: string;
    milestoneLabel: string;
    subcontractorLabel: string;
    contractLabel: string;
    txLabel: string;
    eventsTitle: string;
    stateLabels: Record<EscrowState, string>;
  };
  report: {
    mapTitle: string;
    mapDescription: string;
    legendTitle: string;
    parcelInfoTitle: string;
    areaLabel: string;
    ownerLabel: string;
    statusLabel: string;
    statusLabels: Record<ParcelStatus, string>;
    streamTitle: string;
    streamDescription: string;
  };
  tax: {
    calculatorTitle: string;
    calculatorDescription: string;
    acquisitionLabel: string;
    saleLabel: string;
    deductibleLabel: string;
    holdingYearsLabel: string;
    acquisitionTaxLabel: string;
    capitalGainsTaxLabel: string;
    localTaxLabel: string;
    totalTaxLabel: string;
    netLabel: string;
    resetLabel: string;
  };
  inspection: {
    onlineTitle: string;
    offlineTitle: string;
    onlineDescription: string;
    offlineDescription: string;
    cachedTitle: string;
    cachedDescription: string;
    cachedAtLabel: string;
    checklistTitle: string;
    statusLabels: Record<InspectionStatus, string>;
  };
};

const moduleCopy: Record<Locale, LocaleCopy> = {
  ko: {
    design: {
      workspaceTitle: "설계 워크스페이스",
      workspaceDescription: "프롬프트 시안 선택과 참조 이미지 상태를 한 화면에서 확인합니다.",
      previewTitle: "선택된 평면도 시안",
      generatorTitle: "평면도 생성 패널",
      generatorDescription: "Mock 프롬프트와 참조 이미지를 기준으로 추천 시안을 전환합니다.",
      promptLabel: "생성 프롬프트",
      uploadLabel: "참조 이미지 업로드",
      generateLabel: "추천 시안 반영",
      referenceIdle: "참조 이미지가 아직 선택되지 않았습니다.",
      referenceReady: "선택된 참조 이미지",
      optionsTitle: "추천 시안 목록",
      statusLabels: {
        recommended: "추천",
        draft: "초안",
        review: "검토 필요",
      },
      statusTitle: "상태",
      areaLabel: "면적",
      roomsLabel: "주요 공간",
      collaborationTitle: "협업 커서 오버레이",
      collaborationDescription: "설계, 사업성, 권리분석 담당자의 현재 검토 위치를 Mock 상태로 표시합니다.",
    },
    finance: {
      overviewTitle: "금융 분석 패널",
      avmTitle: "AI 시세 추정",
      estimateLabel: "추정 가치",
      changeRateLabel: "최근 변동률",
      confidenceLabel: "신뢰도",
      comparablesTitle: "비교 거래",
      riskTitle: "전세 리스크 진단",
      scoreLabel: "리스크 점수",
      summaryLabel: "요약",
      factorsTitle: "세부 요인",
      factorLabels: {
        stable: "안정",
        watch: "관찰",
        warning: "경고",
      },
    },
    bim: {
      workspaceTitle: "BIM 검토 워크스페이스",
      viewerTitle: "3D IFC Mock 뷰어",
      viewerDescription: "층별 매스를 빠르게 점검하고 XR 가능 여부를 함께 확인합니다.",
      xrReadyLabel: "WebXR 준비 완료",
      xrFallbackLabel: "WebXR 미지원 환경",
      quantityTitle: "물량 산출 표",
      categoryLabel: "카테고리",
      quantityLabel: "물량",
      progressLabel: "진행 상태",
      statusLabels: {
        ready: "준비 완료",
        review: "검토 필요",
        blocked: "차단",
      },
    },
    drone: {
      heatmapTitle: "드론 하자 히트맵",
      heatmapDescription: "심각도와 위치를 한 화면에서 파악할 수 있도록 Mock 좌표를 렌더링합니다.",
      capturedAtLabel: "촬영 시각",
      completionLabel: "점검 진행률",
      riskSummaryLabel: "위험 요약",
      legendTitle: "심각도 범례",
      defectsTitle: "탐지 하자 목록",
      severityLabels: {
        low: "낮음",
        medium: "보통",
        high: "높음",
      },
    },
    agent: {
      timelineTitle: "AI 에이전트 타임라인",
      timelineDescription: "7단계 실행 흐름과 재연결 상태를 Mock 이벤트로 시각화합니다.",
      connectionTitle: "스트림 연결 상태",
      reconnectLabel: "재연결 시뮬레이션",
      updatedAtLabel: "갱신 시각",
      connectionLabels: {
        connected: "연결됨",
        reconnecting: "재연결 중",
        idle: "대기",
      },
      statusLabels: {
        completed: "완료",
        active: "진행 중",
        waiting: "대기",
      },
    },
    blockchain: {
      escrowTitle: "에스크로 상태 카드",
      escrowDescription: "배포 주소, 마일스톤, 만료일, 거래 해시를 프론트에서 먼저 검증합니다.",
      balanceLabel: "예치 금액",
      feeLabel: "수수료",
      expiresAtLabel: "만료일",
      milestoneLabel: "현재 마일스톤",
      subcontractorLabel: "하도급사",
      contractLabel: "컨트랙트 주소",
      txLabel: "트랜잭션",
      eventsTitle: "최근 이벤트",
      stateLabels: {
        funded: "예치 완료",
        review: "검토 중",
        "release-ready": "지급 가능",
        disputed: "분쟁 상태",
      },
    },
    report: {
      mapTitle: "지적도 Mock 뷰",
      mapDescription: "필지 상태와 소유 주체를 한 번에 파악할 수 있도록 요약합니다.",
      legendTitle: "범례",
      parcelInfoTitle: "선택 필지 정보",
      areaLabel: "면적",
      ownerLabel: "소유 주체",
      statusLabel: "상태",
      statusLabels: {
        available: "활용 가능",
        review: "검토 필요",
        restricted: "제약 있음",
      },
      streamTitle: "스트리밍 리포트",
      streamDescription: "SSE 연결 전까지 Mock 텍스트 스트림으로 보고서 렌더링 구조를 검증합니다.",
    },
    tax: {
      calculatorTitle: "세금 계산기",
      calculatorDescription: "취득가, 양도가, 보유 기간을 기준으로 기본 세액 시나리오를 계산합니다.",
      acquisitionLabel: "취득가",
      saleLabel: "양도가",
      deductibleLabel: "필요 경비",
      holdingYearsLabel: "보유 기간(년)",
      acquisitionTaxLabel: "취득세 추정",
      capitalGainsTaxLabel: "양도세 추정",
      localTaxLabel: "지방소득세 추정",
      totalTaxLabel: "총 세액",
      netLabel: "세후 예상 금액",
      resetLabel: "기본값 복원",
    },
    inspection: {
      onlineTitle: "현장 연결 정상",
      offlineTitle: "오프라인 모드 활성화",
      onlineDescription: "네트워크가 연결되어 있어 최신 점검 상태를 바로 동기화할 수 있습니다.",
      offlineDescription: "네트워크가 불안정하면 체크리스트와 사진 메타데이터를 로컬에 저장한 뒤 재연결 시 전송합니다.",
      cachedTitle: "마지막 캐시 기준",
      cachedDescription: "오프라인 상황에서는 마지막 점검 데이터와 로컬 큐 안내를 기준으로 현장 작업을 이어갑니다.",
      cachedAtLabel: "캐시 시각",
      checklistTitle: "현장 점검 체크리스트",
      statusLabels: {
        ready: "준비 완료",
        pending: "대기",
        offline: "오프라인 우선",
      },
    },
  },
  en: {
    design: {
      workspaceTitle: "Design Workspace",
      workspaceDescription: "Review prompt variants and reference image status in one workspace.",
      previewTitle: "Selected Floor Plan",
      generatorTitle: "Floor Plan Generator",
      generatorDescription: "Switch recommended drafts from mock prompts and reference images.",
      promptLabel: "Generation Prompt",
      uploadLabel: "Upload Reference",
      generateLabel: "Apply Recommended Draft",
      referenceIdle: "No reference image has been selected yet.",
      referenceReady: "Selected reference",
      optionsTitle: "Recommended Drafts",
      statusLabels: {
        recommended: "Recommended",
        draft: "Draft",
        review: "Needs Review",
      },
      statusTitle: "Status",
      areaLabel: "Area",
      roomsLabel: "Key spaces",
      collaborationTitle: "Collaboration Cursor Overlay",
      collaborationDescription: "Mock cursor positions from design, finance, and title-review teammates.",
    },
    finance: {
      overviewTitle: "Finance Analysis Panel",
      avmTitle: "AI Valuation",
      estimateLabel: "Estimated value",
      changeRateLabel: "Recent change",
      confidenceLabel: "Confidence",
      comparablesTitle: "Comparable deals",
      riskTitle: "Jeonse Risk Review",
      scoreLabel: "Risk score",
      summaryLabel: "Summary",
      factorsTitle: "Risk factors",
      factorLabels: {
        stable: "Stable",
        watch: "Watch",
        warning: "Warning",
      },
    },
    bim: {
      workspaceTitle: "BIM Review Workspace",
      viewerTitle: "3D IFC Mock Viewer",
      viewerDescription: "Review layered massing quickly and surface XR readiness together.",
      xrReadyLabel: "WebXR ready",
      xrFallbackLabel: "WebXR fallback mode",
      quantityTitle: "Quantity Table",
      categoryLabel: "Category",
      quantityLabel: "Quantity",
      progressLabel: "Progress",
      statusLabels: {
        ready: "Ready",
        review: "Review",
        blocked: "Blocked",
      },
    },
    drone: {
      heatmapTitle: "Drone Defect Heatmap",
      heatmapDescription: "Render mock coordinates with severity and zone information in one view.",
      capturedAtLabel: "Captured at",
      completionLabel: "Inspection progress",
      riskSummaryLabel: "Risk summary",
      legendTitle: "Severity legend",
      defectsTitle: "Detected defects",
      severityLabels: {
        low: "Low",
        medium: "Medium",
        high: "High",
      },
    },
    agent: {
      timelineTitle: "AI Agent Timeline",
      timelineDescription: "Visualize the seven-step execution flow with reconnect state indicators.",
      connectionTitle: "Stream status",
      reconnectLabel: "Simulate reconnect",
      updatedAtLabel: "Updated",
      connectionLabels: {
        connected: "Connected",
        reconnecting: "Reconnecting",
        idle: "Idle",
      },
      statusLabels: {
        completed: "Completed",
        active: "Active",
        waiting: "Waiting",
      },
    },
    blockchain: {
      escrowTitle: "Escrow Status Card",
      escrowDescription: "Validate address, milestone, expiry, and transaction hash before contract wiring.",
      balanceLabel: "Escrow balance",
      feeLabel: "Fee",
      expiresAtLabel: "Expires",
      milestoneLabel: "Current milestone",
      subcontractorLabel: "Subcontractor",
      contractLabel: "Contract",
      txLabel: "Transaction",
      eventsTitle: "Recent events",
      stateLabels: {
        funded: "Funded",
        review: "In review",
        "release-ready": "Release ready",
        disputed: "Disputed",
      },
    },
    report: {
      mapTitle: "Cadastral Mock View",
      mapDescription: "Summarize parcel status and ownership in one glance.",
      legendTitle: "Legend",
      parcelInfoTitle: "Selected parcel",
      areaLabel: "Area",
      ownerLabel: "Owner",
      statusLabel: "Status",
      statusLabels: {
        available: "Available",
        review: "Review",
        restricted: "Restricted",
      },
      streamTitle: "Streaming Report",
      streamDescription: "Validate streaming report rendering with mock text before SSE wiring.",
    },
    tax: {
      calculatorTitle: "Tax Calculator",
      calculatorDescription: "Estimate a baseline tax scenario from acquisition, sale, and holding period.",
      acquisitionLabel: "Acquisition price",
      saleLabel: "Sale price",
      deductibleLabel: "Deductible cost",
      holdingYearsLabel: "Holding period (years)",
      acquisitionTaxLabel: "Acquisition tax",
      capitalGainsTaxLabel: "Capital gains tax",
      localTaxLabel: "Local income tax",
      totalTaxLabel: "Total tax",
      netLabel: "Estimated net amount",
      resetLabel: "Reset",
    },
    inspection: {
      onlineTitle: "Field Connection Healthy",
      offlineTitle: "Offline Mode Enabled",
      onlineDescription: "The network is available, so inspection status can sync immediately.",
      offlineDescription: "If the connection drops, checklists and photo metadata are stored locally and sent after reconnect.",
      cachedTitle: "Last cached snapshot",
      cachedDescription: "During offline work, the field team continues from the latest cached inspection state and local queue guidance.",
      cachedAtLabel: "Cached at",
      checklistTitle: "Field Inspection Checklist",
      statusLabels: {
        ready: "Ready",
        pending: "Pending",
        offline: "Offline first",
      },
    },
  },
  "zh-CN": {
    design: {
      workspaceTitle: "设计工作区",
      workspaceDescription: "在同一界面查看提示词方案和参考图状态。",
      previewTitle: "当前选中的平面方案",
      generatorTitle: "平面方案生成面板",
      generatorDescription: "基于 Mock 提示词与参考图切换推荐方案。",
      promptLabel: "生成提示词",
      uploadLabel: "上传参考图",
      generateLabel: "应用推荐方案",
      referenceIdle: "尚未选择参考图。",
      referenceReady: "已选择的参考图",
      optionsTitle: "推荐方案列表",
      statusLabels: {
        recommended: "推荐",
        draft: "草案",
        review: "待复核",
      },
      statusTitle: "状态",
      areaLabel: "面积",
      roomsLabel: "主要空间",
      collaborationTitle: "协作光标叠层",
      collaborationDescription: "以 Mock 状态显示设计、测算、权利分析成员的当前位置。",
    },
    finance: {
      overviewTitle: "金融分析面板",
      avmTitle: "AI 估值",
      estimateLabel: "估计价值",
      changeRateLabel: "近期变化",
      confidenceLabel: "置信度",
      comparablesTitle: "可比案例",
      riskTitle: "租赁风险诊断",
      scoreLabel: "风险分数",
      summaryLabel: "摘要",
      factorsTitle: "细分因素",
      factorLabels: {
        stable: "稳定",
        watch: "观察",
        warning: "警告",
      },
    },
    bim: {
      workspaceTitle: "BIM 审查工作区",
      viewerTitle: "3D IFC Mock 视图",
      viewerDescription: "快速检查分层体量，并同时显示 XR 可用性。",
      xrReadyLabel: "WebXR 已就绪",
      xrFallbackLabel: "WebXR 回退模式",
      quantityTitle: "工程量表",
      categoryLabel: "类别",
      quantityLabel: "工程量",
      progressLabel: "进度",
      statusLabels: {
        ready: "已准备",
        review: "待复核",
        blocked: "受阻",
      },
    },
    drone: {
      heatmapTitle: "无人机缺陷热力图",
      heatmapDescription: "在一个视图中呈现 Mock 坐标、严重度与区域信息。",
      capturedAtLabel: "拍摄时间",
      completionLabel: "检查进度",
      riskSummaryLabel: "风险摘要",
      legendTitle: "严重度图例",
      defectsTitle: "检测到的缺陷",
      severityLabels: {
        low: "低",
        medium: "中",
        high: "高",
      },
    },
    agent: {
      timelineTitle: "AI 智能体时间线",
      timelineDescription: "以 Mock 事件展示七阶段执行流程与重连状态。",
      connectionTitle: "流连接状态",
      reconnectLabel: "模拟重连",
      updatedAtLabel: "更新时间",
      connectionLabels: {
        connected: "已连接",
        reconnecting: "重连中",
        idle: "等待中",
      },
      statusLabels: {
        completed: "已完成",
        active: "进行中",
        waiting: "等待中",
      },
    },
    blockchain: {
      escrowTitle: "托管状态卡片",
      escrowDescription: "在接入真实合约前，先验证地址、里程碑、到期日与交易哈希的前端表现。",
      balanceLabel: "托管金额",
      feeLabel: "手续费",
      expiresAtLabel: "到期时间",
      milestoneLabel: "当前里程碑",
      subcontractorLabel: "分包方",
      contractLabel: "合约地址",
      txLabel: "交易",
      eventsTitle: "最近事件",
      stateLabels: {
        funded: "已注资",
        review: "审核中",
        "release-ready": "可释放",
        disputed: "争议中",
      },
    },
    report: {
      mapTitle: "地籍 Mock 视图",
      mapDescription: "在一个视图中概览地块状态与权属信息。",
      legendTitle: "图例",
      parcelInfoTitle: "当前地块信息",
      areaLabel: "面积",
      ownerLabel: "权属方",
      statusLabel: "状态",
      statusLabels: {
        available: "可用",
        review: "待审查",
        restricted: "受限",
      },
      streamTitle: "流式报告",
      streamDescription: "在接入 SSE 前，先用 Mock 文本流验证报告渲染结构。",
    },
    tax: {
      calculatorTitle: "税费计算器",
      calculatorDescription: "根据取得价、出售价和持有期限计算基础税费情景。",
      acquisitionLabel: "取得价",
      saleLabel: "出售价",
      deductibleLabel: "可扣除成本",
      holdingYearsLabel: "持有年限",
      acquisitionTaxLabel: "取得税",
      capitalGainsTaxLabel: "资本利得税",
      localTaxLabel: "地方所得税",
      totalTaxLabel: "总税额",
      netLabel: "税后预计金额",
      resetLabel: "恢复默认值",
    },
    inspection: {
      onlineTitle: "现场连接正常",
      offlineTitle: "离线模式已启用",
      onlineDescription: "网络可用，现场状态可以立即同步。",
      offlineDescription: "若网络中断，检查项和照片元数据会先保存在本地，重连后再发送。",
      cachedTitle: "最近缓存快照",
      cachedDescription: "离线作业时，现场团队会基于最近缓存的检查状态和本地队列提示继续工作。",
      cachedAtLabel: "缓存时间",
      checklistTitle: "现场检查清单",
      statusLabels: {
        ready: "已准备",
        pending: "待处理",
        offline: "离线优先",
      },
    },
  },
};

export function getModuleCopy(locale: Locale) {
  return moduleCopy[locale];
}
