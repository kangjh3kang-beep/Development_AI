import {
  mockDashboardOverview,
  mockIntegrationStatus,
  mockProjectDetails,
  mockProjectListResponse,
} from "@/mocks/data";
import {
  mockESGDashboardData,
  mockInvestmentMetrics,
  mockIoTDashboardData,
} from "@/mocks/analytics-data";
import { createMockComplianceResponse } from "@/mocks/compliance-data";
import {
  mockDigitalTwinDashboard,
  mockParkingDashboard,
  mockSafetyDashboard,
  mockSTTTranscripts,
} from "@/mocks/phase4-data";

function cloneValue<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

async function withLatency<T>(value: T) {
  await new Promise((resolve) => {
    setTimeout(resolve, 120);
  });

  return cloneValue(value);
}

function normalizePath(path: string) {
  try {
    const url = new URL(path, "http://mock.local");
    return url.pathname
      .replace(/^\/api\/latest/, "")
      .replace(/^\/api\/v1/, "")
      .replace(/^\/api\/v2/, "")
      .replace(/\/$/, "");
  } catch {
    return path.replace(/\/$/, "");
  }
}

export async function resolveMockRequest<T>(method: string, path: string) {
  const normalizedMethod = method.toUpperCase();
  const normalizedPath = normalizePath(path);

  if (normalizedMethod === "GET" && normalizedPath === "/dashboard/overview") {
    return withLatency<T>(mockDashboardOverview as T);
  }

  if (normalizedMethod === "GET" && normalizedPath === "/integration/status") {
    return withLatency<T>(mockIntegrationStatus as T);
  }

  if (normalizedMethod === "GET" && normalizedPath === "/projects") {
    return withLatency<T>(mockProjectListResponse as T);
  }

  const projectDetailMatch = normalizedPath.match(/^\/projects\/([^/]+)$/);

  if (normalizedMethod === "GET" && projectDetailMatch) {
    const projectId = projectDetailMatch[1];
    const detail = mockProjectDetails[projectId] || mockProjectDetails["sample-project"]; // Fallback to sample-project

    if (detail) {
      return withLatency<T>(detail as T);
    }
  }

  // POST /building-compliance/check - 법규 검증 mock
  if (
    normalizedMethod === "POST" &&
    normalizedPath === "/building-compliance/check"
  ) {
    const mockBody = {
      project_id: "mock",
      design: {
        points: [] as Array<{ x: number; y: number }>,
        surfaces: [] as Array<{ pointIds: string[] }>,
        floor_count: 1,
        building_height_m: 3,
        scale: 10,
      },
    };
    return withLatency<T>(createMockComplianceResponse(mockBody) as T);
  }

  // GET /analytics/investment
  if (normalizedMethod === "GET" && normalizedPath === "/analytics/investment") {
    return withLatency<T>(mockInvestmentMetrics as T);
  }

  // GET /analytics/iot
  if (normalizedMethod === "GET" && normalizedPath === "/analytics/iot") {
    return withLatency<T>(mockIoTDashboardData as T);
  }

  // GET /analytics/esg
  if (normalizedMethod === "GET" && normalizedPath === "/analytics/esg") {
    return withLatency<T>(mockESGDashboardData as T);
  }

  // Phase 4 — Part-M: 안전 관제
  if (normalizedMethod === "GET" && normalizedPath === "/safety/dashboard") {
    return withLatency<T>(mockSafetyDashboard as T);
  }

  // Phase 4 — Part-M: 주차 관제
  if (normalizedMethod === "GET" && normalizedPath === "/parking/dashboard") {
    return withLatency<T>(mockParkingDashboard as T);
  }

  // Phase 4 — Part-L: 디지털 트윈
  if (normalizedMethod === "GET" && normalizedPath === "/digital-twin/anomalies") {
    return withLatency<T>(mockDigitalTwinDashboard as T);
  }

  // Phase 4 — Part-L: WebRTC STT 회의록
  if (normalizedMethod === "GET" && normalizedPath === "/webrtc/transcripts") {
    return withLatency<T>(mockSTTTranscripts as T);
  }

  // Stage 4: Feasibility Simulation (Monte Carlo)
  if (
    normalizedMethod === "POST" &&
    normalizedPath.match(/^\/projects\/[^/]+\/simulate-feasibility$/)
  ) {
    return withLatency<T>({
      success: true,
      results: {
        npv_mean_krw: 1250000000 + Math.random() * 100000000,
        roi_mean: 0.184,
        var_5_krw: -210000000, // Matched with widget expectation
        profitability_index: 1.18, // Matched with widget expectation
      },
    } as T);
  }

  // Stage 6: BIM Takeoff (Construction)
  if (
    normalizedMethod === "GET" &&
    normalizedPath.match(/^\/projects\/[^/]+\/bim-takeoff$/)
  ) {
    return withLatency<T>({
      items: [
        { id: "1", code: "A-101", desc: "터파기 및 흙막이 공사", unit: "m3", qty: "4,500.2", rate: "45,000", total: "202,509,000" },
        { id: "2", code: "C-201", desc: "철근 콘크리트 공사 (기초)", unit: "m3", qty: "1,200.5", rate: "180,000", total: "216,090,000" },
        { id: "3", code: "C-305", desc: "조량 철골 공사 (기둥/호이스트)", unit: "ton", qty: "850.2", rate: "2,450,000", total: "2,082,990,000" },
        { id: "4", code: "F-401", desc: "외벽 유리 및 커튼월", unit: "m2", qty: "2,840.0", rate: "320,000", total: "908,800,000" },
        { id: "5", code: "M-501", desc: "설비 및 공조 시스템", unit: "set", qty: "1.0", rate: "509,611,000", total: "509,611,000" },
      ],
    } as T);
  }

  // Stage 3: Design Generation
  if (normalizedMethod === "POST" && normalizedPath === "/design/floor-plan") {
    return withLatency<T>({
      design_id: "mock-plan-001",
      file_url: "/mock/floor-plan.svg",
      room_count: 5,
      generation_method: "AI Generative Model v2",
      vision_validation: { detected_rooms: 5, expected_rooms: 5, confidence: 0.98, match: true },
    } as T);
  }

  if (normalizedMethod === "POST" && normalizedPath === "/bim/generate-ifc") {
    return withLatency<T>({
      id: "mock-ifc-001",
      project_id: "demo",
      total_volume_m3: 15400.5,
      total_area_sqm: 4500,
      material_breakdown: [{ concrete: 0.6 }, { steel: 0.3 }, { glass: 0.1 }],
      element_count: 1250,
      ifc_version: "IFC4",
      created_at: new Date().toISOString(),
    } as T);
  }

  if (normalizedMethod === "POST" && normalizedPath === "/bim/carbon") {
    return withLatency<T>({
      total_embodied_carbon: 450.2,
      total_operational_carbon: 120.5,
      total_carbon: 570.7,
      breakdown: [{ structure: 0.7 }, { envelope: 0.2 }, { systems: 0.1 }],
      reduction_tips: [
        "포졸란멘트 사용으로 탄소발자국 12% 절감 가능",
        "재활용 철강재 비중 확대 권고",
        "단열 성능 15% 상향 시 운영 탄소 8% 추가 절감",
      ],
    } as T);
  }

  // Stage 6: Construction Schedule
  if (
    normalizedMethod === "GET" &&
    normalizedPath.match(/^\/projects\/[^/]+\/construction\/schedule$/)
  ) {
    return withLatency<T>({
      tasks: [
        { task: "대지 경계 측량", dur: 20, complete: true },
        { task: "가설 울타리 설치", dur: 15, complete: true },
        { task: "기초 터파기", dur: 45, complete: false },
        { task: "골조 공사 (B1-B3)", dur: 80, complete: false },
        { task: "지상층 골조 공사", dur: 120, complete: false },
        { task: "마감 및 인테리어", dur: 60, complete: false },
      ],
    } as T);
  }

  // Stage 5: Permit Status & Docs
  if (
    normalizedMethod === "GET" &&
    normalizedPath.match(/^\/projects\/[^/]+\/permit\/status$/)
  ) {
    return withLatency<T>({
      stages: [
        { label: "접수", status: "completed" },
        { label: "심사중", status: "current" },
        { label: "보완 요청", status: "pending" },
        { label: "승인", status: "pending" },
        { label: "착공 신고", status: "pending" },
      ],
      documents: [
        { label: "건축허가 신청서", submitted: true },
        { label: "설계도서", submitted: true },
        { label: "구조안전확인서", submitted: true },
        { label: "환경영향평가서", submitted: false },
        { label: "교통영향평가서", submitted: false },
        { label: "소방시설 설계도", submitted: true },
      ],
    } as T);
  }

  // Stage 8: Operations (FM)
  if (
    normalizedMethod === "GET" &&
    normalizedPath.match(/^\/projects\/[^/]+\/operations\/status$/)
  ) {
    return withLatency<T>({
      kpis: [
        { label: "입주율", value: "94.2%" },
        { label: "월 수익률", value: "5.8%" },
        { label: "관리비 (월)", value: "1,240 만원" },
        { label: "에너지 비용 (월)", value: "450 만원" },
      ],
      maintenance: [
        { label: "다음 정기점검", value: "2026-04-15" },
        { label: "지난 점검일", value: "2026-03-01" },
        { label: "보수 이력", value: "12 건" },
        { label: "긴급 이슈", value: "0 건" },
      ],
      sensors: [
        { label: "온도", value: "22.5 °C", icon: "🌡️" },
        { label: "습도", value: "42.0 %", icon: "💧" },
        { label: "전력 사용량", value: "12,450 kWh", icon: "⚡" },
      ],
    } as T);
  }

  // Stage 1: Site Analysis (Land Info)
  if (
    normalizedMethod === "GET" &&
    normalizedPath.match(/^\/projects\/[^/]+\/site-analysis\/land-info$/)
  ) {
    return withLatency<T>({
      pnu: "1168010100104120002",
      address: "서울 특별시 성동구 성수동2가 125-1",
      area: 452.8,
      zoning: {
        current: "제2종 일반주거지역",
        target: "준주거지역",
        possibility: 85
      },
      geomorphic: {
        slope: 2.5,
        shape: "장방형",
        level: "평지",
        road_contact: "각지(소로)"
      },
      scenarios: [
        { type: "오피스텔", floor_area_ratio: 399.5, coverage_ratio: 58.2, estimated_profit: "상", score: 92 },
        { type: "지식산업센터", floor_area_ratio: 350.0, coverage_ratio: 55.0, estimated_profit: "중", score: 78 }
      ]
    } as T);
  }

  return undefined;
}
