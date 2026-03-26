import type { ComplianceCheckResponse } from "@/components/cad/types";

/** 법규 검증 mock 응답 생성. 디자인 페이로드 기반으로 계산. */
export function createMockComplianceResponse(body: {
  project_id: string;
  design: {
    points: Array<{ x: number; y: number }>;
    surfaces: Array<{ pointIds: string[] }>;
    floor_count: number;
    building_height_m: number;
    scale: number;
  };
}): ComplianceCheckResponse {
  const { design } = body;
  const scale = design.scale || 10;

  // 간단한 바운딩 박스 기반 면적 계산
  let totalArea = 0;
  if (design.surfaces.length > 0 && design.points.length >= 3) {
    // Rough area from bounding box of all points
    const xs = design.points.map((p) => p.x / scale);
    const ys = design.points.map((p) => p.y / scale);
    const w = Math.max(...xs) - Math.min(...xs);
    const h = Math.max(...ys) - Math.min(...ys);
    totalArea = w * h;
  }

  const siteArea = 500; // 가정: 대지면적 500m^2
  const bcr = totalArea > 0 ? (totalArea / siteArea) * 100 : 0;
  const far = bcr * design.floor_count;
  const height = design.building_height_m || design.floor_count * 3;

  const bcrLimit = 60;
  const farLimit = 300;
  const heightLimit = 50;
  const setbackLimit = 1.5;
  const sunlightLimit = 2.0;

  const bcrPass = bcr <= bcrLimit;
  const farPass = far <= farLimit;
  const heightPass = height <= heightLimit;

  const violations: ComplianceCheckResponse["violations"] = [];

  if (!bcrPass) {
    violations.push({
      violation_type: "building_coverage",
      severity: "error",
      message: `건폐율 ${bcr.toFixed(1)}%가 한도 ${bcrLimit}%를 초과합니다.`,
      current_value: bcr,
      limit_value: bcrLimit,
    });
  }
  if (!farPass) {
    violations.push({
      violation_type: "floor_area_ratio",
      severity: "error",
      message: `용적률 ${far.toFixed(1)}%가 한도 ${farLimit}%를 초과합니다.`,
      current_value: far,
      limit_value: farLimit,
    });
  }
  if (!heightPass) {
    violations.push({
      violation_type: "max_height",
      severity: "error",
      message: `건물 높이 ${height.toFixed(1)}m가 한도 ${heightLimit}m를 초과합니다.`,
      current_value: height,
      limit_value: heightLimit,
    });
  }

  return {
    is_compliant: violations.length === 0,
    violations,
    building_coverage_ratio: { current: bcr, limit: bcrLimit, pass: bcrPass },
    floor_area_ratio: { current: far, limit: farLimit, pass: farPass },
    max_height: { current: height, limit: heightLimit, pass: heightPass },
    setback: { current: 2.0, limit: setbackLimit, pass: true },
    sunlight: { current: 4.0, limit: sunlightLimit, pass: true },
  };
}
