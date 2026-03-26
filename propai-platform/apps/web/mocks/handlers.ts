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
  mockSREDashboard,
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
  const url = new URL(path, "http://mock.local");

  return url.pathname
    .replace(/^\/api\/latest/, "")
    .replace(/^\/api\/v1/, "")
    .replace(/\/$/, "");
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
    const detail = mockProjectDetails[projectId];

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

  // Phase 4 — Part-N: SRE 대시보드
  if (normalizedMethod === "GET" && normalizedPath === "/sre/dashboard") {
    return withLatency<T>(mockSREDashboard as T);
  }

  return undefined;
}
