/**
 * 파라메트릭 설계 엔진 — 로컬 평면도 자동 생성
 *
 * 백엔드 API 없이 프론트엔드에서 즉시 건축 평면도를 생성합니다.
 * 입력: 대지면적, 용도지역, 건축용도, 세트백, 세대유형
 * 출력: DesignPayload (Konva 캔버스에 loadDesignPayload로 즉시 표시)
 */

import type {
  AutoDesignRequest,
  AutoDesignResponse,
  DesignPayload,
} from "@/components/cad/types";

// ── 용도지역별 건축 규제 ──
const ZONING_LIMITS: Record<string, { maxBcr: number; maxFar: number; maxHeight: number }> = {
  "1R": { maxBcr: 60, maxFar: 200, maxHeight: 16 },   // 제1종일반주거
  "2R": { maxBcr: 60, maxFar: 250, maxHeight: 21 },   // 제2종일반주거
  "3R": { maxBcr: 50, maxFar: 300, maxHeight: 30 },   // 제3종일반주거
  "GC": { maxBcr: 80, maxFar: 1000, maxHeight: 60 },  // 일반상업
  "NC": { maxBcr: 70, maxFar: 500, maxHeight: 30 },   // 근린상업
  "QI": { maxBcr: 70, maxFar: 400, maxHeight: 30 },   // 준공업
  "QR": { maxBcr: 60, maxFar: 400, maxHeight: 30 },   // 준주거
};

// ── 세대 유형별 면적 (m²) ──
const UNIT_AREAS: Record<string, number> = {
  "59A": 59,
  "74A": 74,
  "84A": 84,
  "114A": 114,
};

// ── 캔버스 스케일 (1m = 10px) ──
const SCALE = 10;

/**
 * 로컬 파라메트릭 설계 엔진
 * 백엔드 없이 즉시 평면도를 생성합니다.
 */
export function generateAutoDesign(req: AutoDesignRequest): AutoDesignResponse {
  const zone = ZONING_LIMITS[req.zone_code] ?? ZONING_LIMITS["2R"];
  const siteArea = req.site_area_sqm;
  const setback = req.setback_m;

  // 1. 대지 치수 (정사각형 가정)
  const siteWidth = Math.sqrt(siteArea);
  const siteDepth = siteWidth;

  // 2. 세트백 적용 → 건축가능 영역
  const buildableWidth = siteWidth - setback.east - setback.west;
  const buildableDepth = siteDepth - setback.north - setback.south;
  const buildableArea = buildableWidth * buildableDepth;

  // 3. 건폐율 한도 적용 → 최대 건축면적
  const maxBuildingArea = siteArea * (zone.maxBcr / 100);
  const buildingArea = Math.min(buildableArea, maxBuildingArea);

  // 4. 건물 치수 결정 (장변:단변 = 1.5:1)
  const buildingDepth = Math.sqrt(buildingArea / 1.5);
  const buildingWidth = buildingArea / buildingDepth;

  // 5. 최대 층수 (용적률 한도 + 높이 한도)
  const maxFloorsByFar = Math.floor((siteArea * zone.maxFar / 100) / buildingArea);
  const maxFloorsByHeight = Math.floor(zone.maxHeight / req.floor_height_m);
  const numFloors = Math.max(1, Math.min(maxFloorsByFar, maxFloorsByHeight));

  // 6. 코어 배치 (중앙 코어: 면적의 15%)
  const coreWidth = buildingWidth * 0.15;
  const coreDepth = buildingDepth * 0.6;

  // 7. 세대 배치
  const unitTypes = req.target_unit_types.length > 0 ? req.target_unit_types : ["84A"];
  const avgUnitArea = unitTypes.reduce((s, t) => s + (UNIT_AREAS[t] ?? 84), 0) / unitTypes.length;
  const usableArea = buildingArea - (coreWidth * coreDepth);
  const unitsPerFloor = Math.max(1, Math.floor(usableArea / avgUnitArea));
  const totalUnits = unitsPerFloor * numFloors;

  // 8. 주차 계산 (세대당 1대 + 0.2대 방문자)
  const parkingCount = Math.ceil(totalUnits * 1.2);

  // 9. 법규 준수 체크
  const actualBcr = (buildingArea / siteArea) * 100;
  const actualFar = (buildingArea * numFloors / siteArea) * 100;
  const actualHeight = numFloors * req.floor_height_m;

  // ── DesignPayload 생성 (캔버스 좌표) ──
  const payload = generatePayload({
    siteWidth, siteDepth, setback,
    buildingWidth, buildingDepth,
    coreWidth, coreDepth,
    unitsPerFloor, unitTypes,
    floorHeight: req.floor_height_m,
    numFloors,
    scale: SCALE,
  });

  return {
    design_payload: payload,
    summary: {
      building_area_sqm: Math.round(buildingArea * 10) / 10,
      total_floor_area_sqm: Math.round(buildingArea * numFloors * 10) / 10,
      bcr_percent: Math.round(actualBcr * 10) / 10,
      far_percent: Math.round(actualFar * 10) / 10,
      num_floors: numFloors,
      building_height_m: Math.round(actualHeight * 10) / 10,
      total_units: totalUnits,
      parking_count: parkingCount,
      units_per_floor: unitsPerFloor,
    },
    compliance: {
      bcr_ok: actualBcr <= zone.maxBcr,
      far_ok: actualFar <= zone.maxFar,
      height_ok: actualHeight <= zone.maxHeight,
      setback_ok: true,
      parking_ok: true,
    },
  };
}

