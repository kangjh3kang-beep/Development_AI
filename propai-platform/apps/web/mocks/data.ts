import type {
  DashboardOverviewResponse,
  IntegrationStatusResponse,
  ProjectCard,
  ProjectDetailResponse,
  ProjectListResponse,
} from "@/mocks/types";

export const mockProjects: ProjectCard[] = [
  {
    id: "sample-project",
    name: "성수 복합개발 1차",
    location: "서울 성동구 성수동",
    phase: "사전 사업성 검토",
    updatedAt: "2026-03-18T07:20:00+09:00",
    nextAction: "설계안 2차 시뮬레이션 연결",
    modules: ["design", "finance", "blockchain", "report"],
  },
  {
    id: "river-front",
    name: "한강변 도시정비 검토",
    location: "서울 영등포구 여의도동",
    phase: "규제 및 세금 분석",
    updatedAt: "2026-03-17T16:10:00+09:00",
    nextAction: "세금 시나리오 비교안 정리",
    modules: ["finance", "tax", "report"],
  },
  {
    id: "smart-yard",
    name: "스마트 물류부지 개발",
    location: "경기 화성시 향남읍",
    phase: "현장 점검 준비",
    updatedAt: "2026-03-16T09:40:00+09:00",
    nextAction: "드론 점검 체크리스트 확정",
    modules: ["drone", "inspection", "report"],
  },
];

export const mockProjectListResponse: ProjectListResponse = {
  projects: mockProjects,
  total: mockProjects.length,
  updatedAt: "2026-03-18T07:20:00+09:00",
};

export const mockProjectDetails: Record<string, ProjectDetailResponse> = {
  "sample-project": {
    project: mockProjects[0],
    summary: {
      budget: "총 사업비 1,280억 원 시나리오",
      schedule: "인허가 기준 14개월 예상",
      risk: "전세 리스크 낮음, 규제 검토 필요",
    },
    timeline: [
      "토지 및 용도지역 검토 완료",
      "초기 설계 프롬프트 기준안 작성",
      "사업성 1차 분석 리포트 생성",
    ],
    nextSteps: [
      "설계 모듈과 평면도 생성 UI 연결",
      "금융 분석 응답 스키마와 카드 매핑",
      "에스크로 ABI 수신 후 상태 카드 연결",
    ],
  },
  "river-front": {
    project: mockProjects[1],
    summary: {
      budget: "토지 매입가 재산정 필요",
      schedule: "권리관계 정리 후 10개월 추정",
      risk: "규제 민감도 높음",
    },
    timeline: [
      "규제 텍스트 수집 완료",
      "세금 비교 케이스 초안 작성",
      "투자 민감도 매트릭스 생성",
    ],
    nextSteps: [
      "세금 모듈 계산 폼 연결",
      "경공매 데이터 연동 범위 확정",
      "정책 리스크 경고 문구 정리",
    ],
  },
  "smart-yard": {
    project: mockProjects[2],
    summary: {
      budget: "드론 점검 예산 반영 중",
      schedule: "점검 이후 6개월 내 착공 검토",
      risk: "현장 데이터 부족",
    },
    timeline: [
      "드론 비행 구역 지정",
      "현장 체크리스트 초안 작성",
      "점검 리포트 포맷 정의",
    ],
    nextSteps: [
      "오프라인 점검 플로우 설계",
      "드론 하자 히트맵 UI 연결",
      "현장 사진 업로드 정책 정리",
    ],
  },
};

export const mockDashboardOverview: DashboardOverviewResponse = {
  metrics: [
    {
      id: "projects",
      label: "활성 프로젝트",
      value: "3개",
    },
    {
      id: "modules",
      label: "준비된 모듈 슬롯",
      value: "12개",
    },
    {
      id: "handoff",
      label: "백엔드 연동 대기",
      value: "REST / GraphQL",
    },
  ],
  featuredProjectId: "sample-project",
};

export const mockIntegrationStatus: IntegrationStatusResponse = {
  channels: [
    {
      id: "rest",
      label: "REST API",
      mode: "mock",
      detail: "백엔드 계약 확정 전까지 Mock 어댑터 사용",
    },
    {
      id: "graphql",
      label: "GraphQL",
      mode: "waiting",
      detail: "Apollo 캐시만 준비, 실제 엔드포인트는 대기",
    },
    {
      id: "realtime",
      label: "실시간 스트림",
      mode: "waiting",
      detail: "SSE 유틸만 준비, 서버 이벤트는 미연결",
    },
  ],
};