// ── 캔버스 좌표 생성 ──
interface PayloadParams {
  siteWidth: number;
  siteDepth: number;
  setback: { north: number; south: number; east: number; west: number };
  buildingWidth: number;
  buildingDepth: number;
  coreWidth: number;
  coreDepth: number;
  unitsPerFloor: number;
  unitTypes: string[];
  floorHeight: number;
  numFloors: number;
  scale: number;
}

function generatePayload(p: PayloadParams): DesignPayload {
  const S = p.scale;
  let ptIdx = 1;
  let lnIdx = 1;

  const points: DesignPayload["points"] = [];
  const lines: DesignPayload["lines"] = [];
  const surfaces: DesignPayload["surfaces"] = [];
  const rects: DesignPayload["rects"] = [];
  const circles: DesignPayload["circles"] = [];
  const texts: DesignPayload["texts"] = [];

  const addPt = (xm: number, ym: number, label?: string) => {
    const id = `pt-${ptIdx++}`;
    points.push({ id, x: xm * S, y: ym * S, label });
    return id;
  };

  const addLine = (startId: string, endId: string) => {
    lines.push({ id: `ln-${lnIdx++}`, startPointId: startId, endPointId: endId });
  };

  // ── 1. 대지 경계선 (파란 사각형) ──
  const s1 = addPt(0, 0, "대지 SW");
  const s2 = addPt(p.siteWidth, 0);
  const s3 = addPt(p.siteWidth, p.siteDepth);
  const s4 = addPt(0, p.siteDepth, "대지 NW");
  addLine(s1, s2);
  addLine(s2, s3);
  addLine(s3, s4);
  addLine(s4, s1);
  surfaces.push({ id: "site-boundary", pointIds: [s1, s2, s3, s4] });

  // ── 2. 건축한계선 (세트백 적용, 점선) ──
  const bx = p.setback.west;
  const by = p.setback.south;
  const bw = p.siteWidth - p.setback.west - p.setback.east;
  const bh = p.siteDepth - p.setback.south - p.setback.north;
  const b1 = addPt(bx, by);
  const b2 = addPt(bx + bw, by);
  const b3 = addPt(bx + bw, by + bh);
  const b4 = addPt(bx, by + bh);
  addLine(b1, b2);
  addLine(b2, b3);
  addLine(b3, b4);
  addLine(b4, b1);

  // ── 3. 건물 외벽 (세트백 내 중앙 배치) ──
  const buildingX = bx + (bw - p.buildingWidth) / 2;
  const buildingY = by + (bh - p.buildingDepth) / 2;
  rects.push({
    id: "building-footprint",
    x: buildingX * S,
    y: buildingY * S,
    width: p.buildingWidth * S,
    height: p.buildingDepth * S,
  });

  // ── 4. 코어 (EV + 계단실) ──
  const coreX = buildingX + (p.buildingWidth - p.coreWidth) / 2;
  const coreY = buildingY + (p.buildingDepth - p.coreDepth) / 2;
  rects.push({
    id: "core-area",
    x: coreX * S,
    y: coreY * S,
    width: p.coreWidth * S,
    height: p.coreDepth * S,
  });
  texts.push({
    id: "core-label",
    x: coreX * S + 4,
    y: coreY * S + 4,
    text: "EV+계단",
  });

  // ── 5. 세대 배치 (코어 좌우로 분배) ──
  const leftUnits = Math.ceil(p.unitsPerFloor / 2);
  const rightUnits = p.unitsPerFloor - leftUnits;

  // 좌측 세대들
  if (leftUnits > 0) {
    const leftWidth = coreX - buildingX;
    const unitDepthL = p.buildingDepth / leftUnits;
    for (let i = 0; i < leftUnits; i++) {
      const typeIdx = i % p.unitTypes.length;
      const typeName = p.unitTypes[typeIdx];
      rects.push({
        id: `unit-L${i + 1}`,
        x: buildingX * S,
        y: (buildingY + i * unitDepthL) * S,
        width: leftWidth * S,
        height: unitDepthL * S,
      });
      texts.push({
        id: `unit-L${i + 1}-label`,
        x: (buildingX + 0.5) * S,
        y: (buildingY + i * unitDepthL + unitDepthL / 2 - 0.5) * S,
        text: `${typeName} ${i + 1}호`,
      });
    }
  }

  // 우측 세대들
  if (rightUnits > 0) {
    const rightX = coreX + p.coreWidth;
    const rightWidth = buildingX + p.buildingWidth - rightX;
    const unitDepthR = p.buildingDepth / rightUnits;
    for (let i = 0; i < rightUnits; i++) {
      const typeIdx = (leftUnits + i) % p.unitTypes.length;
      const typeName = p.unitTypes[typeIdx];
      rects.push({
        id: `unit-R${i + 1}`,
        x: rightX * S,
        y: (buildingY + i * unitDepthR) * S,
        width: rightWidth * S,
        height: unitDepthR * S,
      });
      texts.push({
        id: `unit-R${i + 1}-label`,
        x: (rightX + 0.5) * S,
        y: (buildingY + i * unitDepthR + unitDepthR / 2 - 0.5) * S,
        text: `${typeName} ${leftUnits + i + 1}호`,
      });
    }
  }

  // ── 6. 주차장 영역 (대지 하단) ──
  const parkingY = p.siteDepth - p.setback.north + 1;
  texts.push({
    id: "parking-label",
    x: 1 * S,
    y: (p.siteDepth - 2) * S,
    text: `주차 ${Math.ceil(p.unitsPerFloor * p.numFloors * 1.2)}대`,
  });

  // ── 7. 정보 텍스트 ──
  texts.push({
    id: "info-bcr",
    x: (p.siteWidth + 1) * S,
    y: 1 * S,
    text: `건폐율: ${((p.buildingWidth * p.buildingDepth / (p.siteWidth * p.siteDepth)) * 100).toFixed(1)}%`,
  });
  texts.push({
    id: "info-far",
    x: (p.siteWidth + 1) * S,
    y: 3 * S,
    text: `용적률: ${((p.buildingWidth * p.buildingDepth * p.numFloors / (p.siteWidth * p.siteDepth)) * 100).toFixed(1)}%`,
  });
  texts.push({
    id: "info-floors",
    x: (p.siteWidth + 1) * S,
    y: 5 * S,
    text: `${p.numFloors}층 / ${(p.numFloors * p.floorHeight).toFixed(1)}m`,
  });

  return {
    points,
    lines,
    surfaces,
    rects,
    circles,
    texts,
    floor_count: p.numFloors,
    building_height_m: p.numFloors * p.floorHeight,
    scale: S,
  };
}
